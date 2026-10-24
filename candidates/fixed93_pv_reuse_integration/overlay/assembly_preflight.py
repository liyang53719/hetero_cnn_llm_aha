"""Fresh Fixed93 fullblock assembly checks, with no DUT or native imports.

The same byte/AST preflight must be used by the future supervised actual entry.
Passing this function does not create authority or close the resource gate.
Reference tensor payloads are stat-checked only in this fresh process.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'SOURCE_MANIFEST.json'
BASE_SHA = 'fb45a594e6cf516f9ce722d5db1279950241083206486e164782367b48811423'
R3_SHA = '26928f829488600765cefa2d836f4afe32413e03798ae0eb958bfd016994e13d'
CONTRACT = 'original-algorithm-arrays-plus-true-events-and-pv-reuse-attention-v1'
PV_REUSE_DELTA = {'source/candidates/qwen2_fixed93_attention/owner.py': {'before': {'bytes': 15337, 'sha256': '1e90ecb2e5cf26755c7fe5b7cc201d563afde23af6c27105daeb2387cb5cf443'}, 'after': {'bytes': 15806, 'sha256': 'b18172eb9af3f047eaed5aa3d6e40741e57add5b0b856c6817017cc16693bc0e'}}, 'selected/chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala': {'before': {'bytes': 56051, 'sha256': 'a6e7f781dd46063a7373c712f7d8eda289038e0be51e0f9184f382fe26805491'}, 'after': {'bytes': 57109, 'sha256': '3b7f25537da7492d3c706c55129ca5ed0a18d9c2e0ec4f5d9e6e43b1ae2210d4'}}}



def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, expected=None, *, retain=True):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'canonical regular path required')
    h = hashlib.sha256()
    data = [] if retain else None
    total = 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode), 'regular source/runtime file required')
        while block := stream.read(1048576):
            h.update(block)
            total += len(block)
            if retain:
                data.append(block)
        after = os.fstat(stream.fileno())
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(stamp(before) == stamp(after) == stamp(path.stat()), 'file changed during hash')
    identity = dict(bytes=total, sha256=h.hexdigest())
    need(expected is None or identity == {k: expected[k] for k in ('bytes', 'sha256')}, 'file identity drift: ' + str(path))
    return b''.join(data) if retain else identity


def relative(root, name):
    need(type(name) is str and name and not Path(name).is_absolute() and
         '..' not in Path(name).parts, 'relative source namespace required')
    return root / name


def source_inventory(root):
    found = set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        parent = Path(parent)
        if parent == root and 'work' in dirs:
            dirs.remove('work')
        for name in dirs:
            need(not (parent / name).is_symlink() and name != '__pycache__', 'source alias/bytecode directory')
        for name in files:
            path = parent / name
            st = path.lstat()
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'source special/hardlinked file')
            found.add(str(path.relative_to(root)))
    return found


def successor_assembly(base_objects):
    """Exactly two reviewed byte deltas; all other baseline entries retained."""
    need(type(base_objects) is list and len(base_objects) == 321, 'exact321 baseline objects')
    result = {}
    for item in base_objects:
        need(type(item) is dict and {'path','bytes','sha256'} <= item.keys(), 'baseline object shape')
        name = item['path']
        need(type(name) is str and name not in result and not Path(name).is_absolute() and
             '..' not in Path(name).parts, 'unique relative baseline namespace')
        need(type(item['bytes']) is int and item['bytes'] >= 0 and type(item['sha256']) is str and
             len(item['sha256']) == 64 and all(c in '0123456789abcdef' for c in item['sha256']),
             'baseline strict byte/hash types')
        result[name] = dict(bytes=item['bytes'], sha256=item['sha256'])
    for name, change in PV_REUSE_DELTA.items():
        need(result.get(name) == change['before'], 'wrong predecessor for exact successor delta: '+name)
        result[name] = dict(change['after'])
    return result


def validate_successor_identity(manifest):
    need(type(manifest) is dict and manifest.get('schema') == 'fixed93-pv-reuse-source-manifest-v1' and
         manifest.get('evidence_contract') == CONTRACT and
         manifest.get('candidate_identity') == 'fixed93-pv-normalization-reuse-source-candidate-v1' and
         manifest.get('reviewed_manifest_sha256','missing') is None and
         manifest.get('predecessor_reviewed_manifest_sha256') == R3_SHA and
         manifest.get('candidate_review_status') == 'SOURCE_PREPARED_REVIEW_SEPARATE' and
         manifest.get('old_pass_inherited') is False and manifest.get('actual_execution_authorized') is False,
         'exact new PV reuse identity; predecessor PASS is not current authority')


def validate_successor_domain(manifest, expected, directory, hash_key, size_key, count):
    hashes, sizes = manifest[hash_key], manifest[size_key]
    need(type(hashes) is dict and type(sizes) is dict and hashes.keys() == sizes.keys() and len(hashes) == count,
         'exact successor domain inventory: '+directory)
    need(all(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts and
             type(sizes[name]) is int and sizes[name] >= 0 and type(sha) is str and len(sha) == 64 and
             all(c in '0123456789abcdef' for c in sha) for name,sha in hashes.items()),
         'strict successor source byte/hash types')
    need({directory+'/'+name:dict(bytes=sizes[name],sha256=sha) for name,sha in hashes.items()} ==
         {name:pin for name,pin in expected.items() if name.startswith(directory+'/')},
         'only exact owner and selected Scala successor changes allowed: '+directory)


def verify(expected_sha):
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,
         'python -I -S -B without optimization required')
    need(type(expected_sha) is str and len(expected_sha) == 64 and
         all(c in '0123456789abcdef' for c in expected_sha), 'explicit NEW source-manifest SHA required')
    need(not any(n.split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates') for n in sys.modules),
         'source preflight must precede all native/DUT imports')
    raw = checked(MANIFEST)
    need(digest(raw) == expected_sha, 'reviewed manifest file differs')
    manifest = json.loads(raw)
    validate_successor_identity(manifest)
    base = checked(HERE / 'ASSEMBLY_BASE.json')
    need(digest(base) == BASE_SHA, 'exact306/selected9/support6 predecessor assembly')
    base_objects = json.loads(base)['objects']
    expected_successor = successor_assembly(base_objects)
    for directory, hash_key, size_key, count in (
            ('source', 'source_sha256', 'source_bytes', 306),
            ('selected', 'selected_source_sha256', 'selected_source_bytes', 9),
            ('support', 'support_sha256', 'support_bytes', 6)):
        hashes, sizes = manifest[hash_key], manifest[size_key]
        need(type(hashes) is dict and type(sizes) is dict and hashes.keys() == sizes.keys() and
             len(hashes) == count and source_inventory(HERE / directory) == set(hashes),
             'exact immutable assembly inventory: ' + directory)
        validate_successor_domain(manifest, expected_successor, directory, hash_key, size_key, count)
        for name, sha in hashes.items():
            checked(relative(HERE / directory, name), dict(bytes=sizes[name], sha256=sha), retain=False)
    for name, pin in manifest['preparation_files'].items():
        path = relative(HERE, name)
        raw = checked(path, pin)
        if name.endswith('.py'):
            ast.parse(raw, filename=str(path))
            compile(raw, str(path), 'exec', dont_inherit=True, optimize=0)
    runtime = json.loads(checked(HERE / 'RUNTIME_PINS.json'))
    for name, pin in runtime['files'].items():
        checked(Path(name), pin, retain=False)
    need(Path(sys.executable).resolve() == Path(runtime['python']['path']), 'exact existing Python runtime required')
    copies = json.loads(checked(HERE / 'contract/FROZEN_DATA_COPIES.json'))
    reference_stats = 0
    for name, pin in copies['files'].items():
        path = relative(HERE / 'source', name)
        if name.startswith('work/qwen2_recovered_reference/first/') and path.suffix in ('.f32le', '.bf16le'):
            st = path.lstat()
            need(stat.S_ISREG(st.st_mode) and not path.is_symlink() and st.st_size == pin['bytes'],
                 'frozen reference payload extent')
            reference_stats += 1
        else:
            checked(path, pin, retain=False)
    need(reference_stats == 30, 'exact29 + native mask reference payload stat-only boundary')
    binding = json.loads(checked(HERE / 'source/work/qwen2_fixed93_fullblock_binding/FROZEN_BINDING.json'))
    source_map = {name: dict(bytes=manifest['source_bytes'][name], sha256=sha)
                  for name, sha in manifest['source_sha256'].items()}
    need(binding['source_closure_sha256'] == digest(json.dumps(source_map, sort_keys=True,
         separators=(',', ':'), allow_nan=False).encode()), 'noncircular306 source binding')
    budget = json.loads(checked(HERE / 'BUDGET_PROPOSAL.json'))
    result = dict(status='SOURCE_ASSEMBLY_BYTE_AST_ONLY', source_manifest_sha256=expected_sha,
                  source_files=306, selected_files=9, support_files=6, runtime_files=len(runtime['files']),
                  input_reference_metadata_files=76, reference_payloads_stat_only=reference_stats,
                  reference_payloads_read=0, native_imported=False, constructor_executed=False,
                  actual_authorized=False, resource_gate_status=budget['status'],
                  complete_actual_admission=False, fullblock=False, M128_executed=False, RTL=False)
    return result, manifest, runtime, budget


def preflight(expected_sha):
    state = {'active': True, 'attempts': []}
    def audit(event, args):
        if not state['active']:
            return
        if event.startswith(('ctypes.', 'subprocess.', 'socket.')) or event in (
                'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn'):
            state['attempts'].append(event)
            raise RuntimeError('preflight native/process/network boundary denied: ' + event)
        if event == 'import' and args[0].split('.')[0] in ('numpy', 'ctypes', 'torch', 'candidates'):
            state['attempts'].append('import:' + args[0])
            raise RuntimeError('preflight DUT/native import denied')
    sys.addaudithook(audit)
    try:
        result, manifest, runtime, budget = verify(expected_sha)
        need(not state['attempts'], 'source preflight attempted forbidden action')
        result['denied_boundary_attempts'] = list(state['attempts'])
        return result, manifest, runtime, budget
    finally:
        state['active'] = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(preflight(args.manifest_sha)[0], sort_keys=True))
