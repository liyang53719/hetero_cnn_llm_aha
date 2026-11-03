"""Isolated V2 thread-entry and non-owned signal-mask regression tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BASE=Path(os.environ.get('RSS_TELEMETRY_BASE',str(HERE)))
OWNED={signal.SIGINT,signal.SIGTERM,signal.SIGALRM,signal.SIGPROF}


def need(value,detail):
    if not value:raise AssertionError(detail)


def caps():
    policy=dict(schema='FULL_PREFILL_RSS_GZIP_V1',raw_bytes=1<<20,compressed_bytes=64<<20,
                line_bytes=1<<20,verification_wall_seconds=3,verification_cpu_seconds=3)
    return dict(wall_seconds=3,cleanup_seconds=3,rss_telemetry_policy=policy,file_bytes=2<<20,
                tree_bytes=8<<20,log_bytes=1<<20,raw_log_bytes=1<<20,max_entries=1000,
                per_process_as_bytes=512<<20,per_process_cpu_seconds=3,rss_bytes=256<<20,
                cpu_seconds=3,min_free_disk_bytes=0)


def load(root):
    for name in ('strict_cleanup.py','lossless_log.py'):
        shutil.copyfile(BASE/name,root/name)
    for name in ('rss_telemetry.py','supervise_multiroot.py'):
        shutil.copyfile(HERE/name,root/name)
    spec=importlib.util.spec_from_file_location('bits_supervisor',root/'supervise_multiroot.py')
    module=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(root))
    try:spec.loader.exec_module(module)
    finally:sys.path.pop(0)
    return module


def thread_probe():
    with tempfile.TemporaryDirectory(prefix='rss-thread-probe-') as temporary:
        root=Path(temporary);module=load(root);result={}
        def task():
            before=signal.pthread_sigmask(signal.SIG_BLOCK,set())
            actual_mask=signal.pthread_sigmask
            with patch.object(module,'helper',side_effect=AssertionError('must reject before helper')), \
                 patch.object(module.os,'open',side_effect=AssertionError('must reject before lock')), \
                 patch.object(module.signal,'pthread_sigmask',side_effect=AssertionError('must reject before mask')):
                try:module.execute(['must-not-start'],root/'run',root/'lock',caps(),{}, {})
                except ValueError as error:result['error']=str(error)
                except BaseException as error:result['unexpected']=repr(error)
            result['before']=sorted(before)
            result['after']=sorted(actual_mask(signal.SIG_BLOCK,set()))
        thread=threading.Thread(target=task);thread.start();thread.join(3)
        need(not thread.is_alive(),'worker thread did not return')
        need(result.get('error')=='V2 supervisor requires main thread',result)
        need(result['before']==result['after'],result)
        need(not(root/'lock').exists() and not(root/'run').exists(),'thread entry created state')
        print(json.dumps(dict(kind='thread',preserved=True,result=result)))


def mask_probe(checkpoint,direction):
    initially_blocked=direction=='unblock'
    expected_blocked=not initially_blocked
    if initially_blocked:signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGUSR1})
    else:signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGUSR1})
    initial_owned=signal.pthread_sigmask(signal.SIG_BLOCK,set())&OWNED
    def change():
        signal.pthread_sigmask(signal.SIG_BLOCK if expected_blocked else signal.SIG_UNBLOCK,{signal.SIGUSR1})
    with tempfile.TemporaryDirectory(prefix='rss-nonowned-probe-') as temporary:
        root=Path(temporary);module=load(root)
        if checkpoint=='verification':
            with (root/'rss_telemetry.py').open('a') as output:
                output.write('\nimport signal\n_saved_verify=verify\ndef verify(*args,**kwargs):\n result=_saved_verify(*args,**kwargs)\n signal.pthread_sigmask(signal.'+('SIG_BLOCK' if expected_blocked else 'SIG_UNBLOCK')+',{signal.SIGUSR1})\n return result\n')
        pins={str(root/'rss_telemetry.py'):hashlib.sha256((root/'rss_telemetry.py').read_bytes()).hexdigest()}
        if checkpoint=='rejection':
            actual=signal.getitimer
            signal.setitimer(signal.ITIMER_REAL,5)
            def foreign_timer(which):
                change()
                return actual(which)
            with patch.object(signal,'getitimer',side_effect=foreign_timer):
                try:module.execute(['must-not-start'],root/'run',root/'lock',caps(),{},pins)
                except ValueError as error:need('initially active' in str(error),str(error))
                else:raise AssertionError('active timer accepted')
            need(actual(signal.ITIMER_REAL)[0]>0,'foreign timer canceled')
            signal.setitimer(signal.ITIMER_REAL,0)
            status='REJECTED'
        else:
            original=module.verify_aliases;calls=0
            def aliases(values):
                nonlocal calls
                calls+=1
                if calls==1 and checkpoint in ('early_failure','work'):
                    change()
                    if checkpoint=='early_failure':raise ValueError('synthetic early failure')
                return original(values)
            with patch.object(module,'verify_aliases',side_effect=aliases):
                result=module.execute([sys.executable,'-c',"import time; print('synthetic-mask-fixture'); time.sleep(.1)"],
                                      root/'run',root/'lock',caps(),dict(os.environ),pins)
            status=result['status']
            need(status==('FAIL_OR_INCOMPLETE' if checkpoint=='early_failure' else 'PASS_PROCESS_ONLY'),result)
        final=signal.pthread_sigmask(signal.SIG_BLOCK,set())
        need((signal.SIGUSR1 in final)==expected_blocked,(checkpoint,direction,sorted(final)))
        need(final&OWNED==initial_owned,('owned bits not restored',initial_owned,final))
        need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.) and signal.getitimer(signal.ITIMER_PROF)==(0.,0.),'timer leak')
        print(json.dumps(dict(kind='mask',checkpoint=checkpoint,direction=direction,preserved=True,status=status)))


def raising_restore_probe(kind):
    import fcntl
    class ExternalFailure(RuntimeError):pass
    real=signal.pthread_sigmask;original_mask=real(signal.SIG_BLOCK,set())
    original_handlers={s:signal.getsignal(s)for s in OWNED|{signal.SIGUSR1}}
    seen=[]
    def external_handler(signum,frame):
        real(signal.SIG_BLOCK,{signal.SIGUSR2});seen.append(signum)
        raise ExternalFailure('actual unrelated handler during rejected-entry restoration')
    signal.signal(signal.SIGUSR1,external_handler)
    real(signal.SIG_UNBLOCK,OWNED|{signal.SIGUSR1,signal.SIGUSR2})
    if kind.startswith('blocked_'):
        real(signal.SIG_BLOCK,{signal.SIGALRM if kind=='blocked_alarm'else signal.SIGPROF})
    elif kind=='foreign_real':signal.setitimer(signal.ITIMER_REAL,20,1)
    elif kind=='foreign_prof':signal.setitimer(signal.ITIMER_PROF,20,1)
    else:raise AssertionError(kind)
    entry=real(signal.SIG_BLOCK,set());pending=signal.sigpending()
    handlers={s:signal.getsignal(s)for s in OWNED}
    timers={t:signal.getitimer(t)for t in (signal.ITIMER_REAL,signal.ITIMER_PROF)}
    try:
        with tempfile.TemporaryDirectory(prefix='rss-raising-restore-')as temporary:
            root=Path(temporary);module=load(root);original_restore=module._v2_set_owned_signal_mask
            state=dict(restoring=False,injected=False)
            def restore(desired):
                state['restoring']=True
                try:return original_restore(desired)
                finally:state['restoring']=False
            def interleave(how,signals):
                previous=real(how,signals)
                if state['restoring']and not state['injected']:
                    state['injected']=True;os.kill(os.getpid(),signal.SIGUSR1)
                return previous
            with patch.object(module,'_v2_set_owned_signal_mask',side_effect=restore),patch.object(signal,'pthread_sigmask',side_effect=interleave),patch.object(module.subprocess,'Popen',side_effect=AssertionError('rejected entry must not start child')):
                try:module.execute(['must-not-start'],root/'run',root/'lock',caps(),{}, {})
                except ExternalFailure:pass
                else:raise AssertionError('raising handler did not propagate')
            need(seen==[signal.SIGUSR1]and state['injected'],'real handler not delivered once')
            need(real(signal.SIG_BLOCK,set())==entry|{signal.SIGUSR2},'owned restore incomplete or unrelated change lost')
            need(signal.sigpending()==pending,'pending signal changed')
            need(all(signal.getsignal(s)is h for s,h in handlers.items()),'caller handlers changed')
            for timer,before in timers.items():
                after=signal.getitimer(timer)
                need(after==before if before==(0.,0.) else 0<after[0]<=before[0]and after[1]==before[1],'caller timer changed')
            need(not(root/'run').exists(),'rejected entry created run')
            fd=os.open(root/'lock',os.O_RDWR)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(fd)
            print(json.dumps(dict(kind='raising_restore',variant=kind,preserved=True)))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.setitimer(signal.ITIMER_PROF,0)
        for signum,handler in original_handlers.items():signal.signal(signum,handler)
        real(signal.SIG_SETMASK,original_mask)


class SignalBits(unittest.TestCase):
    def child(self,*args):
        command=[sys.executable]+(['-O'] if not __debug__ else [])+[str(Path(__file__).resolve()),'--probe',*args]
        result=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout.strip().splitlines()[-1])['preserved'])

    def test_raising_reentrant_rejection_restores_owned_bits_and_releases_lock(self):
        for kind in ('blocked_alarm','blocked_prof','foreign_real','foreign_prof'):
            with self.subTest(kind=kind):self.child('raising_restore',kind)

    def test_worker_thread_rejects_before_any_owned_state(self):self.child('thread')

    def test_nonowned_mask_changes_survive_every_v2_transition(self):
        for checkpoint in ('rejection','early_failure','work','verification'):
            for direction in ('block','unblock'):
                with self.subTest(checkpoint=checkpoint,direction=direction):self.child('mask',checkpoint,direction)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--probe':
        if sys.argv[2]=='thread':thread_probe()
        elif sys.argv[2]=='raising_restore':raising_restore_probe(sys.argv[3])
        else:mask_probe(*sys.argv[3:])
    else:unittest.main(verbosity=2)
