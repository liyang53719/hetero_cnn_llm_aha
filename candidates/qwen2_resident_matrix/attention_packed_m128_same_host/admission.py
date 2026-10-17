"""Fresh same-host M128 admission; no historical receipt grants authority.

The owner authenticates both producer/reference children and full M16. Repeated
admission hashes their outputs only; original arrays are independently replayed
by the parent's fresh verifier before it signs the qualification receipt.
"""
import importlib.util
import math
import os
from pathlib import Path
from . import contract as C, prerequisite, views
from .identity import prerequisite_view, terminal_identity

PROFILE = C.PROFILE
STATUS = 'SEALED_FRESH_SAME_HOST_M128_NOT_EXECUTED'
QUALIFIED_PROFILE = 'qwen2-fresh-same-host-m128-producer-qualified-v1'
PRODUCER_REL = 'candidates/qwen2_resident_matrix/portable_official_producer_m128/'
CLAIMS = ('actual_chain_executed','full_public_admission','full_29_node_acceptance',
          'rtl_execution','hardware_recipe_acceptance','old_pass_inherited')
read_reference_bytes = views.read_reference_bytes
read_native_reference = views.read_native_reference


def exact(value, keys, label): C.need(type(value) is dict and set(value) == set(keys), label)


def absolute(value):
    C.need(type(value) is str and Path(value).is_absolute() and '..' not in Path(value).parts and
           str(Path(value)) == value and '\\' not in value and '\x00' not in value, 'canonical absolute path')


def pointer(value):
    exact(value,('path','sha256'),'exact metadata pointer');absolute(value['path'])
    C.need(C.digest(value['sha256']),'metadata pointer digest')


