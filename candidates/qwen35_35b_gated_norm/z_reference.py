"""Pinned original Z K2048/N4096 vs independent strict C, diagnostics only.

No full model, owner, N8192/N32 gate inheritance, or norm operation is executed.
The original constructor, single full-width Linear call and reshape AST are
executed unchanged. The separately pinned payload module owns weight selection.
"""
from __future__ import annotations

import argparse
import ast
import ctypes as C
import hashlib
import inspect
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time
from types import SimpleNamespace

from candidates.qwen35_35b_rms import reference as rms
from candidates.qwen35_35b_projection_reference.run_reference import FLAGS, record

ROOT = Path(__file__).resolve().parents[2]
K, N, HEADS, HEAD_DIM = 2048, 4096, 32, 128
WEIGHT_KEY = 'layers.0.linear_attn.in_proj_z.weight'


def require(ok, why):
    if not ok:
        raise ValueError('35B Z reference: ' + why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'SHA256 pin required')
    return value


def geometry(m, n=N, k=K):
    require(type(m) is int and m in (16, 128) and
            type(n) is int and n == N and type(k) is int and k == K,
            'only M16/M128, N4096, K2048; no inherited projection shape')
    return m, n, k


def operators(root=ROOT):
    """Pure pinned AST/geometry verification; no Torch or payload reads."""
    root = Path(root)
    source_identity = rms.source_identity(root)
    raw = (root / rms.SOURCE).read_bytes()
    tree = ast.parse(raw)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and
               n.name == 'Qwen3_5MoeGatedDeltaNet']
    require(len(classes) == 1, 'one original GatedDeltaNet class')
    cls = classes[0]
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    forward = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'forward')
    constructors = [n for n in init.body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Attribute) and t.attr == 'in_proj_z' for t in n.targets)]
    z_assignments = [n for n in forward.body if isinstance(n, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == 'z' for t in n.targets)]
    require(len(constructors) == 1 and len(z_assignments) == 3, 'original Z statement count')
    assignment, call, reshape = constructors[0], z_assignments[0], z_assignments[1]
    expected = [
        'self.in_proj_z = nn.Linear(self.hidden_size, self.value_dim, bias=False)',
        'z = self.in_proj_z(hidden_states)',
        'z = z.reshape(batch_size, seq_len, -1, self.head_v_dim)',
    ]
    require([ast.unparse(n) for n in (assignment, call, reshape)] == expected,
            'exact original Z constructor, full-N4096 call and head reshape')
    config = json.loads((root / rms.CONFIG).read_bytes())['text_config']
    require((config['hidden_size'], config['linear_num_value_heads'],
             config['linear_value_head_dim']) == (K, HEADS, HEAD_DIM),
            'original hidden/value geometry drift')
    require(config['linear_num_value_heads'] * config['linear_value_head_dim'] == N,
            'original full N4096 width')
    return (assignment, call, reshape), dict(
        source={key: source_identity[key] for key in
                ('model_revision', 'transformers_revision', 'source', 'source_sha256', 'config_sha256')},
        class_name=cls.name, operator=expected,
        operator_lines=[[n.lineno, n.end_lineno] for n in (assignment, call, reshape)],
        ast_sha256=sha('\n'.join(ast.dump(n, include_attributes=False)
                                 for n in (assignment, call, reshape)).encode()),
        full_n_call=True, m_choices=[16, 128], k=K, n=N, heads=HEADS, head_dim=HEAD_DIM)


def compile_node(node):
    return compile(ast.Module(body=[node], type_ignores=[]), rms.SOURCE, 'exec')


