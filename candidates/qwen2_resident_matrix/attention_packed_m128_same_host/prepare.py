"""Reversible source-only genuine M128 composition over current same-host M16.

The source assembler must install the old-source support lock into the original
checkout. No historical asset, library, receipt, PASS or launch is imported.
"""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
from . import contract as C

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'candidates/qwen2_resident_matrix/'
TARGETS = tuple(BASE+n for n in ('dense_block_reduce/check_public_numeric.py',
    'official_bf16/check_numeric.py','ffn_public/check_fullgraph_numeric.py','raw_kv_public/model.py'))
OBSERVER = BASE+'attention_packed_tiled_observation/pins.json'
OLD_REFERENCE = 'explicitly reused same-input M128 sequential/block-pair and native outputs; original gates retained'
FRESH_REFERENCE = 'fresh same-host M128 sequential/block-pair and newly executed official M128 outputs; original gates retained'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reverse_fresh_m16(text):
    from ..attention_packed_m16_same_host import prepare as m16
    return text.replace('attention_packed_m16_same_host import','attention_packed_m16_entry import').replace(
        m16.FRESH_REFERENCE,m16.OLD_REFERENCE).replace(
        'new_official_forward_executed=True, native_execution_reused=False,',
        'new_official_forward_executed=False, native_execution_reused=True,')


def rewrite(text, target):
    C.need(target in (*TARGETS,BASE+'attention_packed_m128_entry/profile.py'), 'exact M128 rewrite target')
    updated = text.replace('attention_packed_m128_assets import','attention_packed_m128_same_host import')
    updated = updated.replace('attention_packed_m128_entry import','attention_packed_m128_same_host import')
    updated = updated.replace('attention_packed_m128_entry.profile import','attention_packed_m128_same_host.profile import')
    if target in TARGETS[:2]:
        C.need(updated.count(OLD_REFERENCE) == 1, 'exact old M128 producer statement')
        updated = updated.replace(OLD_REFERENCE,FRESH_REFERENCE)
    if target == TARGETS[1]:
        old = 'new_official_forward_executed=False, native_execution_reused=True,'
        C.need(updated.count(old) == 1, 'exact old M128 native forward flags')
        updated = updated.replace(old,'new_official_forward_executed=True, native_execution_reused=False,')
    # Reverse every edited token, using the original import spellings per line.
    reverse = updated.replace(FRESH_REFERENCE,OLD_REFERENCE)
    if target == TARGETS[1]:
        reverse = reverse.replace('new_official_forward_executed=True, native_execution_reused=False,',
                                  'new_official_forward_executed=False, native_execution_reused=True,')
    original_lines,changed_lines = text.splitlines(),reverse.splitlines()
    C.need(len(original_lines) == len(changed_lines), 'no numerical statement added or removed')
    for index,(before,after) in enumerate(zip(original_lines,changed_lines)):
        if before != after:
            C.need('attention_packed_m128_same_host' in after and
                after.replace('attention_packed_m128_same_host','attention_packed_m128_assets') == before or
                'attention_packed_m128_same_host' in after and
                after.replace('attention_packed_m128_same_host','attention_packed_m128_entry') == before,
                'only explicit M128 source identity edits')
            changed_lines[index] = before
    C.need(ast.dump(ast.parse('\n'.join(changed_lines)),include_attributes=False) ==
           ast.dump(ast.parse(text),include_attributes=False), 'M128 numerical/control drift')
    return updated


def check_terminal_scope():
    from . import terminal_transform
    baseline = (HERE/'terminal_original.py').read_text()
    C.need(sha(HERE/'terminal_original.py') == terminal_transform.BASELINE_SHA256,
           'original full M128 terminal bytes changed')
    C.need((HERE/'terminal_validator.py').read_text() == terminal_transform.transform(baseline),
           'M128 terminal edits exceed explicit identity/provenance scope')
    return True


