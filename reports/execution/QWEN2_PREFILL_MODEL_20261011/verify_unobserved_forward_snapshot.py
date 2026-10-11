"""Diagnostic replay only: unchanged official forward, without observers."""
from pathlib import Path
import gc, hashlib, json, math, os, sys, time
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import qwen2_layer0_model_gate as gate
from qwen2_layer0_payload import load_payload
from transformers.modeling_attn_mask_utils import _prepare_4d_causal_attention_mask

base = Path(__file__).resolve().parent
original = json.loads((base / 'RESULT.json').read_text())
module, identity = gate.runtime_identity(ROOT)
assert identity == original['identity']
torch.set_num_threads(4)
torch.set_num_interop_threads(1)
torch.set_default_dtype(torch.float32)
torch.use_deterministic_algorithms(True)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
manifest, raw = load_payload(ROOT, ROOT / 'work/qwen2_layer0_payload_20261011')
records = {entry['local_name']:entry for entry in manifest['tensors']}
weights = {name: (np.frombuffer(value,dtype='<u2').astype(np.uint32)<<16).view(np.float32).reshape(records[name]['shape']) for name,value in raw.items()}
embeddings = weights.pop('embed_tokens.rows_0_255')
del raw
config_dict = json.loads((ROOT/gate.SOURCE/'config.json').read_text())
config = module.Qwen2Config(**config_dict); config._attn_implementation='eager'
x = embeddings[:128][None].copy()
positions = torch.arange(128,dtype=torch.long).unsqueeze(0)
result={'status':'DIAGNOSTIC_UNOBSERVED_REPLAY','original_result_sha256':gate.sha(base/'RESULT.json'),
        'diagnostic_source_sha256':gate.sha(Path(__file__)), 'identity':identity,
        'payload_manifest_sha256':gate.sha(ROOT/'work/qwen2_layer0_payload_20261011/manifest.json'),
        'input_f32_sha256':gate.digest_array(x),'token_ids':list(range(128)),
        'position_ids':positions.tolist(), 'head_dim':128,'scale_divisor':math.sqrt(128),
        'mask':'official _prepare_4d_causal_attention_mask, past=0, no padding, no sliding window',
        'autocast_cpu_enabled':torch.is_autocast_enabled('cpu'),'no_RTL':True,
        'acceptance_change':False,'modes':{}}
for mode,dtype in [('bf16',torch.bfloat16),('fp32',torch.float32)]:
    layer=module.Qwen2DecoderLayer(config,layer_idx=0)
    layer.load_state_dict({name:torch.from_numpy(value).to(dtype) for name,value in weights.items()}, strict=True,assign=True)
    layer.to(dtype=dtype).eval()
    xt=torch.from_numpy(x).to(dtype)
    assert np.array_equal(xt.float().numpy().view(np.uint32),x.view(np.uint32))
    assert all(np.array_equal(param.detach().float().numpy().view(np.uint32),weights[name].view(np.uint32)) for name,param in layer.named_parameters())
    assert all(not sub.training and not sub._forward_hooks and not sub._forward_pre_hooks for sub in layer.modules())
    assert sys.gettrace() is None and sys.getprofile() is None
    assert not torch.is_autocast_enabled('cpu')
    mask=_prepare_4d_causal_attention_mask(None,xt.shape[:2],xt,0)
    cache=module.DynamicCache()
    started=time.monotonic()
    with torch.inference_mode():
        out=layer(xt,attention_mask=mask,position_ids=positions,past_key_value=cache,output_attentions=True,use_cache=True)
    elapsed=time.monotonic()-started
    y=out[0].float().numpy()
    native_entry=original['modes'][mode]['phases'][0]['stages']['y']
    prior=np.fromfile(base/native_entry['native_file'],dtype='<f4').reshape(native_entry['shape'])
    metric=gate.compare(y,prior)
    mask_entry=original['modes'][mode]['phases'][0]['stages']['mask']
    prior_mask=np.fromfile(base/mask_entry['native_file'],dtype='<f4').reshape(mask_entry['shape'])
    checks={
        'y_bit_exact_to_observed_forward':metric['bit_exact'],
        'input_lossless_from_BF16_checkpoint':True,'parameters_lossless_from_BF16_checkpoint':True,
        'all_modules_eval':True,'no_hooks_or_tracer':True,
        'mask_bit_exact_to_observed':np.array_equal(mask.float().numpy().view(np.uint32),prior_mask.view(np.uint32)),
        'cache_sequence_length':cache.get_seq_length(0),
        'parameter_count':sum(v.numel()for v in layer.parameters()),
        'parameter_names':sorted(weights),
        'selected_attention_class':type(layer.self_attn).__name__,
        'stored_key_dtype':str(cache.key_cache[0].dtype),'stored_value_dtype':str(cache.value_cache[0].dtype),
        'finite':bool(torch.isfinite(out[0]).all()),'seconds':elapsed,'metrics':metric}
    for stage,tensor in [('cache_k',cache.key_cache[0]),('cache_v',cache.value_cache[0]),('prob',out[1])]:
        s=original['modes'][mode]['phases'][0]['stages'][stage]
        prior=np.fromfile(base/s['native_file'],dtype='<f4').reshape(s['shape'])
        checks[stage+'_bit_exact_to_observed']=np.array_equal(tensor.float().numpy().view(np.uint32),prior.view(np.uint32))
    result['modes'][mode]=checks
    del layer,xt,mask,cache,out,y
    gc.collect()

stages={}
for name in sorted(gate.REQUIRED_STAGES):
    arrays={}
    for mode in ['bf16','fp32']:
        entry=original['modes'][mode]['phases'][0]['stages'][name]
        arrays[mode]=np.fromfile(base/entry['native_file'],dtype='<f4').reshape(entry['native_export_shape'])
    stats=gate.compare(arrays['bf16'],arrays['fp32'])
    for mode,array in arrays.items():
        absolute=np.abs(array.astype(np.float64))
        stats[mode+'_magnitude']={'min':float(array.min()),'max':float(array.max()),'max_abs':float(absolute.max()),
                                  'mean_abs':float(absolute.mean()),'rms':float(np.sqrt(np.mean(array.astype(np.float64)**2)))}
    delta=np.abs(arrays['bf16'].astype(np.float64)-arrays['fp32'].astype(np.float64))
    coordinate=np.unravel_index(delta.argmax(),delta.shape)
    stats['maximum_error_export_coordinate']=list(map(int,coordinate))
    stats['maximum_error_native_bf16_value']=float(arrays['bf16'][coordinate])
    stats['maximum_error_native_fp32_value']=float(arrays['fp32'][coordinate])
    stages[name]=stats
result['native_bf16_vs_native_fp32_stages']=stages
result['all_unobserved_outputs_match']=all(mode['y_bit_exact_to_observed_forward'] and mode['cache_k_bit_exact_to_observed'] and mode['cache_v_bit_exact_to_observed'] and mode['prob_bit_exact_to_observed']for mode in result['modes'].values())
(base/'UNOBSERVED_FORWARD_DIAGNOSTIC.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({'all_unobserved_outputs_match':result['all_unobserved_outputs_match'],'modes':result['modes'],
'ordered_stage_summary':{name:{k:stages[name][k]for k in ['max_abs','mean_abs','relative_l2','bf16_magnitude','fp32_magnitude']}for name in ['x','n0','qr','kr','v','cos','sin','q','k','scores','logits','prob','att','o','r','n1','gate','up','silu','act','down','y']}},indent=2))
