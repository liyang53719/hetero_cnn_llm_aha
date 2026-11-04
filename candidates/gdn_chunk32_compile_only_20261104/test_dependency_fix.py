"""Pure metadata/source tests. No subprocess, networking, dependency fetch or CI."""
import json,hashlib,os,sys,unittest,tempfile,gzip
from pathlib import Path
O=Path(__file__).resolve().parent;sys.path.insert(0,str(O))
import restore_compile_inputs as r,safe_pin_diagnostics as d,safe_compile_summary as summaries
B=Path(os.environ['GDN32_BASE']).resolve() if 'GDN32_BASE'in os.environ else O.parent.parent
C=Path(os.environ['GDN32_CANDIDATE']).resolve() if 'GDN32_CANDIDATE'in os.environ else B/r.CANDIDATE_REL
def audit(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.fork','socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('PURE_ONLY')
sys.addaudithook(audit)
class Tests(unittest.TestCase):
 def test_actual_five_legacy_conflicts(self):
  legacy=Path(os.environ.get('GDN32_LEGACY_BASE',str(B)));m=json.loads((legacy/r.TOOLCHAIN).read_text());fresh=legacy/'candidates/fresh_original_top_recovery_20261028';bad=[]
  for row in m['sources']:
   p=fresh/row['path']
   if r.sha(p)!=row['sha256']:bad.append(dict(name=p.name,expected=row['sha256'],actual=r.sha(p)))
  fixture=json.loads((O/'LEGACY155_CONFLICT_REGRESSION.json').read_text());expected=[dict(name=Path(x['repo_path']).name,expected=x['expected_sha256'],actual=x['actual_sha256'])for x in fixture['mismatches']]
  self.assertEqual(bad,expected);self.assertEqual(len(bad),5)
 def test_unchanged_original_manifest(self):self.assertEqual(r.sha(B/r.TOOLCHAIN),r.TOOLCHAIN_SHA256)
 def test_full_dual_source_closure(self):
  pins,selection,_=r.source_closure(B,C);self.assertEqual(len(selection['source_paths']),162)
  scala=[p for p in pins if p.endswith('.scala')];self.assertEqual(len(scala),172)
  for p,h in pins.items():self.assertEqual(r.sha(p),h)
  self.assertEqual(sum(Path(p).name=='CancellableHeldDecoupledOfferV1.scala'for p in selection['source_paths']),1);self.assertIn(selection['helper'],pins)
 def test_model_metadata_closed(self):
  pins,_,_=r.source_closure(B,C)
  for n in (r.MODEL_RESTORE,r.TOOLCHAIN,'candidates/model_candidate_build_20261101/candidate_generation_gate.py','candidates/model_candidate_build_20261101/GENERATION_CONTRACT.json','candidates/model_candidate_build_20261101/MODEL_SOURCE_OVERLAY.json','candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json'):self.assertIn(str(B/n),pins)
 def test_actual_verify_only_no_download(self):
  result=r.run(B,C,False,True);self.assertEqual(result['status'],'SOURCE162_AND_MODEL159_JAR_INVENTORY_VERIFIED_ONLY');self.assertEqual(result['source_count'],162);self.assertEqual(result['legacy_gate_source_count'],159);self.assertEqual(result['verified_jar_count'],0);self.assertFalse(result['compiler_executed'])
 def test_both_fetch_and_compile_keep_closure(self):
  s=(O/'compile_only.py').read_text();self.assertIn('fetchpins=merge_pins(commonpins,source_pins)',s);self.assertIn('pins=merge_pins(commonpins,source_pins)',s);self.assertNotIn("for row in m['sources']",s)
 def test_no_observed_source_pin_overwrite(self):
  s=(O/'compile_only.py').read_text();self.assertNotIn('pins[s]=sha(s)',s);self.assertNotIn('pins[str(candidate/name)]=sha(candidate/name)',s);self.assertIn("for path,digest in source_pins.items():need(sha(path)==digest,'cross-phase source pin drift')",s)
 def test_original_helper_full_gate_not_bypassed(self):self.assertIn("helper.run(download,verify_only,'legacy')",(O/'restore_compile_inputs.py').read_text())
 def test_pin_failure_safe_known_role_hashes(self):
  with tempfile.TemporaryDirectory()as t:
   p=Path(t)/'actual.scala';p.write_text('actual bytes');expected='a'*64;raw=str(p);receipt={'errors':['ValueError: input pin mismatch '+raw]}
   rows=d.pin_failures(receipt,{raw:expected},{raw:{'role':'REVIEWED_SOURCE','label':'candidates/source/Actual.scala'}})
   self.assertEqual(rows[0]['expected_sha256'],expected);self.assertEqual(rows[0]['actual_sha256'],r.sha(p));self.assertEqual(rows[0]['label'],'candidates/source/Actual.scala');self.assertNotIn(t,json.dumps(rows))
 def test_untrusted_pin_error_not_echoed(self):
  self.assertEqual(d.pin_failures({'errors':['ValueError: input pin mismatch /private/token=secret']},{},{}),[])
 def test_model_failure_reason_safe_summary(self):
  r=dict(schema='GDN32_COMPILE_INPUT_STATUS_V1',status='INCOMPLETE',reason='JAR_HTTP_ERROR',http_status=503,source_count=162,legacy_gate_source_count=159,verified_jar_count=3,required_jar_count=107,jar_index=3,compiler_executed=False,numerical_pass=False,ignored_secret='never show')
  result=summaries.input_status(json.dumps(r).encode());self.assertEqual(result['reason'],'JAR_HTTP_ERROR');self.assertNotIn('never show',json.dumps(result))
 def test_real_status_with_null_http_survives_summary(self):
  actual=r.run(B,C,False,True);self.assertIsNone(actual['http_status']);safe=summaries.input_status(json.dumps(actual).encode());self.assertIsNotNone(safe);self.assertEqual(safe['source_count'],162)
 def test_network_reason_with_null_http(self):
  actual=dict(schema='GDN32_COMPILE_INPUT_STATUS_V1',status='INCOMPLETE',reason='JAR_NETWORK_ERROR',http_status=None,source_count=162,legacy_gate_source_count=159,verified_jar_count=0,required_jar_count=107,jar_index=0,compiler_executed=False,numerical_pass=False);safe=summaries.input_status(json.dumps(actual).encode());self.assertEqual(safe['reason'],'JAR_NETWORK_ERROR');self.assertIsNone(safe['http_status'])
 def test_unbounded_reason_rejected(self):
  self.assertIsNone(summaries.input_status(json.dumps(dict(schema='GDN32_COMPILE_INPUT_STATUS_V1',status='INCOMPLETE',reason='secret',compiler_executed=False,numerical_pass=False)).encode()))
if __name__=='__main__':unittest.main(verbosity=2)
