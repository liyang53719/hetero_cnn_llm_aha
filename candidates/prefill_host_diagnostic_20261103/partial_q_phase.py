"""DRAFT pure partial-phase projection. No launch, authority, model, or file writes.
Integrate only AFTER existing numeric_tail.require_cleanup and accepted same-job
candidate build/source/ABI admission. This helper NEVER replaces those gates.
It reads bounded pinned metadata/phase payloads; never ELF/SV/weights.
"""
import ast, hashlib, json, os, pathlib, re, stat, struct
P=pathlib.Path
DRIVER_SHA='e4b23d01ee81a738220512eb24d63b4e323723f686c8af340ad64849a00b5887'
COMPARE_SOURCE_SHA='5513ca59dd2f3bf9dc48337fc1a97966bb5fc3f527f5d3d86a76a48e73ccf773'
COMPARE_AST_SHA='71dad068f9d113ca77de5694396752917f18b9e45a1240b253f121a6bb6ac957'
PROGRAM_SHA='4f201e1744b8aa2c604a478ca837076abaf41a7235b62d8aa7ef14fcdc830163'
SIZE=128*1536*4
SCOPE='PARTIAL_PHASE_NUMERIC_P0_M128_QR_NOT_FULL_BLOCK_OR_FINAL_RTL'
PROGRESS_FIELDS=set('cycles active_cycles pc completions read_bursts read_beats read_acks write_bursts write_beats write_acks write_ack_bytes pipeline_issues pipeline_stalls idma_transfers idma_cache_hits idma_streamed_read_beats idma_streamed_write_beats owner_jobs useful_macs executed_macs host_write_bytes memory_accepted_0 memory_returned_0 memory_accepted_1 memory_returned_1 reset_required'.split())

def need(v,m):
    if not v: raise ValueError(m)

def digest(data): return hashlib.sha256(data).hexdigest()

class BoundedReader:
    def __init__(self): self.bytes=0
    def read(self,path,cap,expected=None):
        path=P(path);need(path.is_absolute() and path==path.resolve() and all(not x.is_symlink() for x in (path,*path.parents)), 'canonical regular path')
        before=path.stat();need(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=cap,'file cap')
        def stable(st):return (st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            need(stable(os.fstat(fd))==stable(before),'open identity')
            chunks=[];size=0
            while True:
                chunk=os.read(fd,65536)
                if not chunk:break
                self.bytes+=len(chunk);need(self.bytes<=64<<20,'aggregate read cap')
                chunks.append(chunk);size+=len(chunk);need(size<=cap,'read cap')
            raw=b''.join(chunks)
            need(stable(os.fstat(fd))==stable(before)==stable(path.stat()) and len(raw)==before.st_size,'stable closed bytes')
        finally:os.close(fd)
        pin=dict(path=str(path),bytes=len(raw),sha256=digest(raw))
        if expected is not None:need(pin==expected,'input pin')
        return raw,pin
    def pinned(self,pin,cap):return self.read(pin['path'],cap,pin)[0]

def original_comparison(source):
    """Caller pins current source bytes; only fixed original function ASTs execute.
    Unrelated same-job branches may change, never these two numeric functions.
    The fixed digest was derived from COMPARE_SOURCE_SHA, not supplied by callers.
    """
    tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('compare','nonfinite')]
    need([n.name for n in nodes]==['nonfinite','compare'],'exact original comparison definitions')
    module=ast.Module(body=nodes,type_ignores=[])
    canonical=ast.dump(module,annotate_fields=True,include_attributes=False).encode()
    need(digest(canonical)==COMPARE_AST_SHA,'fixed original comparison AST pin')
    ns={'need':need,'hashlib':hashlib,'struct':struct}
    exec(compile(module,'pinned_original_comparison','exec'),ns)
    return ns['compare'],ns['nonfinite']

def progress(line):
    m=re.fullmatch(r'HOST_PROGRESS (reset|running|completion|terminal) ((?:[a-z0-9_]+=\d+ ?)+)',line)
    if m is None:return None
    pairs=[x.split('=') for x in m[2].split()];need(len(dict(pairs))==len(pairs) and set(dict(pairs))==PROGRESS_FIELDS,'exact counter-only progress allowlist')
    return dict(kind=m[1],**{k:int(v) for k,v in pairs})

