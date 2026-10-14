"""Non-runnable, reviewable capture body for the next explicitly authorized revision.

This module imports only stdlib. capture() always raises before touching arguments,
inputs, outputs, Torch or NumPy. The body below that latch is a source proposal,
not execution evidence. Removing the latch requires a new review and source seal;
no flag, environment variable, receipt, or pin edit can enable this revision.
"""
from __future__ import annotations

import ast
import collections
import copy
import datetime
import hashlib
import math
import os
import re
from pathlib import Path
import sys
import types


class CaptureDisabled(RuntimeError):
    pass


def capture(root, pins, out, *, stage='bootstrap-capture', recipe=None):
    raise CaptureDisabled('SOURCE_ONLY: capture implementation awaits independent review and new authorization/seal')

    # BEGIN REVIEWABLE FUTURE BODY. Intentionally unreachable in this revision.
    R = recipe
    R.need(stage in ('bootstrap-capture','capture'), 'only bootstrap or distinct frozen reproduction')
    bootstrap = stage == 'bootstrap-capture'
    if not bootstrap:
        R.require_frozen_references(pins)
    R.need(not any(n in sys.modules for n in ('torch','numpy','transformers')), 'fresh numerical process required')
    R.need(sys.gettrace() is None, 'existing tracer refused')
    R.source_check(root,pins)
    expected = pins['runtime_requirements']
    R.need({k:os.getenv(k) for k in pins['capture_environment']} == pins['capture_environment'],
           'explicit pinned environment required; no implicit overrides')
    relative = str(out.relative_to(root))
    R.need(re.fullmatch(r'work/qwen2_fullblock_reference_m128/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/'
                       r'(bootstrap|frozen)',relative), 'fresh canonical planned output path required')
    R.need(R.safe_path(root,relative) == out and not out.exists(), 'fresh output required')
    R.need(out.name == ('bootstrap' if bootstrap else 'frozen'), 'stage path mismatch')

    def native_identity():
        result = {}
        for name,pin in pins['runtime_native_files'].items():
            path = Path(pin['path']) if Path(pin['path']).is_absolute() else R.safe_path(root,pin['path'])
            raw = path.read_bytes()
            actual = {'path':pin['path'],'bytes':len(raw),'sha256':R.sha(raw)}
            R.need(R.same(actual,pin), 'native runtime identity drift: '+name)
            result[name] = actual
        return result

    def boundary():
        R.source_check(root,pins)
        R.need(R.same(R.load_pins(root),pins), 'in-memory pin drift')
        sources = {path:{'bytes':pin['bytes'],'sha256':R.sha(R.checked(root,path,pin))}
                   for path,pin in pins['sources'].items()}
        own = {name:R.sha(R.safe_path(root,R.PACKAGE+'/'+name).read_bytes())
               for name in ('recipe.py','capture.py','pins.json','ADMISSION.json')}
        raws = {spec['path']:{'bytes':spec['bytes'],'sha256':R.sha(R.checked(root,spec['path'],spec))}
                for spec in pins['raw_tensors']}
        return {'sources':sources,'recipe':own,'raw13':raws,'native_files':native_identity()}

    before = boundary()
    # Only original raw13 are arithmetic inputs. The 14 materialized role files
    # are NEVER opened by this oracle, including gamma1's FP32 producer export.
    values = {s['local_name']:R.checked(root,s['path'],s) for s in pins['raw_tensors']}
    nodes = R.official_nodes(root,pins['model_ast_nodes'],R.MODEL_SOURCE,pins['sources'])
    activations = R.official_nodes(root,pins['activation_ast_nodes'],R.ACTIVATION_SOURCE,pins['sources'])
    import numpy as np
    import torch
    from torch import nn
    R.need(np.__version__ == expected['numpy'] and str(torch.__version__) == expected['torch'] and
           torch.version.git_version == expected['torch_commit'], 'runtime version drift')
    R.need(torch.backends.cpu.get_cpu_capability() == expected['capability'], 'CPU dispatch drift')
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    R.need(R.sha(torch.__config__.show().encode()) == expected['torch_build_sha256'], 'Torch build drift')
    R.need(Path(torch._C.__file__).resolve() == (root/pins['runtime_native_files']['torch_C']['path']).resolve(),
           'Torch imported from unpinned runtime')
    R.need(Path(np._core._multiarray_umath.__file__).resolve() ==
           (root/pins['runtime_native_files']['numpy_multiarray']['path']).resolve(), 'NumPy imported from unpinned runtime')
    R.need(Path(sys.executable).resolve() == Path(pins['runtime_native_files']['python']['path']).resolve(),
           'Python executable path drift')
    namespace = {'torch':torch,'nn':nn,'Tensor':torch.Tensor,'math':math,'OrderedDict':collections.OrderedDict}

    def execute(part,filename=R.MODEL_SOURCE):
        # Compile unchanged whole AST nodes; no replacing/splitting expressions.
        code = compile(ast.Module(body=copy.deepcopy(part),type_ignores=[]),str(root/filename),'exec')
        exec(code,namespace)

    execute(activations,R.ACTIVATION_SOURCE)
    execute(nodes[:4])
    execute(nodes[15:16])
    execute(nodes[27:28])  # Original Qwen2MLP class, including its original line180.
    specs = {s['local_name']:s for s in pins['raw_tensors']}

    def tensor(name):
        spec = specs[name]
        value = torch.from_numpy(np.frombuffer(values[name],dtype='<u2').copy()).view(
            torch.bfloat16).reshape(spec['shape'])
        R.need(value.dtype == torch.bfloat16 and list(value.shape) == spec['shape'], 'raw binding '+name)
        return value

    x = tensor('embed_tokens.rows_0_255')[:128].unsqueeze(0).contiguous()
    norm = namespace['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
    norm.weight = nn.Parameter(tensor('input_layernorm.weight'),requires_grad=False)
    attention = nn.Module()
    attention.hidden_size,attention.num_heads = 1536,12
    attention.num_key_value_heads,attention.head_dim = 2,128
    attention.num_key_value_groups,attention.attention_dropout = 6,0.0
    namespace['self'] = attention
    execute(nodes[4:7])
    execute(nodes[28:29])  # Original o_proj constructor231.
    for letter in 'qkv':
        layer = getattr(attention,letter+'_proj')
        layer.weight = nn.Parameter(tensor('self_attn.'+letter+'_proj.weight'),requires_grad=False)
        layer.bias = nn.Parameter(tensor('self_attn.'+letter+'_proj.bias'),requires_grad=False)
    attention.o_proj.weight = nn.Parameter(tensor('self_attn.o_proj.weight'),requires_grad=False)
    attention.rotary_emb = namespace['Qwen2RotaryEmbedding'](
        128,max_position_embeddings=256,base=1e6).to(torch.bfloat16)
    attention.to(torch.bfloat16).eval()
    # Bounded rotary256 vs official config32768 remains explicitly disclosed.
    config = types.MappingProxyType({'hidden_size':1536,'intermediate_size':8960,
                                     'rms_norm_eps':1e-6,'hidden_act':'silu'})
    class ReadOnlyConfig:
        __slots__ = ()
        def __getattr__(self,name):
            return config[name]
    decoder = nn.Module()
    namespace.update(self=decoder,config=ReadOnlyConfig())
    execute(nodes[29:31])  # Original decoder730 / postnorm732.
    decoder.post_attention_layernorm.weight = nn.Parameter(tensor('post_attention_layernorm.weight'),requires_grad=False)
    for name in ('gate','up','down'):
        getattr(decoder.mlp,name+'_proj').weight = nn.Parameter(tensor('mlp.'+name+'_proj.weight'),requires_grad=False)
    decoder.to(torch.bfloat16).eval()
    R.need(type(decoder.mlp.act_fn) is nn.SiLU and decoder.mlp.act_fn.inplace is False,
           'original ACT2FN[hidden_act] must select non-inplace nn.SiLU')
    for module in (norm,attention,decoder):
        R.need(not module.training, 'all holders in eval')
        for parameter in module.parameters():
            R.need(parameter.dtype == torch.bfloat16 and not parameter.requires_grad,
                   'all random parameters replaced by fixed raw BF16 before arithmetic')
    # Explicit cold mask wrapper argument, not a claim of mask-helper execution.
    mask_raw = b''.join((0xff7f if k > q else 0).to_bytes(2,'little')
                        for q in range(128) for k in range(128))
    R.need(R.sha(mask_raw) == pins['mask_contract']['native_sha256'], 'exact cold mask words')
    mask = torch.from_numpy(np.frombuffer(mask_raw,dtype='<u2').copy()).view(torch.bfloat16).reshape(1,1,128,128)
    outputs = {}
    hook_records = {}
    hook_order = []
    handles = []
    softmax_returns = []
    softmax_code = nn.functional.softmax.__code__

    def trace(frame,event,arg):
        if frame.f_code is softmax_code:
            if event == 'return':
                softmax_returns.append(arg.detach())
            return trace
        return None

    def observe(name,value):
        R.need(name not in hook_records, 'duplicate MLP hook: '+name)
        # Record actual returned tensor layout, then copy for observation only.
        hook_records[name] = {'shape':list(value.shape),'native_dtype':str(value.dtype),
            'native_stride':list(value.stride()),'storage_offset':value.storage_offset(),
            'is_contiguous':value.is_contiguous()}
        outputs[name] = value.detach().clone()
        hook_order.append(name)

    def output_hook(name):
        def hook(module,args,result):
            observe(name,result)
            return None
        return hook

    def down_pre_hook(module,args):
        R.need(len(args) == 1, 'down input observation arity')
        observe('act',args[0])
        return None

    with torch.inference_mode():
        namespace.update(hidden_states=x,self=attention)
        execute(nodes[31:32])  # Original763 preserves input x before prefix.
        n0 = norm(x)
        namespace['hidden_states'] = n0
        execute(nodes[7:10])
        outputs.update(x=x,n0=n0,qr=namespace['query_states'],kr=namespace['key_states'],v=namespace['value_states'])
        namespace.update(bsz=1,q_len=128,kv_seq_len=128,
                         position_ids=torch.arange(128,dtype=torch.long).unsqueeze(0))
        execute(nodes[10:13])
        execute(nodes[13:15])
        outputs.update(q=namespace['query_states'],k=namespace['key_states'],cos=namespace['cos'],sin=namespace['sin'],
                       cache_k=namespace['key_states'],cache_v=namespace['value_states'])
        namespace['attention_mask'] = mask
        execute(nodes[16:18])
        outputs.update(repeat_k=namespace['key_states'],repeat_v=namespace['value_states'],mask=mask)
        execute(nodes[18:20]); outputs['scores'] = namespace['attn_weights']
        execute(nodes[20:21]); outputs['logits'] = namespace['attn_weights']
        try:
            sys.settrace(trace)
            execute(nodes[21:22])  # Original300 unchanged FP32 softmax -> BF16.
        finally:
            sys.settrace(None)
        R.need(len(softmax_returns) == 1, 'exactly one native softmax return')
        outputs['softmax_fp32'] = softmax_returns[0]
        execute(nodes[22:23]); outputs['prob'] = namespace['attn_weights']
        execute(nodes[23:25]); outputs['pv'] = namespace['attn_output']
        execute(nodes[25:27]); outputs['att'] = namespace['attn_output']
        execute(nodes[32:33]); outputs['o'] = namespace['attn_output']  # Original313.
        # Wrapper-only name/context handoff. No claim full Attention/Decoder ran.
        namespace.update(hidden_states=namespace['attn_output'],self=decoder)
        execute(nodes[33:34]); outputs['r'] = namespace['hidden_states']
        execute(nodes[34:35])
        execute(nodes[35:36]); outputs['n1'] = namespace['hidden_states']
        try:
            for name,module in [('gate',decoder.mlp.gate_proj),('silu',decoder.mlp.act_fn),
                                ('up',decoder.mlp.up_proj),('down',decoder.mlp.down_proj)]:
                handles.append(module.register_forward_hook(output_hook(name)))
            handles.append(decoder.mlp.down_proj.register_forward_pre_hook(down_pre_hook))
            execute(nodes[36:37])  # Original781; original MLP180 remains whole.
        finally:
            for handle in handles:
                handle.remove()
        R.need(hook_order == ['gate','silu','up','act','down'], 'original MLP hook count/order')
        R.need(torch.equal(outputs['down'],namespace['hidden_states']), 'down hook return is original MLP result')
        execute(nodes[37:38]); outputs['y'] = namespace['hidden_states']
    R.exact_keys(outputs,R.NAMES,'captured29')
    R.need('transformers' not in sys.modules, 'Transformers import forbidden')
    records,raw_outputs = {},{}
    for name,value in outputs.items():
        spec = pins['references'][name]
        dtype = torch.float32 if name == 'softmax_fp32' else torch.bfloat16
        R.need(value.dtype == dtype and bool(torch.isfinite(value).all()), 'native finite dtype '+name)
        data = value.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
        native = value.contiguous().view(torch.uint8).numpy().tobytes()
        token = value.transpose(1,2).reshape(1,128,-1) if name in R.TOKEN_MAJOR else value
        token_data = token.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
        layout = hook_records.get(name,{'native_stride':list(value.stride()),
            'storage_offset':value.storage_offset(),'is_contiguous':value.is_contiguous()})
        actual = {'shape':list(value.shape),'bytes':len(data),'native_dtype':str(value.dtype),
            'export_dtype':spec['export_dtype'],'native_bytes':len(native),'sha256':R.sha(data),
            'native_sha256':R.sha(native),'token_major_sha256':R.sha(token_data),
            **{k:layout[k] for k in ('native_stride','storage_offset','is_contiguous')}}
        R.fields(actual,{k:spec[k] for k in ('shape','bytes','native_dtype','export_dtype','native_bytes')},'native geometry '+name)
        if name in pins['prior18_expectations']:
            R.need(R.same(actual,pins['prior18_expectations'][name]), 'fresh prior18 exact reproduction '+name)
        if not bootstrap:
            R.need(R.same(actual,{k:spec[k] for k in actual}), 'frozen29 exact metadata/hash mismatch '+name)
        records[name] = {**actual,'file':name+'.f32le'}
        raw_outputs[name] = data
    R.need(records['cache_k']['sha256'] == records['k']['sha256'], 'cold cache_k alias equality')
    R.need(records['cache_v']['token_major_sha256'] == records['v']['sha256'], 'cold cache_v fixed layout equality')
    R.need(records['pv']['token_major_sha256'] == records['att']['sha256'], 'PV->att fixed layout equality')
    R.need(records['mask']['sha256'] == pins['mask_contract']['export_sha256'], 'exact exported mask')
    for name in ('softmax_fp32','prob'):
        raw = raw_outputs[name]
        for head in range(12):
            for query in range(128):
                start = ((head*128+query)*128+query+1)*4
                end = ((head*128+query+1)*128)*4
                R.need(raw[start:end] == b'\0'*(end-start), 'future reference probability +0')
    # These are validation-only relations, never fed into the original execution.
    R.need(torch.equal(outputs['r'],outputs['x']+outputs['o']), 'observed BF16 residual relation')
    R.need(torch.equal(outputs['act'],outputs['silu']*outputs['up']), 'observed BF16 product relation')
    R.need(torch.equal(outputs['y'],outputs['r']+outputs['down']), 'observed BF16 final residual relation')
    R.need(float(torch.max(torch.abs(outputs['softmax_fp32'].sum(dim=-1)-1))) <= 2e-5, 'softmax row-sum semantic check')
    runtime = {'python':sys.version,'python_major_minor':list(sys.version_info[:2]),
        'implementation':sys.implementation.name,'torch':str(torch.__version__),'numpy':np.__version__,
        'torch_commit':torch.version.git_version,'capability':torch.backends.cpu.get_cpu_capability(),
        'torch_build_sha256':R.sha(torch.__config__.show().encode()),'threads':torch.get_num_threads(),
        'interop_threads':torch.get_num_interop_threads(),'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
        'environment':{k:os.getenv(k) for k in pins['capture_environment']},'affinity':sorted(os.sched_getaffinity(0)),
        'native_files':native_identity()}
    after = boundary()
    R.need(R.same(before,after), 'source/raw/runtime changed; no completion manifest')
    result = {'status':'BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' if bootstrap else 'FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY',
        'stage':stage,'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'outputs':records,'runtime':runtime,'recipe':before['recipe'],'source_pins_sha256':R.PINS_SHA256,
        'boundary':{'unchanged':True,'before_sha256':R.sha(R.encoded(before)),'after_sha256':R.sha(R.encoded(after))},
        'official_model_ast_nodes':38,'official_activation_ast_nodes':14,'official_ast_subset_executed':True,
        'full_official_forward_executed':False,'dynamic_cache_executed':False,'transformers_imported':False,
        'cold_cache_semantics':'cold semantic aliases; DynamicCache not executed',
        'rotary_cache_max_position_embeddings':256,'original_config_max_position_embeddings':32768,
        'configuration_equivalence_claimed':False,'actual_or_typed_input_read':False,
        'materialized_producer_payload_read':False,'saved_reference_payload_read':False,
        'numerical_acceptance_claimed':False,'old_pass_inherited':False,'full_29_node_acceptance':False,
        'hook_records':hook_records,'hook_order':hook_order,'softmax_calls':len(softmax_returns),
        'prior18_fresh_hash_matches':True,'frozen29_hash_matches':None if bootstrap else True}
    files = {name+'.f32le':data for name,data in raw_outputs.items()}
    files['mask.bf16le'] = mask_raw
    R.need(sum(map(len,files.values())) == pins['budget']['payload_bytes_per_capture'], 'exact capture payload bytes')
    files['BOUNDARY_BEFORE.json'],files['BOUNDARY_AFTER.json'] = R.encoded(before),R.encoded(after)
    manifest_name = 'BOOTSTRAP_REFERENCE.json' if bootstrap else 'REFERENCE.json'
    files[manifest_name] = R.encoded(result)
    R.need(sum(map(len,files.values())) <= pins['budget']['per_capture_cap_bytes'], 'per-capture cap')
    # Budget covers only this run's bootstrap/frozen pair and bounded review metadata.
    existing = sum(p.stat().st_size for p in out.parent.rglob('*') if p.is_file()) if out.parent.exists() else 0
    R.need(existing+sum(map(len,files.values())) <= pins['budget']['total_cap_bytes'], '69 MiB pair cap')
    out.mkdir(parents=True,exist_ok=False)
    # Completion manifest last; any failed write leaves an unsealed diagnostic directory.
    for name,data in files.items():
        if name != manifest_name:
            with (out/name).open('xb') as stream:
                stream.write(data)
    with (out/manifest_name).open('xb') as stream:
        stream.write(files[manifest_name])
    return result
