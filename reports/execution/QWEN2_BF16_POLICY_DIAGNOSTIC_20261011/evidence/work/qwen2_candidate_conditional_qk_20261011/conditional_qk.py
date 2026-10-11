"""One conditional QK operator; own candidate Q/K, no full forward or admission."""
from pathlib import Path
import importlib.util,json,os,hashlib,time
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
CAND=ROOT/'work/qwen2_bf16_candidate_v1_m128_final_20261011'
NATIVE=ROOT/'work/qwen2_layer0_model_gate_cold_m128_20261011'
spec=importlib.util.spec_from_file_location('candidate',ROOT/'scripts/qwen2_bf16_materialization_candidate.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
r=json.loads((CAND/'RESULT.json').read_text());native=json.loads((NATIVE/'RESULT.json').read_text())
assert r['generator_sha256']==c.R.file_sha(ROOT/'scripts/qwen2_bf16_materialization_candidate.py')
recipe_dir=Path(r['recipe_directory']);recipe=c.R.validate_recipe_receipt(ROOT,recipe_dir)
c.R.validate_native_receipt(ROOT,NATIVE,recipe)
actual=c.load_exports(CAND/'tensors',r['tensors'],128)
c.validate_raw_evidence(r,CAND,recipe_dir,c.R.make_layout(),128,actual)
assert torch.__version__==native['identity']['torch']
for key,value in native['blas_environment'].items():assert os.environ.get(key)==value
torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.set_default_dtype(torch.float32)
torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
module,identity=c.N.runtime_identity(ROOT);assert identity==native['identity']
def saved(name):
 e=native['modes']['bf16']['phases'][0]['stages'][name]
 assert c.N.sha(NATIVE/e['native_file'])==e['native_file_sha256']
 a=np.fromfile(NATIVE/e['native_file'],dtype='<f4').reshape(e['native_export_shape'])
 if name in ('q','k'):a=a.reshape(1,128,12 if name=='q' else 2,128).transpose(0,2,1,3).copy()
 return a
def tensor(a):
 # Reconstruct original projection view/head transpose used in the traced call.
 return torch.from_numpy(a.transpose(0,2,1,3).copy()).to(torch.bfloat16).transpose(1,2)
q=tensor(actual['q']);k=tensor(actual['k']);kt=module.repeat_kv(k,6).transpose(2,3)
with torch.inference_mode():
 start=time.monotonic();dot=torch.matmul(q,kt);scores=dot/(128**0.5);elapsed=time.monotonic()-start
conditional=scores.float().numpy();conditional.tofile(OUT/'conditional_scores.f32le')
causal=np.broadcast_to(np.tri(128,dtype=bool)[None,None],conditional.shape)
def comparison(a,b):
 result={}
 for name,mask in [('all',np.ones(a.shape,dtype=bool)),('active_causal',causal),('masked_future',~causal)]:
  diff=np.abs(a.astype(np.float64)-b.astype(np.float64));flat=np.where(mask,diff,-1).argmax();ix=np.unravel_index(flat,a.shape)
  result[name]=dict(elements=int(mask.sum()),bit_mismatch_count=int(np.count_nonzero((a.view('<u4')!=b.view('<u4'))&mask)),
   max_abs=float(diff[ix]),max_abs_coordinate=list(map(int,ix)),left_at_max=float(a[ix]),right_at_max=float(b[ix]),
   mean_abs=float(diff[mask].mean()),over_original_operator_abs_limit_count=int(np.count_nonzero((diff>0.03125)&mask)))
 return result
inputs={}
for name,t in [('q',q),('k',k),('repeat_k_transposed',kt)]:
 inputs[name]=dict(shape=list(t.shape),stride=list(t.stride()),dtype=str(t.dtype),storage_sha256=hashlib.sha256(t.contiguous().view(torch.uint8).numpy().tobytes()).hexdigest())
result=dict(status='CONDITIONAL_OPERATOR_DIAGNOSTIC_NOT_ACCEPTED',scope='One native BF16 QK matmul and scale on candidate-owned Q/K; neither full official forward nor candidate acceptance.',
 tokens=128,elapsed_seconds=elapsed,script_sha256=c.N.sha(Path(__file__)),candidate_result_sha256=c.N.sha(CAND/'RESULT.json'),
 native_result_sha256=c.N.sha(NATIVE/'RESULT.json'),candidate_source_sha256=r['candidate_cpp_sha256'],actual_input=inputs,
 candidate_input_difference_from_official={name:c.N.compare(actual[name],saved(name)) for name in ('q','k')},
 conditional_vs_candidate=comparison(conditional,actual['scores']),conditional_vs_official=comparison(conditional,saved('scores')),
 candidate_vs_official=comparison(actual['scores'],saved('scores')),
 selected_points=[dict(coordinate=list(ix),conditional=float(conditional[ix]),candidate=float(actual['scores'][ix]),official=float(saved('scores')[ix]),masked_future=ix[-1]>ix[-2]) for ix in [(0,6,70,75),(0,9,102,2)]],
 output_sha256=c.N.sha(OUT/'conditional_scores.f32le'),identity=identity,
 backend_settings=dict(num_threads=torch.get_num_threads(),num_interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,deterministic=torch.are_deterministic_algorithms_enabled()),
 conclusion_boundary='Conditional comparison separates score arithmetic on identical candidate operands from upstream operand differences; it cannot establish the vendor reduction instruction order or satisfy the full-chain gates.')
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:result[k] for k in ('status','elapsed_seconds','conditional_vs_candidate','conditional_vs_official','selected_points')},indent=2))
