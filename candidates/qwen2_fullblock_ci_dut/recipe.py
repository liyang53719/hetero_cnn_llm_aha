"""Bind a fresh CI bootstrap to source expectations without rewriting its history.

Default is cold. Oracle binding is a separate pre-DUT payload verification step.
The actual-process metadata reader never opens raw, typed or reference operands.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PACKAGE='candidates/qwen2_fullblock_ci_dut'
WORK='work/qwen2_fullblock_ci_dut/ci01'
FROZEN_BINDING=WORK+'/FROZEN_BINDING.json'
REFERENCE='work/qwen2_fullblock_ci_reference/ci01/bootstrap'
REFERENCE_MANIFEST='BOOTSTRAP_REFERENCE.json'
CI_SOURCE='candidates/qwen2_fullblock_ci_reference/recipe.py'
CI_SOURCE_SHA='a265c289e6a85ab75796f5c8701e286eacc9d3d1d99bc6bf6254f4f6727ef7eb'
CI_MANIFEST='candidates/qwen2_fullblock_ci_reference/SOURCE_MANIFEST.json'
CI_MANIFEST_SHA='7b9ad01ea6c58f1ab2114a587f3cece558a877a07a6aa64558b149fbc82b0d14'
CLOSURE_ENV='QWEN2_DUT_SOURCE_CLOSURE_SHA256'
BINDING_ENV='QWEN2_DUT_FROZEN_BINDING_SHA256'
METADATA_NAMES=frozenset(('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json','WRAPPER_BEFORE.json',
    'WRAPPER_AFTER.json',REFERENCE_MANIFEST,'GO.json','OBSERVATIONS.json','STAGES.jsonl','stdout.log','stderr.log'))
BOUNDARIES=('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json','WRAPPER_BEFORE.json','WRAPPER_AFTER.json')
STATUS='LOCAL_FRESH_BOOTSTRAP_EXACT_SOURCE_MATCH_ORACLE_ONLY'

def _load_ci_recipe():
    path=ROOT/CI_SOURCE
    raw=path.read_bytes()
    if path.resolve()!=path or hashlib.sha256(raw).hexdigest()!=CI_SOURCE_SHA:
        raise ValueError('unchanged CI reference recipe identity required')
    manifest=(ROOT/CI_MANIFEST).read_bytes()
    if hashlib.sha256(manifest).hexdigest()!=CI_MANIFEST_SHA:
        raise ValueError('unchanged CI reference manifest identity required')
    # Verify the dependency map before imported code can use it to load anything.
    inventory=json.loads(manifest)['files']
    directory=(ROOT/CI_MANIFEST).parent
    for name,expected in inventory.items():
        source=directory/name
        data=source.read_bytes()
        if source.resolve()!=source or len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
            raise ValueError('unchanged CI reference package dependency identity required')
    # Execute exactly checked source bytes; no global recipe/lifecycle rebinding.
    spec=importlib.util.spec_from_file_location('_ci_dut_original_reference',path)
    module=importlib.util.module_from_spec(spec)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
C=_load_ci_recipe()
Rejected,need,same,fields,exact_keys=C.Rejected,C.need,C.same,C.fields,C.exact_keys
encoded,parse,sha,checked,safe_path,stat_only=C.encoded,C.parse,C.sha,C.checked,C.safe_path,C.stat_only
PINS_SHA256=C.PINS_SHA256
FROZEN_CONTRACT_SHA256=C.O.FROZEN_CONTRACT_SHA256
FROZEN_CONTRACT_FILE=C.O.FROZEN_CONTRACT_FILE
NAMES,TOKEN_MAJOR=C.NAMES,C.TOKEN_MAJOR
validate_observations,require_supported_python=C.validate_observations,C.require_supported_python
MODEL_SOURCE,ACTIVATION_SOURCE=C.MODEL_SOURCE,C.ACTIVATION_SOURCE


def identity(path):
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while chunk:=stream.read(1<<20):h.update(chunk);size+=len(chunk)
    return dict(bytes=size,sha256=h.hexdigest())


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) and value!='0'*64,'explicit SHA256 required')
    return value


def load_pins(root=ROOT):return C.load_pins(root)
def metadata_check(root,pins):return C.metadata_check(root,pins)
def reference_source_manifest(root=ROOT):return C.source_manifest(root)


def source_manifest(root=ROOT):
    need(root==ROOT,'fixed DUT source root')
    path=safe_path(root,PACKAGE+'/SOURCE_MANIFEST.json')
    manifest=parse(path.read_bytes())
    exact_keys(manifest,('schema','files'),'DUT source manifest')
    need(type(manifest['schema']) is int and manifest['schema']==1,'DUT source schema')
    present={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()}
    need(present==set(manifest['files'])|{'SOURCE_MANIFEST.json'},'exact DUT source inventory')
    for name,spec in manifest['files'].items():checked(root,PACKAGE+'/'+name,spec)
    return identity(path)


def source_check(root,pins):
    own=source_manifest(root)
    need(same(pins,load_pins(root)),'effective CI reference pins unchanged')
    result=C.source_check(root,pins)
    return {**result,'dut_source_manifest':own,'oracle_payload_read':False}


def read13(root=ROOT,pins=None):
    """Explicit raw payload reader for callers whose gate permits raw input reads."""
    pins=load_pins(root) if pins is None else pins
    need(same(pins,load_pins(root)),'raw13 fixed effective pins')
    return {s['local_name']:checked(root,s['path'],s) for s in pins['raw_tensors']}


def _package_module(directory,filename,name):
    path=safe_path(ROOT,directory+'/'+filename+'.py')
    spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    old_path=list(sys.path)
    try:
        sys.path.insert(0,str(ROOT))
        spec.loader.exec_module(module)
    finally:sys.path[:]=old_path
    return module


def bootstrap_source_closure():
    return _package_module('candidates/qwen2_fullblock_ci_execution','closure','_dut_bootstrap_closure').digest(ROOT)


def _platform_observation():
    platform=_package_module(PACKAGE,'platform_freeze','_dut_platform_freeze')
    observed=platform.observe(execute=True)
    platform.verify_same(observed)
    # PID belongs to this observation process, not a cross-process file freeze.
    return {k:observed[k] for k in ('python','libpython','python_version','scope')}


def _native_binding():
    directory='work/qwen2_fullblock_ci_native/ci01'
    receipt_path=safe_path(ROOT,directory+'/official_bf16_compile.json')
    library=safe_path(ROOT,directory+'/official_bf16_matrix_silu.so')
    need(receipt_path.stat().st_size<=262144,'bounded current native receipt')
    before=identity(receipt_path)
    receipt=parse(receipt_path.read_bytes())
    need(receipt.get('library')==str(library),'native ELF must be current fixed build')
    old_path=list(sys.path)
    try:
        sys.path.insert(0,str(ROOT))
        dense=importlib.import_module('candidates.qwen2_resident_matrix.official_bf16.dense_silu')
    finally:sys.path[:]=old_path
    need(Path(dense.__file__).resolve()==ROOT/'candidates/qwen2_resident_matrix/official_bf16/dense_silu.py',
         'native verifier source origin')
    # Source/compiler/invocation/ELF verification only; never CDLL or arithmetic.
    verified=dense.verify_library(receipt_path)
    need(same(receipt,verified) and same(before,identity(receipt_path)),'current native receipt changed')
    elf=identity(library)
    need(elf['sha256']==verified['library_sha256'],'current native ELF identity')
    return dict(native_receipt=dict(path=str(receipt_path.relative_to(ROOT)),**before),
                native_library=dict(path=str(library.relative_to(ROOT)),**elf))


def execution_context():
    """Recheck current source, compiled ELF and actually mapped libpython identity."""
    expected=digest(os.getenv(CLOSURE_ENV))
    closure=_package_module(PACKAGE,'closure','_dut_source_closure')
    actual=closure.digest(ROOT)
    need(actual==expected,'reviewed DUT source closure drift')
    platform=_platform_observation()
    native=_native_binding()
    need(same(platform,_platform_observation()) and actual==closure.digest(ROOT),'execution context changed')
    return dict(source_closure_sha256=actual,source_manifest=source_manifest(),
        platform_files=platform,platform_binding_scope='CROSS_PROCESS_FILE_IDENTITIES_ONLY',**native)


def source_expectations(pins):
    """Read only existing tracked source expectations, never old work evidence."""
    path=safe_path(ROOT,FROZEN_CONTRACT_FILE)
    raw=path.read_bytes()
    need(sha(raw)==FROZEN_CONTRACT_SHA256,'tracked fixed expectation source drift')
    value=parse(raw)
    fields(value,dict(schema=1,status='FROZEN_FROM_INDEPENDENT_REVIEW'),'source expectation metadata')
    validate_observations(value['outputs'],pins)
    return value['outputs'],dict(path=FROZEN_CONTRACT_FILE,bytes=len(raw),sha256=sha(raw))


def validate_bootstrap_documents(pins,expected_outputs,seal,manifest,boundaries,*,reference_source,bootstrap_closure,observed_binding,proof_files):
    """Pure, strict validation. A matching bootstrap stays a bootstrap."""
    fields(seal,dict(schema=1,status='SEALED_BOOTSTRAP_OBSERVATIONS_UNACCEPTED',mode='bootstrap',run_id='ci01',
        manifest=REFERENCE_MANIFEST,numerical_acceptance_claimed=False,dut_executed=False,retries=0), 'fresh bootstrap seal')
    fields(manifest,dict(status='BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT',stage='bootstrap',
        source_pins_sha256=PINS_SHA256,official_model_ast_nodes=38,official_activation_ast_nodes=14,
        official_ast_subset_executed=True,prior18_fresh_hash_matches=True,frozen29_hash_matches=None,
        wrapper_boundary_unchanged=True,dut_executed=False,actual_or_typed_input_read=False,
        materialized_producer_payload_read=False,saved_reference_payload_read=False,
        numerical_acceptance_claimed=False,old_pass_inherited=False,full_official_forward_executed=False,
        dynamic_cache_executed=False,full_29_node_acceptance=False),'honest fresh bootstrap manifest')
    validate_observations(manifest['outputs'],pins)
    need(same(manifest['outputs'],expected_outputs),'fresh full29 differs from source expectations')
    need(same(seal['source_manifest'],reference_source) and same(manifest['source_manifest'],reference_source),'bootstrap reference source identity')
    resource=seal['resources']
    need(same(resource,manifest['resources']),'bootstrap resource identity')
    fields(resource,dict(returncode=0,limit_reason=None,rss_limit_bytes=1536*(1<<20),
        overall_wall_limit_seconds=120,external_watchdog_deadline_seconds=122,
        independent_overall_watchdog_enabled=True,cleanup_pids=[]),'successful bounded bootstrap')
    need(resource['descendant_cleanup']['remaining_descendants']=={},'bootstrap descendants not drained')
    need(type(resource['overall_elapsed_seconds']) in (int,float) and 0<=resource['overall_elapsed_seconds']<=122,'bootstrap elapsed budget')
    need(type(resource['peak_sampled_process_tree_rss_bytes']) is int and
        0<=resource['peak_sampled_process_tree_rss_bytes']<=1536*(1<<20),'bootstrap RSS budget')
    expected_files={n+'.f32le' for n in NAMES}|{'mask.bf16le'}|set(METADATA_NAMES)
    exact_keys(seal['files'],expected_files,'bootstrap exact sealed inventory')
    need(set(boundaries)==set(BOUNDARIES),'four bootstrap boundaries')
    before=boundaries[BOUNDARIES[0]]
    need(all(same(before,v) for v in boundaries.values()),'bootstrap boundary drift')
    fields(before,dict(source_manifest=reference_source,pins=observed_binding,
        effective_pins_sha256=sha(encoded(pins)),source_closure_sha256=bootstrap_closure,
        historical_receipts_revalidated=False,native_files=pins['runtime_native_files'],
        raw13={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in pins['raw_tensors']},
        sources={p:{k:s[k] for k in ('bytes','sha256')} for p,s in pins['sources'].items()},
        input_proofs=proof_files,raw_support={}), 'bootstrap current input/runtime/source provenance')
    expected_certificate=os.environ.get('QWEN2_BOOTSTRAP_CERTIFICATE_SHA256')
    digest(expected_certificate)
    need(before['external_certificate_sha256']==expected_certificate,'same independently reviewed reference certificate')
    fields(manifest['boundary'],dict(unchanged=True,
        before_sha256=seal['files']['BOUNDARY_BEFORE.json']['sha256'],
        after_sha256=seal['files']['BOUNDARY_AFTER.json']['sha256']),'bootstrap boundary seal identities')
    for name,spec in manifest['outputs'].items():
        need(same(seal['files'][name+'.f32le'],{k:spec[k] for k in ('bytes','sha256')}),'bootstrap payload identity: '+name)
    need(same(seal['files']['mask.bf16le'],dict(bytes=pins['mask_contract']['native_bytes'],sha256=pins['mask_contract']['native_sha256'])),'bootstrap mask sidecar identity')
    return dict(status=STATUS,outputs=manifest['outputs'],bootstrap_status_preserved=True,
        fixed_expectations_match=True,old_pass_inherited=False,dut_executed=False)


def validate_bootstrap_metadata(pins=None,*,seal_sha256):
    """Metadata and stat only; safe before actual-process reference-read gate opens."""
    pins=load_pins() if pins is None else pins
    need(same(pins,load_pins()),'bootstrap reader requires current CI pins')
    digest(seal_sha256)
    metadata=source_check(ROOT,pins)
    expected,expectation_spec=source_expectations(pins)
    directory=safe_path(ROOT,REFERENCE)
    seal_path=safe_path(ROOT,REFERENCE+'/SEAL.json')
    need(seal_path.stat().st_size<=262144,'bounded bootstrap seal')
    raw=seal_path.read_bytes();need(sha(raw)==seal_sha256,'explicit fresh bootstrap seal digest')
    seal=parse(raw)
    need(type(seal.get('files')) is dict,'sealed bootstrap inventory')
    expected_files={n+'.f32le' for n in NAMES}|{'mask.bf16le'}|set(METADATA_NAMES)
    exact_keys(seal['files'],expected_files,'bootstrap exact inventory before reads')
    need({p.name for p in directory.iterdir()}==expected_files|{'SEAL.json'},'bootstrap directory inventory')
    documents={}
    for name in METADATA_NAMES:
        spec=seal['files'][name]
        need(type(spec['bytes']) is int and 0<=spec['bytes']<=262144,'bounded bootstrap metadata')
        content=checked(ROOT,REFERENCE+'/'+name,spec)
        if name.endswith('.json'):documents[name]=parse(content)
    manifest=documents[REFERENCE_MANIFEST]
    need(same(documents['OBSERVATIONS.json'],{k:v for k,v in manifest.items()
        if k not in ('resources','wrapper_boundary_unchanged','go_identity')}),'bootstrap observations/manifest mismatch')
    go=documents['GO.json']
    exact_keys(go,('receipt','content'),'bootstrap wrapper go record')
    need(same(go['receipt'],manifest['go_identity']),'bootstrap admitted go identity')
    fields(go['receipt'],dict(path='work/qwen2_fullblock_ci_reference/ci01/GO.json',
        bytes=len(encoded(go['content'])),sha256=sha(encoded(go['content']))),'bootstrap go bytes')
    fields(go['content'],dict(schema=1,action='single-bootstrap',run_id='ci01',
        source_manifest=reference_source_manifest(),maximum_invocations=1,no_retry=True,
        exclusive_numeric_slot=True,issued_by='root-source-policy-issuer'),'bootstrap single-go scope')
    result=validate_bootstrap_documents(pins,expected,seal,documents[REFERENCE_MANIFEST],
        {n:documents[n] for n in BOUNDARIES},reference_source=reference_source_manifest(),
        bootstrap_closure=bootstrap_source_closure(),observed_binding=identity(safe_path(ROOT,C.BINDING)),
        proof_files=metadata['proof_files'])
    for name in expected_files-set(METADATA_NAMES):stat_only(ROOT,REFERENCE+'/'+name,seal['files'][name]['bytes'])
    need(sum(s['bytes'] for s in seal['files'].values())+len(raw)<=pins['budget']['per_capture_cap_bytes'],'bootstrap directory budget')
    return {**result,'seal':seal,'manifest':documents[REFERENCE_MANIFEST],
        'bootstrap_seal':dict(path=REFERENCE+'/SEAL.json',bytes=len(raw),sha256=seal_sha256),
        'bootstrap_manifest':dict(path=REFERENCE+'/'+REFERENCE_MANIFEST,**seal['files'][REFERENCE_MANIFEST]),
        'source_expectations':expectation_spec,'oracle_payload_read':False}


def _binding_record(pins,record,context):
    return dict(schema=1,status=STATUS,reference_directory=REFERENCE,
        bootstrap_seal=record['bootstrap_seal'],bootstrap_manifest=record['bootstrap_manifest'],
        source_expectations=record['source_expectations'],outputs_sha256=sha(encoded(record['outputs'])),
        input_metadata=pins['input_metadata'],raw13={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in pins['raw_tensors']},
        producer14={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in pins['producer_roles'].values()},
        runtime_native_files=pins['runtime_native_files'],effective_pins_sha256=sha(encoded(pins)),
        context=context,all29_payloads_rehashed=True,mask_payload_rehashed=True,
        raw13_payloads_rehashed=True,producer14_payloads_rehashed=True,
        fixed_expectations_match=True,bootstrap_status_preserved=True,
        independent_new_numeric_review_claimed=False,old_pass_inherited=False,
        numerical_acceptance_claimed=False,dut_executed=False)


def bind_bootstrap(*,seal_sha256,execute=False):
    if not execute:return dict(status='NOT_EXECUTED',dut_executed=False)
    need(ROOT==C.CI_ROOT,'exact CI binding root')
    need(not any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules),'fresh stdlib oracle-binding process')
    target=safe_path(ROOT,FROZEN_BINDING)
    need(not target.exists(),'new oracle binding only; never overwrite')
    pins=load_pins();context=execution_context()
    record=validate_bootstrap_metadata(pins,seal_sha256=seal_sha256)
    for name in sorted(record['seal']['files']):
        spec=record['seal']['files'][name]
        need(same(identity(safe_path(ROOT,REFERENCE+'/'+name)),spec),'fresh bootstrap full sealed payload hash: '+name)
    for spec in list(pins['raw_tensors'])+list(pins['producer_roles'].values()):
        need(same(identity(safe_path(ROOT,spec['path'])),{k:spec[k] for k in ('bytes','sha256')}),'current raw13/typed14 binding hash')
    after=validate_bootstrap_metadata(pins,seal_sha256=seal_sha256)
    need(same(after,record) and same(context,execution_context()),'oracle binding boundary drift')
    value=_binding_record(pins,record,context)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(encoded(value))
    return dict(status=STATUS,reference_outputs_checked=29,bootstrap_status_preserved=True,
        binding_sha256=identity(target)['sha256'],numerical_acceptance_claimed=False,dut_executed=False)


def require_frozen_references(pins,root=ROOT):
    """Gate compatibility API: validates new local binding; never reads oracle payloads."""
    need(root==ROOT and same(pins,load_pins(root)),'fixed CI oracle pins/root')
    path=safe_path(root,FROZEN_BINDING)
    need(path.stat().st_size<=262144,'bounded new oracle binding')
    raw=path.read_bytes()
    need(sha(raw)==digest(os.getenv(BINDING_ENV)),'launch-pinned local oracle binding drift')
    binding=parse(raw)
    fields(binding,dict(schema=1,status=STATUS),'new local bootstrap oracle binding')
    record=validate_bootstrap_metadata(pins,seal_sha256=binding['bootstrap_seal']['sha256'])
    need(same(binding,_binding_record(pins,record,execution_context())),'local oracle binding drift')
    return dict(status=STATUS,outputs=record['outputs'],bootstrap_manifest=record['bootstrap_manifest'],
        bootstrap_seal=record['bootstrap_seal'],binding=dict(path=FROZEN_BINDING,**identity(path)),
        bootstrap_status_preserved=True,fixed_expectations_match=True,old_pass_inherited=False,
        oracle_payload_read=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bind-bootstrap',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--seal-sha256')
    a=p.parse_args(argv)
    if a.bind_bootstrap:
        need(a.execute and a.seal_sha256,'explicit binding action and fresh seal digest required')
        result=bind_bootstrap(seal_sha256=a.seal_sha256,execute=True)
    else:
        need(not a.execute and a.seal_sha256 is None,'cold default flags')
        result=dict(status='NOT_EXECUTED',dut_executed=False,oracle_payload_read=False)
    print(json.dumps(result,sort_keys=True))
    return 0
if __name__=='__main__':raise SystemExit(main())
