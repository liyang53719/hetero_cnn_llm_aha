"""Fresh-host admission, distinct from immutable historical M16 receipts.

All private tensors are hash-only before whole terminal. Parent receipts bind
observed execution but cannot authenticate their own creator; the separately
reviewed supervisor owns that boundary. This module never authorizes a launch.
"""
import math
from pathlib import Path
from ..raw_kv_public_fresh import assets as A
from . import contract as C, views

PROFILE = C.PROFILE
STATUS = 'SEALED_FRESH_SAME_HOST_M16_NOT_EXECUTED'
QUALIFIED_PROFILE = 'qwen2-fresh-same-host-m16-producer-qualified-v1'
CLAIMS = ('actual_chain_executed','full_public_admission','full_29_node_acceptance',
          'rtl_execution','hardware_recipe_acceptance','old_pass_inherited')
read_reference_bytes = views.read_reference_bytes
read_native_reference = views.read_native_reference


def exact(value, keys, label):
    C.need(type(value) is dict and set(value) == set(keys), label)


def pointer(value):
    exact(value, ('path','sha256'), 'exact metadata pointer')
    C.need(type(value['path']) is str and Path(value['path']).is_absolute() and
           '..' not in Path(value['path']).parts and C.digest(value['sha256']), 'canonical metadata pointer')


def _producer_workspace(path):
    """Reject overlap before loading a generated runner or sealing admission."""
    workspace = C.safe(path, directory=True)
    C.need(not workspace.is_relative_to(C.ROOT) and not C.ROOT.is_relative_to(workspace),
           'producer workspace must be disjoint from the executing source tree')
    return workspace


def ci_identity(ci):
    exact(ci, ('commit','run_id','run_attempt'), 'exact triggering CI identity')
    C.need(C.commit(ci['commit']) and all(type(ci[k]) is str and ci[k].isascii() and ci[k].isdigit() and
           int(ci[k]) > 0 for k in ('run_id','run_attempt')) and ci['run_attempt'] == '1',
           'canonical first-attempt triggering CI identity')


def validate_qualification(value, producer, manifest_sha256):
    exact(value, ('schema','profile','status','attempt_nonce','producer_manifest_sha256',
         'producer_source_manifest_sha256','host_sha256','runtime_identity_sha256','ci',
         'child_pid','child_exit_code','owned_group_cleanup_complete','producer_native_gate_validated',
         'elapsed_seconds','claims','fresh_tiny_result_sha256','fresh_tiny_source_manifest_sha256'),
          'exact parent qualification receipt')
    C.need(type(value['schema']) is int and value['schema'] == 1 and value['profile'] == QUALIFIED_PROFILE and
           value['status'] == 'PASS_FRESH_M16_PRODUCER', 'fresh producer qualification required')
    C.need(C.digest(value['attempt_nonce']) and value['attempt_nonce'] == producer['attempt_nonce'] and
           value['producer_manifest_sha256'] == manifest_sha256 and
           value['producer_source_manifest_sha256'] == producer['source_manifest_sha256'] and
           value['host_sha256'] == C.sha(C.encoded(producer['host'])) and
           value['runtime_identity_sha256'] == C.sha(C.encoded(producer['runtime_identity'])),
           'producer/source/nonce/host/runtime binding differs')
    ci_identity(value['ci'])
    C.need(A.same(value['ci'], producer['ci']), 'producer triggering CI differs')
    C.need(type(value['child_pid']) is int and value['child_pid'] > 0 and
           type(value['child_exit_code']) is int and value['child_exit_code'] == 0 and
           value['owned_group_cleanup_complete'] is True and value['producer_native_gate_validated'] is True,
           'observed producer completion and cleanup required')
    C.need(type(value['elapsed_seconds']) in (int,float) and math.isfinite(value['elapsed_seconds']) and
           value['elapsed_seconds'] >= 0, 'finite observed producer duration')
    C.need(C.digest(value['fresh_tiny_result_sha256']) and C.digest(value['fresh_tiny_source_manifest_sha256']),
           'fresh actual tiny qualification binding required')
    exact(value['claims'], CLAIMS, 'exact producer-only claims')
    C.need(all(v is False for v in value['claims'].values()), 'producer cannot claim consumer acceptance')
    return value


