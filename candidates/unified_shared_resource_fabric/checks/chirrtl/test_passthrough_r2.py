"""Small synthetic/parent-supplied 15 KiB excerpt controls, no actual FIR file read."""
import copy,hashlib,importlib.util,unittest
from pathlib import Path
R=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('base_tests',R/'test_check_chirrtl.py');base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
c=base.c;E=base.E
EXCERPT=R/'ACTUAL_COLLECTION_EXCERPT.fir.txt'

def actual_collection():
 data=EXCERPT.read_bytes()
 if len(data)!=15094 or hashlib.sha256(data).hexdigest()!='5c82676da956319c795a67cc819f91c7dcdec53ccdfbd15def77f887e4768a6f':raise ValueError('fixed parent excerpt identity')
 result={'kind':'module','ports':{},'instances':[],'body':[],'defname':None}
 lines=data.decode().splitlines()
 if lines[0].split(' @[',1)[0]!='  module UnifiedSharedResourceCollection :':raise ValueError('excerpt module')
 for line in lines[1:]:
  code=line.split(' @[',1)[0]
  if not code.strip():continue
  m=c.PORT.fullmatch(code)
  if m:result['ports'][m[2]]=[m[1],m[3]];continue
  m=c.INSTANCE.fullmatch(code)
  if m:result['instances'].append(m.groups());continue
  if not code.startswith('    '):raise ValueError('excerpt indent')
  result['body'].append(code[4:])
 return result

def parsed_collection(m):
 return {'ports':m['ports'],'lines':['    '+line for line in m['body']]}

def leaf_connections(m):
 # Independent direction source is an explicit recursive lexical grammar below,
 # not c.passthrough_leaves; generated cases still synthetic, not real IR proof.
 import re
 def walk(t,root,flip=False):
  if t.endswith(']'):
   a=t.rfind('[');n=int(t[a+1:-1]);return sum((walk(t[:a],root+'['+str(i)+']',flip) for i in range(n)),[])
  if t.startswith('{'):
   inner=t[1:-1];level=0;parts=[];start=0
   for i,ch in enumerate(inner):
    if ch in '{[':level+=1
    if ch in '}]':level-=1
    if ch==',' and level==0:parts.append(inner[start:i]);start=i+1
   parts.append(inner[start:]);out=[]
   for p in parts:
    name,typ=p.split(':',1);name=name.strip();f=name.startswith('flip ')
    if f:name=name[5:]
    out+=walk(typ.strip(),root+'.'+name,flip^f)
   return out
  if re.fullmatch(r'(UInt|SInt)<[0-9]+>|Clock|Reset|AsyncReset',t) is None:raise ValueError(t)
  return [(root,flip)]
 out=['connect top.clock, clock','connect top.reset, reset']
 for inst in E['collection_instances']:
  root='port' if inst=='top' else inst+'Port'
  for leaf,flip in walk(m['ports'][root][1],root):
   child=inst+'.io'+leaf[len(root):]
   out.append('connect '+(child+', '+leaf if flip else leaf+', '+child))
 return out