def actual_rms_input(directory, summary_sha, m, *, case_name=None, input_name=None):
    """Require a raw actual RMS publication covered by a pinned producer summary.

    New prefix summaries may use explicit names but must retain the same
    cases[].official_output and cases[].owner evidence contract. No slice,
    numerical replacement, official-output fallback or filename inference.
    """
    geometry(m)
    directory = Path(directory).resolve(strict=True)
    summary_path = directory / 'summary.json'
    raw = summary_path.read_bytes()
    require(sha(raw) == digest(summary_sha), 'actual RMS producer summary pin')
    summary = json.loads(raw)
    case_name = case_name or f'actual_embedding_rms_m{m}'
    cases = [c for c in summary['cases'] if c['name'] == case_name]
    require(len(cases) == 1, 'one exact actual RMS case')
    case = cases[0]
    official, owner = case['official_output'], case['owner']
    require(official['bit_mismatches'] == 0 and owner['output_published'] is True and
            owner['complete'] is True, 'accepted complete actual RMS publication')
    input_path = (directory / (input_name or f'{case_name}.actual_output.bin')).resolve(strict=True)
    require(input_path.is_relative_to(directory), 'RMS input stays in producer directory')
    input_raw = input_path.read_bytes()
    observed = sha(input_raw)
    require(len(input_raw) == m * K * 2 and
            observed == official['actual_sha256'] == official['expected_sha256'] == owner['output_sha256'],
            'actual RMS raw length/identity and producer-output agreement')
    return input_raw, input_path, summary_path, case_name