def validate_manifest(value, *, rows=128):
    exact(value, ('schema','profile','status','rows','past_tokens','enable_raw_kv','enable_packed',
        'source_sha256','source_manifest_sha256','producer_origin','producer_workspace','producer_manifest',
        'producer_receipt','producer_context','m16_prerequisite','library'), 'exact fresh M128 manifest')
    C.need(type(rows) is int and rows == 128 and type(value['schema']) is int and value['schema'] == 1 and
           value['profile'] == PROFILE and value['status'] == STATUS and type(value['rows']) is int and
           value['rows'] == 128 and type(value['past_tokens']) is int and value['past_tokens'] == 0 and
           value['enable_raw_kv'] is True and value['enable_packed'] is True, 'genuine fresh M128/past0')
    sources = value['source_sha256']
    C.need(type(sources) is dict and sources and value['source_manifest_sha256'] == C.sha(C.encoded(sources)),
           'fresh M128 source binding')
    for name,digest in sources.items():
        C.need(type(name) is str and name and '\\' not in name and '\x00' not in name and
               not Path(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')) and
               C.digest(digest), 'source map entry')
    for key in ('producer_origin','producer_workspace'): absolute(value[key])
    for key in ('producer_manifest','producer_receipt','producer_context','m16_prerequisite'): pointer(value[key])
    lib = value['library'];exact(lib,('receipt','binary','origin_root'),'same full M16 library record')
    pointer(lib['receipt']);absolute(lib['origin_root']);exact(lib['binary'],('path','bytes','sha256'),'combined ELF')
    absolute(lib['binary']['path'])
    C.need(type(lib['binary']['bytes']) is int and 0 < lib['binary']['bytes'] <= 64*1024*1024 and
           C.digest(lib['binary']['sha256']), 'combined ELF bytes')
    return value


def read_manifest(path, expected_sha256, *, rows=128):
    return validate_manifest(C.read_json(path,expected_sha256),rows=rows)


def source_snapshot(*, enable_raw_kv=False):
    C.need(enable_raw_kv is True,'fresh M128 requires raw KV');return C.snapshot()


def own_sources(): return source_snapshot(enable_raw_kv=True)


def fresh_mode(enabled, manifest=None, manifest_sha256=None, *, rows=None):
    C.need(enabled is True and manifest is not None and C.digest(manifest_sha256) and
           (rows is None or type(rows) is int and rows == 128),'explicit fresh M128 only');return True


def snapshot_mode(snapshot, enabled, *, enable_raw_kv=False):
    C.need(enabled is True and enable_raw_kv is True and snapshot.get('fresh_profile') is True,'fresh snapshot mode')
    identity=snapshot.get('fresh_assets');exact(identity,('profile','manifest','manifest_sha256','enable_raw_kv'),'snapshot identity')
    C.need(identity['profile'] == PROFILE and identity['enable_raw_kv'] is True,'fresh snapshot profile')
    fresh_mode(True,identity['manifest'],identity['manifest_sha256'],rows=snapshot['rows']);return identity


def _load_producer(manifest, sources):
    """Load exact original-checkout producer code without importing a second namespace."""
    origin=C.safe(manifest['producer_origin'],directory=True)
    for leaf in ('driver.py','verify.py','source-lock.json'):
        C.need(C.sha(C.safe(origin/PRODUCER_REL/leaf).read_bytes()) == sources[PRODUCER_REL+leaf],
               'original producer executable source differs')
    path=C.safe(origin/PRODUCER_REL/'verify.py');name=PRODUCER_REL+'verify.py'
    raw=path.read_bytes();C.need(C.sha(raw) == sources[name],'current producer verifier source')
    spec=importlib.util.spec_from_file_location('fresh_m128_original_producer_verifier',path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    C.need(path.read_bytes() == raw,'producer verifier changed during load')
    return module


def validate_qualification(value, producer, manifest):
    exact(value, ('schema','profile','status','attempt_nonce','ci','host_sha256','runtime_identity_sha256',
        'producer_manifest_sha256','producer_source_manifest_sha256','parent_context_sha256','verifier_receipt_sha256',
        'child_pid','child_exit_code','owned_group_cleanup_complete','original_array_gate_revalidated','claims'),
        'exact independently qualified fresh M128 producer')
    C.need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == QUALIFIED_PROFILE and
           value['status'] == 'PASS_FRESH_M128_PRODUCER' and
           value['producer_manifest_sha256'] == manifest['producer_manifest']['sha256'] and
           value['producer_source_manifest_sha256'] == producer['source_manifest_sha256'] and
           value['parent_context_sha256'] == manifest['producer_context']['sha256'] == producer['parent_context_sha256'] and
           value['attempt_nonce'] == producer['attempt_nonce'] and value['ci'] == producer['ci'] and
           value['host_sha256'] == C.sha(C.encoded(producer['host'])) and
           value['runtime_identity_sha256'] == C.sha(C.encoded(producer['runtime_identity'])),
           'fresh producer/source/runtime/context chain')
    C.need(type(value['child_pid']) is int and value['child_pid'] > 1 and
           type(value['child_exit_code']) is int and value['child_exit_code'] == 0 and
           value['owned_group_cleanup_complete'] is True and value['original_array_gate_revalidated'] is True and
           C.digest(value['verifier_receipt_sha256']),'parent-observed independent producer qualification')
    exact(value['claims'],CLAIMS,'producer-only claims')
    C.need(all(v is False for v in value['claims'].values()),'producer cannot claim consumer success')
    return value


def verify_library(receipt, *, manifest):
    from ..attention_packed_m16_entry import library_origin
    lib=manifest['library'];C.need(str(C.safe(receipt)) == lib['receipt']['path'],'exact shared compile receipt')
    binary=C.safe(lib['binary']['path'])
    C.need(binary.stat().st_size == lib['binary']['bytes'] and C.sha(binary.read_bytes()) == lib['binary']['sha256'],
           'same current-job combined ELF')
    return library_origin.verify(receipt,lib['receipt']['sha256'],origin_root=lib['origin_root'],
        execution_root=C.ROOT,library_sha256=lib['binary']['sha256'])



def verify(path, expected_sha256, *, rows=128, enable_raw_kv=False, parent_pid=None):
    C.need(type(rows) is int and rows == 128 and enable_raw_kv is True,'fresh M128/raw admission')
    sources=C.snapshot();C.git_context();manifest=read_manifest(path,expected_sha256)
    C.need(manifest['source_sha256'] == sources,'current M128 execution source identity')
    workspace=C.safe(manifest['producer_workspace'],directory=True);job=workspace.parent
    C.need(workspace.name == 'producer128' and not workspace.is_relative_to(C.ROOT) and
           not C.ROOT.is_relative_to(workspace),'fresh disjoint M128 output root')
    fixed={'producer_manifest':workspace/'PRODUCER_M128.json','producer_receipt':job/'M128_QUALIFICATION.json',
           'producer_context':job/'M128_CONTEXT.json','m16_prerequisite':job/'M16_PREREQUISITE.json'}
    for name,expected in fixed.items(): C.need(C.safe(manifest[name]['path']) == expected,'current-job pointer '+name)
    context=C.read_json(manifest['producer_context']['path'],manifest['producer_context']['sha256'])
    expected_parent=os.getppid() if parent_pid is None else parent_pid
    C.need(type(expected_parent) is int and expected_parent > 1 and context['parent_pid'] == expected_parent and
           context['root'] == manifest['producer_origin'] and context['workspace'] == str(workspace) and
           context['ci']['commit'] == C.source_contract()['git_head'],'live parent/current triggering commit')
    verifier=_load_producer(manifest,sources)
    producer=verifier.verify_handoff(manifest['producer_origin'],workspace,manifest['producer_manifest']['sha256'],
        context=context,expected_context_sha256=manifest['producer_context']['sha256'],
        decode_native=False)
    qualified=C.read_json(manifest['producer_receipt']['path'],manifest['producer_receipt']['sha256'])
    validate_qualification(qualified,producer,manifest)
    replayed=C.read_json(job/'VERIFIED_M128_PRODUCER.json',qualified['verifier_receipt_sha256'])
    driver=verifier.driver(context['driver_sha256'])
    C.need(replayed == verifier.verification_receipt(driver,producer,manifest['producer_manifest']['sha256'],
           manifest['producer_context']['sha256']), 'parent full native29/116 and scalar22/12 verification chain')
    C.need(producer['ci'] == context['ci'] and producer['attempt_nonce'] == context['attempt_nonce'] and
           producer['upstream']['m16_prerequisite'] == manifest['m16_prerequisite'],'current parent/M16 producer binding')
    m16=prerequisite.verify(manifest['m16_prerequisite']['path'],manifest['m16_prerequisite']['sha256'],
        m16_root=job/'m16',parent_pid=expected_parent,ci=producer['ci'],attempt_nonce=producer['attempt_nonce'],
        host_sha256=qualified['host_sha256'],runtime_identity_sha256=qualified['runtime_identity_sha256'],
        current_sources=sources,library=manifest['library'])
    lib=verify_library(manifest['library']['receipt']['path'],manifest=manifest)
    C.need(lib['compiler'] == producer['runtime_observation']['compiler'],'same current runtime compiler')
    # Only reference outputs in the current namespace feed the unchanged late
    # comparator. Payload inputs may point to immutable same-job M16 storage.
    driver=verifier.driver(context['driver_sha256'])
    def resolve(item): return driver.resolve_artifact(workspace,producer,item)
    def local(value):
        if type(value) is dict:
            if set(value) == {'root','path','bytes','sha256'}:
                C.need(value['root'] == 'current','reference output must be freshly produced at M128')
                return {k:value[k] for k in ('path','bytes','sha256')}
            return {k:local(v) for k,v in value.items()}
        if type(value) is list: return [local(v) for v in value]
        return value
    origin_manifest={k:local(producer[k]) for k in ('readonly','sequential','reduced','native')}
    native=C.read_json(resolve(producer['native']['result']),producer['native']['result']['sha256'],limit=16*1024*1024)
    exported=C.read_json(resolve(producer['sequential']['export_receipt']),producer['sequential']['export_receipt']['sha256'])
    identity=terminal_identity(manifest,producer,qualified,m16,expected_sha256)
    result=views.build_views(manifest_path=C.safe(path),manifest_sha256=expected_sha256,origin_assets=workspace,
        origin_manifest=origin_manifest,native_result=native,exported=exported,
        library_receipt=manifest['library']['receipt']['path'],library=manifest['library']['binary']['path'],
        origin_identity=identity['origin_identity'],m16_prerequisite=identity['m16_prerequisite'],
        payload_paths={name:str(resolve(item)) for name,item in producer['payload']['tensors'].items()},
        producer_generated_sha256=driver.RUNNER_SHA)
    result['terminal_identity']=identity
    C.need(C.snapshot() == sources and read_manifest(path,expected_sha256) == manifest,'M128 admission source drift')
    return result


def seal_manifest(destination, *, producer_origin, producer_workspace, producer_manifest_sha256,
                  producer_receipt, producer_receipt_sha256, producer_context, producer_context_sha256,
                  m16_prerequisite, m16_prerequisite_sha256):
    workspace=C.safe(producer_workspace,directory=True);origin=C.safe(producer_origin,directory=True)
    m16=C.read_json(m16_prerequisite,m16_prerequisite_sha256);sources=C.snapshot()
    destination=Path(destination).absolute();C.safe(destination.parent,directory=True)
    C.need(not destination.exists() and not destination.is_symlink(),'new M128 entry manifest required')
    value=dict(schema=1,profile=PROFILE,status=STATUS,rows=128,past_tokens=0,enable_raw_kv=True,enable_packed=True,
        source_sha256=sources,source_manifest_sha256=C.sha(C.encoded(sources)),producer_origin=str(origin),
        producer_workspace=str(workspace),producer_manifest=dict(path=str(workspace/'PRODUCER_M128.json'),sha256=producer_manifest_sha256),
        producer_receipt=dict(path=str(C.safe(producer_receipt)),sha256=producer_receipt_sha256),
        producer_context=dict(path=str(C.safe(producer_context)),sha256=producer_context_sha256),
        m16_prerequisite=dict(path=str(C.safe(m16_prerequisite)),sha256=m16_prerequisite_sha256),library=m16['library'])
    validate_manifest(value);raw=C.encoded(value)
    with destination.open('xb') as stream: stream.write(raw)
    try: admitted=verify(destination,C.sha(raw),enable_raw_kv=True)
    except BaseException:
        destination.unlink(missing_ok=True);raise
    return destination,C.sha(raw),admitted
