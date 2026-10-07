"""Source-only chain policy, independent C agreement, and fail-closed inputs.

Tests contain no checkpoint weights or native-array fixture. Fresh official
materialization is an explicit separate integration run under ignored work/.
All acceptance checks use require and remain active under Python -O.
"""
from pathlib import Path
import random
import shutil
import subprocess

import numpy as np
import pytest

from heteronpu.model_geometry import require
from heteronpu import matrix_norm_rope_candidate as q
from heteronpu import rope_bf16_candidate as r

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def references(tmp_path_factory):
    if shutil.which('cc') is None:
        pytest.skip('independent C compiler unavailable')
    directory = tmp_path_factory.mktemp('matrix_norm_rope_c')
    return q._compile_references(ROOT, directory)


@pytest.mark.parametrize('a,b,c,result,flags', [
    (0x3f800001, 0x3f800001, 0xbf800002, 0x28800000, 0),
    (0x7f7fffff, 0x40000000, 0xff7fffff, 0x7f7fffff, 0),
    (0x3f800000, 0x33800000, 0x3f800000, 0x3f800000, 1),
    (0x3f800000, 0x33800000, 0x3f800001, 0x3f800002, 1),
    (1, 0x3f000000, 0, 0, 3),
    (0x80000000, 0x3f800000, 0x80000000, 0x80000000, 0),
    (0x80000000, 0x3f800000, 0, 0, 0),
    (0x3f800000, 0x3f800000, 0xbf800000, 0, 0),
    (0, 0x7f800000, 0, 0x7fc00000, 16),
    (0x7f800000, 0x3f800000, 0xff800000, 0x7fc00000, 16),
    (0x7f800001, 0x3f800000, 0, 0x7fc00000, 16),
    (0x7fc00000, 0x3f800000, 0, 0x7fc00000, 0),
])
def test_fused_single_rounding_specials_and_ties(a, b, c, result, flags):
    require(q.fma_rne(a, b, c) == (result, flags), 'FMA result/flags drift')


def test_fusion_witness_distinguishes_separate_rounding():
    a, b, c = 0x3f800001, 0x3f800001, 0xbf800002
    require(q.fma_rne(a, b, c)[0] == 0x28800000, 'fused witness lost')
    require(r.add_rne(r.mul_rne(a, b)[0], c)[0] == 0, 'unfused witness changed')


def test_integer_fma_against_independent_host_fmaf(references, tmp_path):
    rng = random.Random(0x1024256)
    # Finite full-exponent words include normal/subnormal arithmetic probes.
    # Nonfinite IEEE host NV choice for 0*inf+qNaN is outside chain admission.
    rows = []
    for _ in range(8192):
        rows.append(tuple((rng.getrandbits(1) << 31) | (rng.randrange(255) << 23)
                          | rng.getrandbits(23) for _ in range(3)))
    source, target = tmp_path / 'fma_inputs.bin', tmp_path / 'fma_outputs.bin'
    np.asarray(rows, dtype='<u4').tofile(source)
    subprocess.run([str(references['matrix']), '--fma', str(source), str(target)], check=True)
    actual = np.fromfile(target, dtype='<u4').reshape(-1, 2)
    expected = np.asarray([q.fma_rne(*row) for row in rows], dtype='<u4')
    require(np.array_equal(actual, expected), 'finite integer/host FMA result or flags mismatch')


@pytest.mark.parametrize('bad', [True, -1, 0x100000000, 1.5, np.uint32(1)])
def test_fma_words_reject_coercion(bad):
    for row in ((bad, 0, 0), (0, bad, 0), (0, 0, bad)):
        with pytest.raises(ValueError):
            q.fma_rne(*row)


@pytest.mark.parametrize('field,value', [
    ('role', 'v'), ('role', 0), ('phase', 0), ('phase', 'warm'),
    ('head', True), ('head', -1), ('head', 8), ('head', 1.0),
    ('token', 128), ('token', -1), ('position', 1), ('position', False),
    ('columns', 256), ('columns', 512.0),
])
def test_descriptor_fail_closed(field, value):
    case = {**q.CASES[0], field: value}
    with pytest.raises(ValueError):
        q.validate_descriptor(case)


def test_exact_descriptor_inventory_and_head_offsets():
    for case in q.CASES:
        q.validate_descriptor(case)
    for case in ({k: v for k, v in q.CASES[0].items() if k != 'head'},
                 {**q.CASES[0], 'untrusted': True}, {**q.CASES[3], 'head': 2}):
        with pytest.raises(ValueError):
            q.validate_descriptor(case)
    require(q.CASES[2]['head'] * q.CASES[2]['columns'] == 3584, 'Q final-head offset drift')
    require(q.CASES[3]['head'] * q.CASES[3]['columns'] == 256, 'K final-head offset drift')


@pytest.mark.parametrize('word', [0x0001, 0x807f, 0x7f80, 0xff80, 0x7fc0, 0x7f81])
def test_bf16_input_rejects_subnormal_and_nonfinite(word):
    x = np.zeros(1024, dtype='<u2')
    x[0] = word
    with pytest.raises(ValueError):
        q.bf16_array(x, (1024,), 'input')


def test_bf16_shapes_types_and_raw_encoding_fail_closed():
    for x in (np.zeros(1024, dtype='<u4'), np.zeros(1024, dtype=np.float32),
              np.zeros((1, 1024), dtype='<u2'), np.zeros(1023, dtype='<u2'), [0] * 1024):
        with pytest.raises(ValueError):
            q.bf16_array(x, (1024,), 'input')
    good = np.array([0, 0x8000, 0x0080, 0x7f7f, 0xff7f], dtype='<u2')
    require(q.bf16_array(good, (5,), 'input') is good, 'finite boundary input rejected')
    with pytest.raises(ValueError):
        q.projection_trace(np.zeros(1024, dtype='<u2'), np.zeros((1024, 32), dtype='<u2'))
    with pytest.raises(ValueError):
        q.chain_trace(np.zeros(1024, dtype='<u2'), np.zeros((1024, 256), dtype='<u2'),
                      np.zeros(256, dtype='<u2'), np.zeros(64, dtype='<u2'), role='q')


