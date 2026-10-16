"""Compose the separate, pinned M128 runtime source layer without executing it.

The published nine-file preparation is the exact starting point. Only the setup
variant and explicit assets/entry source-identity bridge are added here. A source
preparation receipt is not a setup, admission or numerical acceptance receipt.
"""
import ast
import hashlib
from pathlib import Path
import stat
import subprocess

from candidates.qwen2_resident_matrix.raw_kv_public_m128 import profile as previous
from candidates.qwen2_resident_matrix.raw_kv_public_m128 import prerequisite

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_m128_runtime/'
BRIDGE_TARGETS = (prerequisite.ASSETS, prerequisite.ENTRY)
PATCH_TARGETS = {'setup128.patch': (prerequisite.SETUP,), 'bridging.patch': BRIDGE_TARGETS}
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_source(name):
    path = ROOT / previous.relative_name(name)
    for part in (path, *path.parents):
        need(not part.is_symlink(), 'runtime preparation source symlink')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= previous.MAX_SOURCE_BYTES,
         'runtime preparation source type/size')
    with path.open('rb') as stream:
        raw = stream.read(previous.MAX_SOURCE_BYTES + 1)
    after = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    need(len(raw) == info.st_size and identity(after) == identity(info), 'runtime preparation source read drift')
    return raw


def _dump(node):
    return ast.dump(node, include_attributes=False)


def check_bridge_scope(originals, generated):
    """Exact AST equivalence except the two imports and one source-map return."""
    need(set(originals) == set(generated) == set(BRIDGE_TARGETS), 'exact runtime bridge targets required')
    old_import = ast.parse('from ..raw_kv_public_m128 import profile as m128_profile').body[0]
    new_import = ast.parse('from ..raw_kv_public_m128_runtime import runtime as m128_profile').body[0]
    new_return = ast.parse('return m128_profile.own_asset_sources()').body[0]
    for name in BRIDGE_TARGETS:
        before = ast.parse(originals[name]); after = ast.parse(generated[name])
        old_matches = [node for node in before.body if _dump(node) == _dump(old_import)]
        new_matches = [node for node in after.body if _dump(node) == _dump(new_import)]
        need(len(old_matches) == len(new_matches) == 1, 'exact runtime bridge import required')
        after.body[after.body.index(new_matches[0])] = old_import
        if name == prerequisite.ASSETS:
            old_functions = [node for node in before.body if isinstance(node, ast.FunctionDef) and node.name == 'own_sources']
            new_functions = [node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == 'own_sources']
            need(len(old_functions) == len(new_functions) == 1, 'exact own_sources bridge function required')
            original = old_functions[0]; updated = new_functions[0]
            need(len(original.body) == len(updated.body) == 2 and
                 _dump(updated.body[0]) == _dump(original.body[0]) and
                 _dump(updated.body[1]) == _dump(new_return), 'exact own_sources guard/return required')
            updated.body[1] = original.body[1]
        need(_dump(before) == _dump(after), 'runtime bridge exceeds source-identity plumbing')


def _inventory(out):
    result = {}
    for path in out.rglob('*'):
        need(not path.is_symlink(), 'runtime generated symlink')
        if path.is_dir():
            continue
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) and info.st_size <= previous.MAX_SOURCE_BYTES,
             'runtime generated source type/size')
        raw = path.read_bytes()
        name = str(path.relative_to(out))
        ast.parse(raw, filename=name)
        result[name] = sha(raw)
    return result


def prepare(out, *, enable_raw_kv=True):
    need(type(enable_raw_kv) is bool and enable_raw_kv is True, 'runtime preparation requires explicit raw KV')
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'fresh runtime composition directory required')
    need(all(not parent.is_symlink() for parent in out.parents), 'runtime output ancestor symlink')
    # The sibling contract is source/hash-only and validates independently frozen pins.
    from . import runtime
    snapshot = runtime.contract_snapshot(composed=False)
    need(type(snapshot) is dict and type(snapshot.get('inputs')) is dict and
         type(snapshot.get('generated')) is dict, 'runtime source contract schema')
    need(snapshot['inputs'].get(PREFIX + 'prepare.py') == IMPORTED_SHA256 and
         sha(read_source(PREFIX + 'prepare.py')) == IMPORTED_SHA256, 'loaded runtime preparer drift')
    baseline = previous.prepare(out, enable_raw_kv=True)
    need(all(snapshot['inputs'].get(name) == identity for name, identity in baseline['inputs'].items()),
         'published M128 preparation input drift')
    need(_inventory(out) == baseline['generated'], 'published nine-overlay preparation drift')
    expected_names = set(baseline['generated']) | {prerequisite.SETUP}
    need(len(expected_names) == 10 and set(snapshot['generated']) == expected_names,
         'exact ten runtime overlays required')
    need(all(snapshot['generated'][name] == identity for name, identity in baseline['generated'].items()
             if name not in BRIDGE_TARGETS), 'unchanged seven M16 overlays differ')
    for name in (*BRIDGE_TARGETS, prerequisite.SETUP):
        old = baseline['generated'].get(name, baseline['inputs'].get(name))
        need(snapshot['generated'][name] != old, 'explicit runtime variants required')
    setup_raw = read_source(prerequisite.SETUP)
    need(sha(setup_raw) == baseline['inputs'][prerequisite.SETUP], 'original setup identity drift')
    target = out / prerequisite.SETUP
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(setup_raw)
    originals = {name: (out / name).read_bytes() for name in BRIDGE_TARGETS}
    for filename, targets in PATCH_TARGETS.items():
        raw = read_source(PREFIX + filename)
        need(sha(raw) == snapshot['inputs'].get(PREFIX + filename), 'runtime patch source drift')
        text = raw.decode('utf-8')
        need([line for line in text.splitlines() if line.startswith('--- ')] == ['--- a/' + name for name in targets] and
             [line for line in text.splitlines() if line.startswith('+++ ')] == ['+++ b/' + name for name in targets],
             'runtime patch target scope differs')
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=out, input=raw,
                       check=True, capture_output=True, timeout=10)
    generated = _inventory(out)
    need(generated == snapshot['generated'], 'runtime generated source identity drift')
    check_bridge_scope(originals, {name: (out / name).read_bytes() for name in BRIDGE_TARGETS})
    need(runtime.contract_snapshot(composed=False) == snapshot, 'runtime preparation source postflight drift')
    return dict(status='PASS_PREPARATION_ONLY', enable_raw_kv=True, inputs=dict(snapshot['inputs']),
                generated=generated, numerical_execution=False, native_execution=False,
                m128_executed=False, full_29_node_acceptance=False)
