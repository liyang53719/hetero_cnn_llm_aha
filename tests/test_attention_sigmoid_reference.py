from fractions import Fraction
from pathlib import Path
import hashlib
import importlib.util
import json
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'chisel/continuous_prefill'
spec = importlib.util.spec_from_file_location('attention_reference', ROOT / 'scripts/attention_sigmoid_reference.py')
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def test_pinned_official_rule_and_geometry():
    source = (REPO / 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py').read_bytes()
    assert hashlib.sha256(source).hexdigest() == ref.SOURCE_SHA256
    assert b'attn_output = attn_output * torch.sigmoid(gate)' in source
    profile = json.loads((REPO / 'config/model_profiles/qwen3_5_0p8b.json').read_text())
    assert profile['full_attention']['q_heads'] * profile['full_attention']['head_dim'] == 2048


def test_fixed_vectors_and_distinct_bf16_sigmoid_boundary():
    assert json.loads(json.dumps(ref.manifest())) == ref.manifest()
    rows = ref.vectors()
    assert any(ref.bf16(ref.multiply(row['steps'][3]['result'], row['context'] << 16)) != row['output'] for row in rows)
    assert any(ref.bf16(ref.multiply(ref.bf16(ref.multiply(row['steps'][3]['result'], row['gate'] << 16)) << 16,
                                   row['context'] << 16)) != row['output'] for row in rows)
    assert all([step['op'] for step in row['steps']] == [4, 0, 2, 6, 6] for row in rows)
    assert all(row['steps'][-1]['a'] == row['sigmoid'] << 16 for row in rows)


def test_independent_rational_steps_match_native_fp32():
    def fp(bits):
        return np.asarray(bits, dtype='<u4').view('<f4')[()]
    def bits(value):
        return int(np.asarray(value, dtype='<f4').view('<u4'))
    for row in ref.vectors():
        for step in row['steps']:
            a, b = fp(step['a']), fp(step['b'])
            if step['op'] == 0:
                assert bits(np.add(a, b, dtype=np.float32)) == step['result']
            elif step['op'] == 2:
                assert bits(np.divide(a, b, dtype=np.float32)) == step['result']
            elif step['op'] == 6:
                assert bits(np.multiply(a, b, dtype=np.float32)) == step['result']
    # Frozen polynomial constants are pinned to production source construction.
    import math
    assert ref.INV_LN2 == bits(1 / math.log(2))
    assert list(ref.COEFFICIENTS) == [bits((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]


def test_zero_subnormal_rounding_saturation_and_supported_negative_edge():
    assert ref.lane(0, 0x3F80)['output'] == 0x3F00
    assert ref.lane(0x8000, 0x8000)['output'] == 0x8000
    assert ref.lane(1, 1)['output'] == 0
    assert ref.lane(0x8001, 0x8001)['output'] == 0x8000
    assert ref.lane(0, 3)['output'] == 2  # BF16 halfway rounds to even.
    assert ref.lane(0x8000, 0x8003)['output'] == 0x8002
    assert ref.lane(0x42A0, 0x4000)['output'] == 0x4000
    assert ref.lane(0x7F7F, 0xBF80)['output'] == 0xBF80
    assert ref.lane(0xC29F, 0x3F80)['output'] != 0
    assert ref.bf16(0x3F808000) == 0x3F80
    assert ref.bf16(0x3F818000) == 0x3F82
    assert ref.rounded_f32(Fraction(1, 1 << 150)) == 0
    assert ref.rounded_f32(Fraction(3, 1 << 150)) == 2


@pytest.mark.parametrize('gate', [0xC2A0, 0xC2C8, 0xFF7F])
def test_negative_unsupported_domain_is_not_saturated(gate):
    with pytest.raises(ValueError, match='Unsupported'):
        ref.lane(gate, 0x3F80)


@pytest.mark.parametrize('bad', [0x7F80, 0xFF80, 0x7FC0, 0xFFC1])
def test_nonfinite_inputs_fail_closed(bad):
    for gate, context in [(bad, 0x3F80), (0x3F80, bad)]:
        with pytest.raises(ValueError, match='nonfinite'):
            ref.lane(gate, context)


def test_owner_source_has_no_added_arithmetic_resources_and_default_off():
    source = (ROOT / 'src/main/scala/heteronpu/continuous/GdnElementwiseOwner.scala').read_text()
    assert 'val Add = 0; val SiluMul = 1; val SigmoidMul = 2' in source
    assert 'maxTokens: Int = 128, attentionWidth: Int = 2048,' in source
    assert 'enableAttentionSigmoidMul: Boolean = false' in source
    assert 'Module(new' not in source
    assert 'fail(Status.Unsupported.U)' in source and 'F32.lit(80)' in source
    assert 'ScalarOp.MulIeeeRne' in source


def test_runtime_synthetic_fixture_is_regenerated_and_pinned_outside_git(tmp_path):
    import subprocess
    import sys
    import tempfile
    (REPO / 'work').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sigmoid_test_', dir=REPO / 'work') as directory:
        target = Path(directory) / 'vectors.json'
        command = [sys.executable, str(ROOT / 'scripts/attention_sigmoid_reference.py'), '--output', str(target)]
        receipt = json.loads(subprocess.check_output(command, text=True))
        assert receipt['sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert receipt['sha256'] == '40254ca4fffe28d430e755109ee0c4b640b9b3606801fe9ee3b5526b74274779'
        assert json.loads(target.read_text()) == ref.manifest()
        assert subprocess.run(command, capture_output=True).returncode != 0
    outside = tmp_path / 'not_ignored.json'
    rejected = subprocess.run([sys.executable, str(ROOT / 'scripts/attention_sigmoid_reference.py'),
                               '--output', str(outside)], capture_output=True)
    assert rejected.returncode != 0 and not outside.exists()
