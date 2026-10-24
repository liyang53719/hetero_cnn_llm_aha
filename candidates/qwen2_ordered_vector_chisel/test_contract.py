"""Source contracts + existing micro-model/client integration, NOT Chisel execution.

Only pinned stdlib AST definitions are loaded. No compiler, RTL emission, native
library, weights or production import prelude is used. Model steps are not cycles.
"""
import argparse
import ast
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
import hashlib
import importlib.util
import itertools
import json
import operator
from pathlib import Path
import re
import struct
import sys
import types
import unittest

HERE=Path(__file__).resolve(strict=True).parent
sys.path.insert(0,str(HERE))
import prepare
if Path(prepare.__file__).resolve(strict=True)!=HERE/'prepare.py':
    raise ImportError('unexpected prepare origin')
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--selected-root',required=True,type=Path)
parser.add_argument('--source-root',required=True,type=Path)
parser.add_argument('--micro-root',required=True,type=Path)
args, rest=parser.parse_known_args();sys.argv[:]=[sys.argv[0],*rest]
PIN=json.loads((HERE/'TEST_INPUT_PINS.json').read_text())
for rel,expected in PIN['raw_sources'].items():
    if hashlib.sha256((args.source_root/rel).read_bytes()).hexdigest()!=expected:
        raise ValueError('raw source pin mismatch: '+rel)
micro_path=args.micro_root/'model.py'
if hashlib.sha256(micro_path.read_bytes()).hexdigest()!=PIN['micro_model_sha256']:
    raise ValueError('micro model pin mismatch')
spec=importlib.util.spec_from_file_location('_ordered_qk_micro',micro_path)
micro=importlib.util.module_from_spec(spec);spec.loader.exec_module(micro)
output=prepare.compose(args.selected_root)
REL='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
core=output[REL+'Qwen2Block.scala']
base=(args.selected_root/(REL+'Qwen2Block.scala')).read_text()
client_scala=(args.selected_root/(REL+'PackedAttentionStreamClient.scala')).read_text()
new=core[core.index('  if(enableOrderedVectorQkFold){\n    val c='):core.index('  when(state===st("attReduce"))')]

def load(relative,names=None,env=None):
    path=args.source_root/relative
    tree=ast.parse(path.read_text(),filename=relative)
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and (names is None or n.name in names)]
    if names is not None and {n.name for n in nodes}!=set(names):raise ValueError('missing AST definition')
    module=types.ModuleType('_qk_contract_'+str(len(sys.modules)));sys.modules[module.__name__]=module
    module.__dict__.update(Counter=Counter,Sequence=Sequence,dataclass=dataclass,replace=replace,struct=struct,Fraction=Fraction,lru_cache=lru_cache,operator=operator)
    module.__dict__.update({k:v for k,v in (env or {}).items() if not k.startswith("__")})
    exec(compile(ast.Module(body=nodes,type_ignores=[]),relative,'exec'),module.__dict__)
    return module

PK='candidates/qwen2_resident_matrix/'
ref=load(PK+'ffn_public/test_prefix_owners.py',('exact','rn','ref_add','ref_mul','ref_div','ref_bf'))
arith=load(PK+'attention_matrix_batch/test_model.py',('finite','ArithmeticFault','ExactScalar'),{k:getattr(ref,k) for k in ('exact','rn','ref_add','ref_mul','ref_div','ref_bf')})
matrix=load(PK+'ffn_attention/matrix_service.py',('MatrixProtocolError','require','NormalGroup','NormalStep','_MatrixRow','MatrixValue','MatrixResult','MatrixDone'))
client=load(PK+'attention_packed_owner/client.py',env={**vars(matrix),'ArithmeticFault':arith.ArithmeticFault})
fixture=load(PK+'attention_packed_owner/test_client.py',('_State','ScriptedService','pv','deliver','finish','ClientTests'),{**vars(matrix),**vars(client),'ArithmeticFault':arith.ArithmeticFault,'unittest':unittest})
OriginalClientTests=fixture.ClientTests

# Evaluate only the actual added boolean gate, under all 128 truth assignments.
gate=re.search(r'val orderedSafe=(.*?)\n    when\(orderedActive\)',new,re.S).group(1)
names={'packedBusy':'busy','poisoned':'poison','c.io.resetRequired':'reset','c.io.port.done.valid':'done','c.io.result.valid':'valid','matrixFault':'matrix_fault','f.address_error_o.orR':'address_fault'}
expr=gate
for source,target in sorted(names.items(),key=lambda x:-len(x[0])):expr=expr.replace(source,target)
expr=' '.join(expr.replace('&&',' and ').replace('!',' not ').split())
gate_ast=ast.parse(expr,mode='eval')
if any(not isinstance(n,(ast.Expression,ast.BoolOp,ast.And,ast.UnaryOp,ast.Not,ast.Name,ast.Load)) for n in ast.walk(gate_ast)):
    raise ValueError('unexpected safe-gate expression')
