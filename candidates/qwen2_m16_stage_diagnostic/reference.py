"""Fresh M16 original-AST reference, only after independently sealed actuals.

No formal reference contract is issued. Geometry/mask are explicit wrapper
arguments. All 38 selected model and 14 activation AST nodes remain unchanged;
MLP is the original whole expression. No prior M128 result is an oracle operand.
"""
import argparse,ast,collections,copy,hashlib,json,math,resource,signal,sys,time,traceback,types
from pathlib import Path
from . import common as c,geometry as g,inputs as inp
from .stage_log import StageLog,COUNTER_LIMITS,safe_last

EXPECTED_RUNTIME=dict(torch='2.10.0+cpu',commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
 numpy='2.3.5',capability='AVX2',threads=4,interop_threads=1,mkldnn_enabled=False,deterministic=True)

def validate_model_record(r):
    g.need(r['status']=='M16_MODEL_COMPLETE_COST_DIAGNOSTIC' and r['scope']=='M16_PUBLIC21_STAGE_COST_DIAGNOSTIC' and
      r['logical_rows']==16 and r['physical_matrix_rows']==128,'completed same-scope M16 model required')
    for key in ('model_completed','actual_outputs_sealed','whole_block_terminal','finalfence','source_post_verified','input_post_verified','native_post_verified'):
        g.need(r[key] is True,'incomplete model seal')
    for key in ('formal_reference_contract','fullblock_pass','reference_executed','old_wrapper_optimizations_loaded'):
        g.need(r[key] is False,'model isolation/scope')
    h=r['execution']['host'];a=h['accepted'];t=h['launch_result']
    g.need(t['status'] is None and t['completed']==21 and t['jobs']==17 and
      a['completion_fire']==21 and a['request_fire']==a['owner_result_fire']==17 and a['result_fire']==1,'genuine complete public21 terminal')
    g.need(r['backend_debts'] and not any(r['backend_debts'].values()),'no sealed backend debt')
    g.need(r['native_before']==r['native_after'] and r['artifact_before']==r['artifact_after'],'native identity pre/post')
    g.need(r['final_counters']['completed']==21 and r['final_counters']['jobs']==17 and r['final_counters']['accepted_results']==1,'final live counters')
    return True

def observation_shapes():
    shapes={n:(12,16,16) for n in ('unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16')}
    shapes.update(dot_parts=(12,16,16,16),normalizer=(12,16,3),pv_raw=(12,16,128),pv_bf16=(12,16,128))
    return shapes

def validate_inventory(r):
    from candidates.qwen2_exact64_diagnostic_fullblock.retention import ACTUAL_NAMES
    inventory=r['local_retention']['inventory'];obs=r['observation'];shapes=observation_shapes()
    expected={'actual_'+n+'.f32le' for n in ACTUAL_NAMES|{'silu'}}|{'attention_observation/summary.json'}
    expected|={'attention_observation/'+n+suffix for n in shapes for suffix in ('.u32le','.presence','.count.u16le')}
    g.need(set(inventory)==expected and len(expected)==51,'complete exact actual/observer inventory')
    receipt=r['local_retention']
    g.need(receipt['schema']==1 and receipt['scope']=='DIAGNOSTIC_SOFTWARE_OWNER' and
      receipt['status']=='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE' and receipt['local_only'] is True and receipt['upload_authorized'] is False and
      receipt['oracle_payloads_read'] is False and receipt['reference_operands_in_execution'] is False,'local actual retention scope')
    g.need(obs['schema']=='qwen2-pv32-readonly-observation-v1' and obs['status']=='COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED' and
      obs['observer_error'] is None and obs['probability_repeats']==4 and obs['causal_only'] is True and obs['future_scores_observed'] is False and
      obs['job']['m']==16 and obs['terminal']['status'] is None and obs['terminal']['write_bytes']==98304 and
      set(obs['fields'])==set(shapes),'actual complete M16 observation')
    for name in ACTUAL_NAMES|{'silu'}:
        width=8960 if name in ('gate','up','silu','act') else 256 if name in ('kraw','kr','k','vraw','v') else 512 if name=='kv' else 1536
        g.need(inventory['actual_'+name+'.f32le']['bytes']==16*width*4,'actual M16 payload extent')
    for name,shape in shapes.items():
        words=math.prod(shape);observed=576 if name=='normalizer' else 24576 if name.startswith('pv_') else g.CAUSAL*(16 if name=='dot_parts' else 1)
        writes=4*g.CAUSAL if name in ('softmax_fp32','prob_bf16') else 12*g.CAUSAL if name=='normalizer' else observed
        f=obs['fields'][name]
        g.need(tuple(f['shape'])==shape and f['words']==words and f['observed_words']==observed and f['writes']==writes,'full M16 observed coverage metadata')
        for suffix,mult,key in (('.u32le',4,'raw_sha256'),('.presence',1,'presence_sha256'),('.count.u16le',2,'frequency_sha256')):
            spec=inventory['attention_observation/'+name+suffix]
            g.need(spec['bytes']==words*mult and spec['sha256']==f[key],'observation metadata/inventory equality')
    return True

