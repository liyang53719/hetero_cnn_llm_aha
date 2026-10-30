"""SYNTHETIC export-only fixtures. No Java/SV execution and never acceptance evidence."""
import json,pathlib,tempfile,time,unittest,sys
from unittest.mock import patch
import contract as c
import export_metadata as e
import test_projection
from validate_launch import LAUNCH

def setup_fixture(d):
 work=d/'work';work.mkdir();identity=dict(run_id=1,artifact_name='hetero-observer-sv-only-summary-1',source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,launch_manifest_path=LAUNCH)
 def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x))
 put(d/'identity.json',identity);put(work/'IDENTITY.json',identity);put(d/'clock.json',dict(schema='SAME_JOB_START_V1',started_monotonic=time.monotonic()-2,job_budget_seconds=10800,run_id=1,launch_commit='b'*40))
 for n,wall,rss in c.STAGES:
  put(work/n/'RESULT.json',dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture=dict(pipe_eof_observed=True,gzip_finalized=True),caps=dict(wall_seconds=wall,cleanup_seconds=30,rss_bytes=rss<<30,max_entries=100000),elapsed_seconds=1.0,observed_peak_rss=10000))
 saved=[]
 for n,_,_ in c.STAGES:
  x=e.stage_row(n,work/n/'RESULT.json');saved.append({k:x[k]for k in ('name','native_exit','elapsed_seconds','observed_peak_rss','strict_complete','error_count','result_sha256')})
 put(work/'STAGES.json',saved);proof=test_projection.T().proof_fixture();sv_inputs={};canonical_paths={}
 for side in ('old','new'):
  sv=work/(side+'_emit_sv')/'compiled-host/HostBlockTopV4.sv';sv.parent.mkdir(parents=True);sv.write_bytes(b'SYNTHETIC_EXPLICITLY_NOT_REAL_SV')
  canon=work/(side+'_canonical')/'canonical.tsv';canon.write_bytes(b'SYNTHETIC_CANONICAL_TEST_DOUBLE');canonical_paths[str(canon)]=c.CANONICAL[side]
  scan=work/(side+'_svscan')/'sv-identity.json';put(scan,dict(normalized_sha256=c.NORMALIZED[side],raw_sha256=c.sha(sv),bytes=sv.stat().st_size))
  sv_inputs[side]=dict(sha256=c.sha(sv),bytes=sv.stat().st_size)
  proof['full_sv'][side]=dict(bytes=sv.stat().st_size,raw_sha256=c.sha(sv),normalized_sha256=c.NORMALIZED[side],metadata_sha256=c.sha(scan),scan_receipt_sha256=c.sha(scan.parent/'RESULT.json'))
 put(work/'projection/proof.json',proof)
 java=d/'bin/java';java.parent.mkdir();java.write_bytes(b'SYNTHETIC_JAVA_NOT_EXECUTABLE');h=c.sha(java)
 runtime=dict(schema='SV_ONLY_JDK_PYTHON_IDENTITY_V1',old_pass_transfer=False,scope='IDENTITY_ONLY_NO_RUNTIME_CPU_OR_NUMERICAL_QUALIFICATION',contract=dict(schema='BOUNDED_FRESH_HOST_V1',**{k:identity[k]for k in ('run_id','source_commit','launch_commit')}),pins={str(java):h},jdk=dict(status='NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION',old_pass_transfer=False,version=dict(JAVA_VERSION='21.0.13',IMPLEMENTOR='Eclipse Adoptium',JAVA_RUNTIME_VERSION='21.0.13+9'),actual_runtime_properties={'java.vendor':'Eclipse Adoptium','java.runtime.version':'21.0.13+9','os.arch':'amd64'},files=[dict(path='bin/java',sha256=h)]))
 put(work/'jdk-runtime.json',runtime)
 complete=dict(schema='SV_ONLY_RECONSTRUCTION_COMPLETE_V1',identity=identity,source_pins_sha256=c.sha(c.D/'SOURCE_PINS.json'),runtime_inventory_sha256=c.sha(work/'jdk-runtime.json'),proof_sha256=c.sha(work/'projection/proof.json'),canonical_sha256=c.CANONICAL,normalized_sha256=c.NORMALIZED,sv_inputs=sv_inputs,stage_count=15,numerical_pass=False,sv_repin_authorized=False);put(work/'COMPLETE.json',complete)
 return work,canonical_paths
class ExportFlow(unittest.TestCase):
 def execute(self,d,work,canonical):
  actual_sha=e.sha
  def fake_canonical_sha(p):return canonical[str(p)]if str(p)in canonical else actual_sha(p)
  args=['export_metadata.py','--repo',str(d),'--work',str(work),'--identity',str(d/'identity.json'),'--job-start',str(d/'clock.json'),'--output',str(d/'output')]
  # Only source checkout and two canonical-byte artifacts are explicit test doubles;
  # real production project_proof, all15 RESULTs, runtime, COMPLETE, bindings and main run.
  with patch.object(e,'closure',return_value={}),patch.object(e,'sha',side_effect=fake_canonical_sha),patch.object(sys,'argv',args):e.main()
  out=d/'output';self.assertEqual({p.name for p in out.iterdir()},{'sv-only-proof.json','sv-only-summary.json'});summary=json.loads((out/'sv-only-summary.json').read_text());self.assertEqual(summary['proof_file'],dict(name='sv-only-proof.json',bytes=(out/'sv-only-proof.json').stat().st_size,sha256=c.sha(out/'sv-only-proof.json')));self.assertFalse(summary['numerical_pass']);self.assertFalse(summary['sv_repin_authorized']);self.assertLessEqual(sum(p.stat().st_size for p in out.iterdir()),131072)
  return summary,json.loads((out/'sv-only-proof.json').read_text())
 def test_full_synthetic_export(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can=setup_fixture(d);s,p=self.execute(d,w,can);self.assertEqual(s['status'],'TWO_MODULE_PROJECTION_OBSERVED_NOT_PRODUCTION_ACCEPTANCE');self.assertEqual(len(s['stages']),15);self.assertEqual(p['schema'],'EXACT_TWO_MODULE_KEY_PROJECTION_V1');self.assertEqual(s['runtime_provenance']['version'],'21.0.13')
 def test_missing_complete_exports_unavailable(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can=setup_fixture(d);(w/'COMPLETE.json').unlink();s,p=self.execute(d,w,can);self.assertEqual(s['status'],'OBSERVATION_UNAVAILABLE_OR_INCOMPLETE');self.assertEqual(p['schema'],'SV_ONLY_PROOF_UNAVAILABLE_V1');self.assertEqual(len(s['stages']),15)
 def test_proof_wrong_actual_binding_not_accepted(self):
  with tempfile.TemporaryDirectory()as td:
   d=pathlib.Path(td);w,can=setup_fixture(d);p=w/'projection/proof.json';proof=json.loads(p.read_text());proof['full_sv']['new']['metadata_sha256']='d'*64;p.write_text(json.dumps(proof));p=w/'COMPLETE.json';complete=json.loads(p.read_text());complete['proof_sha256']=c.sha(w/'projection/proof.json');p.write_text(json.dumps(complete));s,p=self.execute(d,w,can);self.assertEqual(s['status'],'OBSERVATION_UNAVAILABLE_OR_INCOMPLETE');self.assertEqual(p['schema'],'SV_ONLY_PROOF_UNAVAILABLE_V1')
if __name__=='__main__':unittest.main()
