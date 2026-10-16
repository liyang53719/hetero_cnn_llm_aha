"""Cold synthetic capture tests; no payload, native library, model or reference run."""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from .capture import PackedFields, FIELDS, SENTINEL
from . import monitor
from ..official_bf16.observation import OfficialAttentionObservation
from ..attention_packed_owner.schedule import PackedSchedule
from ..attention_packed_owner.client import PackedRequest, PackedResult, PackedTag, PackedConsumerAck
from ..attention_packed_owner.protocol import ScratchAction, ScratchResponse
from ..ffn_attention.attention_owner import AttentionOwner


def fill(rows):
    result = PackedFields(rows)
    for name,f in result.fields.items():
        for h in range(12):
            for t in range(rows):
                if name in ('normalizer','pv_raw','pv_bf16'):
                    width = 3 if name == 'normalizer' else 128
                    result._put(name,(h,t,0),tuple(0x3f000000+i+h*256+t*4096 for i in range(width)))
                else:
                    for k in range(t+1):
                        c=(h,t,k);width=16 if name=='dot_parts' else 1
                        result._put(name,c+(0,) if width==16 else c,
                                    tuple(0x3f000000+i+h*256+t*4096+k*65536 for i in range(width)))
    return result


class FieldsTests(unittest.TestCase):
    def test_exact_fields_and_causal_masks(self):
        for rows in (1,2,16):
            capture=fill(rows)
            self.assertEqual(tuple(capture.fields),FIELDS)
            self.assertTrue(capture.coverage())
            self.assertFalse(any(f['repeats'] for f in capture.fields.values()))

    def test_legacy_numerical_bytes_equal_explicit_frequency_differs(self):
        for rows in (1,2,16):
            packed=fill(rows)
            legacy=object.__new__(OfficialAttentionObservation)
            legacy.owner=SimpleNamespace(job=SimpleNamespace())
            legacy.fields=deepcopy(packed.fields)
            # Rebuild legacy expected frequencies without changing numerical words.
            for name,f in legacy.fields.items():
                f['frequency']=type(f['frequency'])('H',[0])*len(f['frequency'])
                f['observed']=bytearray(len(f['observed'])); f['writes']=f['repeats']=0
                shape=f['shape']
                for h in range(12):
                    for t in range(rows):
                        if name in ('normalizer','pv_raw','pv_bf16'):
                            width=3 if name=='normalizer' else 128
                            repeat=8*(t+1) if name=='normalizer' else 1
                            start=(h*rows+t)*width
                            for _ in range(repeat):legacy._put(name,(h,t,0),tuple(packed.fields[name]['words'][start:start+width]))
                        else:
                            width=16 if name=='dot_parts' else 1
                            repeat=8 if name in ('softmax_fp32','prob_bf16') else 1
                            for k in range(t+1):
                                start=(h*rows*rows+t*rows+k)*width;c=(h,t,k)
                                for _ in range(repeat):legacy._put(name,c+(0,) if width==16 else c,
                                    tuple(packed.fields[name]['words'][start:start+width]))
                self.assertEqual(packed._bytes(name),legacy._bytes(name))
                self.assertEqual(bytes(packed.fields[name]['observed']),bytes(f['observed']))
                if name in ('normalizer','softmax_fp32','prob_bf16'):
                    self.assertNotEqual(packed._bytes(name,'frequency'),legacy._bytes(name,'frequency'))
                else:self.assertEqual(packed._bytes(name,'frequency'),legacy._bytes(name,'frequency'))

    def test_geometry_rejects(self):
        for value in (True,False,0,3,15,17,128,1.0,'16',None):
            with self.assertRaises(ValueError):PackedFields(value)

    def test_missing_each_field_fails(self):
        for name in FIELDS:
            c=fill(2);f=c.fields[name];f['observed'][0]=f['frequency'][0]=0;f['words'][0]=SENTINEL;f['writes']-=1
            self.assertFalse(c.coverage(),name)

    def test_duplicate_future_wrong_word_and_cross_row_rejected(self):
        c=PackedFields(2)
        for name,coordinates,values in [('scores_bf16',(0,0,1),(1,)),('dot_parts',(0,0,0,15),(1,2)),
                                       ('pv_raw',(0,0,0),(True,)),('pv_raw',(0,0,0),(-1,)),
                                       ('pv_raw',(0,0,0),(1<<32,)),('nope',(0,0,0),(1,))]:
            with self.assertRaises(ValueError):c._put(name,coordinates,values)
        c._put('scores_bf16',(0,0,0),(1,))
        with self.assertRaises(ValueError):c._put('scores_bf16',(0,0,0),(1,))

    def test_all_frequency_presence_counter_mutations_fail(self):
        for name in FIELDS:
            for kind in ('frequency','observed','writes','repeats'):
                c=fill(2)
                if kind in ('frequency','observed'):c.fields[name][kind][0]=2
                else:c.fields[name][kind]+=1
                self.assertFalse(c.coverage(),(name,kind))

    def test_future_sentinel_corruption_fails(self):
        c=fill(2);c.fields['scores_bf16']['words'][1]=0
        self.assertFalse(c.coverage())

    def test_pending_scalar_blocks_coverage(self):
        c=fill(1);c.pending_dot={}
        self.assertFalse(c.coverage())
        c.pending_dot=None;c.pending_prob={}
        self.assertFalse(c.coverage())

    def test_source_point_drift_rejected(self):
        source=(monitor.ROOT/monitor.SCHEDULE).read_text()
        self.assertEqual(set(monitor.capture_points(source)),set(monitor.POINTS))
        for statement in monitor.POINTS.values():
            # Mutate the entire method AST, retaining parseability.
            tree=ast.parse(source)
            target=ast.dump(ast.parse(statement).body[0],include_attributes=False)
            class Change(ast.NodeTransformer):
                def visit(self,node):
                    if isinstance(node,ast.stmt) and ast.dump(node,include_attributes=False)==target:
                        return ast.Pass()
                    return super().visit(node)
            altered=ast.unparse(Change().visit(tree))
            with self.assertRaises(ValueError):monitor.capture_points(altered)

    def test_incomplete_dot_sequence_rejects(self):
        local=dict(head=0,token=0,key=0,total=1,lanes=(2,)*16,score=3,scores=[3])
        c=PackedFields(1);c.begin_dot(local)
        with self.assertRaises(ValueError):c.end_dot(local)
        with self.assertRaises(ValueError):c.dot_return('mul',1,0,3)

    def test_incomplete_probability_sequence_rejects(self):
        local=dict(token=0,kv=0,key=0,panel=[(1,)]*6,inverses=[2]*6,a=(0,)*16)
        c=PackedFields(1);c.begin_probability(local)
        with self.assertRaises(ValueError):c.end_probability(local)
        with self.assertRaises(ValueError):c.probability_return(local,1,'mul',1,2,3)


