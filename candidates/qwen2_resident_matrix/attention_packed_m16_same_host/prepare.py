"""Source-only fresh-host composition. No package, weights, ELF or numeric run."""
import ast
import hashlib
import json
from pathlib import Path
from ..attention_packed_m16_host_job import prepare as prior
from . import contract as C

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TARGETS = (
    'candidates/qwen2_resident_matrix/dense_block_reduce/check_public_numeric.py',
    'candidates/qwen2_resident_matrix/official_bf16/check_numeric.py',
    'candidates/qwen2_resident_matrix/ffn_public/check_fullgraph_numeric.py',
    'candidates/qwen2_resident_matrix/attention_packed_m16/profile.py',
)
OBSERVER = 'candidates/qwen2_resident_matrix/attention_packed_observation/pins.json'
OLD_REFERENCE = 'fresh same-input sequential/block-pair outputs; explicitly reused verified native M16 outputs; original gates retained'
FRESH_REFERENCE = 'fresh same-host sequential/block-pair and newly executed official M16 outputs; original gates retained'
OWN = ('contract.py','admission.py','views.py','prepare.py','entry.py','terminal_validator.py','terminal_original.py',
       'test_entry.py','test_terminal_validator.py','README.md','RESOURCE_PLAN.json','SCOPE_AUDIT.json')


def check_terminal_scope():
    baseline = (HERE/'terminal_original.py').read_text()
    C.need(sha(HERE/'terminal_original.py') == '2fdabe1135b877fa6b78a1cd8f4b51dd14da316773ec79413ff5edd743683347',
           'immutable wholephase validator baseline changed')
    expected = baseline.replace('qwen2-public-pv16-packed-m16-linked-v1', C.PROFILE)
    expected = expected.replace("c['new_official_forward_executed'] is False and c['native_execution_reused'] is True",
                                "c['new_official_forward_executed'] is True and c['native_execution_reused'] is False")
    expected = expected.replace(OLD_REFERENCE, FRESH_REFERENCE)
    expected = expected.replace('VALIDATED_ORIGINAL_M16_OBSERVED_GATES_ONLY',
                                'VALIDATED_FRESH_SAME_HOST_M16_OBSERVED_GATES_ONLY')
    C.need((HERE/'terminal_validator.py').read_text() == expected, 'wholephase validator numerical/control drift')
    return True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rewrite(text, target):
    C.need(target in TARGETS and 'attention_packed_m16_entry import' in text, 'exact installed old entry selection')
    updated = text.replace('attention_packed_m16_entry import', 'attention_packed_m16_same_host import')
    if target in TARGETS[:2]:
        C.need(text.count(OLD_REFERENCE) == 1, 'exact old producer metadata')
        updated = updated.replace(OLD_REFERENCE, FRESH_REFERENCE)
    if target == TARGETS[1]:
        old = 'new_official_forward_executed=False, native_execution_reused=True,'
        C.need(updated.count(old) == 1, 'exact old native-reuse flags')
        updated = updated.replace(old, 'new_official_forward_executed=True, native_execution_reused=False,')
    # No gate, tolerance, geometry, execution statement, release/ACK check,
    # source type guard, failure preservation, or whole-reference fence changes.
    reversed_text = updated.replace('attention_packed_m16_same_host import', 'attention_packed_m16_entry import')
    reversed_text = reversed_text.replace(FRESH_REFERENCE, OLD_REFERENCE)
    if target == TARGETS[1]:
        reversed_text = reversed_text.replace('new_official_forward_executed=True, native_execution_reused=False,',
                                              'new_official_forward_executed=False, native_execution_reused=True,')
    C.need(ast.dump(ast.parse(reversed_text), include_attributes=False) ==
           ast.dump(ast.parse(text), include_attributes=False), 'numerical/control source changed')
    return updated


def compose(destination, *, git_head, producer_package, support_roots=()):
    """Return an exact source overlay for a caller-owned genuine Git worktree.

    producer_package is the reviewed portable_official_producer directory. The
    caller pins the returned map and source contract in its launch receipt.
    This routine neither creates a Git worktree nor grants numerical admission.
    """
    C.need(C.commit(git_head), 'exact reviewed triggering commit required')
    check_terminal_scope()
    C.need(type(support_roots) in (tuple,list), 'explicit source-only support roots')
    support_roots = (ROOT, *(C.safe(Path(p).absolute(), directory=True) for p in support_roots))
    destination = Path(destination).absolute()
    C.need(not destination.exists() and not destination.is_symlink(), 'fresh source composition required')
    prior.compose(destination)
    before = {name:(destination/name).read_text() for name in TARGETS}
    for name in TARGETS:
        (destination/name).write_text(rewrite(before[name], name))
    for name in OWN:
        raw = C.safe(HERE/name).read_bytes()
        path = destination/C.PREFIX/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    producer = C.safe(producer_package, directory=True)
    C.need(producer.name == 'portable_official_producer', 'exact producer package selection')
    files = [p for p in sorted(producer.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    C.need(files and any(p.name == 'driver.py' for p in files), 'producer driver missing')
    for path in files:
        C.safe(path)
        C.need(path.suffix in ('.py','.json','.md','.patch'), 'producer source-only inventory')
        target = destination/'candidates/qwen2_resident_matrix/portable_official_producer'/path.relative_to(producer)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    lock = C.read_json(producer/'source-lock.json')
    C.need(set(lock) == {'schema','sources'} and type(lock['schema']) is int and lock['schema'] == 1 and
           type(lock['sources']) is dict, 'producer support source lock required')
    for name, expected in lock['sources'].items():
        C.need(type(name) is str and not Path(name).is_absolute() and '\\' not in name and
               all(p not in ('','.','..') for p in name.split('/')) and C.digest(expected), 'producer support pin')
        target = destination/name
        if not target.exists():
            matches = [C.safe(base/name) for base in support_roots if (base/name).is_file()]
            C.need(matches and all(sha(p) == expected for p in matches), 'producer support source absent or changed: '+name)
            source = matches[0]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        C.need(sha(target) == expected, 'producer source conflicts with full-M16 composition: '+name)
    observer = json.loads((destination/OBSERVER).read_bytes())
    observer['runtime'] = {name:sha(destination/name) for name in observer['runtime']}
    (destination/OBSERVER).write_text(json.dumps(observer, sort_keys=True, indent=2)+'\n')
    sources = {str(p.relative_to(destination)):sha(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    C.need(C.PREFIX+C.SOURCE_FILE not in sources, 'source contract must remain acyclic')
    value = dict(schema=1, profile=C.PROFILE, git_head=git_head, sources=sources, scope='FRESH_M16_ASSIGNED27_ONLY')
    path = destination/C.PREFIX/C.SOURCE_FILE
    path.write_bytes(C.encoded(value))
    sources[str(path.relative_to(destination))] = sha(path)
    return dict(profile=C.PROFILE, git_head=git_head, source_sha256=sources,
                source_manifest_sha256=C.sha(C.encoded(sources)), source_contract_sha256=sha(path),
                actual_chain_executed=False, full_public_admission=False)