class Passthrough(unittest.TestCase):
 def setUp(self):self.m=actual_collection()
 def check(self):return c.check_collection_passthrough(parsed_collection(self.m),E)
 def bad(self):
  with self.assertRaises(ValueError):self.check()
 def replace(self,old,new):
  if old not in self.m['body']:raise ValueError('test old line absent '+old)
  self.m['body'][self.m['body'].index(old)]=new
 def test_exact_actual_excerpt(self):
  r=self.check();self.assertEqual(r,{'leaf_count':4616,'connect_count':46,'roots':5,'clock_reset_connections':2})
 def test_actual_excerpt_with_mock_graph(self):
  m=base.fixture_modules();m[E['top']]=copy.deepcopy(self.m)
  # The inherited mock alphabetizes FMA fields; retain the actual source order
  # when combining this small real collection excerpt with mock child declarations.
  for inst,child in E['collection_instances'].items():
   if inst!='top':m[child]['ports']['io']=copy.deepcopy(self.m['ports'][inst+'Port'])
  report=c.parse_bytes(base.encode(m),E)
  self.assertEqual(report['status'],c.STATUS)
  self.assertEqual(report['passthrough'],{'leaf_count':4616,'connect_count':46,'roots':5,'clock_reset_connections':2})
 def test_all_ground_leaf(self):
  self.m['body']=leaf_connections(self.m);self.assertEqual(self.check()['connect_count'],4616)
 def test_whole_roots(self):
  self.m['body']=['connect top.clock, clock','connect top.reset, reset']+['connect '+('port' if i=='top' else i+'Port')+', '+i+'.io' for i in E['collection_instances']]
  self.assertEqual(self.check()['leaf_count'],4616)
 def test_doubleflip_ready_exact(self):
  t=c.passthrough_type_tree('{ flip x : { flip ready : UInt<1>, bits : UInt<4>}, y : UInt<2>[3][2]}')
  got=c.passthrough_leaves(t)
  self.assertEqual(got,[('.x.ready',False,('UInt',1)),('.x.bits',True,('UInt',4))]+[('.y['+str(i)+']['+str(j)+']',False,('UInt',2)) for i in range(2) for j in range(3)])
 def test_select_doubleflip(self):
  t=c.passthrough_type_tree('{ flip x : { flip ready : UInt<1>, bits : UInt<4>}}')
  self.assertFalse(c.passthrough_select(t,'.x.ready')[1]);self.assertTrue(c.passthrough_select(t,'.x.bits')[1])
 def test_reversed_input_bundle(self):self.replace('connect top.io.launch, port.launch','connect port.launch, top.io.launch');self.bad()
 def test_reversed_output_bundle(self):self.replace('connect port.context, top.io.context','connect top.io.context, port.context');self.bad()
 def test_reversed_ready(self):self.replace('connect top.io.result.ready, port.result.ready','connect port.result.ready, top.io.result.ready');self.bad()
 def test_reversed_fma(self):self.replace('connect mul.io.mulAddA, mulPort.mulAddA','connect mulPort.mulAddA, mul.io.mulAddA');self.bad()
 def test_cross_fma(self):self.replace('connect post.io.mulAddResult, postPort.mulAddResult','connect mul.io.mulAddResult, postPort.mulAddResult');self.bad()
 def test_rename_same_width(self):self.replace('connect pre.io.a, prePort.a','connect pre.io.a, prePort.b');self.bad()
 def test_missing_leaf(self):self.m['body'].remove('connect mul.io.mulAddA, mulPort.mulAddA');self.bad()
 def test_missing_subtree(self):self.m['body'].remove('connect port.matrixResult.bits, top.io.matrixResult.bits');self.bad()
 def test_duplicate_leaf(self):self.m['body'].append('connect mul.io.mulAddA, mulPort.mulAddA');self.bad()
 def test_overlap_subtree_leaf(self):self.m['body'].append('connect port.context.profile.hidden, top.io.context.profile.hidden');self.bad()
 def test_overlap_whole(self):self.m['body'].append('connect port, top.io');self.bad()
 def test_extra_unknown_connect(self):self.m['body'].append('connect unknown, other');self.bad()
 def test_source_expression(self):self.replace('connect port.resetRequired, top.io.resetRequired','connect port.resetRequired, not(top.io.resetRequired)');self.bad()
 def test_constant(self):self.replace('connect port.resetRequired, top.io.resetRequired','connect port.resetRequired, UInt<1>(0h0)');self.bad()
 def test_sink_expression(self):self.replace('connect port.resetRequired, top.io.resetRequired','connect not(port.resetRequired), top.io.resetRequired');self.bad()
 def test_same_side(self):self.replace('connect port.resetRequired, top.io.resetRequired','connect port.resetRequired, port.resetRequired');self.bad()
 def test_unknown_suffix(self):self.m['body'].append('connect port.noSuch, top.io.noSuch');self.bad()
 def test_array_range(self):self.m['body'].append('connect port.matrixResult.bits.payload.value[16][0], top.io.matrixResult.bits.payload.value[16][0]');self.bad()
 def test_array_negative(self):self.m['body'].append('connect port.matrixResult.bits.payload.value[-1][0], top.io.matrixResult.bits.payload.value[-1][0]');self.bad()
 def test_array_dynamic(self):self.m['body'].append('connect port.matrixResult.bits.payload.value[i][0], top.io.matrixResult.bits.payload.value[i][0]');self.bad()
 def test_array_leading_zero(self):self.m['body'].append('connect port.matrixResult.bits.payload.value[00][0], top.io.matrixResult.bits.payload.value[00][0]');self.bad()
 def test_array_wrong_inner(self):self.m['body'].append('connect port.matrixResult.bits.payload.value[0][256], top.io.matrixResult.bits.payload.value[0][256]');self.bad()
 def test_array_swapped_index(self):
  self.m['body']=leaf_connections(self.m)
  self.replace('connect port.matrixResult.bits.payload.value[0][1], top.io.matrixResult.bits.payload.value[0][1]','connect port.matrixResult.bits.payload.value[0][1], top.io.matrixResult.bits.payload.value[1][0]');self.bad()
 def test_if_conditional(self):self.m['body'].insert(0,'when UInt<1>(0h1) :');self.bad()
 def test_nested_connect(self):self.replace('connect pre.io.a, prePort.a','  connect pre.io.a, prePort.a');self.bad()
 def test_unknown_partial_connect(self):self.m['body'].append('partialconnect port, top.io');self.bad()
 def test_invalid(self):self.m['body'].append('invalidate port');self.bad()
 def test_alias_node(self):self.m['body'].insert(0,'node alias = port');self.bad()
 def test_extra_clock(self):self.m['body'].append('connect mul.clock, clock');self.bad()
 def test_missing_clock(self):self.m['body'].remove('connect top.clock, clock');self.bad()
 def test_missing_reset(self):self.m['body'].remove('connect top.reset, reset');self.bad()
 def test_reset_reverse(self):self.replace('connect top.reset, reset','connect reset, top.reset');self.bad()
 def test_clock_duplicate(self):self.m['body'].append('connect top.clock, clock');self.bad()
 def test_clock_reverse(self):self.replace('connect top.clock, clock','connect clock, top.clock');self.bad()
 def test_reset_expression(self):self.replace('connect top.reset, reset','connect top.reset, asAsyncReset(reset)');self.bad()
 def test_trailing_second_statement(self):self.replace('connect pre.io.a, prePort.a','connect pre.io.a, prePort.a; connect pre.io.b, prePort.b');self.bad()
 def test_bad_type_tokens(self):
  with self.assertRaises(ValueError):c.passthrough_type_tree('{ a : UInt<1>; }')
 def test_empty_type(self):
  with self.assertRaises(ValueError):c.passthrough_type_tree('{}')
 def test_duplicate_field(self):
  with self.assertRaises(ValueError):c.passthrough_type_tree('{ a : UInt<1>, a : UInt<2>}')
 def test_leaf_count_mismatch(self):
  self.m['ports']['port'][1]='UInt<1>';self.bad()
if __name__=='__main__':unittest.main()