def test_entire_synthetic_chain_all_steps_c_and_q_gate(references, tmp_path):
    x = np.zeros(1024, dtype='<u2')
    x[0], x[1], x[-1] = 0x3f80, 0x4000, 0xbf80
    w = np.zeros((1024, 512), dtype='<u2')
    w[0] = np.asarray([0x3f00 + (i % 128) for i in range(512)], dtype='<u2')
    w[1] = 0x3c00
    w[-1] = 0x3b80
    nw = np.zeros(256, dtype='<u2')
    trig = np.concatenate((np.full(32, 0x3f80, dtype='<u2'), np.zeros(32, dtype='<u2')))
    trace = q.chain_trace(x, w, nw, trig, role='q')
    crosscheck = q._crosscheck_c(tmp_path, references, x, w, nw, trig, trace)
    require(crosscheck['matrix_accumulator_steps'] == 524288 and crosscheck['pass'], 'incomplete C chain check')
    require(trace['gate_bf16'] == trace['projected']['bf16'][256:], 'Q gate altered')
    expected_norm = tuple(v >> 16 for v in trace['norm']['output_bf16'])
    require(trace['rope_bf16'] == expected_norm, 'zero-angle rotation changed normalization')
    steps = trace['projected']['steps_fp32']
    require(steps.shape == (1024, 512), 'step trace geometry drift')
    require(np.array_equal(steps[0], w[0].astype('<u4') << 16), 'K0 initial accumulator is not +0')
    require(tuple(int(v) for v in steps[-1]) == trace['projected']['fp32'], 'final-step projection link drift')
    tiled = steps.reshape(1024, 16, 32).transpose(1, 0, 2).reshape(-1)
    require(int(tiled[32]) == int(steps[1, 0]) and int(tiled[32768]) == int(steps[0, 32]),
            'tile-major/K-major/lane steps encoding drift')


def test_native_comparison_unchanged_thresholds_and_failure_visible():
    a = np.full(256, 0x3f80, dtype='<u2')
    b = a.copy()
    require(q.compare_native(a, b)['pass'], 'exact native target rejected')
    b[0] = 0x3f88
    result = q.compare_native(a, b)
    require(not result['pass'] and result['max_abs'] == 0.0625 and result['bit_mismatches'] == 1,
            'native failure hidden')
    require(result['thresholds'] == {'max_abs': 0.03125, 'mean_abs': 0.005}, 'native tolerance changed')
    for bad in (np.zeros(255, dtype='<u2'), np.zeros(256, dtype='<u4'), np.array([], dtype='<u2')):
        with pytest.raises(ValueError):
            q.compare_native(a, bad)


def test_extraction_uses_actual_preprojection_operand_and_k_address():
    case = q.CASES[3]
    producers = {}
    for index, shape, value in ((7, (1, 128, 1024), 1.0), (17, (1, 128, 512), 9.0),
                               (25, (1, 128, 2, 256), 3.0), (32, (1, 2, 128, 64), 4.0)):
        producers[f'carried_m128_native_producer_{index:02d}'] = np.full(shape, value, dtype='<f4')
    producers['carried_m128_native_cos'] = np.ones((1, 128, 64), dtype='<f4')
    producers['carried_m128_native_sin'] = np.zeros((1, 128, 64), dtype='<f4')
    weight = np.zeros((512, 1024), dtype='<u2')
    weight[256:] = 0x3f80
    raw = {'self_attn.k_proj.weight': weight.tobytes(),
           'self_attn.k_norm.weight': np.zeros(256, dtype='<u2').tobytes()}
    activation, selected, nw, trig, projected, normalized, rotated = q._extract_case(producers, raw, case)
    require(np.all(activation == 0x3f80) and np.all(projected == 0x4110), 'projection target injected as input')
    require(selected.shape == (1024, 256) and np.all(selected == 0x3f80), 'last K-head selection drift')
    require(np.all(rotated[:64] == 0x4080) and np.all(rotated[64:] == 0x4040), 'native tail assembly drift')
    producers['carried_m128_native_cos'][0, 127, 63] = 0
    with pytest.raises(ValueError):
        q._extract_case(producers, raw, case)


def test_memh_is_fixed_width_raw16_or_fp32_and_rejects_range(tmp_path):
    raw = q._memh(tmp_path / 'words.memh', (0, 0x3f80, 0x8000), width=4)
    require((tmp_path / 'words.memh').read_text() == '0000\n3f80\n8000\n' and raw['words'] == 3,
            'memh raw16 encoding drift')
    for values, width in (((0x10000,), 4), ((-1,), 4), ((True,), 4), ((0,), 16), ((1.0,), 8)):
        with pytest.raises(ValueError):
            q._memh(tmp_path / 'bad.memh', values, width=width)


def test_no_arbitrary_npz_download_or_digest_cli():
    cli = (ROOT / 'scripts/materialize_matrix_norm_rope_vectors.py').read_text()
    require('--input-npz' not in cli and '--trusted' not in cli and '--manifest' not in cli,
            'arbitrary corpus trust override added')
    source = (ROOT / 'src/heteronpu/matrix_norm_rope_candidate.py').read_text()
    require('urlopen' not in source and 'requests.get' not in source, 'arbitrary array downloader added')
