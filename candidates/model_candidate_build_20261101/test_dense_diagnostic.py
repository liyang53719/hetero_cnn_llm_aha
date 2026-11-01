import importlib.util,pathlib,re,unittest
D=pathlib.Path(__file__).resolve().parent
BASE=D.parent
if not (BASE/'ci_frontend_pipeline_r2_20261029/PortableHostDenseAccMemoryLowering.scala').is_file():raise ValueError('repo-local original Dense transform required')
s=importlib.util.spec_from_file_location('dense_diag',D/'candidate_diagnostic.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def doc(self):return dict(schema='MODEL_CANDIDATE_DIAGNOSTIC_V1',stage='transform_new_toolchain',status='REJECTED_UNREVIEWED',reason_code='DENSE_ACC_LOCAL_SHAPE',actual=dict(dense_predicate_code='ZERO_EXACT_LITERAL',dense_zero_elements=256),numerical_pass=False,post_build_structure_accepted=False)
 def test_exact_finite_code(self):self.assertEqual(m.project(self.doc(),'transform_new_toolchain'),self.doc())
 def test_scala_codes_match(self):
  s=(D/'CandidateDenseAccMemoryLoweringV2.scala').read_text();codes=set(re.findall(r'"([A-Z_]+)"',re.search(r'PredicateCodes:Set\[String\]=Set\((.*?)\)',s).group(1)));self.assertEqual(codes,m.DENSE_PREDICATES)
 def test_reject_rawcode(self):
  d=self.doc();d['actual']['dense_predicate_code']='private path /token'
  with self.assertRaises(ValueError):m.project(d,'transform_new_toolchain')
 def test_reject_boolean_counter(self):
  d=self.doc();d['actual']['dense_zero_elements']=True
  with self.assertRaises(ValueError):m.project(d,'transform_new_toolchain')
 def test_reject_success_code(self):
  d=self.doc();d.update(status='OBSERVED_COMPLETE_UNREVIEWED',reason_code='NONE')
  with self.assertRaises(ValueError):m.project(d,'transform_new_toolchain')
 def test_reject_other_phase_code(self):
  d=self.doc();d['reason_code']='CANONICAL_IDENTITY'
  with self.assertRaises(ValueError):m.project(d,'transform_new_toolchain')
 def test_no_generated_names_gate(self):
  s=(D/'CandidateDenseAccMemoryLoweringV2.scala').read_text();self.assertNotIn('"_WIRE_26"',s);self.assertNotIn('"_WIRE_44"',s);self.assertIn('elementCount==8192',s);self.assertIn('owned.size==34',s);self.assertIn('sameBlock(s,write)<sameBlock(next,write)',s);self.assertIn('rc.forall(_.expr==UIntLiteral(0,IntWidth(32)))',s)
 def test_old_transform_substitutions_exact(self):
  old=(BASE/'ci_frontend_pipeline_r2_20261029/PortableHostDenseAccMemoryLowering.scala').read_text();new=(D/'CandidateDenseAccMemoryLoweringV2.scala').read_text()
  for a,b in [('  private def declaration:', '  def apply(')]:
   # All storage data/path construction before new proof is byte-identical.
   original=old[old.index(a):old.index(b)];actual=new[new.index(a):new.index('  /** Prove exactly')];self.assertEqual(original.strip(),actual.strip())
if __name__=='__main__':unittest.main()
