"""Portable derived source/contract checks only. No compiler, model, producer or subprocess."""
import ast,hashlib,itertools,json,sys,unittest
from pathlib import Path
P=Path(__file__).resolve().parent;sys.dont_write_bytecode=True;sys.path.insert(0,str(P))
import cold_contract as c
class Cold(unittest.TestCase):
 def valid_loan(self):
  t=c.Trace();g=((7<<16)|17,0,0,0);u=(*g[:3],1);a=(0x3f800000,)*16;b=(0x40000000,)*16
  t.accept_read(g);t.response(g,a);t.accept_read(u);t.response(u,b,(True,)*5,((a,b),)*5);return t
 def test_original_source_bytes(self):
  expected={'silu_observer.hpp':'4517356fae02531b1eab19d825423440c197bfeb0f5269475dda501da1225245','cold_contract.py':'12ba721acd31087e8b0efa5288dafe603eaf18782bc95ed6599135f9f6640032'}
  for name,digest in expected.items():self.assertEqual(hashlib.sha256((P/name).read_bytes()).hexdigest(),digest)
 def test_syntax(self):
  for f in P.glob('*.py'):ast.parse(f.read_text())
 def test_single_exact_qualification_conjunction(self):
  self.assertEqual(set(__import__('re').findall(r'q\.(\w+)',c.EXPR)),set(c.FIELDS));self.assertTrue(c.guard(c.good_guard()))
 def test_all_guard_combinations(self):
  accepted=0
  for row in itertools.product((False,True),repeat=len(c.FIELDS)):
   fields=dict(zip(c.FIELDS,row));result=c.guard(fields);accepted+=result
   self.assertEqual(result,fields==c.good_guard())
  self.assertEqual(accepted,1)
 def test_raw_valid_alone(self):
  fields={n:False for n in c.FIELDS};fields['raw_valid']=True;self.assertFalse(c.guard(fields))
 def test_each_guard_negative(self):
  for n in c.FIELDS:
   f=c.good_guard();f[n]=not f[n]
   with self.subTest(n=n):self.assertFalse(c.guard(f))
 def test_guard_non_bool_and_missing(self):
  for n in c.FIELDS:
   for x in [0,1,0.0,1.0,None,'true']:
    f=c.good_guard();f[n]=x
    with self.assertRaises(ValueError):c.guard(f)
  f=c.good_guard();f.pop('loan_matched')
  with self.assertRaises(ValueError):c.guard(f)
 def test_valid_small_contract_trace_is_only_provisional(self):
  t=self.valid_loan();t.capture(c.good_guard());t.result();self.assertEqual(t.count,1)
  self.assertLess(t.count,128*8960//16)
 def test_unmatched_or_reordered_response(self):
  for k in [((7<<16)|17,0,0,1),((7<<16)|18,0,0,0),((7<<16)|17,160,0,0),((7<<16)|17,0,1,0)]:
   t=c.Trace();t.accept_read(((7<<16)|17,0,0,0))
   with self.assertRaises(ValueError):t.response(k,(0,)*16)
   self.assertTrue(t.fatal)
 def test_raw_without_real_loan(self):
  with self.assertRaises(ValueError):c.Trace().capture(c.good_guard())
 def test_duplicate_raw_fatal(self):
  t=self.valid_loan();t.capture(c.good_guard())
  with self.assertRaises(ValueError):t.capture(c.good_guard())
  with self.assertRaises(ValueError):t.result()
 def test_result_cannot_substitute_silu(self):
  with self.assertRaises(ValueError):self.valid_loan().result()
 def test_missing_request_path_and_wrong_payload(self):
  a=(1,)*16;b=(2,)*16;g=((7<<16)|17,0,0,0);u=(*g[:3],1)
  for i in range(5):
   for wrong_payload in (False,True):
    t=c.Trace();t.accept_read(g);t.response(g,a);t.accept_read(u)
    fires=[True]*5;payloads=[(a,b)]*5
    if wrong_payload:payloads[i]=(b,a)
    else:fires[i]=False
    with self.assertRaises(ValueError):t.response(u,b,tuple(fires),tuple(payloads))
 def test_late_abort_sticky(self):
  t=self.valid_loan();t.capture(c.good_guard())
  with self.assertRaises(ValueError):t.abort()
  with self.assertRaises(ValueError):t.result()
 def test_all_canonical_coordinates_unique_and_complete(self):
  coords=set()
  for ng in range(0,8960,160):
   for index in range(1280):
    point=c.coordinate(((7<<16)|17,ng,index,1),0);coords.add(point)
    self.assertEqual(c.coordinate(((7<<16)|17,ng,index,1),15),(0,point[1]+15,point[2]))
  self.assertEqual(len(coords)*16,128*8960);self.assertIn((0,0,0),coords);self.assertIn((0,112,8959),coords)
 def test_coordinate_bounds_and_identity(self):
  for k in [((7<<16)|18,0,0,1),((7<<16)|17,-160,0,1),((7<<16)|17,8960,0,1),((7<<16)|17,1,0,1),((7<<16)|17,0,1280,1),((7<<16)|17,0,-1,1),((7<<16)|17,0,0,0)]:
   with self.assertRaises(ValueError):c.coordinate(k,0)
  for lane in [-1,16,True,1.0]:
   with self.assertRaises(ValueError):c.coordinate(((7<<16)|17,0,0,1),lane)
 def test_unbound_generated_path_always_incomplete(self):
  s=c.SOURCE.split('template<class ActualHostModel> class GeneratedBinding {',1)[1].split('struct Qualification',1)[0]
  self.assertEqual(s.count('throw Incomplete('),4);self.assertNotIn('return ',s)
  req=json.loads((P/'BINDING_REQUIREMENTS.json').read_text());self.assertFalse(req['generated_binding_complete'])
  self.assertTrue(all(x['generated_cpp_symbol'] is None for x in req['groups']))
 def test_pre_post_edge_and_sticky_failure_source(self):
  for token in ['edge==edge_+1','!pending_edge_','pending_edge_&&edge==edge_','!pre_.clock&&!pre_.reset','post.clock&&!post.reset','failed_=true;throw;',
                'read_before&&outstanding_read_','f.loan_context.active==loan_before','post.loan_context.active==bool(loan_key_)','!f.raw_silu_valid&&stage_==Stage::Loan','f.vector_state==3']:
   self.assertIn(token,c.SOURCE)
  self.assertEqual(c.SOURCE.count('catch(...) {failed_=true;throw;}'),3)
 def test_early_coverage_failure_cannot_be_repaired(self):
  t=self.valid_loan()
  with self.assertRaises(ValueError):t.coverage()
  with self.assertRaises(ValueError):t.capture(c.good_guard())
  body=c.SOURCE.split('void require_provisional_silu_coverage()',1)[1]
  self.assertIn('catch(...) {failed_=true;throw;}',body)
  self.assertNotIn('coverage()const',c.SOURCE)
 def test_no_arithmetic_or_expected_input(self):
  for token in ['std::exp','std::pow','std::fma','reinterpret_cast<float','expected.npy','silu.npy','return true;']:
   self.assertNotIn(token,c.SOURCE)
  self.assertIn('f.raw_silu_value==f.vector_value',c.SOURCE)
  self.assertIn('f.raw_silu_value};',c.SOURCE)
 def test_capture_counter_is_actual_event_increment(self):
  self.assertEqual(c.SOURCE.count('++captures_'),1)
  self.assertIn('require(qualified(q)',c.SOURCE);self.assertIn('raw_seen_=true;++captures_',c.SOURCE)
  self.assertIn('captures_==expected_vectors',c.SOURCE)
 def projection(self):return json.loads((P/'SV_LOGICAL_LEAVES.json').read_text())
 def test_projection_schema_and_cardinality(self):
  j=self.projection()
  self.assertEqual(j['schema'],1)
  self.assertEqual(j['columns'],['member','module_signal','width','access_kind'])
  self.assertEqual(len(j['pre']),468);self.assertEqual(len(j['post']),13)
  self.assertEqual(set(j),{'schema','scope','columns','pre','post','alias_limits','generated_binding_complete','runtime_capture_proved','Host_RTL_run_pass','projection_omissions'})
  for phase in ('pre','post'):
   self.assertEqual(len({r[0] for r in j[phase]}),len(j[phase]))
   for row in j[phase]:
    self.assertEqual(len(row),4)
    self.assertRegex(row[0],r'^'+phase+r'\.[A-Za-z_][A-Za-z0-9_.\[\]]*$')
    self.assertRegex(row[1],r'^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$')
    self.assertIs(type(row[2]),int);self.assertIn(row[2],(1,2,3,4,8,11,16,32))
    self.assertIn(row[3],('direct','alias'))
 def test_logical_projection_is_unbound(self):
  j=self.projection()
  self.assertIn('NOT_ORIGINAL_BYTES_NOT_RUNTIME_BINDING',j['scope'])
  for k in ('generated_binding_complete','runtime_capture_proved','Host_RTL_run_pass'):self.assertIs(j[k],False)
  for forbidden in ('declaration','sv_line','sv_byte_start','sv_sha256','qualification_sv_path','collection_sv_path','generated_cpp_symbol'):
   self.assertNotIn(chr(34)+forbidden+chr(34)+':',(P/'SV_LOGICAL_LEAVES.json').read_text())
 def test_alias_is_only_named_existing_wire(self):
  j=self.projection();aliases=[r for r in j['pre']+j['post'] if r[3]=='alias']
  self.assertEqual(aliases,[['pre.bridge_call.cols','FfnTileSiluBridge.io_tiles_control_bits_cols',8,'alias']])
  self.assertEqual(j['alias_limits']['member'],aliases[0][0])
  self.assertEqual(j['alias_limits']['observed'],aliases[0][1])
  self.assertIn('INCOMPLETE',j['alias_limits']['scope'])
 def test_post_leaves_refer_to_same_logical_sources(self):
  j=self.projection();pre={r[0]:r for r in j['pre']}
  for r in j['post']:self.assertEqual(r[1:3],pre['pre.'+r[0][5:]][1:3])
 def test_raw_tap_words_are_exact_sixteen_32bit_leaves(self):
  rows={r[0]:r for r in self.projection()['pre']}
  self.assertEqual(rows['pre.raw_silu_valid'][1:3],['SiluVectorUnit.canonicalSiluTap_valid',1])
  for lane in range(16):
   self.assertEqual(rows[f'pre.raw_silu_value[{lane}]'][1:3],[f'SiluVectorUnit.canonicalSiluTap_value_{lane}',32])
   self.assertEqual(rows[f'pre.vector_value[{lane}]'][1:3],[f'SiluVectorUnit.value_{lane}',32])
 def test_derived_requirements_have_no_source_locations(self):
  j=json.loads((P/'BINDING_REQUIREMENTS.json').read_text())
  self.assertIn('NOT_ORIGINAL_BYTES_NOT_RUNTIME_BINDING',j['scope'])
  self.assertEqual(len(j['groups']),15)
  for group in j['groups']:
   self.assertNotIn('source',group)
   self.assertTrue(group['source_modules'])
   for name in group['source_modules']:self.assertRegex(name,r'^[A-Za-z_][A-Za-z0-9_]*$')
 def test_payload_is_self_contained_source_only(self):
  self.assertEqual({x.name for x in P.iterdir()}, {'silu_observer.hpp','cold_contract.py','BINDING_REQUIREMENTS.json','SV_LOGICAL_LEAVES.json','test_portable_cold.py','README_CN.md'})
  for f in P.iterdir():self.assertTrue(f.is_file() and not f.is_symlink())
  self.assertNotIn('W'+'/',Path(__file__).read_text())
if __name__=='__main__':unittest.main(verbosity=2)
