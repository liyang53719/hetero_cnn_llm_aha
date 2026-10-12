"""Read-only capture audit; only writes its own receipt. No model imports/forwards."""
import datetime, hashlib, json, math, pathlib, subprocess
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
B = ROOT / 'work/qwen2_official_public21_20261012'
RUN = B / 'actual_m128_02'
SNAP = B / 'snapshot_m128_02'
OUT = B / 'published_capture_audit'
OUT.mkdir(parents=True,exist_ok=True)
checks = []
def sha(raw): return hashlib.sha256(raw).hexdigest()
def fsha(path):
    with pathlib.Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def read(path): return json.loads(pathlib.Path(path).read_text())
def check(ok, label):
    checks.append(label)
    if not bool(ok): raise AssertionError(label)
def filecheck(path, digest, size=None):
    check(fsha(path) == digest, 'SHA256 ' + str(path.relative_to(ROOT) if pathlib.Path(path).is_relative_to(ROOT) else path))
    if size is not None: check(path.stat().st_size == size, 'length ' + str(path.name))
def f32(path): return np.fromfile(path, dtype='<f4')
def bf16_words(raw): return (np.frombuffer(raw,dtype='<u2').astype('<u4') << 16).tobytes()
def comparison(a,b,claimed,label):
    a=np.ascontiguousarray(a,dtype='<f4');b=np.ascontiguousarray(b,dtype='<f4')
    check(a.shape==b.shape and a.size>0 and np.isfinite(a).all() and np.isfinite(b).all(),label+' shape/finite')
    err=np.abs(a.astype(np.float64)-b.astype(np.float64))
    different=np.flatnonzero(a.ravel().view('<u4')!=b.ravel().view('<u4'))
    got=dict(actual_f32_sha256=sha(a.tobytes()),reference_f32_sha256=sha(b.tobytes()),
        elements=int(a.size),shape=list(a.shape),max_abs=float(err.max()),mean_abs=float(err.mean()),
        different_elements=int(different.size),bit_exact=not bool(different.size),finite=True,
        first_difference_flat=int(different[0]) if different.size else None)
    check(all(claimed[k]==v for k,v in got.items()),label+' metrics')
    return got

s=read(RUN/'summary.json'); z=read(SNAP/'SNAPSHOT.json'); obs=read(RUN/'attention_observation/summary.json')
filecheck(RUN/'summary.json','25b947ff774412685d9691de0a06f1a1cf489388557db357013bf7911c11681a')
filecheck(SNAP/'SNAPSHOT.json','5b9247588ddddcada1e669034c3e8e0a17ffb39c6c6aef3ffd1bb5e49c6924ab')
check(s['snapshot_sha256']==fsha(SNAP/'SNAPSHOT.json') and s['observation']==obs,'summary binds snapshot and observation')
check(len(s['source_sha256'])==86 and s['source_sha256']==s['source_sha256_after']==z['source_sha256'],'86 source inventories before/after/snapshot equal')
for name,digest in z['source_sha256'].items():
    filecheck(ROOT/name,digest);filecheck(SNAP/'frozen_sources'/name,digest)
check(z['source_manifest_sha256']==sha((json.dumps(z['source_sha256'],sort_keys=True,indent=2,allow_nan=False)+'\n').encode()),'source manifest digest')
for name,entry in s['sealed_actual_outputs'].items(): filecheck(RUN/f'actual_{name}.f32le',entry['sha256'],entry['bytes'])
check(len(s['sealed_actual_outputs'])==19,'19 sealed actual outputs')
filecheck(RUN/'actual_silu.f32le',s['sealed_silu_sha256'],128*8960*4)
for name,entry in z['metadata']['tables'].items():
    p=SNAP/(name+'_table.bin');filecheck(p,entry['sha256'],entry['bytes'])
    check(p.read_bytes()[:16*entry['count']]==b''.join(bytes.fromhex(h) for h in entry['record_hex']),name+' table records')
