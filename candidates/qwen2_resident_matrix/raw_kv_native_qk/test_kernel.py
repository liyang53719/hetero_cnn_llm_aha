"""Cold candidate raw-QK source/control and exact Fraction tests.

No test here builds or loads a library. Receipt/ELF fixtures are metadata-only.
The exact scalar oracle checks the proposed order, not PyTorch equivalence.
"""
import ast
from copy import deepcopy
from fractions import Fraction
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from . import kernel as k


def exact(word):
    if type(word) is not int or not 0<=word<=0xffffffff:
        raise ValueError('binary32 word required')
    exponent=(word>>23)&255;significand=word&0x7fffff
    if exponent==255:raise ValueError('finite word required')
    shift=-149 if exponent==0 else exponent-150
    if exponent:significand+=1<<23
    if word>>31:significand=-significand
    return Fraction(significand<<max(shift,0),1<<max(-shift,0))


def rounded(value,*,negative_zero=False):
    """Exact quotient/remainder binary32 nearest-even, including subnormals."""
    sign=0x80000000 if value<0 or (not value and negative_zero) else 0
    if not value:return sign
    n,d=abs(value).as_integer_ratio()
    exponent=n.bit_length()-d.bit_length()
    if abs(value)<Fraction(1<<max(exponent,0),1<<max(-exponent,0)):exponent-=1
    shift=149 if exponent < -126 else 23-exponent
    n<<=max(shift,0);d<<=max(-shift,0)
    q,remainder=divmod(n,d)
    if 2*remainder>d or (2*remainder==d and q&1):q+=1
    if exponent < -126:return sign|q
    if q>=1<<24:q>>=1;exponent+=1
    if exponent>127:return sign|0x7f800000
    return sign|((exponent+127)<<23)|(q&0x7fffff)


def fma_word(a,b,c):
    product=exact(a)*exact(b);value=product+exact(c)
    negative_zero=(not product and not exact(c) and bool((a^b)&0x80000000) and bool(c&0x80000000))
    return rounded(value,negative_zero=negative_zero)


def dot128(q,keys,*,high_first=True):
    if len(q)!=128 or len(keys)!=128 or type(high_first) is not bool:
        raise ValueError('exact128 fixture required')
    for word in (*q,*keys):
        exact(word)
        if word&0xffff:raise ValueError('decoded BF16 fixture required')
    result=0
    for pair in range(64):
        for index in ((2*pair+1,2*pair) if high_first else (2*pair,2*pair+1)):
            result=fma_word(q[index],keys[index],result)
    return result


