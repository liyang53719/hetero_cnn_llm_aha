"""Explicit single-new-child tick-policy M2 authority, never M128 admission.

The root supervisor creates ADMISSION and a parent lease. Each fresh child may
consume only the new arm once. This module cannot create root permission or launch.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types
import math
import time

HERE = Path(__file__).resolve().parent
BASE_MANIFEST_SHA = '4e5496a21b3ecd2b99c0022c1e99bb1666eafb284c84e91b525fc0e1c89c2889'
_STATE = None
_PURPOSES = set()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def stamp(s):
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)


def checked(path, pin=None, *, retain=True, cap=1<<30):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path,*path.parents)), 'absolute unaliased pin path')
    h=hashlib.sha256(); count=0; chunks=[]
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as f:
        before=os.fstat(f.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= cap,
             'bounded single-link regular pin required')
        if pin is not None:
            need(type(pin['bytes']) is int and pin['bytes']==before.st_size and
                 type(pin['sha256']) is str and len(pin['sha256'])==64,'pin size/type')
        while raw:=f.read(1<<20):
            count+=len(raw); need(count<=cap,'read cap'); h.update(raw)
            if retain: chunks.append(raw)
        after=os.fstat(f.fileno())
    need(stamp(before)==stamp(after)==stamp(path.lstat()),'pin changed during read')
    result={'bytes':count,'sha256':h.hexdigest()}
    if pin is not None:
        need(result=={k:pin[k] for k in ('bytes','sha256')},'pin bytes changed')
    return b''.join(chunks) if retain else result


def parse(raw):
    def pairs(items):
        out={}
        for k,v in items:
            need(k not in out,'duplicate JSON key'); out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def tick_policy(own):
    policy=parse(checked(HERE/'TICK_POLICY.json',own['files']['TICK_POLICY.json'],cap=32768))
    names={'cached_wholeblock.py','narrow_fullblock_attention.py','anchors.json','CODEC_PINS.json'}
    need(type(policy) is dict and policy.get('schema')=='fixed93-attention-tick-boundary-integrity-v1' and
         policy.get('policy_id')=='tick-boundary-metadata-integrity-v1' and
         own.get('policy_id')==policy['policy_id'] and
         policy.get('sampling_enabled') is False and policy.get('full_identity_frequency_changed') is True and
         policy.get('event_schema_changed') is False and policy.get('underlying_integrity_policy')=='op-evidence-boundary-v1' and
         policy.get('transient_metadata_detection_equivalent') is False and
         policy.get('scope_must_close') is True and type(policy.get('max_tick_ancestry_frames')) is int and
         policy['max_tick_ancestry_frames']==128 and policy.get('original_full_identity_unchanged') is True and
         type(policy.get('module_files')) is dict and set(policy['module_files'])==names and
         policy['module_files']=={k:own['files'][k] for k in names}, 'exact tick-boundary policy/source binding')
    return policy


def process(pid):
    text=Path('/proc/'+str(pid)+'/stat').read_text(); prefix,sep,rest=text.rpartition(') ')
    need(sep and prefix.split(' ',1)[0]==str(pid),'process identity format')
    return {'pid':pid,'start_ticks':int(rest.split()[19])}


def load_source(path, name, pin):
    need(name not in sys.modules,'module already loaded: '+name)
    raw=checked(path,pin,cap=2<<20)
    module=types.ModuleType(name);module.__file__=str(path);module.__package__=name.rpartition('.')[0]
    sys.modules[name]=module
    try: exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),vars(module))
    except BaseException:
        if sys.modules.get(name) is module:del sys.modules[name]
        raise
    need(sys.modules.get(name) is module,'module replaced during load')
    return module


def admit(*, arm, base, out, admission, admission_sha, manifest_sha):
    global _STATE
    need(_STATE is None and arm == 'new','one explicit arm per fresh process')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and not sys.flags.optimize,
         'isolated no-site source execution required')
    own_raw=checked(HERE/'SOURCE_MANIFEST.json',cap=1<<20)
    need(hashlib.sha256(own_raw).hexdigest()==manifest_sha,'new calibration source manifest')
    own=parse(own_raw)
    need(own['schema']=='fixed93-success-m2-tick-policy-source-v1' and own['actual_execution_authorized'] is False,
         'source declaration is not actual authority')
    for name,pin in own['files'].items():
        p=Path(name);need(not p.is_absolute() and '..' not in p.parts and str(p)==name,'relative source pin')
        checked(HERE/p,pin,retain=False,cap=2<<20)
    base=Path(base);out=Path(out);approval=Path(admission)
    need(base.is_absolute() and base.resolve()==base and str(base)==own['base']['path'],'exact baseline root')
    raw=checked(base/'SOURCE_MANIFEST.json',own['base']['manifest'],cap=2<<20)
    need(hashlib.sha256(raw).hexdigest()==BASE_MANIFEST_SHA,'fixed baseline identity')
    baseline=parse(raw)
    declaration_raw=checked(approval,cap=1<<20)
    need(hashlib.sha256(declaration_raw).hexdigest()==admission_sha,'root approval digest')
    a=parse(declaration_raw)
    need(a.get('schema')=='fixed93-success-m2-tick-policy-admission-v1' and
         a.get('status')=='REVIEWED_SINGLE_SUCCESS_M2_TICK_POLICY_ACTUAL' and
         a.get('authorized_by')=='/root' and a.get('actual_execution_authorized') is True and
         a.get('maximum_invocations')==1 and type(a.get('maximum_invocations')) is int and
         a.get('arms')==['new'] and a.get('automatic_retry') is False and
         a.get('M128_authorized') is False and a.get('fullblock_authorized') is False,
         'new bounded M2 permission required; fullblock authority rejected')
    need(a.get('source_manifest_sha256')==manifest_sha and a.get('base_source_manifest_sha256')==BASE_MANIFEST_SHA and
         a.get('policy_sha256')==own['files']['POLICY.json']['sha256'] and
         a.get('tick_policy_sha256')==own['files']['TICK_POLICY.json']['sha256'] and
         a.get('historical_comparison_sha256')==own['parent_files']['parent/HISTORY.json']['sha256'] and
         a.get('historical_comparison_only') is True and a.get('sampling_enabled') is False,
         'exact source/cache policy and parent-only historical comparison binding')
    tick_policy(own)
    budget=parse(checked(HERE/'BUDGET.json',own['files']['BUDGET.json']))
    need(a.get('budget_sha256')==own['files']['BUDGET.json']['sha256'] and
         budget['total_wall_seconds']==120 and budget['cpu_count']==1 and budget['rss_bytes']==2<<30 and
         budget['output_bytes']==80<<20,'one shared calibration budget')
    rootout=Path(a['output_root'])
    need(rootout.is_absolute() and rootout.resolve()==rootout and rootout.parent==HERE/'work' and
         out==rootout/arm and not out.exists() and approval==rootout/'ADMISSION.json', 'fresh exact arm namespace')
    lease=parse(checked(rootout/'LEASE.json',cap=1<<20));parent=process(os.getppid())
    need(lease['parent']==parent and lease['admission_sha256']==admission_sha and
         lease['source_manifest_sha256']==manifest_sha and lease['output_root']==str(rootout) and lease.get('arms')==['new'], 'parent lease binding')
    need(type(lease['work_stop']) in (int,float) and type(lease['whole_stop']) in (int,float) and
         all(math.isfinite(lease[k]) for k in ('start','work_stop','whole_stop')) and
         0 < lease['whole_stop']-lease['start'] <= 120 and
         lease['work_stop'] == lease['whole_stop']-15 and time.monotonic()<lease['work_stop'],'absolute shared deadline')
    need(len(os.sched_getaffinity(0))==1 and all(os.environ.get(k)=='1' for k in
         ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')),'single CPU/runtime threads')
    need(os.environ.get('PATH')=='/usr/bin:/bin' and not any(k.startswith('GIT_') or k in
         ('LD_PRELOAD','LD_LIBRARY_PATH','PYTHONPATH','PYTHONHOME') for k in os.environ),'sanitized child environment')
    review=parse(checked(Path(a['source_cold_review']['path']),a['source_cold_review'],cap=1<<20))
    need(review['status']=='GO_SINGLE_SUCCESS_M2_TICK_POLICY_SOURCE_COLD' and
         review['source_manifest_sha256']==manifest_sha and review['actual_authorized'] is False,
         'independent calibration source/cold review missing')
    with (rootout/('CONSUMED_'+arm+'.json')).open('x') as f:
        json.dump({'arm':arm,'child':process(os.getpid()),'parent':parent,'admission_sha256':admission_sha,
                   'source_manifest_sha256':manifest_sha},f,sort_keys=True)
    out.mkdir()
    _STATE={'arm':arm,'base':base,'out':out,'own':own,'source_manifest':baseline,'parent':parent,
            'pid':os.getpid(),'lease':lease,'declaration':a,'budget':budget,'manifest_sha256':manifest_sha}
    return _STATE


def require_actual_runtime(purpose):
    need(_STATE is not None and _STATE['pid']==os.getpid() and process(os.getppid())==_STATE['parent'],
         'current exact M2 authority/parent required')
    need(time.monotonic() < _STATE['lease']['work_stop'], 'shared M2 work deadline expired')
    sequence=('initialize_m2_runtime','existing_profile2_elf_load','construct_m2_observers',
              'success_m2_'+_STATE['arm'])
    need(len(_PURPOSES)<len(sequence) and purpose==sequence[len(_PURPOSES)] and
         purpose not in _PURPOSES,'unadmitted/repeated/out-of-order M2 purpose')
    _PURPOSES.add(purpose)
    return _STATE
