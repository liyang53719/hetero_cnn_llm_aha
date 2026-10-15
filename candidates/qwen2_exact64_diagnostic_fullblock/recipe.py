"""Conditionally bind two same-job official captures; DUT readers are metadata-only.

The externally reviewed source policy approves conditions, not future private
payloads. Old observed hash expectations and old FAIL records are untouched.
"""
import argparse
import hashlib
import importlib
import re
import os
from pathlib import Path
import sys
from candidates.qwen2_fullblock_ci_dut import platform_freeze
from candidates.qwen2_official_cpu_platform_reference import recipe as N, pair as P, policy as POLICY, validator as V
from . import closure
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PACKAGE='candidates/qwen2_exact64_diagnostic_fullblock'
AUTH='candidates/qwen2_exact64_diagnostic_fullblock_authorization'
WORK='work/qwen2_exact64_diagnostic_fullblock/ci01'
FROZEN_BINDING=WORK+'/FROZEN_BINDING.json'
REFERENCE=P.WORK+'/new01/bootstrap'
REFERENCE_MANIFEST='BOOTSTRAP_REFERENCE.json'
STATUS='LOCAL_SAME_JOB_PAIR_POLICY_CONDITIONS_SATISFIED_ORACLE_ONLY'
CONTRACT=POLICY.policy()['contract_id']
C=N.C
Rejected,need,same,fields,exact_keys=N.Rejected,N.need,N.same,N.fields,N.exact_keys
encoded,parse,sha,checked,safe_path,stat_only=N.encoded,N.parse,N.sha,N.checked,N.safe_path,N.stat_only
PINS_SHA256=C.PINS_SHA256
# This new contract identity is source policy, never a legacy output digest.
FROZEN_CONTRACT_SHA256=sha(encoded(POLICY.policy()))
NAMES,TOKEN_MAJOR=N.NAMES,N.TOKEN_MAJOR
METADATA_NAMES=frozenset(('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json','WRAPPER_BEFORE.json',
    'WRAPPER_AFTER.json',REFERENCE_MANIFEST,'GO.json','OBSERVATIONS.json','STAGES.jsonl','stdout.log','stderr.log'))
BOUNDARIES=('BOUNDARY_BEFORE.json','BOUNDARY_AFTER.json','WRAPPER_BEFORE.json','WRAPPER_AFTER.json')
CLOSURE_ENV='QWEN2_EXACT64_DIAGNOSTIC_SOURCE_CLOSURE_SHA256'
BINDING_ENV='QWEN2_EXACT64_DIAGNOSTIC_BINDING_SHA256'
load_pins,metadata_check=N.load_pins,N.metadata_check


def identity(path):
    h=hashlib.sha256();size=0
    with path.open('rb') as stream:
        while chunk:=stream.read(1<<20):h.update(chunk);size+=len(chunk)
    return dict(bytes=size,sha256=h.hexdigest())


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) and value!='0'*64,'explicit SHA256 required')
    return value


def _platform_observation():
    observed=platform_freeze.observe(execute=True)
    platform_freeze.verify_same(observed)
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



def source_manifest(root=ROOT):
    need(root==ROOT,'fixed source root')
    closure.source_manifest(root)
    return identity(HERE/'SOURCE_MANIFEST.json')


def source_check(root,pins):
    result=N.source_check(root,pins)
    return {**result,'dut_source_manifest':source_manifest(root),'oracle_payload_read':False}


def execution_context():
    expected=digest(os.getenv(CLOSURE_ENV))
    actual=closure.digest(ROOT);need(actual==expected,'reviewed source drift')
    platform=_platform_observation();native=_native_binding()
    from . import exact64_artifact
    exact64=exact64_artifact.verify()
    need(same(platform,_platform_observation()) and closure.digest(ROOT)==actual,'execution context drift')
    return dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED',
        source_closure_sha256=actual,source_manifest=source_manifest(),platform_files=platform,
        platform_binding_scope='CROSS_PROCESS_FILE_IDENTITIES_ONLY',exact64_artifact=exact64,**native)


def _common_metadata(pins,context):
    metadata=source_check(ROOT,pins)
    native={}
    for name,spec in pins['runtime_native_files'].items():
        path=Path(spec['path']) if Path(spec['path']).is_absolute() else safe_path(ROOT,spec['path'])
        native[name]=dict(path=spec['path'],**identity(path))
        need(same(native[name],spec),'same actual runtime native bytes')
    return dict(source_closure_sha256=V.source_digest(ROOT),source_manifest=N.source_manifest(),
        pins=identity(safe_path(ROOT,C.BINDING)),effective_pins_sha256=sha(encoded(pins)),
        sources={p:{k:s[k] for k in ('bytes','sha256')} for p,s in pins['sources'].items()},
        raw13={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in pins['raw_tensors']},
        native_files=native,input_proofs=metadata['proof_files'],raw_support={},
        historical_receipts_revalidated=False,
        platform_files={k:context['platform_files'][k] for k in ('python','libpython')})


def _record(run,receipt):
    out=P.run_out(run)
    return dict(run=run,reference_directory=str(out.relative_to(ROOT)),
        outputs=receipt['outputs'],common=receipt['common'],
        inventory=receipt['inventory'],guard=receipt['guard'])