class FractionQkTests(unittest.TestCase):
    def test_pair_order_cancellation_distinguishes_increasing_order(self):
        q=[0x3f800000]*128;keys=[0]*128
        keys[:4]=[0x3f800000,0,0xbf800000,0x33800000]
        self.assertEqual(dot128(q,keys),0)
        self.assertEqual(dot128(q,keys,high_first=False),0x33800000)

    def test_raw_output_retains_fp32_bits_without_scale_or_bf16_rounding(self):
        q=[0x3f800000]*128;keys=[0]*128
        keys[:2]=[0x37800000,0x3f800000]  # 1 + 2^-16, raw FP32.
        self.assertEqual(dot128(q,keys),0x3f800080)
        self.assertNotEqual(dot128(q,keys)&0xffff,0)
        self.assertEqual(dot128(q,[0x3f800000]*128),0x43000000)

    def test_bf16_fused_subnormal_halfway_uses_single_round(self):
        q=[0]*128;keys=[0]*128
        q[:2]=[0x00010000,0x00010000]
        keys[:2]=[0x37000000,0x37800000] # high=minsubnormal, low=half-minsubnormal.
        self.assertEqual(dot128(q,keys),2)
        first=rounded(exact(q[1])*exact(keys[1]))
        unfused=rounded(exact(rounded(exact(q[0])*exact(keys[0])))+exact(first))
        self.assertEqual(unfused,1)
        self.assertEqual(rounded(Fraction(1,1<<150)),0)
        self.assertEqual(rounded(Fraction(3,1<<150)),2)

    def test_fused_cancellation_and_nearest_even(self):
        a,b,c=0x3f800001,0x3f7ffffe,0xbf800000
        self.assertEqual(fma_word(a,b,c),0xa8800000)
        self.assertEqual(rounded(exact(rounded(exact(a)*exact(b)))+exact(c)),0)
        self.assertEqual(rounded(Fraction(1)+Fraction(1,1<<24)),0x3f800000)
        self.assertEqual(rounded(Fraction(1)+Fraction(3,1<<24)),0x3f800002)

    def test_signed_zero_and_exact_cancellation(self):
        self.assertEqual(fma_word(0x80000000,0x3f800000,0x80000000),0x80000000)
        self.assertEqual(fma_word(0x80000000,0x3f800000,0),0)
        self.assertEqual(fma_word(0xbf800000,0x3f800000,0x3f800000),0)
        q=[0x80000000]*128;keys=[0x3f800000]*128
        q[1]=0x80010000;keys[1]=0x37000000
        self.assertEqual(dot128(q,keys),0x80000000)

    def test_fixture_shape_type_and_nonfinite_guards(self):
        for q,keys in (([0]*127,[0]*128),([0]*128,[0]*129),([True]+[0]*127,[0]*128),
                       ([0x7f800000]+[0]*127,[0]*128),([0x7fc00000]+[0]*127,[0]*128),
                       ([0x3f800001]+[0]*127,[0]*128)):
            with self.subTest(q=q[:1],size=len(q)),self.assertRaises(ValueError):dot128(q,keys)
        for word in (0,0x80000000,1,0x80000001,0x007fffff,0x00800000,0x3f800000,0x7f7fffff):
            self.assertEqual(rounded(exact(word),negative_zero=word==0x80000000),word)