if {n.id for n in ast.walk(gate_ast) if isinstance(n,ast.Name)}!=set(names.values()):
    raise ValueError('safe-gate signals changed')
gate_code=compile(gate_ast,'orderedSafe','eval')
def safe(**values):return eval(gate_code,{'__builtins__':{}},values)

class SourceContracts(unittest.TestCase):
    def test_exact_composition_and_wrong_baseline_rejection(self):
        pins=json.loads((HERE/'PROFILE_PINS.json').read_text())
        for rel,text in output.items():
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),pins['selected_files'][rel]['after_sha256'])
        originals={rel:(args.selected_root/rel).read_text() for rel in output}
        originals[REL+'Qwen2Block.scala']='changed\n'+originals[REL+'Qwen2Block.scala']
        with self.assertRaises(ValueError):prepare.apply_exact_patch(originals,(HERE/'ordered_fold.patch').read_text())
    def test_default_off_through_existing_hierarchy(self):
        for text in output.values():
            self.assertIn('enableOrderedVectorQkFold:Boolean=false',text)
            self.assertIn('require(!enableOrderedVectorQkFold ||',text)
        self.assertEqual(output[REL+'HostBlockTop.scala'].count('enableOrderedVectorQkFold=enableOrderedVectorQkFold'),2)
        self.assertEqual(output[REL+'QwenOwnerProtocol.scala'].count('enableOrderedVectorQkFold=enableOrderedVectorQkFold'),1)
        self.assertIn('s.headDim==128',core)
    def test_same_alu_acc_and_only_sixteen_fault_bits(self):
        self.assertEqual(core.count('Module(new HeteroFP32Alu)'),base.count('Module(new HeteroFP32Alu)'))
        self.assertEqual(core.count('val acc=Reg(Vec(16,UInt(32.W)))'),1)
        self.assertIn('val vectorAlus=(0 until 16).map',core)
        self.assertIn('val vflags=VecInit(vectorAlus.map(_.io.exceptionFlags))',core)
        self.assertIn('Some(RegInit(VecInit(Seq.fill(16)(false.B))))else None',core)
        self.assertNotIn('Reg(',new);self.assertNotIn('RegInit(',new)
    def test_state_codes_append_and_no_reuse_collision(self):
        old_names=re.search(r'val names=Seq\((.*?)\)\n',base).group(1)
        self.assertIn('val names=Seq('+old_names+') ++ (if(enableOrderedVectorQkFold)',core)
        count=len(re.findall(r'"[^"]+"',old_names))
        self.assertEqual(count,103);self.assertLessEqual(count+4,128)
        self.assertIn('else Seq.empty[String]',core)
    def test_safe_gate_exhaustive(self):
        for bits in itertools.product([False,True],repeat=7):
            values=dict(zip(names.values(),bits))
            expected=values['busy'] and values['valid'] and not any(values[n] for n in ('poison','reset','done','matrix_fault','address_fault'))
            self.assertEqual(safe(**values),expected)
        for state in ('scanning','folding','scaling','retiring'):
            self.assertIn('when('+state+' && orderedSafe)',new)
    def test_tail_zero_and_strict_flags_materialization(self):
        self.assertIn('val usable=active && !orderedQkFault.get(j)',new)
        self.assertIn('val stripe=Mux(active,c.io.result.bits.value(lane)((16*j).U+lane),0.U(32.W))',new)
        self.assertEqual(new.count('vflags(j)(4,1).orR'),2)
        self.assertIn('vectorA:=VecInit(Seq.fill(16)(0.U(32.W)))',new)
        self.assertIn('vectorB:=VecInit(Seq.fill(16)(0.U(32.W)))',new)
        self.assertIn('val dotValue=materialize(acc(j))',new)
        self.assertIn('val score=materialize(vout(j))',new)
        self.assertIn('!TensorMath.finite(dotValue)',new)
        self.assertIn('!TensorMath.finite(score)',new)
    def test_ordered_retire_and_last_key_no_wrap(self):
        self.assertIn('when(orderedQkFault.get(packedSelected.get)){packedSelectedFault:=true.B}',new)
        self.assertNotIn('orderedQkFault.get.asUInt.orR',new)
        self.assertIn('scores.write(key+packedSelected.get,score)',new)
        self.assertIn('packedCommitted.get:=true.B;state:=st("attNextKey")',new)
        self.assertIn('}.otherwise{packedSelected.get:=packedSelected.get+1.U}',new)
        self.assertEqual(new.count('packedSelected.get:='),1)
    def test_actual_client_and_debt_logic_unchanged(self):
        for anchor in ['c.io.result.ready:=packedCommitted.get && !poisoned',
                       'c.io.completion.ready:=packedBusy && (packedCommitted.get || poisoned || c.io.resetRequired)',
                       'when(c.io.completion.fire){packedOwned.get:=false.B}']:
            self.assertIn(anchor,core);self.assertIn(anchor,base)
        anchor='    // Track accepted work, including an acceptance concurrent with a fault.'
        self.assertEqual(core[core.index(anchor):],base[base.index(anchor):])
        for term in ('calc(','read(','localRead(','io.result.ready:=','io.completion.ready:='):
            self.assertNotIn(term,new)
        self.assertIn('(io.port.done.valid && (!matchingDone || (state=/=awaitDone && state=/=draining)))',client_scala)
    def test_no_false_conflict_on_backpressured_external_offer(self):
        self.assertNotIn('assert(!scalarExternalExclusive',new)
        self.assertIn('assert(!scalar.io.request.valid',new)
        self.assertIn('val available=state===st("idle") && !poisoned && !busy',core)
        self.assertIn('require(!externalElementwiseLoan || !officialBf16',core)

