"""Bounded diagnostic metadata only. Never an execution or PASS credential.

One exclusive child writer, atomic snapshots, fixed enums and scalar counters.
The parent independently validates the latest snapshot after child-group cleanup.
"""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import time
from ..raw_kv_public_fresh import assets, setup

FILE='numeric.progress.json'
OWNER='numeric.progress.owner.json'
LIMIT=4096
MAX_WRITES=256
MAX_SECONDS=3420
PHASES=('context_check','setup_admission','entry_import','snapshot_prepare','snapshot_bind',
        'setup_revalidation','actual_execute','actual_validate','actual_file_check',
        'postflight_revalidation','complete_receipt')
STAGES=('none','run_preflight','input_load','public_prefix','public_suffix',
        'observation_seal','comparison','source_recheck','save_receipt')
OPERATORS=('none','Norm','Dense','Bias','Rope','KvAppend','Attention','Add','FFN')
PC_OPERATORS=('Norm','Dense','Bias','Rope','Dense','Bias','Rope','Dense','Bias','KvAppend',
              'Attention','Attention','Attention','Dense','Add','Norm','FFN','FFN','FFN','Dense','Add')
COUNTS={'host_model_ticks':2**63-1,'request_fire':17,'owner_result_fire':17,'completion_fire':21,'result_fire':1}
FIXED=dict(schema=1,kind='NUMERIC_PROGRESS_DIAGNOSTIC_ONLY',numerical_acceptance=False,
           postflight_complete=False,elapsed_origin='NUMERIC_WRITER_START')
KEYS=set(FIXED)|{'context_sha256','source_manifest_sha256','writer_sha256','sequence','elapsed_seconds',
                'phase_elapsed_seconds','phase','phase_state','stage','event','operator','ordinal','counts','capped'}
_ACTIVE=None

def need(ok):
    if not ok:raise ValueError('numeric progress metadata rejected')

def identities(context,sources):
    return dict(context_sha256=assets.sha(assets.encoded(context)),
                source_manifest_sha256=assets.sha(assets.encoded(sources)))

def validate(value,expected,*,previous=None):
    need(type(value) is dict and set(value)==KEYS)
    need(all(assets.same(value[k],v) for k,v in FIXED.items()))
    need(all(assets.digest(value[k]) for k in ('context_sha256','source_manifest_sha256','writer_sha256')))
    need(all(value[k]==v for k,v in expected.items()))
    need(type(value['sequence']) is int and 1<=value['sequence']<=MAX_WRITES)
    need(type(value['capped']) is bool and value['capped']==(value['sequence']==MAX_WRITES))
    for key in ('elapsed_seconds','phase_elapsed_seconds'):
        need(type(value[key]) in (int,float) and math.isfinite(value[key]) and 0<=value[key]<=MAX_SECONDS)
    need(value['phase_elapsed_seconds']<=value['elapsed_seconds'])
    need(value['phase'] in PHASES and value['phase_state'] in ('ENTERED','RETURNED'))
    need(value['stage'] in STAGES and value['event'] in ('PHASE','STAGE','REQUEST','COMPLETION','HEARTBEAT'))
    need(value['operator'] in OPERATORS and type(value['ordinal']) is int and -1<=value['ordinal']<=20)
    need(value['operator']==('none' if value['ordinal']==-1 else PC_OPERATORS[value['ordinal']]))
    counts=value['counts'];need(type(counts) is dict and set(counts)==set(COUNTS))
    need(all(type(counts[k]) is int and 0<=counts[k]<=bound for k,bound in COUNTS.items()))
    if previous is not None:
        need(value['sequence']==previous['sequence']+1 and value['elapsed_seconds']>=previous['elapsed_seconds'])
        need(all(counts[k]>=previous['counts'][k] for k in COUNTS))
        need(value['writer_sha256']==previous['writer_sha256'])
        need(PHASES.index(value['phase'])>=PHASES.index(previous['phase']))
        if value['phase']==previous['phase']:
            need(value['phase_elapsed_seconds']>=previous['phase_elapsed_seconds'])
            need(previous['phase_state']!='RETURNED' or value['phase_state']=='RETURNED')
            need(STAGES.index(value['stage'])>=STAGES.index(previous['stage']))
    return value


def read(private,context,sources):
    """Bounded independent projection; no logs, payloads, paths or free text."""
    private=assets.safe_path(private,directory=True)
    expected=identities(context,sources)
    owner=assets.read_json(private/OWNER,limit=1024)
    need(type(owner) is dict and set(owner)==set(expected)|{'writer_sha256'})
    need(all(owner[k]==v for k,v in expected.items()) and assets.digest(owner['writer_sha256']))
    return validate(assets.read_json(private/FILE,limit=LIMIT),owner)


