#!/usr/bin/env python3
"""Run existing external-AXI DUT for one selected profile using the unchanged shared artifact manifest; no model arithmetic.
Full exact-reference qualification is joined only after verified outer cleanup.
No new tolerance is assumed; mismatch does not itself locate an arithmetic bug.
Binding paths are explicit; all hardware artifacts and inputs must remain immutable.
NEW lifecycle-only adapter: requires caller-owned strict outer supervision.
Calibration changes only the wall deadline, never stimulus, cycles or acceptance.
"""
import argparse, hashlib, json, os, pathlib, resource, signal, subprocess, time, struct, stat
import required_acceptance


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def pin(p):
    f = pathlib.Path(p['path'])
    need(f.is_absolute() and f.is_file() and not f.is_symlink(), 'regular absolute pin path')
    need(f.stat().st_size == p['bytes'] and sha(f) == p['sha256'], 'pin mismatch: '+str(f))
    return f


def records(path):
    need(path.stat().st_size <= 65536, 'runtime manifest size')
    rows = [x.split('\t') for x in path.read_text().splitlines()]
    need(rows[0] == ['HOST_COMPILED_INPUT_V2'], 'runtime version')
    launch = [r for r in rows if r[0] == 'launch']
    need(len(launch) == 1, 'one launch')
    observations = {r[2]: (int(r[1]), int(r[3]), int(r[4]), int(r[5])) for r in rows if r[0] == 'observe'}
    need(len(observations) == sum(r[0] == 'observe' for r in rows), 'duplicate observations')
    return rows, launch[0], observations


def reference(root, result, key, shape, dtype):
    r = result['tensor_records'][key]
    need(r['shape'] == shape and r['dtype'] == dtype, 'reference shape/dtype '+key)
    path = (root/r['file']).resolve()
    need(path.is_relative_to(root.resolve()), 'reference path escape')
    pin(dict(path=str(path), bytes=r['bytes'], sha256=r['sha256']))
    return path.read_bytes()


def token_major(data, heads, tokens, dim, element_bytes, widen=False):
    """Pure byte permutation: official [1,H,T,D] -> external [T,H,D]."""
    need(len(data) == heads*tokens*dim*element_bytes, 'cache byte count')
    out = bytearray()
    for t in range(tokens):
        for h in range(heads):
            off = (h*tokens+t)*dim*element_bytes
            chunk = data[off:off+dim*element_bytes]
            if widen:
                need(element_bytes == 2, 'BF16 bit expansion only')
                for j in range(0,len(chunk),2):
                    out.extend(b'\x00\x00'+chunk[j:j+2])
            else:
                out.extend(chunk)
    return bytes(out)


def expected(root, result, profile):
    width = [1536,1024,1024,2048,2048][profile]
    out = {'y' if profile == 0 else 'output': reference(root,result,'output_storage',[1,128,width], 'torch.float32' if profile==0 else 'torch.bfloat16')}
    if profile in (1,3):
        channels,heads = (6144,16) if profile==1 else (8192,32)
        out['history_out'] = reference(root,result,'final_cache.conv_states.0',[1,channels,4],'torch.bfloat16')
        # StateTransfer copies contiguous head spans from next_state; Execute's
        # row is key dim and col is value dim. Official recurrence is K^T @ V.
        out['state_out'] = reference(root,result,'final_cache.recurrent_states.0',[1,heads,128,128],'torch.float32')
    else:
        dim = 128 if profile==0 else 256
        kv = [token_major(reference(root,result,'final_cache.'+k,[1,2,128,dim],'torch.bfloat16'),2,128,dim,2,profile==0) for k in ('keys','values')]
        if profile==0:
            out.update(cache_k=kv[0],cache_v=kv[1])
        else:
            # This entry admits capacity128 only: both planes are contiguous.
            out['cache'] = kv[0]+kv[1]
    return out


def nonfinite(data, dtype):
    code,mask=('<I',0x7f800000) if dtype=='FP32' else ('<H',0x7f80)
    return sum((word & mask)==mask for (word,) in struct.iter_unpack(code,data))

def compare(actual, wanted, float_dtype=None):
    need(len(actual)==len(wanted), 'actual output size')
    mismatches=sum(a!=b for a,b in zip(actual,wanted))
    first=next((i for i,(a,b) in enumerate(zip(actual,wanted)) if a!=b),None)
    result=dict(bytes=len(actual),byte_mismatches=mismatches,first_mismatch_byte=first,
                actual_sha256=hashlib.sha256(actual).hexdigest(),expected_layout_sha256=hashlib.sha256(wanted).hexdigest())
    if float_dtype is not None:
        need(float_dtype in ('FP32','BF16'),'declared floating comparison type')
        result.update(actual_nonfinite_elements=nonfinite(actual,float_dtype),reference_nonfinite_elements=nonfinite(wanted,float_dtype))
    return result


def router_compare(data, ids, weights):
    need(len(data)==8192 and len(ids)==8192 and len(weights)==2048,'full128x8 route coverage')
    actual_ids=bytearray();actual_weights=bytearray();counts=[0]*256
    for i,(word,) in enumerate(struct.iter_unpack('<Q',data)):
        token=(word>>34)&127;rank=(word>>31)&7;expert=(word>>23)&255;weight=(word>>7)&65535;row=word&127
        need(word>>41==0 and token==i//8 and rank==i%8,'route reserved/token/rank')
        need(row==counts[expert],'route expert groupRow prefix')
        if rank==0: seen=set()
        need(expert not in seen,'duplicate actual expert');seen.add(expert);counts[expert]+=1
        actual_ids.extend(struct.pack('<q',expert));actual_weights.extend(struct.pack('<H',weight))
    return {'ids':compare(actual_ids,ids),'normalized_bf16_weights':compare(actual_weights,weights,'BF16'),
            'coverage':'128x8_ACKNOWLEDGED_DUT_ROUTE_RECORDS','raw_fp32_selection_scores':'INCOMPLETE_NOT_STORED_IN_ROUTE_MAP'}


def classify_observed_profile(result, has_router):
    """Observed byte diagnostics are never full-stage numerical qualification."""
    checks=list(result['comparisons'].values())
    if has_router:
        checks += [result['router'][key] for key in ('ids','normalized_bf16_weights','bf16_dense_logits')]
        raw=result['router'].get('raw_probability_diagnostics',{})
        if raw.get('status')=='COMPARED_DIAGNOSTIC_ONLY':
            checks.append(raw['full_probabilities'])
            selected=raw.get('actual_selected_output',{})
            if selected.get('status')=='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY':
                checks += [selected['input_output_score_consistency'],selected['official_probability_at_actual_selected_id'],selected['official_selected_probability_by_rank']]
                checks += [{'byte_mismatches':selected['selected_vs_route_id_mismatches']},{'byte_mismatches':selected['selected_vs_official_id_mismatches']}]
    result['observed_subset_status']=('BITWISE_MATCH_DIAGNOSTIC' if checks and all(x['byte_mismatches']==0 for x in checks) else 'BITWISE_MISMATCH_DIAGNOSTIC')
    qualification=required_acceptance.evaluate(result)
    result['qualification']=qualification
    result['status']=qualification['status']
    result['numerical_pass']=False  # Outer cleanup cannot be known inside its live worker.
    result['remaining_required_stage_comparisons']=qualification['missing']
    if has_router:
        raw=result['router'].get('raw_probability_diagnostics',{})
        result['missing_observations']=(['raw_fp32_selected_topk_scores'] if raw.get('status')=='COMPARED_DIAGNOSTIC_ONLY' else ['raw_fp32_selection_scores','raw_fp32_selected_topk_scores'])
        if raw.get('actual_selected_output',{}).get('status')=='COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY':
            result['missing_observations']=[]
        result['moe_small_id_tie_contract']='PENDING_USER_APPROVAL'


OBSERVATION_HELPER_PINS={'resident_compare': '0b0aebe70aa668847cf816b5aed86eae245bebea1a5f29ecdf66e99efb08ddfb', 'moe_score_compare': 'd541c55019d81d518375ec91aa9e696cec7839747c79b8b60786d67faf8f139e'}

def observation_helpers():
    import importlib.util
    modules=[]
    for name,expected_sha in OBSERVATION_HELPER_PINS.items():
        path=pathlib.Path(__file__).resolve().with_name(name+'.py')
        need(path.is_file() and not path.is_symlink() and sha(path)==expected_sha,'reviewed observation helper '+name)
        spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        modules.append(module)
    return modules


def verify_current_observation_round(log, binary, runtime):
    started=log.with_suffix('.started.json')
    need(started.is_file() and not started.is_symlink() and started.stat().st_size<=4096,'bounded actual Popen receipt')
    proof=json.loads(started.read_text())
    need(proof['schema']=='ACTUAL_DUT_POPEN_V1' and type(proof['pid']) is int and proof['pid']>0,'actual DUT process identity')
    need(proof['consumer_pid']==os.getpid() and proof['consumer_start_tick']==int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),'current consumer process identity')
    need(proof['inherited_group']==os.getpgrp()==os.getpid() and proof['inherited_session']==os.getsid(0)==os.getpid(),'current owned outer group/session')
    need(proof['binary_sha256']==sha(binary) and proof['runtime_sha256']==sha(runtime),'current binary/runtime identity')
    return dict(proof,receipt_sha256=sha(started))

