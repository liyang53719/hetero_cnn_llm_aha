"""Synthetic bytes/mocks only; never read real arrays or run native work."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LOADER_PIN = (1180, '2161141538deb72a17e30ace874e7c955213d8e2f7017658a61ebba91f96a856')
IN_CONSUMER = False

def audit(event, args):
    if event.startswith(('socket.', 'subprocess.')) or event in ('os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','ctypes.dlopen'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy','torch','ctypes'):
        raise RuntimeError('COLD_NUMERIC_NATIVE_IMPORT_FORBIDDEN')
    if IN_CONSUMER and event == 'open':
        if type(args[2]) is int and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            raise RuntimeError('CONSUMER_WRITE_FORBIDDEN')
    if IN_CONSUMER and event in ('os.remove','os.rename','os.mkdir','os.rmdir','os.symlink','os.link'):
        raise RuntimeError('CONSUMER_MUTATION_FORBIDDEN')
sys.addaudithook(audit)
raw=(HERE/'load_compare.py').read_bytes()
if (len(raw),hashlib.sha256(raw).hexdigest()) != LOADER_PIN: raise RuntimeError('LOADER_PIN')
L=types.ModuleType('fixed_loader');exec(compile(raw,str(HERE/'load_compare.py'),'exec'),L.__dict__)
compare=L.load_compare(HERE)
C=types.SimpleNamespace(**compare.__globals__)
G=compare.__globals__

def valid_counts():
    c={**C.TEXT_FIELDS,**C.FIXED_INTS,'official_raw_numeric_pass':None,'full_block_pass':False,
       'n0_cycles':1000,'pc1_entry_edge':1000,'pc1_accept_edge':1002,'ack1_edge':100001,
       'total_cycles':100002,'pc1_complete_window_cycles':99000,'utilization_denominator':4096*99000,
       'matrix_stalls':7,'n0_read_bytes_pc1':786432,'wq_read_bytes_pc1':4718592}
    c['pc1_axi']={k:0 for k in C.AXI_KEYS}
    c['pc1_axi'].update(ars=1024,rlasts=1024,rbeats_expected=86016,rbeats=86016,aws=2048,bs=2048,
        wbeats_expected=12288,wbeats=12288,wbeats_committed=12288,strobed_bytes=786432)
    return c

class Counts(unittest.TestCase):
    def test_exact_schema(self): self.assertEqual(C.verify_counts(valid_counts())['ack1s'],1)
    def test_each_missing_field(self):
        for key in C.COUNT_KEYS:
            c=valid_counts();del c[key]
            with self.assertRaises(ValueError): C.verify_counts(c)
    def test_extra_field_rejected(self):
        c=valid_counts();c['claimed_complete']=True
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_ack0_missing(self):
        c=valid_counts();c['ack0s']=0
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_ack1_missing(self):
        c=valid_counts();c['ack1s']=0
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_partial_coverage(self):
        for key in ('qraw_values','qraw_bytes','qraw_committed_bytes','n0_committed'):
            c=valid_counts();c[key]-=1
            with self.assertRaises(ValueError): C.verify_counts(c)
    def test_b_is_2048_not_n0_12288(self):
        c=valid_counts();c['qraw_successful_b']=12288
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_all_integer_fields_reject_bool(self):
        for key in set(C.FIXED_INTS)|C.VARIABLE_INTS:
            c=valid_counts();c[key]=True
            with self.assertRaises(ValueError): C.verify_counts(c)
    def test_axi_reject_boolean(self):
        c=valid_counts();c['pc1_axi']['ar_stall']=False
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_write_debt(self):
        c=valid_counts();c['pc1_axi']['bs']-=1
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_read_debt(self):
        c=valid_counts();c['pc1_axi']['rbeats']-=1
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_bad_window(self):
        c=valid_counts();c['pc1_complete_window_cycles']-=1
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_more_macs_than_capacity(self):
        c=valid_counts();c.update(ack1_edge=1002,total_cycles=1003,pc1_complete_window_cycles=1,utilization_denominator=4096)
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_read_operand_not_covered(self):
        c=valid_counts();c['wq_read_bytes_pc1']+=64
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_numeric_authority_rejected(self):
        c=valid_counts();c['official_raw_numeric_pass']=True
        with self.assertRaises(ValueError): C.verify_counts(c)
    def test_json_duplicate_and_nan(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'[]'):
            with self.assertRaises(ValueError): C.decode(raw)

class Numerics(unittest.TestCase):
    def setUp(self): self.stop=time.monotonic()+10
    @staticmethod
    def packed(values,width=32): return b''.join(struct.pack('<I' if width==32 else '<Q',x) for x in values)
    def track(self,a,r,width=32):return C.math_track(self.packed(a),self.packed(r,width),width,len(a),self.stop)
    def test_zero_sign_separate(self):
        a=self.packed([0x80000000]);r=self.packed([0])
        t=C.typed_track(a,r,1,self.stop);m=self.track([0x80000000],[0])
        self.assertFalse(t['bit_exact']);self.assertEqual(m['max_ulp'],0);self.assertEqual(m['bit_equal_values'],0)
        self.assertIsNone(m['max_relative_over_nonzero_references'])
    def test_subnormal_exact_error(self):
        m=self.track([1],[0]);self.assertEqual(m['sum_abs_error_units_hex'],'1')
        self.assertEqual(m['nonzero_error_over_zero_reference_count'],1);self.assertEqual(m['max_ulp'],1)
    def test_fp32_error_mean(self):
        m=self.track([0x40000000,0x3f800000],[0x3f800000,0x3f800000])
        self.assertEqual(m['max_abs_error']['approx_f64'],1);self.assertEqual(m['mean_abs_error']['approx_f64'],.5)
        self.assertEqual(m['max_relative_over_nonzero_references']['approx_f64'],1)
    def test_fp64_ulp_exact_widening(self):
        m=self.track([0x3f800000],[0x3ff0000000000001],64)
        self.assertEqual(m['max_ulp'],1);self.assertEqual(m['max_abs_error']['approx_f64'],2**-52)
    def test_widen_general_edges(self):
        for b in (0,0x80000000,1,0x007fffff,0x00800000,0x3f800001,0x7f7fffff,0xff7fffff):
            expected=struct.unpack('<Q',struct.pack('<d',struct.unpack('<f',struct.pack('<I',b))[0]))[0]
            self.assertEqual(C.widen32(b),expected)
    def test_fp64_mean_underflow_keeps_exact_total(self):
        m=self.track([0,0],[1,0],64)
        self.assertEqual(m['sum_abs_error_units_hex'],'1')
        self.assertEqual(m['mean_abs_error']['approx_f64'],0.0)
    def test_nan_inf_rejected(self):
        for x in (0x7f800000,0xff800000,0x7fc00001):
            with self.assertRaisesRegex(ValueError,'NONFINITE'):self.track([x],[0])
        with self.assertRaises(ValueError):self.track([0],[0x7ff0000000000000],64)
    def test_last_element_not_truncated(self):
        m=self.track([0,0,1],[0,0,0]);self.assertEqual(m['max_abs_error_index'],2)
        t=C.typed_track(self.packed([0,0,1]),self.packed([0,0,0]),3,self.stop)
        self.assertEqual(t['first_mismatch_index'],2);self.assertEqual(t['mismatch_values'],1)
    def test_exact_aggregate_and_full_histogram(self):
        m=self.track([0x3f800000+i for i in (0,1,2,4,8,16,256)],[0x3f800000]*7)
        self.assertEqual(m['ulp_histogram_0_1_2to3_4to7_8to15_16to255_over255'],[1]*7)
        self.assertEqual(int(m['sum_abs_error_units_hex'],16),sum((0,1,2,4,8,16,256))<<126)
    def test_relative_overflow_is_explicit(self):
        m=self.track([0x7f7fffff],[1],64)
        self.assertIsNone(m['max_relative_over_nonzero_references']['approx_f64'])
        self.assertTrue(m['max_relative_over_nonzero_references']['overflow_f64'])
    def test_zero_error_nonzero_reference_index(self):
        m=self.track([0,0x3f800000],[0,0x3f800000]);self.assertEqual(m['max_relative_over_nonzero_references']['index'],1)
    def test_deadline(self):
        with self.assertRaises(TimeoutError): C.math_track(self.packed([0]),self.packed([0]),32,1,0)

class FileAndSource(unittest.TestCase):
    def test_samebuffer_pin(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(b'abc');pin=(3,hashlib.sha256(b'abc').hexdigest())
            self.assertEqual(C.read_fixed(p,3,time.monotonic()+5,pin),b'abc')
            p.write_bytes(b'abd')
            with self.assertRaises(ValueError):C.read_fixed(p,3,time.monotonic()+5,pin)
    def test_symlink_leaf_and_parent_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'dir').mkdir();p=root/'dir/x';p.write_bytes(b'x')
            (root/'x').symlink_to(p);(root/'link').symlink_to(root/'dir')
            for q in (root/'x',root/'link/x'):
                with self.assertRaises(OSError):C.read_fixed(q,1,time.monotonic()+5)
    def test_fifo_not_opened_blocking(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'fifo';os.mkfifo(p)
            with self.assertRaises(ValueError):C.read_fixed(p,1,time.monotonic()+5)
    def test_source_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'compare.py';p.write_bytes((HERE/'compare.py').read_bytes().replace(b'QRAW_B_RESPONSES = 2048',b'QRAW_B_RESPONSES = 2049'))
            with self.assertRaises(ValueError):L.load_compare(Path(t))
    def test_source_relocation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'compare.py';p.write_bytes((HERE/'compare.py').read_bytes())
            f=L.load_compare(Path(t));self.assertEqual(f.__globals__['N0_SHA'],C.N0_SHA)
    def test_read_race_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(b'abc');original=C.os.read;changed=[]
            def read(fd,count):
                value=original(fd,count)
                if not changed:
                    changed.append(True);p.write_bytes(b'abd')
                return value
            with mock.patch.object(C.os,'read',side_effect=read):
                with self.assertRaisesRegex(ValueError,'STABLE_SAME_BUFFER'):C.read_fixed(p,3,time.monotonic()+5)
    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):C.read_fixed(Path('relative'),1,time.monotonic()+5)

class FullMock(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.capture=root/'capture';self.reference=root/'reference'
        self.capture.mkdir();self.reference.mkdir()
        self.a=struct.pack('<I',0x3f800000)*C.COUNT;self.d=struct.pack('<Q',0x3ff0000000000000)*C.COUNT
        self.n0=b'\0'*C.BYTES
        (self.capture/'counts.json').write_text(json.dumps(valid_counts()))
        (self.capture/'actual_n0.f32le').write_bytes(self.n0);(self.capture/'actual_qraw.f32le').write_bytes(self.a)
        refs={}
        for leaf in C.REFERENCES:
            raw=self.d if 'f64' in leaf else self.a;(self.reference/leaf).write_bytes(raw)
            refs[leaf]=(len(raw),hashlib.sha256(raw).hexdigest())
        rr={'status':'COMPLETE_TWO_MODEL_DIAGNOSTIC','elements':C.COUNT,'official_raw_numeric_pass':None,
            'application_accuracy_pass':None,'typed_recipe_bit_exact_to_rtl':None,'rtl_executed':False,'nonfinite_count':0,
            'typed_fp32_sha256':refs['qraw.typed.f32le'][1],'math_fp32_sha256':refs['qraw.math.f32le'][1],
            'math_fp64_sha256':refs['qraw.math.f64le'][1]}
        raw=json.dumps(rr).encode();self.receipt=self.reference/'RESULT.json';self.receipt.write_bytes(raw)
        patch=mock.patch.dict(G,REFERENCES=refs,RECEIPT_PIN=(len(raw),hashlib.sha256(raw).hexdigest()),N0_SHA=hashlib.sha256(self.n0).hexdigest())
        patch.start();self.addCleanup(patch.stop)
    def go(self,stop=None):
        global IN_CONSUMER
        IN_CONSUMER=True
        try:return compare(self.capture,self.reference,self.receipt,shared_stop=time.monotonic()+60 if stop is None else stop)
        finally:IN_CONSUMER=False
    def test_full_196608_readonly_positive(self):
        r=self.go();self.assertEqual(r['elements'],196608);self.assertTrue(r['typed_reference']['bit_exact'])
        for track in ('mathematical_fp32','mathematical_fp64'):
            self.assertEqual(sum(r[track]['ulp_histogram_0_1_2to3_4to7_8to15_16to255_over255']),196608)
            self.assertEqual(r[track]['sum_abs_error_units_hex'],'0')
        self.assertIsNone(r['official_raw_numeric_pass']);self.assertIsNone(r['typed_recipe_bit_exact_to_rtl'])
        self.assertTrue(r['qualification']['caller_native_exit_cleanup_source_association_required'])
    def test_full_last_mismatch_is_observation_not_authority(self):
        (self.capture/'actual_qraw.f32le').write_bytes(self.a[:-4]+struct.pack('<I',0x3fc00000))
        r=self.go();self.assertFalse(r['typed_reference']['bit_exact'])
        self.assertEqual(r['typed_reference']['first_mismatch_index'],C.COUNT-1)
        self.assertEqual(r['mathematical_fp32']['max_abs_error']['approx_f64'],.5)
        self.assertIsNone(r['application_accuracy_pass'])
    def test_full_last_nonfinite_rejected(self):
        (self.capture/'actual_qraw.f32le').write_bytes(self.a[:-4]+struct.pack('<I',0x7fc00001))
        with self.assertRaisesRegex(ValueError,'NONFINITE_ARRAY_VALUE'):self.go()
    def test_local_cap_and_shared_cap_intersection(self):
        for shared,expected in ((100,60),(30,30)):
            seen=[]
            def typed(a,r,count,stop):
                seen.append(stop);raise RuntimeError('STOP_BEFORE_NUMERICS')
            with mock.patch.object(C.time,'monotonic',return_value=0),mock.patch.dict(G,typed_track=typed):
                with self.assertRaisesRegex(RuntimeError,'STOP_BEFORE_NUMERICS'):self.go(shared)
            self.assertEqual(seen,[expected])
    def test_wrong_n0(self):
        (self.capture/'actual_n0.f32le').write_bytes(b'X'+self.n0[1:])
        with self.assertRaisesRegex(ValueError,'FIXED_HASH'):self.go()
    def test_swapped_reference(self):
        p=self.reference/'qraw.math.f64le';p.write_bytes(b'X'+self.d[1:])
        with self.assertRaisesRegex(ValueError,'FIXED_HASH'):self.go()
    def test_reference_receipt_tamper(self):
        self.receipt.write_bytes(self.receipt.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.go()
    def test_partial_qraw(self):
        (self.capture/'actual_qraw.f32le').write_bytes(self.a[:-4])
        with self.assertRaisesRegex(ValueError,'FULL_QRAW_LENGTH'):self.go()
    def test_incomplete_capture_no_scan(self):
        c=valid_counts();c['ack1s']=0;(self.capture/'counts.json').write_text(json.dumps(c))
        with self.assertRaises(ValueError):self.go()
    def test_capture_changed_on_postflight(self):
        original=G['read_fixed'];calls=[]
        def read(path,*args,**kw):
            calls.append(path)
            if len(calls)==8:raise ValueError('POST_HASH_CHANGED')
            return original(path,*args,**kw)
        with mock.patch.dict(G,read_fixed=read):
            with self.assertRaisesRegex(ValueError,'POST_HASH_CHANGED'):self.go()
    def test_final_identity_work_cannot_cross_local_cap(self):
        now=[0];calls=[];original=G['identity']
        def identify(raw):
            calls.append(None)
            if len(calls)==9:now[0]=61
            return original(raw)
        with mock.patch.object(C.time,'monotonic',side_effect=lambda:now[0]),mock.patch.dict(G,identity=identify):
            with self.assertRaises(TimeoutError):self.go(100)
    def test_shared_deadline(self):
        with self.assertRaises(TimeoutError):self.go(0)
    def test_no_extra_timer(self):
        self.assertNotIn('signal',G)

if __name__=='__main__': unittest.main(verbosity=2)
