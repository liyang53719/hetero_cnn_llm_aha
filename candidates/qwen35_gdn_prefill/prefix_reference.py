"""Independent, pinned official eager RMS and projection prefix comparison.

Only the exact original RMS class is executed from the pinned module AST.
Projection calls preserve the original separate QKV/Z/A/B Linear shapes.
This is an operation reference, not a full official DecoderLayer execution;
there is no cache, conv, GDN recurrence, output projection or FFN in this file.
It must run after actual owner outputs are sealed, never feed those owners.
"""
from __future__ import annotations

import ast
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

import numpy as np

SOURCE = 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'
SOURCE_SHA = 'aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'
MODEL_REVISION = '2fc06364715b967f1860aea9cf38778875588b17'
TRANSFORMERS_REVISION = '14e738b5d0cc69aa27a95dde272aea41fde44f2f'
ROOT = Path(__file__).resolve().parents[2]
GATE_SOURCE = 'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def original_rms_class(raw, torch):
    require(sha(raw) == SOURCE_SHA, 'pinned official source hash changed')
    tree = ast.parse(raw)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Qwen3_5RMSNorm']
    require(len(classes) == 1 and [ast.unparse(d) for d in classes[0].decorator_list] ==
            ["use_kernel_forward_from_hub('RMSNormZeroCentered')"], 'official RMS source dispatch changed')
    namespace = dict(torch=torch, nn=torch.nn,
                     use_kernel_forward_from_hub=lambda name: lambda cls: cls)
    exec(compile(ast.Module(body=classes, type_ignores=[]), SOURCE, 'exec'), namespace)
    return namespace['Qwen3_5RMSNorm']


def native_prefix(hidden_raw, weights, *, root=ROOT):
    """Original BF16 materialization; independent full-shape Linear calls.

    ``weights`` contains the unmodified checkpoint bytes. A and B remain two
    N16 projections; packing them together happens only AFTER these calls.
    """
    import torch
    require(torch.__version__.split('+')[0] == '2.10.0', 'frozen Torch 2.10 required')
    require(isinstance(hidden_raw, bytes) and len(hidden_raw) in (16 * 2048, 128 * 2048),
            'prefix requires an exact M16 or M128 BF16 input')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    capability = torch.backends.cpu.get_cpu_capability()
    require(capability in ('NO AVX', 'DEFAULT', 'AVX2'), 'frozen V8 CPU reduction backend required')
    rows = len(hidden_raw) // 2048
    dtype = torch.bfloat16

    def tensor(name, shape):
        raw = weights[name]
        require(len(raw) == int(np.prod(shape)) * 2, 'original BF16 parameter size: ' + name)
        return torch.frombuffer(bytearray(raw), dtype=dtype).reshape(shape)

    source = (Path(root) / SOURCE).read_bytes()
    norm = original_rms_class(source, torch)(1024).eval()
    norm.weight = torch.nn.Parameter(tensor('input_layernorm.weight', (1024,)), requires_grad=False)
    hidden = torch.frombuffer(bytearray(hidden_raw), dtype=dtype).reshape(1, rows, 1024)
    require(torch.isfinite(hidden).all().item(), 'nonfinite native input')
    with torch.inference_mode():
        normalized = norm(hidden)
        values = {'input_norm': normalized}
        for role, width in (('qkv', 6144), ('z', 2048), ('a', 16), ('b', 16)):
            weight = tensor('linear_attn.in_proj_' + role + '.weight', (width, 1024))
            require(torch.isfinite(weight).all().item(), 'nonfinite native weight')
            values[role] = torch.nn.functional.linear(normalized, weight)
        values['ab'] = torch.cat((values['a'], values['b']), dim=-1)
    require(all(torch.isfinite(v).all().item() for v in values.values()), 'nonfinite official prefix')
    raw = {name: value.contiguous().view(torch.int16).numpy().astype('<i2', copy=False).tobytes()
           for name, value in values.items()}
    receipt = dict(scope='PINNED_OFFICIAL_EAGER_RMS_AND_SEPARATE_LINEAR_OPERATIONS_ONLY',
        model_revision=MODEL_REVISION, transformers_revision=TRANSFORMERS_REVISION,
        official_source_sha256=sha(source), optional_hub_decorator='identity_no_external_kernel',
        hidden_sha256=sha(hidden_raw), rows=rows,
        parameter_sha256={name: sha(data) for name, data in weights.items()},
        backend=dict(torch=torch.__version__, torch_git=torch.version.git_version,
                     cpu_capability=capability, requested_cpu_capability=os.environ.get('ATEN_CPU_CAPABILITY'),
                     machine=platform.machine(), threads=torch.get_num_threads(),
                     deterministic=True, autocast=False, eval=True, float32_matmul_precision='highest',
                     configuration=torch.__config__.show()),
        linear_shapes={'qkv': [rows, 1024, 6144], 'z': [rows, 1024, 2048],
                       'a': [rows, 1024, 16], 'b': [rows, 1024, 16]},
        output_sha256={name: sha(data) for name, data in raw.items()},
        full_official_block_executed=False, hardware_execution=False)
    return raw, receipt


