"""Real 0.8B L3 checkpoint -> original common runtime BF16 weight layout.
Only physical input/weight bytes; no fabricated producer receipt or Q/K/V output.
"""
from pathlib import Path
import hashlib,json,argparse,sys,numpy as np

def sha(b):return hashlib.sha256(b).hexdigest()
def fp(x):return (x.astype('<u4')<<np.uint32(16)).view('<f4')
def transpose_weight(w):
 if w.dtype!=np.dtype('<u2') or w.ndim!=2:raise ValueError('expected BF16 checkpoint N,K')
 return np.ascontiguousarray(w.T)
def ordered_dot(x,w):
 s=np.float32(0)
 for k in range(len(x)):s=np.float32(s+np.float32(x[k]*w[k]))
 return s

def prepare(root,payload,output):
 sys.path.insert(0,str(root.resolve()/'src'))
 from heteronpu.pinned_block_payload import load_payload
 manifest,raw=load_payload(root,payload) # original hash/geometry/HTTP receipt validator
 specs={t['local_name']:t for t in manifest['tensors']}
 output.mkdir(parents=True,exist_ok=False);records=[];validation=[]
 # Checkpoint weights remain BF16. Dense expects B[K,N], address b+(k*N+n)*2.
 for role,name,width in [(0,'q',4096),(1,'k',512),(2,'v',512)]:
  key='self_attn.'+name+'_proj.weight';w=np.frombuffer(raw[key],dtype='<u2').reshape(specs[key]['shape'])
  if w.shape!=(width,1024):raise ValueError('runtime profile2 shape drift')
  runtime=transpose_weight(w);blob=runtime.tobytes();filename=name+'_weight_k_n.bf16le';(output/filename).write_bytes(blob)
  # Independent scalar reference evaluates selected actual-weight columns using
  # identical ascending-k multiply/add order; this tests layout, not DUT order.
  x=(np.arange(1024,dtype='<f4')%17-8)/np.float32(32)
  for n in [0,width//2,width-1]:
   original=ordered_dot(x,fp(w[n]));mapped=ordered_dot(x,fp(runtime[:,n]))
   if original.view('<u4')!=mapped.view('<u4'):raise ValueError('layout changes projection')
   validation.append(dict(role=role,column=n,result_fp32_bits=f'{int(original.view("<u4")):08x}'))
  if not np.array_equal(runtime.T,w):raise ValueError('not bitwise reversible')
  records.append(dict(role=role,name=name,file=filename,shape=[1024,width],dtype='BF16',bytes=len(blob),sha256=sha(blob),source_sha256=sha(raw[key])))
 # Runtime RMS takes raw gamma. Do not pre-apply 1+gamma or normalize input.
 for key in ['input_layernorm.weight','self_attn.q_norm.weight','self_attn.k_norm.weight']:
  filename=key+'.bf16le';(output/filename).write_bytes(raw[key]);records.append(dict(name=key,file=filename,shape=specs[key]['shape'],dtype='BF16',bytes=len(raw[key]),sha256=sha(raw[key])))
 # Declared synthetic layer input, not mislabelled trained layer0-2 activation.
 x=np.arange(128*1024,dtype='<i4').reshape(128,1024)%17-8
 values=(x.astype('<f4')/np.float32(32)).view('<u4')
 if np.any(values&65535):raise ValueError('input not exact BF16')
 blob=(values>>16).astype('<u2').tobytes();(output/'input_m128.bf16le').write_bytes(blob)
 records.append(dict(name='input',file='input_m128.bf16le',shape=[128,1024],dtype='BF16',bytes=len(blob),sha256=sha(blob),origin='synthetic_exact_dyadic_not_prior_layers_output'))
 summary=dict(status='PASS_LAYOUT_BYTES_AND_SELECTED_REFERENCE_ONLY',runtime_profile=2,tokens=128,hidden=1024,model=manifest['model_id'],revision=manifest['revision'],records=records,selected_ordered_reference=validation,reference_order='ascending_k_separate_fp32_multiply_add_only_layout_check_not_asserted_DUT_order',initial_memory_contains_only='inputs_and_weights',producer_outputs_preset=False,producer_receipts_fabricated=False,hardware_executed=False,full_block_pass=False)
 (output/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');return summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--payload',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.root,a.payload,a.output),indent=2))
