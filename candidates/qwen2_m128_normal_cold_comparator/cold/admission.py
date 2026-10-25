"""Exact cold-only review plus independent root GO. No execution on import."""
import json,os,stat,sys
from pathlib import Path
from supervisor_common import need,read_checked,file_id,process_stat,write_new

BOUNDS=dict(cpus=1,address_space_bytes=268435456,cpu_seconds=20,wall_seconds=25)
ACTION='single_m128_exact_source_normal_cold_only'


def validate(config,config_sha,review,review_sha,approval):
    need(config['actual_numeric_authorized'] is False and config['resource']==BOUNDS,'cold-only fixed original resource bounds')
    need(review['status']=='GO_EXACT_M128_COLD_SOURCE_ONLY' and review['config_sha256']==config_sha and review['blockers']==[],'exact independent cold review required')
    need(review['resource']==BOUNDS and review['numeric_or_native_executed'] is False,'cold review scope differs')
    need(approval['issued_by']=='root' and approval['go']=='GO' and approval['action']==ACTION,'explicit root cold GO required')
    need(approval['config_sha256']==config_sha and approval['review_sha256']==review_sha,'approval identities')
    need(approval['maximum_invocations']==1 and approval['no_retry'] is True,'single no-retry action')
    need(review['reviewer'] and review['reviewer']!=approval['issued_by'],'separate reviewer and authorizer')
    run_id=approval['run_id'];need(type(run_id) is str and 0<len(run_id)<=64 and run_id.replace('_','').isalnum(),'bounded canonical run ID')


def claim(fd,config,config_sha,out):
    need(stat.S_ISFIFO(os.fstat(fd).st_mode),'inherited pipe capability required')
    with os.fdopen(fd,'rb') as stream:raw=stream.read(16385)
    need(len(raw)<=16384,'capability size')
    cap=json.loads(raw);parent=os.getppid();pid=process_stat(parent)
    need(pid and cap['parent_pid']==parent and cap['parent_start_ticks']==pid['start_ticks'],'exact parent birth')
    need(cap['config_sha256']==config_sha and cap['output']==str(out),'capability config/output')
    need(os.getpgrp()==os.getpid(),'worker owns process group')
    need(Path('/proc/%d/exe'%parent).resolve()==Path(config['interpreter']),'parent interpreter')
    argv=[os.fsdecode(s) for s in Path('/proc/%d/cmdline'%parent).read_bytes().split(b'\0') if s]
    need(argv==cap['parent_argv'] and argv[1:4]==['-I','-S','-B'] and Path(argv[4]).resolve()==Path(config['cold_directory'])/'run_cold.py','exact launcher argv')
    need('--go' in argv and argv[argv.index('--go')+1]=='GO','parent explicit GO')
    review=read_checked(out/'REVIEW.json',cap['review_sha256'])
    approval=read_checked(out/'APPROVAL.json',cap['approval_sha256'])
    validate(config,config_sha,review,cap['review_sha256'],approval)
    need(out==Path(config['cold_directory'])/approval['run_id'],'unique approved output')
    ledger=read_checked(Path(config['cold_directory'])/'COLD_CLAIM.json',cap['claim_sha256'])
    for key in ('config_sha256','review_sha256','approval_sha256','output','run_id'):
        need(ledger[key]==cap[key],'claim ledger mismatch '+key)
    need(ledger['parent_identity']['pid']==parent and ledger['parent_identity']['start_ticks']==pid['start_ticks'],'claim parent identity')
    for path,pin in config['cold_executable_files'].items():need(file_id(path)==pin,'cold executable drift')
    need(sorted(os.sched_getaffinity(0))==cap['affinity'],'cold affinity')
    limits=Path('/proc/self/limits').read_text().splitlines()
    for label,value in [('Max cpu time',BOUNDS['cpu_seconds']),('Max address space',BOUNDS['address_space_bytes'])]:
        rows=[line.split() for line in limits if line.startswith(label)]
        need(len(rows)==1 and rows[0][-3:-1]==[str(value),str(value)],'cold hard per-process bounds')
    write_new(out/'WORKER_CLAIM.json',dict(capability=cap,worker=process_stat(os.getpid())))
    return cap