def compare_bf16(actual, expected):
    require(isinstance(actual, bytes) and isinstance(expected, bytes) and
            len(actual) == len(expected) and len(actual) > 0 and len(actual) % 2 == 0,
            'same complete BF16 byte shape required')
    a, b = np.frombuffer(actual, dtype='<u2'), np.frombuffer(expected, dtype='<u2')
    fa, fb = (a.astype('<u4') << 16).view('<f4'), (b.astype('<u4') << 16).view('<f4')
    require(np.isfinite(fa).all() and np.isfinite(fb).all(), 'nonfinite prefix comparison')
    ordered = lambda x: np.where(x & 0x8000, 0x8000 - (x & 0x7fff), 0x8000 + x)
    ulp = np.abs(ordered(a.astype(np.int32)) - ordered(b.astype(np.int32)))
    delta = np.abs(fa.astype(np.float64) - fb.astype(np.float64))
    return dict(elements=int(a.size), bit_mismatches=int(np.count_nonzero(a != b)),
                numerical_mismatches=int(np.count_nonzero(ulp)), max_bf16_ulp=int(ulp.max()),
                max_abs=float(delta.max()), mean_abs=float(delta.mean()),
                signed_zero_only_mismatches=int(np.count_nonzero((a != b) & (ulp == 0))),
                first_bit_mismatch=None if np.array_equal(a, b) else int(np.flatnonzero(a != b)[0]),
                actual_sha256=sha(actual), expected_sha256=sha(expected),
                acceptance='DIAGNOSTIC_NO_NEW_STAGE_THRESHOLD_ASSIGNED')


def original_prefix_gate(actual, expected, *, root=ROOT):
    raw=(Path(root)/GATE_SOURCE).read_bytes()
    contract=json.loads(raw)['native_thresholds']
    require(contract['projection_max_abs']==0.03125 and contract['projection_mean_abs']==0.005,
            'original GDN native thresholds changed')
    result=compare_bf16(actual,expected)
    result.update(thresholds=dict(max_abs=0.03125,mean_abs=0.005),
                  gate_source=GATE_SOURCE,gate_source_sha256=sha(raw),
                  acceptance='ORIGINAL_NATIVE_PER_NODE_THRESHOLDS_PREFIX_SCOPE_ONLY',
                  passed=result['max_abs']<=0.03125 and result['mean_abs']<=0.005)
    return result


