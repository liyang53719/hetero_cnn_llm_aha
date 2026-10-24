"""Bounded software transition tests; never imports production preludes or RTL."""
import argparse
import ast
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
import hashlib
import importlib.util
import json
import operator
from pathlib import Path
import struct
import sys
import types
import unittest

HERE = Path(__file__).resolve(strict=True).parent
sys.path.insert(0, str(HERE))
import control
import stream_client
for module in (control, stream_client):
    if Path(module.__file__).resolve(strict=True) != HERE / (module.__name__ + '.py'):
        raise ImportError('unexpected local model origin')
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--micro-root', type=Path)
args, rest = parser.parse_known_args()
sys.argv[:] = [sys.argv[0], *rest]
pins = json.loads((HERE/'SOURCE_PINS.json').read_text())
for rel, sha in pins['raw_sources'].items():
    if hashlib.sha256((args.source_root/rel).read_bytes()).hexdigest() != sha:
        raise ValueError('source mismatch: '+rel)
path = (args.micro_root or args.source_root/'candidates/qwen2_ordered_vector_fold')/'model.py'
if hashlib.sha256(path.read_bytes()).hexdigest() != pins['micro_model_sha256']:
    raise ValueError('micro model mismatch')
spec = importlib.util.spec_from_file_location('_pinned_micro', path)
micro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(micro)

def load(rel, names=None, env=None):
    tree = ast.parse((args.source_root/rel).read_text(), filename=rel)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and (names is None or n.name in names)]
    if names is not None and {n.name for n in nodes} != set(names):
        raise ValueError('missing reference definitions')
    module = types.ModuleType('_behavior_ref_'+str(len(sys.modules)))
    sys.modules[module.__name__] = module
    module.__dict__.update(Counter=Counter, Sequence=Sequence, dataclass=dataclass,
                          replace=replace, struct=struct, Fraction=Fraction,
                          lru_cache=lru_cache, operator=operator, unittest=unittest)
    module.__dict__.update({k:v for k,v in (env or {}).items() if not k.startswith('__')})
    exec(compile(ast.Module(body=nodes,type_ignores=[]),rel,'exec'),module.__dict__)
    return module

PK='candidates/qwen2_resident_matrix/'
ref=load(PK+'ffn_public/test_prefix_owners.py',('exact','rn','ref_add','ref_mul','ref_div','ref_bf'))
arith=load(PK+'attention_matrix_batch/test_model.py',('finite','ArithmeticFault','ExactScalar'),vars(ref))
mat=load(PK+'ffn_attention/matrix_service.py',('MatrixProtocolError','require','NormalGroup','NormalStep','_MatrixRow','MatrixValue','MatrixResult','MatrixDone'))
old=load(PK+'attention_packed_owner/client.py',env={**vars(mat),'ArithmeticFault':arith.ArithmeticFault})
fixture=load(PK+'attention_packed_owner/test_client.py',('_State','ScriptedService','pv','deliver','finish','ClientTests'),{**vars(mat),**vars(old),'ArithmeticFault':arith.ArithmeticFault})
OriginalServiceClientRegression = fixture.ClientTests

class Tile:
    def __init__(self, keys):
        self.keys, self.reads = keys, []
        self.value = self
    def __getitem__(self, row):
        outer = self
        class Row:
            def __getitem__(self, col):
                key, r = divmod(col, 16)
                if key >= len(outer.keys) or r != row:
                    raise AssertionError('inactive/unselected tile read')
                outer.reads.append((row,col))
                return outer.keys[key][row]
        return Row()

def baseline(keys):
    scalar=arith.ExactScalar(); scores=[]; maximum=0xff800000
    for j,values in enumerate(keys):
        try:
            if any(not arith.finite(x) for x in values):
                raise arith.ArithmeticFault('finite scan')
            a=0
            for word in values:a=scalar('add',a,word)
            dot=scalar('bf',a)
            if not arith.finite(dot):raise arith.ArithmeticFault('dot')
            score=scalar('bf',scalar('mul',dot,0x3db504f3))
            if not arith.finite(score):raise arith.ArithmeticFault('score')
            scores.append(score)
            if maximum==0xff800000 or ref.exact(maximum)<ref.exact(score):maximum=score
        except arith.ArithmeticFault:return scores,maximum,j
    return scores,maximum,None

