import gzip,json,pathlib,tempfile,unittest
from safe_diagnostics import stage_diagnostics
from summarize_frontend import summarize
class Tests(unittest.TestCase):
 def test_secret_not_exported(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'log.gz'
   with gzip.open(p,'wb') as f:f.write(b'ghp_SECRET_TOKEN subprocess.TimeoutExpired: /private/data')
   r=stage_diagnostics({'native_exit':1,'errors':[],'cleanup_proof':True},p);s=json.dumps(r)
   self.assertNotIn('SECRET',s);self.assertNotIn('/private',s);self.assertIn('PYTHON_TIMEOUT_EXPIRED',s)
 def test_unknown_not_inferred(self):
  r=stage_diagnostics({'native_exit':1,'errors':[],'cleanup_proof':True},'/absent');self.assertEqual(r['root_cause'],'NOT_ESTABLISHED')
 def test_all_stage_summary(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);s=p/'stage_idma';s.mkdir();(s/'RESULT.json').write_text(json.dumps({'native_exit':1,'elapsed_seconds':1,'observed_peak_rss':4,'errors':['TOKEN secret'],'cleanup_proof':True}))
   r=summarize(p,'a'*40);self.assertNotIn('secret',json.dumps(r));self.assertEqual(r['stages'][0]['diagnostics']['failure_codes'],['CHILD_NONZERO_EXIT','SUPERVISOR_REPORTED_ERROR'])
 def test_bad_gzip(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'x';p.write_bytes(b'bad');self.assertEqual(stage_diagnostics({},p)['log_status'],'UNREADABLE')
if __name__=='__main__':unittest.main()
