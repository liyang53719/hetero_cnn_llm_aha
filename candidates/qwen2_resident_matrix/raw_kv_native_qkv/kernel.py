"""Explicit, source-frozen independent QKV recipe. Import never builds or loads.

Only the published two-block/high-first FP32 helper is reused. This is a
backend-scoped software reference, not a universal BF16 instruction emulator.
"""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import struct
import subprocess
import time

ROOT=Path(__file__).resolve().parents[3]
PREFIX='candidates/qwen2_resident_matrix/raw_kv_native_qkv/'
PROFILE='qwen2-independent-qkv-block-pair-v1'
PINS_PATH=PREFIX+'pins.json'
DOT='candidates/qwen2_resident_matrix/dense_block_reduce/reference/dot16.inc'
RECIPE='candidates/qwen2_resident_matrix/dense_block_reduce/reference/profile.json'
SPEC='spec/numerical_contract.md'
ORIGINAL='scripts/qwen2_layer0_model_gate.py'
FIXED={DOT:'175a8c3ff32287c6403a9bdf83c91d45249b6824cf4633753fcccb65c48d4ad6',
       RECIPE:'07008af966dbe4d64b10f75c37e4d19e17159e3708543982a70c8ec996f1d5a5',
       SPEC:'5cf7f538577e171ad42d70de60a24907b27e59991cc4d3895c42885fec962bb5',
       ORIGINAL:'917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85'}
SOURCE_PATHS=tuple(PREFIX+n for n in ('kernel.py','adapter.py','prepare.py','variant.patch','test_recipe.py','README.md'))+tuple(FIXED)
FLAGS=('-shared','-fPIC','-O2','-std=c++17','-ffp-contract=off','-fno-fast-math','-fno-builtin-fmaf')
CPP='qkv_pair.cpp'
LIBRARY='qkv_pair.so'
RECEIPT='qkv_pair_compile.json'
TOTAL=30
GRACE=5
IMPORTED_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def need(ok):
    if not ok:raise ValueError('independent QKV recipe contract')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def digest(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def json_bytes(raw,limit=131072):
    need(type(raw) is bytes and len(raw)<=limit)
    def pairs(items):
        value={}
        for key,item in items:need(key not in value);value[key]=item
        return value
    def nonfinite(_):raise ValueError('nonfinite QKV metadata')
    def number(token):
        value=float(token)
        if not math.isfinite(value):nonfinite(token)
        return value
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite,parse_float=number)


def safe_path(path,*,directory=False):
    path=Path(path).absolute();need('..' not in path.parts)
    need(all(not item.is_symlink() for item in (path,*path.parents)))
    info=path.stat();need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    return path


def read(path,limit=16*1024*1024):
    path=safe_path(path);before=path.stat();need(before.st_size<=limit)
    with path.open('rb') as stream:raw=stream.read(limit+1)
    after=path.stat()
    identity=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
    need(len(raw)==before.st_size and identity(before)==identity(after))
    return raw


def source(name):
    need(type(name) is str and not PurePosixPath(name).is_absolute() and
         all(part not in ('','.','..') for part in name.split('/')) and '\\' not in name)
    return read(ROOT/name,4*1024*1024)


