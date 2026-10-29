import hashlib,inspect,json,os,argparse
from pathlib import Path
import torch,transformers
from transformers.models.qwen2 import modeling_qwen2 as m
from transformers.models.qwen2.configuration_qwen2 import Qwen2Config

def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def raw(t):return t.detach().contiguous().view(torch.uint8).numpy().tobytes()
need(torch.__version__=='2.10.0+cpu' and transformers.__version__=='4.40.1','runtime')
need(sha(inspect.getfile(m))=='f1c7a117ced20ee632e4c17d09982863304d6e30bb44f0ccdebd4b27dde259ad','official source')
ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
p=args.config;need(sha(p)=='a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136','config')
cfg=Qwen2Config(**json.loads(p.read_text()));torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.set_float32_matmul_precision('highest');need(torch.get_default_dtype()==torch.float32 and torch.backends.cpu.get_cpu_capability()=='AVX512','dispatch/defaultdtype')
# Exact official decoder's rotary constructor: full32768 FP32 cache, then module BF16 conversion.
rot=m.Qwen2RotaryEmbedding(cfg.hidden_size//cfg.num_attention_heads,max_position_embeddings=cfg.max_position_embeddings,base=cfg.rope_theta).to(dtype=torch.bfloat16,device='cpu')
with torch.inference_mode(),torch.autocast('cpu',enabled=False):cos,sin=rot(torch.empty(0,dtype=torch.bfloat16),seq_len=1024)
need(tuple(cos.shape)==tuple(sin.shape)==(1024,128),'table shape');need(torch.equal(cos[:,:64],cos[:,64:]) and torch.equal(sin[:,:64],sin[:,64:]),'duplicated halves')
old=args.reference/'input_only'
need(raw(cos[:128].float())==(old/'rope_cos.bin').read_bytes(),'actual cosine128 prefix differs');need(raw(sin[:128].float())==(old/'rope_sin.bin').read_bytes(),'actual sine128 prefix differs')
table=torch.stack((cos[:,:64],sin[:,:64])).float();data=raw(table);out=args.output;out.mkdir(exist_ok=False);(out/'rope_fp32.bin').write_bytes(data)
r=dict(status='PASS_OFFICIAL_INPUT_ONLY_ROPE_CAPACITY_AND_PREFIX',shape=list(table.shape),dtype='FP32',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),layout='[cos_or_sin,position0..1023,first64channels]',arithmetic='Original FP32 constructor32768 cache then BF16module conversion; widen storedBF16 coefficients toFP32',actual128_prefix_byte_equal=True,source_sha256=sha(inspect.getfile(m)),config_sha256=sha(p),scope='Input-only capacity extension; no weights, decoderforward, output/reference or hardwareexecution')
(out/'manifest.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
