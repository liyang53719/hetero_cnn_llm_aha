import sys,pathlib,json,hashlib,time,random
import resource
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
import numpy as np
from audit import fma
root=pathlib.Path(__file__).resolve().parents[2];out=pathlib.Path(__file__).parent
sys.path.insert(0,str(root/'round_20261110T0833/legacy_python'))
sys.path.insert(0,str(root/'round_20261110T0833/numpy_fma_candidate'))
from legacy_reference import fraction
from rational_oracle import round_fraction
from candidate import fma_bf16_words,bf16_words
from fractions import Fraction

def frac_oracle(a,b,c):
 x=fraction(a)*fraction(b)+fraction(c);w=round_fraction(x)
 if not x and ((a^b)>>31) and (not (a&0x7fffffff) or not(b&0x7fffffff)) and c==0x80000000:w=0x80000000
 if w&0x7f800000==0x7f800000:return w,5
 inx=fraction(w)!=x
 return w,int(inx)|(2 if inx and abs(fraction(w))<Fraction(1,1<<126) else 0)

start=time.monotonic();rng=random.Random(317);cases=[(0x00800000,0x3f000000,0),(0x00010000,0x3f000000,0),(0x00010000,0x00010000,0),(0x7f7f0000,0x40000000,0),(0x80000000,0x3f800000,0x80000000),(0x3f800000,0x3f800000,0xbf800000)]
for _ in range(20000):
 a=rng.randrange(65536)<<16;b=rng.randrange(65536)<<16;c=rng.randrange(1<<32)
 if all(x&0x7f800000!=0x7f800000 for x in (a,b,c)):cases.append((a,b,c))
for a,b,c in cases:
 got=fma(a,b,c);expected=frac_oracle(a,b,c)
 if got!=expected:raise AssertionError((hex(a),hex(b),hex(c),got,expected))
 cv=int(fma_bf16_words(np.uint32(a),np.uint32(b),np.uint32(c)))
 if cv!=got[0]:raise AssertionError(('candidate double round mismatch',a,b,c,cv,got))
# Each full-K path uses exact integer oracle for accumulator and compares every
# step to FP64 candidate, then final word against stored full-M128 stage.
p=root/'round_20261110T0833/numpy_fma_candidate';payload=root/'round_20261110T0733/qwen2_host_payload'
result=json.loads((p/'full_m128/RESULT.json').read_text());prior=json.loads((p/'REAL_Q_RESULT.json').read_text());bindings=json.loads((payload/'REAL_INPUT_BINDING.json').read_text())
pins={payload/(x['name']+'.f32le'):x['sha256'] for x in bindings['records']}
pins[p/'norm0.local.f32']=prior['norm_sha256'];pins[p/'q0.local.f32']=prior['q_sha256']
for x in result['progress']:
 if x.get('stage') and x['status']=='CANDIDATE_REFERENCE_STAGE_ONLY' and len(x['sha256'])==1:pins[p/'full_m128'/(x['buffer']+'.local.f32')]=x['sha256'][0]
old=json.loads((p/'resume_m128/RESULT.json').read_text())
for x in old['progress']:
 f=p/'resume_m128'/(x['buffer']+'.local.f32')
 if f.exists():pins[f]=x['sha256']
verified={}
def load(f,shape):
 expected=pins[f];actual=hashlib.sha256(f.read_bytes()).hexdigest()
 if actual!=expected:raise AssertionError('hash '+str(f))
 verified[str(f.relative_to(root))]=actual
 return np.memmap(f,dtype='<u4',mode='r',shape=shape)
stages=[('q','norm0','wq','q0',1536,1536),('k','norm0','wk','k0',1536,256),('v','norm0','wv','v0',1536,256),('out','att','wo','proj',1536,1536),('gate','norm1','wg','gate',1536,8960),('up','norm1','wu','up',1536,8960),('down','act','wd','down',8960,1536)]
def locate(n):
 for parent in (p,p/'full_m128',p/'resume_m128'):
  f=parent/(n+'.local.f32')
  if f.exists():return f
 raise FileNotFoundError(n)
reports=[]
for name,an,wn,on,k,n in stages:
 a=load(locate(an),(128,k));w=load(payload/(wn+'.f32le'),(k,n));y=load(locate(on),(128,n));counts={};steps=0
 coords=sorted(set([(r,c) for r in (0,63,127) for c in (0,n//2,n-1)]))
 for r,c in coords:
  av=bf16_words(a[r]);wv=bf16_words(w[:,c]);acc=0;candidate_acc=0
  # Vectorize candidate over all K is invalid; sequential recurrence below.
  for j in range(k):
   aa=int(av[j]);bb=int(wv[j]);got,flags=fma(aa,bb,acc)
   cv=int(fma_bf16_words(np.uint32(aa),np.uint32(bb),np.uint32(candidate_acc)))
   if got!=cv:raise AssertionError((name,r,c,j,'step',got,cv))
   acc=got;candidate_acc=cv;counts[str(flags)]=counts.get(str(flags),0)+1;steps+=1
  if acc!=int(y[r,c]):raise AssertionError((name,r,c,'stored output',acc,int(y[r,c])))
 reports.append(dict(stage=name,outputs=len(coords),steps=steps,flag_counts=counts,status='SAMPLED_FULL_K_VALUE_AND_EXACT_FLAGS_ONLY'))
 print(json.dumps(reports[-1]),flush=True)
report=dict(status='PASS_BOUNDED_INDEPENDENT_ORACLE_AND_SAMPLED_PATHS',oracle_cases=len(cases),stages=reports,verified_inputs=verified,seconds=time.monotonic()-start,full_matrix_flags='NOT_QUALIFIED',hardware_comparison=False,all_matrix_outputs_verified=False)
(out/'RESULT.json').write_text(json.dumps(report,indent=2));print(report['status'],flush=True)