FULL_LOG_POLICY=None
FULL_LOG_HELPER_SHA256='8573562ad287b9849bbe2da2a8a604fece8dd5a447bbc91db1b66991828f80fc'
def full_log_module():
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('full_log.py')
    need(path.is_file() and not path.is_symlink() and sha(path)==FULL_LOG_HELPER_SHA256,'reviewed full log helper')
    spec=importlib.util.spec_from_file_location('reviewed_full_log',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def require_model162_binary_mode(binary):
    p=pathlib.Path(binary);s=p.lstat()
    need(p.is_absolute() and p==p.resolve(strict=True) and stat.S_ISREG(s.st_mode),'actual162 regular canonical executable')
    need(stat.S_IMODE(s.st_mode)==0o700 and s.st_uid==os.geteuid(),'actual162 direct executable exact owner/mode')

def execute_streaming(binary, runtime, output, log, limits, *, model162_binary=False):
    need(type(model162_binary)is bool,'explicit binary mode policy')
    need('diagnostic_deadline_monotonic'not in limits,'same-job diagnostic uses existing closed raw-log execution, no unbound streaming deadline')
    helper=full_log_module();archive,capture_path=helper.paths(log)
    need(not log.exists() and not archive.exists() and not capture_path.exists(),'fresh full streaming log')
    writer=helper.Writer(archive,FULL_LOG_POLICY)
    def bounded():
        resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    binary_sha=sha(binary);runtime_sha=sha(runtime)
    def started(p):
        if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()
        with log.with_suffix('.started.json').open('x') as evidence:
            json.dump(dict(schema='ACTUAL_DUT_POPEN_V1',pid=p.pid,consumer_pid=os.getpid(),consumer_start_tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),inherited_group=os.getpgrp(),inherited_session=os.getsid(0),binary_sha256=binary_sha,runtime_sha256=runtime_sha),evidence)
    try:
        if model162_binary:
            need(WORKSPACE_LOADER is None,'actual162 ordinary direct execution only')
            require_model162_binary_mode(binary)
        p=subprocess.Popen(runtime_abi_module().execution_argv(binary,runtime,output,limits['max_active_cycles']) if WORKSPACE_LOADER is not None else [str(binary),str(runtime),str(output),str(limits['max_active_cycles'])],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,preexec_fn=bounded,env=runtime_abi_module().clean_env(),bufsize=0)
    except BaseException:
        try:
            writer.finish()
        finally:
            try:writer.close()
            finally:
                if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()
        raise
    result=helper.capture(p,log,FULL_LOG_POLICY,limits['wall_seconds'],started,writer=writer)
    if result['termination_reason']=='WALL_TIMEOUT':raise TimeoutError('DUT wall deadline')
    need(result['complete'],'DUT streaming log incomplete: '+result['termination_reason'])
    return result['native_exit']


def execute(binary, runtime, output, log, limits, *, model162_binary=False):
    need(type(model162_binary)is bool,'explicit binary mode policy')
    def bounded():
        resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    binary_sha=sha(binary);runtime_sha=sha(runtime)
    with open(log,'xb') as f:
        diagnostic_launch=host_diagnostic_module().cap_before_popen(limits,time.monotonic()) if 'diagnostic_deadline_monotonic'in limits else None
        try:
            if model162_binary:
                need(WORKSPACE_LOADER is None,'actual162 ordinary direct execution only')
                require_model162_binary_mode(binary)
            p=subprocess.Popen(runtime_abi_module().execution_argv(binary,runtime,output,limits['max_active_cycles']) if WORKSPACE_LOADER is not None else [str(binary),str(runtime),str(output),str(limits['max_active_cycles'])],stdout=f,stderr=subprocess.STDOUT,preexec_fn=bounded,env=runtime_abi_module().clean_env())
        except BaseException:
            if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()
            raise
        observed_exit_monotonic=None;diagnostic_wall_timeout=False
        try:
            if CLOUD_MEMORY is not None:CLOUD_MEMORY.after_popen()
            started=pathlib.Path(log).with_suffix('.started.json')
            with started.open('x') as evidence:
                proof=dict(schema='ACTUAL_DUT_POPEN_V1',pid=p.pid,consumer_pid=os.getpid(),consumer_start_tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),inherited_group=os.getpgrp(),inherited_session=os.getsid(0),binary_sha256=binary_sha,runtime_sha256=runtime_sha)
                if diagnostic_launch is not None:
                    proof['host_diagnostic_execution']=dict(diagnostic_launch,popen_after_monotonic=time.monotonic())
                    proof.update(started_monotonic=diagnostic_launch['popen_before_monotonic'],effective_runtime_limits=dict(limits))
                json.dump(proof,evidence)
            deadline=time.monotonic()+limits['wall_seconds']
            if diagnostic_launch is not None:deadline=min(deadline,diagnostic_launch['absolute_deadline_monotonic'])
            while True:
                # WNOWAIT retains the leader (including a zombie) as PGID anchor.
                state=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if state is not None:
                    if diagnostic_launch is not None:observed_exit_monotonic=time.monotonic()
                    return state.si_status if state.si_code==os.CLD_EXITED else -state.si_status
                if time.monotonic()>=deadline:
                    diagnostic_wall_timeout=diagnostic_launch is not None
                    raise TimeoutError('DUT wall deadline')
                time.sleep(0.2)
        finally:
            # The DUT inherits the strict outer group/session: never create or
            # kill a nested group here. Reap this leader only; caller must retain
            # the consumer leader and prove full outer group absence afterward.
            if diagnostic_launch is None:
                if p.poll() is None:p.kill()
                p.wait()
            else:
                # Never poll/reap first: wait4 supplies this actual child's CPU,
                # separate from outer controller/supervisor wall and CPU.
                state=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                cleanup_started=time.monotonic()
                if state is None:
                    try:p.kill()
                    except ProcessLookupError:pass
                while True:
                    try:waited,status,usage=os.wait4(p.pid,0);break
                    except InterruptedError:continue
                need(waited==p.pid,'actual diagnostic child wait identity')
                p.returncode=os.waitstatus_to_exitcode(status);reaped=time.monotonic()
                termination=dict(schema='ACTUAL_DUT_TERMINATION_V1',scope=HOST_DIAGNOSTIC_SCOPE,pid=p.pid,consumer_pid=os.getpid(),binary_sha256=binary_sha,runtime_sha256=runtime_sha,started_monotonic=diagnostic_launch['popen_before_monotonic'],observed_exit_monotonic=observed_exit_monotonic,cleanup_started_monotonic=cleanup_started,reaped_monotonic=reaped,elapsed_through_reap_seconds=reaped-diagnostic_launch['popen_before_monotonic'],wait4_child_user_seconds=usage.ru_utime,wait4_child_system_seconds=usage.ru_stime,wait4_child_cpu_seconds=usage.ru_utime+usage.ru_stime,native_exit=p.returncode,wall_deadline_triggered=diagnostic_wall_timeout,effective_runtime_limits=dict(limits),measurement_scope='DIRECT_DUT_CHILD_HOST_TIME_NOT_RTL_CYCLES_NOT_OUTER_STAGE',outer_cleanup_still_required=True)
                with pathlib.Path(log).with_suffix('.termination.json').open('x')as evidence:json.dump(termination,evidence)


OWNED_ENVIRONMENT=None

