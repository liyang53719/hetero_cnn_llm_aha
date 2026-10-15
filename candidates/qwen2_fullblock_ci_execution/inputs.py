"""Fixed fresh CI inputs. Default performs no I/O; execution needs both opt-ins.

The explicit materialization stage compiles and loads the original pinned scalar
RoPE helper. It never runs a model/reference, imports Torch/NumPy, or uploads data.
All returned identities describe newly generated local records, never historical
manifests. A failed run is not resumed: use a clean isolated CI workspace.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = Path('/home/runner/work/hetero_cnn_llm_aha/hetero_cnn_llm_aha')
PATHS = {
    'qkv_raw': 'work/qwen2_live_qkv_inputs_m128/ci01/raw',
    'qkv_inputs': 'work/qwen2_live_qkv_inputs_m128/ci01/inputs',
    'tail_raw': 'work/qwen2_live_tail_acquisition_m128/ci01/raw',
    'tail_inputs': 'work/qwen2_live_tail_acquisition_m128/ci01/inputs',
}
SOURCE_HASHES = {
    'candidates/qwen2_live_qkv_inputs_m128/recipe.py': '15ff7d73838e2d049d3930abd0c05b17c3927bc7fd336aef0d5ddc93b98ba489',
    'candidates/qwen2_live_qkv_inputs_m128/capture.py': '7393857f674545e22de86d5685372b6801f422f06ad757c6565f1e82a23834a4',
    'candidates/qwen2_live_qkv_inputs_m128/pins.json': '503b452bb030050f0a570cde89448a4f5bd4c8b95b86e1d1cdb81a362729618d',
    'candidates/qwen2_live_tail_acquisition_m128/acquire.py': 'b63259ae7c3118eae9d221202ae33dc9732587b78b58a9a1538052a2a03bcb93',
    'candidates/qwen2_fullblock_ci_prepare/fresh_tail.py': 'd369a849333cc9d925577fcede198d9f8601eb1b1c3a970b40387a3d9ffe13a8',
}
MANIFESTS = {'qkv_raw': 'subset_manifest.json', 'qkv_inputs': 'INPUTS_READY.json',
             'tail_raw': 'FRESH_ACQUISITION.json', 'tail_inputs': 'INPUTS_READY.json'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_path(root, relative):
    need(type(relative) is str and relative and '\\' not in relative,
         'canonical relative path required')
    pieces = relative.split('/')
    need(not Path(relative).is_absolute() and all(p not in ('', '.', '..') for p in pieces),
         'canonical relative path required')
    path = root
    for piece in pieces:
        path = path / piece
        need(not path.is_symlink(), 'symlink path refused')
    need(path.resolve().is_relative_to(root), 'path escaped workspace')
    return path


def preflight(root):
    root = Path(root)
    need(root == CI_ROOT and root == ROOT and root.resolve() == root,
         'fixed isolated CI workspace required')
    # Inspect every ancestor too: resolve equality alone can hide a self alias.
    need(not any(p.is_symlink() for p in (root, *root.parents)), 'workspace symlink refused')
    need((root / '.git').exists(), 'checkout required')
    paths = [safe_path(root, value) for value in PATHS.values()]
    need(len(set(paths)) == 4, 'four distinct stages required')
    for i, path in enumerate(paths):
        need(not path.exists(), 'all four output stages must be absent before acquisition')
        for other in paths[i + 1:]:
            need(not path.is_relative_to(other) and not other.is_relative_to(path), 'overlapping stages')
    need(not any(n.split('.')[0] in ('torch', 'numpy', 'transformers') for n in sys.modules),
         'input preparation must run in a fresh stdlib process')
    return root


def source_check(root):
    sources = {}
    for relative, expected in SOURCE_HASHES.items():
        raw = safe_path(root, relative).read_bytes()
        need(sha(raw) == expected, 'input preparation source drift: ' + relative)
        sources[relative] = raw
    return sources


def load_source(root, relative, sources, name):
    # Execute exactly the checked in-memory bytes, not a later unverified reread.
    namespace = dict(__name__=name, __file__=str(root / relative))
    exec(compile(sources[relative], str(root / relative), 'exec'), namespace)
    return namespace


def contracts(root):
    sources = source_check(root)
    q = load_source(root, 'candidates/qwen2_live_qkv_inputs_m128/recipe.py', sources, '_ci_qkv_inputs')
    pins = q['load_pins'](root)
    q['source_check'](root, pins)
    tail = load_source(root, 'candidates/qwen2_fullblock_ci_prepare/fresh_tail.py', sources, '_ci_tail_inputs')
    a, n, tail_pins = tail['contract'](root)
    return q, pins, tail, a, n, tail_pins


def identity(root, role):
    raw = safe_path(root, PATHS[role] + '/' + MANIFESTS[role]).read_bytes()
    return {'bytes': len(raw), 'sha256': sha(raw)}


def prepare(root=ROOT, *, execute=False, download=False):
    # Reject missing authorization before any filesystem/network/helper operation.
    need(execute is True and download is True, 'both --execute and --download required')
    root = preflight(root)
    q, pins, tail, a, n, tail_pins = contracts(root)
    q['acquire'](root, pins, safe_path(root, PATHS['qkv_raw']), download=True)
    q['materialize'](root, pins, PATHS['qkv_raw'], safe_path(root, PATHS['qkv_inputs']))
    # Independently reread original reports, payload hashes and scalar provenance.
    manifest, _, subset_sha, _ = q['read_subset'](root, pins, PATHS['qkv_raw'])
    need(manifest['acquisition'] == 'fresh_HTTP206', 'QKV must be entirely fresh')
    _, qkv_ready_sha, _ = q['read_inputs'](root, pins, PATHS['qkv_inputs'], PATHS['qkv_raw'], subset_sha)
    raw_tail = a.acquire(root, PATHS['tail_raw'], n, tail_pins)
    seal_sha = raw_tail['manifest_sha256']
    need(identity(root, 'tail_raw')['sha256'] == seal_sha, 'tail acquisition seal drift')
    tail['materialize'](root, PATHS['tail_raw'], PATHS['tail_inputs'], seal_sha)
    records = {name: identity(root, name) for name in PATHS}
    need(records['qkv_raw']['sha256'] == subset_sha and
         records['qkv_inputs']['sha256'] == qkv_ready_sha, 'QKV metadata changed after verification')
    tail['input_metadata'](root, PATHS['tail_inputs'], records['tail_inputs']['sha256'], seal_sha)
    source_check(root)
    return {'schema': 1, 'status': 'FRESH_CI_INPUTS_READY', 'metadata': records,
            'qkv_http_ranges': 8, 'tail_http_ranges': 14, 'qkv_roles': 9, 'tail_roles': 5,
            'reused_raw_tensors': 0, 'historical_manifest_recreated': False,
            'scalar_rope_executed': True, 'model_executed': False,
            'reference_executed': False, 'rtl_executed': False,
            'source_hashes': dict(SOURCE_HASHES)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args(argv)
    try:
        if not args.execute and not args.download:
            result = {'status': 'NOT_EXECUTED', 'network_used': False, 'outputs_written': False,
                      'raw_payload_read': False, 'model_executed': False, 'reference_executed': False}
        else:
            result = prepare(execute=args.execute, download=args.download)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        # Errors go only to local stderr; never upload unrestricted exceptions.
        print(json.dumps({'status': 'REJECTED', 'reason': str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
