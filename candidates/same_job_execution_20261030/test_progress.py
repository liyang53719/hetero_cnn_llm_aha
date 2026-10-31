import ast,importlib.util,json,pathlib,tempfile,unittest,sys,types
from unittest.mock import patch
D=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('progress',D/'summary_progress.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def line(n=1,phase='running'):
 return ('HOST_PROGRESS '+phase+' '+' '.join(k+'='+str(n if k in ('cycles','active_cycles') else 0)for k in m.KEYS)+'\n').encode()
class Tests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name);self.log=self.root/'profile0.log'
 def tearDown(self):self.t.cleanup()
 def parse(self,data):self.log.write_bytes(data);return m.parse_log(self.log,self.root)
 def test_fields(self):
  r=self.parse(line(0,'reset')+b'some private text\n'+line(1048576));self.assertEqual(r['sample_count'],2);self.assertEqual(r['last']['active_cycles'],1048576);self.assertNotIn('private',json.dumps(r))
 def test_empty(self):self.assertIsNone(self.parse(b'no trace yet\n')['last'])
 def test_bad(self):
  for data in (line().replace(b'pc=0',b'pc=private'),line()+line(0),line().replace(b'cycles=1',b'cycles=-1',1),line().replace(b'pc=0',b'cycles=0'),line()[:-1],b'HOST_PROGRESS '+b'x'*8192):
   with self.subTest(data=data[:60]),self.assertRaises(ValueError):self.parse(data)
 def test_symlink(self):
  target=self.root/'actual';target.write_bytes(line());self.log.symlink_to(target)
  with self.assertRaises(ValueError):m.parse_log(self.log,self.root)
 def fixture(self):
  root=self.root/'materials/numeric';out=root/'profile0/material/dut_result';out.mkdir(parents=True);outer=root/'runs/p0_dut/RESULT.json';outer.parent.mkdir(parents=True)
  ident={'run_id':1,'source_commit':'a'*40,'launch_commit':'b'*40}
  report={'artifact_identity':ident,'artifact_manifest_sha256':'c'*64,'runtime_bundle_sha256':'d'*64}
  start={'binary_sha256':'e'*64,'runtime_sha256':'f'*64}
  for p,v in ((out/'RESULT.json',report),(out/'profile0.started.json',start),(outer,{'elapsed_seconds':300})):
   p.write_text(json.dumps(v))
  (out/'profile0.log').write_bytes(line(100))
  fake=types.SimpleNamespace(pin=lambda p:{'sha256':'1'*64},verify=lambda *args:{'common_artifact_identity':{'binary':'e'*64},'report':{'sha256':'2'*64},'startup':{'sha256':'3'*64},'outer':{'sha256':'4'*64}})
  return ident,fake,out,outer
 def test_mock_projection_partial_never_qualification(self):
  ident,fake,_,_=self.fixture()
  with patch.dict(sys.modules,{'dut_evidence':fake}):r=m.project(self.root,ident)
  self.assertEqual(r['profiles'][0]['observed_cycles_per_outer_second'],100/300);self.assertFalse(r['numerical_pass']);self.assertIsNone(r['profiles'][0]['full_block_total_cycles']);self.assertEqual(r['profiles'][4]['status'],'UNAVAILABLE')
 def test_real_verifier_rejection_not_bypassed(self):
  ident,fake,_,_=self.fixture();fake.verify=lambda *args:(_ for _ in()).throw(ValueError('cleanup incomplete'))
  with patch.dict(sys.modules,{'dut_evidence':fake}):r=m.project(self.root,ident)
  self.assertEqual(r['profiles'][0]['status'],'UNAVAILABLE');self.assertIsNone(r['profiles'][0]['last'])
 def test_reset_only_rate_unknown(self):
  ident,fake,out,_=self.fixture();(out/'profile0.log').write_bytes(line(0,'reset'))
  with patch.dict(sys.modules,{'dut_evidence':fake}):r=m.project(self.root,ident)
  self.assertEqual(r['profiles'][0]['status'],'NO_ACTIVE_PROGRESS_SAMPLE');self.assertIsNone(r['profiles'][0]['observed_cycles_per_outer_second'])
 def test_optional_import_failure_does_not_escape(self):
  tree=ast.parse((D/'summarize_same_job.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='progress_projection')
  scope={'importlib':importlib,'D':D};exec(compile(ast.Module(body=[node],type_ignores=[]),'<exact candidate function>','exec'),scope)
  with patch('importlib.util.spec_from_file_location',side_effect=ImportError('private path')):r=scope['progress_projection'](self.root,{})
  self.assertEqual(r['status'],'UNAVAILABLE');self.assertFalse(r['numerical_pass']);self.assertNotIn('private',json.dumps(r))
 def test_identity_mismatch(self):
  ident,fake,_,_=self.fixture();ident=dict(ident,run_id=2)
  with patch.dict(sys.modules,{'dut_evidence':fake}):r=m.project(self.root,ident)
  self.assertEqual(r['profiles'][0]['status'],'UNAVAILABLE')
 def test_overflow_rate_stays_finite_or_null(self):
  ident,fake,_,outer=self.fixture();outer.write_text(json.dumps({'elapsed_seconds':1e-320}))
  with patch.dict(sys.modules,{'dut_evidence':fake}):r=m.project(self.root,ident)
  self.assertIsNone(r['profiles'][0]['observed_cycles_per_outer_second']);json.dumps(r,allow_nan=False)
if __name__=='__main__':unittest.main()

