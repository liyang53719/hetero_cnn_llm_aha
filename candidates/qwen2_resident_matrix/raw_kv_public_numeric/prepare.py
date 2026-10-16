"""Compose a pinned, default-off PV16 entry and explicit source-contract variant.

This module performs only source reads, hashes, AST checks and bounded patch
application. It does not import any numerical verifier or execute arithmetic.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from candidates.qwen2_resident_matrix.raw_kv_public import prepare as upstream

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREFIX = 'candidates/qwen2_resident_matrix/'
ENTRY = PREFIX + 'dense_block_reduce/check_public_numeric.py'
GUARDS = ('scripts/observe_qwen2_attention_model.py',
          PREFIX + 'official_bf16/observation.py',
          PREFIX + 'official_bf16/observation_monitoring.py',
          PREFIX + 'dense_block_reduce/observation.py')
INVENTORY = PREFIX + 'ffn_public/fullgraph_numerical_receipt.json'
BRIDGE = PREFIX + 'raw_kv_attention/numeric_bridge.py'
OWN_INPUTS = ('entry.patch', 'guard.patch', 'prepare.py', 'pins.json', 'README.md', 'test_entry.py')
TARGETS = (*upstream.TARGETS, ENTRY, *GUARDS)
BASE_COMMIT = 'e5d4377a4d19d85314319f3339428e2c292bc7f9'
HISTORICAL_COMMIT = '38b943cdf6a0e2d642a1aef07b30e6d23e3ceed8'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def _literal(source, name):
    values = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    need(len(values) == 1, 'unique source constant required: ' + name)
    return ast.literal_eval(values[0])


class _DisabledProjection(ast.NodeTransformer):
    """Project declared mode plumbing to the disabled branch and compare ASTs.

    This proves the original disabled projection only. Enabled branches and
    identity checks require direct review and exact generated-source hash pins;
    this projection alone does not establish their semantics.
    """
    constants = {'RAW_KV_SOURCES', 'RAW_KV_SOURCE_PROFILE', 'RAW_KV_COMPOSITION_SHA256',
                 'RAW_KV_EXECUTION_SOURCE_REPLACEMENTS', 'RAW_KV_HELPER_SHA256',
                 'RAW_KV_CAPTURE_SHA256', 'RAW_KV_MONITORING_SHA256'}

    def visit_FunctionDef(self, node):
        if node.name in ('_raw_kv_mode', '_snapshot_raw_kv_mode', '_verify_raw_kv_composition'):
            return None
        pairs = [(a, d) for a, d in zip(node.args.kwonlyargs, node.args.kw_defaults)
                 if a.arg != 'enable_raw_kv']
        node.args.kwonlyargs = [a for a, _ in pairs]
        node.args.kw_defaults = [d for _, d in pairs]
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in self.constants:
                return None
            if (isinstance(target, ast.Attribute) and target.attr == 'enable_raw_kv' and
                    isinstance(target.value, ast.Name) and target.value.id == 'self'):
                return None
        return self.generic_visit(node)

    def visit_Expr(self, node):
        call = node.value
        if isinstance(call, ast.Call):
            if isinstance(call.func, ast.Name) and call.func.id in (
                    '_raw_kv_mode', '_snapshot_raw_kv_mode', '_verify_raw_kv_composition'):
                return None
            if isinstance(call.func, ast.Attribute) and call.func.attr == 'add_argument' and call.args and \
                    isinstance(call.args[0], ast.Constant) and call.args[0].value == '--enable-raw-kv':
                return None
            if isinstance(call.func, ast.Name) and call.func.id == 'require' and call.args and \
                    ast.dump(call.args[0], include_attributes=False) == ast.dump(
                    ast.parse('type(enable_raw_kv) is bool', mode='eval').body, include_attributes=False):
                return None
        return self.generic_visit(node)

    def visit_If(self, node):
        if isinstance(node.test, ast.Name) and node.test.id == 'enable_raw_kv':
            result = []
            for child in node.orelse:
                value = self.visit(child)
                if value is not None:
                    result.extend(value if isinstance(value, list) else [value])
            return result
        return self.generic_visit(node)

    def visit_IfExp(self, node):
        if ((isinstance(node.test, ast.Name) and node.test.id == 'enable_raw_kv') or
                ast.dump(node.test, include_attributes=False) == ast.dump(
                    ast.parse('self.enable_raw_kv', mode='eval').body, include_attributes=False)):
            return self.visit(node.orelse)
        return self.generic_visit(node)

    def visit_Call(self, node):
        node.keywords = [item for item in node.keywords if item.arg != 'enable_raw_kv']
        return self.generic_visit(node)

    def visit_Constant(self, node):
        substitutions = {
            'super().__init__(owner, source_sha256=source_sha256, enable_raw_kv=enable_raw_kv)':
                'super().__init__(owner, source_sha256=source_sha256)',
            'self.profiled_loaded_functions_checked = verify_profiled_dependencies(owner, self.sources, enable_raw_kv=self.enable_raw_kv)':
                'self.profiled_loaded_functions_checked = verify_profiled_dependencies(owner, self.sources)',
        }
        if isinstance(node.value, str) and node.value in substitutions:
            node.value = substitutions[node.value]
        return node


def check_scope(originals, generated, *, enable_raw_kv=False):
    """Check the unchanged disabled projection; prepare also pins enabled bytes."""
    need(type(enable_raw_kv) is bool, 'canonical composition mode required')
    expected = set(TARGETS if enable_raw_kv else (ENTRY,))
    need(set(generated) == expected, 'exact composition target scope required')
    if enable_raw_kv:
        upstream.check_scope(originals, generated)
    for name in (ENTRY, *GUARDS) if enable_raw_kv else (ENTRY,):
        before = ast.parse(originals[name])
        after = _DisabledProjection().visit(ast.parse(generated[name]))
        need(ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False),
             'change exceeds reviewed disabled source projection: ' + name)


def _original_inventory():
    """Hash all 75 active V4 sources without importing their execution modules."""
    helper = (ROOT / GUARDS[0]).read_text()
    receipt = (ROOT / INVENTORY).read_bytes()
    need(_literal(helper, 'SOURCE_VERSION') == 'qwen2-existing-attention-observation-v4',
         'active V4 source version required')
    need(_literal(helper, 'RECEIPT') == INVENTORY and
         sha(receipt) == _literal(helper, 'RECEIPT_SHA'), 'original inventory receipt drift')
    sources = json.loads(receipt)['source_sha256']
    need(len(sources) == 75, 'original inventory must contain exactly 75 sources')
    # The OWNER key is a source-level name, not executable candidate code.
    tree = ast.parse(helper)
    owner = _literal(helper, 'OWNER')
    replacement = next(n.value for n in tree.body if isinstance(n, ast.Assign) and
                       any(isinstance(t, ast.Name) and t.id == 'EXECUTION_SOURCE_REPLACEMENTS' for t in n.targets))
    replacements = {owner if isinstance(k, ast.Name) and k.id == 'OWNER' else ast.literal_eval(k):
                    ast.literal_eval(v) for k, v in zip(replacement.keys, replacement.values)}
    need(len(replacements) == 6 and set(replacements) <= set(sources), 'original V4 six-replacement closure')
    for name, (previous, current) in replacements.items():
        need(sources[name] == previous and previous != current, 'original V4 replacement origin drift')
        sources[name] = current
    for name, expected in sources.items():
        need(sha((ROOT / name).read_bytes()) == expected, 'active V4 source drift: ' + name)
    return sources


def _apply(out, patch_name, targets, pins):
    raw = (HERE / patch_name).read_bytes()
    need(sha(raw) == pins['patch_sha256'][patch_name], 'entry/guard patch drift: ' + patch_name)
    headers = tuple(line[6:] for line in raw.decode().splitlines() if line.startswith('--- a/'))
    need(headers == tuple(targets), 'exact entry/guard patch targets required')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], input=raw, cwd=out,
                   check=True, capture_output=True, timeout=10)


def prepare(out, *, enable_raw_kv=False):
    need(type(enable_raw_kv) is bool, 'canonical composition mode required')
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'fresh source directory required')
    pins = json.loads((HERE / 'pins.json').read_text())
    need(pins['schema'] == 1 and pins['lineage']['base_commit'] == BASE_COMMIT and
         pins['lineage']['historical_source_commit'] == HISTORICAL_COMMIT and
         pins['lineage']['historical_receipt_applies_to_this_extension'] is False and
         pins['lineage']['prepared_pv32_selected'] is False, 'entry composition lineage drift')
    # Upstream validates ORIGINAL bytes before either composition. Runtime never
    # invokes that original-pin checker against an already composed tree.
    with tempfile.TemporaryDirectory(prefix='raw-kv-entry-upstream-') as directory:
        public_out = Path(directory) / 'sources'
        public = upstream.prepare(public_out)
        expected_inputs = set(public['inputs']) | set(GUARDS) | {INVENTORY, BRIDGE}
        need(set(pins['inputs']) == expected_inputs, 'exact original entry input closure required')
        for name, expected in pins['inputs'].items():
            need(blob((ROOT / name).read_bytes()) == expected, 'entry original source drift: ' + name)
        inventory = _original_inventory()
        names = expected_inputs | {str((HERE / name).relative_to(ROOT)) for name in OWN_INPUTS}
        need(pins['raw_kv_sources'] == sorted(names), 'exact enabled runtime freeze closure required')
        inputs = {name: sha((ROOT / name).read_bytes()) for name in sorted(names | set(inventory))}
        originals = {name: (ROOT / name).read_text() for name in TARGETS}
        out.mkdir(parents=True)
        selected = TARGETS if enable_raw_kv else (ENTRY,)
        for name in selected:
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((public_out / name).read_text() if name in upstream.TARGETS else originals[name])
        _apply(out, 'entry.patch', (ENTRY,), pins)
        if enable_raw_kv:
            _apply(out, 'guard.patch', GUARDS, pins)
    generated = {name: (out / name).read_text() for name in selected}
    need(_literal(generated[ENTRY], 'RAW_KV_SOURCES') == tuple(sorted(names)),
         'entry runtime freeze literal differs from pinned closure')
    composition = _literal(generated[ENTRY], 'RAW_KV_COMPOSITION_SHA256')
    need(set(composition) == {'disabled', 'enabled'} and
         composition['disabled'] == {name: sha(originals[name].encode())
                                    for name in (*upstream.TARGETS, *GUARDS)} and
         composition['enabled'] == {name: digest for name, digest in
             pins['generated_sha256']['enabled'].items() if name != ENTRY},
         'entry composition preflight identities differ from pinned variants')
    replacements = {name: [sha(originals[name].encode()),
                          pins['generated_sha256']['enabled'][name]] for name in upstream.TARGETS}
    need(pins['execution_source_replacements'] == replacements,
         'exact two raw KV execution replacements required')
    if enable_raw_kv:
        need(_literal(generated[GUARDS[0]], 'RAW_KV_EXECUTION_SOURCE_REPLACEMENTS') == replacements,
             'helper replacement identities differ from pinned hooks')
    check_scope(originals, generated, enable_raw_kv=enable_raw_kv)
    hashes = {name: sha(raw.encode()) for name, raw in generated.items()}
    need(hashes == pins['generated_sha256']['enabled' if enable_raw_kv else 'disabled'],
         'composed entry/source-contract identity drift')
    need({str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()} == set(selected),
         'unexpected composed file')
    need(all(sha((ROOT / name).read_bytes()) == expected for name, expected in inputs.items()),
         'source changed during entry preparation')
    return dict(status='PASS_PREPARATION_ONLY', enable_raw_kv=enable_raw_kv,
                inputs=inputs, generated=hashes, lineage=pins['lineage'],
                active_v4_sources=75, original_v4_replacements=6,
                raw_kv_replacements=2 if enable_raw_kv else 0,
                arithmetic_executed=False, public_fullgraph_executed=False,
                hardware_simulation=False, old_pass_inherited=False)


def check(*, enable_raw_kv=False):
    with tempfile.TemporaryDirectory(prefix='raw-kv-entry-source-') as directory:
        return prepare(Path(directory) / 'sources', enable_raw_kv=enable_raw_kv)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-raw-kv', action='store_true')
    args = parser.parse_args()
    result = check(enable_raw_kv=args.enable_raw_kv)
    print('PASS: pinned entry/source-contract preparation only; numerical/RTL execution NOT RUN')