def phase_evidence(log,pc,name,size=SIZE,allow_incomplete=False):
    """HOST_OUTPUT+completion are PRE-POSEDGE: require a later safe sample.
    Incomplete phases expose only availability, never a closure or payload claim.
    Malformed/contradictory evidence remains an error even in incomplete mode.
    """
    need(type(log)is str and log.endswith('\n'),'complete bounded closed log')
    lines=log.splitlines()
    hits=[(i,l)for i,l in enumerate(lines)if re.match(rf'HOST_OUTPUT pc={pc}(?: |$)',l)]
    need(len(hits)<=1 and (allow_incomplete or len(hits)==1),'unique phase output')
    index=cycle=None
    if hits:
        index,line=hits[0];m=re.fullmatch(rf'HOST_OUTPUT pc={pc} name={name} bytes={size} dtype=7 cycles=(\d+)',line)
        need(m is not None,'exact complete output marker');cycle=int(m[1])
    completions=[];target=None;successor=None
    for i,l in enumerate(lines):
        p=progress(l)
        if l.startswith('HOST_PROGRESS'):need(p is not None,'malformed progress evidence')
        if p is not None and index is None:need(p['completions']<=pc and p['pc']<=pc,'progress beyond missing phase output')
        if p is not None and p['kind']=='completion':
            completions.append(p)
            need(p['completions']==len(completions) and p['pc']==len(completions)-1,'ordered command completion prefix')
            if p['pc']==pc:
                need(index is not None and i>index and p['cycles']==cycle and p['completions']==pc+1,'output then same-step completion')
                for a,b in [('read_beats','read_acks'),('write_beats','write_acks'),('memory_accepted_0','memory_returned_0'),('memory_accepted_1','memory_returned_1')]:need(p[a]==p[b],'phase AXI/owner drain')
                need(p['reset_required']==0,'completion fault');target=p
        if target is not None and p is not None and p['kind']in('running','completion','terminal') and p['cycles']>target['cycles'] and p['active_cycles']>target['active_cycles'] and p['completions']>=pc+1 and p['pc']>=pc+1:
            need(p['reset_required']==0,'successor fault');successor=(i,p);break
        if ((l.startswith('ORIGINAL_HOST_REPLAY_FAIL:') and not (allow_incomplete and l==WATCHDOG_LINE)) or (p is not None and p.get('reset_required',0)!=0)):
            raise ValueError('fault before safe successor')
    if allow_incomplete and (target is None or successor is None):
        return dict(pc=pc,name=name,status='NOT_REACHED' if index is None else 'NOT_CLOSED')
    need(target is not None and successor is not None,'missing post-posedge safe successor')
    previous=completions[pc-1] if pc else None
    delta=target['active_cycles']-previous['active_cycles'] if previous else target['active_cycles']
    need(delta>0,'positive completed phase cycles')
    return dict(pc=pc,name=name,output_cycle=cycle,previous_completion=previous,completion=target,safe_successor=successor[1],phase_active_cycles=delta,scope='COMPLETED_PHASE_ONLY_NOT_TERMINAL')

