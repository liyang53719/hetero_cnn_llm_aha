"""Bounded extraction of the exact historical Core fixture; never compilation.
Requires the separately retained original HIGH. No download or IR publication.
"""
import argparse,hashlib,pathlib
P=pathlib.Path
EXPECTED_SHA256='dc6a5e1623bf5001f0c6d38fea5dd4287b23fe7460a3dc113e4962d316817bc8'
EXPECTED_BYTES=5839431
MAX_INPUT=384<<20

def extract(path):
 p=P(path)
 if not p.is_file() or any(q.is_symlink() for q in (p,*p.parents)) or not 0<p.stat().st_size<=MAX_INPUT:raise ValueError('bounded regular original HIGH required')
 out=bytearray(b'circuit Qwen2ContinuousBlock :\n');inside=False;matches=0;total=0
 with p.open('rb') as f:
  while True:
   line=f.readline((1<<20)+1)
   if not line:break
   total+=len(line)
   if len(line)>1<<20 or total>MAX_INPUT:raise ValueError('HIGH input bound')
   if line.startswith(b'  module Qwen2ContinuousBlock :'):
    matches+=1;inside=True
   elif inside and line.startswith((b'  module ',b'  extmodule ')):inside=False
   if inside:
    out.extend(line)
    if len(out)>8<<20:raise ValueError('Core extraction bound')
 if matches!=1 or len(out)!=EXPECTED_BYTES or hashlib.sha256(out).hexdigest()!=EXPECTED_SHA256:raise ValueError('not the exact historical Core fixture')
 return bytes(out)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();data=extract(a.input);p=P(a.output)
 if any(q.is_symlink() for q in (p,*p.parents)):raise ValueError('no output symlink')
 with p.open('xb') as f:f.write(data)
 print('EXACT_HISTORICAL_CORE_EXTRACTED_NO_EXECUTION')
if __name__=='__main__':main()
