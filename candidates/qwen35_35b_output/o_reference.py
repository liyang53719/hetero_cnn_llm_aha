"""Original full O K4096/N2048 vs independent strict C; no recipe admission.

Default invocation is provenance/AST/C-selftest only. Full-shape numerical
calibration requires explicit --execute-full-reference through the pinned CPU
runtime. No weights are downloaded, no owner is run, and actual gated_norm
producer bytes are never replaced by same-input official/reference values.
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
K, N, HEADS, HEAD_DIM = 4096, 2048, 32, 128
WEIGHT_KEY = 'layers.0.linear_attn.out_proj.weight'
STAGES = ('input_norm', 'qkv_columns_0', 'conv4_silu', 'a', 'b', 'ab_pack',
          'prep', 'z', 'chunk', 'gated_norm')
ACTUAL_INPUT_PINS = {
    16: dict(summary_sha256='513b6f784a12fb00fc70f05b3b46d26d955051babd956f2237bd69b48db71050',
             input_sha256='0a9fcd787f2df95e3be9b1db4ab455ed6b8b3764ab40d32f4acc37ceed444109'),
    128: dict(summary_sha256='28a791eed33c431cba7df2913d827a22015567587ea6a5e8274ecc552cf9c55d',
              input_sha256='e79c74cec5c6013c80b1c3c7a8873f36b7f9ef4d7b96657a25e5e8544f015014'),
}
RECIPES = (
    dict(mode=0, name='sequential_k4096', parts=1, span=K, pair_high=False,
         merges='none', partial_adds_per_output=0),
    dict(mode=1, name='pair_high_full_k4096', parts=1, span=K, pair_high=True,
         merges='none', partial_adds_per_output=0),
    dict(mode=2, name='pair_high_two_independent_k2048', parts=2, span=2048, pair_high=True,
         merges='add_rne(p0,p1)', partial_adds_per_output=1),
    dict(mode=3, name='pair_high_four_independent_k1024_leftfold', parts=4, span=1024, pair_high=True,
         merges='add_rne(add_rne(add_rne(p0,p1),p2),p3)', partial_adds_per_output=3),
    dict(mode=4, name='pair_high_four_independent_k1024_balanced', parts=4, span=1024, pair_high=True,
         merges='add_rne(add_rne(p0,p1),add_rne(p2,p3))', partial_adds_per_output=3),
)
SELFTEST_CASES = [
    'fused_rounding_witness', 'bf16_positive_negative_ties_even', 'bf16_subnormal_ties',
    'fp32_partialAdd_ties_even', 'gradual_fmaf', 'reject_FTZ_DAZ',
    'reject_MXCSR_non_RNE', 'reject_non_RNE', 'five_recipe_k8_counts_and_results',
    'seeded_continuation_vs_independent_partials', 'leftfold_vs_balanced_witness',
    'ascending_vs_pair_high_witness',
]


def require(ok, why):
    if not ok:
        raise ValueError('35B O reference: ' + why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'SHA256 pin required')
    return value


def geometry(m, n=N, k=K):
    require(type(m) is int and m in (16, 128) and
            type(n) is int and n == N and type(k) is int and k == K,
            'only M16/M128, N2048, K4096; no inherited projection shape')
    return m, n, k


def operators(root=ROOT):
    """Pure pinned original AST verification, without importing Torch."""
    root = Path(root)
    identity = rms.source_identity(root)
    tree = ast.parse((root / rms.SOURCE).read_bytes())
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and
               n.name == 'Qwen3_5MoeGatedDeltaNet']
    require(len(classes) == 1, 'one original GatedDeltaNet class')
    cls = classes[0]
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
    forward = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'forward')
    constructors = [n for n in init.body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Attribute) and t.attr == 'out_proj' for t in n.targets)]
    cores = [n for n in forward.body if isinstance(n, ast.Assign) and
             any(isinstance(t, ast.Name) and t.id == 'core_attn_out' for t in n.targets)]
    outputs = [n for n in forward.body if isinstance(n, ast.Assign) and
               any(isinstance(t, ast.Name) and t.id == 'output' for t in n.targets)]
    require(len(constructors) == 1 and len(cores) == 3 and len(outputs) == 1,
            'original O statement counts')
    nodes = (constructors[0], cores[-1], outputs[0])
    expected = [
        'self.out_proj = nn.Linear(self.value_dim, self.hidden_size, bias=False)',
        'core_attn_out = core_attn_out.reshape(batch_size, seq_len, -1)',
        'output = self.out_proj(core_attn_out)',
    ]
    require([ast.unparse(n) for n in nodes] == expected,
            'exact original O constructor, flatten and full-N2048 Linear call')
    config = json.loads((root / rms.CONFIG).read_bytes())['text_config']
    require((config['hidden_size'], config['linear_num_value_heads'],
             config['linear_value_head_dim']) == (N, HEADS, HEAD_DIM),
            'original hidden/value geometry drift')
    require(HEADS * HEAD_DIM == K, 'complete original K4096 input')
    return nodes, dict(
        source={key: identity[key] for key in
                ('model_revision', 'transformers_revision', 'source', 'source_sha256', 'config_sha256')},
        class_name=cls.name, operator=expected,
        operator_lines=[[n.lineno, n.end_lineno] for n in nodes],
        ast_sha256=sha('\n'.join(ast.dump(n, include_attributes=False) for n in nodes).encode()),
        full_n_call=True, linear_call_count=1, original_bias=False,
        m_choices=[16, 128], k=K, n=N, heads=HEADS, head_dim=HEAD_DIM)


def compile_node(node):
    return compile(ast.Module(body=[node], type_ignores=[]), rms.SOURCE, 'exec')


def actual_gated_norm_input(directory, summary_sha, m):
    """Consume exactly one actual owner publication named by its pinned summary.

    Historical source snapshots must match before/after. They are not silently
    rebound to current modified files. Their authenticity is the external summary
    pin; the original modeling source/config are separately pinned by operators().
    This is transport/publication acceptance, not norm numerical acceptance.
    """
    geometry(m)
    directory = Path(directory).resolve(strict=True)
    summary_path = directory / 'summary.json'
    raw = summary_path.read_bytes()
    require(sha(raw) == digest(summary_sha), 'actual gated_norm producer summary pin')
    summary = json.loads(raw)
    require(type(summary['tokens']) is int and summary['tokens'] == m and
            summary['gated_norm_requested'] is True, 'producer complete requested M shape')
    before, after = summary['source_sha256'], summary['source_sha256_after']
    require(isinstance(before, dict) and len(before) > 0 and before == after and
            summary['sources_unchanged'] is True, 'producer source_before/source_after agreement')
    for key, value in before.items():
        require(isinstance(key, str) and bool(key), 'producer source name')
        digest(value)
    execution = summary['execution']
    require(execution['status'] == 'PASS_TYPED_GATED_NORM_PREFIX_EXECUTION_ONLY' and
            execution['tokens'] == m, 'successful producer execution scope')
    terminals, stages = execution['terminals'], execution['stages']
    require(isinstance(terminals, list) and len(terminals) == len(STAGES) and
            [t['stage'] for t in terminals] == list(STAGES) and
            all('status' in t and t['status'] is None for t in terminals),
            'exact ten successful producer terminals')
    require(isinstance(stages, list) and len(stages) == len(STAGES) and
            [s['stage'] for s in stages] == list(STAGES) and
            all(s['report']['complete'] is True and s['report'].get('status') is None for s in stages),
            'exact ten complete producer stages')
    matches = [o for o in summary['observations'] if o['stage'] == 'gated_norm']
    require(len(matches) == 1, 'one exact actual gated_norm observation')
    observation = matches[0]
    output, owner = observation['output'], observation['owner']
    require(owner == stages[-1]['report'], 'observation agrees with executed gated_norm owner')
    require(owner['complete'] is True and owner['output_published'] is True and
            owner['staging_complete'] is True and 'status' in owner and owner['status'] is None,
            'complete/published successful actual gated_norm owner')
    real = owner['owner']
    original = real['identity']['grouped_source']['source_sha256']
    require(original.get(rms.SOURCE) == rms.SOURCE_SHA and original.get(rms.CONFIG) == rms.CONFIG_SHA,
            'producer original source/config pins')
    require(real['scope'] == 'GDN_GATED_NORM_SOFTWARE_OWNER' and
            real['active_heads'] == HEADS and real['row_bytes'] == K * 2 and
            real['production_geometry'] is True and real['test_only_zero_filled_heads'] == 0 and
            real['status'] is None, 'real full-head gated_norm owner geometry')
    size = m * K * 2
    accepted = real['accepted']
    reads, writes = (2 * size + 512) // 64, size // 64
    require(accepted['owner_results'] == 1 and accepted['read_requests'] == reads and
            accepted['write_requests'] == accepted['write_acks'] == writes and
            accepted['memory_responses'] == reads + writes and
            real['acknowledged_write_bytes'] == size and owner['counts']['write_bytes'] == size and
            owner['counts']['read_bytes'] == 2 * size + 512,
            'accepted full-shape gated_norm memory/results/write acknowledgements')
    require(type(output['bytes']) is int and output['bytes'] == size, 'full MxK4096 BF16 publication length')
    input_path = Path(output['path']).resolve(strict=True)
    require(input_path.is_relative_to(directory) and input_path.name == 'gated_norm.actual.bf16le',
            'only named actual producer file; no reference substitute or path escape')
    input_raw = input_path.read_bytes()
    observed = sha(input_raw)
    require(len(input_raw) == size and observed == digest(output['sha256']) == digest(owner['output_sha256']),
            'actual gated_norm raw length/SHA and owner-output agreement')
    require(summary['gated_norm_diagnostics']['actual_sha256'] == observed,
            'diagnostic actual-input identity, without requiring reference equality')
    evidence = dict(stage='gated_norm', input=record(input_path), producer_report=record(summary_path),
                    actual_owner_output_consumed=True, reference_input_substitution=False,
                    producer_terminal_count=len(terminals), all_producer_terminals_successful=True,
                    source_before=before, source_after=after, producer_sources_unchanged=True,
                    source_snapshot_scope='historical producer snapshots, authenticated by summary pin',
                    accepted=accepted, producer_native_acceptance=False,
                    raw_layout='contiguous token-head-feature BF16[M,32,128], flattened without reordering')
    return input_raw, input_path, summary_path, evidence


def diagnostics(actual, official, m):
    from candidates.qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
    geometry(m)
    require(type(actual) is bytes and type(official) is bytes and
            len(actual) == len(official) == m * N * 2, 'complete MxN2048 comparison')
    result = compare_finite_bf16(actual, official)
    first = result['first_bit_mismatch']
    result.update(passed=None, thresholds=None, bitexact_observed=result['bit_mismatches'] == 0,
                  first_coordinate=None if first is None else dict(row=first // N, column=first % N),
                  diagnostic_only=True, native_acceptance=False, recipe_admitted=False)
    return result


def build_reference(out):
    out = Path(out)
    source = Path(__file__).with_name('reference.c')
    executable = shutil.which('gcc')
    require(executable is not None, 'gcc required')
    compiler = Path(executable).resolve(strict=True)
    library = out / 'o_reference.so'
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
        path = out / ('o_reference.' + name + '.txt')
        path.write_text(text)
        evidence[name] = record(path)
        if name == 'dynamic_symbols':
            require(any('UND' in line and 'fmaf@' in line for line in text.splitlines()),
                    'unresolved external versioned libm fmaf symbol')
        if name == 'disassembly':
            require(('ordered_fmaf' in text or 'fmaf@' in text) and 'o_reference_run' in text,
                    'disassembled ordered fmaf pointer and N2048 entry')
        if name == 'ldd':
            libms = [line.split('=>')[1].split()[0] for line in text.splitlines()
                     if 'libm.so' in line and '=>' in line]
            require(len(libms) == 1, 'one linked libm')
            evidence['libm'] = record(Path(libms[0]))
    native = C.CDLL(str(library))
    for name in ('self_test', 'environment'):
        fn = getattr(native, 'o_reference_' + name)
        fn.argtypes, fn.restype = [], C.c_int
    for name in ('mxcsr', 'n', 'k', 'modes'):
        fn = getattr(native, 'o_reference_' + name)
        fn.argtypes, fn.restype = [], C.c_uint
    native.o_reference_run.argtypes = [C.c_uint, C.c_uint] + [C.c_void_p] * 5
    native.o_reference_run.restype = C.c_int
    require((native.o_reference_n(), native.o_reference_k(), native.o_reference_modes()) == (N, K, len(RECIPES)),
            'independent C N2048/K4096/five-recipe ABI')
    code = native.o_reference_self_test()
    require(code == 0, f'FMA/RNE/partialAdd/gradual/FPenv/recipe selftests: {code}')
    evidence.update(compiler=record(compiler), compile_argv=command, reference_source=record(source),
                    reference_library=record(library), selftest_passed=True,
                    selftest_cases=SELFTEST_CASES, mxcsr=native.o_reference_mxcsr())
    return native, evidence


def verify_unchanged(frozen):
    require(all(sha(Path(p).read_bytes()) == h for p, h in frozen.items()),
            'reference source, input, summary or payload manifest drift')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m', type=int, choices=(16, 128), required=True)
    ap.add_argument('--gated-norm-output', type=Path, required=True)
    ap.add_argument('--gated-norm-summary-sha256', required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--payload', type=Path)
    ap.add_argument('--manifest-sha256')
    ap.add_argument('--execute-full-reference', action='store_true')
    args = ap.parse_args()
    geometry(args.m)
    digest(args.gated_norm_summary_sha256)
    if args.execute_full_reference:
        require(args.payload is not None and args.manifest_sha256 is not None,
                'full numerical reference needs separate O-only payload and manifest pin')
    out = args.out.resolve()
    require(not out.exists() and not args.out.is_symlink() and out.is_relative_to(ROOT / 'work'),
            'fresh ignored output under work/')
    nodes, operator = operators()
    input_raw, input_path, summary_path, input_evidence = actual_gated_norm_input(
        args.gated_norm_output, args.gated_norm_summary_sha256, args.m)
    require(args.gated_norm_summary_sha256 == ACTUAL_INPUT_PINS[args.m]['summary_sha256'] and
            sha(input_raw) == ACTUAL_INPUT_PINS[args.m]['input_sha256'],
            'calibration input is the pinned accepted actual M16/M128 producer')
    out.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), Path(__file__).with_name('reference.c'), Path(rms.__file__),
                    ROOT / rms.SOURCE, ROOT / rms.CONFIG, input_path, summary_path,
                    ROOT / 'candidates/qwen35_35b_projection_reference/run_reference.py']
    frozen = {str(p.resolve()): sha(p.read_bytes()) for p in source_paths}
    native, c_evidence = build_reference(out)
    for name in ('compiler', 'libm', 'reference_library'):
        frozen[c_evidence[name]['path']] = c_evidence[name]['sha256']
    report = dict(
        schema_version=1, status='PREFLIGHT_ONLY_O_N2048_K4096_NO_NUMERIC_CALIBRATION',
        scope='ORIGINAL_O_FULL_N2048_K4096_VS_INDEPENDENT_C_DIAGNOSTICS_ONLY',
        m=args.m, n=N, k=K, passed=None, thresholds=None, native_acceptance=False,
        original_operator=operator, input_provenance=input_evidence, c_reference=c_evidence,
        source_frozen=frozen, recipe_definitions=list(RECIPES), results={},
        seeded_equivalence=dict(
            exact_fp32_two_k2048_ascending='same ordered fmaf chain as sequential_k4096',
            exact_fp32_two_k2048_pair_high='same ordered fmaf chain as pair_high_full_k4096',
            conditions='preserve exact FP32 seed; no intermediate BF16 cast, reset, or merge Add',
            independent_partials_equivalent=False, hardware_support_or_calibration_claim=False),
        claim_boundary=dict(
            full_native_forward=False, actual_o_owner_executed=False, rtl_executed=False,
            full_shape_numeric_calibration_executed=False, recipe_admitted=False,
            inherited_n8192_n4096_n32_profiles=False, full_checkpoint_sha256_verified=False,
            payload_hashes_are_first_acquisition_observations=True,
            host_seconds_are_not_hardware_cycles=True,
            independently_computed_from_actual_gated_norm_input=True))
    verify_unchanged(frozen)
    (out / 'preflight.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    if not args.execute_full_reference:
        print(json.dumps(dict(status=report['status'], m=args.m, passed=None, thresholds=None)), flush=True)
        return
    # Parent-controlled opt-in below: no import, download or matmul in preflight.
    from candidates.qwen35_35b_output import payload
    digest(args.manifest_sha256)
    manifest, values = payload.load(args.payload, args.manifest_sha256)
    require(set(values) == {WEIGHT_KEY}, 'O-only payload; no Z, norm or expert tensors')
    weight_raw = values[WEIGHT_KEY]
    require(type(weight_raw) is bytes and len(weight_raw) == N * K * 2,
            'complete original BF16 weight[N2048,K4096]')
    del values
    resource.setrlimit(resource.RLIMIT_CPU, (300, 305))
    signal.alarm(300)
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
    require(not np.any((a & 0x7f80) == 0x7f80) and not np.any((w & 0x7f80) == 0x7f80),
            'finite actual input and O weights')
    extra_paths = [Path(payload.__file__), Path(prefill_bf16_compare.__file__),
                   Path(inspect.getfile(torch.nn.Linear)), Path(runtime['runtime_root']) / 'python.sh',
                   args.payload / 'manifest.json']
    frozen.update({str(p.resolve()): sha(p.read_bytes()) for p in extra_paths})
    obj = SimpleNamespace(value_dim=K, hidden_size=N)
    scope = dict(self=obj, nn=torch.nn, batch_size=1, seq_len=args.m,
                 core_attn_out=torch.from_numpy(a).view(torch.bfloat16).reshape(args.m * HEADS, HEAD_DIM))
    with torch.device('meta'):
        exec(compile_node(nodes[0]), scope)
    layer = obj.out_proj
    layer.weight = torch.nn.Parameter(torch.from_numpy(w).view(torch.bfloat16), requires_grad=False)
    layer.eval()
    require(layer.bias is None and (layer.in_features, layer.out_features) == (K, N),
            'original bias-free complete N2048/K4096 Linear')
    report.update(runtime=runtime, payload_manifest=record(args.payload / 'manifest.json'),
                  weight=dict(key=WEIGHT_KEY, bytes=len(weight_raw), sha256=sha(weight_raw), shape=[N, K]))
    started = time.monotonic()
    with torch.inference_mode(), torch.autocast(device_type='cpu', enabled=False):
        exec(compile_node(nodes[1]), scope)  # Original flatten, no value substitution.
        require(tuple(scope['core_attn_out'].shape) == (1, args.m, K) and
                scope['core_attn_out'].contiguous().view(torch.uint16).numpy().tobytes() == input_raw,
                'original flatten preserves complete actual producer bytes')
        exec(compile_node(nodes[2]), scope)  # Exactly one original full-N2048 call.
        y = scope['output']
        require(tuple(y.shape) == (1, args.m, N) and y.dtype == torch.bfloat16,
                'original full N2048 shape/dtype')
        official = y.contiguous().view(torch.uint16).numpy().tobytes()
    require(native.o_reference_environment() == 0, 'environment after original operator')
    official_path = out / 'o.official.bf16le'
    official_path.write_bytes(official)
    report['official'] = record(official_path)
    report['official_seconds'] = time.monotonic() - started
    for recipe in RECIPES:
        words, pre, counts = np.zeros((args.m, N), '<u2'), np.zeros((args.m, N), '<f4'), np.zeros(3, '<u8')
        then = time.monotonic()
        require(native.o_reference_run(args.m, recipe['mode'], a.ctypes.data, w.ctypes.data,
                                       words.ctypes.data, pre.ctypes.data, counts.ctypes.data) == 0,
                'strict independent complete K4096/N2048 C recipe')
        require(int(counts[0]) == args.m * N * K and
                int(counts[2]) == args.m * N * recipe['partial_adds_per_output'],
                'complete full-shape C arithmetic counts')
        output_path = out / ('o.' + recipe['name'] + '.bf16le')
        pre_path = out / ('o.' + recipe['name'] + '.fp32le')
        output_path.write_bytes(words.tobytes())
        pre_path.write_bytes(pre.tobytes())
        report['results'][recipe['name']] = dict(
            diagnostics(words.tobytes(), official, args.m), output=record(output_path), pre_bf16=record(pre_path),
            diagnostic_fma_calls=int(counts[0]), diagnostic_fp32_fma_subnormal_observations=int(counts[1]),
            diagnostic_partialAdd_calls=int(counts[2]), seconds=time.monotonic() - then)
    verify_unchanged(frozen)
    require(sha((args.payload / 'manifest.json').read_bytes()) == args.manifest_sha256,
            'payload manifest unchanged')
    require(native.o_reference_environment() == 0, 'final strict floating-point environment')
    report['claim_boundary']['full_shape_numeric_calibration_executed'] = True
    report.update(status='COMPLETE_O_N2048_K4096_DIAGNOSTICS_NO_ADMISSION', sources_unchanged=True,
                  numeric_seconds=time.monotonic() - started, mxcsr_after=native.o_reference_mxcsr(),
                  runtime_after=rms.runtime_identity(),
                  peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    signal.alarm(0)
    print(json.dumps(dict(status=report['status'], m=args.m, passed=None, thresholds=None,
                          native_acceptance=False, seconds=report['numeric_seconds'])), flush=True)


if __name__ == '__main__':
    main()
