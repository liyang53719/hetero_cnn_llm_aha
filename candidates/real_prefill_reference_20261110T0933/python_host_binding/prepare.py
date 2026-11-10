"""Bind saved independent candidate outputs, never create DUT intermediate inputs."""
import pathlib,json,hashlib,shutil
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
P=ROOT/'round_20261110T0833/numpy_fma_candidate'
MAPPING={'n0':'norm0','qraw':'q0','qr':'qb','q':'q','kraw':'k0','kr':'kb','k':'k','vraw':'v0','v':'v','cache_k':'kv.0','cache_v':'kv.1','att':'att','o':'proj','r':'res','n1':'norm1','gate':'gate','up':'up','act':'act','down':'down','y':'y'}
def fnv(data):
 h=1469598103934665603
 for b in data:h=((h^b)*1099511628211)&((1<<64)-1)
 return h

def main():
 report=json.loads((P/'full_m128/RESULT.json').read_text())
 if report['status']!='CANDIDATE_REFERENCE_FULL21_EXECUTED':raise ValueError('reference incomplete')
 pins={}
 for r in report['progress']:
  hs=r['sha256'];hs=[hs] if isinstance(hs,str) else hs
  for i,h in enumerate(hs):pins[r['buffer']+('.'+str(i) if len(hs)>1 else '')]=h
 records=[]; lines=[];out=HERE/'local_reference';out.mkdir(exist_ok=True)
 for name,buf in MAPPING.items():
  choices=[p for p in [P/(buf+'.local.f32'),P/'resume_m128'/(buf+'.local.f32'),P/'full_m128'/(buf+'.local.f32')] if p.exists()]
  if len(choices)!=1:raise ValueError('ambiguous/missing '+buf)
  p=choices[0];b=p.read_bytes();sha=hashlib.sha256(b).hexdigest()
  if sha!=pins[buf]:raise ValueError('reference hash '+buf)
  shutil.copyfile(p,out/(name+'.f32le'));h=fnv(b)
  records.append(dict(name=name,buffer=buf,bytes=len(b),sha256=sha,fnv64=h))
  lines.append('{"%s",%dULL,%dULL},'%(name,len(b),h))
 trig=json.loads((P/'TRIG_MANIFEST.json').read_text());bs=[]
 for name in ['cos','sin']:
  p=P/(name+'.local.f32');b=p.read_bytes()
  if hashlib.sha256(b).hexdigest()!=trig['sha256'][str(p)]:raise ValueError('trig hash')
  bs.append(b)
 b=b''.join(bs);(out/'rope.f32le').write_bytes(b)
 records.append(dict(name='rope',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),fnv64=fnv(b)))
 (HERE/'reference_pins.h').write_text('#pragma once\nstruct ReferencePin {const char*name; unsigned long long bytes,hash;};\nstatic const ReferencePin REFERENCE_PINS[]={\n'+ '\n'.join(lines)+'\n};\nstatic const ReferencePin ROPE_PIN={"rope",%dULL,%dULL};\n'%(len(b),fnv(b)))
 (HERE/'BINDING.json').write_text(json.dumps(dict(classification='CANDIDATE_REFERENCE',matrix_flags='NOT_QUALIFIED',hardware_pass=0,records=records),indent=2))
if __name__=='__main__':main()
