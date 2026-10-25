"""Small identity/JSON helpers; no target imports, native load or tensor decode."""
import hashlib,json,os
from pathlib import Path

def need(ok,message):
    if not ok:raise ValueError(message)
def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()
def file_id(path):
    p=Path(path);a=p.stat();digest=sha(p);b=p.stat()
    need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'identity changed while hashing')
    return dict(bytes=b.st_size,sha256=digest)
def write_new(path,value):
    with Path(path).open('xb') as f:f.write(encoded(value));f.flush();os.fsync(f.fileno())
def write_payload(path,raw):
    need(type(raw) is bytes,'immutable actual bytes only')
    with Path(path).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),file=Path(path).name)
