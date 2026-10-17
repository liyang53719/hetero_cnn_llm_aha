"""Parent-bound current-job full-M16 prerequisite. Receipts never create authority.

The live owning parent supplies expected identity and observations. This module
independently replays original M16 terminal validation and hashes its entire
current source tree. Historical M16 PASS, native16 or ELF cannot substitute.
"""
import os
from pathlib import Path
from . import contract as C

PROFILE = 'qwen2-fresh-same-host-m16-prerequisite-v1'
STATUS = 'VERIFIED_CURRENT_JOB_FULL_M16_SAME_ELF'
M16_PROFILE = 'qwen2-public-pv16-packed-m16-same-host-v1'
M16_VALIDATOR_SHA256 = 'caf027af5688acbe8c29efb38ddba09a88a3223d0749572f6a002c42806aae20'
FILES = {
    'producer_manifest': 'setup/producer/PRODUCER_M16.json',
    'producer_qualification': 'setup/QUALIFICATION.json',
    'actual': 'full_m16/actual/summary.json',
    'snapshot': 'full_m16/snapshot/SNAPSHOT.json',
    'child_result': 'full_m16/CHILD_RESULT.json',
    'full_receipt': 'evidence/full_m16_summary.json',
}

def exact(value, keys, label):
    C.need(type(value) is dict and set(value) == set(keys), label)


def pointer(path):
    path = C.safe(path)
    return dict(path=str(path), sha256=C.sha(path.read_bytes()))


def compatible_sources(current, previous):
    expected = C.read_json(C.HERE/'compatible-sources.json')
    C.need(len(expected) == 24 and C.sha(C.encoded(expected)) ==
           'cd98d6d6ac11b20152946ce9397c774a46db739442d477ceee73b820ddcf66f9',
           'original 24-source compatibility contract')
    for name, digest in expected.items():
        C.need(previous.get(name) == current.get(name) == digest,
               'same M16/M128 arithmetic, owner, service, storage source: '+name)
    return expected


