"""Explicit selected retained data schema. No old PASS or owner liveness transfer.
The independently approved selection is reconstructed from original metadata,
not from the caller's shortened file list. Only selected payloads are opened.
"""
import json
import pathlib
import importlib.util

P = pathlib.Path
D = P(__file__).resolve().parent
SCHEMA = 'RETAINED_SELECTED_M128_MATERIALS_V1'
CANDIDATE_SCHEMA = 'MODEL_CANDIDATE_SELECTED_DATA_REFERENCE_ONLY_V1'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a = load('retained_selected_acquisition', D / 'selected_acquisition.py')
r = load('retained_selected_reference', D / 'selected_reference_job.py')
need, sha, same = a.need, a.sha, a.same


def original_sources(b, selected):
    root = P(b['repo']) / a.RECOVERY
    names = {a.RECOVERY + '/' + name for name in ('reconstruct_plan.py', 'ACQUISITION_PLAN.json',
             'TENSOR_ACQUISITION_PLAN.json', 'HISTORICAL_SOURCE_HASH_SET.json')}
    names.update(a.RECOVERY + '/pins/' + name for name in ('qwen2_1p5b_manifest.json', 'qwen3_5_0p8b_manifest.json',
                  'qwen3_5_35b_a3b_manifest.json', 'layer0_payload_pin.json', 'layer3_payload_pin.json'))
    names.update(a.RECOVERY + '/' + row['header']['json_text'] for row in json.loads((root / 'ACQUISITION_PLAN.json').read_text())['headers'])
    names.update(a.RESUME + '/' + name for name in ('acquire_resumable.py', 'prefix.py'))
    names.update('candidates/same_job_execution_20261030/runtime/' + name for name in ('reference_job.py', 'reference_phase.py'))
    profiles = a.profiles(b)
    # selected_plan uses this metadata file even for a P0-only selection.
    names.add(a.REFERENCE + '/profiles.json')
    for i in selected:
        relative = 'candidates/' + ('independent_reference_p0_cache_arm_20261028T2313' if i == 0 else
                                   'independent_block_reference_prepare_v3_20261028T2312')
        names.update(relative + '/' + name for name in ('run_reference.py', 'profiles.json', 'tensor_acquisition_plan.json', 'stimulus.py'))
        if i:
            names.add(relative + '/router_local_observer.py')
        names.add('config/upstream/weight_headers/' + profiles[i]['model'] + '/config.json')
    return names


def candidate_contract(m, manifest_pin, d, old, b, source_rows):
    after = m.read(b['artifact_manifest'], 65536)
    if after.get('schema') != m.CANDIDATE_SCHEMA:
        need(not b.get('model_candidate_review'), 'selected data-only candidate review requires ordinary full candidate')
        return None
    need(b.get('execution_context') == 'CLOUD_EXECUTOR_V1' and b.get('model_candidate_review'), 'independently approved selected candidate review')
    helper = a.checked_source(b, 'candidates/same_job_execution_20261030/numeric/candidate_admission.py')
    admission = load('retained_selected_candidate_admission', helper)
    review = admission.verify(b['model_candidate_review'], b)
    need(review['scope'] == m.REVIEW_SCOPE, 'ordinary candidate evaluation only')
    c = review['data_reference_contract']
    keys = {'schema', 'scope', 'old_artifact_manifest_sha256', 'new_artifact_manifest_sha256',
            'retained_materials_sha256', 'old_source_pins_sha256', 'reference_sources',
            'weights_sha256', 'references_sha256', 'profiles', 'registered_profiles', 'tokens', 'routing'}
    finite = 'finite_watchdog_driver' in c
    if finite:
        keys.add('finite_watchdog_driver')
    need(type(c) is dict and set(c) == keys and c['schema'] == CANDIDATE_SCHEMA and c['scope'] == m.CANDIDATE_SCOPE,
         'explicit selected candidate data-only contract')
    need(same(c['profiles'], a.policy(b).eligible(b)) and same(c['registered_profiles'], list(range(5)))
         and type(c['tokens']) is int and c['tokens'] == 128 and c['routing'] == 'UNMODIFIED_OFFICIAL_TORCH_TOPK',
         'selected software materials leave complete hardware and original routing unchanged')
    for field, value in (('old_artifact_manifest_sha256', old['artifact_manifest']),
                         ('new_artifact_manifest_sha256', b['artifact_manifest']),
                         ('retained_materials_sha256', manifest_pin), ('old_source_pins_sha256', old['source_pins'])):
        m.checked(value, 2 << 20)
        need(c[field] == value['sha256'], 'independent selected candidate input binding')
    need(c['weights_sha256'] == a.domain_sha(d['weights']) and c['references_sha256'] == a.domain_sha(d['references']),
         'complete exact selected weight and reference domains')
    need(same(sorted(c['reference_sources'], key=lambda row: row['path']), sorted(source_rows, key=lambda row: row['path'])),
         'complete unchanged original selected producer source closure')
    before = m.read(old['artifact_manifest'], 65536)
    need(before['schema'] == 'FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2', 'original production data provenance')
    drivers = []
    for manifest, artifact in ((old['artifact_manifest'], before), (b['artifact_manifest'], after)):
        need(same(artifact['profiles'], list(range(5))) and type(artifact['matrix_macs']) is int
             and artifact['matrix_macs'] == 4096 and type(artifact['vector_lanes']) is int and artifact['vector_lanes'] == 32
             and artifact['moe_reference_contract'] == 'ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',
             'complete registered hardware resource and original routing contract')
        driver = artifact['common']['driver']
        need(type(driver) is dict and set(driver) == {'path', 'bytes', 'sha256'} and driver['path'] == 'driver.cpp', 'fixed original stimulus driver')
        m.checked(dict(driver, path=str(P(manifest['path']).parent / 'driver.cpp')), 1 << 30)
        drivers.append(driver)
    if finite:
        helper = admission.finite_watchdog_module(b['repo'], b['source_pins'])
        need(c['finite_watchdog_driver'] == helper.RELATION, 'exact reviewed ordinary watchdog relation')
        helper.inverse((P(old['artifact_manifest']['path']).parent / 'driver.cpp').read_bytes(),
                       (P(b['artifact_manifest']['path']).parent / 'driver.cpp').read_bytes())
    else:
        need(same(drivers[0], drivers[1]), 'selected candidate may not change stimulus driver')
    return c