V3_DRIVER_SHA256='343e99786a82fd5e738d3e48667fde204e21c077e397f8d20a4cddd59629bb61'

FIRST_FAULT_SCHEMA='MODEL_CANDIDATE_FIRST_FAULT_BUILD_ARTIFACT_V1'
FIRST_FAULT_SCOPE='P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE'
HOST_DIAGNOSTIC_MODE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC'
HOST_DIAGNOSTIC_SCOPE=HOST_DIAGNOSTIC_MODE+'_NOT_FULL_ACCEPTANCE'
class HostDiagnosticBoundary(Exception):pass

def host_diagnostic_module():
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('samejob_host_diagnostic.py')
    spec=importlib.util.spec_from_file_location('actual_samejob_host_diagnostic',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def gdn32_module():
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('samejob_gdn32_full.py')
    spec=importlib.util.spec_from_file_location('actual_samejob_gdn32_full',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def gdn32_context(context):
    return type(context)is dict and context.get('schema')=='ADMITTED_SAME_JOB_GDN32_FULL_V1' and context.get('candidate_scope')=='GDN32_FULL_M128_MODEL_EVALUATION_NOT_FINAL_RTL'

def host_context(context):
    return type(context)is dict and context.get('schema')=='ADMITTED_SAME_JOB_P0_HOST_DIAGNOSTIC_V1' and context.get('candidate_scope')==HOST_DIAGNOSTIC_SCOPE

def diagnostic_driver(frozen,context,row):
    need(type(context)is dict and context.get('candidate_scope')==FIRST_FAULT_SCOPE,'independently admitted diagnostic context')
    import types
    rel='candidates/gdn32_first_model_execution_20261104/numeric/first_fault_driver_contract.py'
    catalog=json.loads(pin(context['current_source_pins_pin']).read_text());need(catalog['schema']=='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1','actual diagnostic checker catalog')
    rows=[r for r in catalog['files']if r['path']==rel];need(len(rows)==1,'one diagnostic driver checker')
    path=pathlib.Path(context['repo'])/rel;need(path==pathlib.Path(__file__).resolve().with_name('first_fault_driver_contract.py'),'fixed diagnostic checker location')
    raw=pin(dict(rows[0],path=str(path))).read_bytes();module=types.ModuleType('admitted_first_fault_driver');module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__)
    return module.require_driver(frozen,context,row)

def verify_frozen(path,expected_sha):
    need(len(expected_sha)==64 and all(c in '0123456789abcdef' for c in expected_sha),'expected artifact SHA256 required')
    need(path.is_file() and not path.is_symlink() and path.stat().st_size<=65536,'bounded regular artifact manifest')
    need(sha(path)==expected_sha,'shared artifact manifest changed')

def artifact_identity(frozen,source_relocation=None):
    if frozen['schema']==FIRST_FAULT_SCHEMA:
        need(source_relocation is not None and source_relocation.get('candidate_scope')==FIRST_FAULT_SCOPE and source_relocation.get('builder_identity')==frozen['artifact_identity'],'independently admitted first fault artifact')
    elif frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1' and gdn32_context(source_relocation):
        gdn32_module().admitted_context(source_relocation)
        need(source_relocation['builder_identity']==frozen['artifact_identity'],'same-job GDN32 full artifact identity')
    elif frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1' and host_context(source_relocation):
        host_diagnostic_module().admitted_context(source_relocation)
        need(source_relocation['builder_identity']==frozen['artifact_identity'],'same-job diagnostic artifact identity')
    elif frozen['schema']=='MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1':
        need(source_relocation is not None and source_relocation.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL' and source_relocation.get('builder_identity')==frozen['artifact_identity'],'independently admitted model candidate, not a legacy schema alias')
    else:need(frozen['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2','frozen artifact schema')
    need(frozen['profiles']==list(range(5)),'artifact qualifies same hardware definition for all five, not a profile-specific build')
    identity=frozen['artifact_identity']
    need(set(identity)=={'run_id','artifact_name','launch_commit','source_commit','launch_manifest_path','launch_manifest_blob_sha'},'artifact provenance fields')
    need(type(identity['run_id']) is int and identity['run_id']>0,'actual build run identity required')
    name=identity['artifact_name'];need(isinstance(name,str) and 0<len(name)<=128 and all(c.isalnum() or c in '-_.' for c in name),'artifact name required')
    commit=identity['source_commit']
    for field in ('source_commit','launch_commit','launch_manifest_blob_sha'):
        value=identity[field];need(len(value)==40 and all(c in '0123456789abcdef' for c in value),'exact Git SHA required: '+field)
    need(identity['launch_commit']!=commit,'two-commit launch/source contract required')
    launch_path=pathlib.PurePosixPath(identity['launch_manifest_path'])
    need(not launch_path.is_absolute() and '..' not in launch_path.parts and len(launch_path.parts)==2 and launch_path.parts[0]=='ci_launch' and launch_path.suffix=='.json','single reviewed ci_launch JSON path')
    return identity

def coverage_policy(profile,common,identity,bundle_root,source_relocation=None):
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('observation_contract.py')
    if source_relocation is not None and source_relocation.get('candidate_scope')==FIRST_FAULT_SCOPE:
        path=path.with_name('first_fault_observation_contract.py');row=source_relocation['candidate_observation_checker'];need(pin(row)==path,'admitted first fault observation checker')
    elif gdn32_context(source_relocation) or host_context(source_relocation) or (source_relocation is not None and source_relocation.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL'):
        path=path.with_name('candidate_observation_contract.py');row=source_relocation['candidate_observation_checker'];need(pin(row)==path,'admitted candidate observation checker')
    else:need(sha(path)=='b8401fd6c8c238757103c3c093ea7dc6f3a0d37aab5f0d423e2a7edf2c293e71','reviewed observation contract module')
    spec=importlib.util.spec_from_file_location('required_observation_policy',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if source_relocation is None:return module.validate(profile,common,identity,bundle_root)
    return module.validate(profile,common,identity,bundle_root,source_relocation)


def finite_long_connection_admission(args):
    if getattr(args,'cloud_binding',None)is None:return None
    binding=cloud_invocation(args)
    if binding.get('execution_mode')!='FULL_BLOCK_ACCEPTANCE':return None
    row=binding.get('full_block_budget');need(type(row)is dict,'full connection budget pin')
    doc=json.loads(pin(row).read_text())
    if 'finite_long_policy'not in doc:return None
    need(binding['artifact_manifest']['sha256']==args.artifact_manifest_sha256 and binding['builder_handoff']['sha256']==args.builder_handoff_sha256,'finite long connector actual artifact')
    need(binding['executor_identity']==executor_context(args),'finite long connector actual executor')
    import importlib.util
    path=pathlib.Path(__file__).resolve().parent.parent/'execution_mode.py'
    need(binding['pins'].get(str(path))==sha(path),'finite long connector policy source pin')
    spec=importlib.util.spec_from_file_location('finite_long_connection_mode',path);mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
    admission=mode.admit(binding);need(mode.finite_long(admission),'actual finite long connector admission')
    return admission

def finite_long_mode():
    import importlib.util
    path=pathlib.Path(__file__).resolve().parent.parent/'execution_mode.py'
    spec=importlib.util.spec_from_file_location('finite_long_runtime_mode',path);mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode);return mode

def load_binding(manifest,expected_sha,bundle_path,profile,source_relocation=None,admission=None):
    verify_frozen(manifest,expected_sha)
    frozen=json.loads(manifest.read_text())
    identity=artifact_identity(frozen,source_relocation);commit=identity['source_commit']
    root=manifest.resolve().parent
    tool=frozen['tool_manifest'];rel=pathlib.Path(tool['path'])
    need(not rel.is_absolute() and '..' not in rel.parts,'relative tool manifest')
    tool_path=root/rel;need(tool_path.resolve().is_relative_to(root),'tool manifest escape');pin(dict(tool,path=str(tool_path.absolute())))
    common={}
    need(set(frozen['common'])=={'binary','sv','source_manifest','driver','build_receipt'},'complete frozen identity')
    for name,p in frozen['common'].items():
        rel=pathlib.Path(p['path']);need(not rel.is_absolute() and '..' not in rel.parts and str(rel) not in ('','.'),'artifact relative path only')
        full=root/rel;need(full.resolve().is_relative_to(root),'artifact path escape')
        common[name]=dict(p,path=str(full.absolute()));pin(common[name])
    if frozen['schema']==FIRST_FAULT_SCHEMA:
        need(type(profile)is int and profile==0,'first fault execution is P0 only');diagnostic_driver(frozen,source_relocation,common['driver'])
    elif gdn32_context(source_relocation):
        gdn32_module().admitted_context(source_relocation)
        need(type(profile)is int and 0<=profile<5 and common['driver']['sha256']==gdn32_module().DRIVER_SHA,'exact new ordinary full driver')
    elif host_context(source_relocation):
        host_diagnostic_module().admitted_context(source_relocation)
        need(profile==0 and common['driver']['sha256']==host_diagnostic_module().DRIVER_SHA,'exact independent same-job host driver only')
    elif admission is not None and 'finite_long_policy'in admission:finite_long_mode().verify_finite_driver(admission,common['driver']['sha256'],expected_sha)
    else:need(common['driver']['sha256']==V3_DRIVER_SHA256,'exact original V3 driver, no config-only replacement')
    receipt=json.loads(pathlib.Path(common['build_receipt']['path']).read_text())
    need(receipt['tool_manifest_sha256']==tool['sha256'] and receipt['source_commit']==commit and receipt['launch_commit']==identity['launch_commit'],'source/launch/tool provenance')
    need(receipt['config_only'] is False and receipt['software_arithmetic_substitution'] is False,'real hardware build required')
    for name in ('binary','sv','source_manifest','driver'):need(receipt[name+'_sha256']==common[name]['sha256'],'frozen build receipt identity '+name)
    need(bundle_path.is_file() and not bundle_path.is_symlink() and bundle_path.stat().st_size<=65536,'bounded local runtime bundle')
    bundle=json.loads(bundle_path.read_text())
    need(bundle['schema']=='SINGLE_PROFILE_RUNTIME_BUNDLE_V3','single profile runtime bundle')
    need(bundle['hardware_executed'] is False and bundle['raw_payloads_upload_allowed'] is False,'materialization only')
    need(len(bundle['profiles'])==1 and bundle['profiles'][0]['id']==profile,'requested single profile, no other profile result import')
    need(bundle['limits']['wall_seconds']==20000,'original 20000s conservative bound, pending remaining-job admission')
    for p in bundle['profiles']:
        for key in ('runtime','views','reference_result','provider_receipt'):
            f=pin(p[key]);need(f.resolve().is_relative_to(bundle_path.resolve().parent),'runtime/reference outside materialization output')
    b={k:frozen[k] for k in ('layer','matrix_macs','vector_lanes','moe_reference_contract')}
    b.update(common=common,profiles=bundle['profiles'],limits=bundle['limits'])
    b['coverage_policy']=coverage_policy(bundle['profiles'][0],common,identity,bundle_path.resolve().parent,source_relocation)
    return b,frozen


def verify_launch_proof(receipt,identity):
    commit_path=pin(receipt['launch_commit_api']);need(commit_path.stat().st_size<=1024*1024,'bounded launch commit API')
    commit=json.loads(commit_path.read_text())
    need(commit['sha']==identity['launch_commit'],'launch commit API SHA')
    need(len(commit['parents'])==1 and commit['parents'][0]['sha']==identity['source_commit'],'unique checked-out source parent')
    files=commit['files'];need(len(files)==1,'launch commit must change exactly one manifest')
    file=files[0]
    need(file['status']=='added' and file['filename']==identity['launch_manifest_path'] and file['sha']==identity['launch_manifest_blob_sha'],'launch added file/blob identity')
    blob_path=pin(receipt['launch_manifest_blob']);need(blob_path.stat().st_size<=65536,'bounded launch JSON')
    raw=blob_path.read_bytes();blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    need(blob_sha==file['sha'],'actual launch Git blob bytes')
    launch=json.loads(raw)
    need(launch['source_sha']==identity['source_commit'],'launch manifest checked-out source_sha')

def cloud_invocation(args):
    path=getattr(args,'cloud_binding',None)
    need(path is not None and path.is_absolute() and path.is_file() and all(not p.is_symlink()for p in(path,*path.parents)) and path.stat().st_size<=1<<20 and sha(path)==args.cloud_binding_sha256,'pinned actual cloud invocation')
    return json.loads(path.read_text())


def executor_context(args):
    global WORKSPACE_LOADER
    path=getattr(args,'executor_identity',None);digest=getattr(args,'executor_identity_sha256',None)
    if path is None:
        need(digest is None and getattr(args,'builder_handoff',None) is None,'paired split execution identity')
        return None
    verify_frozen(path,digest)
    need(path.stat().st_size<=65536,'bounded executor identity')
    import importlib.util
    helper=pathlib.Path(__file__).resolve().parent.parent/'executor_identity.py'
    need(sha(helper)=='e3011725f319f543c0d9ba08075efa9a9341eded6112187de4afe611d1987af4','reviewed cloud identity helper')
    spec=importlib.util.spec_from_file_location('actual_cloud_executor',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    identity=m.verify_owner(json.loads(path.read_text()))
    if getattr(args,'cloud_binding',None) is None:
        need(identity['source_commit']==args.expected_source_commit,'executor source equals builder source')
        return identity
    binding=cloud_invocation(args)
    adaptation=binding.get('executor_adaptation')
    if adaptation is None:
        need(identity['source_commit']==args.expected_source_commit,'executor source equals builder source')
    else:
        helper=pathlib.Path(__file__).resolve().parent.parent/'executor_adaptation.py'
        need(binding['pins'].get(str(helper))==sha(helper),'pinned host executor adaptation checker')
        spec=importlib.util.spec_from_file_location('consumer_executor_adaptation',helper);adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        verify_frozen(args.artifact_manifest,args.artifact_manifest_sha256);frozen=json.loads(args.artifact_manifest.read_text())
        builder=frozen['artifact_identity'];need(builder['source_commit']==args.expected_source_commit,'actual immutable builder source')
        adapter.verify(adaptation,builder,identity,binding['source_pins'],binding['repo'])
        helper=helper.with_name('cloud_budget.py');need(binding['pins'].get(str(helper))==sha(helper),'pinned approved execution resource checker')
        spec=importlib.util.spec_from_file_location('consumer_adapter_budget',helper);budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);budget.admit(binding)
        row=binding['workspace_loader'];value=(row['path'],row['sha256'],args.expected_source_commit,args.artifact_manifest_sha256)
        need(WORKSPACE_LOADER is None or WORKSPACE_LOADER==value,'immutable consumer workspace loader admission');WORKSPACE_LOADER=value
    return identity


def owning_environment_identity(args):
    actual=executor_context(args)
    return actual if actual is not None else dict(run_id=args.expected_run_id,source_commit=args.expected_source_commit,launch_commit=args.expected_launch_commit)


def verify_local_build(args,frozen):
    if getattr(args,'samejob_full_binding',None)is not None:return gdn32_module().verify_build(args,frozen)
    need(getattr(args,'samejob_full_binding_sha256',None)is None,'no unpaired full binding')
    if getattr(args,'samejob_diagnostic_binding',None)is not None:return host_diagnostic_module().verify_build(args,frozen)
    need(getattr(args,'samejob_diagnostic_binding_sha256',None)is None,'no unpaired diagnostic binding')
    import importlib.util
    cloud=executor_context(args)
    if cloud is not None:
        need(getattr(args,'local_build_result',None) is None and getattr(args,'local_build_result_sha256',None) is None,'imported build is not same-job retained result')
        binding=cloud_invocation(args)
        candidate=frozen['schema']in('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',FIRST_FAULT_SCHEMA)
        path=pathlib.Path(__file__).resolve().with_name('candidate_artifact_handoff.py' if candidate else 'artifact_handoff.py')
        if candidate:need(binding['pins'].get(str(path))==sha(path),'reviewed candidate build verifier source')
        else:need(sha(path)=='06ac175b7c1f8ca5b1dc19891a52c09f58f17fec521ee96e0f581ca4011ef0c5','reviewed imported build verifier')
        spec=importlib.util.spec_from_file_location('verified_builder_handoff',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        need(frozen['artifact_identity']['run_id']==args.expected_run_id and frozen['artifact_identity']['launch_commit']==args.expected_launch_commit,'expected builder identity distinct from executor')
        kwargs=dict(executor_adaptation=binding.get('executor_adaptation'))
        if candidate:kwargs.update(current_source_pins_pin=binding['source_pins'],repo=binding['repo'],model_candidate_review=binding.get('model_candidate_review'))
        return m.verify(args.builder_handoff,args.builder_handoff_sha256,args.artifact_manifest,args.artifact_manifest_sha256,frozen,cloud,**kwargs)
    need(getattr(args,'builder_handoff_sha256',None) is None,'no unpaired handoff')
    module_path=pathlib.Path(__file__).resolve().with_name('local_build_proof.py')
    need(sha(module_path)=='b58ebbff5578e641b58e7f2c4c1366a7c73f3a4861cf21e37cab7a01c46d8b56','reviewed local build proof')
    spec=importlib.util.spec_from_file_location('same_job_build_proof',module_path);local_build_proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(local_build_proof)
    return local_build_proof.verify(args.local_build_result,args.local_build_result_sha256,args.artifact_manifest,args.artifact_manifest_sha256,frozen,args.expected_run_id,args.expected_launch_commit,args.expected_source_commit)


def approved_source_relocation(args,frozen):
    """Only the independently approved cloud invocation can authorize relocation.
    No bundle field or user-supplied path map is an authority input.
    """
    if getattr(args,'samejob_full_binding',None)is not None:return gdn32_module().source_context(args,frozen)
    if getattr(args,'samejob_diagnostic_binding',None)is not None:return host_diagnostic_module().source_context(args,frozen)
    candidate=frozen['schema']in('MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1',FIRST_FAULT_SCHEMA)
    if (args.profile!=0 and not candidate) or getattr(args,'cloud_binding',None)is None:return None
    binding=cloud_invocation(args)
    if binding.get('executor_adaptation')is None:return None
    import importlib.util
    path=pathlib.Path(__file__).resolve().parent.parent/'cloud_budget.py'
    need(binding['pins'].get(str(path))==sha(path),'admitted cloud budget source before relocation')
    spec=importlib.util.spec_from_file_location('source_relocation_budget',path);budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
    admitted=budget.admit(binding)
    need(admitted.get('executor_adaptation')==binding['executor_adaptation'],'independently approved adapter input for source relocation')
    provenance=verify_local_build(args,frozen) # Live executor + complete adapter/catalog + immutable builder handoff.
    adaptation=provenance.get('executor_adaptation');need(adaptation is not None,'verified distinct executor source adaptation')
    source_row=frozen['common']['source_manifest'];source=pin(dict(source_row,path=str(args.artifact_manifest.resolve().parent/source_row['path'])))
    need(source.stat().st_size<=16<<20,'bounded immutable builder source manifest');manifest=json.loads(source.read_text())
    catalog=pin(binding['source_pins']);need(catalog.stat().st_size<=2<<20,'bounded actual executor catalog')
    context=None
    if candidate:
        path=pathlib.Path(__file__).resolve().with_name('candidate_admission.py');need(binding['pins'].get(str(path))==sha(path),'candidate admission source pin')
        spec=importlib.util.spec_from_file_location('consumer_model_candidate_admission',path);candidate_gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate_gate)
        reviewed=candidate_gate.verify(binding.get('model_candidate_review'),binding)
        checker=path.with_name('first_fault_observation_contract.py'if frozen['schema']==FIRST_FAULT_SCHEMA else'candidate_observation_contract.py');need(binding['pins'].get(str(checker))==sha(checker),'candidate observation source pin')
        context=dict(artifact_manifest=binding['artifact_manifest'],source_manifest_sha256=source_row['sha256'],candidate_scope=reviewed['scope'],model_candidate_review=binding['model_candidate_review'],model_source_contract=reviewed['source_contract'],builder_identity=frozen['artifact_identity'],repo=binding['repo'],current_source_pins_pin=binding['source_pins'],candidate_observation_checker=dict(path=str(checker),bytes=checker.stat().st_size,sha256=sha(checker)))
    path=pathlib.Path(__file__).resolve().with_name('first_fault_observation_contract.py'if frozen['schema']==FIRST_FAULT_SCHEMA else'candidate_observation_contract.py'if candidate else'observation_contract.py');need(binding['pins'].get(str(path))==sha(path),'actual source mapping verifier pinned')
    spec=importlib.util.spec_from_file_location('source_relocation_contract',path);contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
    anchors=contract.relocation_records(manifest,binding['repo'],binding['pins'],json.loads(catalog.read_text()),context) if candidate and args.profile==0 else {} if candidate else contract.relocation_records(manifest,binding['repo'],binding['pins'],json.loads(catalog.read_text()))
    result=dict(context or {})
    result.update(schema='ADMITTED_CLOUD_P0_SOURCE_RELOCATION_V1',controller_binding=dict(path=str(args.cloud_binding),bytes=args.cloud_binding.stat().st_size,sha256=args.cloud_binding_sha256),executor_adaptation_sha256=binding['executor_adaptation']['sha256'],artifact_manifest_sha256=args.artifact_manifest_sha256,source_manifest_sha256=source_row['sha256'],builder_source_commit=frozen['artifact_identity']['source_commit'],executor_source_commit=provenance['executor_identity']['source_commit'],executor_source_pins_sha256=adaptation['executor_source_pins_sha256'],anchors=anchors)
    return result

def runtime_abi_module():
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('runtime_abi_owned.py')
    need(sha(path)=='11dae378bdf32feb82153cd1ae48aa166a65c7e959d6cecbed42b9ab0a85d3f6','reviewed startup ABI module')
    spec=importlib.util.spec_from_file_location('pinned_startup_abi',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);need(OWNED_ENVIRONMENT is not None,'explicit owned environment admission');m.configure_owned_environment(*OWNED_ENVIRONMENT)
    if WORKSPACE_LOADER is not None:m.configure_workspace_loader(*WORKSPACE_LOADER)
    return m

def verify_runtime_abi(args,frozen):
    root=args.artifact_manifest.resolve().parent
    binary=pin(dict(frozen['common']['binary'],path=str(root/frozen['common']['binary']['path'])))
    tool=pin(dict(frozen['tool_manifest'],path=str(root/frozen['tool_manifest']['path'])))
    result=runtime_abi_module().verify(args.local_runtime_abi,args.local_runtime_abi_sha256,binary,frozen['common']['binary']['sha256'],tool,frozen['tool_manifest']['sha256'])
    if getattr(args,'runtime_bundle',None) is not None:
        bundle=json.loads(args.runtime_bundle.read_text());r=bundle['local_runtime_abi']
        need(pin(r)==args.local_runtime_abi and r['sha256']==args.local_runtime_abi_sha256,'bundle startup ABI receipt binding')
    return result

CLOUD_MEMORY=None
WORKSPACE_LOADER=None

def prepare_cloud_memory(args):
    global CLOUD_MEMORY
    if getattr(args,'cloud_binding',None) is None:return None,None
    binding=json.loads(args.cloud_binding.read_text())
    import importlib.util
    path=pathlib.Path(__file__).resolve().parent.parent/'cloud_budget.py'
    need(binding['pins'].get(str(path))==sha(path),'actual cloud resource source pin')
    spec=importlib.util.spec_from_file_location('consumer_resource_budget',path);budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);admitted=budget.admit(binding)
    helper=pathlib.Path(__file__).resolve().with_name('consumer_memory.py')
    need(binding['pins'].get(str(helper))==sha(helper),'actual cloud memory source pin')
    spec=importlib.util.spec_from_file_location('consumer_memory_envelope',helper);memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory)
    row=memory.prepare(admitted['consumer_address_space_bytes'],admitted['dut_address_space_bytes']);CLOUD_MEMORY=memory
    return (budget,admitted),row


def explicit_execution_admission(args):
    global WORKSPACE_LOADER
    if getattr(args,'samejob_full_binding',None)is not None:
        helper=gdn32_module();binding,row,admission=helper.load_binding(args)
        need(args.execution_mode==helper.FULL,'new full binding never diagnostic/calibration')
        return helper,admission

    if getattr(args,'execution_mode',None)==HOST_DIAGNOSTIC_MODE:
        helper=host_diagnostic_module();binding,row,admission=helper.load_binding(args)
        need(args.calibration_wall_seconds is None,'no calibration fallback for host diagnostic')
        if not args.validate_only:need('frozen_window'in admission,'actual execution requires frozen one-shot long window')
        return helper,admission
    need(getattr(args,'samejob_diagnostic_binding',None)is None and getattr(args,'samejob_diagnostic_binding_sha256',None)is None,'diagnostic binding forbidden in old modes')
    import importlib.util
    path=pathlib.Path(__file__).resolve().parent.parent/'execution_mode.py'
    spec=importlib.util.spec_from_file_location('owned_execution_mode',path);mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)
    selected=getattr(args,'execution_mode',mode.CALIBRATION)
    cloud_path=getattr(args,'cloud_binding',None)
    stage_budget=getattr(args,'stage_coverage_budget',None);stage_sha=getattr(args,'stage_coverage_budget_sha256',None)
    if selected!=mode.STAGE:need(stage_budget is None and stage_sha is None,'stage coverage budget forbidden in other modes')
    if cloud_path is not None:
        need(cloud_path.is_absolute()and cloud_path.is_file()and all(not p.is_symlink()for p in(cloud_path,*cloud_path.parents))and cloud_path.stat().st_size<=1<<20 and sha(cloud_path)==args.cloud_binding_sha256,'bounded independently pinned cloud invocation binding')
        binding=json.loads(cloud_path.read_text());need(binding.get('execution_context')=='CLOUD_EXECUTOR_V1'and binding['executor_identity']==executor_context(args),'same actual executor invocation')
        need(binding['artifact_manifest']['sha256']==args.artifact_manifest_sha256 and binding['builder_handoff']['sha256']==args.builder_handoff_sha256,'cloud invocation actual artifact')
        need(binding['execution_mode']==selected,'actual invocation selected mode')
        cloud_helper=path.parent/'cloud_budget.py';need(binding['pins'].get(str(cloud_helper))==sha(cloud_helper),'actual cloud resource helper source pin')
        spec=importlib.util.spec_from_file_location('actual_consumer_cloud_budget',cloud_helper);cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud);cloud.admit(binding)
        if binding.get('workspace_loader') is not None:
            row=binding['workspace_loader'];WORKSPACE_LOADER=(row['path'],row['sha256'],args.expected_source_commit,args.artifact_manifest_sha256)
        admission=mode.admit(binding)
        if selected==mode.CALIBRATION:need(args.calibration_wall_seconds==admission['profile_seconds'][str(args.profile)],'actual cloud calibration window')
        elif selected==mode.FIRST_FAULT:
            need(args.profile==0 and admission.get('diagnostic_profiles')==[0]and args.calibration_wall_seconds is None and args.full_block_budget is None and args.full_block_budget_sha256 is None,'only approved first-fault P0 and no legacy budget override')
        elif selected==mode.STAGE:
            row=binding.get('stage_coverage_budget')
            need(args.calibration_wall_seconds is None and args.full_block_budget is None and args.full_block_budget_sha256 is None,'no calibration/full flags in stage coverage')
            need(type(row)is dict and stage_budget is not None and stage_sha is not None and str(stage_budget)==row['path']and stage_sha==row['sha256'],'actual stage coverage cloud budget flags')
        else:
            need(selected==mode.FULL,'explicit cloud execution mode')
            need(args.calibration_wall_seconds is None and args.full_block_budget is not None and args.full_block_budget_sha256==binding['full_block_budget']['sha256']and str(args.full_block_budget)==binding['full_block_budget']['path'],'actual full cloud budget flags')
        return mode,admission
    need(selected not in(mode.STAGE,mode.FIRST_FAULT),'diagnostic mode requires actual cloud invocation')
    need(getattr(args,'cloud_binding_sha256',None)is None and executor_context(args)is None,'cloud consumer requires actual invocation binding')
    budget=getattr(args,'full_block_budget',None);budget_sha=getattr(args,'full_block_budget_sha256',None)
    if selected==mode.FULL:
        need(args.calibration_wall_seconds is None,'calibration override forbidden in full mode')
        need(budget is not None and budget_sha is not None,'full mode requires explicit reviewed budget')
        need(budget.is_absolute() and not any(p.is_symlink()for p in (budget,*budget.parents)),'regular absolute full budget')
        admission=mode.admit(dict(execution_mode=selected,full_block_budget=dict(path=str(budget),bytes=budget.stat().st_size,sha256=budget_sha)))
    else:
        need(budget is None and budget_sha is None,'full budget forbidden in calibration mode')
        if selected==mode.CALIBRATION and getattr(args,'validate_only',False)and args.calibration_wall_seconds is None:return mode,None
        need(args.calibration_wall_seconds is not None,'explicit calibration wall required; no implicit full20000')
        admission=mode.admit(dict(execution_mode=selected,calibration_seconds={str(i):args.calibration_wall_seconds for i in range(5)}))
    return mode,admission