def model(keys):
    c=stream_client.PackedAttentionStreamEdge(enabled=True)
    a=micro.OrderedVectorFold(arith.ExactScalar(),arith.finite,arith.ArithmeticFault,enabled=True)
    return control.OrderedController(c,a,len(keys)),Tile(keys)

def live(tile, **extra):
    return dict(port_result_valid=True,port_result_context=0,port_result_last=True,
                port_result_error=False,port_result_value=tile.value,tile=tile,**extra)

def issue(m):
    m.tick({});m.tick({'port_group_ready':True})
    for i in range(8):
        _,p=m.tick({'operands_valid':True,'operands_index':i,'port_step_ready':True})
        if not p['operands_fire']:raise AssertionError('step not accepted')
    if m.client.state!='awaitResult':raise AssertionError('not reachable awaitResult')

def advance(m,tile,state):
    for _ in range(80):
        if m.state==state:return
        m.tick(live(tile))
    raise AssertionError('bounded phase timeout '+state)

class CoupledBehavior(unittest.TestCase):
    def test_all_tails_exact_prefix_hold_and_ack(self):
        for n in range(1,17):
            keys=[[0x3f800000]*16 for _ in range(n)]
            m,t=model(keys);issue(m)
            for step in range(100):
                if m.committed:break
                event,p=m.tick(live(t))
                self.assertFalse(p['port_result_fire'])
                self.assertIs(p['result_value'],t.value)
            self.assertTrue(m.committed)
            self.assertEqual(m.selected,n-1)
            self.assertEqual((m.scores,m.maximum),baseline(keys)[:2])
            _,p=m.tick(live(t));self.assertTrue(p['port_result_fire'])
            self.assertEqual(m.client.state,'awaitDone');self.assertTrue(m.owned)
            for _ in range(3):m.tick({});self.assertTrue(m.owned)
            _,p=m.tick({'port_done_valid':True,'port_done_tag':1})
            self.assertTrue(p['port_done_fire']);self.assertTrue(m.owned)
            _,p=m.tick({});self.assertTrue(p['completion_fire']);self.assertFalse(m.owned)
            self.assertTrue(m.finished)

    def test_error_done_completion_keeps_protocol_status(self):
        m,t=model([[0x3f800000]*16]);issue(m);advance(m,t,'next')
        m.tick(live(t))
        m.tick({'port_done_valid':True,'port_done_tag':1,'port_done_error':True})
        _,p=m.tick({})
        self.assertTrue(p['completion_error']);self.assertTrue(m.poisoned)
        self.assertEqual(m.status,'Protocol');self.assertTrue(m.finished)

    def test_protocol_overrides_address_by_source_order(self):
        m,t=model([[0x3f800000]*16]);issue(m);advance(m,t,'scan')
        m.tick(live(t,port_done_valid=True,port_done_tag=99))
        m.tick(live(t,address_fault=True))
        self.assertEqual(m.status,'Protocol')
        m.tick({'address_fault':True})
        self.assertEqual(m.status,'Protocol')

    def test_early_matching_and_foreign_done_each_phase(self):
        for phase in ('scan','fold','scale','retire'):
            for tag in (1,99):
                m,t=model([[0x3f800000]*16]*3);issue(m);advance(m,t,phase)
                before=(list(m.scores),list(m.arithmetic.acc),list(m.arithmetic.faults))
                event,p=m.tick(live(t,port_done_valid=True,port_done_tag=tag))
                self.assertIsNone(event);self.assertFalse(p['port_done_fire'])
                self.assertFalse(p['port_result_fire']);self.assertFalse(m.committed)
                self.assertEqual(before,(m.scores,m.arithmetic.acc,m.arithmetic.faults))
                self.assertEqual(m.client.state,'draining');self.assertTrue(m.client.poison)
                _,p=m.tick(live(t,port_done_valid=True,port_done_tag=tag))
                self.assertTrue(p['port_result_fire']);self.assertEqual(p['port_done_fire'],tag==1)
                self.assertTrue(m.poisoned)

    def test_early_done_on_final_retire_preserves_only_prior_prefix(self):
        m,t=model([[0x3f800000]*16]*3);issue(m);advance(m,t,'retire')
        m.tick(live(t));m.tick(live(t));self.assertEqual(len(m.scores),2)
        event,p=m.tick(live(t,port_done_valid=True,port_done_tag=1))
        self.assertIsNone(event);self.assertEqual(len(m.scores),2);self.assertFalse(m.committed)

    def test_same_edge_ack_and_early_done_drains_not_success(self):
        m,t=model([[0x3f800000]*16]);issue(m);advance(m,t,'next')
        _,p=m.tick(live(t,port_done_valid=True,port_done_tag=1))
        # Scala actually ACKs the result, but unexpected early done poisons.
        self.assertTrue(p['port_result_fire']);self.assertFalse(p['port_done_fire'])
        self.assertEqual(m.client.state,'draining');self.assertTrue(m.client.poison)
        self.assertFalse(p['success_accepted'])

    def test_later_fault_is_private_until_ordered_retirement(self):
        keys=[[0x3f800000]*16,[0x7f7fffff]*16,[0x7fc00000]+[0]*15]
        m,t=model(keys);issue(m);advance(m,t,'fold')
        self.assertEqual(m.arithmetic.faults[:3],[False,False,True])
        advance(m,t,'retire');self.assertEqual(m.scores,[])
        event,_=m.tick(live(t));self.assertEqual(event[0:2],('score',0))
        event,_=m.tick(live(t));self.assertEqual(event,('fault',1))
        self.assertEqual((m.scores,m.maximum),baseline(keys)[:2]);self.assertFalse(m.committed)
        self.assertEqual(m.status,'Numerical')

    def test_scale_underflow_before_later_scan_fault(self):
        keys=[[0x3f800000]*16,[0x00010000]+[0]*15,[0x7fc00000]+[0]*15]
        m,t=model(keys);issue(m);advance(m,t,'retire')
        self.assertEqual(m.arithmetic.faults[:3],[False,True,True])
        m.tick(live(t));event,_=m.tick(live(t));self.assertEqual(event,('fault',1))

    def test_rounding_cancellation_signed_zero_subnormal_and_bf_overflow(self):
        cases=[[0x3f800000,0x33800000]+[0]*14,
               [0x3f800000,0xbf800000]+[0x80000000]*14,
               [0x80000000]*16,[1]+[0]*15,
               [0x7f7f0000,0x7a800000]+[0]*14]
        for key in cases:
            m,t=model([key]);issue(m)
            for _ in range(80):
                if m.state in ('next','finish'):break
                m.tick(live(t))
            scores,maximum,fault=baseline([key])
            self.assertEqual((m.scores,m.maximum),(scores,maximum))
            self.assertEqual(m.status=='Numerical',fault is not None)

    def test_live_client_payload_cannot_be_replaced_by_harness(self):
        m,t=model([[0x3f800000]*16]);issue(m)
        bad=live(t);bad['port_result_value']=object()
        with self.assertRaises(ValueError):m.tick(bad)
        advance(m,t,'scan')
        other=Tile([[0x3f800000]*16])
        with self.assertRaises(ValueError):m.tick(live(other))

    def test_result_not_yet_valid_stalls_without_read(self):
        m,t=model([[0x3f800000]*16]);issue(m)
        for _ in range(7):m.tick({})
        self.assertEqual(m.state,'feed');self.assertEqual(t.reads,[])
        advance(m,t,'scan');self.assertEqual(t.reads,[])

    def test_fault_cancel_each_phase_then_tagged_drain(self):
        for phase in ('scan','fold','scale','retire','next'):
            m,t=model([[0x3f800000]*16]*2);issue(m);advance(m,t,phase)
            prefix=list(m.scores)
            event,p=m.tick(live(t,matrix_fault=True))
            retired=p['port_result_fire']
            self.assertIsNone(event);self.assertEqual(m.scores,prefix);self.assertTrue(m.poisoned)
            _,p=m.tick({} if retired else live(t));self.assertTrue(p['port_abort'])
            self.assertFalse(p['port_result_fire']) # registered abort first enters drain
            _,p=m.tick({} if retired else live(t))
            self.assertEqual(p['port_result_fire'],not retired)
            _,p=m.tick({'port_done_valid':True,'port_done_tag':99})
            self.assertFalse(p['port_done_fire']);self.assertTrue(m.owned)
            _,p=m.tick({'port_done_valid':True,'port_done_tag':1})
            self.assertTrue(p['port_done_fire'])
            _,p=m.tick({});self.assertTrue(p['completion_error']);self.assertTrue(m.finished)

