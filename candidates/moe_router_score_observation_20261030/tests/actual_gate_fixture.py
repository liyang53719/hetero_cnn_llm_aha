"""Bounded real pinned Torch/official gate-only observer fixture; NOT block PASS."""
import argparse,hashlib,inspect,json
from pathlib import Path
from types import SimpleNamespace
from router_local_observer import OfficialRouterObserver

def need(x,message):
 if not x:raise ValueError(message)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--sidecar',type=Path,required=True);p.add_argument('--sidecar-sha',required=True);p.add_argument('--observer-sha',required=True);a=p.parse_args()
 helper=Path(__file__).with_name('router_local_observer.py');need(sha(helper)==a.observer_sha,'observer identity')
 need(sha(a.sidecar)==a.sidecar_sha,'sidecar identity');sidecar=json.loads(a.sidecar.read_text())
 import torch,importlib
 need(torch.__version__=='2.10.0+cpu' and torch.version.git_version=='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0','pinned Torch')
 need(torch.backends.cpu.get_cpu_capability()=='DEFAULT','DEFAULT CPU')
 for name,digest in sidecar['module_sha256'].items():need(sha(inspect.getfile(importlib.import_module(name)))==digest,'module pin '+name)
 from transformers.models.qwen3_5_moe.modeling_qwen3_5_moe import Qwen3_5MoeTopKRouter
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.set_float32_matmul_precision('highest')
 gate=Qwen3_5MoeTopKRouter(SimpleNamespace(num_experts_per_tok=8,num_experts=256,hidden_size=2048)).to(dtype=torch.bfloat16).eval()
 # Deliberately repeated deterministic weights exercise tied experts without
 # choosing a tie policy. This is synthetic fixture data, not model weights.
 with torch.no_grad():gate.weight.copy_(((torch.arange(256*2048,dtype=torch.int64).reshape(256,2048)%31)-15).float().div(1024).to(torch.bfloat16))
 x=((torch.arange(128*2048,dtype=torch.int64).reshape(128,2048)%17)-8).float().div(64).to(torch.bfloat16)
 code=type(gate).forward.__code__;topk=torch.topk;softmax=torch.nn.functional.softmax
 def raw(t):return t.detach().contiguous().view(torch.uint8).numpy().tobytes()
 with torch.inference_mode(),torch.autocast('cpu',enabled=False):baseline=gate(x)
 observer=OfficialRouterObserver(gate)
 with torch.inference_mode(),torch.autocast('cpu',enabled=False),observer:observed=gate(x)
 need(observed is observer.events[0][1],'original returned tuple retained, not substituted')
 need(type(gate).forward.__code__ is code and torch.topk is topk and torch.nn.functional.softmax is softmax,'original callable identity unchanged')
 need(all(raw(a)==raw(b) for a,b in zip(baseline,observed)),'observer changed original outputs')
 probs=observer.take(torch);need(probs is observer.events[0][0],'captured original local identity')
 for name,digest in sidecar['module_sha256'].items():need(sha(inspect.getfile(importlib.import_module(name)))==digest,'post module pin '+name)
 need(sha(helper)==a.observer_sha,'post observer identity')
 print(json.dumps({'status':'PASS_GATE_ONLY_OBSERVER_FIXTURE','scope':'SYNTHETIC_128x2048_GATE_ONLY_NOT_FULL_BLOCK_NOT_OFFICIAL_WEIGHT_REFERENCE','torch_version':torch.__version__,'forward_calls':2,'original_return_identity':True,'original_outputs_ids_weights_bitwise_unchanged':True,'captured_local_identity':True,'capture':{'shape':list(probs.shape),'dtype':str(probs.dtype),'bytes':len(raw(probs)),'sha256':hashlib.sha256(raw(probs)).hexdigest()},'outputs':[{'shape':list(t.shape),'dtype':str(t.dtype),'sha256':hashlib.sha256(raw(t)).hexdigest()}for t in observed],'hardware_executed':False,'block_numerical_pass':False},sort_keys=True))
if __name__=='__main__':main()