check(s['metadata']==z['metadata'] and s['binaries']==z['binaries'] and s['input_spec']==z['input_spec'],'snapshot metadata/binaries/inputs preserved')
binary=z['binaries'];filecheck(pathlib.Path(binary['library']),binary['library_sha256']);filecheck(pathlib.Path(binary['compile_receipt']),binary['compile_sha256'])
check(pathlib.Path(binary['library']).read_bytes()[:4]==b'\x7fELF','actual library ELF')
compile=read(binary['compile_receipt']);check(compile['returncode']==0 and compile['library_sha256']==binary['library_sha256'],'compile receipt success/library identity')
check([a for a in compile['argv'][1:] if a.startswith('-') and a!='-o']==['-shared','-fPIC','-O2','-ffp-contract=off','-fno-fast-math'],'strict FP compile flags')
for name,digest in compile['source_sha256'].items(): filecheck(ROOT/name,digest)
filecheck(pathlib.Path(compile['compiler']['path']),compile['compiler']['sha256'])

ref=z['reference'];RD=pathlib.Path(ref['directory']);cold=RD/'cold'
filecheck(RD/'RESULT.json',ref['top_sha256']);filecheck(cold/'RESULT.json',ref['cold_sha256'])
for name,key in [('candidate','binary_sha256'),('candidate.cpp','cpp_sha256'),('block_layout.h','header_sha256')]:filecheck(RD/'build'/name,ref['build'][key])
for name,digest in ref['source_files'].items():filecheck(ROOT/name,digest)
for entry in ref['artifacts']:filecheck(cold/entry['path'],entry['sha256'],entry['bytes'])
filecheck(RD/'rope_full.f32le',ref['inputs']['rope_table_sha256'])
raw={}
for role,entry in z['input_spec']['payloads'].items():
    p=ROOT/entry['path'];filecheck(p,entry['sha256'],entry['bytes']);raw[role]=p.read_bytes()
for p,digest in z['input_spec']['metadata_sha256'].items():filecheck(ROOT/p,digest)
arena=z['input_spec']['oracle_arena'];filecheck(ROOT/arena['path'],arena['sha256'],arena['bytes'])
inputs={role:np.frombuffer(raw[role],dtype='<u2').reshape(z['input_spec']['payloads'][role]['shape']).T.copy().tobytes() for role in ['wq','wk','wv','wo','wg','wu','wd']}
inputs.update({role:bf16_words(raw[role]) for role in ['bk','bq','bv','gamma0','gamma1']})
inputs['x']=np.frombuffer(bf16_words(raw['embeddings']),dtype='<u4').reshape(256,1536)[np.arange(128)].copy().tobytes()
trig=f32(RD/'rope_full.f32le');check(trig.size==192+5*16384,'rope raw table shape')
table=np.zeros((2,1024,64),dtype='<f4')
for i,segment in enumerate([1,2]):table[i,:128]=trig[192+segment*16384:192+(segment+1)*16384].reshape(256,64)[:128]
inputs['rope']=table.tobytes()
check(len(inputs)==14 and {k:dict(bytes=len(v),sha256=sha(v)) for k,v in inputs.items()}==s['loaded_inputs']==z['loaded_inputs'],'14 raw inputs reconstructed independently')
check(sha(inputs['x'])==ref['inputs']['input_x_sha256']==z['input_spec']['original_input']['input_x_sha256'],'raw x identity actual/reference/original')
check(ref['inputs']['past_tokens']==ref['inputs']['intermediate_preloads']==0 and ref['inputs']['position_ids']==ref['inputs']['token_ids']==list(range(128)),'cold M128 raw workload')
check(not s['prelaunch_intermediate_payloads'] and not z['prelaunch_intermediate_payloads'] and not s['old_pass_inherited'] and not ref['old_pass_inherited'],'no prelaunch intermediates or inherited PASS')

arrays={};presence={};coverage={};causal=np.broadcast_to(np.tri(128,dtype=np.uint16),(12,128,128))
for name,field in obs['fields'].items():
    stem=RUN/'attention_observation'/name; shape=tuple(field['shape']);words=math.prod(shape)
    for suffix,digest,size in [('.u32le','raw_sha256',4*words),('.presence','presence_sha256',words),('.count.u16le','frequency_sha256',2*words)]:filecheck(pathlib.Path(str(stem)+suffix),field[digest],size)
    a=np.fromfile(str(stem)+'.u32le',dtype='<u4').reshape(shape);p=np.fromfile(str(stem)+'.presence',dtype=np.uint8).reshape(shape);freq=np.fromfile(str(stem)+'.count.u16le',dtype='<u2').reshape(shape)
    if name=='normalizer':expected=np.broadcast_to((8*np.arange(1,129,dtype=np.uint16))[None,:,None],shape)
    elif name.startswith('pv_'):expected=np.ones(shape,dtype=np.uint16)
    elif name=='dot_parts':expected=np.broadcast_to(causal[:,:,:,None],shape)
    else:expected=causal*(8 if name in ('softmax_fp32','prob_bf16') else 1)
    check(np.array_equal(freq,expected) and np.array_equal(p,expected>0),name+' exact presence/frequency')
    check(np.all(a[expected==0]==0xa5963cc3),name+' absent words retain sentinel')
    check(int((p>0).sum())==field['observed_words'] and int(freq.sum())==field['writes'] and field['writes']-field['observed_words']==field['identical_repeats'],name+' observed/write/repeat totals')
    check(np.isfinite(a.view('<f4')[p>0]).all(),name+' observed values finite')
    arrays[name]=a.view('<f4');presence[name]=p.astype(bool)
    coverage[name]=dict(words=words,observed_words=field['observed_words'],absent_words=words-field['observed_words'],writes=field['writes'],raw_presence_frequency_verified=True)
