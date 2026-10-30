"""Synthetic metadata only; cannot establish actual CI execution or acceptance."""
import importlib.util,json,pathlib,tempfile,unittest
import audit_artifact as a
class Audit(unittest.TestCase):
 def fixture(self,root):
  m=a.load_module();canonical=a.OLD_CANONICAL.read_bytes();head,mods=a.rows(canonical)
  contract=json.loads((a.SRC/'PORT_CONTRACT.json').read_text())
  detail={'schema':'OBSERVED_HIGH_DESCRIPTOR_V1','qualification':'OBSERVED_UNREVIEWED','main':'HostBlockTopV4','canonical_algorithm':'CanonicalHighGate_public_semantic_methods','module_count':len(mods),'annotation_count':1,'target_dir_annotation_count':1,'retained_annotation_count':0,'annotation_classes':{'firrtl2.options.TargetDirAnnotation':1},'circuit_sha256':head['circuit'],'ordered_annotations_sha256':head['annotations_order_preserved'],'low_port_source':'ORIGINAL_HELPER_HASH_BOUND_EXTRACTION_NOT_FULL_LOW_REPARSE','ports':[dict(name=n,direction=v[0],width=v[1],type='Clock'if n=='clock'else'UInt<'+str(v[1])+'>')for n,v in {**contract['old_ports'],**contract['added_ports']}.items()]}
  dd=root/'metadata';dd.mkdir();(dd/'observed-canonical.tsv').write_bytes(canonical);(dd/'observed-details.json').write_text(json.dumps(detail));artifacts={n:dict(bytes=1,sha256='a'*64)for n in m.INPUTS};receipt=m.inspect(dd,artifacts,contract)
  identity=dict(source_commit='97555642bee1b7a40047db8677d28f1f89185bce',launch_commit='ec198c27364fc537da06d6430bf27607d9865596',launch_manifest_blob_sha='ce88cb7cefdb7e71d937fcabb342d5c02e031562',run_id=41114764250)
  prov=dict(identity,schema='OBSERVED_DESCRIPTOR_PROVENANCE_V1',qualification='OBSERVED_UNREVIEWED',descriptor=receipt);(dd/'provenance.json').write_text(json.dumps(prov))
  summary=dict(identity,status='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY',descriptor=receipt,artifacts=artifacts,stages=[dict(name=n,native_exit=0,error_count=0,complete=True,admission=dict(status='ADMITTED',census_complete=True,execute_called=True))for n in ('jdk','compile_tools','jars','verilator_bytes','runtime_identity','compile155','helper_compile','original_ir','descriptor')],**{k:False for k in ('numerical_pass','canonical_pass','target_host_qualified','sv_generated','generated_abi_qualification','physical_resource_or_qor_qualification','block_numerical_pass')})
  sp=root/'summary.json';sp.write_text(json.dumps(summary));return dd,sp,summary
 def test_fixture_no_acceptance_and_candidate_mismatch(self):
  with tempfile.TemporaryDirectory()as t:
   dd,sp,s=self.fixture(pathlib.Path(t));r=a.audit(dd,sp);self.assertFalse(r['acceptance_authorized']);self.assertFalse(r['annotations']['candidate_full_raw_and_ordered_match']);self.assertEqual(r['changed_modules'],[]);self.assertEqual(len(r['expected_modules_not_changed']),8)
 def test_wrong_identity(self):
  with tempfile.TemporaryDirectory()as t:
   dd,sp,s=self.fixture(pathlib.Path(t));s['run_id']=1;sp.write_text(json.dumps(s))
   with self.assertRaises(ValueError):a.audit(dd,sp)
 def test_metadata_tamper(self):
  with tempfile.TemporaryDirectory()as t:
   dd,sp,s=self.fixture(pathlib.Path(t));p=dd/'observed-details.json';p.write_text(p.read_text()+' ')
   with self.assertRaises(ValueError):a.audit(dd,sp)
 def test_reject_numeric_claim(self):
  with tempfile.TemporaryDirectory()as t:
   dd,sp,s=self.fixture(pathlib.Path(t));s['numerical_pass']=True;sp.write_text(json.dumps(s))
   with self.assertRaises(ValueError):a.audit(dd,sp)
if __name__=='__main__':unittest.main()
