"""Repack two exact parent RoPE coefficient inputs; no block arithmetic."""
import argparse,hashlib,json
from pathlib import Path
from parent_inputs import path_for_sha
def build():
 c=json.loads(path_for_sha('788c72cb65c32c872fd19c0ee8a1f6b8dcc50ae52a985ab5fa38e6ed53eeb847').read_text());inputs=[]
 for r in c['source_coefficients']:
  data=path_for_sha(r['sha256'],16384).read_bytes()
  for t in range(128):
   if data[t*128:t*128+64]!=data[t*128+64:t*128+128]:raise ValueError('rotary duplicated-half mismatch')
  inputs.append(data)
 if len(inputs)!=2:raise ValueError('exact cos/sin inputs required')
 out=b''.join(inputs[0][t*128:t*128+64]+inputs[1][t*128:t*128+64] for t in range(128))
 if hashlib.sha256(out).hexdigest()!=c['sha256']:raise ValueError('coefficient output identity')
 return out
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 with a.out.open('xb') as f:f.write(build())