def validate_manifest(value, *, rows=16):
    exact(value, ('schema','profile','status','rows','past_tokens','enable_raw_kv','enable_packed',
         'source_sha256','source_manifest_sha256','producer_workspace','producer_manifest',
         'producer_receipt','library','tiny'), 'exact fresh-host entry manifest')
    C.need(type(rows) is int and rows == 16 and type(value['schema']) is int and value['schema'] == 1 and
           value['profile'] == PROFILE and value['status'] == STATUS and
           type(value['rows']) is int and value['rows'] == 16 and type(value['past_tokens']) is int and
           value['past_tokens'] == 0 and value['enable_raw_kv'] is True and value['enable_packed'] is True,
           'canonical fresh-host full-M16 profile')
    C.need(type(value['source_sha256']) is dict and value['source_sha256'] and
           value['source_manifest_sha256'] == C.sha(C.encoded(value['source_sha256'])), 'source manifest binding')
    C.need(type(value['producer_workspace']) is str and Path(value['producer_workspace']).is_absolute() and
           '..' not in Path(value['producer_workspace']).parts, 'absolute producer workspace')
    for key in ('producer_manifest','producer_receipt'):
        pointer(value[key])
    exact(value['tiny'], ('workspace','result','input_contract'), 'exact fresh tiny result binding')
    C.need(type(value['tiny']['workspace']) is str and Path(value['tiny']['workspace']).is_absolute() and
           '..' not in Path(value['tiny']['workspace']).parts, 'absolute fresh tiny workspace')
    pointer(value['tiny']['result'])
    pointer(value['tiny']['input_contract'])
    exact(value['library'], ('receipt','binary','origin_root'), 'fresh consumer library binding')
    C.need(type(value['library']['origin_root']) is str and Path(value['library']['origin_root']).is_absolute() and
           '..' not in Path(value['library']['origin_root']).parts, 'explicit compile source origin')
    pointer(value['library']['receipt'])
    exact(value['library']['binary'], ('path','bytes','sha256'), 'fresh combined ELF record')
    binary = value['library']['binary']
    C.need(type(binary['path']) is str and Path(binary['path']).is_absolute() and '..' not in Path(binary['path']).parts and
           type(binary['bytes']) is int and 0 < binary['bytes'] <= 64*1024*1024 and C.digest(binary['sha256']),
           'fresh combined ELF record types')
    return value


def read_manifest(path, expected_sha256, *, rows=16):
    return validate_manifest(C.read_json(path, expected_sha256), rows=rows)


def source_snapshot(*, enable_raw_kv=False):
    C.need(enable_raw_kv is True, 'fresh-host profile requires raw KV')
    return C.snapshot()


def own_sources():
    return source_snapshot(enable_raw_kv=True)


def fresh_mode(enabled, manifest=None, manifest_sha256=None, *, rows=None):
    C.need(enabled is True and manifest is not None and C.digest(manifest_sha256) and
           (rows is None or type(rows) is int and rows == 16), 'explicit fresh-host M16 mode required')
    return True


def snapshot_mode(snapshot, enabled, *, enable_raw_kv=False):
    C.need(enabled is True and enable_raw_kv is True and snapshot.get('fresh_profile') is True,
           'explicit fresh-host snapshot modes')
    identity = snapshot.get('fresh_assets')
    exact(identity, ('profile','manifest','manifest_sha256','enable_raw_kv'), 'fresh-host snapshot identity')
    C.need(identity['profile'] == PROFILE and identity['enable_raw_kv'] is True, 'fresh-host snapshot profile')
    fresh_mode(True, identity['manifest'], identity['manifest_sha256'], rows=snapshot['rows'])
    return identity


