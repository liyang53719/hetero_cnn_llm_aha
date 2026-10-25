"""Exclusive atomic stage records; no numerical/control instrumentation."""
import json,os,time
from pathlib import Path

def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.pending')
    with temporary.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    # This admitted worker is the sole producer of unique sequence/stage paths.
    # Reject existing evidence, then atomically rename within its new directory.
    # No transient hard-link count can trip the unchanged supervisor output gate.
    if path.exists():raise FileExistsError(str(path))
    os.rename(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

class Stages:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir();self.rows=[]
        self.start=self.previous=(time.process_time_ns(),time.monotonic_ns())
    def mark(self,stage,details=None):
        now=(time.process_time_ns(),time.monotonic_ns())
        row=dict(index=len(self.rows),stage=stage,pid=os.getpid(),cpu_ns=now[0],monotonic_ns=now[1],
            elapsed_cpu_ns=now[0]-self.start[0],elapsed_wall_ns=now[1]-self.start[1],
            delta_cpu_ns=now[0]-self.previous[0],delta_wall_ns=now[1]-self.previous[1],details=details)
        atomic_json(self.directory/('%03d_%s.json'%(len(self.rows),stage)),row)
        self.rows.append(row);self.previous=now
        return row

def sync_files(directory):
    directory=Path(directory)
    for path in directory.iterdir():
        if path.is_file():
            fd=os.open(path,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
