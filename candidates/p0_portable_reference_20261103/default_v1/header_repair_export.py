"""Fixed three-JSON boundary for one header-only transport diagnosis."""
import json
import os
from pathlib import Path
import stat
from safe_export import exact, enum, integer, number, digest, boolean, require, canonical, _decode, _open_dir
from fixture_gate import sha, strict_json

FAILED_RUN = 41720209902
ID = 'P0_QWEN2_HEADER_REPAIR_41720209902_V1'
FILES = ('RESULT.json','CHECKS.json','HOST_RESOURCES.json')
HEADER_SHA = '124516afba769374e2b948e185dd3e9203e2412daaef3f2ccf7bdbaca0f88987'
POINTS = ('NOT_STARTED','REQUEST','REDIRECT','STATUS','RANGE','LENGTH','ENCODING','READ','BODY_SIZE','HEADER_HASH','HEADER_PREFIX','HEADER_JSON','SEMANTIC','COMPLETE')
CODES = ('NONE','URL_POLICY','REDIRECT_LIMIT','HTTP_ERROR','HTTP_STATUS','CONTENT_RANGE','CONTENT_LENGTH','CONTENT_ENCODING','BODY_SIZE','HEADER_HASH','HEADER_PREFIX','HEADER_JSON','SEMANTIC','TRANSPORT','INPUT_PIN','OUTPUT')
HOSTS = ('HUGGINGFACE','HF_US_AWS_CDN','HF_CAS_BRIDGE','HF_LFS','HF_LFS_US1','HF_CDN_LFS','HF_CDN_LFS_US1','OTHER')
COMPLETE = 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'
DIAG_FIELDS = ('schema','status','failure_point','failure_code','http_status','final_host','response_bytes','observed_header_sha256','header_sha_equal','geometry_checked','redirect_count')
RESULT_FIELDS = ('schema','candidate_id','status','reason','source_manifest_sha256','failed_run_id','run_id','header_exact','metadata_checked','runtime_installed','weights_downloaded','reference_executed','hardware_executed','raw_payloads_uploaded','original_failure_cause_proven')
HOST_FIELDS = ('schema','architecture','python_version','python_sha256','cpu_affinity_count','cpu_evidence_sha256','initial_free_bytes','minimum_free_bytes','effective_memory_available_bytes','wall_budget_seconds','cpu_budget_seconds','job_wall_seconds','job_cpu_seconds','rss_budget_bytes','tree_budget_bytes','stage_status','stage_wall_seconds','stage_cpu_seconds','peak_rss_bytes','peak_tree_bytes','native_exit','cleanup','pipe_eof','gzip_finalized')


def diagnostic(value):
    exact(value, DIAG_FIELDS)
    enum(value['schema'], ('P0_HEADER_DIAGNOSTIC_V1',))
    enum(value['status'], ('PASS_HEADER_ONLY','FAIL'))
    enum(value['failure_point'], POINTS);enum(value['failure_code'], CODES)
    integer(value['http_status'],100,599,True);enum(value['final_host'],HOSTS,True)
    integer(value['response_bytes'],0,38537,True);digest(value['observed_header_sha256'],True)
    boolean(value['header_sha_equal'],True);integer(value['geometry_checked'],0,12);integer(value['redirect_count'],0,4)
    if value['status']=='PASS_HEADER_ONLY':
        require(value['failure_point']=='COMPLETE' and value['failure_code']=='NONE' and value['http_status']==206)
        require(value['response_bytes']==38536 and value['observed_header_sha256']==HEADER_SHA and value['header_sha_equal'] is True and value['geometry_checked']==12)
        require(value['final_host'] in HOSTS[:-1])
    else:
        require(value['failure_code']!='NONE')
    return value