class DebtsAndBorrowers(unittest.TestCase):
    def test_three_accepted_debts_drain_only_matching_work(self):
        d=control.FeedDebts()
        d.tick(busy=True,memory_accept=7,local_accept=True,scalar_accept=True)
        self.assertTrue(d.any)
        self.assertEqual(d.drain_ready(finish=True,poisoned=True,response_tag=8),(False,True,True))
        d.tick(busy=True,memory_response=8,local_response=True)
        self.assertTrue(d.memory);self.assertFalse(d.local);self.assertTrue(d.scalar)
        d.tick(busy=True,memory_response=7,scalar_response=True);self.assertFalse(d.any)
    def test_acceptance_concurrent_fault_not_lost(self):
        d=control.FeedDebts()
        d.tick(busy=True,memory_accept=9,memory_response=9,local_accept=True,local_response=True,scalar_accept=True,scalar_response=True)
        self.assertEqual((d.memory,d.local,d.scalar),(True,True,True))
        d.tick(busy=True,memory_response=9,local_response=True,scalar_response=True)
        self.assertFalse(d.any)
    def test_coupled_failure_waits_all_accepted_feed_responses(self):
        m,t=model([[0x3f800000]*16]);issue(m)
        # At the feeder boundary, requests accepted concurrently with failure
        # remain debt. The model does not synthesize fictitious requests in fold.
        m.tick(dict(memory_accept=7,local_accept=True,scalar_accept=True,matrix_fault=True))
        self.assertTrue(m.debts.any);self.assertFalse(m.finished)
        m.tick({});m.tick(live(t))
        m.tick({'port_done_valid':True,'port_done_tag':1});m.tick({})
        self.assertFalse(m.owned);self.assertFalse(m.finished)
        _,p=m.tick(dict(memory_response_valid=True,memory_response_tag=99,
                       local_response_valid=True,scalar_response_valid=True))
        self.assertEqual(p['feed_drain_ready'],(False,True,True))
        self.assertTrue(m.debts.memory);self.assertFalse(m.finished)
        m.tick(dict(memory_response_valid=True,memory_response_tag=7))
        self.assertTrue(m.finished)
        with self.assertRaises(ValueError):m.tick({'memory_accept':8})

    def test_idle_offers_and_busy_result_exclude_owner_launch(self):
        b=control.ScalarBorrower()
        p=b.tick(idle=False,request_valid=True,owner_valid=True)
        self.assertFalse(p['request_fire']);self.assertFalse(b.busy)
        p=b.tick(idle=True,request_valid=True,owner_valid=True)
        self.assertTrue(p['request_fire']);self.assertFalse(p['owner_fire'])
        for _ in range(3):
            p=b.tick(idle=True,result_valid=True,owner_valid=True)
            self.assertFalse(p['owner_fire']);self.assertTrue(b.busy)
        p=b.tick(idle=True,result_valid=True,result_ready=True,owner_valid=True)
        self.assertFalse(p['owner_fire']);self.assertFalse(b.busy)
        self.assertTrue(b.tick(idle=True,owner_valid=True)['owner_fire'])
    def test_profile_and_elementwise_exclusion(self):
        control.ScalarBorrower.validate_profile()
        for kw in ({'elementwise_loan':True},{'official':False},{'head_dim':64},{'packed':False}):
            with self.assertRaises(ValueError):control.ScalarBorrower.validate_profile(**kw)
        b=control.ScalarBorrower()
        self.assertFalse(b.tick(idle=True,owner_valid=True,elementwise_exclusive=True)['owner_fire'])

if __name__=='__main__':unittest.main()
