"""Source-bound group disappearance barrier; no work starts on import.

Keep the exact direct leader retained until completed bounded scans observe no
nonleader identities, including dead/defunct ones. Only then reap the leader.
This is an anchored process-group contract, not unobserved-tree confinement.
Callers must disable their work alarm/protect cleanup before calling, propagate
CleanupFailure, and validate the returned parent-owned proof before proceeding.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

# The caller verifies and executes one immutable admitted buffer, injecting its
# digest before exec. Do not reread __file__ and accidentally bind different bytes.
SOURCE_SHA256=globals().get('_ADMITTED_SOURCE_SHA256')
if (type(SOURCE_SHA256) is not str or len(SOURCE_SHA256)!=64 or
        any(c not in '0123456789abcdef' for c in SOURCE_SHA256)):
    raise ImportError('strict cleanup requires the admitted execution buffer SHA-256')
STATES=frozenset('RSDZTtXxKWPI')
DEAD=frozenset(('Z','X','x'))
IDENTITY_KEYS={'pid','ppid','group','start','session','state'}
OWNER_KEYS={'pid','ppid','group','start'}
MAX_PROC_ENTRIES=100000
MAX_GROUP_IDENTITIES=4096
MAX_SCANS=4096
MAX_EVIDENCE_RECORDS=16384
MAX_EVIDENCE_BYTES=2*1024*1024
SCOPE='ANCHORED_ORIGINAL_GROUP_AND_OBSERVED_IDENTITIES_ONLY'


class CleanupFailure(RuntimeError):
    def __init__(self,message,evidence):
        super().__init__(message)
        self.evidence=evidence


class _Invalid(RuntimeError):
    pass


class _Deadline(_Invalid):
    pass


def _need(ok,message):
    if not ok:raise _Invalid(message)


def _encoded(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def _sha(value):return hashlib.sha256(_encoded(value)).hexdigest()


def _identity(row,*,captured=False):
    _need(type(row) is dict and set(row)==IDENTITY_KEYS,'complete process identity')
    _need(all(type(row[k]) is int and row[k]>0 for k in ('pid','start')) and
          all(type(row[k]) is int and row[k]>=0 for k in ('ppid','group','session')) and
          type(row['state']) is str and row['state'] in STATES,'process identity fields')
    if captured:_need(row['group']>0 and row['session']>0,'captured group/session')
    return row


def parse_stat(raw):
    _need(type(raw) is bytes and 0<len(raw)<=4096,'bounded proc stat')
    try:
        opening=raw.index(b' (');closing=raw.rindex(b')')
        pid=raw[:opening].decode('ascii');fields=raw[closing+1:].decode('ascii').split()
        _need(pid.isdecimal() and closing>opening+1 and len(fields)>=50,'proc stat structure')
        _need(all(v.lstrip('-').isdecimal() and v.count('-')<=1 and
                  ('-' not in v or v.startswith('-')) for v in fields[1:]),'proc stat numeric field')
        return _identity(dict(pid=int(pid),state=fields[0],ppid=int(fields[1]),group=int(fields[2]),
            session=int(fields[3]),start=int(fields[19])))
    except (ValueError,UnicodeError,IndexError) as error:
        raise _Invalid('invalid proc stat: '+str(error)) from error


class _Linux:
    def __init__(self):
        self.parent=os.getpid();self.parent_group=os.getpgrp()
    def boot(self):
        with Path('/proc/sys/kernel/random/boot_id').open('rb') as stream:raw=stream.read(38)
        _need(len(raw)<=37,'bounded boot identity')
        value=raw.decode('ascii').strip()
        _need(len(value)==36 and tuple(i for i,c in enumerate(value) if c=='-')==(8,13,18,23) and
              all(c in '0123456789abcdef-' for c in value),'boot identity')
        return value
    def read(self,pid):
        try:
            with (Path('/proc')/str(pid)/'stat').open('rb') as stream:raw=stream.read(4097)
        except FileNotFoundError:return None
        result=parse_stat(raw);_need(result['pid']==pid,'proc PID mismatch');return result
    def peek(self,process):
        return os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    def kill_group(self,pid):
        try:os.killpg(pid,signal.SIGKILL)
        except ProcessLookupError:pass
    def reap(self,process,timeout):return process.wait(timeout=timeout)
    def arm(self,stop,now):
        # The caller has disabled its work timer. Block delivery while replacing
        # handlers, then run with SIGALRM unblocked even if entry masked it.
        _need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'work alarm must be disabled before cleanup')
        self.previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
        self.previous_alarm=signal.getsignal(signal.SIGALRM)
        self.alarm_installed=True
        _need(signal.SIGALRM not in signal.sigpending(),'preexisting pending alarm at cleanup entry')
        def expired(signum,frame):raise _Deadline('original cleanup deadline alarm')
        signal.signal(signal.SIGALRM,expired)
        remaining=stop-now();_need(remaining>0,'original deadline before observation alarm')
        signal.setitimer(signal.ITIMER_REAL,remaining)
        signal.pthread_sigmask(signal.SIG_SETMASK,self.previous_mask-{signal.SIGALRM})
    def disarm(self):
        if not getattr(self,'alarm_installed',False):return
        signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
        pending=False
        try:
            signal.setitimer(signal.ITIMER_REAL,0)
            pending=signal.SIGALRM in signal.sigpending()
            if pending:signal.sigtimedwait({signal.SIGALRM},0)
        finally:
            try:signal.signal(signal.SIGALRM,self.previous_alarm)
            finally:
                self.alarm_installed=False
                signal.pthread_sigmask(signal.SIG_SETMASK,self.previous_mask)
        _need(not pending,'pending original deadline alarm at cleanup finalization')
    def scan(self,tracked,group,stop,now):
        scan=dict(started=now(),finished=None,complete=False,captured={},members=[],vanished=[])
        def check():_need(now()<stop,'original deadline during scan')
        def read(pid):
            check();row=self.read(pid);check()
            if row is None:scan['vanished'].append(pid)
            return row
        try:
            check()
            for pid in sorted(tracked):scan['captured'][str(pid)]=read(pid)
            check();names=[]
            with os.scandir('/proc') as entries:
                for entry in entries:
                    check();_need(len(names)<MAX_PROC_ENTRIES,'bounded proc enumeration')
                    names.append(entry.name)
            check()
            for name in sorted(n for n in names if n.isascii() and n.isdecimal()):
                row=read(int(name))
                if row is not None and (row['group']==group or row['pid'] in tracked):scan['members'].append(row)
                _need(len(scan['members'])<=MAX_GROUP_IDENTITIES,'bounded group scan')
            check();scan['complete']=True
        except (OSError,_Invalid,ValueError) as error:scan['error']=type(error).__name__+': '+str(error)
        scan['finished']=now()
        if scan['finished']>=stop:scan.update(complete=False,error='original deadline during scan')
        return scan


def _verify_leader(owner,api,expected,boot):
    process=owner['process']
    _need(type(process.pid) is int and process.pid>1 and process.returncode is None,'unreaped direct process handle')
    waited=api.peek(process)  # ChildProcessError means no authority to signal.
    row=api.read(process.pid);_identity(row,captured=True)
    identity={key:row[key] for key in OWNER_KEYS}
    _need(identity['pid']==identity['group']==process.pid!=api.parent_group and
          identity['ppid']==api.parent and row['session']==process.pid,'owned direct leader/session')
    if owner['identity'] is None:owner['identity']=identity
    _need(type(owner['identity']) is dict and set(owner['identity'])==OWNER_KEYS and
          all(type(owner['identity'][key]) is int for key in OWNER_KEYS) and
          owner['identity']==identity,'exact retained leader PID/PPID/PGID/start')
    if expected is not None:
        _need(all(row[key]==expected[key] for key in ('pid','ppid','group','start','session')),'leader identity changed')
    _need(api.boot()==boot,'boot identity changed')
    return row,waited is not None


def _classify_scan(scan,tracked,leader):
    _need(scan.get('complete') is True,'incomplete full process-group scan: '+str(scan.get('error')))
    _need(set(scan['captured'])=={str(pid) for pid in tracked},'incomplete tracked identity reads')
    anchor=scan['captured'].get(str(leader['pid']))
    _identity(anchor,captured=True)
    _need(all(anchor[key]==leader[key] for key in ('pid','ppid','group','start','session')),
          'retained leader missing or changed in independent scan')
    _need(any(row['pid']==leader['pid'] and row['start']==leader['start'] for row in scan['members']),
          'retained leader missing from full enumeration')
    rows=[row for row in scan['captured'].values() if row is not None]+scan['members']
    for row in rows:
        _identity(row)
        if row['pid'] in tracked and row['start']==tracked[row['pid']]['start']:
            _need(row['group']==leader['group'] and row['session']==leader['session'],
                  'observed original identity escaped group/session')
        if row['group']==leader['group']:
            _need(row['session']==leader['session'] and row['start']>=leader['start'],'ambiguous owned group member')
            if row['pid'] in tracked:
                _need(row['start']==tracked[row['pid']]['start'],'reused tracked PID still in original group')
            else:tracked[row['pid']]=dict(row)
    _need(len(tracked)<=MAX_GROUP_IDENTITIES,'bounded tracked group identities')
    observations=[];present=[]
    for pid,original in sorted(tracked.items()):
        found=[row for row in rows if row['pid']==pid]
        if not found:found=[None]
        for row in found:
            if row is None:state='identity_disappeared'
            elif row['start']!=original['start']:state='identity_reused_unrelated'
            elif row['state']=='Z':state='defunct_present_unreaped'
            elif row['state'] in ('X','x'):state='dead_transient_present'
            else:state='live_or_not_proven_dead'
            observations.append(dict(original=original,observed=row,classification=state))
            if pid!=leader['pid'] and state not in ('identity_disappeared','identity_reused_unrelated'):present.append(row)
    scan['identities']=observations
    scan['nonleader_present']=bool(present)
    scan['live_nonleader_present']=any(row['state'] not in DEAD for row in present)
    return not present


def _retain_scan(report,scan,*,original_failure=False):
    records=sum(len(scan.get(key,())) for key in ('captured','members','vanished','identities'))
    size=len(_encoded(scan))
    if (report['evidence_records']+records>MAX_EVIDENCE_RECORDS or
            report['evidence_bytes']+size>MAX_EVIDENCE_BYTES):
        report['evidence_budget_exhausted']=True
        report['omitted_scan']=dict(started=scan.get('started'),finished=scan.get('finished'),records=records,bytes=size)
        if not original_failure:raise _Invalid('cumulative cleanup evidence budget exhausted')
        return
    report['scans'].append(scan)
    report['evidence_records']+=records;report['evidence_bytes']+=size


def _cleanup(owner,stop,api,now,sleep):
    report=dict(schema=1,scope=SCOPE,source_sha256=SOURCE_SHA256,stop=stop,started=now(),
        signals=[],scans=[],evidence_records=0,evidence_bytes=0,leader=None,leader_reaped=False,authority_released=False,cleanup_complete=False,
        observed_live_nonleader=False,observed_dead_nonleader=False,
        grandchildren_reaped_by_this_helper=False)
    if type(owner) is not dict:
        raise CleanupFailure('strict owned cleanup failed: parent-owned dictionary required',report)
    owner.pop('strict_cleanup_proof',None);owner.pop('strict_cleanup_seal',None)
    owner['strict_cleanup_observation']=report
    leader=None;boot=None;signaled=False;alarm_ready=False
    try:
        _need(type(stop) in (int,float) and math.isfinite(stop) and stop>0,'finite original absolute stop')
        _need(type(owner) is dict and 'process' in owner and 'identity' in owner and owner['process'] is not None,
              'parent-owned process handle')
        _need(now()<stop,'original cleanup deadline expired')
        api.arm(stop,now);alarm_ready=True
        boot=api.boot();leader,_=_verify_leader(owner,api,None,boot);report['leader']=dict(leader)
        # Signal before broad enumeration, but never after the original stop.
        # Identity reads and scans share that same absolute alarm boundary.
        leader,_=_verify_leader(owner,api,leader,boot)
        _need(now()<stop,'original deadline before verified group signal')
        api.kill_group(leader['pid']);signaled=True
        report['signals'].append(dict(at=now(),pid=leader['pid'],kind='SIGKILL',leader_retained=True))
        _need(now()<stop,'original cleanup deadline expired')
        tracked={leader['pid']:dict(leader)};quiet=0;barrier=None
        for index in range(MAX_SCANS):
            _need(now()<stop,'original cleanup deadline expired')
            _verify_leader(owner,api,leader,boot)
            scan=api.scan(tracked,leader['group'],stop,now)
            try:
                _need(type(scan.get('started')) in (int,float) and type(scan.get('finished')) in (int,float) and
                      report['started']<=scan['started']<=scan['finished']<stop and now()<stop,
                      'original deadline or invalid scan timing')
                absent=_classify_scan(scan,tracked,leader)
                report['observed_live_nonleader']|=scan['live_nonleader_present']
                report['observed_dead_nonleader']|=any(row['classification'] in
                    ('defunct_present_unreaped','dead_transient_present') and row['original']['pid']!=leader['pid']
                    for row in scan['identities'])
                _,exited=_verify_leader(owner,api,leader,boot)
                scan['leader_exited_retained']=exited
            except Exception:
                _retain_scan(report,scan,original_failure=True)
                raise
            _retain_scan(report,scan)
            quiet=quiet+1 if absent and exited else 0
            if quiet==2:barrier=scan['finished'];break
            remaining=stop-now();_need(remaining>0,'original cleanup deadline expired')
            sleep(min(0.02,remaining))
        _need(barrier is not None,'bounded scan inventory exhausted')
        _verify_leader(owner,api,leader,boot)
        reap_started=now();_need(barrier<reap_started<stop,'original deadline or barrier order before direct reap')
        code=api.reap(owner['process'],min(5,stop-reap_started));report.update(leader_reaped=True,authority_released=True)
        reaped=now();_need(type(code) is int and owner['process'].returncode==code,'exact direct wait result')
        _need(reaped<stop,'original deadline after direct reap')
        api.disarm()
        _need(now()<stop,'original deadline after alarm finalization')
        proof=dict(schema=1,status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',scope=SCOPE,
            source_sha256=SOURCE_SHA256,parent_pid=api.parent,boot_id=boot,
            owner_identity={key:leader[key] for key in OWNER_KEYS},session=leader['session'],stop=stop,
            started=report['started'],signal_at=report['signals'][0]['at'],barrier_at=barrier,
            reap_started_at=reap_started,reaped_at=reaped,completed_at=now(),empty_complete_scans=2,
            no_nonleader_identities_at_barrier=True,direct_leader_reaped=True,direct_exit_code=code,
            no_post_reap_signals=True,grandchildren_reaped_by_this_helper=False,
            complete_scan_bounds=[[scan['started'],scan['finished']] for scan in report['scans'][-2:]],
            scan_evidence_sha256=_sha(report['scans'][-2:]))
        _need(proof['completed_at']<stop,'original deadline before proof return')
        owner['strict_cleanup_proof']=proof;owner['strict_cleanup_seal']=_sha(proof)
        _validate_proof(proof,owner,stop,api.parent)
        _need(now()<stop,'original deadline after proof validation')
        report.update(cleanup_complete=True,proof=proof)
        return proof
    except (Exception,) as error:
        report['cleanup_complete']=False
        report['error']=type(error).__name__+': '+str(error)
        # Fail-closed containment: signal only a still-waitable exact owner; no
        # fresh scan/grace interval. A reaped leader never authorizes signaling.
        # Fail-closed teardown is not the successful absence barrier. Keep the
        # first failure, never signal after expiry/reap, and use no fresh budget.
        if not report['leader_reaped']:
            try:
                process=owner.get('process')
                _need(process is not None,'direct failure handle unavailable')
                if not signaled and not alarm_ready:
                    report['containment_signal_skipped']='cleanup_alarm_not_established'
                if not signaled and alarm_ready and type(stop) in (int,float) and math.isfinite(stop) and now()<stop:
                    if boot is None:boot=api.boot()
                    retained,_=_verify_leader(owner,api,leader,boot)
                    _need(now()<stop,'original deadline before failure signal')
                    api.kill_group(retained['pid']);signaled=True
                    report['signals'].append(dict(at=now(),pid=retained['pid'],kind='SIGKILL',leader_retained=True))
            except Exception as containment:
                report['containment_signal_error']=type(containment).__name__+': '+str(containment)
            try:
                process=owner.get('process')
                _need(process is not None,'direct failure handle unavailable')
                remaining=max(0,min(5,stop-now())) if type(stop) in (int,float) and math.isfinite(stop) else 0
                try:
                    code=api.reap(process,remaining)
                    report.update(leader_reaped=True,authority_released=True,failure_containment_direct_exit_code=code)
                except (subprocess.TimeoutExpired,_Deadline):
                    report['direct_handle_retained_for_supervisor']=True
                    report['direct_reap_incomplete']=True
            except Exception as containment:
                report['containment_reap_error']=type(containment).__name__+': '+str(containment)
                report['direct_reap_incomplete']=True
        try:api.disarm()
        except Exception as epilogue:report['alarm_finalization_error']=type(epilogue).__name__+': '+str(epilogue)
        owner.pop('strict_cleanup_proof',None);owner.pop('strict_cleanup_seal',None)
        raise CleanupFailure('strict owned cleanup failed: '+str(error),report) from error


PROOF_KEYS={'schema','status','scope','source_sha256','parent_pid','boot_id','owner_identity','session','stop',
    'started','signal_at','barrier_at','reap_started_at','reaped_at','completed_at','empty_complete_scans',
    'no_nonleader_identities_at_barrier','direct_leader_reaped','direct_exit_code','no_post_reap_signals',
    'grandchildren_reaped_by_this_helper','complete_scan_bounds','scan_evidence_sha256'}


def _validate_proof(proof,owner,stop,parent_pid):
    _need(type(stop) in (int,float) and math.isfinite(stop) and stop>0,'finite original proof stop')
    _need(type(proof) is dict and set(proof)==PROOF_KEYS and owner.get('strict_cleanup_proof') is proof and
          owner.get('strict_cleanup_seal')==_sha(proof),'parent-owned exact sealed cleanup proof')
    _need(type(proof['schema']) is int and proof['schema']==1 and
          proof['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and proof['scope']==SCOPE and
          proof['source_sha256']==SOURCE_SHA256,'strict cleanup source/schema/scope')
    identity=proof['owner_identity']
    _need(type(identity) is dict and set(identity)==OWNER_KEYS and
          all(type(identity[key]) is int and identity[key]>0 for key in OWNER_KEYS) and
          identity['ppid']==parent_pid and identity['pid']==identity['group'] and
          type(proof['session']) is int and type(proof['boot_id']) is str and
          len(proof['boot_id'])==36 and tuple(i for i,c in enumerate(proof['boot_id']) if c=='-')==(8,13,18,23) and
          all(c in '0123456789abcdef-' for c in proof['boot_id']), 'strict proof identity fields')
    _need(type(proof['parent_pid']) is int and proof['parent_pid']==parent_pid and
          proof['owner_identity']==owner['identity'] and proof['owner_identity']['pid']==owner['process'].pid and
          proof['session']==owner['process'].pid and type(proof['stop']) in (int,float) and proof['stop']==stop,
          'cleanup proof owner/deadline binding')
    times=[proof[k] for k in ('started','signal_at','barrier_at','reap_started_at','reaped_at','completed_at')]
    _need(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in times) and
          times==sorted(times) and times[-1]<stop,'cleanup proof barrier-before-reap ordering')
    _need(type(proof['empty_complete_scans']) is int and proof['empty_complete_scans']==2 and
          all(proof[k] is True for k in ('no_nonleader_identities_at_barrier','direct_leader_reaped','no_post_reap_signals')) and
          proof['grandchildren_reaped_by_this_helper'] is False and type(proof['direct_exit_code']) is int and
          owner['process'].returncode==proof['direct_exit_code'],'cleanup proof absence/wait claims')
    report=owner.get('strict_cleanup_observation')
    _need(type(report) is dict and type(report.get('scans')) is list and len(report['scans'])>=2,
          'parent-owned complete scan evidence')
    scans=report['scans'][-2:]
    bounds=[value for scan in scans for value in (scan.get('started'),scan.get('finished'))]
    _need(all(type(value) in (int,float) and math.isfinite(value) for value in bounds) and
          proof['signal_at']<=bounds[0]<=bounds[1]<=bounds[2]<=bounds[3]==proof['barrier_at']<proof['reap_started_at']<stop,
          'strict proof finite signal/scan/barrier/reap bounds')
    _need(proof['scan_evidence_sha256']==_sha(scans) and
          proof['complete_scan_bounds']==[[scan['started'],scan['finished']] for scan in scans] and
          scans[0]['finished']<=scans[1]['started'] and scans[1]['finished']==proof['barrier_at'] and
          all(scan.get('complete') is True and scan.get('nonleader_present') is False and
              scan.get('leader_exited_retained') is True for scan in scans),
          'strict proof complete retained-leader absence scans')
    return proof


def validate_cleanup_proof(proof,*,owner,stop):
    """Validate only the proof returned to this parent-owned invocation."""
    try:return _validate_proof(proof,owner,stop,os.getpid())
    except (Exception,) as error:
        raise CleanupFailure('invalid strict cleanup proof: '+str(error),{}) from error


def cleanup_owned(owner,stop):
    """Drop-in cleanup binding; callers must validate its returned proof."""
    return _cleanup(owner,stop,_Linux(),time.monotonic,time.sleep)
