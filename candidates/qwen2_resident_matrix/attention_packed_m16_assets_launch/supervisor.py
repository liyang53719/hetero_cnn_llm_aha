"""Linux bounded process ownership for one isolated reference-preparation child."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import time

from ..attention_packed_m16_assets import reuse as R
from ..attention_packed_m16_assets.producer import protected_cleanup


def process_table():
    result={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            text=(path/'stat').read_text();fields=text.rsplit(')',1)[1].split()
            result[int(path.name)]=dict(pid=int(path.name),ppid=int(fields[1]),group=int(fields[2]),
                start=int(fields[19]),state=fields[0])
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            continue
    return result


def descendants(table,parent):
    found={parent};changed=True
    while changed:
        changed=False
        for pid,item in table.items():
            if item['ppid'] in found and pid not in found:
                found.add(pid);changed=True
    return {pid:table[pid] for pid in found if pid in table}


def enable_subreaper():
    R.need(not any(x['ppid']==os.getpid() for x in process_table().values()),'dedicated launcher process required')
    libc=ctypes.CDLL(None,use_errno=True)
    current=ctypes.c_int()
    R.need(libc.prctl(37,ctypes.byref(current),0,0,0)==0,'subreaper query failed')
    R.need(current.value==0,'launcher already owns an inherited subreaper scope')
    R.need(libc.prctl(36,1,0,0,0)==0,'subreaper setup failed')
    return libc


def restore_subreaper(libc):
    R.need(libc.prctl(36,0,0,0,0)==0,'subreaper restore failed')


class Child:
    def __init__(self,process):
        self.process=process;self.tracked={}

    def observe(self):
        table=process_table();owned=descendants(table,self.process.pid)
        # Orphans from the dedicated child become our children after subreaping.
        for pid,item in table.items():
            if item['ppid']==os.getpid():owned.update(descendants(table,pid))
        for pid,item in owned.items():
            old=self.tracked.get(pid)
            R.need(old is None or old['start']==item['start'],'owned PID reused unexpectedly')
            self.tracked[pid]=item
        return {pid:item for pid,item in table.items() if pid in self.tracked and
                item['start']==self.tracked[pid]['start']}

    def wait(self,stop):
        while True:
            self.observe()
            remaining=stop-time.monotonic()
            if remaining<=0:raise TimeoutError('reference preparation work deadline')
            try:
                code=self.process.wait(timeout=min(0.1,remaining))
                self.observe()
                return code
            except subprocess.TimeoutExpired:
                pass

    def signal_groups(self,signal_number,*,primary_only=False):
        live=self.observe();groups=set()
        for pid,item in live.items():
            if not primary_only or pid==self.process.pid:
                R.need(item['group']!=os.getpgrp(),'refuse launcher process-group signal')
                groups.add(item['group'])
        for group in groups:
            try:os.killpg(group,signal_number)
            except ProcessLookupError:pass

    def reap(self):
        self.process.poll()
        for pid in self.observe():
            if pid==self.process.pid:continue
            try:os.waitpid(pid,os.WNOHANG)
            except ChildProcessError:pass

    def clean_exit(self):
        self.reap()
        return not self.observe()

    def terminate(self,outer_deadline):
        """Give the child's protected cleanup five seconds before fallback KILL."""
        with protected_cleanup():
            self.observe()
            self.signal_groups(signal.SIGTERM,primary_only=True)
            grace=min(time.monotonic()+5,outer_deadline-0.75)
            while time.monotonic()<grace:
                self.reap()
                if not self.observe():return True
                time.sleep(min(0.025,max(0,grace-time.monotonic())))
            self.signal_groups(signal.SIGKILL)
            reap_end=outer_deadline-0.25
            while time.monotonic()<reap_end:
                self.reap()
                if not self.observe():return True
                time.sleep(min(0.01,max(0,reap_end-time.monotonic())))
            self.reap()
            return not self.observe()
