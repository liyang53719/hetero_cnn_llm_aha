"""Synthetic source-only fixtures: no artifact execution or numerical evidence."""
import copy, hashlib, json, pathlib, tempfile, unittest
import executor_adaptation as a
P=pathlib.Path
class Fixture:
 def __init__(self,root):
  self.root=root/'repo'; self.root.mkdir(); self.old_path=root/'old.json'; self.current=self.root/a.CATALOG_PATH
  self.builder=dict(run_id=1,artifact_name='synthetic-build',source_commit='a'*40,launch_commit='b'*40,launch_manifest_path='ci_launch/synthetic.json',launch_manifest_blob_sha='c'*40)
  self.executor={'source_commit':'d'*40}; self.manifest='e'*64
  self.old={a.PREFIX+'numeric/runtime_abi_owned.py':b'old verifier\n','hardware/fixed.scala':b'unchanged hardware\n'}
  self.new={**self.old,a.PREFIX+'numeric/runtime_abi_owned.py':b'new verifier\n',a.ADAPTER_PATH:P(a.__file__).read_bytes()}
  self.review_path=root/'review.json';self.adaptation_path=root/'adaptation.json'; self.refresh()
 def write(self,p,d):
  p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,sort_keys=True));return a.pin(p)
 def catalog(self,files):
  return dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',original_source_commit='f'*40,files=[dict(path=n,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())for n,b in sorted(files.items())])
 def refresh(self):
  for n,b in self.new.items():
   p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
  self.old_pin=self.write(self.old_path,self.catalog(self.old));self.current_pin=self.write(self.current,self.catalog(self.new))
  changes=[dict(path=n,old_sha256=hashlib.sha256(self.old[n]).hexdigest()if n in self.old else None,new_sha256=hashlib.sha256(self.new[n]).hexdigest()if n in self.new else None)for n in sorted(self.old.keys()|self.new.keys())if self.old.get(n)!=self.new.get(n)]
  self.review=dict(schema='HOST_ONLY_EXECUTOR_ADAPTATION_REVIEW_V1',status='SOURCE_ONLY_GO_NOT_NUMERICAL',builder_source_commit=self.builder['source_commit'],executor_source_commit=self.executor['source_commit'],builder_source_pins_sha256=self.old_pin['sha256'],executor_source_pins_sha256=self.current_pin['sha256'],artifact_manifest_sha256=self.manifest,changes_sha256=a.changes_sha256(changes),numerical_pass=False)
  self.doc=dict(schema='HOST_ONLY_EXECUTOR_ADAPTATION_V1',scope='FROZEN_BUILDER_BYTES_HOST_EXECUTOR_ONLY',builder_identity=self.builder,executor_source_commit=self.executor['source_commit'],artifact_manifest_sha256=self.manifest,builder_source_pins=self.old_pin,executor_source_pins=self.current_pin,review=self.write(self.review_path,self.review),changes=changes,numerical_pass=False)
  self.save()
 def save(self):self.adaptation_pin=self.write(self.adaptation_path,self.doc)
 def verify(self):return a.verify(self.adaptation_pin,self.builder,self.executor,self.current_pin,self.root)
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.f=Fixture(P(self.tmp.name))
 def reject(self):
  with self.assertRaises((ValueError,KeyError)):self.f.verify()
 def test_positive_discloses_distinct_sources(self):
  r=self.f.verify();self.assertEqual(r['builder_source_commit'],'a'*40);self.assertEqual(r['executor_source_commit'],'d'*40);self.assertIs(r['numerical_pass'],False)
 def test_external_pin_tamper(self):self.f.adaptation_pin['sha256']='0'*64;self.reject()
 def test_actual_source_tamper(self):(self.f.root/'hardware/fixed.scala').write_bytes(b'tamper');self.reject()
 def test_hardware_change_even_reviewed_rejected(self):self.f.new['hardware/fixed.scala']=b'changed';self.f.refresh();self.reject()
 def test_pipeline_producer_change_rejected(self):self.f.new['pipeline/driver_dependency_proof.py']=b'changed';self.f.refresh();self.reject()
 def test_reference_add_rejected(self):self.f.new[a.PREFIX+'reference_job.py']=b'changed';self.f.refresh();self.reject()
 def test_missing_diff(self):self.f.doc['changes'].pop();self.f.save();self.reject()
 def test_extra_diff(self):self.f.doc['changes'].append(copy.deepcopy(self.f.doc['changes'][0]));self.f.save();self.reject()
 def test_review_drift(self):self.f.review['changes_sha256']='0'*64;self.f.doc['review']=self.f.write(self.f.review_path,self.f.review);self.f.save();self.reject()
 def test_review_numerical_pass(self):self.f.review['numerical_pass']=True;self.f.doc['review']=self.f.write(self.f.review_path,self.f.review);self.f.save();self.reject()
 def test_extra_doc_field(self):self.f.doc['ignored']='no';self.f.save();self.reject()
 def test_same_source_not_adaptation(self):self.f.executor['source_commit']='a'*40;self.f.refresh();self.reject()
 def test_builder_wrong_identity(self):self.f.builder=copy.deepcopy(self.f.builder);self.f.builder['run_id']=2;self.reject()
 def test_executor_wrong_identity(self):self.f.executor={'source_commit':'0'*40};self.reject()
 def test_deletion(self):del self.f.new[a.PREFIX+'numeric/runtime_abi_owned.py'];self.f.refresh();self.reject()
 def test_symlink_current_source(self):
  p=self.f.root/'hardware/fixed.scala';p.unlink();p.symlink_to(self.f.old_path);self.reject()
 def test_wrong_checker_bytes(self):self.f.new[a.ADAPTER_PATH]=b'pass\n';self.f.refresh();self.reject()
 def test_stale_current_catalog_pin(self):self.f.current_pin=dict(self.f.current_pin,sha256='0'*64);self.reject()
 def test_catalog_duplicate_rejected(self):
  c=self.f.catalog(self.f.new);c['files'].append(c['files'][0]);self.f.current_pin=self.f.write(self.f.current,c);self.f.doc['executor_source_pins']=self.f.current_pin;self.f.save();self.reject()
 def test_catalog_self_row_rejected(self):
  c=self.f.catalog(self.f.new);c['files'].append(dict(path=a.CATALOG_PATH,bytes=1,sha256='0'*64));self.f.current_pin=self.f.write(self.f.current,c);self.f.doc['executor_source_pins']=self.f.current_pin;self.f.save();self.reject()
 def test_noncanonical_relative(self):
  for path in ['../escape','a//b','a/./b','/absolute','x/','']:
   with self.subTest(path=path),self.assertRaises(ValueError):a.relative(path)
 def test_repo_symlink_rejected(self):
  alias=P(self.tmp.name)/'alias';alias.symlink_to(self.f.root)
  with self.assertRaises(ValueError):a.verify(self.f.adaptation_pin,self.f.builder,self.f.executor,self.f.current_pin,alias)
if __name__=='__main__':unittest.main()
