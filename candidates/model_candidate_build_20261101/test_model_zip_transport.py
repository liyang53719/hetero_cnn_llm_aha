"""Transport-only synthetic tests. Payload semantic verifier mocked; no ELF execution."""
import json,pathlib,stat,tempfile,unittest,zipfile
from unittest.mock import patch
import receive_model_zip as m
class Transport(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.d=pathlib.Path(self.t.name)
  self.i=dict(run_id=1,artifact_name='model-1',source_commit='a'*40,launch_commit='b'*40)
 def archive(self,mode='normal'):
  z=self.d/'payload.zip'
  with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_DEFLATED)as f:
   for n in sorted(set(m.NAMES.values())|{'frozen_artifact.json'}):
    q=zipfile.ZipInfo('../'+n if mode=='traversal'else n)
    q.create_system=3;q.external_attr=((stat.S_IFLNK if mode=='symlink'else stat.S_IFREG)|0o600)<<16
    f.writestr(q,b'x')
   if mode=='extra':f.writestr('local.npz',b'x')
  p=self.d/'api.json';r=dict(schema='AUTHENTICATED_GITHUB_ARTIFACT_RECEIPT_V1',artifact_id=1,name='model-1',run_id=1,source_commit='a'*40,launch_commit='b'*40,expired=False,api_size_in_bytes=123,downloaded_zip_bytes=z.stat().st_size,archive_sha256=m.sha(z),api_verified=True)
  p.write_text(json.dumps(r));return z,p
 def call(self,z,p):return m.receive(z,m.sha(z),p,m.sha(p),self.d/'out',self.i,'f'*64)
 def test_transport_only_exact_seven_nonexecuting(self):
  z,p=self.archive()
  with patch.object(m,'verify',return_value={'scope':'SYNTHETIC_ONLY'})as v:
   r=self.call(z,p);v.assert_called_once();self.assertFalse(r['executable_permission_granted'])
  self.assertEqual(len(list((self.d/'out').iterdir())),7)
  self.assertTrue(all(stat.S_IMODE(x.stat().st_mode)==0o600 for x in (self.d/'out').iterdir()))
 def test_bad_names_and_types_before_semantics(self):
  for mode in ('traversal','symlink','extra'):
   z,p=self.archive(mode)
   with patch.object(m,'verify')as v:
    with self.assertRaises(ValueError):self.call(z,p)
    v.assert_not_called()
   self.assertFalse((self.d/'out').exists())
 def test_actual_api_identity_and_download_size(self):
  z,p=self.archive();original=json.loads(p.read_text())
  for k,val in [('run_id',2),('expired',True),('api_verified',False),('downloaded_zip_bytes',1),('archive_sha256','0'*64)]:
   p.write_text(json.dumps(dict(original,**{k:val})))
   with self.assertRaises(ValueError):self.call(z,p)
   self.assertFalse((self.d/'out').exists())
 def test_original_zip_digest_required(self):
  z,p=self.archive()
  with self.assertRaises(ValueError):m.receive(z,'0'*64,p,m.sha(p),self.d/'out',self.i,'f'*64)
 def test_semantic_failure_never_grants_execution(self):
  z,p=self.archive()
  with patch.object(m,'verify',side_effect=ValueError('unreviewed candidate evidence')):
   with self.assertRaises(ValueError):self.call(z,p)
  self.assertTrue(all(stat.S_IMODE(x.stat().st_mode)==0o600 for x in (self.d/'out').iterdir()))
if __name__=='__main__':unittest.main()
