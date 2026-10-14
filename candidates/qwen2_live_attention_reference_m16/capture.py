"""Optional numerical runtime, imported only for explicitly requested fresh capture."""
from __future__ import annotations
import ast
import copy
import math
import os
from pathlib import Path
import sys


def capture(root,pins,subset,inputs,out,*,bootstrap=False,recipe):
    R=recipe
    R.need(not out.exists(),'fresh output required')
    R.need(bootstrap==(pins['reference_freeze']['status']=='BOOTSTRAP_UNACCEPTED'),'capture/freeze mode mismatch')
    if not bootstrap: R.require_frozen_references(pins)
    R.need('torch' not in sys.modules and 'numpy' not in sys.modules,'fresh process without Torch/NumPy required')
    R.need(sys.gettrace() is None,'refuse existing Python tracer')
    paths=[R.P.stage_path(root,p) for p in (subset,inputs)]
    before=R.boundary_snapshot(root,pins,paths,native=True)
    values,subset_sha,inputs_sha=R.read_inputs(root,pins,subset,inputs)
    nodes=R.official_nodes(root,pins)
    expected=pins['runtime_requirements']
    R.need(list(sys.version_info[:2])==expected['python_major_minor'],'Python version drift')
    R.need({k:os.getenv(k) for k in pins['capture_environment']}==pins['capture_environment'],
           'explicit pinned capture environment required; no implicit runtime overrides')
    R.start_output(out)
    R.write_new(out/'BOUNDARY_BEFORE.json',R.json_bytes(before))
    import numpy as np
    import torch
    from torch import nn
    R.need(np.__version__==expected['numpy'] and str(torch.__version__)==expected['torch'] and
           torch.version.git_version==expected['torch_commit'],'runtime version drift')
    R.need(torch.backends.cpu.get_cpu_capability()==expected['capability'],'CPU dispatch drift')
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    namespace={'torch':torch,'nn':nn,'math':math}

    def execute(part):
        # Only whole pinned nodes are compiled; no AST substitutions or formulas.
        code=compile(ast.fix_missing_locations(ast.Module(body=copy.deepcopy(part),type_ignores=[])),
                     str(root/R.MODEL_SOURCE),'exec')
        exec(code,namespace)

    execute(nodes[:4])
    execute(nodes[15:16])
    specs={s['local_name']:s for s in pins['tensors']}

    def tensor(name):
        return torch.from_numpy(np.frombuffer(values[name],dtype='<u2').copy()).view(
            torch.bfloat16).reshape(specs[name]['shape'])

    x=tensor('embed_tokens.rows_0_255')[:R.ROWS].unsqueeze(0).contiguous()
    norm=namespace['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
    norm.weight=nn.Parameter(tensor('input_layernorm.weight'),requires_grad=False)
    holder=nn.Module()
    holder.hidden_size,holder.num_heads=1536,12
    holder.num_key_value_heads,holder.head_dim=2,128
    holder.num_key_value_groups,holder.attention_dropout=6,0.0
    namespace['self']=holder
    execute(nodes[4:7])
    for letter in 'qkv':
        layer=getattr(holder,letter+'_proj')
        layer.weight=nn.Parameter(tensor('self_attn.'+letter+'_proj.weight'),requires_grad=False)
        layer.bias=nn.Parameter(tensor('self_attn.'+letter+'_proj.bias'),requires_grad=False)
    holder.rotary_emb=namespace['Qwen2RotaryEmbedding'](128,max_position_embeddings=256,base=1e6).to(torch.bfloat16)
    holder.eval()
    mask_raw=R.mask_bytes()
    mask_verification=R.verify_mask(mask_raw,pins)
    mask=torch.from_numpy(np.frombuffer(mask_raw,dtype='<u2').copy()).view(torch.bfloat16).reshape(1,1,R.ROWS,R.ROWS)
    outputs={}
    softmax_returns=[]
    softmax_code=nn.functional.softmax.__code__

    def trace(frame,event,arg):
        if frame.f_code is softmax_code:
            if event=='return': softmax_returns.append(arg.detach())
            return trace
        return None

    def attention_pre_projection(attention_mask):
        # Wrapper call parameter, explicitly not a Transformers mask-helper result.
        namespace['attention_mask']=attention_mask
        execute(nodes[16:18])
        outputs.update(repeat_k=namespace['key_states'],repeat_v=namespace['value_states'],mask=attention_mask)
        execute(nodes[18:20])
        outputs['scores']=namespace['attn_weights']
        execute(nodes[20:21])
        outputs['logits']=namespace['attn_weights']
        # The ORIGINAL line300 expression executes unchanged. Observe the FP32
        # return from its actual softmax call, before original .to(BF16).
        try:
            sys.settrace(trace)
            execute(nodes[21:22])
        finally:
            sys.settrace(None)
        R.need(len(softmax_returns)==1,'exactly one original softmax return required')
        outputs['softmax_fp32']=softmax_returns[0]
        execute(nodes[22:23])
        outputs['prob']=namespace['attn_weights']
        execute(nodes[23:25])
        outputs['pv']=namespace['attn_output']
        execute(nodes[25:27])
        outputs['att']=namespace['attn_output']

    with torch.inference_mode():
        n0=norm(x)
        namespace['hidden_states']=n0
        execute(nodes[7:10])
        outputs.update(x=x,n0=n0,qr=namespace['query_states'],kr=namespace['key_states'],v=namespace['value_states'])
        namespace.update(bsz=1,q_len=R.ROWS,kv_seq_len=R.ROWS,
                         position_ids=torch.arange(R.ROWS,dtype=torch.long).unsqueeze(0))
        execute(nodes[10:13]);execute(nodes[13:15])
        outputs.update(q=namespace['query_states'],k=namespace['key_states'],cos=namespace['cos'],sin=namespace['sin'])
        attention_pre_projection(attention_mask=mask)
    R.exact_keys(outputs,pins['references'],'captured output inventory')
    records,raw_outputs={},{}
    for name,value in outputs.items():
        spec=pins['references'][name]
        dtype=torch.float32 if name=='softmax_fp32' else torch.bfloat16
        R.need(value.dtype==dtype and bool(torch.isfinite(value).all()),'finite native dtype required: '+name)
        data=value.float().contiguous().numpy().astype('<f4',copy=False).tobytes()
        native=value.contiguous().view(torch.uint8).numpy().tobytes()
        actual={'shape':list(value.shape),'bytes':len(data),'native_dtype':str(value.dtype),
                'export_dtype':spec['export_dtype'],'sha256':R.sha(data),
                'token_major_sha256':R.sha(R.token_bytes(name,data,list(value.shape))),
                'native_bytes':len(native),'native_sha256':R.sha(native),
                'native_stride':list(value.stride()),'storage_offset':value.storage_offset(),
                'is_contiguous':value.is_contiguous()}
        R.fields(actual,{k:spec[k] for k in ('shape','bytes','native_dtype','export_dtype','native_bytes','storage_offset')},name+' geometry')
        if name in pins['prefix_references']:
            R.fields(actual,pins['prefix_references'][name],'fresh prefix reproduction '+name)
        if not bootstrap: R.need(R.same(actual,spec),'frozen Attention reference drift: '+name)
        records[name]={**actual,'file':name+'.f32le'};raw_outputs[name]=data
    R.verify_mask(raw_outputs['mask'],pins,exported=True)
    R.need(records['mask']['native_sha256']==pins['mask_contract']['native_sha256'],'native BF16 mask identity')
    R.need(R.token_bytes('pv',raw_outputs['pv'],records['pv']['shape'])==raw_outputs['att'],'fixed PV to att layout identity')
    # Future probability zeros follow from the explicit mask; they are reference
    # facts only and never authorize synthetic DUT future-position observations.
    for name in ('softmax_fp32','prob'):
        raw=raw_outputs[name]
        for h in range(12):
            for q in range(R.ROWS):
                start=((h*R.ROWS+q)*R.ROWS+q+1)*4;end=((h*R.ROWS+q+1)*R.ROWS)*4
                R.need(raw[start:end]==b'\0'*(end-start),'future reference probability must be +0')
    runtime={'python_major_minor':list(sys.version_info[:2]),'python':sys.version,
        'numpy':np.__version__,'torch':str(torch.__version__),'torch_commit':torch.version.git_version,
        'capability':torch.backends.cpu.get_cpu_capability(),'threads':torch.get_num_threads(),
        'interop_threads':torch.get_num_interop_threads(),
        'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
        'torch_build':torch.__config__.show(),'torch_build_sha256':R.sha(torch.__config__.show().encode()),
        'affinity':sorted(os.sched_getaffinity(0)),
        'environment':{k:os.getenv(k) for k in pins['capture_environment']},
        'new_process':True,'historical_runtime_equivalence_claimed':False}
    libraries={'python':Path(sys.executable).resolve(),'torch_C':Path(torch._C.__file__),
               'numpy_multiarray':Path(np._core._multiarray_umath.__file__)}
    for name in ('libtorch_cpu.so','libc10.so','libtorch_python.so'):
        libraries[name]=Path(torch.__file__).parent/'lib'/name
    runtime['native_files']={name:{'path':str(path.resolve()),'bytes':path.stat().st_size,
                                  'sha256':R.sha(path.read_bytes())} for name,path in libraries.items()}
    runtime['identity_scope']=R.P.RUNTIME_IDENTITY_SCOPE
    R.check_runtime(runtime,pins)
    R.need('transformers' not in sys.modules,'Transformers import forbidden in bounded AST capture')
    for name,data in raw_outputs.items(): R.write_new(out/(name+'.f32le'),data)
    R.write_new(out/'mask.bf16le',mask_raw)
    boundary=R.finish_boundary(root,pins,paths,before,out,native=True)
    stage='bootstrap-capture' if bootstrap else 'capture'
    result=R.report(root,pins,stage)
    result.update(status='BOOTSTRAP_UNACCEPTED_NO_NUMERICAL_VERDICT' if bootstrap else 'FRESH_OFFICIAL_AST_ATTENTION_CAPTURE_ONLY',
        subset=subset,inputs=inputs,subset_manifest_sha256=subset_sha,input_ready_sha256=inputs_sha,
        official_ast_nodes=pins['official_ast_nodes'],outputs=records,runtime=runtime,
        official_ast_subset_executed=True,full_official_forward_executed=False,transformers_imported=False,
        posthoc_oracle_only=True,numerical_acceptance_claimed=False,old_pass_inherited=False,
        actual_or_typed_input_read=False,prefix_saved_reference_read=False,
        cold_cache_semantics='past=0; current K/V only; no Cache implementation executed',
        mask_contract=pins['mask_contract'],mask_verification=mask_verification,
        softmax_observation=pins['softmax_observation'],rotary_cache_max_position_embeddings=256,
        original_config_max_position_embeddings=32768,configuration_equivalence_claimed=False,
        layout_rule=pins['layout_rule'],reference_freeze=pins['reference_freeze'],
        reference_hash_comparison=None if bootstrap else R.expected_comparison(pins),
        prefix9_reproduction=R.prefix_comparison(pins),boundary=boundary)
    R.write_new(out/R.STAGES[stage],R.json_bytes(result))
    return result