def recheck_saved_coverage(model):
    from array import array
    from candidates.qwen2_attention_resident_candidate.observation import ResidentAttentionObservation
    fields={}
    for name,shape in observation_shapes().items():
        prefix=model/'attention_observation'/name
        words=array('I');words.frombytes(prefix.with_suffix('.u32le').read_bytes())
        frequency=array('H');frequency.frombytes(prefix.with_suffix('.count.u16le').read_bytes())
        fields[name]=dict(words=words,frequency=frequency,observed=prefix.with_suffix('.presence').read_bytes())
    g.need(ResidentAttentionObservation._coverage(types.SimpleNamespace(job={'m':16},fields=fields)),'original PV32 full stored coverage/frequency/sentinel check')

def model_seal(model,sources,native,artifact,input_records):
    from candidates.qwen2_exact64_diagnostic_fullblock import retention
    model=Path(model).absolute();g.need(model==c.BASE/'cost01/model' and model.resolve()==model,'fixed same-run model path')
    path=model/'RESULT.json';digest=inp.sha(path);r=json.loads(path.read_text());validate_model_record(r)
    g.need(r['sources']==sources and json.loads((model/'SOURCES_BEFORE.json').read_text())==sources,'actual execution source identity')
    g.need(r['native_after']==native and r['artifact_after']==artifact and r['input_records']==input_records,'actual execution input/native identity')
    validate_inventory(r)
    g.need(retention.verify(model,r['local_retention']),'all actual and observation payload identities')
    g.need(json.loads((model/'attention_observation/summary.json').read_text())==r['observation'],'same actual observer summary')
    recheck_saved_coverage(model)
    for name,spec in r['sealed_actual_outputs'].items():
        g.need(r['local_retention']['inventory']['actual_'+name+'.f32le']==spec,'actual seal/inventory correspondence')
    g.need(set(r['sealed_actual_outputs'])==retention.ACTUAL_NAMES|{'silu'},'complete actual inventory')
    g.exact_totals(r['exact64_projections'])
    return r,digest