def diagnostics(actual, official, m):
    from candidates.qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
    geometry(m)
    require(type(actual) is bytes and type(official) is bytes and
            len(actual) == len(official) == m * N * 2, 'complete MxN4096 comparison')
    result = compare_finite_bf16(actual, official)
    first = result['first_bit_mismatch']
    result.update(passed=None, thresholds=None,
                  bitexact_observed=result['bit_mismatches'] == 0,
                  first_coordinate=None if first is None else dict(row=first // N, column=first % N),
                  diagnostic_only=True, native_acceptance=False)
    return result


def build_reference(out):
    source = Path(__file__).with_name('reference.c')
    executable = shutil.which('gcc')
    require(executable is not None, 'gcc required')
    compiler = Path(executable).resolve(strict=True)
    library = out / 'z_reference.so'
    command = [str(compiler), *FLAGS, str(source), '-o', str(library), '-lm']
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    evidence = {}
    for name, argv in (
        ('disassembly', ['objdump', '-dr', str(library)]),
        ('dynamic_symbols', ['readelf', '--dyn-syms', '--wide', str(library)]),
        ('ldd', ['ldd', str(library)]),
        ('compiler_version', [str(compiler), '--version']),
    ):
        text = subprocess.check_output(argv, text=True, timeout=30)
        path = out / ('z_reference.' + name + '.txt')
        path.write_text(text)
        evidence[name] = record(path)
        if name == 'dynamic_symbols':
            require(any('UND' in line and 'fmaf@' in line for line in text.splitlines()),
                    'unresolved external versioned libm fmaf symbol')
        if name == 'disassembly':
            require(('ordered_fmaf' in text or 'fmaf@' in text) and 'z_reference_run' in text,
                    'disassembled ordered fmaf pointer and N4096 entry')
        if name == 'ldd':
            libms = [line.split('=>')[1].split()[0] for line in text.splitlines()
                     if 'libm.so' in line and '=>' in line]
            require(len(libms) == 1, 'one linked libm')
            evidence['libm'] = record(Path(libms[0]))
    native = C.CDLL(str(library))
    for name in ('self_test', 'environment'):
        fn = getattr(native, 'z_reference_' + name)
        fn.argtypes, fn.restype = [], C.c_int
    for name in ('mxcsr', 'n', 'k'):
        fn = getattr(native, 'z_reference_' + name)
        fn.argtypes, fn.restype = [], C.c_uint
    native.z_reference_run.argtypes = [C.c_uint, C.c_uint] + [C.c_void_p] * 5
    native.z_reference_run.restype = C.c_int
    require((native.z_reference_n(), native.z_reference_k()) == (N, K), 'new C N4096/K2048 ABI')
    require(native.z_reference_self_test() == 0, 'FMA/RNE/partialAdd/gradual-underflow/FTZ selftests')
    evidence.update(compiler=record(compiler), compile_argv=command,
                    reference_library=record(library), selftest_passed=True,
                    selftest_cases=['fused_rounding_witness', 'bf16_positive_negative_ties_even',
                                    'bf16_subnormal_ties', 'fp32_partialAdd_ties_even',
                                    'gradual_fmaf', 'reject_FTZ_DAZ', 'reject_MXCSR_non_RNE', 'reject_non_RNE'],
                    mxcsr=native.z_reference_mxcsr())
    return native, evidence


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m', type=int, choices=(16, 128), required=True)
    ap.add_argument('--payload', type=Path, required=True)
    ap.add_argument('--manifest-sha256', required=True)
    ap.add_argument('--rms-output', type=Path, required=True)
    ap.add_argument('--rms-summary-sha256', required=True)
    ap.add_argument('--rms-case-name')
    ap.add_argument('--rms-input-name')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--preflight-only', action='store_true')
    args = ap.parse_args()
    geometry(args.m)
    digest(args.manifest_sha256)
    digest(args.rms_summary_sha256)
    out = args.out.resolve()
    require(not out.exists() and not args.out.is_symlink() and out.is_relative_to(ROOT / 'work'),
            'fresh ignored output under work/')
    nodes, operator = operators()
    input_raw, input_path, summary_path, case_name = actual_rms_input(
        args.rms_output, args.rms_summary_sha256, args.m,
        case_name=args.rms_case_name, input_name=args.rms_input_name)
    # Deferred import allows pure AST/shape tests before the new payload is present.
    from candidates.qwen35_35b_gated_norm import payload
    manifest, values = payload.load(args.payload, args.manifest_sha256)
    weight_raw = values[WEIGHT_KEY]
    require(type(weight_raw) is bytes and len(weight_raw) == N * K * 2,
            'complete original BF16 weight[N4096,K2048]')
    del values
    out.mkdir(parents=True, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    signal.alarm(120)
    import numpy as np
    import torch
    from candidates.qwen35_gdn_prefill import prefill_bf16_compare
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    require(torch.set_flush_denormal(False), 'gradual underflow')
    runtime = rms.runtime_identity()
    a = np.frombuffer(input_raw, '<u2').copy().reshape(args.m, K)
    w = np.frombuffer(weight_raw, '<u2').copy().reshape(N, K)
    require(not np.any((a & 0x7f80) == 0x7f80) and
            not np.any((w & 0x7f80) == 0x7f80), 'finite actual input and Z weights')
    frozen_paths = [Path(__file__), Path(__file__).with_name('reference.c'),
                    Path(payload.__file__), Path(rms.__file__), Path(prefill_bf16_compare.__file__),
                    ROOT / rms.SOURCE, ROOT / rms.CONFIG,
                    ROOT / 'candidates/qwen35_35b_projection_reference/run_reference.py',
                    Path(inspect.getfile(torch.nn.Linear)),
                    Path(runtime['runtime_root']) / 'python.sh']
    frozen = {str(p.resolve()): sha(p.read_bytes()) for p in frozen_paths}
    native, c_evidence = build_reference(out)
    obj = SimpleNamespace(hidden_size=K, value_dim=N, head_v_dim=HEAD_DIM)
    scope = dict(self=obj, nn=torch.nn, batch_size=1, seq_len=args.m,
                 hidden_states=torch.from_numpy(a).view(torch.bfloat16).reshape(1, args.m, K))
    with torch.device('meta'):
        exec(compile_node(nodes[0]), scope)
    layer = obj.in_proj_z
    layer.weight = torch.nn.Parameter(torch.from_numpy(w).view(torch.bfloat16), requires_grad=False)
    layer.eval()
    require(layer.bias is None and (layer.in_features, layer.out_features) == (K, N),
            'original bias-free complete N4096 layer')
    report = dict(
        schema_version=1, status='PREFLIGHT_ONLY_Z_N4096_DIAGNOSTICS',
        scope='ORIGINAL_Z_FULL_N4096_VS_INDEPENDENT_C_DIAGNOSTICS_ONLY',
        m=args.m, n=N, k=K, passed=None, thresholds=None,
        original_operator=operator, input=record(input_path), producer_report=record(summary_path),
        producer_case=case_name, payload_manifest=record(args.payload / 'manifest.json'),
        weight=dict(key=WEIGHT_KEY, bytes=len(weight_raw), sha256=sha(weight_raw), shape=[N, K]),
        source_frozen=frozen, runtime=runtime, c_reference=c_evidence, results={},
        claim_boundary=dict(
            full_native_forward=False, actual_z_owner_executed=False, norm_executed=False,
            rtl_executed=False, new_n4096_profile_admitted=False,
            n8192_profile_inherited=False, n32_profile_inherited=False,
            full_checkpoint_sha256_verified=False,
            payload_hashes_are_first_acquisition_observations=True,
            host_seconds_are_not_hardware_cycles=True,
            independently_computed_from_actual_rms_input=True))
    (out / 'preflight.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    if args.preflight_only:
        signal.alarm(0)
        print(json.dumps(dict(status=report['status'], m=args.m)), flush=True)
        return
    started = time.monotonic()
    with torch.inference_mode(), torch.autocast(device_type='cpu', enabled=False):
        exec(compile_node(nodes[1]), scope)  # Exactly one original full-N4096 call.
        y = scope['z']
        require(tuple(y.shape) == (1, args.m, N) and y.dtype == torch.bfloat16,
                'original full N4096 shape/dtype')
        official = y.contiguous().view(torch.uint16).numpy().tobytes()
        exec(compile_node(nodes[2]), scope)
        require(tuple(scope['z'].shape) == (1, args.m, HEADS, HEAD_DIM), 'original head reshape')
    require(native.z_reference_environment() == 0, 'environment after original operator')
    official_path = out / 'z.official.bf16le'
    official_path.write_bytes(official)
    report['official'] = record(official_path)
    report['official_seconds'] = time.monotonic() - started
    for mode, label in ((0, 'sequential_k2048'), (1, 'pair_hi_first_two_k1024')):
        words = np.zeros((args.m, N), '<u2')
        pre = np.zeros((args.m, N), '<f4')
        counts = np.zeros(3, '<u8')
        then = time.monotonic()
        require(native.z_reference_run(args.m, mode, a.ctypes.data, w.ctypes.data,
                                       words.ctypes.data, pre.ctypes.data, counts.ctypes.data) == 0,
                'strict independent N4096 C recipe')
        require(int(counts[0]) == args.m * N * K and
                int(counts[2]) == (args.m * N if mode else 0), 'complete full-shape C arithmetic counts')
        output_path, pre_path = out / ('z.' + label + '.bf16le'), out / ('z.' + label + '.fp32le')
        output_path.write_bytes(words.tobytes())
        pre_path.write_bytes(pre.tobytes())
        report['results'][label] = dict(
            diagnostics(words.tobytes(), official, args.m),
            output=record(output_path), pre_bf16=record(pre_path),
            diagnostic_fma_calls=int(counts[0]),
            diagnostic_fp32_fma_subnormal_observations=int(counts[1]),
            diagnostic_partialAdd_calls=int(counts[2]), seconds=time.monotonic() - then)
    report['sources_unchanged'] = all(sha(Path(p).read_bytes()) == h for p, h in frozen.items())
    require(report['sources_unchanged'], 'reference source drift')
    require(sha(input_path.read_bytes()) == sha(input_raw) and
            sha(summary_path.read_bytes()) == args.rms_summary_sha256 and
            sha((args.payload / 'manifest.json').read_bytes()) == args.manifest_sha256,
            'input or producer/manifest drift during diagnostics')
    require(native.z_reference_environment() == 0, 'final strict floating-point environment')
    report.update(status='COMPLETE_Z_N4096_DIAGNOSTICS_NO_ADMISSION',
                  numeric_seconds=time.monotonic() - started, mxcsr_after=native.z_reference_mxcsr(),
                  peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    signal.alarm(0)
    print(json.dumps(dict(status=report['status'], m=args.m, passed=None, thresholds=None,
                          seconds=report['numeric_seconds'])), flush=True)


if __name__ == '__main__':
    main()
