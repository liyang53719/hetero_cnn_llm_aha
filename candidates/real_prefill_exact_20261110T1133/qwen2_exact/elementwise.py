"""All actual bias/RoPE/residual nodes, FP32 storage preserved."""
from softmax import *
def main_elementwise():
 payload=R/'round_20261110T0733/qwen2_host_payload';binding=json.loads((payload/'REAL_INPUT_BINDING.json').read_text());pp={x['name']:x['sha256'] for x in binding['records']}
 old=json.loads((P/'resume_m128/RESULT.json').read_text());rp={x['buffer']:x['sha256'] for x in old['progress']}
 def read(n,shape,kind='resume'):
  if kind=='payload':p=payload/(n+'.f32le');h=pp[n]
  elif n=='q0':p=P/'q0.local.f32';h=json.loads((P/'REAL_Q_RESULT.json').read_text())['q_sha256']
  else:p=P/'resume_m128'/(n+'.local.f32');h=rp[n]
  actual=hashlib.sha256(p.read_bytes()).hexdigest()
  if actual!=h:raise ValueError('pin '+n)
  verified[str(p.relative_to(R))]=h;return np.fromfile(p,dtype='<u4').reshape(shape).view('<f4')
 for n,width,bias in [('q',1536,'bq'),('k',256,'bk'),('v',256,'bv')]:
  out=add(read(n+'0',(128,width)),read(bias,(width,),'payload')[None,:],True,n+'_bias');expected=read(n+'b' if n!='v' else 'v',(128,width))
  if not np.array_equal(out.view('<u4'),expected.view('<u4')):raise ValueError('bias mismatch '+n)
 manifest=json.loads((P/'TRIG_MANIFEST.json').read_text());trig={}
 for n in ['cos','sin']:
  p=P/(n+'.local.f32');h=hashlib.sha256(p.read_bytes()).hexdigest()
  if h!=manifest['sha256'][str(p)]:raise ValueError('trig '+n)
  verified[n]=h;trig[n]=np.fromfile(p,dtype='<f4').reshape(1024,64)[:128,None,:]
 for n,heads in [('q',12),('k',2)]:
  a=read(n+'b',(128,heads,128));x=a[...,:64];y=a[...,64:];c=trig['cos'];s=trig['sin'];out=np.empty_like(a)
  out[...,:64]=add(mul(x,c,True,n+'_rope_xc'),-mul(y,s,True,n+'_rope_ys'),True,n+'_rope_sub')
  out[...,64:]=add(mul(x,s,True,n+'_rope_xs'),mul(y,c,True,n+'_rope_yc'),True,n+'_rope_add')
  if not np.array_equal(out.view('<u4'),load(n,(128,heads,128))):raise ValueError('RoPE '+n)
 x=read('x',(128,1536),'payload');res=add(x,load('proj',(128,1536)).view('<f4'),True,'residual0')
 if not np.array_equal(res.view('<u4'),load('res',(128,1536))):raise ValueError('residual0')
 out=add(res,load('down',(128,1536)).view('<f4'),True,'residual1')
 if not np.array_equal(out.view('<u4'),load('y',(128,1536))):raise ValueError('residual1')
 if not np.array_equal(load('kv.0',(128,256)),load('k',(128,256))):raise ValueError('K copy')
 if not np.array_equal(load('kv.1',(128,256)),read('v',(128,256)).view('<u4')):raise ValueError('V copy')
 for n,c in counts.items():
  if any(int(f)&6 for f in c['flags']):raise ValueError('node fatal flags '+n)
 check_environment()
 result=dict(status='PASS_FULL_M128_BIAS_ROPE_RESIDUAL_MATH_REFERENCE_NODE_FLAGS',counts=counts,verified_inputs=verified,scope='All stored FP32 bias/rope/residual words and KV copies checked; mathematical node flags not aggregate hardware status',hardware=False)
 (O/'ELEMENTWISE_RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main_elementwise()