def capture(R,pins,values,native):
    import numpy as np
    g.need('torch' not in sys.modules and sys.gettrace() is None,'fresh Torch process/no existing tracer')
    import torch
    from torch import nn
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def state():return dict(torch=str(torch.__version__),commit=torch.version.git_version,numpy=np.__version__,
      capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),
      mkldnn_enabled=torch.backends.mkldnn.enabled,deterministic=torch.are_deterministic_algorithms_enabled())
    g.need(state()==EXPECTED_RUNTIME,'fixed local AVX2 official runtime')
    g.need(Path(torch._C.__file__).resolve()==Path(native['torch_C']['path']) and
      Path(np._core._multiarray_umath.__file__).resolve()==Path(native['numpy_multiarray']['path']),'loaded pinned native paths')
    from candidates.qwen2_fullblock_ci_execution.runtime_profile import AVX2_BUILD_SHA256
    build=torch.__config__.show()
    g.need(hashlib.sha256(build.encode()).hexdigest()==AVX2_BUILD_SHA256,'published local AVX2 build identity')
    g.need(build.count('CPU capability usage: AVX2')==1 and hashlib.sha256(build.replace('CPU capability usage: AVX2','CPU capability usage: AVX512').encode()).hexdigest()==pins['runtime_requirements']['torch_build_sha256'],'only declared build capability difference')
    root=c.ROOT
    nodes=R.official_nodes(root,pins['model_ast_nodes'],R.MODEL_SOURCE,pins['sources'])
    activations=R.official_nodes(root,pins['activation_ast_nodes'],R.ACTIVATION_SOURCE,pins['sources'])
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

    x = tensor('embed_tokens.rows_0_255')[:16].unsqueeze(0).contiguous()
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
    # Bind every learnable parameter to its original raw identity before forward.
    bindings = {'norm.weight':(norm.weight,'input_layernorm.weight'),
        'decoder.post_attention_layernorm.weight':(decoder.post_attention_layernorm.weight,'post_attention_layernorm.weight')}
    for letter in 'qkv':
        for field in ('weight','bias'):
            bindings['attention.'+letter+'_proj.'+field] = (getattr(getattr(attention,letter+'_proj'),field),
                                                          'self_attn.'+letter+'_proj.'+field)
    bindings['attention.o_proj.weight'] = (attention.o_proj.weight,'self_attn.o_proj.weight')
    for name in ('gate','up','down'):
        bindings['decoder.mlp.'+name+'_proj.weight'] = (getattr(decoder.mlp,name+'_proj').weight,'mlp.'+name+'_proj.weight')
    actual_parameters = {prefix+'.'+name:value for prefix,module in [('norm',norm),('attention',attention),('decoder',decoder)]
                         for name,value in module.named_parameters()}
    R.exact_keys(actual_parameters,bindings,'all12 fixed parameter bindings')
    for key,(parameter,raw_name) in bindings.items():
        R.need(actual_parameters[key] is parameter and list(parameter.shape) == specs[raw_name]['shape'] and
               R.sha(parameter.detach().contiguous().view(torch.uint8).numpy().tobytes()) == specs[raw_name]['sha256'],
               'direct original BF16 parameter identity: '+key)
    # Explicit cold mask wrapper argument, not a claim of mask-helper execution.
    mask_raw = b''.join((0xff7f if k > q else 0).to_bytes(2,'little')
                        for q in range(16) for k in range(16))
    R.need(len(mask_raw)==512, 'exact M16 finite BF16 mask words')
    mask = torch.from_numpy(np.frombuffer(mask_raw,dtype='<u2').copy()).view(torch.bfloat16).reshape(1,1,16,16)
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
        namespace.update(bsz=1,q_len=16,kv_seq_len=16,
                         position_ids=torch.arange(16,dtype=torch.long).unsqueeze(0))
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
    g.need(set(outputs)==R.NAMES and 'transformers' not in sys.modules,'actual 29 observations, no alternate model')
    arrays={}
    for name,value in outputs.items():
        g.need(value.dtype==(torch.float32 if name=='softmax_fp32' else torch.bfloat16) and bool(torch.isfinite(value).all()),'native finite observed dtype')
        arrays[name]=value.float().contiguous().numpy().astype('<f4',copy=True)
    g.need(torch.equal(outputs['r'],outputs['x']+outputs['o']) and torch.equal(outputs['act'],outputs['silu']*outputs['up']) and
      torch.equal(outputs['y'],outputs['r']+outputs['down']),'original BF16 residual/product relations')
    from scripts import qwen2_layer0_model_gate as gate
    config=dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2)
    g.need({n:list(v.shape) for n,v in arrays.items()}==gate.expected_shapes(config,16,0),'all29 actual M16 shapes')
    semantics=gate.audit_semantics(arrays,None,config,'bf16');g.need(all(semantics.values()),'original semantic audit actual M16')
    future=np.broadcast_to(np.triu(np.ones((16,16),dtype=bool),k=1),(1,12,16,16))
    g.need(all(np.all(arrays[n].view('<u4')[future]==0) for n in ('softmax_fp32','prob')),'future native probability positive zero')
    g.need(state()==EXPECTED_RUNTIME,'runtime state unchanged')
    return arrays,dict(profile=state(),model_ast_nodes=len(nodes),activation_ast_nodes=len(activations),
      official_ast_subset_executed=True,full_official_forward_executed=False,dynamic_cache_executed=False,
      finite_bf16_mask=True,rotary_max_position_embeddings=256,original_max_position_embeddings=32768,
      configuration_equivalence_claimed=False,formal_reference_contract=False,prior_m128_bitexact_assumed=False,hook_order=hook_order,semantics=semantics)