check(len(arrays)==10 and not obs['future_scores_observed'],'10 fields and future absence')
check(arrays['pv_bf16'].transpose(1,0,2).copy().tobytes()==(RUN/'actual_att.f32le').read_bytes(),'observed PV bitwise equals physical attention')
check(obs['terminal']['status'] is None and obs['terminal']['tag']==obs['job']['tag'] and obs['terminal']['write_bytes']==786432,'attention successful terminal')
ret=obs['accepted_retirement'];check(ret==dict(client_retired=True,matrix_released=True,matrix_reset_required=False,memory_pending=False,poison=False,same_job=True,same_services=True,scalar_released=True,state='idle'),'attention clean retirement')

names=['n0','qr','kr','v','q','k','att','o','r','n1','gate','up','act','down','y'];fields={};fixed={}
for i,name in enumerate(names):
    shape=s['comparison']['whole_outputs'][name]['shape'];fields[name]=f32(RUN/f'actual_{name}.f32le').reshape(shape)
    fixed[name]=comparison(fields[name],f32(cold/f'raw_stages/phase_{i}_{name}_recipe.f32le').reshape(shape),s['comparison']['whole_outputs'][name],name+' fixed')
fields['q']=fields['q'].reshape(1,128,12,128).transpose(0,2,1,3);fields['k']=fields['k'].reshape(1,128,2,128).transpose(0,2,1,3)
kv=f32(RUN/'actual_kv.f32le').reshape(2,128,2,128)
fields['cache_k'],fields['cache_v']=[kv[i].transpose(1,0,2)[None] for i in range(2)]
fields['repeat_k']=np.repeat(fields['cache_k'],6,axis=1);fields['repeat_v']=np.repeat(fields['cache_v'],6,axis=1)
fields['x']=np.frombuffer(inputs['x'],dtype='<f4').reshape(1,128,1536)
for i,name in enumerate(['cos','sin']):
    w=table[i,:128].copy().view('<u4');rounded=((w+np.uint32(0x7fff)+((w>>16)&1))&np.uint32(0xffff0000)).view('<f4')
    fields[name]=np.concatenate([rounded,rounded],axis=1)
fields['silu']=f32(RUN/'actual_silu.f32le').reshape(1,128,8960)
masks={}
for name,obname in [('scores','scores_bf16'),('logits','scores_bf16'),('softmax_fp32','softmax_fp32'),('prob','prob_bf16'),('pv','pv_bf16')]:fields[name]=arrays[obname][None];masks[name]=presence[obname][None]
extra={}
for name in ['scores','logits','softmax_fp32','prob','pv','silu']:
    entry=next(e for e in ref['tensors'] if e['name']==name);a=fields[name];b=f32(cold/'tensors'/entry['path']).reshape(a.shape)
    if name in masks:a=a[masks[name]];b=b[masks[name]]
    extra[name]=comparison(a,b,s['comparison']['actual_observed_nodes'][name],name+' observed fixed')