class SourceQkTests(unittest.TestCase):
    def test_cpp_exact_raw_128_high_then_low_scope_and_bounds(self):
        raw=k.source_bytes()
        self.assertIn(b'extern "C" int qk_pair(int rows,const float* q,const float* repeated_k,float* output) noexcept',raw)
        self.assertIn(b'if(rows!=16 && rows!=128)return 1;',raw)
        self.assertIn(b'const size_t count=size_t(12)*rows*128,oc=size_t(12)*rows*rows;',raw)
        self.assertIn(b'float sum=0.0f;',raw)
        self.assertIn(b'for(int pair=0;pair<64;pair++)',raw)
        high=b'sum=std::fma(qrow[low+1],krow[low+1],sum);'
        low=b'sum=std::fma(qrow[low],krow[low],sum);'
        self.assertEqual(raw.count(b'std::fma('),2);self.assertLess(raw.index(high),raw.index(low))
        self.assertIn(b'(size_t(head)*rows+column)*128',raw)
        self.assertIn(b'result[(size_t(head)*rows+row)*rows+column]=sum;',raw)
        for foreign in (b'sqrt',b'bias',b'bf(',b'torch',b'numpy',b'matmul',b'RESULT',b'1024',b'512'):
            self.assertNotIn(foreign,raw)
        self.assertNotIn(b'/',raw) # no scaling, alternate divides, or source comments.
        self.assertEqual(k.FLAGS,k.previous.FLAGS)

    def test_cpp_rejections_precede_transactional_output_copy(self):
        raw=k.source_bytes()
        for guard in (b'!q || !repeated_k || !output',b'))&3u',b'std::fegetround()!=FE_TONEAREST',
                      b'_mm_getcsr()&0xe040u',b'overlaps(output,oc,q,count)',
                      b'overlaps(output,oc,repeated_k,count)',b'overlaps(q,count,repeated_k,count)',
                      b'!valid(q,count) || !valid(repeated_k,count)',b'!std::isfinite(sum)'):
            self.assertLess(raw.index(guard),raw.index(b'std::copy(result.begin(),result.end(),output)'))
        self.assertIn(b'if(x>UINTPTR_MAX-an*4 || y>UINTPTR_MAX-bn*4)return true;',raw)
        self.assertIn(b'!std::isfinite(values[i]) || (bits(values[i])&0xffffu)',raw)
        self.assertEqual(raw.count(b'std::copy('),1)
        self.assertIn(b'std::vector<float> result(oc);',raw)
        self.assertIn(b'}catch(...){return 6;}',raw)
        self.assertEqual(12*128*128*4,786432) # maximum transactional scratch bytes.

    def test_original_bounded_compiler_and_elf_machinery_preserved(self):
        old=ast.parse(Path(k.previous.__file__).read_text())
        new=ast.parse(Path(k.__file__).read_text().replace('COMPILED_QK_RECIPE','COMPILED_QKV_RECIPE'))
        oldf={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
        newf={n.name:n for n in new.body if isinstance(n,ast.FunctionDef)}
        for name in ('sha','digest','encoded','safe_path','read','source','compiler_identity',
                     '_atomic','_remaining','_compile','verify','build'):
            self.assertEqual(ast.dump(oldf[name]),ast.dump(newf[name]),name)
        self.assertEqual((k.TOTAL,k.GRACE),(30,5))
        self.assertEqual(k.OLD_PINS_SHA256,k.previous.source_snapshot()['pins_sha256'])

    def test_real_closure_keeps_all_frozen_qkv_sources(self):
        frozen=k.source_snapshot();old=k.previous.source_snapshot()
        self.assertEqual(len(k.SOURCE_PATHS),18)
        self.assertEqual(len(frozen['source_sha256']),19)
        self.assertTrue(all(frozen['source_sha256'][n]==h for n,h in old['source_sha256'].items()))
        self.assertEqual(frozen['cpp_sha256'],k.sha(k.source_bytes()))
        self.assertEqual(frozen['source_sha256'][k.PREFIX+'kernel.py'],k.IMPORTED_SHA256)


class KernelControlTests(unittest.TestCase):
    def fixture(self,out):
        """Synthetic ELF header and metadata only; never loaded or executed."""
        from . import kernel as k
        source=k.source_bytes();(out/k.CPP).write_bytes(source)
        binary=bytearray(64);binary[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',binary,16,3,62)
        (out/k.LIBRARY).write_bytes(binary)
        frozen=dict(source_sha256={'CONTROL_ONLY/source.py':'a'*64},pins_sha256='b'*64,
            cpp_sha256=k.sha(source),generated_module_sha256='c'*64)
        compiler=dict(path='/CONTROL_ONLY/g++',sha256='d'*64)
        value=dict(schema=1,profile=k.PROFILE,status='COMPILED_QK_RECIPE',returncode=0,
            numerical_execution=False,official_framework_acceptance=False,**frozen,compiler=compiler,
            argv=[compiler['path'],*k.FLAGS,str(out/k.CPP),'-o',str(out/k.LIBRARY)],
            library_sha256=k.sha(binary),elapsed_seconds=0.1,total_budget_seconds=k.TOTAL)
        (out/k.RECEIPT).write_bytes(k.encoded(value))
        return k,frozen,compiler,value

    def test_synthetic_library_receipt_metadata_and_identity_postflight(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,value=self.fixture(out)
            with patch.object(k,'source_snapshot',return_value=frozen),patch.object(k,'compiler_identity',return_value=compiler):
                result=k.verify(out)
            self.assertEqual(result['library_path'],str(out/k.LIBRARY))
            self.assertEqual(result['receipt_sha256'],k.sha((out/k.RECEIPT).read_bytes()))
            self.assertEqual(result['source_sha256'],frozen['source_sha256'])
            for field,changed in (('source',dict(frozen,pins_sha256='e'*64)),('compiler',dict(compiler,sha256='e'*64))):
                with self.subTest(field=field),patch.object(k,'source_snapshot',
                        side_effect=[frozen,changed] if field=='source' else [frozen,frozen]), \
                        patch.object(k,'compiler_identity',side_effect=[compiler,changed] if field=='compiler' else [compiler,compiler]), \
                        self.assertRaises(ValueError):k.verify(out)

    def test_receipt_type_flag_hash_and_nonfinite_negatives(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,good=self.fixture(out)
            cases=[]
            for key,bad in (('schema',True),('returncode',False),('numerical_execution',0),
                    ('official_framework_acceptance',0),('elapsed_seconds',True),('elapsed_seconds',float('inf')),
                    ('elapsed_seconds',-1),('elapsed_seconds',31),('total_budget_seconds',30.0),
                    ('library_sha256','0'*64),('pins_sha256','0'*64),('cpp_sha256','0'*64),
                    ('generated_module_sha256','0'*64),('status','PASS')):
                value=deepcopy(good);value[key]=bad;cases.append(value)
            value=deepcopy(good);value['argv'].append('-ffast-math');cases.append(value)
            value=deepcopy(good);value['compiler']['sha256']='0'*64;cases.append(value)
            value=deepcopy(good);value['extra']='CONTROL_ONLY';cases.append(value)
            value=deepcopy(good);del value['source_sha256'];cases.append(value)
            for index,value in enumerate(cases):
                (out/k.RECEIPT).write_text(json.dumps(value))
                with self.subTest(case=index),patch.object(k,'source_snapshot',return_value=frozen), \
                        patch.object(k,'compiler_identity',return_value=compiler),self.assertRaises(ValueError):k.verify(out)

    def test_library_source_binary_symlink_and_bounded_json_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);k,frozen,compiler,value=self.fixture(out)
            for kind in ('cpp','elf','hash','symlink','receipt_size','duplicate','nonfinite','overflow'):
                self.fixture(out)
                if kind=='cpp':(out/k.CPP).write_bytes(k.source_bytes()+b'\n')
                elif kind=='elf':(out/k.LIBRARY).write_bytes(b'CONTROL_ONLY'*6)
                elif kind=='hash':
                    raw=bytearray((out/k.LIBRARY).read_bytes());raw[-1]=1;(out/k.LIBRARY).write_bytes(raw)
                elif kind=='symlink':
                    (out/'link').write_bytes((out/k.LIBRARY).read_bytes());(out/k.LIBRARY).unlink();(out/k.LIBRARY).symlink_to(out/'link')
                elif kind=='receipt_size':(out/k.RECEIPT).write_bytes(b' '*131073)
                elif kind=='duplicate':(out/k.RECEIPT).write_bytes(b'{"schema":1,"schema":1}')
                elif kind=='nonfinite':(out/k.RECEIPT).write_bytes(b'{"x":NaN}')
                else:(out/k.RECEIPT).write_bytes(b'{"x":1e999}')
                with self.subTest(kind=kind),patch.object(k,'source_snapshot',return_value=frozen), \
                        patch.object(k,'compiler_identity',return_value=compiler),self.assertRaises(ValueError):k.verify(out)
                if (out/k.LIBRARY).is_symlink():(out/k.LIBRARY).unlink()
        for execute in (False,0,1,None,'yes'):
            with patch.object(k,'source_snapshot') as snapshot,self.subTest(execute=execute),self.assertRaises(ValueError):
                k.build('/CONTROL_ONLY/no-build',execute=execute)
            snapshot.assert_not_called()
        with patch.object(k,'source_snapshot') as snapshot,self.assertRaises(TimeoutError):
            k.build('/CONTROL_ONLY/no-build',execute=True,deadline_ns=time.monotonic_ns()-1)
        snapshot.assert_not_called()

    def test_sleep_only_process_group_timeout_kills_and_reaps(self):
        from . import kernel as k
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);pids=out/'control_pids';processes=[];real_popen=subprocess.Popen
            code=("import os,signal,time;from pathlib import Path;"
                  "signal.signal(signal.SIGTERM,signal.SIG_IGN);child=os.fork();"
                  f"Path({str(pids)!r}).write_text(str(os.getpid())+' '+str(child)) if child else None;"
                  "time.sleep(60)")
            def spawn(*args,**kwargs):
                process=real_popen(*args,**kwargs);processes.append(process);return process
            started=time.monotonic()
            try:
                with patch.object(k,'GRACE',0.05),patch.object(k.subprocess,'Popen',side_effect=spawn):
                    with self.assertRaises((TimeoutError,subprocess.TimeoutExpired)):
                        k._compile([sys.executable,'-c',code],out,time.monotonic_ns()+1_300_000_000)
                self.assertLess(time.monotonic()-started,2.0)
                self.assertTrue(pids.is_file(),'sleep-only child did not initialize')
                self.assertIsNotNone(processes[0].returncode,'direct child was not reaped')
                for pid in map(int,pids.read_text().split()):
                    state=Path('/proc')/str(pid)/'stat'
                    try:observed=state.read_text().split(') ')[1].split()[0]
                    except (FileNotFoundError,ProcessLookupError):observed=None
                    self.assertIn(observed,(None,'Z'))
            finally:
                for process in processes:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=0.5)


def smoke_vectors():
    """Seven independent raw BF16 vectors on each side; no model tensors."""
    one=0x3f800000
    q=[[one]*128,[0]*128,[0x80000000]*128,
       [one,0xbf800000,0x3f000000,0xbe800000]*32,[0]*128,[0]*128,[0]*128]
    keys=[[0]*128,[0]*128,[0]*128,[one]*128,[one]*128,
          [0x3f000000,one,0xbf800000,0x3e800000]*32,[0]*128]
    q[1][:2]=[0x00010000,0x00010000]
    q[2][1]=0x80010000
    q[4][0]=one;q[5][127]=one
    keys[0][:4]=[one,0,0xbf800000,0x33800000]
    keys[1][:2]=[0x37800000,one]
    keys[2][:2]=[0x37000000,0x37800000]
    keys[3][1]=0x37000000
    return q,keys


def run_native_smoke(out):
    """Explicit opt-in only, never called by discovery.

    The authorized caller must impose one external30s ceiling, including build.
    This tests synthetic ABI/results only, not either complete native model gate.
    """
    import ctypes
    started=time.monotonic_ns();deadline=started+30_000_000_000
    def need(ok):
        if not ok:raise ValueError('isolated raw QK synthetic check')
        if time.monotonic_ns()>=deadline:raise TimeoutError('isolated QK deadline')
    receipt=k.build(out,execute=True,deadline_ns=deadline)
    need(k.verify(out)==receipt)
    library=ctypes.CDLL(receipt['library_path']);function=library.qk_pair
    pointer=ctypes.POINTER(ctypes.c_float)
    function.argtypes=[ctypes.c_int,pointer,pointer,pointer];function.restype=ctypes.c_int
    qvectors,kvectors=smoke_vectors()
    expected={(a,b):dot128(qvectors[a],kvectors[b]) for a in range(7) for b in range(7)}
    need(expected[0,0]==0 and expected[0,1]==0x3f800080 and expected[1,2]==2 and expected[2,3]==0x80000000)
    need(dot128(qvectors[0],kvectors[0],high_first=False)==0x33800000)
    calls=0;digests={};words=0
    def pointer_of(value):return ctypes.cast(value,pointer)
    def call(rows,q,keys,output):
        nonlocal calls
        need(True);code=function(rows,pointer_of(q),pointer_of(keys),pointer_of(output));calls+=1;need(True);return code
    for rows in (16,128):
        count=12*rows*128;oc=12*rows*rows
        q=(ctypes.c_uint32*count)();keys=(ctypes.c_uint32*count)();output=(ctypes.c_uint32*oc)()
        for head in range(12):
            for row in range(rows):
                offset=(head*rows+row)*128
                q[offset:offset+128]=qvectors[(head+row)%7]
                keys[offset:offset+128]=kvectors[(3*head+row)%7]
        need(call(rows,q,keys,output)==0)
        wanted=[expected[(head+row)%7,(3*head+column)%7]
                for head in range(12) for row in range(rows) for column in range(rows)]
        need(list(output)==wanted)
        actual=ctypes.string_at(ctypes.addressof(output),ctypes.sizeof(output))
        need(k.sha(actual)==k.sha(b''.join(struct.pack('<I',word) for word in wanted)))
        digests[str(rows)]=k.sha(actual);words+=oc
    # Small rows retain the same ABI with bounded negative-call scratch.
    rows=16;count=12*rows*128;oc=12*rows*rows
    q=(ctypes.c_uint32*count)(*([0x3f800000]*count))
    keys=(ctypes.c_uint32*count)(*([0x3f800000]*count))
    output=(ctypes.c_uint32*oc)();sentinel=0x7fc12345
    rejected=0
    def reject(code,*,m=rows,a=q,b=keys,y=output):
        nonlocal rejected
        output[:]=[sentinel]*oc
        before_q=bytes(q);before_keys=bytes(keys)
        need(call(m,a,b,y)==code)
        need(all(word==sentinel for word in output))
        need(bytes(q)==before_q and bytes(keys)==before_keys);rejected+=1
    for invalid in (-1,0,1,15,17,127,129):reject(1,m=invalid)
    reject(2,a=None);reject(2,b=None);reject(2,y=None)
    reject(2,a=ctypes.addressof(q)+1)
    reject(2,y=q);reject(2,y=keys);reject(2,b=q)
    reject(2,y=ctypes.addressof(q)+4)
    reject(2,a=(1<<(ctypes.sizeof(ctypes.c_void_p)*8))-4)
    for invalid in (0x3f800001,0x7f800000,0x7fc00000):
        saved=q[0];q[0]=invalid
        try:reject(4)
        finally:q[0]=saved
    saved_q,saved_k=q[-1],keys[-1];q[-1]=keys[-1]=0x7f7f0000
    try:reject(5)
    finally:q[-1]=saved_q;keys[-1]=saved_k
    process=ctypes.CDLL(None)
    need(hasattr(process,'fegetround') and hasattr(process,'fesetround'))
    process.fegetround.argtypes=[];process.fegetround.restype=ctypes.c_int
    process.fesetround.argtypes=[ctypes.c_int];process.fesetround.restype=ctypes.c_int
    previous=process.fegetround();need(previous==0)
    try:
        need(process.fesetround(0x400)==0)  # x86-64 FE_DOWNWARD, restore unconditionally.
        reject(3)
    finally:need(process.fesetround(previous)==0)
    need(k.verify(out)==receipt)
    elapsed=(time.monotonic_ns()-started)/1e9;need(0<=elapsed<30)
    return dict(status='PASS_ISOLATED_QK_SYNTHETIC_ONLY',rows=[16,128],heads=12,depth=128,
        output_words=words,fixture_pairs=49,native_calls=calls,rejected_calls=rejected,fenv_checks=1,
        output_sha256=digests,elapsed_seconds=elapsed,compile_returncode=0,kernel_returncode=0,
        library_sha256=receipt['library_sha256'],cpp_sha256=receipt['cpp_sha256'],pins_sha256=receipt['pins_sha256'],
        source_manifest_sha256=k.sha(k.encoded(receipt['source_sha256'])),
        full_native_m16=False,full_native_m128=False,official_framework_acceptance=False,rtl_execution=False)


if __name__=='__main__':unittest.main()