def runtime_entry(m, old, job, key, d, policy=None):
    if policy is None:
        policy = load('retained_original_policy_shape', D.parent / 'profile_policy.py')
    selected = policy.is_selected(old)
    mode = old.get('runtime_mode')
    if mode == 'IMPORT_EXISTING_PINNED_RUNTIME':
        need(old.get('runtime_reuse_manifest') is not None and old.get('archive_mode') == 'READ_EXISTING_PINNED_ARCHIVES'
             and 'runtime_owner' not in d, 'explicit original imported runtime provenance mode')
        runtime = m.read(old['runtime_reuse_manifest'])
        need(runtime['schema'] == ('PINNED_EXISTING_SELECTED_RUNTIME_BYTES_V1' if selected else 'PINNED_EXISTING_THREE_RUNTIME_BYTES_V1')
             and runtime['scope'] == 'EXISTING_BYTES_ONLY_REVALIDATE_EVERY_EXECUTOR'
             and runtime['reference_qualified'] is False and runtime['numerical_qualified'] is False,
             'exact original imported runtime schema and no historical qualification')
        need(runtime['source_commit'] == old['identity']['source_commit'], 'original selected runtime source provenance')
        need(set(runtime['entries']) == set(policy.runtimes(old) if selected else ('qwen2', 'qwen35_08b', 'qwen35_35b')),
             'complete original producer runtime inventory')
        if selected:
            policy.require_same(old, runtime)
        need(key in runtime['entries'], 'original runtime for selected reference')
        return runtime['entries'][key]
    # Fresh-install provenance is a pinned original owner manifest, never a live
    # lease or a transferred install PASS. No other runtime entries are opened.
    need(mode == 'FRESH_ORIGINAL_RUNTIME_INSTALL' and old.get('archive_mode') == 'DOWNLOAD_ORIGINAL_ARCHIVES'
         and old.get('runtime_reuse_manifest') is None, 'explicit original fresh runtime provenance mode')
    need('runtime_owner' in d, 'selected retained fresh installation needs original owner manifest pin')
    owner = m.read(d['runtime_owner'])
    need(owner['schema'] == ('SHARED_SELECTED_RUNTIME_OWNER_FRESH_JOB_V1' if selected else 'SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3')
         and P(d['runtime_owner']['path']) == job / 'materials/runs/bind/owner/SHARED_RUNTIMES_FRESH_JOB_V3.json'
         and owner['identity'] == old['identity'] and owner['owner_root'] == str(job / 'materials')
         and owner['reference_qualified'] is False and owner['numerical_qualified'] is False
         and same(owner['profile_mapping'], list(r.KEYS)) and set(owner['entries']) == set(policy.runtimes(old)),
         'exact original fresh owner schema and inventory, no qualification transfer')
    policy.require_same(old, owner)
    return owner['entries'][key]


