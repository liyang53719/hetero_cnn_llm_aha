"""Full Qwen2 original ascending RMS, not Qwen3.5 grouped RMS."""
from softmax import *
import operators as ops

def main_rms():
 payload=R/'round_20261110T0733/qwen2_host_payload';binding=json.loads((payload/'REAL_INPUT_BINDING.json').read_text());pp={x['name']:x['sha256'] for x in binding['records']}
 prior=json.loads((P/'REAL_Q_RESULT.json').read_text());pins['norm0']=prior['norm_sha256']
 def source(n,shape):
  f=payload/(n+'.f32le');h=hashlib.sha256(f.read_bytes()).hexdigest()
  if h!=pp[n]:raise ValueError('payload pin '+n)
  verified[n]=h;return np.fromfile(f,dtype='<u4').reshape(shape).view('<f4')
 summaries=[]
 for name,an,gn,on in [('input','x','gamma0','norm0'),('post','res','gamma1','norm1')]:
  a=source(an,(128,1536)) if an=='x' else load(an,(128,1536)).view('<f4');gamma=source(gn,(1536,));total=np.zeros(128,np.float32)
  for j in range(1536):
   square=mul(a[:,j],a[:,j],True,name+'_square');total=add(total,square,True,name+'_sum')
  recip=np.array([ref.rounded(Fraction(1,1536))],dtype='<u4').view('<f4')[0];mean=mul(total,recip,True,name+'_mean');argument=add(mean,np.array([0x358637bd],dtype='<u4').view('<f4')[0],True,name+'_epsilon');inv=np.empty(128,dtype='<u4');stats={'sqrt':{},'div':{}}
  budget=ref.Budget(100000)
  for i,u in enumerate(argument.view('<u4')):
   root=ops.sqrt(int(u),budget);sq_exact=ref.fraction(root)**2==ref.fraction(int(u));sf=0 if sq_exact else 1;stats['sqrt'][str(sf)]=stats['sqrt'].get(str(sf),0)+1
   w=ops.div(0x3f800000,root,budget);df=int(ref.fraction(w)!=Fraction(1)/ref.fraction(root));stats['div'][str(df)]=stats['div'].get(str(df),0)+1;inv[i]=w
  scaled=mul(a,inv.view('<f4')[:,None],True,name+'_normalize');final=mul(scaled,gamma[None,:],True,name+'_gamma');out=bf16_words(final.view('<u4'))
  if on=='norm0':
   f=P/'norm0.local.f32';h=hashlib.sha256(f.read_bytes()).hexdigest()
   if h!=pins[on]:raise ValueError('norm0 pin')
   verified[on]=h;expected=np.fromfile(f,dtype='<u4').reshape(128,1536)
  else:expected=load(on,(128,1536))
  if not np.array_equal(out,expected):raise ValueError('RMS full output mismatch '+name)
  summaries.append(dict(stage=name,rows=128,width=1536,sqrt_div_flags=stats,output_sha256=hashlib.sha256(out.tobytes()).hexdigest()))
 for name,c in counts.items():
  if any(int(f)&6 for f in c['flags']):raise ValueError('fatal/node flags '+name)
 check_environment()
 result=dict(status='PASS_BOTH_FULL_M128_QWEN2_RMS_MATH_REFERENCE_NODES',counts=counts,stages=summaries,verified_inputs=verified,scope='Ascending square/sum plus exact sqrt/div and ordered normalize/gamma; BF16 materialization values only, conversion flags excluded; no hardware/fullblock acceptance',hardware=False)
 (O/'RMS_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main_rms()