def _metadata_records(pins,binding,context):
    """Open only exact bounded metadata; exported payloads are stat-only here."""
    need(same(binding['context'],context),'bound current DUT/platform/native/source drift')
    common=_common_metadata(pins,context)
    need(len(binding['captures'])==2,'two capture records')
    for run,record in zip(P.RUNS,binding['captures']):
        out=P.run_out(run)
        exact_keys(record,('run','reference_directory','outputs','common','inventory','guard'),'capture binding')
        need(record['run']==run and record['reference_directory']==str(out.relative_to(ROOT)), 'fixed fresh pair run')
        need(same(record['common'],common),'same reference source/raw/native/platform/input contract')
        names={n+'.f32le' for n in NAMES}|{'mask.bf16le'}|set(METADATA_NAMES)|{'SEAL.json'}
        exact_keys(record['inventory'],names,'pair inventory')
        need({p.name for p in out.iterdir()}==names,'pair output inventory drift')
        docs={}
        for name in METADATA_NAMES|{'SEAL.json'}:
            spec=record['inventory'][name]
            need(type(spec['bytes']) is int and 0<=spec['bytes']<=262144,'bounded metadata')
            raw=checked(ROOT,str((out/name).relative_to(ROOT)),spec)
            if name.endswith('.json'):docs[name]=parse(raw)
        seal=docs['SEAL.json'];manifest=docs[REFERENCE_MANIFEST];obs=docs['OBSERVATIONS.json']
        fields(seal,dict(schema=1,status=P.SEALED,mode='bootstrap',run_id=run,manifest=REFERENCE_MANIFEST,
            source_manifest=common['source_manifest'],numerical_acceptance_claimed=False,dut_executed=False,retries=0),'fresh seal')
        exact_keys(seal,('schema','status','mode','run_id','manifest','files','resources','source_manifest',
            'numerical_acceptance_claimed','dut_executed','retries'),'sealed record')
        need(same(seal['files'],{n:s for n,s in record['inventory'].items() if n!='SEAL.json'}),'sealed file identities')
        before=dict(common,external_certificate_sha256=binding['reference_certificates'][run])
        need(all(same(docs[name],before) for name in BOUNDARIES),'reference four-boundary drift')
        P.observations_checked(N,pins,obs,before)
        exact_keys(manifest,set(obs)|{'resources','wrapper_boundary_unchanged','go_identity'},'manifest')
        need(same({k:manifest[k] for k in obs},obs) and manifest['wrapper_boundary_unchanged'] is True and
            same(manifest['resources'],seal['resources']),'manifest/seal binding')
        P.resources_checked(seal['resources'],record['inventory'])
        need(same(record['outputs'],obs['outputs']),'bound actual output metadata drift')
        for name,spec in record['outputs'].items():
            need(same(record['inventory'][name+'.f32le'],{k:spec[k] for k in ('bytes','sha256')}),'observed payload identity')
        for name in names-set(METADATA_NAMES)-{'SEAL.json'}:
            stat_only(ROOT,str((out/name).relative_to(ROOT)),record['inventory'][name]['bytes'])
        guard=P.guard_log(run)
        need(same(identity(guard),record['guard']),'guard result drift')
    need(same(binding['captures'][0]['outputs'],binding['captures'][1]['outputs']),'pair output/layout identity drift')
    for path,spec in binding['metadata_files'].items():
        checked(ROOT,path,spec)
    return binding['captures'][0]


def _read_binding():
    path=safe_path(ROOT,FROZEN_BINDING)
    need(0<path.stat().st_size<=262144,'bounded new local oracle binding')
    raw=path.read_bytes();need(sha(raw)==digest(os.getenv(BINDING_ENV)),'validator-returned binding identity drift')
    value=parse(raw)
    exact_keys(value,('schema','status','contract_id','reference_directory','bootstrap_seal','bootstrap_manifest',
        'captures','reference_certificates','metadata_files','input_metadata','raw13','producer14','runtime_native_files',
        'effective_pins_sha256','context','pair_payload_bytes_equal','all29_payloads_rehashed','mask_payload_rehashed',
        'raw13_payloads_rehashed','producer14_payloads_rehashed','policy_conditions_satisfied',
        'bootstrap_status_preserved','independent_new_numeric_review_claimed','old_pass_inherited',
        'numerical_acceptance_claimed','dut_executed'),'new binding exact schema')
    fields(value,dict(schema=1,status=STATUS,contract_id=CONTRACT,reference_directory=REFERENCE,
        pair_payload_bytes_equal=True,all29_payloads_rehashed=True,mask_payload_rehashed=True,
        raw13_payloads_rehashed=True,producer14_payloads_rehashed=True,policy_conditions_satisfied=True,
        bootstrap_status_preserved=True,independent_new_numeric_review_claimed=False,old_pass_inherited=False,
        numerical_acceptance_claimed=False,dut_executed=False),'source-policy conditional local freeze')
    return value