def rms_recipe(hidden_raw, weight_raw, policy):
    """Independent array schedule, not the owner's Scalar or memory machine."""
    require(len(hidden_raw) % 2048 == 0 and len(weight_raw) == 2048, 'RMS raw shape')
    x = (np.frombuffer(hidden_raw, '<u2').astype('<u4') << 16).view('<f4').reshape(-1, 1024)
    w = (np.frombuffer(weight_raw, '<u2').astype('<u4') << 16).view('<f4')
    sq = np.multiply(x, x, dtype=np.float32)
    total = np.zeros((len(x), 1), dtype=np.float32)
    if policy == 'legacy_ascending':
        for index in range(1024): total = np.add(total, sq[:, index:index+1], dtype=np.float32)
    elif policy == 'torch210_cpu_default1024':
        for lane in range(8):
            lane_sum = np.zeros_like(total)
            for residue in range(4):
                residue_sum = np.zeros_like(total)
                for block in range(2):
                    block_sum = np.zeros_like(total)
                    for term in range(16):
                        index = block*512 + term*32 + residue*8 + lane
                        block_sum = np.add(block_sum, sq[:, index:index+1], dtype=np.float32)
                    residue_sum = np.add(residue_sum, block_sum, dtype=np.float32)
                lane_sum = np.add(lane_sum, residue_sum, dtype=np.float32)
            total = np.add(total, lane_sum, dtype=np.float32)
    else: raise ValueError('unsupported explicit RMS reference policy')
    mean = np.multiply(total, np.float32(1/1024), dtype=np.float32)
    variance = np.add(mean, np.float32(1e-6), dtype=np.float32)
    inverse = np.divide(np.float32(1), np.sqrt(variance, dtype=np.float32), dtype=np.float32)
    normalized = np.multiply(x, inverse, dtype=np.float32)
    output = np.multiply(normalized, np.add(np.float32(1), w, dtype=np.float32), dtype=np.float32)
    require(np.isfinite(output).all(), 'nonfinite RMS recipe')
    u = output.view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2').tobytes()


def build_projection_reference(output, *, root=ROOT):
    """A small independent C++ reference, used only after actual completion."""
    output, root = Path(output), Path(root)
    require(not output.exists(), 'reference output must be fresh')
    source = root / 'candidates/qwen35_gdn_prefill/projection_reference.cpp'
    compiler = shutil.which('g++')
    require(compiler is not None, 'g++ reference compiler unavailable')
    before = sha(source.read_bytes())
    output.mkdir(parents=True)
    library = (output / 'projection_reference.so').resolve()
    argv = [compiler, '-std=c++17', '-O2', '-fPIC', '-shared', '-fno-fast-math',
            '-ffp-contract=off', '-frounding-math', str(source.resolve()), '-o', str(library)]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    receipt = dict(source=str(source.relative_to(root)), source_sha256=before,
        source_unchanged=sha(source.read_bytes()) == before, argv=argv,
        compiler=str(Path(compiler).resolve()),
        compiler_sha256=sha(Path(compiler).resolve().read_bytes()),
        compiler_version=subprocess.check_output([compiler, '--version'], text=True),
        returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        library=str(library), library_sha256=sha(library.read_bytes()) if library.is_file() else None)
    (output / 'compile.json').write_text(json.dumps(receipt, indent=2) + '\n')
    require(result.returncode == 0 and receipt['source_unchanged'], 'reference build failed/source changed')
    return receipt


def projection_reference(receipt, actual_input, original_weight, rows, columns, *, root=ROOT):
    """Independent sequential-K FMA, retaining the checkpoint N×K layout."""
    require(receipt['returncode'] == 0 and receipt['source_unchanged'] and
            sha(Path(receipt['library']).read_bytes()) == receipt['library_sha256'] and
            sha((Path(root) / receipt['source']).read_bytes()) == receipt['source_sha256'],
            'independent projection reference identity drift')
    require(type(rows) is int and type(columns) is int and 0 < rows <= 128 and 0 < columns < 65536,
            'projection geometry')
    require(type(actual_input) is bytes and type(original_weight) is bytes and
            len(actual_input) == rows * 1024 * 2 and len(original_weight) == columns * 1024 * 2,
            'full raw BF16 projection input/weight shape')
    lib = C.CDLL(receipt['library'])
    u16 = C.POINTER(C.c_uint16)
    fn = lib.gdn_projection_reference
    fn.argtypes, fn.restype = [C.c_uint] * 3 + [u16] * 3, C.c_int
    a = (C.c_uint16 * (rows * 1024)).from_buffer_copy(actual_input)
    b = (C.c_uint16 * (columns * 1024)).from_buffer_copy(original_weight)
    out = (C.c_uint16 * (rows * columns))()
    require(fn(rows, 1024, columns, a, b, out) == 0, 'independent projection arithmetic failure')
    return bytes(out)