def compose(destination, *, git_head, producer_package, producer_m128_package, support_roots=()):
    from ..attention_packed_m16_same_host import prepare as prior
    from ..attention_packed_m128 import prepare as tiled
    from ..attention_packed_m128_entry import composition
    from ..attention_packed_tiled_observation import prepare as observer
    from ..attention_packed_m128_run_gate import prepare as repaired
    from .prerequisite import compatible_sources
    C.need(C.commit(git_head), 'actual triggering commit required')
    check_terminal_scope()
    destination = Path(destination).absolute()
    before = prior.compose(destination,git_head=git_head,producer_package=producer_package,
                           support_roots=support_roots)
    original_m16_sources = before['source_sha256']
    # Drop only the old dynamic entry contract; the current M16 evidence has its
    # own separate worktree and is never altered by this new M128 source overlay.
    (destination/prior.C.PREFIX/prior.C.SOURCE_FILE).unlink()
    support = C.read_json(HERE/'m128-support-lock.json')
    C.need(set(support) == {'schema','sources'} and support['schema'] == 1, 'exact old M128 source support lock')
    roots = (ROOT,*(C.safe(Path(p).absolute(),directory=True) for p in support_roots))
    for name,expected in support['sources'].items():
        matches = [C.safe(root/name) for root in roots if (root/name).is_file()]
        C.need(matches and any(sha(path) == expected for path in matches), 'missing exact M128 support: '+name)
        source = next(path for path in matches if sha(path) == expected)
        target = destination/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(source.read_bytes())
    # Original old M128 selector and residual-gate repair are applied verbatim.
    for name in TARGETS[:3]:
        path = destination/name
        path.write_text(composition.entry(reverse_fresh_m16(path.read_text()),name))
    path = destination/TARGETS[0]; path.write_text(repaired.repair(path.read_text()))
    path = destination/TARGETS[3]; path.write_text(composition.transport(path.read_text()))
    with tempfile.TemporaryDirectory() as temp:
        schedule = tiled.compose(Path(temp)/'tiled')
        (destination/tiled.TARGET).write_bytes((schedule/tiled.TARGET).read_bytes())
    for name in TARGETS:
        path = destination/name; path.write_text(rewrite(path.read_text(),name))
    # Successor profile retains every original owner/Host PrefixJob guard.
    for path in sorted(HERE.iterdir()):
        if not path.is_file() or path.name == C.SOURCE_FILE or path.suffix not in ('.py','.json','.md'):
            continue
        target = destination/C.PREFIX/path.name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(C.safe(path).read_bytes())
    producer = C.safe(producer_m128_package,directory=True)
    C.need(producer.name == 'portable_official_producer_m128', 'exact new producer source package')
    for path in sorted(producer.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts: continue
        C.need(path.suffix in ('.py','.json','.md','.patch'), 'source-only producer package')
        target = destination/BASE/'portable_official_producer_m128'/path.relative_to(producer)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(C.safe(path).read_bytes())
    op = json.loads((destination/OBSERVER).read_bytes())
    op['runtime'] = {name:sha(destination/name) for name in op['runtime']}
    (destination/OBSERVER).write_text(json.dumps(op,sort_keys=True,indent=2)+'\n')
    sources = {str(path.relative_to(destination)):sha(path) for path in sorted(destination.rglob('*')) if path.is_file()}
    compatible_sources(sources,original_m16_sources)
    value = dict(schema=1,profile=C.PROFILE,git_head=git_head,sources=sources,scope='FRESH_M128_ASSIGNED27_ONLY')
    path = destination/C.PREFIX/C.SOURCE_FILE;path.write_bytes(C.encoded(value))
    sources[str(path.relative_to(destination))] = sha(path)
    return dict(profile=C.PROFILE,git_head=git_head,source_sha256=sources,
        source_manifest_sha256=C.sha(C.encoded(sources)),source_contract_sha256=sha(path),
        actual_chain_executed=False,full_public_admission=False)
