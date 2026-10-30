#!/usr/bin/env python3
"""Derive reference imports/native hashes from pinned archives, never imports."""
import argparse, hashlib, json, tarfile, zipfile
from pathlib import Path, PurePosixPath
TORCH_SHA='ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d'
FRAMEWORKS={
 '4.40.1':('qwen2','f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad'),
 '14e738b5d0cc69aa27a95dde272aea41fde44f2f':('qwen3_5','aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18'),
 '42ca97014c85d71a88ad60d55f08cb9fb4d26e2c':('qwen3_5_moe','ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30')}
def need(ok,msg):
 if not ok: raise ValueError(msg)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def stream_sha(f):
 h=hashlib.sha256()
 for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def safe(n):
 p=PurePosixPath(n);need(not p.is_absolute() and '..' not in p.parts,'unsafe archive member');return n
class Artifact:
 def __init__(self,path):
  self.zip=zipfile.is_zipfile(path)
  self.obj=zipfile.ZipFile(path) if self.zip else tarfile.open(path,'r:*')
  self.names=self.obj.namelist() if self.zip else self.obj.getnames()
  need(len(self.names)==len(set(self.names)),'duplicate archive members')
  for n in self.names:safe(n)
 def hash(self,n):
  need(n in self.names,'missing archive member '+n)
  if self.zip:
   info=self.obj.getinfo(n);need(not info.is_dir() and ((info.external_attr>>16)&0o170000)!=0o120000,'linked archive member')
   with self.obj.open(n) as f:return stream_sha(f)
  info=self.obj.getmember(n);need(info.isfile(),'nonregular archive member')
  with self.obj.extractfile(info) as f:return stream_sha(f)
 def close(self):self.obj.close()
def derive(revision,framework,framework_sha,torch,out):
 need(revision in FRAMEWORKS,'unsupported revision');need(sha(framework)==framework_sha,'framework archive hash mismatch');need(sha(torch)==TORCH_SHA,'official Torch wheel hash mismatch')
 if revision=='4.40.1':need(framework_sha=='9d5ee0c8142a60501faf9e49a0b42f8e9cb8611823bce4f195a9325a6816337e','Qwen2 wheel pin')
 f=Artifact(framework);t=Artifact(torch)
 try:
  model,model_sha=FRAMEWORKS[revision];suffix='transformers/models/'+model+'/modeling_'+model+'.py'
  matches=[n for n in f.names if n.endswith(suffix)];need(len(matches)==1,'unique pinned model source')
  root=matches[0][:-len(suffix)];need(f.hash(matches[0])==model_sha,'retained official modeling source mismatch')
  if revision!='4.40.1':need(revision in root,'archive root does not identify exact commit')
  modules={'transformers.models.'+model+'.modeling_'+model:suffix,'transformers.models.'+model+'.configuration_'+model:'transformers/models/'+model+'/configuration_'+model+'.py','transformers.activations':'transformers/activations.py','transformers.cache_utils':'transformers/cache_utils.py'}
  if revision!='4.40.1':modules['transformers.masking_utils']='transformers/masking_utils.py'
  hashes={name:f.hash(root+rel) for name,rel in modules.items()}
  hashes['torch.nn.functional']=t.hash('torch/nn/functional.py')
  natives=sorted(n for n in t.names if n.startswith('torch/') and (n.endswith('.so') or '.so.' in n) and not n.endswith('/'))
  c=[n for n in natives if n.startswith('torch/_C.')];need(len(c)==1,'unique Torch native loader');hashes['torch._C']=t.hash(c[0])
  native={n:t.hash(n) for n in natives}
  result={'framework_revision':revision,'module_sha256':hashes,'module_relative_paths':{**modules,'torch.nn.functional':'torch/nn/functional.py','torch._C':c[0]},'native_file_sha256':native,'artifact_sha256':{'framework':framework_sha,'torch':TORCH_SHA},'identity':'ARCHIVE_DERIVED_NOT_LIVE_IMPORT_CALIBRATED','limits':'Imported helper set is not complete transitive framework source closure. Native Torch shared libraries are separately checked before and after execution.'}
  with Path(out).open('x') as w:json.dump(result,w,indent=2);w.write('\n')
  return result
 finally:f.close();t.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--revision',required=True);p.add_argument('--framework',type=Path,required=True);p.add_argument('--framework-sha256',required=True);p.add_argument('--torch-wheel',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=derive(a.revision,a.framework,a.framework_sha256,a.torch_wheel,a.output);print(json.dumps({'modules':len(r['module_sha256']),'native_files':len(r['native_file_sha256']),'output_sha256':sha(a.output)},indent=2))
if __name__=='__main__':main()
