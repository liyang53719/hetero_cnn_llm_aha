import copy,json,pathlib,unittest
import validate_launch as g
import summarize_ir as s
D=pathlib.Path(__file__).resolve().parent
class Guard(unittest.TestCase):
 def setUp(self):
  self.source='a'*40;self.head='b'*40
  self.event={'ref':'refs/heads/main','before':self.source,'after':self.head}
  self.manifest={'schema':'OBSERVER_FIXED155_ORIGINAL_IR_ONE_SHOT_V1','source_sha':self.source,'profile':'FIXED4096_OBSERVER8_COMPILE155_HIGH_OFFICIAL_LOW_ONLY','nonce':'observer_fixed155_original_ir_r2_20261030_once'}
 def call(self,manifest=None,diff=None,attempt='1',parent=None,event=None):
  return g.validate(event or self.event,manifest or self.manifest,attempt,self.head,parent or self.source,diff if diff is not None else 'A\t'+g.LAUNCH+'\n')
 def test_positive(self):self.assertEqual(self.call(),self.source)
 def test_old_paths(self):
  for nonce in ('five_m128_samejob_calibration_20261030_once','five_m128_samejob_diagnostic_r2_20261030_once','qwen35_four_m128_freshhost_20261030_once','qwen35_four_m128_freshhost_canonical_r2_20261030_once','qwen35_four_m128_freshhost_python_dso_r3_20261030_once'):
   with self.subTest(nonce=nonce),self.assertRaises(ValueError):self.call(diff='A\tci_launch/'+nonce+'.json\n')
   bad=dict(self.manifest,nonce=nonce)
   with self.assertRaises(ValueError):self.call(manifest=bad)
 def test_retry_modified_extra(self):
  for diff in ('M\t'+g.LAUNCH+'\n','A\t'+g.LAUNCH+'\nM\tcode.py\n',''):
   with self.assertRaises(ValueError):self.call(diff=diff)
  with self.assertRaises(ValueError):self.call(attempt='2')
 def test_source_parent_and_schema(self):
  with self.assertRaises(ValueError):self.call(parent='c'*40)
  for field,value in [('schema','old'),('profile','runtime'),('source_sha','notsha')]:
   with self.assertRaises(ValueError):self.call(manifest=dict(self.manifest,**{field:value}))
 def test_workflow_binding(self):
  w=(D.parents[1]/'.github/workflows/hetero-observer-original-ir-only.yml').read_text()
  for text in (g.LAUNCH,'timeout-minutes: 60','job_budget_seconds=3600','hetero-exclusive-numeric-bootstrap','--execute-reviewed-ir-only','--source-pins-sha256','steps.launch.outputs.source_sha','path: ${{ runner.temp }}/observer-ir-summary.json'):
   self.assertIn(text,w)
  self.assertIn('name: hetero-observer-ir-summary-${{ github.run_id }}',w)
  self.assertIn("artifact_name='hetero-observer-ir-summary-'",(D/'validate_launch.py').read_text())
  self.assertNotIn('GH_TOKEN',w);self.assertNotIn('continue-on-error',w)
class Summary(unittest.TestCase):
 def setUp(self):self.identity=dict(source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,run_id=123)
 def test_missing(self):self.assertEqual(s.project({},self.identity)['status'],'OBSERVATION_UNAVAILABLE')
 def test_strips_payload(self):
  out=s.project({'status':'FAILED_OR_INCOMPLETE','secret':'payload','exception_class':'payload','log':'payload'},self.identity)
  self.assertNotIn('payload',json.dumps(out))
 def test_reject_pass(self):
  for field in s.FLAGS:
   with self.assertRaises(ValueError):s.project({field:True},self.identity)
 def test_numeric_fields_fail_closed(self):
  row=dict(name='jdk',complete=False,native_exit=1,error_count=1,elapsed_seconds=1,observed_peak_rss=1)
  for key,value in [('name','payload'),('error_count','payload'),('elapsed_seconds',float('nan')),('observed_peak_rss',True),('native_exit','payload')]:
   with self.assertRaises(ValueError):s.project({'stages':[dict(row,**{key:value})]},self.identity)
 def test_complete_requires_stages_and_artifacts(self):
  with self.assertRaises(ValueError):s.project({'status':s.COMPLETE},self.identity)
 def test_positive_complete(self):
  raw=dict(status=s.COMPLETE,stages=[dict(name=n,complete=True,native_exit=0,error_count=0,elapsed_seconds=1,observed_peak_rss=1) for n in s.STAGES],artifacts={n:dict(bytes=1,sha256='d'*64) for n in s.NAMES},measured_top_port_counts={'high':30,'low':122})
  out=s.project(raw,self.identity);self.assertEqual(out['status'],s.COMPLETE);self.assertFalse(out['numerical_pass'])
  raw['artifacts']['evil']='payload'
  with self.assertRaises(ValueError):s.project(raw,self.identity)
if __name__=='__main__':unittest.main()
