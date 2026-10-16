"""Bounded private oneDNN stdout capture; never changes arithmetic modes."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import platform
import sys
import threading

from . import dispatch_diagnostic as diagnostic

LIMIT=2*1024*1024
MODES=('bf16','fp32')


def need(ok):
    if not ok:raise ValueError('dispatch capture contract')


def fenv_snapshot():
    """Read-only glibc x86-64 femode_t controls; no exception flags/pointers."""
    if sys.platform!='linux' or platform.machine()!='x86_64' or platform.libc_ver()[0]!='glibc':
        return {'status':'UNSUPPORTED'}
    lib=ctypes.CDLL(None)
    if not hasattr(lib,'fegetmode'):return {'status':'UNSUPPORTED'}
    class Mode(ctypes.Structure):
        _fields_=[('control',ctypes.c_ushort),('reserved',ctypes.c_ushort),('mxcsr',ctypes.c_uint)]
    need(ctypes.sizeof(Mode)==8 and Mode.mxcsr.offset==4)
    function=lib.fegetmode;function.argtypes=[ctypes.POINTER(Mode)];function.restype=ctypes.c_int
    mode=Mode()
    if function(ctypes.byref(mode))!=0:return {'status':'UNSUPPORTED'}
    return dict(status='OBSERVED',x87_round=(mode.control>>10)&3,
                sse_round=(mode.mxcsr>>13)&3,ftz=bool(mode.mxcsr&0x8000),daz=bool(mode.mxcsr&0x40))


def validate_fenv(value):
    need(type(value) is dict)
    if value.get('status')=='UNSUPPORTED':need(value=={'status':'UNSUPPORTED'});return value
    need(set(value)=={'status','x87_round','sse_round','ftz','daz'} and value['status']=='OBSERVED')
    need(all(type(value[k]) is int and 0<=value[k]<=3 for k in ('x87_round','sse_round')))
    need(all(type(value[k]) is bool for k in ('ftz','daz')))
    return value


def library_fenv(qkv_path,qk_path):
    """Inputs must already be verified library paths; retain no path in evidence."""
    before=fenv_snapshot()
    qkv=ctypes.CDLL(str(qkv_path));after_qkv=fenv_snapshot()
    qk=ctypes.CDLL(str(qk_path));after_qk=fenv_snapshot()
    return dict(before=before,after_qkv=after_qkv,after_qk=after_qk)


def flush_stdout():
    sys.stdout.flush()
    lib=ctypes.CDLL(None);function=lib.fflush
    function.argtypes=[ctypes.c_void_p];function.restype=ctypes.c_int
    need(function(None)==0)


class Capture:
    def __init__(self,directory,torch_module):
        self.directory=Path(directory).absolute()
        need(not self.directory.exists() and not self.directory.is_symlink() and
             all(not p.is_symlink() for p in self.directory.parents))
        self.directory.mkdir(mode=0o700)
        self.torch=torch_module;self.results={};self.active=False

    @contextmanager
    def capture(self,mode):
        need(type(mode) is str and mode in MODES and mode not in self.results and not self.active)
        self.active=True
        path=self.directory/(mode+'.private.log')
        saved=read_fd=write_fd=log_fd=None;worker=None;state={'count':0,'error':False}
        before=self.torch.backends.mkldnn.enabled
        need(type(before) is bool)
        try:
            flush_stdout();log_fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            saved=os.dup(1);read_fd,write_fd=os.pipe()
            def drain():
                try:
                    with os.fdopen(log_fd,'wb',buffering=0) as stream,os.fdopen(read_fd,'rb',buffering=0) as source:
                        while True:
                            chunk=source.read(65536)
                            if not chunk:break
                            retain=max(0,LIMIT-state['count'])
                            if retain:
                                try:
                                    kept=chunk[:retain]
                                    if stream.write(kept)!=len(kept):state['error']=True
                                except OSError:state['error']=True
                            state['count']=min(LIMIT+1,state['count']+len(chunk))
                except BaseException:state['error']=True
            worker=threading.Thread(target=drain,daemon=True);worker.start()
            os.dup2(write_fd,1);os.close(write_fd);write_fd=None
            with self.torch.backends.mkldnn.verbose(self.torch.backends.mkldnn.VERBOSE_ON):
                yield
        finally:
            try:
                if saved is not None:
                    try:flush_stdout()
                    finally:os.dup2(saved,1);os.close(saved);saved=None
                if write_fd is not None:os.close(write_fd)
                if worker is not None and worker.ident is not None:worker.join(timeout=2)
                else:
                    for fd in (read_fd,log_fd):
                        if fd is not None:os.close(fd)
                failed=state['error'] or worker is None or worker.ident is None or worker.is_alive()
                raw=b''
                if not failed:
                    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
                    with os.fdopen(fd,'rb') as stream:raw=stream.read(LIMIT+1)
                need(len(raw)<=LIMIT)
                result=diagnostic.parse_verbose(raw,truncated=failed or state['count']>LIMIT)
                self.results[mode]=result
                need(self.torch.backends.mkldnn.enabled is before)
            finally:self.active=False

    def report(self):
        need(not self.active)
        return {mode:diagnostic.validate_verbose(self.results.get(mode,
            diagnostic.parse_verbose(b'',truncated=True))) for mode in MODES}
