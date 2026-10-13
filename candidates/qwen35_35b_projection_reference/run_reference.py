"""Pinned official operator vs independent strict-C K2048 recipes, host only.

Invoke through the restored one-CPU python.sh. No full model, no owner run,
no production profile admission, no expected output supplied to C reference.
"""
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
ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
MANIFEST_SHA = 'b4f2e4efbba9ec752913c17f9fbf085b66e61e62d3b9b2914583d27d32f3e937'
WEIGHT_SHA = 'b6195bf0347afcbee3eab1e1f7c34b372cc917b19ddf4feaed8f70d699544db6'
RMS_SUMMARY_SHA = 'd49d6fed6dcf4312bbaa1c4a7ce66c7194bf83c05317701cc9bb1bd6aee9cd44'
INPUT_SHAS = {16: 'f1f818f452b945cf01a59f6c30250f23596559f82882fb58adc803c747919619', 128: '36985e9c0fbe3ba24563d550ab2801c82a0393b4e80b46895408ac10cc1a2ff4'}
PAYLOAD = ROOT / 'work/qwen35_35b_qkv_payload_20261013T0531'
RMS = ROOT / 'work/qwen35_35b_rms_owner_actual_20261013T0514'
UPSTREAM = ROOT / 'config/upstream/weight_headers/qwen3_5_35b_a3b'
FLAGS = ['-std=c11', '-shared', '-fPIC', '-O2', '-fno-fast-math', '-ffp-contract=off', '-frounding-math', '-fno-builtin-fmaf']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def record(path):
    p = Path(path).resolve()
    return dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p))

def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def classify(raw, np):
    ex = raw & 32640
    fr = raw & 127
    return dict(normal=int(np.count_nonzero((ex != 0) & (ex != 32640))), subnormal=int(np.count_nonzero((ex == 0) & (fr != 0))), positive_zero=int(np.count_nonzero(raw == 0)), negative_zero=int(np.count_nonzero(raw == 32768)), nonfinite=int(np.count_nonzero(ex == 32640)))

def compare(actual, native, np):
    af = (actual.astype(np.uint32) << 16).view(np.float32).astype(np.float64)
    nf = (native.astype(np.uint32) << 16).view(np.float32).astype(np.float64)
    error = np.abs(af - nf)
    bad = actual != native
    at = np.argwhere(bad)
    first = None
    if at.size:
        r, c = map(int, at[0])
        first = dict(row=r, column=c, flat_index=r * 8192 + c, actual_bits=f'{actual[r, c]:04x}', native_bits=f'{native[r, c]:04x}', actual=float(af[r, c]), native=float(nf[r, c]), abs_error=float(error[r, c]))
    levels, counts = np.unique(error[bad], return_counts=True)
    segments = {}
    for name, lo, hi in [('q', 0, 2048), ('k', 2048, 4096), ('v', 4096, 8192)]:
        e = error[:, lo:hi]
        segments[name] = dict(bit_mismatches=int(bad[:, lo:hi].sum()), max_abs=float(e.max()), mean_abs=float(e.mean()), gate_pass=bool(e.max() <= 0.03125 and e.mean() <= 0.005))
    overall_gate_pass = bool(error.max() <= 0.03125 and error.mean() <= 0.005)
    per_segment_original_gate = {name: segment['gate_pass'] for name, segment in segments.items()}
    az = actual & 32767 == 0
    nz = native & 32767 == 0
    return dict(elements=int(actual.size), bit_mismatches=int(bad.sum()), bitexact=not bool(bad.any()), max_abs=float(error.max()), mean_abs=float(error.mean()), overall_gate_pass=overall_gate_pass, per_segment_original_gate=per_segment_original_gate, gate_pass=overall_gate_pass and all(per_segment_original_gate.values()), first_difference=first, mismatch_rows=[int(x) for x in bad.sum(axis=1)], segments=segments, error_distribution=[dict(abs_error=float(a), count=int(b)) for a, b in zip(levels, counts)], actual_domain=classify(actual, np), native_domain=classify(native, np), signed_zero_only_mismatches=int(np.count_nonzero(bad & az & nz)))

