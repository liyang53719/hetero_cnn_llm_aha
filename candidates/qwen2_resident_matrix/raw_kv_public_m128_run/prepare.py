"""Compose ten exact linked-M128 source overlays without executing them.

The frozen runtime preparer is unchanged. This layer replaces three alias imports and the
backend preflight subprocess's diagnostic dispatch target. Original backend
validation, arithmetic, comparisons, transport and subprocess deadlines stay
unchanged.
"""
import ast
import hashlib
from pathlib import Path
import subprocess

from ..raw_kv_public_m128 import prerequisite
from ..raw_kv_public_m128_runtime import prepare as previous

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_m128_run/'
PATCH = PREFIX + 'launch_bridge.patch'
BRIDGE_TARGETS = (prerequisite.ASSETS, prerequisite.ENTRY, prerequisite.SETUP)
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_source(name):
    need(ROOT == previous.ROOT, 'launch preparation source root differs')
    return previous.read_source(name)


def check_bridge_scope(originals, generated):
    """Whole-AST identity except three imports and one diagnostic dispatch."""
    need(set(originals) == set(generated) == set(BRIDGE_TARGETS), 'exact launch bridge targets required')
    for name in BRIDGE_TARGETS:
        alias = 'm128_runtime' if name == prerequisite.SETUP else 'm128_profile'
        old_import = ast.parse('from ..raw_kv_public_m128_runtime import runtime as ' + alias).body[0]
        new_import = ast.parse('from ..raw_kv_public_m128_run import launch as ' + alias).body[0]
        before, after = ast.parse(originals[name]), ast.parse(generated[name])
        old_matches = [node for node in before.body if ast.dump(node) == ast.dump(old_import)]
        new_matches = [node for node in after.body if ast.dump(node) == ast.dump(new_import)]
        need(len(old_matches) == len(new_matches) == 1, 'exact launch bridge import required')
        after.body[after.body.index(new_matches[0])] = old_import
        if name == prerequisite.SETUP:
            old_code = ast.parse("code='from pathlib import Path; from '+MODULE+' import backend_preflight; backend_preflight(Path('+repr(str(workspace/'context.json'))+'))'").body[0]
            new_code = ast.parse("code='from pathlib import Path; from '+'candidates.qwen2_resident_matrix.raw_kv_public_m128_run.launch'+' import backend_preflight; backend_preflight(Path('+repr(str(workspace/'context.json'))+'))'").body[0]
            original = [node for node in before.body if isinstance(node, ast.FunctionDef) and node.name == '_phase_environment']
            updated = [node for node in after.body if isinstance(node, ast.FunctionDef) and node.name == '_phase_environment']
            need(len(original) == len(updated) == 1, 'exact backend environment function required')
            old_codes = [node for node in original[0].body if ast.dump(node) == ast.dump(old_code)]
            new_codes = [node for node in updated[0].body if ast.dump(node) == ast.dump(new_code)]
            need(len(old_codes) == len(new_codes) == 1, 'exact backend diagnostic dispatch required')
            updated[0].body[updated[0].body.index(new_codes[0])] = old_codes[0]
        need(ast.dump(before) == ast.dump(after), 'launch bridge exceeds reviewed import/diagnostic scope')


def prepare(out, *, enable_raw_kv=True):
    need(type(enable_raw_kv) is bool and enable_raw_kv is True, 'launch preparation requires explicit raw KV')
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'fresh launch composition directory required')
    need(all(not parent.is_symlink() for parent in out.parents), 'launch output ancestor symlink')
    from . import launch
    snapshot = launch.contract_snapshot(composed=False)
    need(type(snapshot) is dict and type(snapshot.get('inputs')) is dict and
         type(snapshot.get('generated')) is dict, 'launch source contract schema')
    need(snapshot['inputs'].get(PREFIX + 'prepare.py') == IMPORTED_SHA256 and
         sha(read_source(PREFIX + 'prepare.py')) == IMPORTED_SHA256, 'loaded launch preparer drift')
    baseline = previous.prepare(out, enable_raw_kv=True)
    need(all(snapshot['inputs'].get(name) == identity for name, identity in baseline['inputs'].items()),
         'published runtime input drift')
    need(previous._inventory(out) == baseline['generated'], 'published ten-overlay runtime drift')
    need(len(baseline['generated']) == 10 and set(snapshot['generated']) == set(baseline['generated']),
         'exact ten launch overlays required')
    need(all(snapshot['generated'][name] == identity for name, identity in baseline['generated'].items()
             if name not in BRIDGE_TARGETS), 'unchanged seven M16 overlays differ')
    need(all(snapshot['generated'][name] != baseline['generated'][name] for name in BRIDGE_TARGETS),
         'explicit three launch variants required')
    originals = {name: (out / name).read_bytes() for name in BRIDGE_TARGETS}
    raw = read_source(PATCH)
    need(sha(raw) == snapshot['inputs'].get(PATCH), 'launch patch source drift')
    lines = raw.decode('utf-8').splitlines()
    need([line for line in lines if line.startswith('--- ')] == ['--- a/' + name for name in BRIDGE_TARGETS] and
         [line for line in lines if line.startswith('+++ ')] == ['+++ b/' + name for name in BRIDGE_TARGETS],
         'launch patch target scope differs')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=out, input=raw,
                   check=True, capture_output=True, timeout=10)
    generated = previous._inventory(out)
    need(generated == snapshot['generated'], 'launch generated source identity drift')
    check_bridge_scope(originals, {name: (out / name).read_bytes() for name in BRIDGE_TARGETS})
    need(launch.contract_snapshot(composed=False) == snapshot, 'launch preparation source postflight drift')
    return dict(status='PASS_PREPARATION_ONLY', enable_raw_kv=True, inputs=dict(snapshot['inputs']),
                generated=generated, numerical_execution=False, native_execution=False,
                m128_executed=False, full_29_node_acceptance=False)
