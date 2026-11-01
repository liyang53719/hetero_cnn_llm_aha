import unittest,tempfile,resource,sys,hashlib,json
from pathlib import Path
from test_support_p0_reuse import build_fixture,core
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.f=build_fixture(self.t.name)
 def test_real_checker_metadata_only(self):
  v=core.verify_metadata(self.f['pin'],self.f['context']);self.assertEqual(v['roots'],[str(self.f['root']/'oldprovider'),str(self.f['root']/'evidence')]);self.assertEqual(len(v['inputs']),14)
 def reject(self):
  pin=self.f['save']()
  with self.assertRaises(ValueError):core.verify_metadata(pin,self.f['context'])
 def test_wrong_context(self):
  b=dict(self.f['context'],repo='/wrong')
  with self.assertRaises(ValueError):core.verify_metadata(self.f['pin'],b)
 def test_extra_output_input(self):self.f['document']['inputs']['dut_output']=self.f['document']['inputs']['x'];self.reject()
 def test_changed_input_size(self):Path(self.f['document']['inputs']['x']['path']).write_bytes(b'x');self.reject()
 def test_symlink_input(self):
  p=Path(self.f['document']['inputs']['x']['path']);p.unlink();p.symlink_to(self.f['document']['rope']['path']);self.reject()
 def test_program_substitution(self):self.f['document']['program']['commands']=self.f['document']['program']['descriptors'];self.reject()
 def test_not_dut_scope(self):self.f['document']['numerical_pass']=True;self.reject()
 def test_source_hash(self):self.f['document']['source_contract']['rebuild']['sha256']='1'*64;self.reject()
 def test_closed_receipt_hash(self):self.f['document']['closed_stage']['receipt']['sha256']='1'*64;self.reject()
 def test_origin_never_read(self):
  for row in self.f['document']['evidence_origins'].values():Path(row['path']).unlink()
  core.verify_metadata(self.f['pin'],self.f['context'])
 def test_copy_hash_rejects(self):
  Path(self.f['document']['prior_controller_binding']['path']).write_bytes(b'{}');self.reject()
 def test_origin_pin_mismatch(self):
  self.f['document']['evidence_origins']['prior']['sha256']='1'*64;self.reject()
 def test_evidence_extra_file(self):
  (Path(self.f['document']['evidence_root'])/'extra').write_text('x');self.reject()
 def test_evidence_symlink(self):
  p=Path(self.f['document']['closed_stage']['phase']['path']);p.unlink();p.symlink_to(self.f['document']['evidence_origins']['phase']['path']);self.reject()
 def rewrite_evidence(self,key,mutate):
  d=self.f['document'];row=d['closed_stage'][key];p=Path(row['path']);obj=json.loads(p.read_text());mutate(obj);p.write_text(json.dumps(obj));new=core.makepin(p);d['closed_stage'][key]=new;d['evidence_origins'][key].update(bytes=new['bytes'],sha256=new['sha256'])
  if key=='phase':self.rewrite_evidence('receipt',lambda x:x['argv'].__setitem__(-1,new['sha256']))
 def test_reader_not_joined(self):
  self.rewrite_evidence('receipt',lambda x:x['reader_join_barrier'].update(complete=False));self.reject()
 def test_owner_exit_wrong(self):
  self.rewrite_evidence('receipt',lambda x:x['cleanup_proof'].update(direct_exit_code=1));self.reject()
 def test_duplicate_provider_flag(self):
  self.rewrite_evidence('phase',lambda x:x['argv'].extend(['--output',self.f['document']['provider_root']]));self.reject()
 def test_independent_transpose_and_expansion(self):
  r=self.f['root'];a=r/'a';b=r/'b';a.write_bytes(bytes([1,0,2,0,3,0,4,0,5,0,6,0]));b.write_bytes(bytes([1,0,4,0,2,0,5,0,3,0,6,0]));core.compare_mapping(a,b,[2,3],True)
  b.write_bytes(bytes([0,0,1,0,0,0,2,0,0,0,3,0,0,0,4,0,0,0,5,0,0,0,6,0]));core.compare_mapping(a,b,[6],False)
  b.write_bytes(b'\0'*24)
  with self.assertRaises(ValueError):core.compare_mapping(a,b,[6],False)
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_AS,(2<<30,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,)*2);unittest.main(verbosity=2)