def compare_qraw_qr(qraw,qr,reference_bf16,source):
    # q_proj hook is frozen contiguous [1,128,1536] BF16. Expansion is a
    # comparison-only view; never change original FP32 DUT storage or rounding.
    need(qraw is None or len(qraw)==SIZE,'full M128 qraw span')
    need((qr is None and reference_bf16 is None) or (qraw is not None and qr is not None and reference_bf16 is not None and len(qr)==SIZE and len(reference_bf16)==SIZE//2),'full M128 qr/reference spans')
    compare,nonfinite=original_comparison(source)
    result=dict(scope=SCOPE,status='PARTIAL_PHASE_NOT_EVALUATED' if qraw is None else 'PARTIAL_PHASE_NUMERIC',profile=0,tokens=128,
      qraw=dict(pc=1,status='NOT_REACHED'),qr=dict(pc=2,status='NOT_REACHED'),
      numerical_pass=False,full_block_numerical_pass=False,final_rtl_executed=False,qualification_scope='NO_FULL_ACCEPTANCE_AUTHORITY')
    if qraw is not None:
        result['qraw']=dict(pc=1,status='COMPLETED',scope='PREBIAS_FINITE_ONLY_NO_MATCHING_FROZEN_REFERENCE',bytes=len(qraw),sha256=digest(qraw),nonfinite_elements=nonfinite(qraw,'FP32'),numerical_comparison_performed=False)
    if qr is not None:
        expected=bytearray(SIZE)
        for i,(word,) in enumerate(struct.iter_unpack('<H',reference_bf16)):struct.pack_into('<I',expected,4*i,word<<16)
        qr_result=compare(qr,expected,'FP32')
        exact=qr_result['byte_mismatches']==0 and qr_result['actual_nonfinite_elements']==qr_result['reference_nonfinite_elements']==0
        result['qr']=dict(pc=2,status='COMPLETED',reference_key='stage.self_attn.q_proj.0',reference_dtype='torch.bfloat16',actual_dtype='FP32',reference_conversion='EXACT_UINT16_LEFT_SHIFT_16_NO_ARITHMETIC',comparison=qr_result,phase_exact_match=exact)
    return result

WATCHDOG_LINE='ORIGINAL_HOST_REPLAY_FAIL: bounded original Host did not finish; partial progress is not numerical PASS'
OUTER_WALL_ERROR='ValueError: wall cap'
OUTER_RESOURCE_ERRORS=frozenset('ValueError: '+x for x in (
    'sampled observed aggregate RSS cap','sampled observed aggregate CPU cap',
    'sampled aggregate writable-root cap','sampled stage output tree cap',
    'file cap','sampled log cap'))
TERMINATIONS=frozenset(('WATCHDOG_CYCLE_LIMIT','TIMEOUT','RESOURCE_LIMIT','FAULT','PROCESS_COMPLETE_NOT_FULL_ACCEPTANCE'))

def termination_kind(consumer,outer,log):
    """Fail closed. Only exact driver-cycle or owned wall-cap evidence is incomplete.
    Native crashes, reset, malformed progress and conflicting error evidence win.
    Caller still owes provenance for these closed original consumer/supervisor receipts.
    """
    rows=consumer.get('profiles',[]);need(len(rows)==1 and rows[0].get('profile')==0,'one actual P0 consumer result')
    record=rows[0];errors=outer.get('errors',[])
    if type(errors)is not list or any(type(e)is not str for e in errors):return 'FAULT'
    lines=log.splitlines();failures=[l for l in lines if l.startswith('ORIGINAL_HOST_REPLAY_FAIL:')]
    samples=[]
    for line in lines:
        if line.startswith('HOST_PROGRESS'):
            try:p=progress(line)
            except (ValueError,TypeError):return 'FAULT'
            if p is None or p['reset_required']!=0:return 'FAULT'
            samples.append(p)
        if line.startswith(('%Error','%Fatal','FAULT','FATAL','terminate called','Segmentation fault','Aborted')):return 'FAULT'
    if failures and failures!=[WATCHDOG_LINE]:return 'FAULT'
    rc=record.get('exit_code');err=record.get('error');ec=record.get('error_class')
    native=outer.get('native_exit')
    if (rc is not None and type(rc)is not int) or (err is None)!=(ec is None):return 'FAULT'
    expected_error=(err=='DUT process failure' and ec=='ValueError')
    exact_wall=(rc is None and err=='DUT wall deadline' and ec=='TimeoutError')
    # The original consumer exits 2 after writing an incomplete/result receipt;
    # do not confuse its exit with the DUT's native exit in the profile record.
    if native not in (None,2):return 'FAULT'
    if failures:
        cap=(consumer.get('execution_admission')or{}).get('effective_limits',{}).get('max_active_cycles')
        terminal=[p for p in samples if p['kind']=='terminal']
        if (errors or native!=2 or rc!=1 or not expected_error or type(cap)is not int
            or not 0<cap<=1000000000 or len(terminal)!=1 or terminal[0]['active_cycles']!=cap
            or samples[-1] is not terminal[0] or lines[-1]!=WATCHDOG_LINE):return 'FAULT'
        return 'WATCHDOG_CYCLE_LIMIT'
    if errors:
        # Exact source messages only, never substring matching. A separate DUT
        # error/nonzero exit is a fault even when the supervisor also hits a cap.
        if rc not in (None,0) or (err is not None and not exact_wall):return 'FAULT'
        if errors==[OUTER_WALL_ERROR] and native is None:return 'TIMEOUT'
        if errors and all(e in OUTER_RESOURCE_ERRORS for e in errors) and native is None:return 'RESOURCE_LIMIT'
        return 'FAULT'
    if exact_wall and native==2:return 'TIMEOUT'
    if rc in (-24,-25) and expected_error and native==2:return 'RESOURCE_LIMIT'
    if rc==0 and err is None and ec is None and native==2:return 'PROCESS_COMPLETE_NOT_FULL_ACCEPTANCE'
    return 'FAULT'

def termination_state(kind):
    need(type(kind)is str and kind in TERMINATIONS,'known termination')
    return 'INCOMPLETE' if kind in ('TIMEOUT','WATCHDOG_CYCLE_LIMIT') else kind

def public_summary(local):
    """Only this typed allowlist may leave the job; never serialize local wholesale.
    Unknown input fields are deliberately ignored, including actual_pins paths,
    raw logs, arrays, argv and source/runtime content. No copied free-form text.
    """
    def integer(v,maximum=(1<<64)-1):
        need(type(v)is int and 0<=v<=maximum,'public integer');return v
    def sha(v):
        need(type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None,'public hash');return v
    def flag(v):
        need(type(v)is bool,'public boolean');return v
    kind=local['termination'];state=termination_state(kind)
    statuses=('PARTIAL_PHASE_NOT_EVALUATED','PARTIAL_PHASE_NUMERIC','PARTIAL_PHASE_NUMERIC_WITH_FAULT','PARTIAL_PHASE_NUMERIC_WITH_RESOURCE_LIMIT')
    need(type(local['status'])is str and local['status']in statuses,'public status')
    for k in ('numerical_pass','full_block_numerical_pass','final_rtl_executed'):need(local[k]is False,'no full acceptance')
    out=dict(schema='P0_Q_PARTIAL_PUBLIC_SUMMARY_V1',scope=SCOPE,status=local['status'],termination=kind,
        termination_state=state,profile=0,tokens=128,numerical_pass=False,full_block_numerical_pass=False,
        final_rtl_executed=False,integration_status='NOT_CONNECTED_TO_REVIEWED_SAMEJOB_SOURCE_CONTEXT_OR_BUILD_PROOF',
        diagnostic_failure=flag(local.get('diagnostic_failure',kind in ('FAULT','RESOURCE_LIMIT'))))
    if kind in ('FAULT','RESOURCE_LIMIT'):need(out['diagnostic_failure']is True,'fault or resource limit cannot become success')
    if local['status']=='PARTIAL_PHASE_NOT_EVALUATED' and 'qraw'not in local and 'qr'not in local:return out
    q=local['qraw'];qr=local['qr'];completed=[];numeric_failure=False
    for name,pc in (('qraw',1),('qr',2)):
        item=local[name];need(item['pc']==pc and type(item['pc'])is int,'public phase identity')
        availability=item['status'];need(type(availability)is str and availability in ('COMPLETED','NOT_REACHED','NOT_CLOSED'),'public phase availability')
        out[name]=dict(pc=pc,status=availability)
        if availability=='COMPLETED':completed.append(name)
    need('qr'not in completed or 'qraw'in completed,'qr requires completed qraw')
    need((local['status']=='PARTIAL_PHASE_NOT_EVALUATED')==(not completed),'public evaluated phase status')
    out['completed_phase_count']=len(completed)
    if 'qraw'in completed:
        out['qraw'].update(bytes=integer(q['bytes'],SIZE),sha256=sha(q['sha256']),
            nonfinite_elements=integer(q['nonfinite_elements'],SIZE//4),numerical_comparison_performed=False)
        need(q['bytes']==SIZE and q['numerical_comparison_performed']is False,'full qraw finite-only summary')
        numeric_failure=q['nonfinite_elements']!=0
    if 'qr'in completed:
        c=qr['comparison']
        out['qr'].update(phase_exact_match=flag(qr['phase_exact_match']),comparison={
            k:integer(c[k],SIZE) for k in ('bytes','byte_mismatches','actual_nonfinite_elements','reference_nonfinite_elements')})
        out['qr']['comparison'].update({k:sha(c[k])for k in ('actual_sha256','expected_layout_sha256')})
        first=c['first_mismatch_byte'];out['qr']['comparison']['first_mismatch_byte']=None if first is None else integer(first,SIZE-1)
        need(c['bytes']==SIZE,'full qr summary')
        exact=c['byte_mismatches']==0 and c['actual_nonfinite_elements']==c['reference_nonfinite_elements']==0
        need(qr['phase_exact_match']==exact,'exact numeric status')
        numeric_failure=numeric_failure or not exact
    need(out['diagnostic_failure']==(kind in ('FAULT','RESOURCE_LIMIT') or numeric_failure),'no hidden diagnostic failure')
    out['phase_closure']={}
    for name,pc in (('qraw',1),('qr',2)):
        if name not in local.get('phase_closure',{}):continue
        need(name in completed,'no closure for uncompleted phase')
        phase=local['phase_closure'][name];need(phase['pc']==pc and phase['name']==name,'public phase identity')
        entry={k:integer(phase[k])for k in ('pc','output_cycle','phase_active_cycles')}
        for field in ('completion','safe_successor'):
            sample=phase[field];need(type(sample['kind'])is str and sample['kind']in ('running','completion','terminal'),'public progress kind')
            entry[field]=dict(kind=sample['kind'],**{k:integer(sample[k])for k in sorted(PROGRESS_FIELDS)})
        out['phase_closure'][name]=entry
    for key in ('termination_source_sha256','artifact_manifest_sha256','runtime_bundle_sha256','outer_result_sha256','source_comparison_sha256','driver_sha256'):
        if key in local:out[key]=sha(local[key])
    if 'bytes_read'in local:out['bytes_read']=integer(local['bytes_read'],64<<20)
    return out


def project_closed_phases(reader,text,actual_dir,profile,source):
    """Only safely closed phase files and their necessary reference may be read.
    Missing/truncated claimed-closed files raise evidence errors, never NOT_REACHED.
    Kept separate so bounded synthetic tests need not execute the full project path.
    """
    availability={n:phase_evidence(text,pc,n,allow_incomplete=True) for pc,n in ((1,'qraw'),(2,'qr'))}
    closure={n:p for n,p in availability.items() if 'status'not in p}
    payloads={};actual_pins={};reference=None
    for name in ('qraw','qr'):
        if name not in closure:continue
        raw,p=reader.read(P(actual_dir)/(name+'.actual.bin'),SIZE)
        need(len(raw)==SIZE,'no partial/truncated phase file');payloads[name]=raw;actual_pins[name]=p
    if 'qr'in closure:
        ref=json.loads(reader.pinned(profile['reference_result'],2<<20));need(ref['profile']['profile']==0 and ref['complete_block_tokens']==128 and ref['exact_baseline_observer_output_equal']is True and ref['hardware_executed']is False and ref['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK','original full reference receipt')
        rp=ref['tensor_records']['stage.self_attn.q_proj.0'];rel=P(rp['file']);need(not rel.is_absolute() and '..'not in rel.parts and rel.parts[0]=='reference_only' and rp['shape']==[1,128,1536] and rp['dtype']=='torch.bfloat16' and rp['bytes']==SIZE//2,'post-bias frozen reference only')
        reference=reader.pinned(dict(path=str(P(profile['reference_result']['path']).parent/rel),bytes=rp['bytes'],sha256=rp['sha256']),SIZE//2)
    result=compare_qraw_qr(payloads.get('qraw'),payloads.get('qr'),reference,source)
    for name in ('qraw','qr'):
        if name not in closure:result[name]['status']=availability[name]['status']
    for name in payloads:need(reader.pinned(actual_pins[name],SIZE)==payloads[name],'second stable full read')
    result.update(phase_closure=closure,actual_pins=actual_pins)
    return result


def project(*,consumer_pin,driver_pin,program_pin,bundle_pin,log_pin,popen_pin,outer_pin,artifact_pin,consumer_result_pin,actual_dir):
    """Caller passes pins already bound by the live same-job controller. No CLI.
    The original candidate compilation/source/ABI gates MUST already have passed.
    Outer RESULT, actual files and this local result remain local. Export ONLY
    public_summary(result), never result itself; provenance integration is unfinished.
    """
    r=BoundedReader();src=r.pinned(consumer_pin,128<<10);driver=r.pinned(driver_pin,64<<10)
    need(digest(driver)==DRIVER_SHA,'reviewed mapper driver only')
    program=r.pinned(program_pin,64<<10);need(digest(program)==PROGRAM_SHA,'unchanged full original P0 program')
    program=json.loads(program);need(program['tokens']==128 and program['commands']==21 and program['descriptors']==215,'full M128 21-command program')
    for pc,name,op in [(1,'qraw','l0.q'),(2,'qr','l0.q_bias')]:
        row=program['schedule'][pc];need(row['pc']==pc and row['operation']==op and row['dst']==name and program['tensors'][name]['dims']==[128,1536],'matching full program phase')
    bundle=json.loads(r.pinned(bundle_pin,65536));need(bundle['schema']=='SINGLE_PROFILE_RUNTIME_BUNDLE_V3' and len(bundle['profiles'])==1 and bundle['profiles'][0]['id']==0,'one actual P0 bundle')
    profile=bundle['profiles'][0]
    policy=json.loads(r.pinned(profile['observation_policy'],65536));need(policy['source_pins']['program_manifest']==program_pin,'bundle actual program anchor')
    runtime=r.pinned(profile['runtime'],65536);rows=[l.split('\t')for l in runtime.decode().splitlines()]
    need(rows[0]==['HOST_COMPILED_INPUT_V2'],'original runtime ABI');observations=[x for x in rows if x[0]=='observe'];need(len({x[2]for x in observations})==len(observations),'unique observation names')
    for pc,name in [(1,'qraw'),(2,'qr')]:
        t=program['tensors'][name];need([x for x in observations if x[2]==name]==[['observe',str(pc),name,str(t['address']),str(SIZE),'7']],'actual full output span')
    artifact=json.loads(r.pinned(artifact_pin,65536));need(artifact['common']['driver']['sha256']==DRIVER_SHA,'built mapper identity')
    built_driver=artifact['common']['driver'];need(driver_pin==dict(built_driver,path=str(P(artifact_pin['path']).parent/built_driver['path'])),'actual artifact driver bytes, not unrelated source')
    popen=json.loads(r.pinned(popen_pin,65536));need(popen['schema']=='ACTUAL_DUT_POPEN_V1' and popen['binary_sha256']==artifact['common']['binary']['sha256'] and popen['runtime_sha256']==profile['runtime']['sha256'],'actual fresh DUT invocation')
    outer=json.loads(r.pinned(outer_pin,2<<20));need((outer.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and (outer.get('log_capture')or{}).get('pipe_eof_observed')is True and (outer.get('log_capture')or{}).get('gzip_finalized')is True,'strict completed outer cleanup and capture')
    actual_dir=P(actual_dir);material=P(bundle_pin['path']).parent
    need(actual_dir==material/'dut_result/profile0' and P(log_pin['path'])==material/'dut_result/profile0.log' and P(popen_pin['path'])==material/'dut_result/profile0.started.json' and P(consumer_result_pin['path'])==material/'dut_result/RESULT.json','same actual connected consumer output tree')
    text=r.pinned(log_pin,32<<20).decode();consumer_result=json.loads(r.pinned(consumer_result_pin,2<<20))
    need(consumer_result['artifact_manifest_sha256']==artifact_pin['sha256'] and consumer_result['runtime_bundle_sha256']==bundle_pin['sha256'],'actual same artifact/runtime consumer result')
    termination=termination_kind(consumer_result,outer,text)
    if outer.get('errors'):return dict(status='PARTIAL_PHASE_NOT_EVALUATED',termination=termination,termination_state=termination_state(termination),scope=SCOPE,numerical_pass=False,full_block_numerical_pass=False,final_rtl_executed=False,diagnostic_failure=termination in ('FAULT','RESOURCE_LIMIT'),reason='SUPERVISOR_ERROR_REQUIRES_INDEPENDENT_REVIEW')
    result=project_closed_phases(r,text,actual_dir,profile,src)
    result.update(termination=termination,termination_source_sha256=consumer_result_pin['sha256'],artifact_manifest_sha256=artifact_pin['sha256'],runtime_bundle_sha256=bundle_pin['sha256'],outer_result_sha256=outer_pin['sha256'],source_comparison_sha256=consumer_pin['sha256'],driver_sha256=DRIVER_SHA,bytes_read=r.bytes,caller_prerequisite='EXISTING_SAME_JOB_CANDIDATE_COMPILATION_SOURCE_ABI_ADMISSION_NOT_REPLACED')
    result['termination_state']=termination_state(termination)
    result['diagnostic_failure']=termination in ('FAULT','RESOURCE_LIMIT') or (result['qraw']['status']=='COMPLETED' and result['qraw']['nonfinite_elements']!=0) or (result['qr']['status']=='COMPLETED' and not result['qr']['phase_exact_match'])
    if result['status']=='PARTIAL_PHASE_NUMERIC':
        if termination=='FAULT':result['status']='PARTIAL_PHASE_NUMERIC_WITH_FAULT'
        if termination=='RESOURCE_LIMIT':result['status']='PARTIAL_PHASE_NUMERIC_WITH_RESOURCE_LIMIT'
    return result
