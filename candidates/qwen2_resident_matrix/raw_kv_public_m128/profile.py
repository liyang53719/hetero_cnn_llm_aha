"""Exact, source-only M128 preparation contract over the successful M16 tree.

This first slice composes nine reviewed files but has no M128 setup variant.
It cannot return a runtime asset-source map or admit numerical execution.
Published M16 files and their contracts are never updated in place.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat

from . import prerequisite

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREFIX = 'candidates/qwen2_resident_matrix/raw_kv_public_m128/'
PINS = PREFIX + 'pins.json'
PROFILE = prerequisite.PROFILE
STATUS = 'PREPARATION_ONLY'
OWN = ('prerequisite.py', 'profile.py', 'test_profile.py', 'assets128.patch',
       'entry128.patch', 'README.md', 'test_assets128.py')
PATCHES = {'assets128.patch': prerequisite.ASSETS, 'entry128.patch': prerequisite.ENTRY}
MAX_JSON_BYTES = 131072
MAX_SOURCE_BYTES = 4194304
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
PREREQUISITE_SHA256 = hashlib.sha256(Path(prerequisite.__file__).read_bytes()).hexdigest()


def need(ok, reason='M128 source contract'):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def relative_name(value):
    need(type(value) is str and value and '\\' not in value and '\x00' not in value)
    path = PurePosixPath(value)
    need(not path.is_absolute() and all(part not in ('', '.', '..') for part in value.split('/')))
    return value


def read_source(name, limit=MAX_SOURCE_BYTES):
    """Read only bounded regular repository files, rejecting symlink components."""
    path = ROOT / relative_name(name)
    for item in (path, *path.parents):
        need(not item.is_symlink(), 'M128 source symlink')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit, 'M128 source size/type')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    after = path.stat()
    identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    need(len(raw) == info.st_size and identity(info) == identity(after), 'M128 source read drift')
    return raw


def json_bytes(raw):
    need(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES)
    def pairs(items):
        result = {}
        for name, value in items:
            need(name not in result, 'M128 duplicate JSON key')
            result[name] = value
        return result
    def forbidden(_):
        raise ValueError('M128 contract requires integer-only finite metadata')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=forbidden, parse_constant=forbidden)


def validate_contract(value):
    """Validate frozen identities, not a caller-selected replacement allowlist."""
    fixed = dict(schema=1, profile=PROFILE, status=STATUS, rows=128, past_tokens=0,
                 enable_raw_kv=True, m16_evidence_sha256=prerequisite.EVIDENCE_SHA256)
    need(type(value) is dict and set(value) == set(fixed) | {
        'source_sha256', 'patch_sha256', 'generated_sha256'})
    for name, expected in fixed.items():
        need(type(value[name]) is type(expected) and value[name] == expected)
    old = prerequisite.evidence()['source_hashes']
    sources = value['source_sha256']; generated = value['generated_sha256']
    names = set(old['source_sha256']) | {prerequisite.EVIDENCE} | {PREFIX + name for name in OWN}
    need(type(sources) is dict and set(sources) == names)
    need(all(relative_name(name) and digest(identity) for name, identity in sources.items()))
    need(all(sources[name] == identity for name, identity in old['source_sha256'].items()))
    need(sources[prerequisite.EVIDENCE] == prerequisite.EVIDENCE_SHA256)
    need(sources[PREFIX + 'profile.py'] == IMPORTED_SHA256)
    need(sources[PREFIX + 'prerequisite.py'] == PREREQUISITE_SHA256)
    need(type(generated) is dict and set(generated) == set(old['generated_sha256']) | {prerequisite.ASSETS})
    need(len(generated) == 9 and all(digest(value) for value in generated.values()))
    need(all(generated[name] == identity for name, identity in old['generated_sha256'].items()
             if name != prerequisite.ENTRY))
    need(generated[prerequisite.ENTRY] != old['generated_sha256'][prerequisite.ENTRY])
    need(generated[prerequisite.ASSETS] != old['source_sha256'][prerequisite.ASSETS])
    patches = value['patch_sha256']
    need(type(patches) is dict and set(patches) == set(PATCHES))
    need(all(patches[name] == sources[PREFIX + name] for name in PATCHES))
    return value


def contract_snapshot(*, composed=False):
    need(type(composed) is bool)
    # Parse exactly the bytes whose hash is returned. Missing pins fail closed.
    raw = read_source(PINS, MAX_JSON_BYTES)
    value = validate_contract(json_bytes(raw))
    expected = dict(value['source_sha256'])
    if composed:
        expected.update(value['generated_sha256'])
    for name, identity in expected.items():
        need(sha(read_source(name)) == identity, 'M128 frozen source drift')
    expected[PINS] = sha(raw)
    return dict(status=STATUS, profile=PROFILE, inputs=expected,
                generated=dict(value['generated_sha256']), pins_sha256=sha(raw),
                m16_evidence_sha256=prerequisite.EVIDENCE_SHA256,
                m128_executed=False, full_29_node_acceptance=False,
                runtime_ready=False, blocker='setup_variant_missing')


def asset_source_snapshot(*, enable_raw_kv=False):
    """Reserved runtime API. This preparation slice never grants admission."""
    need(type(enable_raw_kv) is bool and enable_raw_kv is True, 'M128 requires explicit raw KV')
    contract_snapshot(composed=True)
    raise ValueError('M128 runtime source contract unavailable: setup_variant_missing')


def authorize_run(snapshot, *, wall_budget, enable_raw_kv, fresh_profile):
    """Validate the requested domain, then refuse this incomplete runtime slice."""
    need(type(enable_raw_kv) is bool and enable_raw_kv is True and
         type(fresh_profile) is bool and fresh_profile is True, 'M128 explicit profiles required')
    need(type(wall_budget) in (int, float) and 0 < wall_budget <= 2400 and
         math.isfinite(wall_budget), 'M128 finite bounded run required')
    need(type(snapshot) is dict and type(snapshot.get('rows')) is int and snapshot['rows'] == 128,
         'M128 snapshot rows')
    need(snapshot.get('enable_raw_kv') is True and snapshot.get('fresh_profile') is True,
         'M128 snapshot profiles')
    identity = snapshot.get('fresh_assets')
    need(type(identity) is dict and set(identity) == {'profile', 'manifest', 'manifest_sha256', 'enable_raw_kv'})
    need(type(identity['profile']) is str and identity['profile'] == 'qwen2-public-pv16-fresh-assets-m128-v1' and
         identity['enable_raw_kv'] is True and type(identity['manifest']) is str and
         bool(identity['manifest']) and digest(identity['manifest_sha256']), 'M128 asset identity')
    reference = snapshot.get('independent_reference')
    need(type(reference) is dict and type(reference.get('rows')) is int and reference['rows'] == 128 and
         type(reference.get('past_tokens')) is int and reference['past_tokens'] == 0, 'M128 past-token domain')
    sources = snapshot.get('source_sha256')
    need(type(sources) is dict and all(relative_name(name) and digest(value) for name, value in sources.items()))
    need(sources.get(prerequisite.EVIDENCE) == prerequisite.EVIDENCE_SHA256 and
         snapshot.get('source_manifest_sha256') == sha(prerequisite.encoded(sources)), 'M128 linked M16 sources')
    # There is deliberately no successful authorization branch in this version.
    asset_source_snapshot(enable_raw_kv=True)
    raise ValueError('M128 runtime source contract unavailable: setup_variant_missing')


def check_entry_scope(original, generated):
    """Prove the unchanged M16 branch; reviewed enabled text is hash-pinned too."""
    import ast
    class HistoricalProjection(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.level == 2 and node.module == 'raw_kv_public_m128' and len(node.names) == 1 and \
               node.names[0].name == 'profile' and node.names[0].asname == 'm128_profile':
                return None
            return node

        def visit_Assign(self, node):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and \
               node.targets[0].id == 'm128_selected':
                return None
            return self.generic_visit(node)

        def visit_If(self, node):
            if isinstance(node.test, ast.Name) and node.test.id == 'm128_selected':
                return node.orelse
            return self.generic_visit(node)
    before = ast.parse(original)
    after = HistoricalProjection().visit(ast.parse(generated))
    need(ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False),
         'M128 patch changes the historical entry projection')


def prepare(out, *, enable_raw_kv=True):
    """Compose source text only into a new directory; no imports of that text."""
    need(type(enable_raw_kv) is bool and enable_raw_kv is True, 'M128 requires explicit raw KV')
    out = Path(out)
    need(not out.exists() and not out.is_symlink(), 'fresh M128 composition directory required')
    snapshot = contract_snapshot()
    # Imports here are the already pinned, source-only M16 preparer and patcher.
    import ast
    import subprocess
    from candidates.qwen2_resident_matrix.raw_kv_public_fresh import prepare as old
    baseline = old.prepare(out, enable_raw_kv=True)
    historical = prerequisite.evidence()['source_hashes']['generated_sha256']
    need(baseline['generated'] == historical, 'M16 preparation overlay drift')
    original_entry = (out / prerequisite.ENTRY).read_bytes()
    assets = out / prerequisite.ASSETS
    assets.parent.mkdir(parents=True, exist_ok=True)
    assets.write_bytes(read_source(prerequisite.ASSETS))
    for filename, target in PATCHES.items():
        raw = read_source(PREFIX + filename)
        need(sha(raw) == snapshot['inputs'][PREFIX + filename])
        text = raw.decode('utf-8')
        need([line[6:] for line in text.splitlines() if line.startswith('--- a/')] == [target])
        need([line[6:] for line in text.splitlines() if line.startswith('+++ b/')] == [target])
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=out, input=raw,
                       check=True, capture_output=True, timeout=10)
    generated = {}
    for path in out.rglob('*'):
        need(not path.is_symlink(), 'M128 generated symlink')
        if path.is_file():
            raw = path.read_bytes()
            ast.parse(raw, filename=str(path.relative_to(out)))
            generated[str(path.relative_to(out))] = sha(raw)
    need(generated == snapshot['generated'], 'M128 generated source identity drift')
    check_entry_scope(original_entry, (out / prerequisite.ENTRY).read_bytes())
    need(contract_snapshot() == snapshot, 'M128 preparation source postflight drift')
    return snapshot