check(len(fixed)==15 and len(extra)==6 and all(x['bit_exact'] for x in list(fixed.values())+list(extra.values())),'15 whole plus 6 observed fixed references exact')
native={}
for method,method_claim in s['comparison']['methods'].items():
    failures=[];stages={}
    for name,a in fields.items():
        b=f32(cold/'references'/method/(name+'.f32le')).reshape(a.shape)
        if name in masks:a=a[masks[name]];b=b[masks[name]]
        metrics=comparison(a,b,method_claim['stages'][name]['metrics'],method+'/'+name)
        limit=s['comparison']['thresholds']['block' if name=='y' else 'operator']
        passed=None if name=='softmax_fp32' else metrics['max_abs']<=limit['max_abs'] and metrics['mean_abs']<=limit['mean_abs']
        check(passed==method_claim['stages'][name]['verdict']['passed'],method+'/'+name+' verdict')
        if passed is False:failures.append(name);stages[name]=dict(max_abs=metrics['max_abs'],mean_abs=metrics['mean_abs'],limits=limit)
    check(failures==method_claim['failed_stages'],method+' failure list')
    native[method]=dict(status='FAIL',failed_stages=failures,failures=stages)
check(set(native['official_self_cache']['failed_stages'])=={'scores','logits'} and set(native['independent_self_cache']['failed_stages'])=={'gate','scores','logits','prob'},'preserve expected native failures')
check(all(native['official_self_cache']['failures'][n]['max_abs']==8 for n in ['scores','logits']),'official scores/logits max absolute error 8')
filecheck(ROOT/s['comparison']['thresholds']['source'],s['comparison']['thresholds']['sha256'])
check(s['comparison']['thresholds']['operator']==dict(max_abs=.03125,mean_abs=.005) and s['comparison']['thresholds']['block']==dict(max_abs=.05,mean_abs=.01),'unchanged numerical thresholds')

h=s['execution']['host'];a=h['accepted'];launch=h['launch_result']
check([c['pc'] for c in h['completions']]==list(range(21)) and [c['signal'] for c in h['completions']]==list(range(1,22)) and all(c['status'] is None for c in h['completions']),'21 successful ordered command completions')
check(a['completion_fire']==launch['completed']==21 and a['request_fire']==a['owner_result_fire']==launch['jobs']==len(h['requests'])==17 and a['result_fire']==1 and launch['status'] is None and not h['reset_required'],'17 owners and one whole terminal')
check(h['events']==list(range(22)) and all(x['tick']<y['tick'] for x,y in zip(h['completions'],h['completions'][1:])),'event coverage and monotonic completion ticks')
memory=s['execution']['memory'];physical=memory['outputs']; published={n:v for n,v in physical.items() if v['published']}
for n,v in published.items():check(v['terminal'] and v['ack_bytes']==v['written_bytes']==v['bytes'] and v['sha256']==s['sealed_actual_outputs'][n]['sha256'],'published complete ACK '+n)
check(len(published)==17 and not any(physical[n]['published'] or physical[n]['written_bytes'] or physical[n]['ack_bytes'] for n in ['gate','up','scores','probabilities']),'17 published physical outputs and four virtual reservations')
ma=memory['accepted'];workspace_traffic=s['execution']['reports'][5]['report']['physical_traffic']
check(workspace_traffic['workspace_ack_bytes']==3*physical['workspace']['ack_bytes']==2359296,'workspace cumulative ACK covers three physical sweeps')
check(ma['write_commands']==ma['write_acks']==166784 and ma['write_ack_bytes']==ma['write_data_bytes']==sum(v['ack_bytes'] for v in published.values())+workspace_traffic['workspace_ack_bytes']==15728640,'aggregate physical write ACK accounting')
reports=s['prefix_execution']['reports']+s['execution']['reports'];fences=[];terminals=[]
for item in reports:
    d=item['report'];pc=item.get('pcs',[item.get('pc')]);kind=item['kind']
    fence=d.get('final_ack_fence')
    if fence:
        check(fence['held_ticks']==5 and fence['terminal_strictly_after_final_ack'] and fence['terminal_tick']>fence['final_ack_tick'],str(pc)+' final ACK fence');fences.append(dict(pcs=pc,**fence))
    if kind=='FFN':
        c=d['coordinator'];t=c['terminal'];check(c['accepted']['window_fire']==c['accepted']['window_result_fire']==112 and c['accepted']['drain_fire']==c['accepted']['drain_result_fire']==56 and c['accepted']['request_fire']==c['accepted']['result_fire']==1,'FFN window/drain count balance')
        check(len(c['drain_terminals'])==56 and all(x['status'] is None and x['committed'] for x in c['drain_terminals']) and sum(x['ddr_write_bytes'] for x in c['drain_terminals'])==d['act_ddr']['bytes']==d['act_ddr']['ack_bytes']==4587520,'FFN all drain terminal/ACK bytes')
    elif kind=='Dense':
        t=dict(status=d['completion'][1],tag=d['completion'][0],write_bytes=d['completion'][2],useful_macs=d['useful_macs'],executed_macs=d['executed_macs'])
        check(d['accepted']['write_acks']==d['accepted']['write_descriptors'] and d['accepted']['job_handshakes']==d['accepted']['response_handshakes']==1,'Dense handshake/ACK '+str(pc))
        check(d['ddr']['ack_bytes']==d['ddr']['bytes']==d['ddr']['data_bytes'] and d['ddr']['canaries_exact'] and d['ddr']['full_once_only_coverage'],'Dense physical once-only coverage '+str(pc))
    else:
        t=d['result'];ac=d['backend']['accepted'];check(ac['job_fire']==ac['owner_results']==1 and ac['read_requests']==ac['read_responses'] and ac['write_requests']==ac['write_acks'] and d['accepted']['final_ack_stall']==5,'ordinary owner memory balance '+str(pc))
        check(d['backend']['acknowledged_write_bytes']==t['write_bytes'],'ordinary owner ACK bytes '+str(pc))
    check(t['status'] is None,'owner successful terminal '+str(pc));terminals.append(t)
