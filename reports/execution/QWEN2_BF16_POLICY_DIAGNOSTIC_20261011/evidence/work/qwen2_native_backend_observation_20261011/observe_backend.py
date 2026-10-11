from pathlib import Path
import importlib.util,json,os,platform,sys,hashlib,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;NATIVE=ROOT/'work/qwen2_layer0_model_gate_cold_m128_20261011'
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
n=load(ROOT/'scripts/qwen2_layer0_model_gate.py','n')
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from qwen2_layer0_payload import load_payload
original=json.loads((NATIVE/'RESULT.json').read_text())
assert torch.__version__==original['identity']['torch']
for key,value in original['blas_environment'].items():assert os.environ.get(key)==value
# Match the saved official gate's settings; verbosity/profiling are observers.
torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.set_default_dtype(torch.float32);torch.use_deterministic_algorithms(True)
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
module,identity=n.runtime_identity(ROOT)
assert identity==original['identity']
manifest,raw=load_payload(ROOT,ROOT/'work/qwen2_layer0_payload_20261011')
assert n.sha(ROOT/'work/qwen2_layer0_payload_20261011/manifest.json')==original['payload_manifest_sha256']
def checkpoint(name,shape):
 a=(np.frombuffer(raw[name],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(shape)
 return torch.from_numpy(a.copy()).to(torch.bfloat16)
def saved(name):
 entry=original['modes']['bf16']['phases'][0]['stages'][name];path=NATIVE/entry['native_file']
 assert n.sha(path)==entry['native_file_sha256']
 return np.fromfile(path,dtype='<f4').reshape(entry['native_export_shape']).copy()
x=torch.from_numpy(saved('n0')).to(torch.bfloat16)
w=checkpoint('self_attn.q_proj.weight',(1536,1536));bias=checkpoint('self_attn.q_proj.bias',(1536,))
# Reconstruct source graph's token-major projection view, head transpose, and
# literal official repeat_kv. Original runner did not retain original strides.
q=torch.from_numpy(saved('q').reshape(1,128,12,128)).to(torch.bfloat16).transpose(1,2)
k=torch.from_numpy(saved('k').reshape(1,128,2,128)).to(torch.bfloat16).transpose(1,2)
repeated=module.repeat_kv(k,6);kt=repeated.transpose(2,3)
inputs={}
for name,tensor in [('linear_input',x),('linear_weight',w),('linear_bias',bias),('q',q),('k',k),('repeat_k_transposed',kt)]:
 inputs[name]=dict(shape=list(tensor.shape),stride=list(tensor.stride()),dtype=str(tensor.dtype),contiguous=tensor.is_contiguous(),storage_offset=tensor.storage_offset(),storage_sha256=hashlib.sha256(tensor.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest())
with torch.inference_mode():
 start=time.monotonic()
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU],record_shapes=True,profile_memory=True,with_stack=True) as profile:
  with torch.profiler.record_function('QWEN2_ORIGINAL_SHAPE_Q_LINEAR'):
   qr=torch.nn.functional.linear(x,w,bias)
  with torch.profiler.record_function('QWEN2_ORIGINAL_SHAPE_QK_MATMUL_AND_SCALE'):
   dot=torch.matmul(q,kt)
   scores=dot/(128**0.5)
 elapsed=time.monotonic()-start
profile.export_chrome_trace(str(OUT/'trace.json'))
events=[]
for event in profile.key_averages(group_by_input_shape=True):
 events.append(dict(key=event.key,input_shapes=event.input_shapes,count=event.count,self_cpu_time_total=event.self_cpu_time_total,cpu_time_total=event.cpu_time_total))
(OUT/'operator_events.json').write_text(json.dumps(events,indent=2)+'\n')
comparisons={}
for name,tensor in [('qr',qr),('scores',scores)]:
 a=tensor.float().numpy();reference=saved(name)
 metrics=n.compare(a,reference)
 assert metrics['bit_exact'],f'original complete output did not reproduce: {name}'
 tensor.contiguous().view(torch.uint16).numpy().astype('<u2').tofile(OUT/f'observed_{name}.bf16le')
 comparisons[name]=dict(metrics=metrics,decoded_fp32_sha256=n.digest_array(a),storage_sha256=hashlib.sha256(tensor.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest(),original_storage_sha256=original['modes']['bf16']['phases'][0]['stages'][name]['actual_storage_sha256'])
 assert comparisons[name]['storage_sha256']==comparisons[name]['original_storage_sha256']
dot.contiguous().view(torch.uint16).numpy().astype('<u2').tofile(OUT/'observed_unscaled_qk.bf16le')
cpu={}
try:
 for line in Path('/proc/cpuinfo').read_text().splitlines():
  if ':' in line:
   key,value=(part.strip() for part in line.split(':',1))
   if key in ('vendor_id','cpu family','model','model name','stepping','flags') and key not in cpu:cpu[key]=value
except OSError as error:cpu={'read_error':str(error)}
result=dict(status='EXACT_TWO_OPERATOR_REPRODUCTION_WITH_PROFILER',scope='only original-shape Q Linear and QK matmul/scaling; no block forward or RTL',elapsed_seconds=elapsed,
 input=inputs,comparisons=comparisons,unscaled_qk=dict(shape=list(dot.shape),stride=list(dot.stride()),dtype=str(dot.dtype),storage_sha256=hashlib.sha256(dot.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest(),original_node_saved=False),
 original_result_sha256=n.sha(NATIVE/'RESULT.json'),identity=identity,environment={key:os.environ.get(key) for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_VERBOSE','ONEDNN_VERBOSE','DNNL_VERBOSE','ATEN_CPU_CAPABILITY')},
 backend_settings=dict(mkldnn_enabled=torch.backends.mkldnn.enabled,num_threads=torch.get_num_threads(),num_interop_threads=torch.get_num_interop_threads(),deterministic=torch.are_deterministic_algorithms_enabled()),
 cpu=cpu,trace_sha256=n.sha(OUT/'trace.json'),operator_events_sha256=n.sha(OUT/'operator_events.json'),script_sha256=n.sha(Path(__file__)),
 original_strides_saved=False,stride_reconstruction='token-major saved projection/RoPE values, source view/head transpose, literal official repeat_kv; exact full-node output reproduction verified',
 executed_instruction_order_proven=False,limitation='Profiler dispatcher/kernel names and verbose output cannot by themselves establish instruction-level accumulation or bias order. Raw unscaled original dot was not captured; full scaled score node is compared bitwise.')
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],elapsed_seconds=elapsed,full_output_bit_exact={key:value['metrics']['bit_exact'] for key,value in comparisons.items()},event_names=[e['key'] for e in events]),indent=2))