def validate_input_relation(values,raw,pins,oracle,gate):
    import numpy as np
    specs={s['local_name']:s for s in pins['raw_tensors']}
    def f32(name):return (np.frombuffer(raw[name],'<u2').astype('<u4')<<16).view('<f4').reshape(specs[name]['shape'])
    g.need(f32('embed_tokens.rows_0_255')[:16].tobytes()==values['x'],'original raw leading16 == model x')
    names={'gamma0':'input_layernorm.weight','gamma1':'post_attention_layernorm.weight',
      **{'b'+v:'self_attn.'+v+'_proj.bias' for v in 'qkv'}}
    for role,name in names.items():g.need(f32(name).tobytes()==values[role],'raw scalar parameter matches model')
    names={**{'w'+v:'self_attn.'+v+'_proj.weight' for v in 'qkvo'},'wg':'mlp.gate_proj.weight','wu':'mlp.up_proj.weight','wd':'mlp.down_proj.weight'}
    for role,name in names.items():
        g.need(np.frombuffer(raw[name],'<u2').reshape(specs[name]['shape']).T.copy().tobytes()==values[role],'raw weight transpose matches model')
    rope=np.frombuffer(values['rope'],'<f4').reshape(2,1024,64)
    for i,name in enumerate(('cos','sin')):
        expected=gate.bf16(np.concatenate((rope[i,:16],rope[i,:16]),axis=-1))
        g.need(expected.tobytes()==oracle[name].tobytes(),'full physical rope first16 matches actual M16 official rotary')

def compare_actuals(model,r,oracle,gate):
    import numpy as np
    policy=gate.load_policy(c.ROOT);result={}
    def add(name,a,b):
        metrics=gate.compare(np.asarray(a).reshape(-1),np.asarray(b).reshape(-1))
        result[name]=dict(metrics=metrics,verdict=gate.stage_verdict(name,metrics,'bf16',policy))
    def actual(name):return np.frombuffer((model/('actual_'+name+'.f32le')).read_bytes(),'<f4')
    for name in ('n0','qr','kr','v','o','r','n1','gate','up','silu','act','down','y'):
        add(name,actual(name),oracle[name])
    for name in ('q','k'):add(name,actual(name),oracle[name].transpose(0,2,1,3).copy())
    causal=np.broadcast_to(np.tril(np.ones((16,16),dtype=bool)),(12,16,16))
    obs=model/'attention_observation'
    def field(name):return np.frombuffer((obs/(name+'.u32le')).read_bytes(),'<f4')
    for name,fieldname in (('scores','scores_bf16'),('logits','scores_bf16'),('prob','prob_bf16'),('softmax_fp32','softmax_fp32')):
        observed=field(fieldname).reshape(12,16,16)
        presence=np.frombuffer((obs/(fieldname+'.presence')).read_bytes(),'u1').reshape(12,16,16)
        g.need(np.array_equal(presence.astype(bool),causal),'exact causal observation presence')
        add(name,observed[causal],oracle[name].reshape(12,16,16)[causal])
        g.need(result[name]['metrics']['elements']==g.CAUSAL,'complete causal coverage')
    add('pv',field('pv_bf16'),oracle['pv']);add('att',actual('att'),oracle['att'])
    kv=actual('kv');g.need(kv.tobytes()==actual('k').tobytes()+actual('v').tobytes(),'same-live KV exact copy')
    for name,a in (('cache_k',kv[:16*256]),('cache_v',kv[16*256:])):
        add(name,a,oracle[name].transpose(0,2,1,3).copy())
    soft=field('softmax_fp32').reshape(12,16,16)
    sums=np.where(causal,soft,0).sum(axis=-1,dtype=np.float32)
    soft_error=float(np.max(np.abs(sums-1)))
    g.need(len(result)==23,'fixed complete M16 comparison inventory')
    return dict(policy=policy,stages=result,causal_positions=g.CAUSAL,softmax_sum_error=soft_error,
      softmax_sum_pass=soft_error<=2e-5,numerical_pass=all(v['verdict']['passed'] is not False for v in result.values()) and soft_error<=2e-5,
      scores_logits_same_actual_field=True,formal_reference_contract=False,fullblock_pass=False,
      comparison_scope='ACTUAL_M16_GEOMETRY_DIAGNOSTIC_ORIGINAL_BUDGETS')

