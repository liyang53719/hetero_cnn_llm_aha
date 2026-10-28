"""Pinned Torch reference-only tie audit. Never changes or exports routing IDs."""
import argparse,hashlib,inspect,json,os
from pathlib import Path

def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def raw(t):return t.detach().contiguous().view(__import__('torch').uint8).numpy().tobytes()
def boundary(values,indices):
 threshold=values.gather(-1,indices).min(dim=-1).values
 above=(values>threshold.unsqueeze(-1)).sum(dim=-1);equal=(values==threshold.unsqueeze(-1)).sum(dim=-1)
 return (above<indices.shape[-1])&(above+equal>indices.shape[-1])
def main():
 p=argparse.ArgumentParser();p.add_argument('result',type=Path);p.add_argument('output',type=Path);p.add_argument('--sidecar',type=Path,required=True);a=p.parse_args()
 need(os.environ.get('ATEN_CPU_CAPABILITY')=='default','original DEFAULT dispatch env')
 need(all(os.environ.get(k)=='1' for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS')),'original one-thread env')
 import torch
 need(torch.__version__=='2.10.0+cpu' and torch.version.git_version=='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0','original Torch build')
 need(torch.backends.cpu.get_cpu_capability()=='DEFAULT','actual DEFAULT dispatch')
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.set_float32_matmul_precision('highest')
 side=json.loads(a.sidecar.read_text());need(sha(a.sidecar)=='79078825f230ffecf33fff9b838d40b155217b025accf26e961927a25a475743','archive-derived35Bsidecar')
 site=Path(inspect.getfile(torch)).parent.parent
 for rel,h in side['native_file_sha256'].items():need(sha(site/rel)==h,'native Torch drift')
 need(sha(inspect.getfile(torch.nn.functional))==side['module_sha256']['torch.nn.functional'],'functional source drift')
 r=json.loads(a.result.read_text());base=a.result.parent;need(r['profile']['profile'] in (3,4),'MoE reference only');need(r['runtime_source_pins_sha256']==sha(a.sidecar),'same runtime sidecar');records=r['tensor_records']
 def read(name):
  v=records[name];path=base/v['file'];need(not path.is_symlink() and path.resolve().is_relative_to(base.resolve()),'reference path')
  data=path.read_bytes();need(len(data)==v['bytes'] and hashlib.sha256(data).hexdigest()==v['sha256'],'reference data drift')
  dtype={'torch.bfloat16':torch.bfloat16,'torch.float32':torch.float32,'torch.int64':torch.int64}[v['dtype']]
  return torch.frombuffer(bytearray(data),dtype=dtype).reshape(v['shape'])
 logits=read('stage.mlp.gate.0.0');scores=read('stage.mlp.gate.0.1');indices=read('stage.mlp.gate.0.2')
 need(logits.ndim==indices.ndim==2 and logits.shape[0]==indices.shape[0]==128,'complete128router tensors')
 with torch.inference_mode(),torch.autocast('cpu',enabled=False):
  # Exactly the original router softmax/topk/normalization operations, not NumPy approximations.
  probs=torch.nn.functional.softmax(logits,dtype=torch.float,dim=-1)
  top_values,top_indices=torch.topk(probs,indices.shape[-1],dim=-1)
  top_values/=top_values.sum(dim=-1,keepdim=True);top_values=top_values.to(logits.dtype)
  need(raw(top_indices)==raw(indices),'reconstructed original Torch topk differs from captured IDs')
  need(raw(top_values)==raw(scores),'reconstructed original selected scores differ from captured scores')
  score_ties=boundary(probs,indices);raw_ties=boundary(logits.float(),indices)
 report=dict(status='PASS_REFERENCE_ROUTER_DIAGNOSTICS_ONLY',reference_result_sha256=sha(a.result),tokens=128,experts=logits.shape[-1],top_k=indices.shape[-1],actual_captured_ids_and_selected_scores_reproduced_exactly=True,raw_logit_selection_boundary_tie_count=int(raw_ties.sum()),fp32_softmax_selection_boundary_tie_count=int(score_ties.sum()),fp32_softmax_boundary_tie_token_indices=score_ties.nonzero().flatten().tolist(),softmax_only_boundary_tie_count=int((score_ties&~raw_ties).sum()),arithmetic='Same pinned Torch CPU DEFAULT1thread softmax(dtype=float32), original topk, original normalization then originaldtype; no NumPy softmax',policy='Small-ID tie contract unresolved. No hardware IDs exported, no routing changed, no hardware mismatch waived.')
 with a.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps(report))
if __name__=='__main__':main()