def _load(m16_root):
    root = C.safe(m16_root, directory=True)
    C.need(root.name == 'm16' and not root.is_relative_to(C.ROOT) and not C.ROOT.is_relative_to(root),
           'exact disjoint current-job M16 subchain')
    records = {name:pointer(root/suffix) for name,suffix in FILES.items()}
    values = {name:C.read_json(item['path'],item['sha256'],limit=4*1024*1024)
              for name,item in records.items()}
    frozen_raw = C.safe(C.HERE/'m16-composed-sources.json').read_bytes()
    C.need(C.sha(frozen_raw) == 'f99de4cb9b330e557b066e675342ef93e63143174ba54a520579f78e657334ff', 'frozen complete M16 source closure')
    frozen = C.read_json(C.HERE/'m16-composed-sources.json')
    name = 'candidates/qwen2_resident_matrix/attention_packed_m16_same_host/SOURCE_CONTRACT.json'
    source_contract = C.safe(root/'source'/name).read_bytes()
    expected = dict(schema=1,profile=M16_PROFILE,git_head=values['producer_qualification']['ci']['commit'],
        sources=frozen,scope='FRESH_M16_ASSIGNED27_ONLY')
    C.need(source_contract == C.encoded(expected), 'actual-commit complete M16 source contract')
    sources = dict(frozen, **{name:C.sha(source_contract)})
    C.need(values['actual']['source_sha256'] == sources, 'complete frozen M16 composition map')
    C.need(type(sources) is dict and sources, 'full M16 source map')
    for name,digest in sources.items():
        C.need(type(name) is str and name and '\\' not in name and not Path(name).is_absolute() and
               all(p not in ('','.','..') for p in name.split('/')) and C.digest(digest), 'M16 source path')
        C.need(C.sha(C.safe(root/'source'/name).read_bytes()) == digest, 'current M16 source changed')
    validator_path = C.HERE/'terminal_m16.py'
    C.need(C.sha(C.safe(validator_path).read_bytes()) == M16_VALIDATOR_SHA256 and
           sources.get('candidates/qwen2_resident_matrix/attention_packed_m16_same_host/terminal_validator.py') ==
           M16_VALIDATOR_SHA256, 'exact original full M16 terminal verifier')
    from . import terminal_m16
    validation = terminal_m16.validate_terminal(records['actual']['path'],records['actual']['sha256'],sources,
        records['snapshot']['path'],records['snapshot']['sha256'])
    q,p,f,ch = (values[k] for k in ('producer_qualification','producer_manifest','full_receipt','child_result'))
    exact(q, ('schema','profile','status','attempt_nonce','producer_manifest_sha256',
        'producer_source_manifest_sha256','host_sha256','runtime_identity_sha256','ci','child_pid',
        'child_exit_code','owned_group_cleanup_complete','producer_native_gate_validated','elapsed_seconds',
        'claims','fresh_tiny_result_sha256','fresh_tiny_source_manifest_sha256'), 'original M16 qualification fields')
    exact(f, ('schema','profile','status','ci','attempt_nonce','producer_receipt_sha256','child_result_sha256',
        'child_pid','child_exit_code','owned_group_cleanup_complete','elapsed_seconds','validation','claims'),
        'original parent full M16 fields')
    exact(q['claims'], ('actual_chain_executed','full_public_admission','full_29_node_acceptance',
        'rtl_execution','hardware_recipe_acceptance','old_pass_inherited'), 'original producer M16 scope')
    exact(f['claims'], ('full_29_node_acceptance','full_m128_acceptance','rtl_execution',
        'hardware_recipe_acceptance','old_pass_inherited'), 'original full M16 scope')
    C.need(all(value is False for value in q['claims'].values()), 'producer M16 nonacceptance')
    exact(q['ci'], ('commit','run_id','run_attempt'), 'first triggering CI identity')
    C.need(C.commit(q['ci']['commit']) and type(q['ci']['run_id']) is str and q['ci']['run_id'].isascii() and
           q['ci']['run_id'].isdigit() and int(q['ci']['run_id']) > 0 and q['ci']['run_attempt'] == '1',
           'current first CI attempt')
    C.need(type(q.get('schema')) is int and q['schema'] == 1 and
           q.get('profile') == 'qwen2-fresh-same-host-m16-producer-qualified-v1' and
           q.get('status') == 'PASS_FRESH_M16_PRODUCER' and
           q.get('producer_manifest_sha256') == records['producer_manifest']['sha256'] and
           q.get('attempt_nonce') == p.get('attempt_nonce') and C.digest(q.get('attempt_nonce')) and
           q.get('producer_source_manifest_sha256') == p.get('source_manifest_sha256') and
           q.get('ci') == p.get('ci') and q.get('host_sha256') == C.sha(C.encoded(p['host'])) and
           q.get('runtime_identity_sha256') == C.sha(C.encoded(p['runtime_identity'])) and
           type(q.get('child_exit_code')) is int and q['child_exit_code'] == 0 and
           q.get('owned_group_cleanup_complete') is True and q.get('producer_native_gate_validated') is True,
           'current M16 producer qualification chain')
    source_sha = C.sha(C.encoded(sources))
    expected_child = dict(schema=1,profile=M16_PROFILE,status='VALIDATED_FRESH_M16_CHILD_RESULT',
        attempt_nonce=q['attempt_nonce'],producer_receipt_sha256=records['producer_qualification']['sha256'],
        source_manifest_sha256=source_sha,summary_sha256=records['actual']['sha256'],
        snapshot_sha256=records['snapshot']['sha256'],validation=validation,
        parent_must_authenticate_exit_and_cleanup=True,full_29_node_acceptance=False,
        rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False)
    C.need(C.encoded(ch) == C.encoded(expected_child), 'M16 complete child/terminal chain')
    C.need(f.get('schema') == 1 and type(f['schema']) is int and
           f.get('profile') == 'qwen2-fresh-same-host-m16-combined-v1' and
           f.get('status') == 'PASS_FRESH_SAME_HOST_M16_ASSIGNED27' and f.get('ci') == q['ci'] and
           f.get('attempt_nonce') == q['attempt_nonce'] and
           f.get('producer_receipt_sha256') == records['producer_qualification']['sha256'] and
           f.get('child_result_sha256') == records['child_result']['sha256'] and
           type(f.get('child_pid')) is int and f['child_pid'] > 1 and
           type(f.get('child_exit_code')) is int and f['child_exit_code'] == 0 and
           f.get('owned_group_cleanup_complete') is True and C.encoded(f.get('validation')) == C.encoded(validation),
           'current parent-observed full M16 completion')
    C.need(type(f.get('claims')) is dict and all(v is False for v in f['claims'].values()), 'M16 scope')
    compiled = root/'setup/tiny/build/official_bf16_compile.json'
    binary = C.safe(root/'setup/tiny/build/official_bf16_matrix_silu.so')
    library = dict(receipt=pointer(compiled),binary=dict(path=str(binary),bytes=binary.stat().st_size,
        sha256=C.sha(binary.read_bytes())),origin_root=str(C.safe(root/'setup/tiny/source',directory=True)))
    built = C.read_json(compiled,library['receipt']['sha256'])
    bins = values['actual']['binaries']
    C.need(bins == dict(compile_receipt=str(compiled),compile_sha256=library['receipt']['sha256'],
        library=str(binary),library_sha256=library['binary']['sha256']) and
        built.get('library') == str(binary) and built.get('library_sha256') == library['binary']['sha256'],
        'full M16 exact compile receipt and ELF')
    C.need(values['snapshot']['binaries'] == bins, 'M16 same snapshot/terminal ELF')
    return root,records,values,sources,validation,library