def run(out,model):
    c.limits(60,85);start=time.monotonic();cpu=time.process_time();out=c.fresh_output(out,'reference')
    report=dict(status='STARTED',scope='M16_POSTSEAL_REFERENCE_DIAGNOSTIC',fullblock_pass=False,formal_reference_contract=False)
    log=StageLog(out/'STAGES.jsonl',g.LIMITS_REFERENCE);counters={n:0 for n in COUNTER_LIMITS}
    log.begin('REFERENCE',counters=counters)
    try:
        pins,native=c.check_environment();d=c.dependencies();sources=c.require_freeze();c.snapshot_sources(out,sources)
        _,_,artifact=c.artifacts();values,input_records=inp.load_inputs()
        r,model_sha=model_seal(model,sources,native,artifact,input_records);model=Path(model);counters=r['final_counters']
        g.need(r['framework_sources']==c.runtime_python(pins),'same pinned framework Python sources')
        raw=inp.raw13(pins)
        oracle,capture_info=capture(d['recipe'],pins,raw,native)
        validate_input_relation(values,raw,pins,oracle,d['qwen2_layer0_model_gate'])
        log.transition('POSTSEAL_COMPARISON',counters=counters)
        comparison=compare_actuals(model,r,oracle,d['qwen2_layer0_model_gate'])
        inventory={}
        for name,value in oracle.items():
            data=value.tobytes();(out/(name+'.f32le')).write_bytes(data)
            inventory[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),shape=list(value.shape))
        log.transition('FINAL_SEAL',counters=counters)
        _,native_after=c.check_environment();_,_,artifact_after=c.artifacts();_,input_after=inp.load_inputs()
        g.need(native==native_after and artifact==artifact_after and input_records==input_after and sources==c.require_freeze(),'post reference source/input/native unchanged')
        g.need(all(hashlib.sha256(data).hexdigest()==next(s['sha256'] for s in pins['raw_tensors'] if s['local_name']==name) for name,data in inp.raw13(pins).items()),'post raw identity')
        _,after_sha=model_seal(model,sources,native,artifact,input_records);g.need(after_sha==model_sha,'sealed model unchanged')
        report.update(status='M16_DIAGNOSTIC_COMPARISON_COMPLETE',sources=sources,model_result_sha256=model_sha,
          input_records=input_records,native_before=native,native_after=native_after,artifact_before=artifact,artifact_after=artifact_after,
          capture=capture_info,outputs=inventory,comparison=comparison,source_post_verified=True,framework_sources=c.runtime_python(pins),
          host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-start,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        log.finish(counters=counters);report['safe_last_stage']=safe_last(out/'STAGES.jsonl');c.save(out/'RESULT.json',report)
        print(json.dumps(dict(status=report['status'],numerical_pass=comparison['numerical_pass'],formal_reference_contract=False)));return 0
    except BaseException as e:
        original=traceback.format_exc()
        try:
            if log.active:log.failure(log.active[0],'TIMEOUT' if isinstance(e,TimeoutError) else 'VALIDATION' if isinstance(e,ValueError) else 'INTERNAL',counters=counters)
        except BaseException:pass
        report.update(status='M16_REFERENCE_FAILED',error_type=type(e).__name__,error=str(e),traceback=original,host_cpu_seconds=time.process_time()-cpu,host_wall_seconds=time.monotonic()-start)
        try:report['safe_last_stage']=safe_last(out/'STAGES.jsonl');c.save(out/'RESULT.json',report)
        except BaseException:pass
        print(json.dumps(dict(status='M16_REFERENCE_FAILED')));return 1
    finally:signal.setitimer(signal.ITIMER_REAL,0)

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--out');ap.add_argument('--model');a=ap.parse_args(argv)
    if not a.execute:g.need(a.out is None and a.model is None,'execution args require execute');print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    g.need(a.out is not None and a.model is not None,'fixed reference args');return run(a.out,a.model)
if __name__=='__main__':raise SystemExit(main())