check(len(terminals)==17 and all(sum(t[k] for t in terminals)==launch[k] for k in ['write_bytes','useful_macs','executed_macs']),'17 owner terminal sums equal whole launch totals')
filecheck(pathlib.Path(s['m16_prerequisite']['path']),s['m16_prerequisite']['sha256']);check(not s['m16_prerequisite']['native_acceptance_inherited'],'M16 native acceptance not inherited')
process=read(B/'actual_m128_03_process.json');check(process['returncode']==0 and process['argv'][process['argv'].index('--out')+1]==str(RUN) and process['argv'][process['argv'].index('--wall-budget')+1]=='1800','successful correct process receipt')
old=read(B/'actual_m128_01/summary.json');audit=read(B/'runtime_budget_audit_20261012T1208/audit.json')
for name,digest in audit['evidence_sha256'].items():filecheck(B/name,digest)
check(old['status']=='FAILED' and old['error']=='full group host budget exceeded' and 1200<old['host_wall_seconds']<1201 and not old['old_pass_inherited'],'old 1200-second FAIL preserved')
check(not s['rtl_executed'] and not s['scala_executed'] and s['hardware_cycles'] is None and not s['comparison']['new_official_forward_executed'] and not s['comparison']['full_29_node_acceptance'] and s['native_acceptance']=='FAIL_OR_INCOMPLETE_OBSERVED_NODE_GATE','no RTL/native/full29 signoff claim')
receipt=dict(schema=1,status='PASS_INDEPENDENT_SAVED_CAPTURE_AUDIT_NATIVE_GATE_REMAINS_FAIL',recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='Saved bytes, metadata, source closure and software transaction receipts only. No model rerun, native forward, compilation, RTL, or source edits.',
    git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    summary_sha256=fsha(RUN/'summary.json'),snapshot_sha256=fsha(SNAP/'SNAPSHOT.json'),verifier_sha256=fsha(pathlib.Path(__file__)),checks_passed=len(checks),
    sources_verified=86,actual_output_files_verified=19,silu_file_verified=True,reference_artifacts_verified=len(ref['artifacts']),raw_input_identities_verified=14,
    observation_fields=coverage,observed_pv_equals_physical_attention=True,fixed_whole_nodes=list(fixed),fixed_observed_nodes=list(extra),native_diagnostics=native,
    host_counts=a,launch_result=launch,physical_memory_counts=ma,published_physical_outputs=len(published),final_ack_fences=fences,
    old_failed_summary_sha256=fsha(B/'actual_m128_01/summary.json'),old_1200_second_failure_preserved=True,old_pass_inherited=False,
    successful_process_receipt=str((B/'actual_m128_03_process.json').relative_to(ROOT)),successful_process_finished_utc=process['finished_utc'],
    limits=['Software protocol ticks are not hardware cycles.','Observer does not itself prove whole-block publication; host/memory receipts provide that software claim.','Full 29-node gate incomplete: explicit mask tensor missing and future score/logit/probability/softmax positions absent.','No new native or RTL execution.'],
    check_labels_sha256=sha(json.dumps(checks,separators=(',',':')).encode()))
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:receipt[k] for k in ['status','checks_passed','sources_verified','actual_output_files_verified','reference_artifacts_verified','native_diagnostics']},indent=2))
print('receipt_sha256',fsha(OUT/'receipt.json'))