def finish_report(out, report):
    """Persist a numerical failure for inspection and fail the process."""
    passed = report['results']['pair_hi_first_two_k1024']['gate_pass']
    report['status'] = 'PASS_PAIR_PROFILE_ORIGINAL_GATES' if passed else 'FAIL_PAIR_PROFILE_ORIGINAL_GATES'
    dump(out / 'report.json', report)
    print(json.dumps(dict(status=report['status'], report_sha256=sha(out / 'report.json'), seconds=report['total_numeric_seconds'])), flush=True)
    if not passed:
        raise SystemExit(1)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--m', type=int, choices=(16, 128), required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--preflight-only', action='store_true')
    ap.add_argument('--payload', type=Path, default=PAYLOAD)
    ap.add_argument('--manifest-sha256', default=MANIFEST_SHA)
    ap.add_argument('--rms-output', type=Path, default=RMS)
    ap.add_argument('--rms-summary-sha256', default=RMS_SUMMARY_SHA)
    args = ap.parse_args()
    m = args.m
    out = args.out.resolve()
    if out.exists() or args.out.is_symlink() or not out.is_relative_to(ROOT / 'work'):
        raise ValueError('Reference output must be fresh and under ignored work/')
    for digest in (args.manifest_sha256, args.rms_summary_sha256):
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Independent manifest and RMS summary SHA256 required')
    payload, rms = args.payload.resolve(strict=True), args.rms_output.resolve(strict=True)
    out.mkdir(parents=True, exist_ok=False)
    os.chdir(out)
    resource.setrlimit(resource.RLIMIT_CPU, (120, 125))
    signal.alarm(120)
    if not len(os.sched_getaffinity(0)) == 1:
        raise ValueError('Reference guard failed: len(os.sched_getaffinity(0)) == 1')
    import numpy as np
    import torch
    from candidates.qwen35_35b_payload.packer import load_payload
    from candidates.qwen35_35b_prefill.partial_tiles import resource_ledger
    if not (np.__version__ == '2.3.5' and torch.__version__ == '2.10.0+cpu'):
        raise ValueError("Reference guard failed: np.__version__ == '2.3.5' and torch.__version__ == '2.10.0+cpu'")
    if not torch.version.git_version == '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0':
        raise ValueError("Reference guard failed: torch.version.git_version == '449b1768410104d3ed79d3bcfe4ba1d65c7f22c0'")
    if not os.environ['ATEN_CPU_CAPABILITY'] == 'default':
        raise ValueError("Reference guard failed: os.environ['ATEN_CPU_CAPABILITY'] == 'default'")
    if not torch.backends.cpu.get_cpu_capability() == 'DEFAULT':
        raise ValueError("Reference guard failed: torch.backends.cpu.get_cpu_capability() == 'DEFAULT'")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision('highest')
    if not torch.set_flush_denormal(False):
        raise ValueError('Reference guard failed: torch.set_flush_denormal(False)')
    from candidates.qwen35_35b_rms.reference import runtime_identity
    pinned_runtime = runtime_identity()
    manifest, values = load_payload(ROOT, payload, manifest_sha256=args.manifest_sha256, include_qkv=True)
    if not manifest['plan']['revision'] == '62704185bd97ad488cfc404e7caea797396b74dc':
        raise ValueError("Reference guard failed: manifest['plan']['revision'] == '62704185bd97ad488cfc404e7caea797396b74dc'")
    if not sha(rms / 'summary.json') == args.rms_summary_sha256:
        raise ValueError("Reference guard failed: sha(rms / 'summary.json') == args.rms_summary_sha256")
    summary = json.loads((rms / 'summary.json').read_text())
    case = next((c for c in summary['cases'] if c['name'] == f'actual_embedding_rms_m{m}'))
    if not (case['official_output']['bit_mismatches'] == 0 and case['owner']['output_published']):
        raise ValueError("Reference guard failed: case['official_output']['bit_mismatches'] == 0 and case['owner']['output_published']")
    if not case['official_output']['actual_sha256'] == INPUT_SHAS[m]:
        raise ValueError("Reference guard failed: case['official_output']['actual_sha256'] == INPUT_SHAS[m]")
    ip = rms / f'actual_embedding_rms_m{m}.actual_output.bin'
    if not (sha(ip) == INPUT_SHAS[m] and ip.stat().st_size == m * 2048 * 2):
        raise ValueError('Reference guard failed: sha(ip) == INPUT_SHAS[m] and ip.stat().st_size == m * 2048 * 2')
    wp = payload / 'layers.0.linear_attn.in_proj_qkv.weight.bin'
    if not (sha(wp) == WEIGHT_SHA and wp.stat().st_size == 8192 * 2048 * 2):
        raise ValueError('Reference guard failed: sha(wp) == WEIGHT_SHA and wp.stat().st_size == 8192 * 2048 * 2')
    a = np.fromfile(ip, dtype='<u2').reshape(1, m, 2048)
    w = np.frombuffer(values['layers.0.linear_attn.in_proj_qkv.weight'], dtype='<u2').copy().reshape(8192, 2048)
    del values
    official = UPSTREAM / 'modeling_qwen3_5_moe.py'
    if not sha(official) == 'ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30':
        raise ValueError("Reference guard failed: sha(official) == 'ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30'")
    text = official.read_text()
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Qwen3_5MoeGatedDeltaNet'))
    init = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__'))
    assignment = next((n for n in init.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Attribute) and t.attr == 'in_proj_qkv' for t in n.targets))))
    forward = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'forward'))
    calls = [n for n in forward.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'mixed_qkv' for t in n.targets))][:2]
    if not [ast.get_source_segment(text, n) for n in calls] == ['mixed_qkv = self.in_proj_qkv(hidden_states)', 'mixed_qkv = mixed_qkv.transpose(1, 2)']:
        raise ValueError("Reference guard failed: [ast.get_source_segment(text, n) for n in calls] == ['mixed_qkv = self.in_proj_qkv(hidden_states)', 'mixed_qkv = mixed_qkv.transpose(1, 2)']")
    config = json.loads((UPSTREAM / 'config.json').read_text())['text_config']
    obj = SimpleNamespace(hidden_size=config['hidden_size'], key_dim=config['linear_num_key_heads'] * config['linear_key_head_dim'], value_dim=config['linear_num_value_heads'] * config['linear_value_head_dim'])
    if not (obj.hidden_size, obj.key_dim * 2 + obj.value_dim) == (2048, 8192):
        raise ValueError('Reference guard failed: (obj.hidden_size, obj.key_dim * 2 + obj.value_dim) == (2048, 8192)')
    scope = dict(self=obj, nn=torch.nn)
    with torch.device('meta'):
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(official), 'exec'), scope)
    obj.in_proj_qkv.weight = torch.nn.Parameter(torch.from_numpy(w).view(torch.bfloat16), requires_grad=False)
    obj.in_proj_qkv.eval()
    if not obj.in_proj_qkv.bias is None:
        raise ValueError('Reference guard failed: obj.in_proj_qkv.bias is None')
    scope['hidden_states'] = torch.from_numpy(a).view(torch.bfloat16)
    sources = [SOURCE / 'reference.c', SOURCE / 'run_reference.py', official, UPSTREAM / 'config.json', ROOT / 'candidates/qwen35_35b_payload/packer.py', ROOT / 'candidates/qwen35_35b_prefill/partial_tiles.py', ROOT / 'candidates/qwen35_35b_prefill/sum_tiles.py', ROOT / 'candidates/qwen35_35b_prefill/projection_owner.py', ROOT / 'candidates/qwen35_35b_prefill/projection_driver.py', ROOT / 'candidates/qwen2_resident_matrix/dense_block_reduce/k_window_model.py', ROOT / 'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp', Path(inspect.getfile(torch.nn.Linear)), Path(pinned_runtime['runtime_root']) / 'python.sh', ROOT / 'candidates/qwen35_35b_rms/reference.py', ROOT / 'candidates/qwen35_35b_rms/runtime_recovery_20261013.json']
    frozen = {str(p): sha(p) for p in sources}
    compiler = Path(shutil.which('gcc')).resolve()
    lib = out / 'reference.so'
    argv = [str(compiler), *FLAGS, str(SOURCE / 'reference.c'), '-o', str(lib), '-lm']
    subprocess.run(argv, check=True, capture_output=True, timeout=30)
    disasm = subprocess.check_output(['objdump', '-d', str(lib)], text=True)
    if not 'fmaf@' in disasm:
        raise ValueError("Reference guard failed: 'fmaf@' in disasm")
    (out / 'reference.disassembly.txt').write_text(disasm)
    ldd = subprocess.check_output(['ldd', str(lib)], text=True)
    (out / 'reference.ldd.txt').write_text(ldd)
    libm_path = Path(next((line.split('=>')[1].split()[0] for line in ldd.splitlines() if 'libm.so' in line)))
    native = C.CDLL(str(lib))
    native.reference_mxcsr.restype = C.c_uint
    if not native.reference_self_test() == 0:
        raise ValueError('Reference guard failed: native.reference_self_test() == 0')
    native.reference_run.argtypes = [C.c_uint, C.c_uint, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    beats = m * 8192 // 16
    ledger = dict(resource_ledger(), matrix_mac_lanes=4096, vector_lanes=16, output_windows=52, window_columns=160, final_window_columns=32, proposal_only=True, hardware_cycles=None, added_arithmetic_units=0, shape_useful_macs=m * 8192 * 2048, logical_fp32_partial_bytes=2 * m * 8192 * 4, extra_merge_fp32_adds=m * 8192, extra_merge_vector_requests=beats, extra_merge_operand_read_beats=2 * beats, extra_merge_rmw_read_beats=beats, extra_merge_write_beats=beats, extra_merge_physical_read_bytes=3 * beats * 512, extra_merge_physical_write_bytes=beats * 512, note='Counts are static proposals. Each 16-lane sum reads two operands and one 512-byte SRAM RMW capture, then writes 512 bytes. No hardware/owner measurement.')
    report = dict(schema_version=1, scope='EXACT_PINNED_UPSTREAM_LINEAR_OPERATOR_VS_INDEPENDENT_LOGICAL_C', m=m, k=2048, n=8192, status='PREFLIGHT_PASS', thresholds=dict(max_abs=0.03125, mean_abs=0.005), source_frozen=frozen, compiler=record(compiler), compile_argv=argv, reference_library=record(lib), libm=record(libm_path), source_operator=[ast.get_source_segment(text, n) for n in [assignment, *calls]], official_source=record(official), payload_manifest=record(payload / 'manifest.json'), producer_summary=record(rms / 'summary.json'), input=record(ip), weight=record(wp), input_domain=classify(a, np), weight_domain=classify(w, np), resource_ledger=ledger, runtime=dict(pinned_identity=pinned_runtime, torch=torch.__version__, torch_git=torch.version.git_version, numpy=np.__version__, torch_threads=torch.get_num_threads(), torch_interop_threads=torch.get_num_interop_threads(), affinity=sorted(os.sched_getaffinity(0)), cpu_capability=torch.backends.cpu.get_cpu_capability(), deterministic_algorithms=True, autocast=False, flush_denormal=False, float32_matmul_precision='highest', mkldnn_enabled=torch.backends.mkldnn.enabled, mxcsr=native.reference_mxcsr(), config=torch.__config__.show()), self_test=dict(passed=True, cases=['fused_rounding_witness', 'bf16_ties_even', 'bf16_subnormal_ties', 'gradual_fmaf', 'reject_FTZ_DAZ']), claim_boundary=dict(full_native_forward=False, actual_projection_owner_executed=False, rtl_executed=False, official_35b_profile_admitted=False, full_checkpoint_sha256_verified=False, payload_hashes_are_first_acquisition_observations=True, capture_kind='New exact upstream operator call on actual RMS producer output; never relabeled old capture'))
    dump(out / 'preflight.json', report)
    print(json.dumps(dict(status=report['status'], m=m, preflight_sha256=sha(out / 'preflight.json'))), flush=True)
    if args.preflight_only:
        return
    started = time.monotonic()
    with torch.inference_mode(), torch.autocast(device_type='cpu', enabled=False):
        t = time.monotonic()
        exec(compile(ast.Module(body=[calls[0]], type_ignores=[]), str(official), 'exec'), scope)
        z = scope['mixed_qkv']
        if not (tuple(z.shape) == (1, m, 8192) and z.dtype == torch.bfloat16):
            raise ValueError('Reference guard failed: tuple(z.shape) == (1, m, 8192) and z.dtype == torch.bfloat16')
        words = z.contiguous().view(torch.uint16).numpy().copy().reshape(m, 8192)
        exec(compile(ast.Module(body=[calls[1]], type_ignores=[]), str(official), 'exec'), scope)
        if not tuple(scope['mixed_qkv'].shape) == (1, 8192, m):
            raise ValueError("Reference guard failed: tuple(scope['mixed_qkv'].shape) == (1, 8192, m)")
        report['official_seconds'] = time.monotonic() - t
    if not native.reference_environment() == 0:
        raise ValueError('Reference guard failed: native.reference_environment() == 0')
    words.tofile(out / 'official_output.bf16le')
    report['official_output'] = record(out / 'official_output.bf16le')
    report['official_output_domain'] = classify(words, np)
    report['results'] = {}
    for mode, name in enumerate(['sequential_k2048', 'pair_hi_first_two_k1024']):
        outwords = np.empty((m, 8192), dtype='<u2')
        pre = np.empty((m, 8192), dtype='<f4')
        counts = np.zeros(3, dtype='<u8')
        t = time.monotonic()
        code = native.reference_run(m, mode, a.ctypes.data, w.ctypes.data, outwords.ctypes.data, pre.ctypes.data, counts.ctypes.data)
        if not code == 0:
            raise ValueError(code)
        r = compare(outwords, words, np)
        r.update(seconds=time.monotonic() - t, libm_fmaf_calls=int(counts[0]), intermediate_fp32_subnormal_observations=int(counts[1]), merge_fp32_add_calls=int(counts[2]))
        outwords.tofile(out / (name + '.bf16le'))
        pre.tofile(out / (name + '.fp32le'))
        r['output'] = record(out / (name + '.bf16le'))
        r['pre_bf16'] = record(out / (name + '.fp32le'))
        report['results'][name] = r
        print(json.dumps(dict(profile=name, **{k: r[k] for k in ['seconds', 'bit_mismatches', 'max_abs', 'mean_abs', 'gate_pass', 'first_difference']})), flush=True)
    if not frozen == {str(p): sha(p) for p in sources}:
        raise ValueError('Reference guard failed: frozen == {str(p): sha(p) for p in sources}')
    if not (sha(ip) == INPUT_SHAS[m] and sha(wp) == WEIGHT_SHA and (native.reference_environment() == 0)):
        raise ValueError('Reference guard failed: sha(ip) == INPUT_SHAS[m] and sha(wp) == WEIGHT_SHA and (native.reference_environment() == 0)')
    report.update(total_numeric_seconds=time.monotonic() - started, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, source_frozen_after_verified=True, mxcsr_after=native.reference_mxcsr())
    finish_report(out, report)
if __name__ == '__main__':
    main()