def verify(manifest_pin, b):
    m = load('selected_retained_legacy_primitives', D / 'retained_materials.py')
    policy = a.policy(b)
    for name in ('selected_retained_materials.py', 'selected_acquisition.py', 'selected_reference_job.py'):
        a.checked_source(b, 'candidates/same_job_execution_20261030/runtime/' + name)
    d = m.read(manifest_pin, 2 << 20)
    fields = {'schema', 'scope', 'old_controller_binding', 'old_executor_identity', 'weights_summary', 'weights_outer',
              'references_manifest', 'weights', 'references', 'numerical_pass', 'execution_policy', 'weights_producer'}
    if 'runtime_owner' in d:
        fields.add('runtime_owner')
    need(type(d) is dict and set(d) == fields and d['schema'] == SCHEMA and d['scope'] == m.SCOPE
         and d['numerical_pass'] is False, 'explicit selected retained data-only schema')
    policy.require_same(b, d)
    selected = policy.eligible(b)
    plan = a.selected_plan(b)
    old = m.read(d['old_controller_binding'])
    ident = m.read(d['old_executor_identity'], 65536)
    identity = load('selected_retained_identity', a.checked_source(b, 'candidates/same_job_execution_20261030/executor_identity.py'))
    identity.validate(ident)
    need(old['identity'] == ident and old['executor_identity'] == ident and old['executor_identity_pin'] == d['old_executor_identity'],
         'original completed controller identity binding')
    need(old['execution_context'] == 'CLOUD_EXECUTOR_V1' and same(old['profiles'], list(range(5)))
         and type(old['tokens']) is int and old['tokens'] == 128 and type(old['matrix_macs']) is int and old['matrix_macs'] == 4096,
         'original complete registered hardware M128 materials')
    need(b['identity']['execution_id'] != ident['execution_id'] and b['identity'] != ident, 'fresh executor cannot impersonate old owner')
    need(set(selected).issubset(policy.eligible(old)), 'all selected materials actually eligible for original producer')
    job = P(old['job_root'])
    need(job.is_absolute() and job == job.resolve() and job.is_dir() and all(not item.is_symlink() for item in (job, *job.parents)), 'canonical original material job')
    need(P(d['old_controller_binding']['path']) == P(str(job) + '-CLOUD_BINDING.json')
         and P(d['old_executor_identity']['path']) == P(str(job) + '-EXECUTOR_IDENTITY.json'), 'fixed original completed controller records')
    catalog = m.read(old['source_pins'])
    need(catalog['schema'] == 'REVIEWED_RELATIVE_SOURCE_CLOSURE_V1', 'original source closure schema')
    names = original_sources(b, selected)
    if policy.is_selected(old):
        names.update('candidates/same_job_execution_20261030/runtime/' + name for name in ('selected_acquisition.py', 'selected_reference_job.py'))
    source_rows = [row for row in catalog['files'] if row['path'] in names]
    need(len(source_rows) == len(names) and {row['path'] for row in source_rows} == names, 'independent complete original selected source closure')
    for row in source_rows:
        source = m.source(row['path'], old, b)
        need(source.stat().st_size == row['bytes'] and sha(source) == row['sha256'], 'exact historical original source catalog row')
    need(sha(P(old['runtime_package']) / 'reference_job.py') == r.ORIGINAL_JOB_SHA
         and sha(P(old['runtime_package']) / 'reference_phase.py') == r.ORIGINAL_PHASE_SHA
         and P(old['runtime_package']) == P(old['repo']) / 'candidates/same_job_execution_20261030/runtime', 'exact original reference lifecycle producer')
    candidate = candidate_contract(m, manifest_pin, d, old, b, source_rows)
    artifact_root = str(P(old['artifact_manifest']['path']).parent) if candidate is not None else m.material_artifact_identity(old, b)
    payload = job / 'runs/weights/output'
    producer = d['weights_producer']
    summary = m.at(d['weights_summary'], payload / 'SUMMARY.json')
    if producer == {'kind': 'ORIGINAL_FULL_FIVE_V1'}:
        need(not policy.is_selected(old), 'full original acquisition cannot claim selected producer identity')
        acq = P(old['repo']) / a.RESUME / 'acquire_resumable.py'
        r.strict(m.at(d['weights_outer'], job / 'runs/weights/RESULT.json'), [old['python'], '-B', acq, '--output', payload, '--execute'])
        need(summary['status'] == 'ACQUIRED_70_ORIGINAL_TENSORS_ONLY' and type(summary['tensors']) is int and summary['tensors'] == 70
             and type(summary['tensor_bytes']) is int and summary['tensor_bytes'] == m.TOTAL_BYTES
             and summary['reference_executed'] is False and summary['dut_executed'] is False, 'complete original70 acquisition provenance')
    else:
        need(type(producer) is dict and set(producer) == {'kind', 'binding', 'plan'} and producer['kind'] == 'SELECTED_ORIGINAL_V1', 'exact selected acquisition producer')
        policy.require_same(b, old)
        ab = m.at(producer['binding'], job / 'bindings/SELECTED_WEIGHTS.json')
        need(ab == dict(old, output=str(payload)), 'selected acquisition exact original controller binding')
        need(same(m.at(producer['plan'], payload / 'ACQUISITION_PLAN.json'), plan), 'independently reconstructed original selected acquisition plan')
        acq = P(old['runtime_package']) / 'selected_acquisition.py'
        r.strict(m.at(d['weights_outer'], job / 'runs/weights/RESULT.json'), [old['python'], '-B', acq, '--binding', producer['binding']['path'], '--sha256', producer['binding']['sha256'], '--execute'])
        a.validate_summary(summary, plan)
    need(type(d['weights']) is list and len(d['weights']) == len(plan['specs']), 'complete selected retained weight manifest')
    rows = []
    expected = {(row['model'], row['name']): row for row in plan['specs']}
    for item in d['weights']:
        need(type(item) is dict and set(item) == {'file', 'receipt'}, 'exact selected retained tensor pin row')
        receipt_path = m.checked(item['receipt'], 65536)
        receipt = json.loads(receipt_path.read_text())
        key = (receipt['model'], receipt['name'])
        need(key in expected and receipt_path == payload / key[0] / (key[1] + '.receipt.json'), 'selected independently reconstructed receipt identity')
        rows.append(dict(model=key[0], name=key[1], pin=item['file']))
    weights = a.verify_weights(b, rows, payload, summary if producer['kind'] == 'SELECTED_ORIGINAL_V1' else None,
                               allow_unselected=producer['kind'] == 'ORIGINAL_FULL_FIVE_V1')
    refs = m.at(d['references_manifest'], job / 'materials/references/REFERENCES.json')
    need(refs['identity'] == ident and same(refs['execution_policy'], policy.checked(old))
         and refs['scope'] == 'REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT'
         and set(refs['references']) == set(map(str, policy.eligible(old)))
         and set(d['references']) == set(map(str, selected)), 'original complete producer index and exact selected references')
    result = {}
    for i in selected:
        item = d['references'][str(i)]
        need(type(item) is dict and set(item) == {'result', 'phase', 'outer'} and item['result'] == refs['references'][str(i)], 'exact selected original reference pin')
        home = job / ('materials/references/profile' + str(i))
        dest = home / 'actual/reference'
        phase = m.at(item['phase'], home / 'PHASE.json')
        m.at(item['result'], dest / 'RESULT.json')
        rt = runtime_entry(m, old, job, r.KEYS[i], d, policy)
        for key in ('wrapper', 'installation', 'sidecar'):
            m.checked(rt[key])
        source = r.producer(b, i)
        old_source = P(old['repo']) / source.relative_to(P(b['repo']))
        profile = a.profiles(b)[i]
        config = P(old['repo']) / 'config/upstream/weight_headers' / profile['model'] / 'config.json'
        args = [str(old_source), '--profile', str(i), '--payload', str(payload), '--config', str(config),
                '--runtime-receipt', rt['installation']['path'], '--runtime-receipt-sha256', rt['installation']['sha256'],
                '--runtime-source-pins', rt['sidecar']['path'], '--runtime-source-pins-sha256', rt['sidecar']['sha256'],
                '--output', str(dest), '--execute-reviewed']
        need(same(phase, dict(argv=args, source_sha256=sha(old_source))), 'exact immutable original reference invocation')
        r.strict(m.at(item['outer'], home / 'actual/RESULT.json'), [rt['wrapper']['path'], str(P(old['runtime_package']) / 'reference_phase.py'),
                 '--binding', home / 'PHASE.json', '--sha256', item['phase']['sha256']])
        r.verify_result(b, i, item['result'], dict(receipt=rt['installation'], sidecar=rt['sidecar']))
        result[str(i)] = item['result']
    for value in (manifest_pin, d['old_controller_binding'], d['old_executor_identity'], d['references_manifest']):
        m.checked(value, 2 << 20)
    return dict(payload=str(payload), weights=weights, references=result,
                roots=[str(job), str(P(d['old_controller_binding']['path']).parent)] + ([artifact_root] if artifact_root else []),
                scope=m.CANDIDATE_SCOPE if candidate is not None else m.SCOPE, execution_policy=policy.checked(b),
                retained_schema=SCHEMA, numerical_pass=False, runtime_pass=False)