def validate_bootstrap_metadata(pins=None,*,seal_sha256):
    pins=load_pins() if pins is None else pins
    need(same(pins,load_pins()),'same current input pins')
    value=_read_binding();need(value['bootstrap_seal']['sha256']==digest(seal_sha256),'fixed first capture seal')
    record=_metadata_records(pins,value,execution_context())
    manifest=parse(checked(ROOT,value['bootstrap_manifest']['path'],value['bootstrap_manifest']))
    return dict(outputs=record['outputs'],manifest=manifest,bootstrap_manifest=value['bootstrap_manifest'],
        bootstrap_seal=value['bootstrap_seal'],policy_conditions_satisfied=True,oracle_payload_read=False)


def require_frozen_references(pins,root=ROOT):
    need(root==ROOT and same(pins,load_pins()),'fixed current input contract')
    value=_read_binding()
    record=validate_bootstrap_metadata(pins,seal_sha256=value['bootstrap_seal']['sha256'])
    return dict(status=STATUS,outputs=record['outputs'],bootstrap_manifest=value['bootstrap_manifest'],
        bootstrap_seal=value['bootstrap_seal'],binding=dict(path=FROZEN_BINDING,**identity(safe_path(ROOT,FROZEN_BINDING))),
        bootstrap_status_preserved=True,policy_conditions_satisfied=True,old_pass_inherited=False,oracle_payload_read=False)


def bind_pair(*,execute=False):
    if not execute:return dict(status='NOT_EXECUTED',dut_executed=False)
    from . import job
    review=job.authorize();job.reference_authority(review)
    need(ROOT==C.CI_ROOT,'fixed CI bind root')
    need(not any(n.split('.')[0] in ('torch','numpy','transformers') for n in sys.modules),'fresh stdlib binding process')
    target=safe_path(ROOT,FROZEN_BINDING);need(not target.exists(),'single immutable binding; never overwrite')
    pins=load_pins();context=execution_context()
    receipts=[P.validate_run(run) for run in P.RUNS]
    equal=P.compare_pair(receipts)
    need(equal['status']=='NEW_REFERENCE_PAIR_EQUAL_PENDING_REVIEW' and equal['checked_outputs']==equal['equal_outputs']==29,
        'both complete sealed fresh captures must byte-match')
    common=_common_metadata(pins,context)
    need(all(same(receipt['common'],common) for receipt in receipts),'same current source/raw/native/platform')
    for spec in list(pins['raw_tensors'])+list(pins['producer_roles'].values()):
        need(same(identity(safe_path(ROOT,spec['path'])),{k:spec[k] for k in ('bytes','sha256')}),'fresh raw13/typed14 bytes')
    captures=[_record(run,receipt) for run,receipt in zip(P.RUNS,receipts)]
    metadata_files={}
    for run,record in zip(P.RUNS,captures):
        for name in METADATA_NAMES|{'SEAL.json'}:
            metadata_files[record['reference_directory']+'/'+name]=record['inventory'][name]
        metadata_files[str(P.guard_log(run).relative_to(ROOT))]=record['guard']
        for name in ('SOURCE_CERTIFICATE.json','EXTERNAL_PINS.json'):
            path=AUTH+'/'+run+'/'+name;metadata_files[path]=identity(safe_path(ROOT,path))
    review_path=AUTH+'/DUT_REVIEW.json';metadata_files[review_path]=identity(safe_path(ROOT,review_path))
    first=captures[0]
    value=dict(schema=1,status=STATUS,contract_id=CONTRACT,reference_directory=REFERENCE,
        bootstrap_seal=dict(path=REFERENCE+'/SEAL.json',**first['inventory']['SEAL.json']),
        bootstrap_manifest=dict(path=REFERENCE+'/'+REFERENCE_MANIFEST,**first['inventory'][REFERENCE_MANIFEST]),
        captures=captures,reference_certificates=review['reference_certificates'],metadata_files=metadata_files,
        input_metadata=pins['input_metadata'],raw13=common['raw13'],
        producer14={s['path']:{k:s[k] for k in ('bytes','sha256')} for s in pins['producer_roles'].values()},
        runtime_native_files=pins['runtime_native_files'],effective_pins_sha256=sha(encoded(pins)),context=context,
        pair_payload_bytes_equal=True,all29_payloads_rehashed=True,mask_payload_rehashed=True,
        raw13_payloads_rehashed=True,producer14_payloads_rehashed=True,policy_conditions_satisfied=True,
        bootstrap_status_preserved=True,independent_new_numeric_review_claimed=False,old_pass_inherited=False,
        numerical_acceptance_claimed=False,dut_executed=False)
    _metadata_records(pins,value,context)
    need(same(context,execution_context()),'binding context changed')
    raw=encoded(value);need(len(raw)<=262144,'bounded binding')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(raw)
    need(target.read_bytes()==raw,'binding exact write/readback')
    return dict(status=STATUS,reference_outputs_checked=29,policy_conditions_satisfied=True,
        binding_sha256=sha(raw),numerical_acceptance_claimed=False,dut_executed=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.parse_args(argv)
    print('{"status":"NOT_EXECUTED","dut_executed":false,"oracle_payload_read":false}')
    return 0
if __name__=='__main__':raise SystemExit(main())