def seal(destination, *, m16_root, parent_pid, observed_full, ci):
    """Called only by the owner after observing its full-M16 child exit/cleanup."""
    root,records,values,sources,validation,library = _load(m16_root)
    exact(observed_full, ('pid','observed_exit_code','final_exit_code','owned_group_cleanup_complete'),
          'exact parent full M16 observation')
    C.need(type(parent_pid) is int and parent_pid == os.getpid() and parent_pid > 1 and type(observed_full['pid']) is int and
           observed_full['pid'] == values['full_receipt']['child_pid'] and
           all(type(observed_full[k]) is int and observed_full[k] == 0
               for k in ('observed_exit_code','final_exit_code')) and
           observed_full['owned_group_cleanup_complete'] is True, 'observed zero M16 exit and cleanup')
    q = values['producer_qualification']
    C.need(ci == q['ci'], 'current triggering M16 identity')
    value = dict(schema=1,profile=PROFILE,status=STATUS,parent_pid=parent_pid,m16_root=str(root),
        ci=ci,attempt_nonce=q['attempt_nonce'],host_sha256=q['host_sha256'],
        runtime_identity_sha256=q['runtime_identity_sha256'],source_sha256=sources,
        source_manifest_sha256=C.sha(C.encoded(sources)),records=records,library=library,
        observed_full=observed_full,validation=validation,full_29_node_acceptance=False,
        m128_verdict_inherited=False,old_pass_inherited=False)
    destination = Path(destination).absolute()
    C.need(destination == root.parent/'M16_PREREQUISITE.json' and not destination.exists() and
           not destination.is_symlink(), 'new exact current-job prerequisite destination')
    raw = C.encoded(value)
    with destination.open('xb') as stream: stream.write(raw)
    return destination,C.sha(raw),value


def verify(path, expected_sha256, *, m16_root, parent_pid, ci, attempt_nonce,
           host_sha256, runtime_identity_sha256, current_sources=None, library=None):
    root,records,values,sources,validation,actual_library = _load(m16_root)
    C.need(C.safe(path) == root.parent/'M16_PREREQUISITE.json', 'exact current-job prerequisite path')
    value = C.read_json(path,expected_sha256)
    exact(value, ('schema','profile','status','parent_pid','m16_root','ci','attempt_nonce','host_sha256',
        'runtime_identity_sha256','source_sha256','source_manifest_sha256','records','library',
        'observed_full','validation','full_29_node_acceptance','m128_verdict_inherited','old_pass_inherited'),
        'exact current-job M16 prerequisite')
    C.need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == PROFILE and
           value['status'] == STATUS and type(parent_pid) is int and parent_pid > 1 and
           type(value['parent_pid']) is int and value['parent_pid'] == parent_pid and value['m16_root'] == str(root) and value['ci'] == ci and
           value['attempt_nonce'] == attempt_nonce and value['host_sha256'] == host_sha256 and
           value['runtime_identity_sha256'] == runtime_identity_sha256,
           'live current-job prerequisite context')
    q = values['producer_qualification']
    C.need(q['ci'] == ci and q['attempt_nonce'] == attempt_nonce and q['host_sha256'] == host_sha256 and
           q['runtime_identity_sha256'] == runtime_identity_sha256, 'current M16 runtime/host/CI/nonce')
    C.need(value['source_sha256'] == sources and value['source_manifest_sha256'] == C.sha(C.encoded(sources)) and
           C.encoded(value['records']) == C.encoded(records) and C.encoded(value['library']) == C.encoded(actual_library) and
           C.encoded(value['validation']) == C.encoded(validation),
           'replayed full M16 source/terminal/library chain')
    obs = value['observed_full']
    exact(obs, ('pid','observed_exit_code','final_exit_code','owned_group_cleanup_complete'), 'M16 observed exit fields')
    C.need(type(obs['pid']) is int and obs['pid'] == values['full_receipt']['child_pid'] and
           all(type(obs[k]) is int and obs[k] == 0 for k in ('observed_exit_code','final_exit_code')) and
           obs['owned_group_cleanup_complete'] is True and
           all(value[k] is False for k in ('full_29_node_acceptance','m128_verdict_inherited','old_pass_inherited')),
           'M16 observed completion and limited scope')
    if current_sources is not None: compatible_sources(current_sources,sources)
    if library is not None: C.need(C.encoded(library) == C.encoded(actual_library), 'full M128 must use identical full M16 receipt and ELF')
    return value
