import hashlib,json,os,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
# Published layout: this file lives directly under candidates/model_candidate_*.
# Isolated helper review: exact known checkout is rooted relative to this source,
# never relative to the shell cwd. An explicit absolute test-only override is
# available when neither normal layout exists.
_override=os.environ.get('HETERO_HELPER_TEST_BASELINE_CANDIDATES')
if _override:
 BASE=pathlib.Path(_override)
 if not BASE.is_absolute():raise ValueError('test baseline override must be absolute')
elif (D.parent/'ci_frontend_pipeline_r2_20261029/PortableHostHighSimulationEmitter.scala').is_file():
 BASE=D.parent
else:
 BASE=D.parents[1]/'trusted_executor_rss2_20261101T0738/candidates'
if not (BASE/'ci_frontend_pipeline_r2_20261029/PortableHostHighSimulationEmitter.scala').is_file():
 raise ValueError('missing test baseline: use explicit HETERO_HELPER_TEST_BASELINE_CANDIDATES')
class ContractTests(unittest.TestCase):
 def test_contract_exact_known_schema_and_metadata(self):
  d=json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text());self.assertEqual(d['schema'],'MODEL_CANDIDATE_GENERATION_PRECONDITIONS_V1')
  self.assertEqual(d['scope'],'SOURCE_REVIEWED_PRECONDITIONS_NOT_POST_BUILD_STRUCTURAL_ACCEPTANCE')
  self.assertEqual(len(d['ports']),122);self.assertEqual(len(d['unchanged_modules']),15)
  self.assertEqual(len(d['bank_subtree_reference_modules']),1056)
  self.assertEqual(d['matrix_providers'],8);self.assertEqual(d['shared_vector_banks'],1)
 def test_contract_digest_is_hardlocked(self):
  h=hashlib.sha256((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_bytes()).hexdigest()
  self.assertIn('private val PreconditionsSha="'+h+'"',(D/'ModelCandidateHostSimulationEmitterV1.scala').read_text())
 def test_old_hashes_are_exact_not_learned(self):
  p=BASE/'observer_ir_only_20261030/evidence/run41114764250/observed-canonical.tsv';raw=p.read_bytes();d=json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text())
  self.assertEqual(hashlib.sha256(raw).hexdigest(),d['legacy_canonical_sha256'])
  rows=[x.split('\t')for x in raw.decode().splitlines()if x.startswith('module\t')]
  self.assertEqual(d['bank_subtree_reference_modules'],[{'name':x[1],'sha256':x[2]}for x in rows]);old={x[1]:x[2]for x in rows}
  self.assertTrue(all(old[x['name']]==x['sha256']for x in d['unchanged_modules']))
 def test_legacy_ports_exact(self):
  self.assertEqual(json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text())['ports'],json.loads((BASE/'ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json').read_text()))
 def test_no_new_acceptance_or_count_guess(self):
  s=(D/'ModelCandidateHostSimulationEmitterV1.scala').read_text();self.assertNotIn('==1056',s);self.assertNotIn('==9022',s)
  self.assertIn('"post_build_structure_accepted"->false',s);self.assertIn('"numerical_pass"->false',s)
  self.assertIn('original entire bank subtree canonical definition drift; no suffix rename bypass',s)
 def test_typed_abi_not_width_only(self):
  d=json.loads((D/'MODEL_CANDIDATE_PRECONDITIONS.json').read_text());self.assertEqual(len(d['typed_ports']),122)
  self.assertEqual({p['name']:[p['direction'],p['width']]for p in d['typed_ports']},d['ports'])
  self.assertEqual(d['typed_ports'][0],{'name':'clock','direction':'input','type':'Clock','width':1})
  self.assertEqual(d['typed_ports'][1],{'name':'reset','direction':'input','type':'UInt<1>','width':1})
  self.assertIn('typedPorts==preconditions("typed_ports")',(D/'ModelCandidateHostSimulationEmitterV1.scala').read_text())
 def test_transform_observation_is_not_acceptance(self):
  s=(D/'ModelCandidateTransformGateV1.scala').read_text()
  self.assertIn('CandidateDenseAccMemoryLoweringV2(intermediate,cp)',s)
  self.assertNotIn('PortableHostDenseAccMemoryLowering(intermediate,cp)',s)
  self.assertIn('"post_build_structure_accepted"->false',s)
  self.assertNotIn('0a41c578',s)
  self.assertIn('eb44e4267684bbb9cf265e88ea89a6910dedd67b2bd2896bb6367928d4ecf831',s)
 def test_diagnostic_is_finite_no_exception_text(self):
  s=(D/'ModelCandidateHighDescriptorV1.scala').read_text();diag=s[s.index('object ModelCandidateDiagnosticV1'):]
  self.assertNotIn('getMessage',diag);self.assertNotIn('e.toString',diag)
  self.assertIn('"DENSE_ACC_LOCAL_SHAPE"',diag);self.assertIn('"FIXED_MODULE_HASH"',diag)
  self.assertIn('"MODEL_CANDIDATE_DIAGNOSTIC.json"',diag);self.assertIn('8192',diag)
  for name,stage in [('ModelCandidateHighDescriptorV1.scala','canonical_full'),('ModelCandidateTransformGateV1.scala','transform_new_toolchain'),('ModelCandidateHostSimulationEmitterV1.scala','emit_host')]:
   self.assertIn('ModelCandidateDiagnosticV1.run("'+stage+'")',(D/name).read_text())
 def test_transform_functions_unchanged(self):
  old=(BASE/'ci_frontend_pipeline_r2_20261029/PortableHostHighSimulationEmitter.scala').read_text();new=(D/'ModelCandidateHostSimulationEmitterV1.scala').read_text()
  for start,end in [('  private def postHigh(', '  private def initializationGate('),('  private def initializationGate(', '  /** Official VerilogPrep'),('  private def finalBindings(', '  private def bitWidth('),('  private def verifyCanonicalLow(', '  private def retain(')]:
   expected=old[old.index(start):old.index(end)].replace('PortableHostDenseAccMemoryLowering.check(c)','CandidateDenseAccMemoryLoweringV2.check(c)')
   self.assertEqual(expected,new[new.index(start):new.index(end)])
if __name__=='__main__':unittest.main()
