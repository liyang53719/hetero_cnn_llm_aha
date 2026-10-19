"""Cold, isolated first-M128-N0 comparator; no execution without --execute.

Only the five whole unchanged functions in the fixed original gate are compiled.
The original numerical formula and operator verdict are not reimplemented here.
The caller owns RTL capture provenance, external supervision and shared deadline.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import types

REFERENCE_HELPER = {'bytes': 13753, 'sha256': 'd26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4'}
REFERENCE_PINS = {'bytes': 6364, 'sha256': 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8'}
ORIGINAL_SCRIPT = {'bytes': 37776, 'sha256': '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'}
ORIGINAL_CONTRACT = {'bytes': 2256, 'sha256': '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'}
REFERENCE = {'bytes': 786432, 'sha256': '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'}
SHAPE = [1, 128, 1536]
ELEMENTS = 196608
SCRIPT_PATH = 'scripts/qwen2_layer0_model_gate.py'
CONTRACT_PATH = 'spec/numerical_contract.md'
FUNCTIONS = {
    'sha': (44, 49, '5bf07b3b6a2399eb039b066542c73c02e3a8b3a95ac3682bee327dcaa8017e5b', '9aa62fa7b1d6c6aacf31e9697a9a6c5b08cad63630df10d8fc918cd38566d1fd'),
    'digest_array': (52, 53, '4d114f63652f2514047e9e8338d27958525dfa7aa50e58b032f3ba6ee13cddbd', 'ce246727c243818666050a2f3f08ed9d296b99bd7a17d9ab676dc1920d235e53'),
    'compare': (77, 98, 'd6ba1543006e33ebc9aadb5e9f6220afbad08ba6ede191ac86054b9537a93f56', '425b4b4655176568bb2e8def5ae55d49f6c5c21c35e6b93ab48ef81c7dbfab04'),
    'load_policy': (101, 112, 'df5659105c0648db6c79ca514380b8d522eb93cc8a266b8fb5a414e9415cb7a8', '4f0f8898049399e66151b5d89cadf582a6f6a17bcb17c1c66fe1f3fe37634277'),
    'stage_verdict': (115, 122, '68f35f9f90826bc5421a1ee6d105f41d36bdddc831d54f9ef49c41167fd8a839', 'df47d1a5fff78a266481f66d0ccd2a848e545e9fa57766fd5c1f18aa25be85c7'),
}
CODES = frozenset(('FLAGS', 'PATH', 'FILE', 'SIZE', 'SHA', 'CHANGED', 'SOURCE', 'INPUT',
                   'CAPTURE', 'RUNTIME', 'DISPATCH', 'DEADLINE', 'RESOURCE', 'OUTPUT', 'UNEXPECTED'))
STAGES = frozenset(('SOURCE', 'CAPTURE', 'INPUT', 'RUNTIME_IDENTITY', 'RUNTIME_IMPORT', 'COMPARE', 'POSTFLIGHT', 'COMPLETE'))
ARRAY_SIZES = {'input_ar': 16, 'input_read_bytes': 16, 'core_state_cycles': 128,
               'hub_accepted': 2, 'hub_returned': 2}
AXI_KEYS = frozenset(('ars', 'rbeats_expected', 'rbeats', 'rlasts', 'aws', 'wbeats_expected',
    'wbeats', 'wbeats_committed', 'bs', 'strobed_bytes', 'ar_stall', 'aw_stall', 'w_stall', 'r_stall', 'b_stall'))
COUNT_KEYS = frozenset(('scope', 'status', 'numeric_comparison', 'phase', 'code', 'full_block_pass', 'root256_handles',
    'cycle_budget', 'reduction_only_source_floor', 'unproven_overhead_allowance', 'cycles',
    'launches', 'jobs', 'owner_dones', 'completion_acks', 'core_read_requests', 'core_write_requests',
    'core_responses', 'committed_bytes', 'successful_b', 'writeback_bytes', 'post_pc',
    'post_issued_jobs', 'further_eval_calls', 'input_ar', 'input_read_bytes', 'core_state_cycles',
    'hub_accepted', 'hub_returned', 'idma_transfers', 'idma_read_bursts', 'idma_read_beats',
    'idma_cache_hits', 'axi', 'actual_values', 'actual_bytes'))
METRIC_KEYS = frozenset(('shape', 'elements', 'max_abs', 'mean_abs', 'relative_l2', 'cosine',
    'normalized_max_abs', 'different_elements', 'bit_exact', 'actual_f32_sha256', 'reference_f32_sha256', 'finite'))
REPORT_KEYS = frozenset(('schema', 'scope', 'status', 'code', 'stage', 'numeric_pass', 'bit_exact',
    'hash_exact', 'reference_hash_accepted', 'capture_basic_counts_accepted', 'full_block_pass',
    'shape', 'elements', 'actual_bytes', 'reference_bytes', 'metrics', 'limits', 'source_sha256',
    'contract_sha256', 'actual_sha256', 'reference_sha256', 'capture_sha256'))

class Rejected(ValueError):
    def __init__(self, code):
        if code not in CODES:
            code = 'UNEXPECTED'
        self.code = code
        super().__init__(code)

def need(ok, code):
    if not ok:
        raise Rejected(code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def checked_buffer(raw, pin):
    need(type(raw) is bytes and len(raw) == pin['bytes'], 'SIZE')
    need(digest(raw) == pin['sha256'], 'SHA')
    return raw

def safe_path(value):
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and p.resolve() == p and
         not any(q.is_symlink() for q in (p, *p.parents)), 'PATH')
    return p

def read_fixed(value, size, expected_sha=None, *, maximum=False):
    p = safe_path(value)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode), 'FILE')
        need(0 <= first.st_size <= size if maximum else first.st_size == size, 'SIZE')
        chunks, total = [], 0
        while True:
            part = os.read(fd, min(1048576, size + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            need(total <= size, 'SIZE')
        last = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(identity(first) == identity(last) == identity(p.stat()) and total == first.st_size, 'CHANGED')
        raw = b''.join(chunks)
        need(expected_sha is None or digest(raw) == expected_sha, 'SHA')
        return raw
    finally:
        os.close(fd)

def read_pin(value, pin):
    return read_fixed(value, pin['bytes'], pin['sha256'])

def isolated():
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')
    need(not any(k.split('.')[0] in ('numpy', 'torch', 'transformers') for k in sys.modules), 'RUNTIME')

def load_reference_helper(raw):
    isolated()
    checked_buffer(raw, REFERENCE_HELPER)
    module = types.ModuleType('_frozen_n0_reference_helpers')
    module.__file__ = '<fixed-n0-reference-helpers>'
    # This verified cold module has only stdlib imports and guarded main.
    # No reference recovery or forward method is ever called by this wrapper.
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module

def original_namespace(raw, np):
    checked_buffer(raw, ORIGINAL_SCRIPT)
    text = raw.decode('utf8')
    matches = [node for node in ast.parse(text).body
               if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    need([node.name for node in matches] == list(FUNCTIONS), 'SOURCE')
    for node in matches:
        start, end, ast_sha, source_sha = FUNCTIONS[node.name]
        need((node.lineno, node.end_lineno) == (start, end) and
             digest(ast.dump(node, include_attributes=False).encode()) == ast_sha and
             digest(ast.get_source_segment(text, node).encode()) == source_sha, 'SOURCE')
    # Postponed annotations do not modify the selected original function ASTs.
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    tree = ast.fix_missing_locations(ast.Module(body=[future, *matches], type_ignores=[]))
    namespace = {'np': np, 'hashlib': hashlib, 'Path': Path}
    exec(compile(tree, '<fixed-original-model-gate-functions>', 'exec'), namespace)
    return namespace

class BufferContract:
    """The unchanged original load_policy/sha see only the verified bytes."""
    def __init__(self, raw):
        self.raw = checked_buffer(raw, ORIGINAL_CONTRACT)
    def read_text(self):
        return self.raw.decode('utf8')
    def open(self, mode):
        need(mode == 'rb', 'SOURCE')
        return io.BytesIO(self.raw)
    def relative_to(self, root):
        need(isinstance(root, BufferRoot) and root.contract is self, 'SOURCE')
        return CONTRACT_PATH

class BufferRoot:
    def __init__(self, raw):
        self.contract = BufferContract(raw)
    def __truediv__(self, relative):
        need(relative == CONTRACT_PATH, 'SOURCE')
        return self.contract

def original_policy(namespace, raw):
    policy = namespace['load_policy'](BufferRoot(raw))
    need(policy['sha256'] == ORIGINAL_CONTRACT['sha256'] and
         policy['operator'] == {'max_abs': 0.03125, 'mean_abs': 0.005}, 'SOURCE')
    return policy

def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        need(key not in obj, 'CAPTURE')
        obj[key] = value
    return obj

def nonnegative_int(value):
    return type(value) is int and 0 <= value <= 2**63 - 1

def capture_gate(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'CAPTURE')
    counts = json.loads(raw, object_pairs_hook=unique_object,
                        parse_constant=lambda _: (_ for _ in ()).throw(Rejected('CAPTURE')))
    need(type(counts) is dict and set(counts) == COUNT_KEYS, 'CAPTURE')
    expected = {'scope': 'FIRST_N0_M128_ONLY', 'status': 'ACK0_ACTUAL_CAPTURED',
        'numeric_comparison': 'NOT_RUN', 'phase': 'OUTPUT', 'code': 'ACK0_COMPLETE',
        'full_block_pass': False, 'root256_handles': 'UNKNOWN',
        'cycle_budget': 8000000, 'reduction_only_source_floor': 2428928,
        'unproven_overhead_allowance': 5571072, 'launches': 1, 'jobs': 1,
        'owner_dones': 1, 'completion_acks': 1, 'committed_bytes': 786432,
        'successful_b': 12288, 'writeback_bytes': 786432, 'post_pc': 1,
        'post_issued_jobs': 1, 'further_eval_calls': 0, 'actual_values': ELEMENTS, 'actual_bytes': 786432}
    for key, value in expected.items():
        need(type(counts[key]) is type(value) and counts[key] == value, 'CAPTURE')
    for key, value in counts.items():
        if key not in expected and key not in ARRAY_SIZES and key != 'axi':
            need(nonnegative_int(value), 'CAPTURE')
    need(2428928 <= counts['cycles'] <= 8000000, 'CAPTURE')
    for key, length in ARRAY_SIZES.items():
        value = counts[key]
        need(type(value) is list and len(value) == length and all(nonnegative_int(x) for x in value), 'CAPTURE')
    axi = counts['axi']
    need(type(axi) is dict and set(axi) == AXI_KEYS and all(nonnegative_int(v) for v in axi.values()), 'CAPTURE')
    need(axi['bs'] == 12288 and axi['strobed_bytes'] == 786432, 'CAPTURE')
    return counts

def checked_arrays(np, actual_raw, reference_raw):
    need(len(actual_raw) == REFERENCE['bytes'] and len(reference_raw) == REFERENCE['bytes'], 'SIZE')
    actual = np.frombuffer(actual_raw, dtype='<f4').reshape(SHAPE)
    reference = np.frombuffer(reference_raw, dtype='<f4').reshape(SHAPE)
    for value in (actual, reference):
        need(list(value.shape) == SHAPE and value.size == ELEMENTS and
             value.dtype == np.dtype('<f4') and bool(np.isfinite(value).all()), 'INPUT')
    return actual, reference

def evaluate(namespace, actual, reference, policy, actual_raw, reference_raw):
    """Call the original methods, then independently label numeric and exact outcomes."""
    metrics = namespace['compare'](actual, reference)
    need(metrics['shape'] == SHAPE and metrics['elements'] == ELEMENTS and metrics['finite'] is True, 'INPUT')
    for key in ('max_abs', 'mean_abs', 'relative_l2', 'cosine', 'normalized_max_abs'):
        need(metrics[key] is None or (type(metrics[key]) is float and math.isfinite(metrics[key])), 'INPUT')
    need(metrics['max_abs'] is not None and metrics['mean_abs'] is not None and
         metrics['max_abs'] >= 0 and metrics['mean_abs'] >= 0, 'INPUT')
    need(type(metrics['different_elements']) is int and 0 <= metrics['different_elements'] <= ELEMENTS, 'INPUT')
    actual_sha, reference_sha = digest(actual_raw), digest(reference_raw)
    need(reference_sha == REFERENCE['sha256'] and
         metrics['actual_f32_sha256'] == actual_sha and metrics['reference_f32_sha256'] == reference_sha, 'SHA')
    bit_exact = bool(metrics['bit_exact'])
    need(bit_exact == (metrics['different_elements'] == 0) == (actual_raw == reference_raw), 'INPUT')
    verdict = namespace['stage_verdict']('n0', metrics, 'bf16', policy)
    need(verdict['contract'] == CONTRACT_PATH + ':operator' and verdict['limits'] == policy['operator'] and
         type(verdict['passed']) is bool, 'SOURCE')
    safe_metrics = {key: metrics[key] for key in METRIC_KEYS}
    safe_metrics['bit_exact'] = bit_exact
    return dict(numeric_pass=verdict['passed'], bit_exact=bit_exact,
        hash_exact=actual_sha == reference_sha, actual_sha256=actual_sha, reference_sha256=reference_sha,
        metrics=safe_metrics, limits=verdict['limits'])

def runtime_import(runtime, pins):
    required = {'OMP_NUM_THREADS': '4', 'MKL_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '1', 'PYTHONNOUSERSITE': '1'}
    need(all(os.environ.get(k) == v for k, v in required.items()) and
         all(k not in os.environ for k in ('ATEN_CPU_CAPABILITY', 'MKL_CBWR', 'ONEDNN_MAX_CPU_ISA', 'DNNL_MAX_CPU_ISA')), 'RUNTIME')
    sys.path.insert(0, str(runtime))
    import numpy as np
    import torch
    expected = pins['runtime_requirements']
    need(np.__version__ == expected['numpy'] and str(torch.__version__) == expected['torch'] and
         torch.version.git_version == expected['torch_commit'], 'RUNTIME')
    need(torch.backends.cpu.get_cpu_capability() == expected['capability'], 'DISPATCH')
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    need(digest(torch.__config__.show().encode()) == expected['torch_build_sha256'], 'RUNTIME')
    need(Path(torch._C.__file__).resolve() == runtime/'torch/_C.cpython-312-x86_64-linux-gnu.so' and
         Path(np._core._multiarray_umath.__file__).resolve() == runtime/'numpy/_core/_multiarray_umath.cpython-312-x86_64-linux-gnu.so', 'RUNTIME')
    return np, torch

def new_report():
    return dict(schema=1, scope='FIRST_N0_M128_ONLY', status='NOT_COMPLETED', code='UNEXPECTED',
        stage='SOURCE', numeric_pass=None, bit_exact=None, hash_exact=None,
        reference_hash_accepted=False, capture_basic_counts_accepted=False, full_block_pass=False,
        shape=SHAPE[:], elements=ELEMENTS, actual_bytes=None, reference_bytes=None,
        source_sha256=ORIGINAL_SCRIPT['sha256'], contract_sha256=ORIGINAL_CONTRACT['sha256'])

def report_bytes(report):
    need(set(report) <= REPORT_KEYS and report['stage'] in STAGES and
         report['status'] in ('NOT_COMPLETED', 'N0_LIMITED_TOLERANCE_PASS', 'N0_LIMITED_TOLERANCE_FAIL') and
         (report['code'] is None or report['code'] in CODES), 'OUTPUT')
    need('metrics' not in report or set(report['metrics']) == METRIC_KEYS, 'OUTPUT')
    return (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()

def write_receipt(out, report):
    raw = report_bytes(report)
    need(len(raw) <= 65536, 'OUTPUT')
    fd = os.open(out/'RECEIPT.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            need(stream.write(raw) == len(raw), 'OUTPUT')
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)

def run(args):
    isolated()
    helper_raw = read_pin(args.reference_worker, REFERENCE_HELPER)
    helper = load_reference_helper(helper_raw)
    # Helper rounds accumulated CPU upward: 24 + rounding slack stays <=25 new CPU seconds.
    spec = {'wall_seconds': 30, 'cleanup_postflight_reserve_seconds': 5, 'cpu_seconds': 24,
            'address_space_bytes': 8589934592, 'private_output_bytes': 4194304}
    try:
        helper.limits(args.shared_stop, spec)
    except helper.Rejected as error:
        raise Rejected(error.code) from None
    repo, runtime, python = map(safe_path, (args.repo, args.runtime_root, args.python))
    actual_path, reference_path, capture_path, out = map(safe_path, (args.actual, args.reference, args.capture, args.out))
    need(actual_path.name == 'actual_n0.f32le' and capture_path.name == 'counts.json' and
         actual_path.parent == capture_path.parent, 'PATH')
    need(out.parent.is_dir() and not os.path.lexists(out), 'PATH')
    out.mkdir(mode=0o700)
    report = new_report()
    try:
        pins_raw = read_pin(args.pins, REFERENCE_PINS)
        pins = json.loads(pins_raw)
        need(pins['output']['bytes'] == REFERENCE['bytes'] and
             pins['output']['sha256'] == REFERENCE['sha256'] and pins['output']['shape'] == SHAPE, 'SOURCE')
        buffers = helper.source_buffers(repo, pins)
        original_raw = read_pin(repo/SCRIPT_PATH, ORIGINAL_SCRIPT)
        contract_raw = read_pin(repo/CONTRACT_PATH, ORIGINAL_CONTRACT)
        report['stage'] = 'CAPTURE'
        capture_raw = read_fixed(capture_path, 65536, maximum=True)
        capture_gate(capture_raw)
        report.update(capture_basic_counts_accepted=True, capture_sha256=digest(capture_raw))
        report['stage'] = 'INPUT'
        reference_raw = helper.read_checked(reference_path, REFERENCE)
        actual_raw = read_fixed(actual_path, REFERENCE['bytes'])
        report.update(reference_hash_accepted=True, actual_bytes=len(actual_raw), reference_bytes=len(reference_raw))
        report['stage'] = 'RUNTIME_IDENTITY'
        profile = pins['python_profiles']['ci31214']
        before = helper.runtime_before(runtime, python, profile, pins)
        sys.addaudithook(helper.no_external_actions)
        report['stage'] = 'RUNTIME_IMPORT'
        np, torch = runtime_import(runtime, pins)
        namespace = original_namespace(original_raw, np)
        policy = original_policy(namespace, contract_raw)
        actual, reference = checked_arrays(np, actual_raw, reference_raw)
        report['stage'] = 'COMPARE'
        result = evaluate(namespace, actual, reference, policy, actual_raw, reference_raw)
        report['stage'] = 'POSTFLIGHT'
        need(read_pin(args.reference_worker, REFERENCE_HELPER) == helper_raw and
             read_pin(args.pins, REFERENCE_PINS) == pins_raw and
             read_pin(repo/SCRIPT_PATH, ORIGINAL_SCRIPT) == original_raw and
             read_pin(repo/CONTRACT_PATH, ORIGINAL_CONTRACT) == contract_raw, 'CHANGED')
        need(helper.source_buffers(repo, pins) == buffers and
             helper.read_checked(reference_path, REFERENCE) == reference_raw and
             read_fixed(actual_path, REFERENCE['bytes']) == actual_raw and
             read_fixed(capture_path, 65536, maximum=True) == capture_raw, 'CHANGED')
        after = helper.runtime_before(runtime, python, profile, pins)
        need(after == before and torch.get_num_threads() == 4 and torch.get_num_interop_threads() == 1 and
             torch.are_deterministic_algorithms_enabled() and
             torch.backends.cpu.get_cpu_capability() == pins['runtime_requirements']['capability'] and
             digest(torch.__config__.show().encode()) == pins['runtime_requirements']['torch_build_sha256'], 'CHANGED')
        need(time.monotonic() < args.shared_stop - 5, 'DEADLINE')
        report.update(result)
        report.update(status='N0_LIMITED_TOLERANCE_PASS' if result['numeric_pass'] else 'N0_LIMITED_TOLERANCE_FAIL',
                      code=None, stage='COMPLETE')
    except (Rejected, helper.Rejected) as error:
        report.update(code=error.code if error.code in CODES else 'UNEXPECTED')
    except (MemoryError, TimeoutError):
        report.update(code='RESOURCE')
    except Exception:
        report.update(code='UNEXPECTED')
    write_receipt(out, report)
    return report

class FixedArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse constructs dynamic diagnostics internally; never render them.
        raise Rejected('FLAGS')

def main(argv=None):
    parser = FixedArgumentParser(prog='n0-compare', description=__doc__, allow_abbrev=False)
    for name in ('repo', 'reference-worker', 'pins', 'runtime-root', 'python', 'reference', 'actual', 'capture', 'out'):
        parser.add_argument('--' + name)
    parser.add_argument('--shared-stop', type=float)
    parser.add_argument('--execute', action='store_true')
    try:
        args = parser.parse_args(argv)
    except Rejected:
        print('NOT_COMPLETED:FLAGS')
        return 1
    if not args.execute:
        print('N0_COMPARISON_NOT_EXECUTED')
        return 0
    try:
        required = ('repo', 'reference_worker', 'pins', 'runtime_root', 'python', 'reference', 'actual', 'capture', 'out', 'shared_stop')
        need(all(getattr(args, name) is not None for name in required), 'FLAGS')
        need(math.isfinite(args.shared_stop), 'DEADLINE')
        report = run(args)
        print(report['status'] + (':' + report['code'] if report['code'] else ''))
        return 0 if report['numeric_pass'] is True else 1
    except Rejected as error:
        print('NOT_COMPLETED:' + error.code)
    except (MemoryError, TimeoutError):
        print('NOT_COMPLETED:RESOURCE')
    except Exception:
        print('NOT_COMPLETED:UNEXPECTED')
    return 1

if __name__ == '__main__':
    raise SystemExit(main())
