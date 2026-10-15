"""Durable, fixed-schema M16 owner-group timings; never numerical acceptance.

BEGIN/END delimit actual runner callbacks, including fused pc10-12 Attention
and pc16-18 FFN. Public completion counts are independent of timing segments.
A killed process leaves only records already flushed; no SIGKILL finalizer is
claimed. failure() is best effort and never replaces an active business error.
"""
import json
import math
import os
from pathlib import Path
import stat
import time

SCOPE='M16_PUBLIC21_STAGE_COST_DIAGNOSTIC'
OWNER_STAGES=('PC0_NORM','PC1_Q','PC2_Q_BIAS','PC3_Q_ROPE','PC4_K','PC5_K_BIAS','PC6_K_ROPE',
    'PC7_V','PC8_V_BIAS','PC9_KV_APPEND','PC10_12_ATTENTION','PC13_O','PC14_RESIDUAL',
    'PC15_NORM','PC16_18_FFN','PC19_DOWN','PC20_RESIDUAL')
AUXILIARY_STAGES=('SETUP','PC12_RELEASE','LAUNCH_RESULT','REFERENCE','POSTSEAL_COMPARISON','FINAL_SEAL')
STAGES=frozenset((*OWNER_STAGES,*AUXILIARY_STAGES))
ERRORS=frozenset(('TIMEOUT','PROTOCOL','RESOURCE','VALIDATION','INTERNAL'))
COUNTER_LIMITS=dict(completed=21,jobs=17,accepted_results=1,
    **{key:1<<40 for key in ('host_ticks','read_bytes','write_ack_bytes','dense_steps','normal_steps',
        'dense_fma','normal_fma','exact64_fma','exact64_add','scalar_calls','silu_calls')})
LIMIT_KEYS=frozenset(('cpu_seconds','wall_seconds','address_space_bytes','output_bytes'))
# Serialization bound only. This does not extend either execution budget.
TIME_CAP=1800
LINE_CAP=4096
TAIL_CAP=65536
MAX_RECORDS=2*len(STAGES)


def need(ok,message):
    if not ok:raise ValueError(message)


def finite(value):
    return type(value) in (int,float) and 0<=value<=TIME_CAP and math.isfinite(value)


def counters(value):
    need(type(value) is dict and set(value)==set(COUNTER_LIMITS),'fixed stage counters required')
    need(all(type(value[k]) is int and 0<=value[k]<=limit for k,limit in COUNTER_LIMITS.items()),
        'native bounded stage counters required')
    return dict(value)


def validate_record(record):
    keys={'schema','scope','snapshot_is_acceptance','hardware_cycles','sequence','stage','stage_kind',
        'event','status','error_enum','wall_seconds','cpu_seconds','stage_wall_seconds','stage_cpu_seconds','counters'}
    need(type(record) is dict and set(record)==keys,'fixed stage record keys')
    need(type(record['schema']) is int and record['schema']==1 and record['scope']==SCOPE and
        record['snapshot_is_acceptance'] is False and record['hardware_cycles'] is None,'stage scope')
    need(type(record['sequence']) is int and 1<=record['sequence']<=MAX_RECORDS,'bounded stage sequence')
    stage=record['stage'];event=record['event']
    need(type(stage) is str and stage in STAGES,'fixed stage enum')
    need(record['stage_kind']==('OWNER_GROUP' if stage in OWNER_STAGES else 'AUXILIARY'),'stage kind')
    need(type(event) is str and event in ('BEGIN','END','FAIL'),'fixed stage event')
    need(record['sequence']%2==(1 if event=='BEGIN' else 0),'stage sequence/event parity')
    need(record['status']==dict(BEGIN='RUNNING',END='OK',FAIL='FAILED')[event],'stage status')
    need((type(record['error_enum']) is str and record['error_enum'] in ERRORS) if event=='FAIL'
        else record['error_enum'] is None,'fixed error enum')
    for key in ('wall_seconds','cpu_seconds','stage_wall_seconds','stage_cpu_seconds'):
        need(finite(record[key]),'native finite bounded stage time')
    need(record['stage_wall_seconds']<=record['wall_seconds'] and
        record['stage_cpu_seconds']<=record['cpu_seconds'],'stage time exceeds process observation')
    if event=='BEGIN':need(record['stage_wall_seconds']==record['stage_cpu_seconds']==0,'BEGIN has no completed duration')
    counters(record['counters'])
    return record


