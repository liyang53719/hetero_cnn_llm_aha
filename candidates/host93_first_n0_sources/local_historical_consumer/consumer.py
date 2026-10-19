"""Read-only preflight for an explicit local historical N0 consumer.

No default action, process launch, download, runtime import or reference forward.
The caller owns admission, the original shared deadline, and every native phase.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
import types

SOURCE_PINS = {'candidates/host93_ci_recovery/first_n0/pipeline.py': {'bytes': 31285, 'sha256': 'fa1f359f3e7145cabdeed32898799ac5f72c8fa5fcccd29a0dd21c8970385e12'}, 'candidates/host93_first_n0_sources/historical_comparison/n0_compare.py': {'bytes': 21000, 'sha256': 'e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800'}, 'candidates/host93_first_n0_sources/inputs/CONVERSION_SPEC.json': {'bytes': 17884, 'sha256': 'ab1fabb72d69f0f196dafd19fe7324a1413b000952e0ee04baa3cbaaff4a14ac'}, 'candidates/host93_first_n0_sources/reference/PINS.json': {'bytes': 6364, 'sha256': 'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8'}, 'candidates/host93_first_n0_sources/reference/n0_reference.py': {'bytes': 13753, 'sha256': 'd26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4'}, 'candidates/qwen2_fullblock_ci_execution/platform.py': {'bytes': 6165, 'sha256': 'd644fbf000f5237d6b1e46cd8564d80d0cb5c737f431e21e674cdf98fa128cd8'}, 'candidates/qwen2_fullblock_ci_prepare/requirements-runtime.txt': {'bytes': 1217, 'sha256': '9bd334944d52ae82a86ca89ac44612920270c028f29c15fde93ba4d656535a83'}, 'candidates/qwen2_fullblock_reference_m128/FROZEN_CONTRACT.json': {'bytes': 19978, 'sha256': '64835641b2c0c16d83beb75fbcd9d1c83ade8676fbd825f5e6ab646167af723f'}, 'candidates/qwen2_fullblock_reference_m128/capture.py': {'bytes': 20084, 'sha256': '7bbee0a7edc6d36fb4996657ecea75c5181d292c9761bbb18ca4b12fc2486a86'}, 'candidates/qwen2_fullblock_reference_m128/pins.json': {'bytes': 154690, 'sha256': '48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'}, 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py': {'bytes': 63883, 'sha256': 'f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad'}, 'scripts/qwen2_layer0_model_gate.py': {'bytes': 37776, 'sha256': '917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'}, 'spec/numerical_contract.md': {'bytes': 2256, 'sha256': '5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5'}}
PIPELINE = 'candidates/host93_ci_recovery/first_n0/pipeline.py'
REFERENCE = 'candidates/host93_first_n0_sources/reference/'
COMPARISON = 'candidates/host93_first_n0_sources/historical_comparison/'
PROJECTED_PIN = {'bytes': 31296, 'sha256': 'c3885d039b97861b17a29d74e6bf58448873d1ae476dbffa806a22a199b581cd'}
OLD = b"COMPARISON='candidates/host93_first_n0_sources/comparison/'"
NEW = b"COMPARISON='candidates/host93_first_n0_sources/historical_comparison/'"
RECEIPT_PIN = {'bytes': 4466, 'sha256': 'b2ebccff3ad995a40e79a73974c332e22c5e042cae4cac8dc6a5ec55ed4fc046'}
F32 = {'bytes': 786432, 'sha256': '3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f'}
BF16 = {'bytes': 393216, 'sha256': 'bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2'}
CODES = frozenset(('FLAGS', 'SOURCE', 'PATH', 'CHANGED', 'PINS', 'PYTHON',
                   'RUNTIME', 'REFERENCE', 'DEADLINE', 'INPUTS', 'INCOMPLETE_N0_WINDOW'))


class Rejected(ValueError):
    def __init__(self, code):
        self.code = code if code in CODES else 'SOURCE'
        super().__init__(self.code)


def need(ok, code):
    if not ok:
        raise Rejected(code)


def isolated():
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'FLAGS')
    need(not any(name.split('.')[0] in ('torch', 'numpy', 'transformers') for name in sys.modules), 'RUNTIME')


def path(value):
    p = Path(value)
    need(p.is_absolute() and '..' not in p.parts and p.resolve() == p and
         all(not parent.is_symlink() for parent in (p, *p.parents)), 'PATH')
    return p


def checked(raw, pin):
    need(type(raw) is bytes and len(raw) == pin['bytes'] and
         hashlib.sha256(raw).hexdigest() == pin['sha256'], 'SOURCE')
    return raw


def read(pathname, pin):
    p = path(pathname)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_size == pin['bytes'], 'SOURCE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(pin['bytes'] + 1)
        last = os.fstat(fd)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(stamp(first) == stamp(last) == stamp(p.stat()), 'CHANGED')
        return checked(raw, pin)
    finally:
        os.close(fd)


def module(raw, pin, label):
    isolated()
    checked(raw, pin)
    result = types.ModuleType(label)
    result.__file__ = '<' + label + '>'
    exec(compile(raw, result.__file__, 'exec', dont_inherit=True), result.__dict__)
    return result


def load_pipeline(repo, caller_pins):
    """Fixed same-buffer loader; all original functions remain byte-identical."""
    isolated()
    repo = path(repo)
    need(type(caller_pins) is dict and all(caller_pins.get(name) == pin
         for name, pin in SOURCE_PINS.items()), 'PINS')
    buffers = {name: read(repo / name, pin) for name, pin in SOURCE_PINS.items()}
    candidate = read(Path(__file__).absolute().parent / 'pipeline_historical.py', PROJECTED_PIN)
    need(candidate.count(NEW) == 1 and OLD not in candidate and
         candidate.replace(NEW, OLD) == buffers[PIPELINE], 'SOURCE')
    pipeline = module(candidate, PROJECTED_PIN, '_fixed_local_historical_pipeline')
    need(pipeline.COMPARISON == COMPARISON, 'SOURCE')
    return pipeline, buffers


def deadline(shared_stop):
    need(type(shared_stop) in (int, float) and math.isfinite(shared_stop) and
         time.monotonic() < shared_stop - 15, 'DEADLINE')


def require_numeric_window(original_shared_stop):
    """Caller repeats immediately before N0; never mint a new total deadline.

    Original run_numeric subtracts 15 seconds internally. Subtracting 105 here
    makes its absolute bound original_stop - 120 while preserving its 3600s
    numeric window. The full 3720 seconds must remain before starting N0.
    """
    deadline(original_shared_stop)
    need(original_shared_stop - time.monotonic() >= 3720, 'INCOMPLETE_N0_WINDOW')
    return original_shared_stop - 105


def prepare(repo, inputs, caller_pins, shared_stop, *, runtime_root, reference_file, reference_receipt):
    """Return (original run_numeric, explicit front, read-only observation).

    Runtime binaries are only streamed/hash-checked through the original helper.
    Original reference evidence is read, never rewritten or regenerated. No
    imported capability/build/thread qualification is claimed by this function.
    """
    isolated()
    require_numeric_window(shared_stop)
    pipeline, buffers = load_pipeline(repo, caller_pins)
    repo = path(repo)
    inputs = path(inputs)
    runtime = path(runtime_root)
    reference = path(reference_file)
    receipt_path = path(reference_receipt)
    python = path(Path(sys.executable).resolve())
    need(runtime.name == 'runtime' and reference.name == 'n0.f32le' and
         reference.parent.name == 'reference' and receipt_path.name == 'RECEIPT.json' and
         receipt_path.parent == reference.parent, 'PATH')
    need(inputs.is_dir(), 'INPUTS')
    need(runtime.is_dir(), 'RUNTIME')
    need(python.name == 'python3.12' and sys.implementation.name == 'cpython' and
         list(sys.version_info[:2]) == [3, 12], 'PYTHON')
    pins = pipeline.decode(buffers[REFERENCE + 'PINS.json'])
    helper = module(buffers[REFERENCE + 'n0_reference.py'],
                    SOURCE_PINS[REFERENCE + 'n0_reference.py'], '_fixed_original_reference_helper')
    try:
        identities = helper.runtime_before(runtime, python,
                                           pins['python_profiles']['historical'], pins)
    except helper.Rejected:
        raise Rejected('RUNTIME') from None
    # This is an immutable prior reference receipt, not a newly minted PASS.
    receipt_raw = read(receipt_path, RECEIPT_PIN)
    receipt = pipeline.decode(receipt_raw)
    need(receipt.get('schema') == 1 and receipt.get('scope') == 'FROZEN_M128_N0_REFERENCE_ONLY' and
         receipt.get('status') == 'PASS_FROZEN_N0_EXACT' and receipt.get('stage') == 'COMPLETE' and
         receipt.get('code') is None and receipt.get('reference_accepted') is True and
         receipt.get('python_profile') == 'historical' and receipt.get('rtl_executed') is False and
         receipt.get('fullblock_executed') is False and receipt.get('source_identities') == pins['sources'] and
         receipt.get('input_identities') == pins['raw2'] and
         receipt.get('runtime_requirements') == pins['runtime_requirements'] and
         receipt.get('runtime_before') == receipt.get('runtime_after') == identities and
         receipt.get('output') == {'native': BF16, 'fp32le': F32, 'native_exact': True,
                                  'fp32le_exact': True, 'accepted': True}, 'REFERENCE')
    read(reference, F32)
    need(all(read(repo / name, pin) == buffers[name] for name, pin in SOURCE_PINS.items()), 'CHANGED')
    need(read(receipt_path, RECEIPT_PIN) == receipt_raw, 'CHANGED')
    require_numeric_window(shared_stop)
    isolated()
    front = {'inputs': inputs, 'runtime': runtime, 'reference': reference}
    observation = {
        'schema': 1, 'scope': 'LOCAL_HISTORICAL_CONSUMER_PREFLIGHT_ONLY',
        'python_profile': 'historical', 'runtime_file_identities_checked': True,
        'runtime_file_identities': identities, 'current_runtime_dispatch_qualified_here': False,
        'existing_reference_receipt': dict(RECEIPT_PIN), 'existing_reference_fp32': dict(F32),
        'reference_origin': 'EXISTING_ORIGINAL_HISTORICAL_REFERENCE',
        'original_dual_sha_receipt_checked': True, 'reference_regenerated_here': False,
        'frontdoor_completed_here': False, 'numeric_runtime_imported_here': False,
        'host_or_comparison_executed_here': False, 'baseline_adopted': False,
        'shared_deadline_reused': True,
        'required_numeric_window_seconds': 3600, 'outer_tail_reserve_seconds': 120,
        'original_run_numeric_deadline_offset_seconds': 105,
    }
    return pipeline.run_numeric, front, observation
