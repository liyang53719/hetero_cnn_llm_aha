"""Small synthetic fixtures and exact metadata hashes; never checkpoint execution."""
from pathlib import Path
import hashlib,json,os,tempfile,unittest
from unittest.mock import patch
import numpy as np
from parent_inputs import path_for_sha
from run_provider import load_reader,metadata_from_manifest
from emit_cold128_programs import common
HERE=Path(__file__).resolve().parent
class Projection(unittest.TestCase):
 def test_bundled_input_recipe_identity(self):
  recipe=path_for_sha('86ad51be3fac1e462676ab3ab22c5b806fa5bb17b9b126e81ff68263740e30eb');m=json.loads(recipe.read_text());g=path_for_sha(m['generator_sha256'])
  self.assertEqual(g,HERE/'input_generator.py');self.assertEqual(m['bytes'],524288);self.assertIn('experimental',m['origin'])
 def test_parent_map_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   q=Path(td);p=q/'bytes';p.write_bytes(b'not model data');sha=hashlib.sha256(p.read_bytes()).hexdigest();cfg=q/'map.json';cfg.write_text(json.dumps({'files':{sha:str(p)}}))
   with patch.dict(os.environ,{'BYTE_PROVIDER_INPUTS':str(cfg)}):
    self.assertEqual(path_for_sha(sha,p.stat().st_size),p.resolve())
    for digest,size in [('0'*64,None),('bad',None),(sha,True),(sha,1)]:
     with self.assertRaises(ValueError):path_for_sha(digest,size)
    p.write_bytes(b'tampered value')
    with self.assertRaises(ValueError):path_for_sha(sha)
   with patch.dict(os.environ,{},clear=True):
    with self.assertRaises(ValueError):path_for_sha(sha)
 def test_profile_metadata_exact(self):
  pins=json.loads((HERE/'PROGRAM_PINS.json').read_text())['profiles']
  for i in range(1,5):
   b,blocked=common(i);cb,db,m=b.finish();m['blocker']=blocked;m['complete_program_emitted']=blocked is None;m['sha256']={'commands':hashlib.sha256(cb).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()}
   values={'commands.bin':cb,'descriptors.bin':db,'manifest.json':(json.dumps(m,indent=2)+'\n').encode()}
   for n,v in values.items():self.assertEqual({'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()},pins[i]['files'][n])
   if i in [2,4]:self.assertEqual(m['qknorm_recipe'],'C2_Torch210CpuDefault256_EXISTING_REFERENCE_CONTRACT')
 def test_qwen2_expand_identity_boundaries(self):
  mod=load_reader('qwen2')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'toy';a=np.arange(15,dtype='<u2');p.write_bytes(a.tobytes());r=mod.Reader(p,60,True);expected=b''.join((int(x)<<16).to_bytes(4,'little') for x in a)
   try:
    for o in range(61):
     for n in range(61-o):self.assertEqual(r.read(o,n),expected[o:o+n])
    for o,n in [(True,1),(-1,0),(60,1)]:
     with self.assertRaises(ValueError):r.read(o,n)
   finally:r.close()
 def test_qwen08_transpose_concat_and_gather(self):
  mod=load_reader('qwen08')
  with tempfile.TemporaryDirectory() as td:
   q=Path(td);a=np.arange(12,dtype='<u2').reshape(3,4);b=(np.arange(8,dtype='<u2')+100).reshape(2,4);rows=[];mp={}
   for i,x in enumerate([a,b]):
    p=q/str(i);p.write_bytes(x.tobytes());h=hashlib.sha256(p.read_bytes()).hexdigest();mp[h]=str(p);rows.append(dict(path='ignored-private-parent-label',sha256=h,bytes=p.stat().st_size,dims=list(x.shape),dtype='BF16'))
   cfg=q/'map.json';cfg.write_text(json.dumps({'files':mp}))
   with patch.dict(os.environ,{'BYTE_PROVIDER_INPUTS':str(cfg)}):
    for kind,dims,sources,extra,expected in [('transpose',[4,3],rows[:1],{},a.T),('concat_transpose',[4,5],rows,{'segment_columns':[3,2]},np.concatenate([a.T,b.T],axis=1)),('gather_rows',[2,4],rows[:1],{'row_indices':[2,0]},a[[2,0]])]:
     bind=dict(kind=kind,dtype=5,size=int(np.prod(dims))*2,logical_dims=dims,sources=sources,**extra);r=mod.Reader(bind);raw=expected.astype('<u2').tobytes()
     for o in range(len(raw)+1):
      for n in range(min(7,len(raw)-o)+1):self.assertEqual(r.read(o,n),raw[o:o+n])
 def test_qwen35_sliced_expert_and_padding(self):
  mod=load_reader('qwen35')
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'toy';a=np.arange(48,dtype='<u2').reshape(2,6,4);p.write_bytes(a.tobytes());row=dict(path=str(p),dtype='BF16',shape=list(a.shape),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
   r=mod.array_reader(row,[2,4,3],(0,2,1),slice_axis=1,slice_start=3,slice_count=3);raw=a[:,3:,:].transpose(0,2,1).tobytes()
   for o in range(len(raw)+1):
    for n in range(min(9,len(raw)-o)+1):self.assertEqual(r.read(o,n),raw[o:o+n])
   a=np.arange(4,dtype='<u2');p.write_bytes(a.tobytes());row.update(shape=[1,4]);r=mod.array_reader(row,[4,32],pad_cols=32);expected=np.zeros((4,32),dtype='<u2');expected[:,0]=a;self.assertEqual(r.read(0,r.size),expected.tobytes())
 def test_metadata_parent_lookup_and_padding(self):
  with tempfile.TemporaryDirectory() as td:
   q=Path(td);files={};hashes={}
   for tag,n in [('commands',16),('descriptors',32)]:
    p=q/tag;p.write_bytes(bytes(range(n)));h=hashlib.sha256(p.read_bytes()).hexdigest();files[h]=str(p);hashes[tag]=h
   cfg=q/'map';cfg.write_text(json.dumps({'files':files}));m=dict(launch=dict(commandBase=64,commandLimit=128,commands=1,descriptorBase=128,descriptorLimit=192,descriptors=2),sha256=hashes)
   with patch.dict(os.environ,{'BYTE_PROVIDER_INPUTS':str(cfg)}):self.assertEqual(metadata_from_manifest(m),[('command_bytes',64,bytes(range(16))+bytes(48)),('descriptor_bytes',128,bytes(range(32))+bytes(32))])
if __name__=='__main__':unittest.main()