class LiveClientIntegration(unittest.TestCase):
    def setup_group(self,count,bad_key=None):
        service=fixture.ScriptedService();service.words={}
        for j in range(count):
            for r in range(16):service.words[r*256+16*j+r]=0x3f800000
        # Tail NaNs must never become active numerical errors.
        for j in range(count,16):service.words[16*j]=0x7fc00000
        if bad_key is not None:service.words[16*bad_key]=0x7fc00000
        c=client.PackedClient(service,service.owner)
        for i in range(8):
            result=fixture.deliver(c,client.PackedRequest(0x23,(0x3f80,)*16,(0x3f80,)*256,i==0,i==7,8,255,tuple((r,16*j+r) for j in range(count) for r in range(16)) if i==7 else ()))
        m=micro.OrderedVectorFold(arith.ExactScalar(),arith.finite,arith.ArithmeticFault,enabled=True)
        self.assertTrue(m.accept(result,count))
        return service,c,result,m
    def test_all_tails_live_result_then_real_ack_and_done_backpressure(self):
        for count in range(1,17):
            service,c,result,m=self.setup_group(count)
            held=service.result
            for t in range(160):
                if m.state=='drain':break
                allowed=safe(busy=True,poison=False,reset=False,done=False,valid=t%4!=0,matrix_fault=False,address_fault=False)
                if allowed:m.step(ack_ready=t%3!=0)
                ports=c.tick(result_ready=True)
                self.assertFalse(ports['service_result_fire'])
                self.assertIs(service.result,held)
                self.assertIs(result.value,held.value)
            self.assertTrue(m.ack);self.assertEqual(len(m.committed),count)
            self.assertTrue(c.tick(request=client.PackedConsumerAck(result.tag))['request_fire'])
            for _ in range(3):self.assertFalse(c.tick(service_result_ready=False)['service_result_fire'])
            self.assertTrue(c.tick(service_done_ready=False)['service_result_fire'])
            self.assertFalse(c.drained)
            self.assertTrue(c.tick()['service_done_fire'])
            self.assertFalse(c.drained)
            self.assertTrue(c.tick(result_ready=True)['result_fire'])
            self.assertTrue(c.drained)
    def test_fault_prefix_real_client_abort_drain_no_success_ack(self):
        for key in range(4):
            service,c,result,m=self.setup_group(4,key)
            for _ in range(80):
                if m.state=='drain':break
                m.step()
            self.assertEqual(m.fault_key,key);self.assertEqual(len(m.committed),key)
            self.assertFalse(m.ack)
            held=service.result
            c.tick(abort=True,service_result_ready=False,service_done_ready=False)
            self.assertIs(service.result,held)
            for _ in range(10):
                c.tick(result_ready=True)
                if c.drained:break
            self.assertTrue(c.drained)
    def test_early_done_gate_blocks_same_observation_retire(self):
        service,c,result,m=self.setup_group(2)
        for _ in range(33):m.step()
        self.assertEqual(m.state,'retire')
        allowed=safe(busy=True,poison=False,reset=False,done=True,valid=True,matrix_fault=False,address_fault=False)
        if allowed:m.step()
        self.assertEqual(m.committed,[])
        # Actual client may report poison on a subsequent observation. Do not
        # pretend Python ticks establish the Scala register-edge timing.
        m.step(abort=True);self.assertEqual(m.committed,[])

if __name__=='__main__':unittest.main()