def verify_library(receipt, *, manifest):
    """Original generic compiler flags/source/ELF verifier, with fresh receipts."""
    from ..official_bf16 import dense_silu as original
    lib = manifest['library']
    C.need(str(C.safe(receipt)) == lib['receipt']['path'], 'exact fresh compile receipt')
    value = C.read_json(receipt, lib['receipt']['sha256'], limit=262144)
    C.need(type(value.get('schema')) is int and type(value.get('returncode')) is int,
           'canonical compile receipt integers')
    binary = C.safe(lib['binary']['path'])
    C.need(binary.stat().st_size == lib['binary']['bytes'] and A.file_sha(binary) == lib['binary']['sha256'] and
           value['library'] == str(binary) and value['library_sha256'] == lib['binary']['sha256'],
           'fresh compile receipt/ELF binding')
    from ..attention_packed_m16_entry import library_origin
    return library_origin.verify(receipt, lib['receipt']['sha256'], origin_root=lib['origin_root'],
                                 execution_root=C.ROOT, library_sha256=lib['binary']['sha256'])


def verify_tiny(manifest, qualified, producer, library):
    """Bind the actual new tiny-qualified ELF, source origin and interpreter."""
    from ..portable_consumer_qualification import contract as tiny_contract
    tiny = manifest['tiny']
    workspace = C.safe(tiny['workspace'], directory=True)
    C.need(C.safe(tiny['result']['path']) == workspace/'result.json' and
           C.safe(manifest['library']['origin_root'], directory=True) == workspace/'source' and
           C.safe(manifest['library']['receipt']['path']) == workspace/'build/official_bf16_compile.json' and
           C.safe(manifest['library']['binary']['path']) == workspace/'build/official_bf16_matrix_silu.so',
           'exact fresh tiny build/source paths required')
    C.need(tiny['result']['sha256'] == qualified['fresh_tiny_result_sha256'], 'parent-qualified tiny result differs')
    inputs = tiny_contract.shape(C.read_json(tiny['input_contract']['path'], tiny['input_contract']['sha256']))
    expected = dict(inputs['source_sha256'], **inputs['generated_sha256'])
    C.need(C.sha(C.encoded(expected)) == qualified['fresh_tiny_source_manifest_sha256'],
           'parent-qualified tiny source map differs')
    for name, digest in expected.items():
        path = tiny_contract.safe(workspace/'source', name)
        C.need(A.file_sha(path) == digest, 'fresh tiny generated source drift: '+name)
    value = C.read_json(tiny['result']['path'], tiny['result']['sha256'])
    tiny_contract.result(value, qualified['ci']['commit'], inputs)
    C.need(value['library_sha256'] == library['library_sha256'], 'full consumer ELF is not the fresh qualified ELF')
    observation = producer['runtime_observation']
    for identity in value['identities'].values():
        C.need(identity['interpreter']['sha256'] == observation['python_executable_sha256'] and
               A.same(identity['compiler'], {k:observation['compiler'][k] for k in ('sha256','version')}) and
               identity['combined_elf']['sha256'] == manifest['library']['binary']['sha256'] and
               identity['combined_elf']['bytes'] == manifest['library']['binary']['bytes'],
               'fresh tiny/producer/full consumer interpreter/compiler/ELF differs')
    return value