class SyntheticScalar:
    # Deliberately not a numerical oracle. Values merely exercise actual return
    # routing and source-bound capture; all are deterministic finite uint32.
    def op(self,client,operation,a,b=0,*,policy='vector'):
        if operation=='bf':return a & 0xffff0000
        if operation=='div':return 0x3f800000
        if operation in ('add','mul'):return 0x3f000000 | ((a^b)&0x007f0000)
        if operation=='sub':return 0x3f000000
        raise ValueError(operation)


class SyntheticOwner:
    _op=AttentionOwner._op
    def __init__(self):
        self.scalar=SyntheticScalar();self.scalar.client=self;self.row_words=self.peak_row_words=self.useful_macs=0
        self.counts={'exp_negative_requests':0}
    def _read(self,address):
        return (yield ('read',address))
    def _write(self,address,words):
        yield ('write',address,words)
    def _less(self,a,b):return a==0xff800000 or a<b


@unittest.skipUnless(sys.version_info[:2]==(3,12) and not sys.flags.optimize,'live monitoring requires original CPython mode')
class LiveScheduleTests(unittest.TestCase):
    def execute(self,rows):
        owner=SyntheticOwner();schedule=PackedSchedule();schedule.bind(owner)
        code=schedule.run.__func__.__code__;points=monitor.capture_points((monitor.ROOT/monitor.SCHEDULE).read_text())
        o=object.__new__(monitor.PackedAttentionMonitoringObservation)
        o.owner=owner;o.services=(None,owner.scalar,schedule);o.codes=dict(run=code,op=owner._op.__func__.__code__,tick=None)
        o.prob_code=next(c for c in code.co_consts if hasattr(c,'co_name') and c.co_name=='<genexpr>' and c.co_firstlineno==points['prob'])
        o.points=points;o.thread=__import__('threading').get_ident();o.active=True;o.closed=o.disarmed=False
        o.started=1;o.error=None;o.capture=PackedFields(rows);o.fields=o.capture.fields
        o.tool_id=None;o._configured={};o._registered={};o.tool_name='synthetic-packed-capture'
        ident=next(i for i in (3,4) if sys.monitoring.get_tool(i) is None)
        sys.monitoring.use_tool_id(ident,o.tool_name);o.tool_id=ident
        callbacks=((sys.monitoring.events.LINE,o._line),(sys.monitoring.events.PY_RETURN,o._return))
        for event,callback in callbacks:
            self.assertIsNone(sys.monitoring.register_callback(ident,event,callback));o._registered[event]=callback
        for target,event in ((code,sys.monitoring.events.LINE),(o.codes['op'],sys.monitoring.events.PY_RETURN)):
            sys.monitoring.set_local_events(ident,target,event);o._configured[target]=event
        job=SimpleNamespace(m=rows,a=0,b=1<<20,c=2<<20,dst=3<<20)
        gen=schedule.run(owner,job);response=None;scratch={};serial=0
        try:
            while True:
                try:request=gen.send(response)
                except StopIteration:break
                if type(request) is ScratchAction:
                    if request.operation=='write':scratch[request.line]=request.words
                    response=ScratchResponse(request,scratch[request.line] if request.operation=='read' else (),False)
                elif type(request) is PackedRequest:
                    if request.last:
                        serial+=1;tag=PackedTag(1,serial,serial,1)
                        matrix=tuple(tuple(0x3f000000+((r*256+c)&0x7fff) for c in range(256)) for r in range(16))
                        result=SimpleNamespace(value=matrix,error=False)
                        response=PackedResult(tag,result,request.selected)
                    else:response=None
                elif type(request) is PackedConsumerAck:response=None
                elif request[0]=='read':response=(0x3f000000,)*16
                elif request[0]=='write':response=None
                else:self.fail('unknown synthetic request')
            self.assertIsNone(o.error)
            self.assertTrue(o.capture.coverage())
            return o.capture
        finally:o._stop()

    def test_real_m1_schedule_capture(self):self.execute(1)
    def test_real_m2_schedule_capture(self):self.execute(2)

    def test_production_constructor_rejects_synthetic_owner(self):
        with self.assertRaises(ValueError):monitor.PackedAttentionMonitoringObservation(SyntheticOwner(),source_sha256={})


if __name__=='__main__':unittest.main()
