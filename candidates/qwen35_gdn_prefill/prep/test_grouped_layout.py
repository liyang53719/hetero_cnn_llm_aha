"""Actual synthetic transport/compute for35B grouped heads; no checkpoint/RTL."""
import struct
import json,hashlib
import time
import unittest
from dataclasses import replace
import numpy as np
from . import model as m
from .layout import PrepLayout, EQUAL_HEADS, GROUPED_35B as L
from .scalar import PrepScalar
from .test_model import bf,produced
from . import reference


def fixed_grouped(conv,ab,alog,bias,rows):
    # Independent array mapping, never calls the candidate address helper.
    c=np.frombuffer(conv,'<u2').reshape(rows,8192)
    q=np.repeat(c[:,:2048].reshape(rows,16,128),2,axis=1)
    k=np.repeat(c[:,2048:4096].reshape(rows,16,128),2,axis=1)
    v=c[:,4096:].reshape(rows,32,128)
    a=np.frombuffer(ab,'<u2').reshape(rows,2,32)
    out=np.zeros((rows,12800),'<u4')
    for group in range(2):
        first=group*16;last=first+16
        mixed=np.concatenate([x[:,first:last].reshape(rows,2048) for x in (q,k,v)],axis=1).tobytes()
        gates=a[:,:,first:last].copy().tobytes()
        raw,_=reference.fixed_prep(mixed,gates,alog[group*64:(group+1)*64],bias[group*32:(group+1)*32]+bytes(32),rows)
        local=np.frombuffer(raw,'<u4').reshape(rows,6400)
        for role in range(3):out[:,role*4096+first*128:role*4096+last*128]=local[:,role*2048:(role+1)*2048]
        out[:,12288+first*16:12288+last*16]=local[:,6144:]
    return out.tobytes()