class Writer:
    def __init__(self,private,context,sources):
        self.private=assets.safe_path(private,directory=True)
        self.identity=dict(identities(context,sources),writer_sha256=assets.sha(os.urandom(32)))
        owner=self.private/OWNER
        # An old claim is rejected, never overwritten. Fresh launch private dirs are required.
        with owner.open('xb') as stream:
            stream.write(assets.encoded(self.identity));stream.flush();os.fsync(stream.fileno())
        self.owner_inode=(owner.stat().st_dev,owner.stat().st_ino)
        need(not (self.private/FILE).exists() and not (self.private/FILE).is_symlink())
        self.started=time.monotonic_ns();self.phase_started=self.started
        self.value=None;self.last_sha=None
        self.current=dict(phase=PHASES[0],phase_state='RETURNED',stage='none',operator='none',ordinal=-1,
                          counts={k:0 for k in COUNTS})
        self.emit('PHASE')

    def emit(self,event):
        if self.value is not None and self.value['capped']:return
        owner=assets.safe_path(self.private/OWNER);stat=owner.stat()
        need((stat.st_dev,stat.st_ino)==self.owner_inode and assets.same(assets.read_json(owner,limit=1024),self.identity))
        path=self.private/FILE
        if self.last_sha is None:need(not path.exists())
        else:
            # Reject stale writers and any intervening modification; never repair it silently.
            path=assets.safe_path(path);need(path.stat().st_size<=LIMIT)
            with path.open('rb') as stream:raw=stream.read(LIMIT+1)
            need(len(raw)<=LIMIT and assets.sha(raw)==self.last_sha)
        now=time.monotonic_ns()
        sequence=1 if self.value is None else self.value['sequence']+1
        value=dict(FIXED,**self.identity,**self.current,sequence=sequence,event=event,
            elapsed_seconds=(now-self.started)/1e9,phase_elapsed_seconds=(now-self.phase_started)/1e9,
            capped=sequence==MAX_WRITES)
        validate(value,self.identity,previous=self.value)
        setup.atomic_json(path,value,LIMIT)
        self.last_sha=assets.sha(assets.encoded(value));self.value=value

    @contextmanager
    def phase(self,name):
        need(name in PHASES)
        self.current.update(phase=name,phase_state='ENTERED',stage='none')
        self.phase_started=time.monotonic_ns();self.emit('PHASE')
        yield
        self.current['phase_state']='RETURNED';self.emit('PHASE')

    def stage(self,name):
        need(name in STAGES and self.current['phase']=='actual_execute' and self.current['phase_state']=='ENTERED')
        self.current['stage']=name;self.emit('STAGE')

    def host(self,event,ordinal,counts):
        need(event in ('REQUEST','COMPLETION','HEARTBEAT') and type(ordinal) is int and 0<=ordinal<=20)
        self.current.update(operator=PC_OPERATORS[ordinal],ordinal=ordinal,counts=dict(counts))
        self.emit(event)


@contextmanager
def session(private,context,sources):
    global _ACTIVE
    need(_ACTIVE is None)
    _ACTIVE=Writer(private,context,sources)
    try:yield _ACTIVE
    finally:_ACTIVE=None


def stage(name):
    if _ACTIVE is not None:_ACTIVE.stage(name)


def host(event,ordinal,host_model_ticks,request_fire,owner_result_fire,completion_fire,result_fire):
    if _ACTIVE is not None:
        _ACTIVE.host(event,ordinal,dict(host_model_ticks=host_model_ticks,request_fire=request_fire,
            owner_result_fire=owner_result_fire,completion_fire=completion_fire,result_fire=result_fire))


def observe_trace(trace):
    """Observe the existing Host event sink; the original event is forwarded unchanged.

    No owner/memory/arithmetic method is replaced. Only its already-existing
    accepted-event callback is observed; no per-cycle or tensor tracing is added.
    The original private trace remains private and is never copied into progress.
    """
    if _ACTIVE is None:return
    original=trace.event
    counts={k:0 for k in COUNTS};ordinal=-1
    def event(value):
        nonlocal ordinal
        result=original(value)
        if type(value) is dict and value.get('kind')=='public_host':
            edge=value['edge'];counts['host_model_ticks']=value['tick']
            for key in COUNTS:
                if key!='host_model_ticks':counts[key]+=int(bool(edge[key]))
            if edge['request_fire']:
                request=edge['group_request'].gate if edge['group_request'] is not None else edge['ordinary_request']
                ordinal=request.tag & 0xffff
            if edge['completion_fire']:ordinal=edge['completion'].pc
            if ordinal>=0 and any(edge[k] for k in COUNTS if k!='host_model_ticks'):
                host('COMPLETION' if edge['completion_fire'] else 'REQUEST' if edge['request_fire'] else 'HEARTBEAT',
                     ordinal,**counts)
        return result
    trace.event=event
