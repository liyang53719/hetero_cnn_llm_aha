"""Failure-only observations of existing private metadata, never acceptance.

No numerical imports, loop edits, exception messages, source lines, addresses,
arrays, memory contents or log-controlled paths leave this bounded projection.
Printed traceback syntax and child-written reports are unauthenticated evidence.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

PROFILE='qwen2-full-m16-failure-observation-v1'
OWN='candidates/qwen2_resident_matrix/portable_same_host_m16_launch/'
PARSER='candidates/qwen2_resident_matrix/portable_official_producer_launch/failure_diagnostic.py'
STATUSES=frozenset(('PINNED_NOT_EXECUTED','ACTUAL_PREFIX_COMPLETE','WHOLE_TERMINAL_ACTUAL_OUTPUTS_SEALED',
    'PASS_REDUCED_BF16_OBSERVED_OFFICIAL_GATES','FAIL_OFFICIAL_OBSERVED_NODE_GATES','FAILED'))
COUNTERS={'completion_fire':21,'owner_result_fire':17,'request_fire':17,'result_fire':1,
    'host_model_ticks':10**9,'completion_backpressure_edges':10**9,'result_backpressure_edges':10**9,
    'idle_owner_edges':10**9,'ordinary_owner_edges':10**9,'raw_kv_parent_edges':10**9}
CONTROL_STATUSES=frozenset((None,'Bounds','Dependency','Malformed','Permission','Protocol','Unsupported','Memory','Numerical'))
DISPATCH_PCS=frozenset((*range(10),*range(12,21)))
MAX_SUMMARY=4*1024*1024
MAX_OUTPUT=16384


def need(value):
    if not value:raise ValueError('unavailable diagnostic')


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def integer(value,maximum):return type(value) is int and 0<=value<=maximum

def bounded_file(path,limit):
    """At most limit bytes read, with stable regular-file/inode/alias checks."""
    p=Path(path).absolute();need(not any(x.is_symlink() for x in (p,*p.parents)))
    before=p.stat();need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=limit)
    with p.open('rb') as f:
        opened=os.fstat(f.fileno());need((opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino))
        raw=f.read(limit);after=os.fstat(f.fileno())
    stamp=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    need(stamp(before)==stamp(after) and len(raw)==before.st_size)
    return raw


def strict(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAX_SUMMARY)
    def pairs(items):
        value={}
        for k,v in items:need(k not in value);value[k]=v
        return value
    def invalid(_):raise ValueError('nonfinite diagnostic')
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1;need(count<=250000 and depth<=40)
        if type(item) is dict:
            need(len(item)<=16384 and all(type(k) is str and len(k)<=4096 for k in item))
            pending.extend((v,depth+1) for v in item.values())
        elif type(item) is list:
            need(len(item)<=16384);pending.extend((v,depth+1) for v in item)
        elif type(item) is str:need(len(item)<=16384)
        elif type(item) is float:need(math.isfinite(item))
        elif type(item) is int:need(-(1<<64)<=item<(1<<64))
        else:need(item is None or type(item) is bool)
    return value


def progress(raw,sources,snapshot_sha):
    """Project only explicit scalar/control metadata; missing fields stay unknown."""
    v=strict(raw);need(type(v) is dict and v.get('status') in STATUSES and type(v.get('rows')) is int and v['rows']==16)
    need(encoded(v.get('source_sha256'))==encoded(sources) and v.get('snapshot_sha256')==snapshot_sha)
    need(v.get('old_pass_inherited') is False and v.get('rtl_executed') is False and v.get('scala_executed') is False)
    result=dict(status='OBSERVED',reported_status=v['status'],summary_sha256=sha(raw),snapshot_sha256=snapshot_sha,
        reported_prefix_complete=None,completed_public_pcs=None,host_counters=None,reported_launch_completed=None,
        reported_launch_jobs=None,reported_launch_status=None,reset_required=None,validated_dispatch_pcs=None,
        numeric_elapsed_seconds=None,prefix_elapsed_seconds=None,terminal_elapsed_seconds=None)
    for src,dst in (('host_wall_seconds','numeric_elapsed_seconds'),('prefix_host_wall_seconds','prefix_elapsed_seconds'),
                    ('whole_terminal_host_wall_seconds','terminal_elapsed_seconds')):
        if src in v:
            value=v[src];need(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1950)
            result[dst]=value
    if 'prefix_execution' in v:
        prefix=v['prefix_execution'];need(type(prefix) is list and len(prefix)==10)
        need(all(type(x) is dict and type(x.get('pc')) is int and x['pc']==i for i,x in enumerate(prefix)))
        result['reported_prefix_complete']=True
    host_present='failed_host' in v
    host=v.get('failed_host')
    if not host_present and type(v.get('execution')) is dict:
        host_present='host' in v['execution'];host=v['execution'].get('host')
    if host_present:
        need(type(host) is dict)
        completions=host.get('completions');need(type(completions) is list and len(completions)<=21)
        need(all(type(x) is dict and type(x.get('pc')) is int and x['pc']==i and 'status' in x and x['status'] is None for i,x in enumerate(completions)))
        result['completed_public_pcs']=list(range(len(completions)))
        counters=host.get('accepted');need(type(counters) is dict)
        result['host_counters']={}
        for key,maximum in COUNTERS.items():
            if key in counters:need(integer(counters[key],maximum));result['host_counters'][key]=counters[key]
        if 'reset_required' in host:
            need(type(host['reset_required']) is bool);result['reset_required']=host['reset_required']
        if 'validated_policy_jobs' in host:
            jobs=host['validated_policy_jobs'];need(type(jobs) is dict and len(jobs)<=19)
            allowed={str(pc) for pc in DISPATCH_PCS};need(set(jobs)<=allowed)
            result['validated_dispatch_pcs']=sorted(int(key) for key in jobs)
        launch=host.get('launch_result')
        if launch is not None:
            need(type(launch) is dict and integer(launch.get('completed'),21) and integer(launch.get('jobs'),17))
            need('status' in launch and launch['status'] in CONTROL_STATUSES)
            result['reported_launch_completed']=launch['completed'];result['reported_launch_jobs']=launch['jobs']
            result['reported_launch_status']=launch.get('status')
    need(len(encoded(result))<4096)
    return result


def unavailable(reason):
    return dict(schema=1,profile=PROFILE,status='DIAGNOSTIC_ONLY',diagnostic_only=True,acceptance=False,
        origin_authenticated=False,reason=reason,child_pid=None,observed_exit_code=None,
        run_context_sha256=None,source_manifest_sha256=None,traceback=None,progress=None)


def observe(L,pins,root,out,journal,*,sources,run_context,run_context_sha256,deadline):
    result=unavailable('OWNERSHIP_NOT_ESTABLISHED')
    events=[e for e in journal if e.get('phase')=='full_m16']
    if len(events)!=1:return result
    e=events[0]
    if not (type(e.get('pid')) is int and e['pid']>1 and type(e.get('observed_exit_code')) is int and
        e['observed_exit_code']>0 and type(e.get('final_exit_code')) is int and e['final_exit_code']==e['observed_exit_code'] and
        e.get('owned_group_cleanup_complete') is True and e.get('status')=='FAILED'):return result
    result.update(child_pid=e['pid'],observed_exit_code=e['observed_exit_code'])
    stop=min(time.monotonic()+1,deadline)
    if stop-time.monotonic()<0.05:result['reason']='DIAGNOSTIC_BUDGET';return result
    def budget():need(time.monotonic()<stop)
    try:
        budget();raw=bounded_file(Path(out)/'RUN_CONTEXT.json',65536)
        need(sha(raw)==run_context_sha256 and raw==encoded(run_context))
        need(type(sources) is dict and 1<=len(sources)<=512 and run_context['source_manifest_sha256']==sha(encoded(sources)))
        need(run_context['parent_pid']==os.getpid() and run_context['out']==str(out) and run_context['origin']==str(root))
        result.update(run_context_sha256=run_context_sha256,source_manifest_sha256=sha(encoded(sources)))
        parser=L.load_checked('full_m16_pinned_traceback_parser',Path(root)/PARSER,pins['inputs'][PARSER])
        metadata={}
        for name,expected in sources.items():
            budget();p=Path(out)/'source'/name;data=L.safe(p,8*1024*1024);need(sha(data)==expected)
            if name.endswith('.py'):metadata[str(p)]=dict(path=name,sha256=expected,lines=len(data.splitlines()))
        # The actual worker runs from the original checkout; composed code is separate.
        name=OWN+'worker.py';need(name not in sources);p=Path(root)/name;data=L.safe(p,8*1024*1024)
        need(sha(data)==pins['inputs'][name]);metadata[str(p)]=dict(path=name,sha256=sha(data),lines=len(data.splitlines()))
        budget()
        try:
            log=L.diagnostic_log(Path(out)/'full_m16.log');budget();result['traceback']=parser.extract(log,metadata)
        except TimeoutError:raise
        except Exception:result['traceback']=dict(status='UNAVAILABLE',reason='LOG_OR_PARSER_UNAVAILABLE')
        budget()
        try:
            summary=bounded_file(Path(out)/'full_m16/actual/summary.json',MAX_SUMMARY);budget()
            snapshot=bounded_file(Path(out)/'full_m16/snapshot/SNAPSHOT.json',MAX_SUMMARY);budget()
            result['progress']=progress(summary,sources,sha(snapshot));budget()
        except TimeoutError:raise
        except Exception:result['progress']=dict(status='UNAVAILABLE',reason='METADATA_UNAVAILABLE')
        result['reason']='BOUNDED_FAILURE_OBSERVATIONS'
        need(len(encoded(result))<=MAX_OUTPUT)
    except TimeoutError:raise
    except Exception:
        # Local extraction failures cannot replace the parent's original failure.
        result=unavailable('SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE')
    return result