def verify(path, expected_sha256, *, rows=16, enable_raw_kv=False):
    C.need(type(rows) is int and rows == 16 and enable_raw_kv is True, 'explicit fresh-host M16/raw admission')
    sources = C.snapshot()
    C.git_context()
    manifest = read_manifest(path, expected_sha256, rows=rows)
    C.need(A.same(manifest['source_sha256'], sources), 'entry/executing source identity differs')
    workspace = _producer_workspace(manifest['producer_workspace'])
    pp = manifest['producer_manifest']
    C.need(C.safe(pp['path']) == workspace/'PRODUCER_M16.json', 'exact fresh producer handoff path')
    from ..portable_official_producer import driver
    # Default verification is explicitly hash/metadata-only. It must not call a
    # producer, construct Recipe/CDLL, or decode a comparison tensor.
    producer = driver.verify_handoff(C.ROOT, workspace, pp['sha256'], decode_native=False)
    C.need(A.same(producer, C.read_json(pp['path'], pp['sha256'])), 'verified producer handoff result differs')
    qualified = C.read_json(manifest['producer_receipt']['path'], manifest['producer_receipt']['sha256'])
    validate_qualification(qualified, producer, pp['sha256'])
    C.need(qualified['ci']['commit'] == C.source_contract()['git_head'], 'producer and consumer commits differ')
    library = verify_library(manifest['library']['receipt']['path'], manifest=manifest)
    C.need(A.same(library['compiler'], producer['runtime_observation']['compiler']), 'same-host producer/consumer compiler differs')
    verify_tiny(manifest, qualified, producer, library)
    native_result = A.metadata(workspace, producer['native']['result'])
    exported = A._verify_exports(workspace, producer)
    view_manifest = dict(producer, library=manifest['library'], producer_manifest_sha256=pp['sha256'],
        producer_receipt_sha256=manifest['producer_receipt']['sha256'],
        producer_generated_sha256=driver.RUNNER_SHA)
    directories = {role: A.resolve_artifact(workspace, next(iter(producer[role]['outputs'].values()))).parent
                   for role in ('sequential','reduced')}
    result = views.build_views(workspace, C.safe(path), expected_sha256, view_manifest, exported,
                              native_result, directories, enable_raw_kv=True)
    C.need(C.snapshot() == sources and A.same(read_manifest(path, expected_sha256), manifest),
           'entry/source changed during admission')
    return result


def seal_manifest(destination, *, producer_workspace, producer_manifest_sha256,
                  producer_receipt, producer_receipt_sha256, compile_receipt, compile_origin,
                  tiny_workspace, tiny_input_contract):
    """Seal only verified inputs; caller must still obtain independent launch authority."""
    destination = Path(destination).absolute()
    C.need('..' not in destination.parts and not destination.exists() and not destination.is_symlink(),
           'fresh entry manifest destination required')
    C.safe(destination.parent, directory=True)
    workspace = _producer_workspace(producer_workspace)
    compiled = C.safe(compile_receipt)
    built = C.read_json(compiled)
    binary = C.safe(built['library'])
    tiny_workspace = C.safe(tiny_workspace, directory=True)
    tiny_input_contract = C.safe(tiny_input_contract)
    sources = C.snapshot()
    value = dict(schema=1, profile=PROFILE, status=STATUS, rows=16, past_tokens=0,
        enable_raw_kv=True, enable_packed=True, source_sha256=sources,
        source_manifest_sha256=C.sha(C.encoded(sources)), producer_workspace=str(workspace),
        producer_manifest=dict(path=str(workspace/'PRODUCER_M16.json'), sha256=producer_manifest_sha256),
        producer_receipt=dict(path=str(C.safe(producer_receipt)), sha256=producer_receipt_sha256),
        tiny=dict(workspace=str(tiny_workspace),
                  result=dict(path=str(C.safe(tiny_workspace/'result.json')), sha256=A.file_sha(tiny_workspace/'result.json')),
                  input_contract=dict(path=str(tiny_input_contract), sha256=A.file_sha(tiny_input_contract))),
        library=dict(origin_root=str(C.safe(compile_origin, directory=True)),
                     receipt=dict(path=str(compiled), sha256=A.file_sha(compiled)),
                     binary=dict(path=str(binary), bytes=binary.stat().st_size, sha256=A.file_sha(binary))))
    validate_manifest(value)
    raw = C.encoded(value)
    with destination.open('xb') as stream:
        stream.write(raw)
    try:
        admitted = verify(destination, C.sha(raw), rows=16, enable_raw_kv=True)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination, C.sha(raw), admitted