def owned_execution_limits(limits, calibration_wall_seconds):
    result=dict(limits)
    if calibration_wall_seconds is not None:
        need(type(calibration_wall_seconds) is int and 0 < calibration_wall_seconds <= limits['wall_seconds'],'calibration wall within original bound')
        result['wall_seconds']=calibration_wall_seconds
    return result


def require_outer_context(declared):
    need(declared,'requires established strict outer supervisor; flag alone is not a cleanup proof')
    need(os.getpid()==os.getpgrp()==os.getsid(0),'consumer must be the owned outer session/group leader')


def main():
    global FULL_LOG_POLICY
    FULL_LOG_POLICY=None
    consumer_started=time.monotonic();consumer_cpu_started=time.process_time()
    a=argparse.ArgumentParser()
    a.add_argument('--artifact-manifest',type=pathlib.Path,required=True)
    a.add_argument('--artifact-manifest-sha256',required=True)
    a.add_argument('--local-build-result',type=pathlib.Path)
    a.add_argument('--local-build-result-sha256')
    a.add_argument('--samejob-full-binding',type=pathlib.Path)
    a.add_argument('--samejob-full-binding-sha256')
    a.add_argument('--samejob-diagnostic-binding',type=pathlib.Path)
    a.add_argument('--samejob-diagnostic-binding-sha256')
    a.add_argument('--cloud-binding',type=pathlib.Path)
    a.add_argument('--cloud-binding-sha256')
    a.add_argument('--builder-handoff',type=pathlib.Path)
    a.add_argument('--builder-handoff-sha256')
    a.add_argument('--executor-identity',type=pathlib.Path)
    a.add_argument('--executor-identity-sha256')
    a.add_argument('--expected-run-id',type=int,required=True)
    a.add_argument('--expected-launch-commit',required=True)
    a.add_argument('--expected-source-commit',required=True)
    a.add_argument('--runtime-bundle',type=pathlib.Path,required=True)
    a.add_argument('--local-runtime-abi',type=pathlib.Path,required=True)
    a.add_argument('--local-runtime-abi-sha256',required=True)
    a.add_argument('--profile',type=int,choices=range(5),required=True)
    a.add_argument('--output',type=pathlib.Path,required=True)
    a.add_argument('--validate-only',action='store_true')
    a.add_argument('--strict-outer-supervised',action='store_true')
    a.add_argument('--calibration-wall-seconds',type=int)
    a.add_argument('--execution-mode',choices=('BOUNDED_CALIBRATION','FULL_BLOCK_ACCEPTANCE','STAGE_COVERAGE_DIAGNOSTIC','P0_FIRST_FAULT_DIAGNOSTIC',HOST_DIAGNOSTIC_MODE),default='BOUNDED_CALIBRATION')
    a.add_argument('--full-block-budget',type=pathlib.Path)
    a.add_argument('--full-block-budget-sha256')
    a.add_argument('--stage-coverage-budget',type=pathlib.Path)
    a.add_argument('--stage-coverage-budget-sha256')
    a.add_argument('--owned-environment',type=pathlib.Path,required=True)
    a.add_argument('--owned-environment-sha256',required=True)
    args=a.parse_args()
    global OWNED_ENVIRONMENT
    OWNED_ENVIRONMENT=(args.owned_environment,args.owned_environment_sha256,owning_environment_identity(args))
    mode,admission=explicit_execution_admission(args)
    cloud_resources,resource_receipt=prepare_cloud_memory(args)
    require_outer_context(args.strict_outer_supervised)
    verify_frozen(args.artifact_manifest,args.artifact_manifest_sha256)
    source_relocation=approved_source_relocation(args,json.loads(args.artifact_manifest.read_text()))
    b, frozen=load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile,source_relocation,admission)
    download=verify_local_build(args,frozen)
    abi=verify_runtime_abi(args,frozen)
    runtime_bundle_sha=sha(args.runtime_bundle)
    need(b['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND','not final RTL replay')
    need(b['matrix_macs']==4096 and b['vector_lanes']==32,'fixed hardware resources')
    need(b['moe_reference_contract']=='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE','unapproved MoE contract')
    common=b['common'];need(set(common)=={'binary','sv','source_manifest','driver','build_receipt'},'common identity set')
    files={k:pin(v) for k,v in common.items()}
    receipt=json.loads(files['build_receipt'].read_text())
    need(receipt['config_only'] is False and receipt['software_arithmetic_substitution'] is False,'real DUT build only')
    for k in ('binary','sv','source_manifest','driver'):
        need(receipt[k+'_sha256']==common[k]['sha256'],'build provenance '+k)
    need(len(b['profiles'])==1 and b['profiles'][0]['id']==args.profile,'one requested profile')
    limits=b['limits']
    need(0 < limits['file_bytes'] <= 64*1024*1024, 'bounded log/output file cap')
    mode.validate_runtime_cycles(limits,admission,common['driver']['sha256'],args.artifact_manifest_sha256)
    need(0 < limits['wall_seconds'] <= 21600 and 0 < limits['cpu_seconds'] <= 21600, 'bounded job time')
    need(0 < limits['address_space_bytes'] <= 16*1024**3, 'bounded process AS')
    execution_limits=dict(limits)if admission is None and args.validate_only else mode.consumer_limits(limits,admission,args.profile)
    if cloud_resources is not None:execution_limits=cloud_resources[0].consumer_resource_limits(execution_limits,cloud_resources[1])
    if admission is not None and admission.get('budget_version')in(2,3):
        FULL_LOG_POLICY=full_log_module().effective_policy(admission,args.profile,limits['file_bytes'])
    resident_helper,moe_helper=observation_helpers()
    prepared=[]
    for p in b['profiles']:
        runtime=pin(p['runtime']);views=pin(p['views']);ref=pin(p['reference_result']);pin(p['provider_receipt'])
        rows,launch,obs=records(runtime)
        need(int(launch[2])==p['id'],'profile runtime identity')
        need([r[1] for r in rows if r[0]=='views']==[str(views)],'views binding')
        result=json.loads(ref.read_text());need(result['profile']['profile']==p['id'] and result['complete_block_tokens']==128 and result['exact_baseline_observer_output_equal'] is True,'complete official reference identity')
        need(result['hardware_executed'] is False,'independent reference only')
        want=expected(ref.parent,result,p['id'])
        for name,data in want.items(): need(name in obs and obs[name][2]==len(data),'full final span '+name)
        # Pinned loader itself verifies every mapped source SHA on open. Reject
        # reference-only mappings here as an additional anti-oracle guard.
        for line in views.read_text().splitlines()[1:]:
            fields=line.split('\t');need(len(fields)==16 and fields[0]=='map','views record')
            need('reference_only' not in pathlib.Path(fields[8]).parts,'golden preload forbidden')
        route_ref=None
        if p['id'] in (3,4):
            route_ref=(reference(ref.parent,result,'stage.mlp.gate.0.2',[128,8],'torch.int64'),reference(ref.parent,result,'stage.mlp.gate.0.1',[128,8],'torch.bfloat16'),reference(ref.parent,result,'stage.mlp.gate.0.0',[128,256],'torch.bfloat16'))
        prepared.append((p,runtime,obs,want,route_ref))
    if args.validate_only:
        print('VALIDATED_BINDING_ONLY_NO_DUT_NO_NUMERICAL_PASS');return
    need(not args.output.exists(),'fresh output directory');args.output.mkdir(parents=True)
    summary=dict(status='INCOMPLETE',numerical_pass=False,matrix_macs=b['matrix_macs'],vector_lanes=b['vector_lanes'],layer=b['layer'],artifact_manifest_sha256=args.artifact_manifest_sha256,artifact_identity=frozen['artifact_identity'],local_build_provenance=download,local_build_result_sha256=args.local_build_result_sha256,runtime_bundle_sha256=runtime_bundle_sha,startup_abi=abi,common=common,profiles=[],numeric_acceptance='NO_NEW_TOLERANCE_STRICT_BITWISE_DIAGNOSTICS_ONLY',final_rtl_executed=False)
    if executor_context(args) is not None:
        summary['executor_identity']=executor_context(args)
        summary['builder_handoff_sha256']=args.builder_handoff_sha256
        summary['resource_admission']=resource_receipt
        invocation=cloud_invocation(args)
        if invocation.get('executor_adaptation') is not None:
            summary['executor_adaptation_sha256']=invocation['executor_adaptation']['sha256']
            summary['workspace_loader_sha256']=invocation['workspace_loader']['sha256']
    if source_relocation is not None:
        summary['source_relocation']=source_relocation
        if host_context(source_relocation):summary.update(diagnostic_binding_sha256=source_relocation['diagnostic_binding']['sha256'],candidate_scope=HOST_DIAGNOSTIC_SCOPE)
        elif gdn32_context(source_relocation):summary.update(samejob_full_binding_sha256=source_relocation['full_binding']['sha256'],candidate_scope=source_relocation['candidate_scope'])
        elif source_relocation.get('candidate_scope') is not None:summary.update(model_candidate_review_sha256=source_relocation['model_candidate_review']['sha256'],candidate_scope=source_relocation['candidate_scope'])
    summary['execution_admission']={'scope':HOST_DIAGNOSTIC_SCOPE if admission['mode']==HOST_DIAGNOSTIC_MODE else 'P0_FIRST_FAULT_READONLY_SAME_FULL_M128_STIMULUS_NOT_NUMERICAL_ACCEPTANCE' if admission['mode']==mode.FIRST_FAULT else 'CALIBRATION_SAME_FULL_M128_STIMULUS' if admission['mode']==mode.CALIBRATION else 'STAGE_COVERAGE_DIAGNOSTIC_NOT_FULL_ACCEPTANCE' if admission['mode']==mode.STAGE else 'FULL_BLOCK_ACCEPTANCE_REQUIRED_TERMINAL_AND_REFERENCE', 'execution_mode':admission['mode'], 'reviewed_budget_sha256':admission['reviewed_budget_sha256'],'original_limits':dict(limits),'effective_limits':execution_limits,'outer_cleanup_proof_required':True,'peak_resource_qualification':'INCOMPLETE_SAMPLED','numerical_pass':False}
    if admission['mode']==HOST_DIAGNOSTIC_MODE:summary['execution_admission'].update(frozen_window=admission['frozen_window'],diagnostic_profiles=[0])
    if admission['mode']==mode.FIRST_FAULT:summary['execution_admission'].update(first_fault_document_sha256=admission['reviewed_budget_sha256'],diagnostic_profiles=[0],numerical_pass=False)
    if admission['mode']==mode.STAGE:summary['execution_admission']['stage_budget_sha256']=admission['reviewed_budget_sha256']
    if mode.finite_long(admission):summary['execution_admission']['finite_long_policy']=dict(admission['finite_long_policy'])
    if FULL_LOG_POLICY is not None:summary['execution_admission'].update(budget_version=admission['budget_version'],log_policy=FULL_LOG_POLICY)
    postprocess_limits=None
    if FULL_LOG_POLICY is not None:
        postprocess_limits=dict(wall_seconds=admission['profile_postprocess_wall_seconds'][str(args.profile)],cpu_seconds=admission['profile_postprocess_cpu_seconds'][str(args.profile)])
        summary['execution_admission']['postprocess_limits']=postprocess_limits
    for p,runtime,obs,want,route_ref in prepared:
        r=dict(profile=p['id'],complete_block_tokens=128,status='INCOMPLETE',numerical_pass=False,coverage_policy=b['coverage_policy']);summary['profiles'].append(r)
        postprocess=None
        try:
            # Reverify common frozen identity before AND after every process.
            load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile,source_relocation,admission)
            verify_local_build(args,frozen)
            verify_runtime_abi(args,frozen)
            need(sha(args.runtime_bundle)==runtime_bundle_sha,'runtime bundle changed')
            for v in list(common.values())+[p[k] for k in ('runtime','views','reference_result','provider_receipt')]: pin(v)
            target=args.output/('profile'+str(p['id']));log=args.output/('profile'+str(p['id'])+'.log')
            need(not target.exists() and not log.exists() and not log.with_suffix('.started.json').exists(),'fresh per-round observations')
            if FULL_LOG_POLICY is not None:need(time.monotonic()-consumer_started<=30 and time.process_time()-consumer_cpu_started<=30,'full V2 preflight within reserved 30 seconds')
            if admission['mode']==HOST_DIAGNOSTIC_MODE:
                execution_limits=mode.remaining_limits(execution_limits,admission,time.monotonic());summary['execution_admission']['effective_limits']=dict(execution_limits)
            if getattr(args,'samejob_full_binding',None)is not None:mode.require_consumer_window(args,time.monotonic())
            rc=(execute_streaming if FULL_LOG_POLICY is not None else execute)(files['binary'],runtime,target,log,execution_limits,model162_binary=gdn32_context(source_relocation));r['exit_code']=rc
            if FULL_LOG_POLICY is not None:postprocess=full_log_module().PostprocessBudget(postprocess_limits).start()
            load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile,source_relocation,admission)
            verify_local_build(args,frozen)
            verify_runtime_abi(args,frozen)
            need(sha(args.runtime_bundle)==runtime_bundle_sha,'runtime bundle changed')
            for v in list(common.values())+[p[k] for k in ('runtime','views','reference_result','provider_receipt')]: pin(v)
            need(rc==0,'DUT process failure')
            r['observation_round']=verify_current_observation_round(log,files['binary'],runtime)
            if admission['mode']==HOST_DIAGNOSTIC_MODE:raise HostDiagnosticBoundary() # no full final-value comparison/qualification in this scope
            terminal='COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile='+str(p['id'])+' '
            if FULL_LOG_POLICY is not None:
                markers=[terminal]+[f'HOST_FINAL_OUTPUT name={name} address={obs[name][1]} bytes={obs[name][2]} dtype={obs[name][3]} coverage=ACKNOWLEDGED_EVERY_BYTE' for name in want]
                if p['id']==0:markers.append(resident_helper.MARKER)
                if route_ref is not None:markers += ['HOST_FINAL_ROUTE_MAP bytes=8192 coverage=ACKNOWLEDGED_EVERY_BYTE','HOST_FINAL_ROUTER_LOGITS bytes=65536 dtype=BF16 coverage=ACKNOWLEDGED_EVERY_BYTE']
                text=full_log_module().LogView(log,full_log_module().read_capture(log,FULL_LOG_POLICY),markers,[terminal,'HOST_ROUTER_RAW_SCORE_V1','HOST_ROUTER_SELECTED_SCORE_V2']).verify()
            else:text=log.read_text()
            need(text.count(terminal)==1,'clean real DUT terminal receipt')
            # Every declared stage observation must exist with exact byte size.
            for name,(_,_,size,_) in obs.items():
                f=target/(name+'.actual.bin');need(f.is_file() and f.stat().st_size==size,'missing stage write coverage '+name)
            r['comparisons']={}
            for name,data in want.items():
                _,address,size,dtype=obs[name]
                marker=f'HOST_FINAL_OUTPUT name={name} address={address} bytes={size} dtype={dtype} coverage=ACKNOWLEDGED_EVERY_BYTE'
                need(text.count(marker)==1,'final acknowledged write receipt '+name)
                float_dtype='FP32' if p['id']==0 or name=='state_out' else 'BF16'
                r['comparisons'][name]=compare((target/(name+'.final.bin')).read_bytes(),data,float_dtype)
            if p['id']==0:
                reference_root=pathlib.Path(p['reference_result']['path']).parent
                reference_result=json.loads(pathlib.Path(p['reference_result']['path']).read_text())
                for name in ('gate','up'):
                    relative=pathlib.PurePosixPath(reference_result['tensor_records']['stage.mlp.'+name+'_proj.0']['file'])
                    need(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='reference_only','resident reference_only file required')
                    component=reference_root.resolve()
                    for part in relative.parts:
                        component=component/part
                        need(not component.is_symlink(),'resident reference symlink component')
                resident_refs={name:reference(reference_root,reference_result,'stage.mlp.'+name+'_proj.0',[1,128,8960],'torch.bfloat16') for name in ('gate','up')}
                r['comparisons'].update(resident_helper.compare_full128(target,text,resident_refs))
                for name in ('gate','up'):
                    r['comparisons']['resident_'+name].update(actual_nonfinite_elements=nonfinite((target/('resident_'+name+'.fp32.actual.bin')).read_bytes(),'FP32'),reference_nonfinite_elements=nonfinite(resident_refs[name],'BF16'))
            if route_ref is not None:
                need(text.count('HOST_FINAL_ROUTE_MAP bytes=8192 coverage=ACKNOWLEDGED_EVERY_BYTE')==1,'actual route map coverage')
                r['router']=router_compare((target/'router_token_map.final.bin').read_bytes(),*route_ref[:2])
                need(text.count('HOST_FINAL_ROUTER_LOGITS bytes=65536 dtype=BF16 coverage=ACKNOWLEDGED_EVERY_BYTE')==1,'actual router logits coverage')
                r['router']['bf16_dense_logits']=compare((target/'router_logits_bf16.final.bin').read_bytes(),route_ref[2],'BF16')
                r['router']['raw_fp32_selection_scores']='INCOMPLETE'
                r['router']['raw_probability_diagnostics']={'status':'INCOMPLETE'}
                try:
                    ref_path=pathlib.Path(p['reference_result']['path'])
                    raw_reference=moe_helper.reference_probabilities(ref_path.parent,json.loads(ref_path.read_text()),p['id'])
                    raw=moe_helper.observe(target,text,p['id'],raw_reference,(target/'router_token_map.final.bin').read_bytes(),route_ref[0])
                    r['router']['raw_probability_diagnostics']=raw
                    r['router']['raw_fp32_selection_scores']='COMPARED_DIAGNOSTIC_ONLY'
                except (ValueError,KeyError,OSError) as error:
                    r['router']['raw_probability_diagnostics']={'status':'INCOMPLETE','error':str(error),'error_class':type(error).__name__}
            r['execution_evidence']={key:True for key in required_acceptance.EXECUTION}
            classify_observed_profile(r, route_ref is not None)
        except HostDiagnosticBoundary:r['diagnostic_process_complete']=True
        except Exception as e: r['error']=str(e);r['error_class']=type(e).__name__
        finally:
            if admission['mode']==HOST_DIAGNOSTIC_MODE:summary['execution_admission']['effective_limits']=dict(execution_limits)
            if postprocess is not None:
                r['postprocess_observed']=postprocess.stop()
                if r['postprocess_observed']['budget_exceeded']:
                    r.setdefault('error','postprocess wall or CPU budget exhausted');r.setdefault('error_class','PostprocessBudgetExceeded')
        if FULL_LOG_POLICY is not None:
            try:r['log_capture']=full_log_module().read_capture(log,FULL_LOG_POLICY)
            except Exception as e:
                r.setdefault('error','full log capture unavailable');r.setdefault('error_class',type(e).__name__)
        r['qualification']=dict(status='INCOMPLETE',scope=HOST_DIAGNOSTIC_SCOPE,numerical_pass=False) if admission['mode']==HOST_DIAGNOSTIC_MODE else required_acceptance.evaluate(r)
        r['status']=r['qualification']['status']
        summary['status']='FAIL_EXACT_REFERENCE' if any(x['status']=='FAIL_EXACT_REFERENCE' for x in summary['profiles']) else 'INCOMPLETE'
        summary['numeric_acceptance']=HOST_DIAGNOSTIC_SCOPE if admission['mode']==HOST_DIAGNOSTIC_MODE else 'FULL_M128_EXACT_REFERENCE_PENDING_VERIFIED_OUTER_CLEANUP'
        (args.output/'RESULT.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Never assert Chisel/RTL numerical PASS from unapproved diagnostic policy.
    if admission['mode']==HOST_DIAGNOSTIC_MODE:print('SAME_JOB_P0_HOST_DIAGNOSTIC_LOCAL_RESULT_RECORDED_NOT_ACCEPTANCE')
    else:print(json.dumps(summary,indent=2))
    raise SystemExit(1 if summary['status']=='FAIL_EXACT_REFERENCE' else 2)

if __name__=='__main__': main()