def validate(result, checks, host):
    exact(result,RESULT_FIELDS);enum(result['schema'],('P0_HEADER_REPAIR_RESULT_V1',));enum(result['candidate_id'],(ID,))
    enum(result['status'],('PASS_HEADER_ONLY','FAIL','INCOMPLETE'))
    enum(result['reason'],('HEADER_VERIFIED','PROBE_FAILURE','PRECHECK_PIN','RESOURCE_ADMISSION','CPU_PROOF','ABI','LIMIT','OWNERSHIP_INCOMPLETE','EXPORT_SCHEMA'))
    digest(result['source_manifest_sha256']);integer(result['failed_run_id'],FAILED_RUN,FAILED_RUN);integer(result['run_id'],1,2**63-1)
    boolean(result['header_exact']);integer(result['metadata_checked'],0,12)
    for key in ('runtime_installed','weights_downloaded','reference_executed','hardware_executed','raw_payloads_uploaded','original_failure_cause_proven'):
        require(result[key] is False)
    exact(checks,('schema','expected_header_bytes','expected_header_sha256','diagnostic'))
    enum(checks['schema'],('P0_HEADER_REPAIR_CHECKS_V1',));integer(checks['expected_header_bytes'],38536,38536)
    require(checks['expected_header_sha256']==HEADER_SHA);d=diagnostic(checks['diagnostic'])
    require(result['header_exact']==(d['header_sha_equal'] is True));require(result['metadata_checked']==d['geometry_checked'])
    exact(host,HOST_FIELDS);enum(host['schema'],('P0_HEADER_REPAIR_HOST_V1',))
    enum(host['architecture'],('x86_64',),True)
    if host['python_version'] is not None:
        import re
        require(type(host['python_version']) is str and re.fullmatch(r'3\.12\.[0-9]{1,3}',host['python_version']))
    digest(host['python_sha256'],True);integer(host['cpu_affinity_count'],1,4096,True);digest(host['cpu_evidence_sha256'],True)
    for key in ('initial_free_bytes','minimum_free_bytes','effective_memory_available_bytes','peak_rss_bytes','peak_tree_bytes'):
        integer(host[key],0,1<<50,True)
    for key in ('job_wall_seconds','job_cpu_seconds','stage_wall_seconds','stage_cpu_seconds'):
        number(host[key],86400,True)
    integer(host['wall_budget_seconds'],180,180);integer(host['cpu_budget_seconds'],60,60)
    integer(host['rss_budget_bytes'],256<<20,256<<20);integer(host['tree_budget_bytes'],16<<20,16<<20)
    enum(host['stage_status'],('PASS','FAIL','INCOMPLETE','NOT_REACHED'))
    integer(host['native_exit'],-255,255,True);enum(host['cleanup'],(COMPLETE,'INCOMPLETE','NOT_REACHED'))
    boolean(host['pipe_eof'],True);boolean(host['gzip_finalized'],True)
    if result['status']=='PASS_HEADER_ONLY':
        require(result['reason']=='HEADER_VERIFIED' and d['status']=='PASS_HEADER_ONLY' and host['stage_status']=='PASS')
        require(host['native_exit']==0 and host['cleanup']==COMPLETE and host['pipe_eof'] is True and host['gzip_finalized'] is True)
        for key,bound in (('job_wall_seconds',180),('job_cpu_seconds',60),('stage_wall_seconds',155),('stage_cpu_seconds',60),('peak_rss_bytes',256<<20),('peak_tree_bytes',16<<20)):
            require(host[key] is not None and host[key]<=bound)
        require(all(host[k] is not None for k in ('architecture','python_version','python_sha256','cpu_affinity_count','cpu_evidence_sha256','initial_free_bytes','minimum_free_bytes','effective_memory_available_bytes')))
    return True


def read_exports(work):
    fd=_open_dir(Path(work)/'export')
    try:
        require(set(os.listdir(fd))==set(FILES));records=[];total=0
        for name in FILES:
            file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            with os.fdopen(file_fd,'rb') as stream:
                s=os.fstat(stream.fileno());require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and 0<s.st_size<=4096)
                b=stream.read(4097);require(len(b)==s.st_size);total+=len(b);require(total<=12288);records.append(_decode(b))
        validate(*records);return dict(zip(FILES,records))
    finally:os.close(fd)


def write_exports(work,result,checks,host):
    validate(result,checks,host);output=Path(work)/'export';output.mkdir(mode=0o700,exist_ok=False)
    for name,value in zip(FILES,(result,checks,host)):
        b=canonical(value);require(len(b)<=4096)
        with (output/name).open('xb') as stream:stream.write(b);stream.flush();os.fsync(stream.fileno())
    return read_exports(work)


def seal(work,identity):
    work=Path(work);records=read_exports(work)
    value={'schema':'P0_HEADER_REPAIR_SEAL_V1','identity':identity,'files':{n:sha(work/'export'/n) for n in FILES},'status':records['RESULT.json']['status']}
    temp=work/'TERMINAL.pending'
    with temp.open('x') as stream:json.dump(value,stream,sort_keys=True,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    require(not (work/'TERMINAL.json').exists());temp.replace(work/'TERMINAL.json')


def verify_sealed(work,identity,outcome):
    require(outcome in ('success','failure'));work=Path(work);v=strict_json(work/'TERMINAL.json')
    exact(v,('schema','identity','files','status'));require(v['schema']=='P0_HEADER_REPAIR_SEAL_V1' and v['identity']==identity)
    exact(v['files'],FILES);before={n:sha(work/'export'/n) for n in FILES};require(v['files']==before)
    records=read_exports(work);r=records['RESULT.json'];require(v['status']==r['status'] and r['run_id']==identity['run_id'] and r['source_manifest_sha256']==identity['source_manifest_sha256'] and r['failed_run_id']==identity['failed_run_id'])
    if r['status']=='PASS_HEADER_ONLY':require(outcome=='success')
    require(before=={n:sha(work/'export'/n) for n in FILES});return records
