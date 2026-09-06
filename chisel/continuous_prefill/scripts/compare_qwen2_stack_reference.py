#!/usr/bin/env python3
"""Compare actual DUT hidden output against checkpoint-derived FP32 equations.

This is not a call to the official Transformers forward and is not a logits or
whole-model quality test. It intentionally remains separate from bit-exact
hardware-recipe validation. A failure is preserved; thresholds are not relaxed.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
import numpy as np

MODULE_PATH=Path(__file__).with_name('pack_qwen2_stack.py')
SPEC=importlib.util.spec_from_file_location('qwen2_stack_pack_reference',MODULE_PATH)
PACK=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)

# Developer-defined bring-up budget, not an established model-quality guarantee.
# Changing these values requires a new source commit and rerun of both references.
MAX_RELATIVE_L2=0.01
MIN_COSINE=0.9999
MAX_NORMALIZED_ABS=0.05


def metrics(actual: np.ndarray, reference: np.ndarray) -> dict[str,float]:
    a=np.asarray(actual,dtype=np.float64).reshape(-1)
    r=np.asarray(reference,dtype=np.float64).reshape(-1)
    if a.shape!=r.shape or a.size==0:raise ValueError('shape mismatch or empty tensor')
    if not np.isfinite(a).all() or not np.isfinite(r).all():raise ValueError('nonfinite hidden output')
    error=a-r;an=float(np.linalg.norm(a));rn=float(np.linalg.norm(r));en=float(np.linalg.norm(error))
    cosine=1.0 if an==0 and rn==0 else 0.0 if an==0 or rn==0 else float(np.dot(a,r)/(an*rn))
    relative=en/rn if rn else (0.0 if en==0 else math.inf)
    maximum=float(np.max(np.abs(error)));scale=float(np.max(np.abs(r)))
    normalized=maximum/scale if scale else (0.0 if maximum==0 else math.inf)
    return {'relative_l2':relative,'cosine':cosine,'max_abs':maximum,'mean_abs':float(np.mean(np.abs(error))),'normalized_max_abs':normalized}


def equation_reference(checkpoint, tokens: list[int], layers: int) -> np.ndarray:
    import torch
    import torch.nn.functional as functional
    cfg=checkpoint.config
    torch.set_num_threads(max(1,min(8,torch.get_num_threads())))
    torch.backends.cuda.matmul.allow_tf32=False
    h=int(cfg['hidden_size']);heads=int(cfg['num_attention_heads']);kv=int(cfg['num_key_value_heads']);dim=h//heads
    def tensor(name):return torch.from_numpy(np.array(checkpoint.fp32(name),dtype=np.float32,copy=True))
    def norm(x,gamma):return x*torch.rsqrt((x*x).mean(dim=-1,keepdim=True)+float(cfg['rms_norm_eps']))*gamma
    def linear(x,prefix,name,bias=False):
        w=tensor(prefix+name+'.weight')
        b=tensor(prefix+name+'.bias') if bias else None
        return functional.linear(x,w,b)
    with torch.inference_mode():
        x=torch.from_numpy(np.stack([checkpoint.fp32('model.embed_tokens.weight',t) for t in tokens]).copy())
        inverse=1.0/(float(cfg['rope_theta'])**(torch.arange(0,dim,2,dtype=torch.float32)/dim))
        angles=torch.arange(len(tokens),dtype=torch.float32)[:,None]*inverse[None,:]
        cosine=torch.cat((angles.cos(),angles.cos()),dim=-1)[None,:,:]
        sine=torch.cat((angles.sin(),angles.sin()),dim=-1)[None,:,:]
        def rope(y):
            rotated=torch.cat((-y[...,dim//2:],y[...,:dim//2]),dim=-1)
            return y*cosine+rotated*sine
        causal=torch.triu(torch.ones((len(tokens),len(tokens)),dtype=torch.bool),diagonal=1)
        for layer in range(layers):
            prefix=f'model.layers.{layer}.'
            n=norm(x,tensor(prefix+'input_layernorm.weight'))
            q=linear(n,prefix,'self_attn.q_proj',True).reshape(len(tokens),heads,dim).transpose(0,1)
            k=linear(n,prefix,'self_attn.k_proj',True).reshape(len(tokens),kv,dim).transpose(0,1)
            v=linear(n,prefix,'self_attn.v_proj',True).reshape(len(tokens),kv,dim).transpose(0,1)
            q=rope(q);k=rope(k)
            k=k.repeat_interleave(heads//kv,dim=0);v=v.repeat_interleave(heads//kv,dim=0)
            scores=torch.matmul(q,k.transpose(-1,-2))/math.sqrt(dim)
            probability=torch.softmax(scores.masked_fill(causal,float('-inf')),dim=-1)
            attended=torch.matmul(probability,v).transpose(0,1).contiguous().reshape(len(tokens),h)
            residual=x+linear(attended,prefix,'self_attn.o_proj')
            post=norm(residual,tensor(prefix+'post_attention_layernorm.weight'))
            gate=linear(post,prefix,'mlp.gate_proj');up=linear(post,prefix,'mlp.up_proj')
            x=residual+linear(functional.silu(gate)*up,prefix,'mlp.down_proj')
            if not bool(torch.isfinite(x).all()):raise ValueError(f'nonfinite equation reference layer {layer}')
        return x.cpu().numpy().astype('<f4',copy=False)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--packed-run-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run=a.packed_run_dir.resolve()
    receipt=json.loads((run/'RESULT.json').read_text());manifest=json.loads((run/'packed/manifest.json').read_text())
    if receipt.get('status')!='PASS_PACKED_CHECKPOINT_HARDWARE_RECIPE':raise ValueError('a completed actual-DUT checkpoint run is required')
    if receipt.get('checkpoint_manifest_sha256')!=PACK.digest(run/'packed/manifest.json'):raise ValueError('checkpoint manifest changed')
    actual_path=run/'actual_hidden.f32'
    if receipt.get('actual_hidden_sha256')!=PACK.digest(actual_path):raise ValueError('actual hidden changed')
    checkpoint=PACK.SafeCheckpoint(a.checkpoint)
    tokens=json.loads((run/'packed/tokens.json').read_text());layers=manifest['layers']
    PACK.validate_qwen2(checkpoint.config,manifest['layout'],layers)
    if manifest['config_sha256']!=PACK.digest(checkpoint.root/'config.json'):raise ValueError('reference checkpoint config differs from DUT input')
    if manifest['token_ids_sha256']!=PACK.digest(run/'packed/tokens.json'):raise ValueError('token sequence changed')
    if not manifest.get('source_files'):raise ValueError('checkpoint source identity absent')
    for name,h in manifest['source_files'].items():
        path=(checkpoint.root/name).resolve()
        if not path.is_relative_to(checkpoint.root) or PACK.digest(path)!=h:raise ValueError('checkpoint shard changed: '+name)
    if a.out.exists():raise ValueError('refuse reference output overwrite')
    a.out.mkdir(parents=True)
    ref=equation_reference(checkpoint,tokens,len(layers));actual=np.fromfile(actual_path,dtype='<f4')
    ref.tofile(a.out/'reference_hidden.f32');m=metrics(actual,ref)
    passed=bool(m['relative_l2']<=MAX_RELATIVE_L2 and m['cosine']>=MIN_COSINE and m['normalized_max_abs']<=MAX_NORMALIZED_ABS)
    result={'status':'PASS_CHECKPOINT_FP32_EQUATION_BUDGET' if passed else 'FAIL_CHECKPOINT_FP32_EQUATION_BUDGET',
      'reference_kind':'independent_FP32_checkpoint_equations_not_Transformers_forward',
      'layers':layers,'tokens':len(tokens),'elements':int(ref.size),'metrics':m,
      'thresholds':{'max_relative_l2':MAX_RELATIVE_L2,'min_cosine':MIN_COSINE,'max_normalized_abs':MAX_NORMALIZED_ABS},
      'threshold_status':'developer_defined_bringup_budget_not_model_quality_guarantee',
      'actual_hidden_sha256':PACK.digest(actual_path),'reference_hidden_sha256':PACK.digest(a.out/'reference_hidden.f32'),
      'checkpoint_manifest_sha256':PACK.digest(run/'packed/manifest.json'),
      'official_framework_forward':False,'logits':False,'full_model_quality':False,'pinned_idma':False,'dc':False}
    # Nonfinite ratios are represented explicitly, never non-standard JSON Infinity.
    for key,value in list(result['metrics'].items()):
        if not math.isfinite(value):result['metrics'][key]=None
    (a.out/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result,indent=2,allow_nan=False))
    return 0 if passed else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError,ImportError) as error:
        print('ERROR '+str(error),file=sys.stderr);raise SystemExit(2)
