"""Exact read-only source layout mapping. No block arithmetic or reference outputs."""
from pathlib import Path
import json,hashlib,math
import numpy as np
from parent_inputs import path_for_sha
# Exact parent data supplied by SHA256; no archived path dependency.
def require(x,msg):
 if not x:raise ValueError(msg)
def verify(p):
 q=path_for_sha(p['sha256'],p['bytes']);require(q.is_file() and q.stat().st_size==p['bytes'],'source size/path drift')
 with q.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 require(h==p['sha256'],'source hash drift '+p['path']);return q
class Reader:
 def __init__(self,b):
  self.b=b;self.size=b['size'];self.word=2 if b['dtype']==5 else 4
  require(self.size==math.prod(b['logical_dims'])*self.word,'logical size drift')
  self.arr=[]
  for s in b['sources']:
   require(math.prod(s['dims'])*self.word==s['bytes'],'source dimension drift')
   p=verify(s);require(s['dtype']==('BF16' if self.word==2 else 'F32'),'dtype drift')
   self.arr.append(np.memmap(p,mode='r',dtype='<u2' if self.word==2 else '<u4',shape=tuple(s['dims'])).reshape(-1))
  if b['kind']=='trig_halves':
   for a in self.arr:
    aa=a.reshape(128,64);require(np.array_equal(aa[:,:32],aa[:,32:]),'trig halves differ')
  for k in ('fixture_pin','capture_manifest_pin','recipe_pin'):
   if k in b:verify(b[k])
 def read(self,offset,length):
  require(type(offset)is int and type(length)is int and 0<=offset<=self.size and 0<=length<=self.size-offset,'read boundary')
  if length==0:return b''
  if self.b['kind']=='zero':return bytes(length)
  w=self.word;start=offset//w;end=(offset+length+w-1)//w; ix=np.arange(start,end,dtype=np.int64);kind=self.b['kind']
  if kind=='flat':v=self.arr[0][ix]
  elif kind=='transpose':
   K,N=self.b['logical_dims'];v=self.arr[0][(ix%N)*K+ix//N]
  elif kind=='concat_transpose':
   K,N=self.b['logical_dims'];r=ix//N;c=ix%N;cut=self.b['segment_columns'][0];v=np.empty(len(ix),dtype='<u2');sel=c<cut
   v[sel]=self.arr[0][c[sel]*K+r[sel]];v[~sel]=self.arr[1][(c[~sel]-cut)*K+r[~sel]]
  elif kind=='gather_rows':
   cols=self.b['logical_dims'][-1];ids=np.asarray(self.b['row_indices'],dtype=np.int64);require(len(ids)==self.b['logical_dims'][0] and np.all((ids>=0)&(ids<self.b['sources'][0]['dims'][0])),'input indices')
   v=self.arr[0][ids[ix//cols]*cols+ix%cols]
  elif kind=='trig_halves':
   row=ix//64;c=ix%64;v=np.empty(len(ix),dtype='<u2');sel=c<32
   v[sel]=self.arr[0][row[sel]*64+c[sel]];v[~sel]=self.arr[1][row[~sel]*64+c[~sel]-32]
  else:raise ValueError('unknown mapping')
  raw=v.astype('<u2' if w==2 else '<u4',copy=False).tobytes();return raw[offset-start*w:offset-start*w+length]
BINDINGS_SHA256='77f4910ae24f7096d10dcc10f4fc96568b7bb1032b1975564449568a02b4eeaa'
def load_bindings(raw):
 require(hashlib.sha256(raw).hexdigest()==BINDINGS_SHA256,'binding document drift')
 return json.loads(raw)
def build_readers(manifest_path):
 mpath=Path(manifest_path);m=json.loads(mpath.read_text());p=str(m['launch']['profileId']);allb=load_bindings(path_for_sha(BINDINGS_SHA256).read_bytes());b=allb['profiles'][p]
 require(hashlib.sha256(mpath.read_bytes()).hexdigest()==b['manifest']['sha256'],'program manifest drift');verify(b['weight_manifest']);verify(b['weight_pin'])
 require(set(b['bindings'])=={k for k,t in m['tensors'].items() if t['readonly']},'RO inventory')
 readers={k:Reader(v) for k,v in b['bindings'].items()}
 for k,v in b['bindings'].items():require(v['size']==m['tensors'][k]['bytes'] and v['logical_dims']==m['tensors'][k]['dims'] and v['dtype']==m['tensors'][k]['dtype'],'tensor contract drift')
 return readers,dict(profile=int(p),status='SOURCE_BYTES_VERIFIED_NOT_DUT',bindings=b['bindings'],numeric_pass=False)
