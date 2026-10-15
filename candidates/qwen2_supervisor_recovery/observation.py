"""Small durable observations; never numerical acceptance or process resurrection."""
import json
import os
from pathlib import Path
import signal


def save(path, value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
    raw=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n'
    cap=1048576 if path.name.endswith(('.LAUNCH.json','.HEARTBEAT.json')) else 33554432
    if len(raw.encode())>cap or path.is_symlink() or tmp.is_symlink():
        raise ValueError('diagnostic metadata cap/alias')
    with tmp.open('w') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def stage(path):
    path=Path(path)
    try:
        if path.is_symlink():return {'state':'REJECTED_ALIAS'}
        with path.open('rb') as f:
            f.seek(0,2);size=f.tell();f.seek(max(0,size-65536));raw=f.read(65536)
        lines=raw.splitlines()
        if not lines:return {'state':'EMPTY'}
        record=json.loads(lines[-1])
        return {'state':'OBSERVED','stage':str(record.get('stage','UNKNOWN'))[:256],
                'mtime_ns':path.stat().st_mtime_ns,'snapshot_is_acceptance':False}
    except FileNotFoundError:return {'state':'MISSING'}
    except (OSError,ValueError,AttributeError):return {'state':'UNREADABLE_OR_PARTIAL'}


class ObservedSignal(BaseException):
    pass


class SignalScope:
    def __init__(self):
        self.previous={}
        self.pending=None
    def start(self):
        self.previous={n:signal.getsignal(n) for n in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT)}
        for n in self.previous:signal.signal(n,self.handle)
    def handle(self,n,frame):
        # Do not unwind Popen before its returned child has been assigned.
        if self.pending is None:self.pending=n
    def check(self):
        if self.pending is not None:raise ObservedSignal('supervisor signal '+str(self.pending))
    def cleaning(self):
        # A repeated catchable signal must not interrupt bounded group reaping.
        for n in self.previous:signal.signal(n,signal.SIG_IGN)
    def stop(self):
        for n,h in self.previous.items():signal.signal(n,h)