class StageLog:
    """One fresh JSONL file, explicit approved limits and nonoverlapping stages."""
    def __init__(self,out,limits):
        need(type(limits) is dict and set(limits)==LIMIT_KEYS and
            all(type(v) is int and v>0 for v in limits.values()),'explicit stage limits required')
        need((limits['cpu_seconds'],limits['wall_seconds']) in ((1200,1260),(60,90)) and
            limits['address_space_bytes']==4<<30 and limits['output_bytes']==96<<20,'approved M16 limits only')
        self.path=Path(out).absolute()
        need(self.path.resolve()==self.path and not any(p.is_symlink() for p in (self.path,*self.path.parents)),
            'stage log alias')
        with self.path.open('xb') as stream:
            info=os.fstat(stream.fileno());self.file_identity=(info.st_dev,info.st_ino)
            stream.flush();os.fsync(stream.fileno())
        self.started_wall=time.monotonic();self.started_cpu=time.process_time()
        self.limits=dict(limits);self.sequence=0;self.active=None;self.seen=set();self.closed=False;self.healthy=True
        self.last_counters=None

    def _write(self,record):
        validate_record(record)
        raw=(json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        need(len(raw)<=LINE_CAP,'bounded stage line')
        need(self.path.resolve()==self.path and not any(p.is_symlink() for p in (self.path,*self.path.parents)),
            'stage log changed alias')
        with self.path.open('ab') as stream:
            info=os.fstat(stream.fileno())
            need(stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==self.file_identity,'same stage file')
            stream.write(raw);stream.flush();os.fsync(stream.fileno())

    def _emit(self,stage,event,observed,error_enum=None):
        observed=counters(observed)
        if self.last_counters is not None:
            need(all(observed[k]>=self.last_counters[k] for k in COUNTER_LIMITS),'stage counters regressed')
        wall=time.monotonic();cpu=time.process_time()
        start_wall,start_cpu=(wall,cpu) if event=='BEGIN' else self.active[1:]
        record=dict(schema=1,scope=SCOPE,snapshot_is_acceptance=False,hardware_cycles=None,
            sequence=self.sequence+1,stage=stage,stage_kind='OWNER_GROUP' if stage in OWNER_STAGES else 'AUXILIARY',
            event=event,status=dict(BEGIN='RUNNING',END='OK',FAIL='FAILED')[event],error_enum=error_enum,
            wall_seconds=wall-self.started_wall,cpu_seconds=cpu-self.started_cpu,
            stage_wall_seconds=wall-start_wall,stage_cpu_seconds=cpu-start_cpu,counters=observed)
        try:self._write(record)
        except BaseException:
            self.healthy=False
            raise
        self.sequence+=1;self.last_counters=observed
        return wall,cpu

    def begin(self,stage,*,counters):
        need(not self.closed and self.healthy and self.active is None,'one live stage')
        need(type(stage) is str and stage in STAGES and stage not in self.seen,'one fixed stage per attempt')
        wall,cpu=self._emit(stage,'BEGIN',counters)
        self.active=(stage,wall,cpu);self.seen.add(stage)

    def end(self,stage,*,counters,status='OK'):
        need(not self.closed and self.healthy and self.active is not None and self.active[0]==stage,'matching live stage')
        need(type(status) is str and status=='OK','normal END status must be OK')
        self._emit(stage,'END',counters);self.active=None

    def transition(self,stage,*,counters):
        # Original tail invokes this after the prior operation returns. These
        # are real callback intervals, never fabricated per-public-pc timings.
        need(type(stage) is str and stage in STAGES and stage not in self.seen,'next fixed stage')
        if self.active is not None:self.end(self.active[0],counters=counters)
        self.begin(stage,counters=counters)

    def finish(self,*,counters):
        need(not self.closed and self.healthy,'open healthy stage log')
        if self.active is not None:self.end(self.active[0],counters=counters)
        self.closed=True

    def failure(self,stage,error_enum,*,counters):
        """Return whether FAIL was durable. Caller must re-raise its own error."""
        try:
            need(not self.closed and self.healthy and self.active is not None and self.active[0]==stage,'matching failed stage')
            need(type(error_enum) is str and error_enum in ERRORS,'fixed failure enum')
            self._emit(stage,'FAIL',counters,error_enum)
            self.active=None;self.closed=True
            return True
        except BaseException:
            self.healthy=False;self.closed=True
            return False


def _pairs(items):
    result={}
    for key,value in items:
        need(key not in result,'duplicate stage JSON key');result[key]=value
    return result


def _constant(value):
    raise ValueError('nonfinite stage JSON')


def safe_last(path):
    """Project only the last complete valid record; no original error or path."""
    unavailable=dict(schema=1,scope=SCOPE,status='UNAVAILABLE',record=None)
    try:
        path=Path(path).absolute()
        need(path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),'stage alias')
        with path.open('rb') as stream:
            info=os.fstat(stream.fileno());need(stat.S_ISREG(info.st_mode),'regular stage log')
            size=info.st_size;start=max(0,size-TAIL_CAP);stream.seek(start);raw=stream.read(size-start)
        if start:raw=raw.partition(b'\n')[2]
        lines=raw.split(b'\n')[:-1]
        need(bool(lines) and 0<len(lines[-1])<=LINE_CAP,'complete bounded final stage line')
        record=json.loads(lines[-1],object_pairs_hook=_pairs,parse_constant=_constant)
        validate_record(record)
        return dict(schema=1,scope=SCOPE,status='OBSERVED',record=record)
    except (OSError,ValueError,TypeError,UnicodeError,OverflowError,RecursionError):return unavailable