def source_bytes():
    """Pure source construction; available before the new pins file is installed."""
    original={name:source(name) for name in (DOT,RECIPE,SPEC)}
    need(all(sha(raw)==FIXED[name] for name,raw in original.items()))
    profile=json_bytes(original[RECIPE]);parameters=profile['parameters']
    need(parameters['block_sizes']==[1024,512] and parameters['pair_width']==2 and
         parameters['pair_order']=='high_then_low' and parameters['output']=='BF16 RNE once after bias')
    prefix=r'''#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <vector>
#include <xmmintrin.h>
static_assert(sizeof(float)==4 && std::numeric_limits<float>::is_iec559,"FP32 required");
static void need(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static uint32_t bits(float value){uint32_t word;std::memcpy(&word,&value,4);return word;}
static float bf(float value){uint32_t word=bits(value);word=(word+0x7fff+((word>>16)&1))&0xffff0000u;std::memcpy(&value,&word,4);return value;}
static float add(float a,float b){return a+b;}
'''
    suffix=r'''
static bool valid(const float* values,size_t count){
  for(size_t i=0;i<count;i++)if(!std::isfinite(values[i]) || (bits(values[i])&0xffffu))return false;
  return true;
}
static bool overlaps(const float* a,size_t an,const float* b,size_t bn){
  uintptr_t x=reinterpret_cast<uintptr_t>(a),y=reinterpret_cast<uintptr_t>(b);
  if(x>UINTPTR_MAX-an*4 || y>UINTPTR_MAX-bn*4)return true;
  return x<y+bn*4 && y<x+an*4;
}
extern "C" int qkv_pair(int rows,int columns,const float* activation,const float* weights_kn,
    const float* bias,float* output) noexcept {
  if((rows!=16 && rows!=128) || (columns!=256 && columns!=1536))return 1;
  if(!activation || !weights_kn || !bias || !output)return 2;
  if((reinterpret_cast<uintptr_t>(activation)|reinterpret_cast<uintptr_t>(weights_kn)|reinterpret_cast<uintptr_t>(bias)|reinterpret_cast<uintptr_t>(output))&3u)return 2;
  if(std::fegetround()!=FE_TONEAREST || (_mm_getcsr()&0xe040u))return 3;
  const size_t ac=size_t(rows)*1536,wc=size_t(1536)*columns,oc=size_t(rows)*columns;
  if(overlaps(output,oc,activation,ac) || overlaps(output,oc,weights_kn,wc) || overlaps(output,oc,bias,columns))return 2;
  if(!valid(activation,ac) || !valid(weights_kn,wc) || !valid(bias,columns))return 4;
  try {
    std::vector<float> result(oc);
    const int blocks[2]={1024,512};
    for(int row=0;row<rows;row++)for(int column=0;column<columns;column+=16){
      float sums[16]={};
      reference_qkv_pair_dot16(activation+size_t(row)*1536,weights_kn,1536,columns,column,blocks,2,sums);
      for(int lane=0;lane<16;lane++){
        float value=add(sums[lane],bias[column+lane]);
        if(!std::isfinite(value))return 5;
        value=bf(value);if(!std::isfinite(value))return 5;
        result[size_t(row)*columns+column+lane]=value;
      }
    }
    std::copy(result.begin(),result.end(),output);
    return 0;
  }catch(...){return 6;}
}
'''
    return prefix.encode()+original[DOT]+suffix.encode()


def source_snapshot():
    raw=source(PINS_PATH);value=json_bytes(raw)
    need(type(value) is dict and set(value)=={'schema','profile','source_sha256','generated_module_sha256','cpp_sha256'} and
         type(value['schema']) is int and value['schema']==1 and value['profile']==PROFILE)
    sources=value['source_sha256'];need(type(sources) is dict and set(sources)==set(SOURCE_PATHS))
    need(all(digest(h) and sha(source(n))==h for n,h in sources.items()))
    need(all(sources[n]==h for n,h in FIXED.items()) and sources[PREFIX+'kernel.py']==IMPORTED_SHA256 and
         digest(value['generated_module_sha256']) and value['cpp_sha256']==sha(source_bytes()))
    return dict(source_sha256=dict(sources,**{PINS_PATH:sha(raw)}),pins_sha256=sha(raw),
                cpp_sha256=value['cpp_sha256'],generated_module_sha256=value['generated_module_sha256'])


def compiler_identity():
    found=shutil.which('g++');need(found is not None)
    path=Path(found).resolve(strict=True)
    return dict(path=str(path),sha256=sha(read(path,128*1024*1024)))


def _atomic(path,value):
    raw=encoded(value);need(len(raw)<=131072)
    pending=path.with_name(path.name+'.pending');need(not path.is_symlink())
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(pending,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _remaining(end,reserve=0):
    result=(end-time.monotonic_ns())/1e9-reserve
    if result<=0:raise TimeoutError()
    return result


def _compile(argv,out,end):
    """One compiler process group, reaped before the final receipt reservation."""
    process=None
    with (out/'compile.log').open('xb') as log:
        try:
            process=subprocess.Popen(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            return process.wait(timeout=_remaining(end,GRACE+1))
        finally:
            if process is not None:
                # A second cancellation cannot interrupt group KILL/reaping.
                mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGALRM})
                try:
                    reap_reserve=min(0.25,GRACE/2)
                    try:
                        try:os.killpg(process.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                        try:process.wait(timeout=max(0,min(GRACE-reap_reserve,(end-time.monotonic_ns())/1e9-1-reap_reserve)))
                        except subprocess.TimeoutExpired:pass
                    finally:
                        # Even an expired deadline or exited leader cannot skip KILL.
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                        # Safety-only bounded reap also applies after expiry;
                        # build's final deadline check still forbids success.
                        finally:process.wait(timeout=0.25)
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK,mask)


