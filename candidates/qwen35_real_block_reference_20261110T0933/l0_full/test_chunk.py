import importlib.util,numpy as np,json,pathlib,sys,struct
from fractions import Fraction
from chunk_candidate import Arithmetic,FatalArithmetic
R=pathlib.Path(__file__).resolve().parent;root=R.parents[1]
p=root/'round_20261110T0733/conv_raw_candidate/scalar_core.py';s=importlib.util.spec_from_file_location('old',p);old=importlib.util.module_from_spec(s);s.loader.exec_module(old)
sys.path.insert(0,str(root/'round_20261110T0833/legacy_python'));from rational_oracle import round_fraction
rng=np.random.default_rng(71)
for n in [2,4,8]:
 q=(rng.integers(-8,9,(n,8))/128).astype(np.float32);k=(rng.integers(-8,9,(n,8))/32).astype(np.float32);v=(rng.integers(-8,9,(n,8))/32).astype(np.float32);g=np.full(n,-.1,np.float32);b=np.full(n,.5,np.float32);state=np.zeros((8,8),np.float32)
 a=Arithmetic();out,ns=a.chunk(q,k,v,g,b,state)
 oy,os,_=old.chunk_once(q.tolist(),k.tolist(),v.tolist(),g.tolist(),b.tolist(),state.tolist(),0)
 u=out.view(np.uint32);outbf=((u+0x7fff+((u>>16)&1))>>16).astype(np.uint16)
 want=np.array(oy,np.float32).view(np.uint32)>>16
 if not np.array_equal(outbf,want) or not np.array_equal(ns.view(np.uint32),np.array(os,np.float32).view(np.uint32)):raise ValueError('ordered scalar oracle mismatch')
a=Arithmetic();xs=np.array([0,-.01,-.1,-.5,-1,-12,-79,-80],np.float32)
if not np.array_equal(a.exp(xs).view(np.uint32),np.array([old.exp_negative(float(x),0) for x in xs],np.float32).view(np.uint32)):raise ValueError('exp mismatch')
r=json.loads((R/'RESULT.json').read_text());count=0
for x in r['results']:
 if 'detail' not in x:continue
 d=x['detail'];f=lambda u:struct.unpack('<f',bytes.fromhex(u)[::-1])[0];aa=Fraction(f(d['a']));bb=Fraction(f(d['b']));e=aa*bb if d['operation']=='mul' else aa+bb
 if round_fraction(e)!=int(d['result'],16):raise ValueError('failure rounding not exact')
 count+=1
print('PASS small chunk64-equation order vs scalar oracle: n2/4/8; exp8; exact failing-operation RNE:',count)
