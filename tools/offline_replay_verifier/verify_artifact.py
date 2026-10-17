#!/usr/bin/env python3
"""Offline public JSON verifier; never imports or executes numerical/runtime code.

External run/job/artifact metadata is an operator-supplied binding, not fetched
or independently authenticated here. Private tensors and process proofs are
not present and are not replayed. Candidate and frozen source map are pinned.
"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import types
import zipfile

HERE = Path(__file__).resolve().parent
COMMIT = '8ba333c76722b47b681be88612b1c6987e34a5f4'
TREE = 'bd2c110bb63e39a7a3213e6dea5ffb04dc74ab91'
RUN_ID = '39017864296'
JOB_ID = '117353555753'
MAP_SHA = 'cded2ae582a6387cddce8c8bbc38c2e1df46a4038c1d3460bf7566f3273e5228'
BASE = 'candidates/qwen2_resident_matrix/'
PROFILE = 'qwen2-fresh-same-host-m128-combined-v1'
CLAIMS = dict(full_29_node_acceptance=False, rtl_execution=False, hardware_recipe_acceptance=False, old_pass_inherited=False)
FILES = ('summary.json','source_hashes.json','m16_attempt_summary.json','full_m16_summary.json',
         'producer_summary.json','full_m128_summary.json','stage_exits.json','replay_identity.json')
PHASES = ('fresh_producer','independent_m128_verifier','m128_git_worktree','m128_compose','m128_seal','full_m128')
MAX_MEMBER = 2 * 1024 * 1024
MAX_ZIP = 16 * 1024 * 1024
# Exact independently reviewed public-schema source; checked before execution.
IDENTITY_SCHEMA_SHA = 'a3585e722c17cc9f7d61b9bb4ac22b74690a2b471308de4851c8a003871c2c11'


class VerificationError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise VerificationError(code)


def encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(actual, expected, code):
    need(encoded(actual)==encoded(expected),code)


def fields(value, names, code):
    need(type(value) is dict and set(value)==set(names),code)


def digest(value,n=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',value) is not None


def uint(value,maximum=2**63-1,minimum=0):
    return type(value) is int and minimum<=value<=maximum


def seconds(value,maximum=2**53):
    return type(value) in (int,float) and 0<=value<=maximum and math.isfinite(value)


def strict(raw,limit=MAX_MEMBER):
    need(type(raw) is bytes and len(raw)<=limit,'JSON_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'JSON_DUPLICATE')
            result[key]=value
        return result
    def bad(_):
        raise VerificationError('JSON_NONFINITE')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=bad)
        encoded(value)
        return value
    except (UnicodeError,RecursionError,ValueError,TypeError) as error:
        if isinstance(error,VerificationError):raise
        raise VerificationError('JSON_INVALID') from None


def read_safe(path,limit=8*1024*1024):
    path=Path(os.path.abspath(path))
    need(not any(p.is_symlink() for p in (path,*path.parents)),'FILE_ALIAS')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<=before.st_size<=limit,'FILE_TYPE_SIZE')
        parts=[];left=before.st_size
        while left:
            raw=os.read(fd,min(left,1024*1024));need(bool(raw),'FILE_SHORT_READ');parts.append(raw);left-=len(raw)
        after=os.fstat(fd);named=path.stat(follow_symlinks=False)
        sig=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_nlink,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        need(sig(before)==sig(after)==sig(named),'FILE_DRIFT')
        return b''.join(parts)
    finally:os.close(fd)


def zip_members(raw):
    need(type(raw) is bytes and len(raw)<=MAX_ZIP,'ZIP_SIZE')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos=archive.infolist();names=[v.filename for v in infos]
            need(len(names)==len(set(names)) and set(names)==set(FILES),'ZIP_MEMBERS')
            need(sum(item.file_size for item in infos)<=len(FILES)*MAX_MEMBER,'ZIP_TOTAL_SIZE')
            result={}
            for item in infos:
                mode=item.external_attr>>16
                need(not item.is_dir() and not item.flag_bits&1 and stat.S_IFMT(mode) in (0,stat.S_IFREG) and
                     item.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) and
                     0<=item.file_size<=MAX_MEMBER,'ZIP_MEMBER_TYPE_SIZE')
                with archive.open(item) as stream:body=stream.read(MAX_MEMBER)
                need(len(body)==item.file_size,'ZIP_MEMBER_SIZE');result[item.filename]=body
            return result
    except (zipfile.BadZipFile,RuntimeError,NotImplementedError,EOFError):
        raise VerificationError('ZIP_INVALID') from None


def source_map(value,count):
    need(type(value) is dict and len(value)==count,'SOURCE_COUNT')
    for name,value in value.items():
        need(type(name) is str and name and '\\' not in name and '\x00' not in name and not name.startswith('/') and
             all(p not in ('','.','..') for p in name.split('/')) and digest(value),'SOURCE_ENTRY')


def load_sources(freeze):
    freeze=Path(freeze)
    raw=read_safe(freeze/'FULL_SOURCE_HASHES.json');need(sha(raw)==MAP_SHA,'SOURCE_MAP_PIN')
    full=strict(raw);source_map(full,465)
    members=list((freeze/'source').rglob('*'))
    need(not any(p.is_symlink() for p in members) and
         {p.relative_to(freeze/'source').as_posix() for p in members if p.is_file()}==set(full),'SOURCE_MEMBERS')
    for name,value in full.items():need(sha(read_safe(freeze/'source'/name))==value,'SOURCE_BYTES')
    pins={}
    for rows,count,static_count in ((16,390,360),(128,464,423)):
        path=BASE+f'portable_same_host_m{rows}_launch/input-contract.json'
        p=strict(read_safe(freeze/'source'/path));source_map(p['inputs'],count);source_map(p['composed_sources'],static_count)
        need(all(full.get(n)==h for n,h in p['inputs'].items()),'SOURCE_SUBSET');pins[rows]=p
    exact(full,{**pins[128]['inputs'],BASE+'portable_same_host_m128_launch/input-contract.json':full[BASE+'portable_same_host_m128_launch/input-contract.json']},'COMPLETE_SOURCE_CLOSURE')
    return full,pins


TINY_CONTRACT = BASE+'portable_consumer_qualification/input-contract.json'
TINY_CONTRACT_SHA = '287565c9af2ad155fb14a066fc007229b47be0296e73e743dfc479286f894ebf'
COMPILE_PATHS = tuple(BASE+n for n in ('ffn_attention/matrix_numeric.cpp','official_bf16/silu_recipe.cpp',
                                    'transposed_down/numeric_smoke.cpp','ffn_tiles/silu_recipe.cpp'))


def derive_compile_sources(freeze,full,pins):
    # The fresh tiny build compiles its generated source tree. The input
    # contract's generated overrides are authenticated source, not observed
    # artifact exceptions. Both full-run composition maps must agree.
    raw=read_safe(Path(freeze)/'source'/TINY_CONTRACT)
    need(full.get(TINY_CONTRACT)==TINY_CONTRACT_SHA and sha(raw)==TINY_CONTRACT_SHA,'TINY_CONTRACT_PIN')
    tiny=strict(raw);source_map(tiny['source_sha256'],114)
    need(all(full.get(n)==h for n,h in tiny['source_sha256'].items()),'TINY_SOURCE_BINDING')
    exact(tiny['arithmetic_sources'],list(COMPILE_PATHS),'TINY_COMPILE_CLOSURE')
    fields(tiny['generated_sha256'],(BASE+'ffn_attention/matrix_numeric.cpp',BASE+'ffn_attention/matrix_service.py'),'TINY_GENERATED_SET')
    need(all(digest(h) for h in tiny['generated_sha256'].values()),'TINY_GENERATED_DIGEST')
    compiled={**tiny['source_sha256'],**tiny['generated_sha256']}
    selected={n:compiled[n] for n in COMPILE_PATHS}
    for rows in (16,128):
        exact(selected,{n:pins[rows]['composed_sources'][n] for n in COMPILE_PATHS},'COMPOSED_COMPILE_BINDING')
    return selected


def compose(pins,rows):
    static=pins[rows]['composed_sources']
    path=BASE+f'attention_packed_m{rows}_same_host/SOURCE_CONTRACT.json'
    need(path not in static,'DYNAMIC_CONTRACT')
    contract=dict(schema=1,profile=f'qwen2-public-pv16-packed-m{rows}-same-host-v1',git_head=COMMIT,
                  sources=static,scope=f'FRESH_M{rows}_ASSIGNED27_ONLY')
    result={**static,path:sha(encoded(contract))}
    return result,sha(encoded(contract))


def child_result(rows,full):
    v=full['validation']
    child=dict(schema=1,profile=f'qwen2-public-pv16-packed-m{rows}-same-host-v1',
        status=f'VALIDATED_FRESH_M{rows}_CHILD_RESULT',attempt_nonce=full['attempt_nonce'],
        producer_receipt_sha256=full['producer_receipt_sha256'],source_manifest_sha256=v['source_manifest_sha256'],
        summary_sha256=v['summary_sha256'],snapshot_sha256=v['snapshot_sha256'],validation=v,
        parent_must_authenticate_exit_and_cleanup=True,full_29_node_acceptance=False,rtl_execution=False,
        hardware_recipe_acceptance=False,old_pass_inherited=False)
    if rows==128:child['m16_prerequisite_sha256']=full['m16_prerequisite_sha256']
    return child


def resources(value):
    fields(value,('available_disk_bytes','available_memory_bytes','cpu_affinity'),'RESOURCE_FIELDS')
    minimum=dict(available_disk_bytes=8*1024**3,available_memory_bytes=8*1024**3,cpu_affinity=4)
    need(all(uint(value[k],minimum=floor) for k,floor in minimum.items()),'RESOURCE_VALUES')


def timing(value):
    metrics=('wall_seconds','reaped_children_user_cpu_seconds','reaped_children_system_cpu_seconds')
    fixed=dict(schema=1,diagnostic_only=True,acceptance=False,scope='PARENT_RUSAGE_CHILDREN_DELTA')
    fields(value,(*fixed,'status','reason',*metrics),'TIMING_FIELDS')
    exact({k:value[k] for k in fixed},fixed,'TIMING_SCOPE')
    if value['status']=='AVAILABLE':
        need(value['reason'] is None and all(seconds(value[k]) for k in metrics),'TIMING_VALUES')
    else:
        need(value['status']=='UNAVAILABLE' and value['reason'] in
             ('SNAPSHOT_UNAVAILABLE','INVALID_DELTA','MEASUREMENT_UNAVAILABLE') and
             all(value[k] is None for k in metrics),'TIMING_UNAVAILABLE')


def validate_receipts(raws,ci,pins):
    need(set(raws)==set(FILES),'RECEIPT_MEMBERS')
    values={n:strict(raws[n]) for n in FILES}
    for name,value in values.items():
        need(encoded(value)==raws[name],'CANONICAL_RECEIPT')
        if name=='replay_identity.json':continue
        exact(value['ci'],ci,'CI_BINDING');exact(value['schema'],1,'SCHEMA')
        is16=name in ('full_m16_summary.json','m16_attempt_summary.json')
        exact(value['profile'],PROFILE.replace('m128','m16') if is16 else PROFILE,'PROFILE')
        if name!='stage_exits.json':exact(value['claims'],dict(CLAIMS,full_m128_acceptance=False) if is16 else CLAIMS,'CLAIMS')
    summary=values['summary.json'];a16=values['m16_attempt_summary.json'];producer=values['producer_summary.json'];journal=values['stage_exits.json'];source=values['source_hashes.json']
    common=('ci','schema','profile','claims','status','phase','elapsed_seconds','failure_kind','owned_groups_cleanup_complete','resources_before_setup')
    fields(summary,(*common,'full_m16_prerequisite_pass','producer128_qualified','full_m128_assigned27_pass','replay_identity_ready','replay_identity_sha256','replay_identity_failure','producer_failure_observation','full_m128_failure_diagnostic'),'SUMMARY_FIELDS')
    fields(a16,(*common,'producer_qualified','full_m16_assigned27_pass','full_m16_failure_diagnostic','resources_after_setup'),'M16_SUMMARY_FIELDS')
    for value,rows,flags,limit in ((summary,128,('full_m16_prerequisite_pass','producer128_qualified','full_m128_assigned27_pass','replay_identity_ready'),4920),
                                 (a16,16,('producer_qualified','full_m16_assigned27_pass'),1950)):
        exact(value['status'],f'PASS_FRESH_SAME_HOST_M{rows}_ASSIGNED27','SUMMARY_STATUS')
        need(value['phase']=='complete' and value['failure_kind'] is None and seconds(value['elapsed_seconds'],limit),'SUMMARY_COMPLETION')
        need(all(value[k] is True for k in (*flags,'owned_groups_cleanup_complete')),'SUMMARY_FLAGS');resources(value['resources_before_setup'])
    resources(a16['resources_after_setup'])
    need(summary['replay_identity_failure'] is None and summary['producer_failure_observation'] is None and summary['full_m128_failure_diagnostic'] is None and a16['full_m16_failure_diagnostic'] is None,'FAILURE_DIAGNOSTICS')
    need(summary['replay_identity_sha256']==sha(raws['replay_identity.json']),'MANIFEST_PARENT_HASH')
    fields(source,('ci','schema','profile','claims','inputs','composed_sources_template','dynamic_source_contract'),'SOURCE_RECEIPT_FIELDS')
    need(source['dynamic_source_contract'] is True,'DYNAMIC_SOURCE');exact(source['inputs'],pins[128]['inputs'],'ACTUAL_INPUTS');exact(source['composed_sources_template'],pins[128]['composed_sources'],'ACTUAL_TEMPLATE')
    fields(producer,('ci','schema','profile','claims','status','attempt_nonce','producer_manifest_sha256','producer_qualification_sha256','verifier_receipt_sha256','m16_prerequisite_sha256','owned_groups_cleanup_complete','stages'),'PRODUCER_FIELDS')
    need(producer['status']=='PASS_FRESH_M128_PRODUCER' and producer['owned_groups_cleanup_complete'] is True,'PRODUCER_STATUS')
    for key in ('attempt_nonce','producer_manifest_sha256','producer_qualification_sha256','verifier_receipt_sha256','m16_prerequisite_sha256'):need(digest(producer[key]),'PRODUCER_DIGEST')
    source_chains={}
    for rows in (16,128):
        f=values[f'full_m{rows}_summary.json'];sources,contract_sha=compose(pins,rows)
        fields(f,('schema','profile','ci','claims','status','attempt_nonce','producer_receipt_sha256','child_result_sha256','child_pid','child_exit_code','owned_group_cleanup_complete','elapsed_seconds','validation',*(['m16_prerequisite_sha256'] if rows==128 else [])),'FULL_FIELDS')
        need(f['status']==f'PASS_FRESH_SAME_HOST_M{rows}_ASSIGNED27' and f['attempt_nonce']==producer['attempt_nonce'] and uint(f['child_pid'],2**31-1,2) and type(f['child_exit_code']) is int and f['child_exit_code']==0 and f['owned_group_cleanup_complete'] is True and seconds(f['elapsed_seconds'],930 if rows==16 else 2430),'FULL_STATE')
        for key in ('producer_receipt_sha256','child_result_sha256'):need(digest(f[key]),'FULL_DIGEST')
        v=f['validation'];wanted=dict(schema=1,status=f'VALIDATED_FRESH_SAME_HOST_M{rows}_OBSERVED_GATES_ONLY',assigned_official_gates=27,official_observed_stages=28,capture_fields=10,diagnostic_fp32_stages=1,owner_jobs=17,public_completions=21,rows=rows,source_files=len(sources),source_manifest_sha256=sha(encoded(sources)),execution_authenticated_by_this_validator=False,fixed_arithmetic_pass=True,observed_official_gates_pass=True,full_29_node_acceptance=False,hardware_acceptance=False,rtl_acceptance=False)
        fields(v,(*wanted,'summary_sha256','snapshot_sha256'),'VALIDATION_FIELDS');exact({k:v[k] for k in wanted},wanted,'VALIDATION_STATE')
        need(digest(v['summary_sha256']) and digest(v['snapshot_sha256']),'VALIDATION_DIGEST')
        need(sha(encoded(child_result(rows,f)))==f['child_result_sha256'],'CHILD_RESULT_BINDING')
        source_chains[str(rows)]=dict(source_files=len(sources),source_contract_sha256=contract_sha,source_manifest_sha256=sha(encoded(sources)))
    f128=values['full_m128_summary.json']
    need(producer['producer_qualification_sha256']==f128['producer_receipt_sha256'] and producer['m16_prerequisite_sha256']==f128['m16_prerequisite_sha256'],'QUALIFICATION_PREREQUISITE')
    fields(journal,('schema','profile','ci','stages','m16_stage_exits_sha256'),'JOURNAL_FIELDS');need(digest(journal['m16_stage_exits_sha256']),'M16_JOURNAL_DIGEST')
    events=journal['stages'];need(type(events) is list and len(events)==6,'JOURNAL_COUNT');need(type(producer['stages']) is list and len(producer['stages'])==2,'PRODUCER_JOURNAL_COUNT');exact(producer['stages'],events[:2],'PRODUCER_JOURNAL')
    pids=[]
    for name,event in zip(PHASES,events):
        fields(event,('phase','pid','status','observed_exit_code','final_exit_code','owned_group_cleanup_complete','timing_diagnostic'),'EVENT_FIELDS')
        need(event['phase']==name and uint(event['pid'],2**31-1,2) and event['status']=='PASS' and event['owned_group_cleanup_complete'] is True and all(type(event[k]) is int and event[k]==0 for k in ('observed_exit_code','final_exit_code')),'EVENT_STATE')
        timing(event['timing_diagnostic']);pids.append(event['pid'])
    need(events[-1]['pid']==f128['child_pid'],'FULL_CHILD_PID')
    # PID reuse across sequentially reaped stages is permitted; identity safety
    # is proved inside the private source-bound strict helper, not this journal.
    return values,source_chains


def validate_provenance(values,raws,source_chains,full_map):
    manifest=values['replay_identity.json'];p=manifest['provenance'];producer=values['producer_summary.json']
    exact(p['ci'],values['summary.json']['ci'],'MANIFEST_CI')
    need(p['raw_source_map_sha256']==sha(encoded(values['source_hashes.json']['inputs'])),'MANIFEST_RAW_MAP')
    for rows in (16,128):
        f=values[f'full_m{rows}_summary.json'];prefix=f'm{rows}'
        need(p[prefix+'_composed_source_map_sha256']==source_chains[str(rows)]['source_manifest_sha256'] and
             p[prefix+'_summary_sha256']==f['validation']['summary_sha256'] and
             p[prefix+'_snapshot_sha256']==f['validation']['snapshot_sha256'] and
             p[prefix+'_full_receipt_sha256']==sha(raws[f'full_m{rows}_summary.json']),'MANIFEST_FULL_BINDING')
        driver=BASE+('portable_official_producer/' if rows==16 else 'portable_official_producer_m128/')+'driver.py'
        need(p['driver_sha256'][str(rows)]==full_map[driver],'MANIFEST_DRIVER')
    need(p['qualification_sha256']==producer['producer_qualification_sha256'] and
         p['m16_prerequisite_sha256']==producer['m16_prerequisite_sha256'] and
         p['producer_manifest_sha256']['128']==producer['producer_manifest_sha256'] and
         p['verifier_receipt_sha256']==producer['verifier_receipt_sha256'] and
         p['m128_child_result_sha256']==values['full_m128_summary.json']['child_result_sha256'],'MANIFEST_QUALIFICATION_BINDING')
    need(p['emitter_sha256']==full_map[BASE+'portable_same_host_m128_launch/replay_identity.py'] and
         p['wheel_lock_sha256']==full_map[BASE+'portable_official_producer_launch/wheel-lock.json'],'MANIFEST_SOURCE_PINS')


def load_identity_schema():
    need(digest(IDENTITY_SCHEMA_SHA),'VALIDATOR_NOT_FROZEN')
    raw=read_safe(HERE/'identity_schema.py');need(sha(raw)==IDENTITY_SCHEMA_SHA,'VALIDATOR_SOURCE_PIN')
    module=types.ModuleType('checked_public_identity_schema');module.__file__=str(HERE/'identity_schema.py')
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module


def verify(raw_zip,*,artifact_sha256,ci,freeze):
    fields(ci,('commit','run_id','run_attempt'),'CI_FIELDS')
    need(ci['commit']==COMMIT and ci['run_attempt']=='1' and ci['run_id']==RUN_ID,'CI_VALUES')
    need(digest(artifact_sha256) and sha(raw_zip)==artifact_sha256,'ARTIFACT_SHA')
    full,pins=load_sources(freeze);compiled=derive_compile_sources(freeze,full,pins);raws=zip_members(raw_zip)
    values,chains=validate_receipts(raws,ci,pins)
    inventory=load_identity_schema().validate_manifest(values['replay_identity.json'],pins[128]['inputs'],compile_sources=compiled)
    validate_provenance(values,raws,chains,full)
    return dict(schema=1,status='PASS_PUBLIC_REPLAY_IDENTITY_AND_RECEIPT_BINDING',ci=ci,
        artifact_sha256=artifact_sha256,artifact_bytes=len(raw_zip),
        files={n:dict(bytes=len(raws[n]),sha256=sha(raws[n])) for n in FILES},
        full_source_map_sha256=MAP_SHA,raw_source_files=465,source_chains=chains,inventory=inventory,
        combined_compile_source_map_sha256=sha(encoded(compiled)),
        combined_compile_source_derivation='AUTHENTICATED_TINY_SOURCE_PLUS_GENERATED_AND_BOTH_COMPOSED_MAPS',
        stable_identity_sha256=values['replay_identity.json']['identity_sha256'],
        replay_identity_sha256=sha(raws['replay_identity.json']),
        program_reported_replay_identity_ready=True,source_bound_strict_cleanup_required=True,
        numerical_execution_performed=False,private_tensor_bytes_replayed=False,
        private_qualification_bytes_replayed=False,private_process_proofs_replayed=False,
        github_metadata_independently_fetched=False,actual_git_publication_proof_replayed=False,
        publication_closure_required_separately=True,future_job_admission_authority=False,
        full_29_node_acceptance=False,rtl_execution=False,hardware_acceptance=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact',required=True);p.add_argument('--artifact-sha256',required=True)
    p.add_argument('--run-id',required=True);p.add_argument('--job-id',required=True);p.add_argument('--artifact-id',required=True)
    p.add_argument('--freeze',required=True);p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    for item in (a.job_id,a.artifact_id):need(re.fullmatch('[1-9][0-9]*',item) is not None,'EXTERNAL_ID')
    need(a.run_id==RUN_ID and a.job_id==JOB_ID,'ACTUAL_RUN_JOB_BINDING')
    result=verify(read_safe(a.artifact,MAX_ZIP),artifact_sha256=a.artifact_sha256,
        ci=dict(commit=COMMIT,run_id=a.run_id,run_attempt='1'),freeze=a.freeze)
    result['external_metadata']=dict(binding='OPERATOR_SUPPLIED_GITHUB_IDENTIFIERS',repository='liyang53719/hetero_cnn_llm_aha',commit=COMMIT,tree=TREE,job_id=a.job_id,artifact_id=a.artifact_id)
    with Path(a.out).open('xb') as stream:stream.write(encoded(result))
    print(json.dumps(dict(status=result['status'],files=8,stable_identity_sha256=result['stable_identity_sha256']),sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