class GroupedLayoutTests(unittest.TestCase):
    def setup_driver(self,rows=1):
        memory=m.TypedMemory();scalar=PrepScalar(enable_softplus=True)
        owner=m.InputPrepOwner(scalar,heads=32,layout=L)
        vectors=[]
        for role,count in ((0,16),(1,16),(2,32)):
            for h in range(count):vectors += [(.125*(h+1)),(-.25 if h%2 else .25)]+[0.]*126
        conv=bf(vectors)*rows
        ab=bf([h/64-.2 for h in range(32)]+[h/32-.4 for h in range(32)])*rows
        alog=struct.pack('<32f',*[h/64-.25 for h in range(32)])
        bias=bf([h/128-.1 for h in range(32)])
        produced(memory,0x100000,conv);produced(memory,0x400000,ab)
        memory.add_readonly(0x410000,alog);memory.add_readonly(0x420000,bias)
        memory.allocate_output(0x800000,rows*L.core_row_bytes)
        job=m.InputPrepJob(3581,0x100000,0x400000,0x410000,0x420000,0x800000,rows,32,L)
        return m.TypedInputPrepDriver(owner,memory,job)

    def finish(self,d,hook=None):
        reads=[];deadline=time.monotonic()+90
        for i in range(1000000):
            self.assertLess(time.monotonic(),deadline)
            ports=d.owner.ports();args={} if hook is None else hook(d,i)
            event=d.tick(**args)
            if event['memory_fire'] and not ports['memory'].write:reads.append(ports['memory'].address)
            if d.response is not None:return reads
        self.fail('bounded grouped transport')

    def test_m1_m128_actual_grouped_map_fixed_recipe_and_packet_counts(self):
        for rows in (1,128):
            with self.subTest(rows=rows):
                d=self.setup_driver(rows);source=tuple(x.raw() for x in d.sources)
                expected=fixed_grouped(*source,rows)
                reads=self.finish(d)
                self.assertIsNone(d.response.status);self.assertTrue(d.output.published)
                self.assertEqual(d.output.raw(),expected)
                report=d.report();owner=report['owner']
                self.assertEqual(report['counts']['read_bytes'],rows*(32*3*256+2*4*64))
                self.assertEqual(report['counts']['write_bytes'],rows*51200)
                self.assertEqual(owner['retained_parameter_elements'],64)
                self.assertEqual(owner['retained_fp32_head_capacity'],128)
                self.assertEqual(reads.count(d.job.a_log),rows)
                self.assertEqual(reads.count(d.job.a_log+64),rows)
                self.assertEqual(reads.count(d.job.dt_bias),2*rows)
                first=reads[:4];self.assertEqual(first,[d.job.a_log,d.job.dt_bias,d.job.ab,d.job.ab+64])
                x=np.frombuffer(d.output.raw(),'<u4').reshape(rows,12800)
                for role in (0,1):
                    heads=x[:,role*4096:(role+1)*4096].reshape(rows,32,128)
                    self.assertTrue(np.array_equal(heads[:,::2],heads[:,1::2]))
                    self.assertFalse(np.array_equal(heads[:,1],heads[:,2]))
                self.assertFalse(np.array_equal(x[:,8192:8320],x[:,8320:8448]))
                self.assertEqual(source,tuple(x.raw() for x in d.sources))
                self.assertFalse(report['history_committed']);self.assertFalse(report['state_committed'])
                self.assertIsNone(d.owner.scalar.client)
                print('GROUPED_PREP_CASE '+json.dumps(dict(tokens=rows,synthetic=True,checkpoint_payload_used=False,
                    fixed_recipe_bitexact=True,native_acceptance=False,rtl_executed=False,
                    output_sha256=hashlib.sha256(d.output.raw()).hexdigest(),source_identity=owner['identity'],
                    counts=report['counts'],scalar_calls=owner['scalar_calls'],
                    exp_internal_calls=owner['exp_internal_calls'],softplus_internal_calls=owner['softplus_internal_calls'],
                    qk_square_products_executed=rows*32*2*128,qk_unique_source_square_products=rows*16*2*128,
                    matrix_macs=0,vector_operations=0,scalar_units=1,
                    retained_parameter_elements=64,retained_fp32_head_capacity=128,
                    hardware_cycles=None,mac_utilization=None,busy_duty=None,lane_duty=None,
                    stall_breakdown=None,overlap_timeline=None),sort_keys=True),flush=True)

    def test_second_parameter_group_read_fault_drains_without_publication(self):
        d=self.setup_driver();fault=[]
        def hook(d,i):
            yes=d.pending is not None and d.owner.request.address==d.job.a_log+64
            if yes:fault.append(i)
            return dict(read_error=yes)
        self.finish(d,hook)
        self.assertEqual(len(fault),1);self.assertIsNotNone(d.response.status)
        self.assertFalse(d.output.published);self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client);self.assertTrue(d.owner.poison)
        self.assertEqual(d.owner.ack_bytes,16*(3*512+64))

    def test_final_ack_stall_and_error_keep_complete_span_unpublished(self):
        d=self.setup_driver();stalls=[]
        def hook(d,i):
            final=d.pending is not None and d.owner.request.write and d.owner.ack_bytes+64==d.job.write_bytes
            if final and len(stalls)<3:
                stalls.append(i);self.assertFalse(d.output.published)
                return dict(memory_response_ready=False)
            return dict(ack_error=final)
        self.finish(d,hook)
        self.assertEqual(len(stalls),3);self.assertIsNotNone(d.response.status)
        self.assertFalse(d.output.published);self.assertIsNone(d.memory.pending)
        self.assertIsNone(d.owner.scalar.client)

    def test_explicit_geometry_rejects_bad_or_mixed_profiles(self):
        self.assertEqual([L.source_head(0,h) for h in (0,1,2,31)],[0,0,1,15])
        self.assertEqual(L.source_head(2,31),31)
        with self.assertRaises(ValueError):PrepLayout(16,24)
        with self.assertRaises(ValueError):PrepLayout(True,32)
        d=self.setup_driver()
        with self.assertRaises(ValueError):replace(d.job,layout=EQUAL_HEADS).validate(32,L)
        with self.assertRaises(ValueError):m.InputPrepOwner(PrepScalar(enable_softplus=True),heads=16,layout=L)