def verify(out):
    """Verify the current source/strict compiler/ELF receipt before any CDLL load."""
    out=safe_path(out,directory=True);raw=read(out/RECEIPT,131072);value=json_bytes(raw)
    fixed=dict(schema=1,profile=PROFILE,status='COMPILED_QKV_RECIPE',returncode=0,
        numerical_execution=False,official_framework_acceptance=False)
    need(type(value) is dict and set(value)==set(fixed)|{'source_sha256','pins_sha256','cpp_sha256',
        'generated_module_sha256','compiler','argv','library_sha256','elapsed_seconds','total_budget_seconds'})
    need(all(type(value[k]) is type(v) and value[k]==v for k,v in fixed.items()))
    frozen=source_snapshot();need(all(encoded(value[k])==encoded(v) for k,v in frozen.items()))
    compiler=compiler_identity();need(encoded(value['compiler'])==encoded(compiler))
    need(value['argv']==[compiler['path'],*FLAGS,str(out/CPP),'-o',str(out/LIBRARY)] and
         sha(read(out/CPP))==frozen['cpp_sha256'] and read(out/CPP)==source_bytes())
    binary=read(out/LIBRARY)
    need(len(binary)>=64 and binary[:6]==b'\x7fELF\x02\x01' and
         struct.unpack_from('<HH',binary,16)==(3,62) and sha(binary)==value['library_sha256'])
    need(type(value['elapsed_seconds']) in (int,float) and math.isfinite(value['elapsed_seconds']) and
         0<=value['elapsed_seconds']<=TOTAL and type(value['total_budget_seconds']) is int and value['total_budget_seconds']==TOTAL)
    need(source_snapshot()==frozen and compiler_identity()==compiler)
    return dict(library_path=str(out/LIBRARY),library_sha256=sha(binary),receipt_path=str(out/RECEIPT),
        receipt_sha256=sha(raw),**frozen)


def build(out,*,execute=False,deadline_ns=None):
    """Explicit opt-in only; one 30s absolute attempt, including cleanup/receipt."""
    need(type(execute) is bool and execute is True)
    start=time.monotonic_ns();end=start+TOTAL*10**9
    if deadline_ns is not None:need(type(deadline_ns) is int);end=min(end,deadline_ns)
    _remaining(end,GRACE+1)
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0))
    old={sig:signal.getsignal(sig) for sig in (signal.SIGALRM,signal.SIGTERM)}
    def timeout(signum,frame):raise TimeoutError()
    def interrupted(signum,frame):raise InterruptedError()
    signal.signal(signal.SIGALRM,timeout);signal.signal(signal.SIGTERM,interrupted)
    created_out=None;complete=False
    try:
        signal.setitimer(signal.ITIMER_REAL,_remaining(end,1))
        frozen=source_snapshot();compiler=compiler_identity();out=Path(out).absolute()
        need('..' not in out.parts and not out.exists() and not out.is_symlink() and
             all(not part.is_symlink() for part in out.parents))
        out.mkdir(parents=True);created_out=out;(out/CPP).write_bytes(source_bytes())
        argv=[compiler['path'],*FLAGS,str(out/CPP),'-o',str(out/LIBRARY)]
        signal.setitimer(signal.ITIMER_REAL,0)
        code=_compile(argv,out,end)
        signal.setitimer(signal.ITIMER_REAL,_remaining(end,1))
        need(type(code) is int and code==0 and source_snapshot()==frozen and compiler_identity()==compiler)
        receipt=dict(schema=1,profile=PROFILE,status='COMPILED_QKV_RECIPE',returncode=0,
            numerical_execution=False,official_framework_acceptance=False,**frozen,compiler=compiler,argv=argv,
            library_sha256=sha(read(out/LIBRARY)),elapsed_seconds=(time.monotonic_ns()-start)/1e9,total_budget_seconds=TOTAL)
        _atomic(out/RECEIPT,receipt)
        result=verify(out);_remaining(end);complete=True
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGALRM})
        try:
            if created_out is not None and not complete:
                for name in (RECEIPT,RECEIPT+'.pending'):
                    try:(created_out/name).unlink(missing_ok=True)
                    except OSError:pass
        finally:
            for sig,handler in old.items():signal.signal(sig,handler)
            signal.pthread_sigmask(signal.SIG_SETMASK,mask)
