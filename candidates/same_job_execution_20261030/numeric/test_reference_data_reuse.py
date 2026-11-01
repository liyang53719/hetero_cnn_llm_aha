import errno,hashlib,importlib.util,json,os,resource,tempfile,unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).parent
SOURCE=HERE/'reference_data_reuse.py'if (HERE/'reference_data_reuse.py').exists()else HERE/'source/reference_data_reuse.py'
spec=importlib.util.spec_from_file_location('core',SOURCE);core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
@lru_cache(None)
def zero_hash(size):
 h=hashlib.sha256();chunk=bytes(1<<20)
 while size:n=min(size,len(chunk));h.update(chunk[:n]);size-=n
 return h.hexdigest()
def fixture(root):
 root=Path(root);repo=root/'repo';repo.mkdir();refs={};files={}
 def save(p,d):p.write_text(json.dumps(d));return core.pin(p)
 for i in range(5):
  r=root/str(i);r.mkdir();(r/'input_only').mkdir();ts={};fs={}
  for j in range(core.COUNTS[i]):
   size=1 if j else core.BYTES[i]-(core.COUNTS[i]-1);rel='input_only/t'+str(j)+'.bin';p=r/rel
   with p.open('wb')as f:f.truncate(size)
   row=dict(path=str(p),bytes=size,sha256=zero_hash(size));fs[rel]=row;ts[str(j)]=dict(file=rel,bytes=size,sha256=row['sha256'])
  refs[str(i)]=save(r/'RESULT.json',dict(profile={'profile':i},complete_block_tokens=128,hardware_executed=False,exact_baseline_observer_output_equal=True,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',tensor_records=ts));files[str(i)]=fs
 context=dict(repo=str(repo),artifact_manifest=save(root/'artifact.json',{}),retained_materials=save(root/'retained.json',{'references':{k:{'result':v}for k,v in refs.items()}}))
 d=dict(schema='READONLY_REFERENCE_REUSE_V1',scope=core.SCOPE,execution_mode=core.MODE,context=context,references=refs,tensor_files=files,tensor_bytes=sum(core.BYTES),tree_cap=core.TREE,numerical_pass=False)
 p=root/'reuse.json';save(p,d);out=root/'out';out.mkdir()
 return d,core.pin(p),context,out,lambda:save(p,d)
class Test(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.d,self.pin,self.context,self.out,self.save=fixture(self.root)
 def reject(self):
  with self.assertRaises((ValueError,OSError)):core.verify_metadata(self.save(),self.context)
 def test_metadata_five(self):
  v=core.verify_metadata(self.pin,self.context);self.assertEqual(v['tensor_bytes'],44262400);self.assertEqual(len(v['roots']),5)
 def test_whole_p0_link_and_verify(self):
  ref=self.d['references']['0'];target=core.link_reference(ref,self.out,0,self.pin,self.context);self.assertEqual(core.verify_materialized(ref,self.out,0,self.pin,self.context),target)
  source=Path(next(iter(self.d['tensor_files']['0'].values()))['path']);self.assertEqual(source.stat().st_ino,(target/'input_only/t0.bin').stat().st_ino)
  self.assertNotEqual(Path(ref['path']).stat().st_ino,(target/'RESULT.json').stat().st_ino)
 def test_materialized_changed_shared_byte(self):
  ref=self.d['references']['0'];target=core.link_reference(ref,self.out,0,self.pin,self.context)
  (target/'input_only/t1.bin').write_bytes(b'x')
  with self.assertRaises(ValueError):core.verify_materialized(ref,self.out,0,self.pin,self.context)
 def test_materialized_equal_bytes_wrong_inode(self):
  ref=self.d['references']['0'];target=core.link_reference(ref,self.out,0,self.pin,self.context);p=target/'input_only/t1.bin';p.unlink();p.write_bytes(b'\0')
  with self.assertRaises(ValueError):core.verify_materialized(ref,self.out,0,self.pin,self.context)
 def test_materialized_extra_file(self):
  ref=self.d['references']['0'];target=core.link_reference(ref,self.out,0,self.pin,self.context);(target/'extra').write_text('x')
  with self.assertRaises(ValueError):core.verify_materialized(ref,self.out,0,self.pin,self.context)
 def test_foreign_reference(self):
  with self.assertRaises(ValueError):core.link_reference(self.d['references']['1'],self.out,0,self.pin,self.context)
 def test_wrong_mode(self):self.d['execution_mode']='FULL';self.reject()
 def test_changed_context(self):self.d['context']=dict(self.context,repo='/wrong');self.reject()
 def test_wrong_byte_budget(self):self.d['tensor_bytes']-=1;self.reject()
 def test_tensor_extra(self):self.d['tensor_files']['0']['foreign']=next(iter(self.d['tensor_files']['0'].values()));self.reject()
 def test_tensor_symlink(self):
  p=Path(self.d['tensor_files']['0']['input_only/t1.bin']['path']);p.unlink();p.symlink_to(self.root/'0/input_only/t2.bin');self.reject()
 def test_link_exdev_no_fallback(self):
  p=self.root/'tiny';p.write_bytes(b'ab');dest=self.out/'dest'
  with patch.object(core.os,'link',side_effect=OSError(errno.EXDEV,'cross device')):
   with self.assertRaises(OSError):core.link_one(core.pin(p),dest)
  self.assertFalse(dest.exists())
 def test_link_existing_rejected(self):
  p=self.root/'tiny';p.write_bytes(b'ab');q=self.out/'dest';q.write_bytes(b'ab')
  with self.assertRaises(ValueError):core.link_one(core.pin(p),q)
 def test_changed_byte_rejected(self):
  p=self.root/'tiny';p.write_bytes(b'ab');row=core.pin(p);p.write_bytes(b'ac')
  with self.assertRaises(ValueError):core.link_one(row,self.out/'dest')
 def test_destination_symlink_rejected(self):
  p=self.root/'tiny';p.write_bytes(b'ab');dest=self.out/'dest';dest.symlink_to(p)
  with self.assertRaises(ValueError):core.link_one(core.pin(p),dest)
if __name__=='__main__':
 resource.setrlimit(resource.RLIMIT_AS,(256<<20,)*2);resource.setrlimit(resource.RLIMIT_CPU,(15,)*2);unittest.main(verbosity=2)
