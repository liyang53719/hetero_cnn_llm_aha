"""Synthetic bounded CHIRRTL only. No JVM, native, real generated IR reads."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('unified_guard',R/'check_chirrtl.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
E=json.loads((R/'STRUCTURE_EXPECTATION.json').read_text())
def typed_ports(io=None,raw=False,top=False):
 p={} if raw else {'clock':['input','Clock'],'reset':['input','UInt<1>' if top else 'Reset']}
 if io is not None:p['io']=['output',io]
 return p
ALUIO='{ flip op : UInt<1>, flip x : UInt<32>, flip y : UInt<32>, out : UInt<32>, exceptionFlags : UInt<5>}'
def fixture_modules():
 m={}
 def mod(name,ports=None,children=(),lines=(),kind='module',defname=None):
  m[name]={'kind':kind,'ports':copy.deepcopy(ports or {}),'instances':list(children),'body':list(lines),'defname':defname}
 # Handwritten tiny graph with exact production resource cardinalities; primitive internals are mock.
 for n in ['AddRecFN','MulRecFN','DivSqrtRecFM_small_e8_s24','RecFNToIN_e8_s24_i32','INToRecFN_i32_e8_s24']:
  mod(n,typed_ports(),lines=['node dummy = UInt<1>(0h0)'])
 alus=[]
 for i in range(17):
  n='HeteroFP32Alu'+('_'+str(i) if i else '');alus.append(n)
  mod(n,typed_ports(ALUIO),[('add','AddRecFN'),('mul','MulRecFN')])
 mod('UnifiedVectorBank',typed_ports(E['vector_io_type']),[('alus_'+str(i),alus[i]) for i in range(16)])
 mod('BlockScalarFloat',typed_ports('{ error : UInt<1>}'),[('alu',alus[16]),('div','DivSqrtRecFM_small_e8_s24'),('conv','RecFNToIN_e8_s24_i32'),('integer','INToRecFN_i32_e8_s24')])
 mod('GdnChunkStateTransferOwner',typed_ports('{ resetRequired : UInt<1>}'),lines=['regreset payload : UInt<512>, clock, reset, UInt<512>(0h0)'])
 mod('UnifiedBlockAdmission',typed_ports('{ active : UInt<1>}'),lines=['regreset state : UInt<3>, clock, reset, UInt<3>(0h0)'])
 for n in E['external_definition_names']:
  b=c.external_base(n,E);mod(n,E['external_ports'][b],kind='extmodule',defname=b)
 queue='{ context : UInt<3>, last : UInt<1>, finish : UInt<1>, emit : UInt<1>}'
 mod('Queue8_Meta',typed_ports('{ count : UInt<4>}'),lines=['cmem ram : '+queue+'[8]'])
 store='{ value : UInt<32>[256][16], context : UInt<3>, last : UInt<1>, error : UInt<1>}[2]'
 mod('MatrixResultFifo',typed_ports('{ empty : UInt<1>}'),lines=['regreset storage : '+store+', clock, reset, invalid']+['regreset '+n+' : UInt<'+str(w)+'>, clock, reset, UInt<'+str(w)+'>(0h0)' for n,w in [('head',1),('tail',1),('count',2)]])
 children=[('tags','Queue8_Meta'),('values','MatrixResultFifo')]
 for b,inst in [('qwen2_matrix_command_endpoint','leaves'),('tc_clk_gating','gate')]:
  children += [(inst+'_'+str(i),b+('_'+str(i) if i else '')) for i in range(8)]
 mod('MatrixPipelineService',typed_ports('{ port : { abort : UInt<1>}}'),children)
 mod(E['fabric'],typed_ports('{ resetRequired : UInt<1>}'),list(E['fabric_instances'].items()))
 productlines=['regreset mode : UInt<3>, clock, reset, UInt<3>(0h0)','node _resourceMode_T = geq(mode, UInt<1>(0h1))','node _resourceMode_T_1 = leq(mode, UInt<3>(0h4))','node resourceMode = and(_resourceMode_T, _resourceMode_T_1)','node _lease = and(admission.io.dispatch.valid, resourceMode)','connect fabric.io.lease.valid, _lease','connect admission.io.completion.bits.status, mux(rejected, UInt<8>(0h80), fabric.io.done.bits.status)','connect io.completeBlockImplemented, UInt<1>(0h0)']
 mod(E['product'],typed_ports(E['top_io_type']),list(E['product_instances'].items()),productlines)
 rootports=typed_ports(top=True);rootports['port']=['output',E['top_io_type']]
 for inst,n in E['collection_instances'].items():
  if inst=='top':continue
  fields=[]
  for fn,abi in E['fma_abi'][n].items():fields.append(('flip ' if abi['direction']=='input' else '')+fn[3:]+' : UInt<'+str(abi['width'])+'>')
  t='{ '+', '.join(fields)+'}';mod(n,typed_ports(t,raw=True));rootports[inst+'Port']=['output',t]
 lines=['connect top.clock, clock','connect top.reset, reset']+['connect '+('port' if inst=='top' else inst+'Port')+', '+inst+'.io' for inst in E['collection_instances']]
 mod(E['top'],rootports,list(E['collection_instances'].items()),lines)
 return m

def encode(m,mutate_annotations=None):
 annotations=[]
 for n in m:annotations.append({'class':'firrtl.transforms.DedupGroupAnnotation','target':'~'+E['top']+'|'+n,'group':n})
 for root in E['dont_touch_roots']:
  for leaf in c.type_leaf_paths(m[E['top']]['ports'][root][1],root):annotations.append({'class':'firrtl.transforms.DontTouchAnnotation','target':'~'+E['top']+'|'+E['top']+'>'+leaf})
 if mutate_annotations:mutate_annotations(annotations)
 text='FIRRTL version 3.3.0\ncircuit '+E['top']+' :%['+json.dumps(annotations,separators=(',',':'))+']\n'
 for n,q in m.items():
  text+='  '+q['kind']+' '+n+' :\n'
  for pn,(d,t) in q['ports'].items():text+='    '+d+' '+pn+' : '+t+'\n'
  if q['kind']=='extmodule':text+='    defname = '+q['defname']+'\n'
  for i,t in q['instances']:text+='    inst '+i+' of '+t+'\n'
  for line in q['body']:text+='    '+line+'\n'
 return text.encode()
class Tests(unittest.TestCase):
 def setUp(self):self.m=fixture_modules()
 def runcheck(self,m=None,e=None,edit=None):return c.parse_bytes(encode(self.m if m is None else m,edit),copy.deepcopy(E if e is None else e))
 def test_positive(self):
  r=self.runcheck();self.assertEqual(r['recursive_product_resource_occurrences']['HeteroFP32Alu'],17);self.assertEqual(r['physical_matrix_endpoint_slots'],4096);self.assertFalse(r['scope']['fullblock_accepted']);self.assertFalse(r['unsupported_evidence']['completeBlockImplemented_constant'])
 def test_missing_product(self):
  self.m.pop(E['product'])
  with self.assertRaises((ValueError,KeyError)):self.runcheck()
 def test_extra_fabric(self):
  self.m[E['product']]['instances'].append(('extra','UnifiedPhysicalFabric'))
  with self.assertRaises(ValueError):self.runcheck()
 def test_missing_vector_lane(self):
  self.m['UnifiedVectorBank']['instances'].pop()
  with self.assertRaises(ValueError):self.runcheck()
 def test_extra_vector_lane(self):
  self.m['UnifiedVectorBank']['instances'].append(('extra','HeteroFP32Alu'))
  with self.assertRaises(ValueError):self.runcheck()
 def test_scalar_no_alu(self):
  self.m['BlockScalarFloat']['instances'].pop(0)
  with self.assertRaises(ValueError):self.runcheck()
 def test_wrong_original_alu(self):
  self.m['HeteroFP32Alu']['instances'][1]=('mul','AddRecFN')
  with self.assertRaises(ValueError):self.runcheck()
 def test_alu_flags_width(self):
  self.m['HeteroFP32Alu']['ports']['io'][1]=ALUIO.replace('UInt<5>','UInt<4>')
  with self.assertRaises(ValueError):self.runcheck()
 def test_old_core_forbidden(self):
  self.m['OrderedQkBehaviorCore']=self.m.pop('AddRecFN')
  for q in self.m.values():q['instances']=[(i,'OrderedQkBehaviorCore' if n=='AddRecFN' else n) for i,n in q['instances']]
  with self.assertRaises(ValueError):self.runcheck()
 def test_unknown_external(self):
  self.m['tc_clk_gating']['defname']='unknown'
  with self.assertRaises(ValueError):self.runcheck()
 def test_seed_port(self):
  self.m['qwen2_matrix_command_endpoint']['ports']['seed']=['input','UInt<1>']
  with self.assertRaises(ValueError):self.runcheck()
 def test_ext_parameter(self):
  self.m['tc_clk_gating']['body'].append('parameter EXTRA = 1')
  with self.assertRaises(ValueError):self.runcheck()
 def test_ext_normal_body(self):
  self.m['tc_clk_gating']['body'].append('node fake = UInt<1>(0h0)')
  with self.assertRaises(ValueError):self.runcheck()
 def test_duplicate_external_instance(self):
  self.m['MatrixPipelineService']['instances'][-1]=('gate_7','tc_clk_gating')
  with self.assertRaises(ValueError):self.runcheck()
 def test_unknown_matrix_option(self):
  self.m['MatrixPipelineService']['ports']['io'][1]='{ packedStepsDrained : UInt<1>}'
  with self.assertRaises(ValueError):self.runcheck()
 def test_unreachable(self):
  self.m['Unused']={'kind':'module','ports':{},'instances':[],'body':[],'defname':None}
  with self.assertRaises(ValueError):self.runcheck()
 def test_recursive(self):
  self.m['AddRecFN']['instances']=[('again','AddRecFN')]
  with self.assertRaises(ValueError):self.runcheck()
 def test_wrong_mode_zero_admitted(self):
  self.m[E['product']]['body'][1]='node _resourceMode_T = geq(mode, UInt<1>(0h0))'
  with self.assertRaises(ValueError):self.runcheck()
 def test_wrong_mode_max(self):
  self.m[E['product']]['body'][2]='node _resourceMode_T_1 = leq(mode, UInt<3>(0h5))'
  with self.assertRaises(ValueError):self.runcheck()
 def test_fullblock_true(self):
  self.m[E['product']]['body'][-1]='connect io.completeBlockImplemented, UInt<1>(0h1)'
  with self.assertRaises(ValueError):self.runcheck()
 def test_fullblock_duplicate_assignment(self):
  self.m[E['product']]['body'].append('connect io.completeBlockImplemented, UInt<1>(0h0)')
  with self.assertRaises(ValueError):self.runcheck()
 def test_bad_reject_code(self):
  self.m[E['product']]['body'][-2]=self.m[E['product']]['body'][-2].replace('0h80','0h0')
  with self.assertRaises(ValueError):self.runcheck()
 def test_lease_ignores_mode(self):
  self.m[E['product']]['body'][-3]='connect fabric.io.lease.valid, admission.io.dispatch.valid'
  with self.assertRaises(ValueError):self.runcheck()
 def test_nested_expr_cycle(self):
  self.m[E['product']]['body'][1]='node _resourceMode_T = resourceMode'
  with self.assertRaises(ValueError):self.runcheck()
 def test_same_manual_top_abi(self):
  self.m[E['product']]['ports']['io'][1]=E['top_io_type'].replace('resourceMode : UInt<3>','resourceMode : UInt<4>')
  with self.assertRaises(ValueError):self.runcheck()
 def test_collection_top_type_mismatch(self):
  self.m[E['top']]['ports']['port'][1]=E['top_io_type'].replace('contextValid : UInt<1>','contextValid : UInt<2>')
  with self.assertRaises(ValueError):self.runcheck()
 def test_collection_bad_passthrough(self):
  self.m[E['top']]['body']=[('connect prePort, mul.io' if line=='connect prePort, pre.io' else line) for line in self.m[E['top']]['body']]
  with self.assertRaises(ValueError):self.runcheck()
 def test_collection_partial_override(self):
  self.m[E['top']]['body'].append('connect port.completeBlockImplemented, UInt<1>(0h1)')
  with self.assertRaises(ValueError):self.runcheck()
 def test_collection_duplicate_whole(self):
  self.m[E['top']]['body'].append('connect port, top.io')
  with self.assertRaises(ValueError):self.runcheck()
 def test_annotated_top_is_only_donttouch_root(self):
  x=self.runcheck();self.assertGreater(x['annotation_report']['dont_touch_count'],4000)
  self.assertEqual(x['unsupported_evidence']['excluded_complete_block_mode'],0)
 def test_wrong_collection_reset(self):
  self.m[E['top']]['ports']['reset']=['input','Reset']
  with self.assertRaises(ValueError):self.runcheck()
 def test_wrong_nested_reset(self):
  self.m[E['product']]['ports']['reset']=['input','UInt<1>']
  with self.assertRaises(ValueError):self.runcheck()
 def test_namespace_fma_abi(self):
  self.m['HeteroBF16FmaPre']['ports']['io'][1]=self.m['HeteroBF16FmaPre']['ports']['io'][1].replace('UInt<54>','UInt<53>')
  with self.assertRaises(ValueError):self.runcheck()
 def test_stateowner_memory(self):
  self.m['GdnChunkStateTransferOwner']['body'].append('smem hidden : UInt<32>[4096]')
  with self.assertRaises(ValueError):self.runcheck()
 def test_stateowner_payload(self):
  self.m['GdnChunkStateTransferOwner']['body'][0]=self.m['GdnChunkStateTransferOwner']['body'][0].replace('512','1024')
  with self.assertRaises(ValueError):self.runcheck()
 def test_bad_result_fifo(self):
  self.m['MatrixResultFifo']['body'][0]=self.m['MatrixResultFifo']['body'][0].replace('[2]','[3]')
  with self.assertRaises(ValueError):self.runcheck()
 def test_bad_metadata_fifo(self):
  self.m['Queue8_Meta']['body'][0]=self.m['Queue8_Meta']['body'][0].replace('[8]','[7]')
  with self.assertRaises(ValueError):self.runcheck()
 def test_unknown_anno(self):
  with self.assertRaises(ValueError):self.runcheck(edit=lambda a:a.append({'class':'Hidden','target':'x'}))
 def test_missing_donttouch(self):
  with self.assertRaises(ValueError):self.runcheck(edit=lambda a:a.pop())
 def test_extra_donttouch(self):
  with self.assertRaises(ValueError):self.runcheck(edit=lambda a:a.append({'class':'firrtl.transforms.DontTouchAnnotation','target':'~'+E['top']+'|'+E['product']+'>io.completeBlockImplemented'}))
 def test_bad_structural(self):
  self.m['AddRecFN']['body'].append('intmodule Hidden :')
  with self.assertRaises(ValueError):self.runcheck()
 def test_limits(self):
  for key,val in [('max_bytes',1),('max_line_bytes',8),('max_lines',4),('max_modules',3),('max_instances',2),('max_registers',1),('max_hierarchy_depth',1)]:
   with self.subTest(key=key):
    e=copy.deepcopy(E);e[key]=val
    with self.assertRaises(ValueError):self.runcheck(e=e)
 def test_file_api(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as d:
   p=Path(d)/'synthetic.fir';p.write_bytes(encode(self.m));self.assertEqual(c.check(p,E)['status'],c.STATUS)
 def test_file_symlink(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as d:
   p=Path(d)/'synthetic.fir';p.write_bytes(encode(self.m));q=Path(d)/'link';q.symlink_to(p)
   with self.assertRaises(ValueError):c.check(q,E)
if __name__=='__main__':unittest.main()
