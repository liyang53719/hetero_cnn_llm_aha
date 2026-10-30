#!/usr/bin/env python3
"""Run existing external-AXI DUT for one selected profile using the unchanged shared artifact manifest; no model arithmetic.
No tolerance contract is assumed. Bitwise equality is a diagnostic, NOT block PASS.
Binding paths are explicit; all hardware artifacts and inputs must remain immutable.
NEW lifecycle-only adapter: requires caller-owned strict outer supervision.
Calibration changes only the wall deadline, never stimulus, cycles or acceptance.
"""
import argparse, hashlib, json, os, pathlib, resource, signal, subprocess, time, struct


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


def compare(actual, wanted):
    need(len(actual)==len(wanted), 'actual output size')
    mismatches=sum(a!=b for a,b in zip(actual,wanted))
    first=next((i for i,(a,b) in enumerate(zip(actual,wanted)) if a!=b),None)
    return dict(bytes=len(actual),byte_mismatches=mismatches,first_mismatch_byte=first,
                actual_sha256=hashlib.sha256(actual).hexdigest(),expected_layout_sha256=hashlib.sha256(wanted).hexdigest())


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
    return {'ids':compare(actual_ids,ids),'normalized_bf16_weights':compare(actual_weights,weights),
            'coverage':'128x8_ACKNOWLEDGED_DUT_ROUTE_RECORDS','raw_fp32_selection_scores':'INCOMPLETE_NOT_STORED_IN_ROUTE_MAP'}


def execute(binary, runtime, output, log, limits):
    def bounded():
        resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(limits['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(limits['file_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    binary_sha=sha(binary);runtime_sha=sha(runtime)
    with open(log,'xb') as f:
        p=subprocess.Popen([str(binary),str(runtime),str(output),str(limits['max_active_cycles'])],stdout=f,stderr=subprocess.STDOUT,preexec_fn=bounded,env=runtime_abi_module().clean_env())
        try:
            started=pathlib.Path(log).with_suffix('.started.json')
            with started.open('x') as evidence:
                json.dump(dict(schema='ACTUAL_DUT_POPEN_V1',pid=p.pid,consumer_pid=os.getpid(),consumer_start_tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]),inherited_group=os.getpgrp(),inherited_session=os.getsid(0),binary_sha256=binary_sha,runtime_sha256=runtime_sha),evidence)
            deadline=time.monotonic()+limits['wall_seconds']
            while True:
                # WNOWAIT retains the leader (including a zombie) as PGID anchor.
                state=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if state is not None:
                    return state.si_status if state.si_code==os.CLD_EXITED else -state.si_status
                if time.monotonic()>=deadline: raise TimeoutError('DUT wall deadline')
                time.sleep(0.2)
        finally:
            # The DUT inherits the strict outer group/session: never create or
            # kill a nested group here. Reap this leader only; caller must retain
            # the consumer leader and prove full outer group absence afterward.
            if p.poll() is None:
                p.kill()
            p.wait()


OWNED_ENVIRONMENT=None

V3_DRIVER_SHA256='20df2692d41693491f0da03fa17f21886b9375ca599c83b5b75c0994841dc45e'

def verify_frozen(path,expected_sha):
    need(len(expected_sha)==64 and all(c in '0123456789abcdef' for c in expected_sha),'expected artifact SHA256 required')
    need(path.is_file() and not path.is_symlink() and path.stat().st_size<=65536,'bounded regular artifact manifest')
    need(sha(path)==expected_sha,'shared artifact manifest changed')

def artifact_identity(frozen):
    need(frozen['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2','frozen artifact schema')
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

def coverage_policy(profile,common,identity,bundle_root):
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('observation_contract.py')
    need(sha(path)=='ffb1c043cc1e21912a6ee6f11c7222e0885ebe89a38e68efce0027129e12617b','reviewed observation contract module')
    spec=importlib.util.spec_from_file_location('required_observation_policy',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.validate(profile,common,identity,bundle_root)

def load_binding(manifest,expected_sha,bundle_path,profile):
    verify_frozen(manifest,expected_sha)
    frozen=json.loads(manifest.read_text())
    identity=artifact_identity(frozen);commit=identity['source_commit']
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
    need(common['driver']['sha256']==V3_DRIVER_SHA256,'exact original V3 driver, no config-only replacement')
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
    b['coverage_policy']=coverage_policy(bundle['profiles'][0],common,identity,bundle_path.resolve().parent)
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

def verify_local_build(args,frozen):
    import importlib.util
    module_path=pathlib.Path(__file__).resolve().with_name('local_build_proof.py')
    need(sha(module_path)=='b58ebbff5578e641b58e7f2c4c1366a7c73f3a4861cf21e37cab7a01c46d8b56','reviewed local build proof')
    spec=importlib.util.spec_from_file_location('same_job_build_proof',module_path);local_build_proof=importlib.util.module_from_spec(spec);spec.loader.exec_module(local_build_proof)
    return local_build_proof.verify(args.local_build_result,args.local_build_result_sha256,args.artifact_manifest,args.artifact_manifest_sha256,frozen,args.expected_run_id,args.expected_launch_commit,args.expected_source_commit)


def runtime_abi_module():
    import importlib.util
    path=pathlib.Path(__file__).resolve().with_name('runtime_abi_owned.py')
    need(sha(path)=='ca7e9d9ce42634d57cd249e4407be436018ce5afbc18fe79e9bdac50b6496930','reviewed startup ABI module')
    spec=importlib.util.spec_from_file_location('pinned_startup_abi',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);need(OWNED_ENVIRONMENT is not None,'explicit owned environment admission');m.configure_owned_environment(*OWNED_ENVIRONMENT);return m

def verify_runtime_abi(args,frozen):
    root=args.artifact_manifest.resolve().parent
    binary=pin(dict(frozen['common']['binary'],path=str(root/frozen['common']['binary']['path'])))
    tool=pin(dict(frozen['tool_manifest'],path=str(root/frozen['tool_manifest']['path'])))
    result=runtime_abi_module().verify(args.local_runtime_abi,args.local_runtime_abi_sha256,binary,frozen['common']['binary']['sha256'],tool,frozen['tool_manifest']['sha256'])
    if getattr(args,'runtime_bundle',None) is not None:
        bundle=json.loads(args.runtime_bundle.read_text());r=bundle['local_runtime_abi']
        need(pin(r)==args.local_runtime_abi and r['sha256']==args.local_runtime_abi_sha256,'bundle startup ABI receipt binding')
    return result

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
    a=argparse.ArgumentParser()
    a.add_argument('--artifact-manifest',type=pathlib.Path,required=True)
    a.add_argument('--artifact-manifest-sha256',required=True)
    a.add_argument('--local-build-result',type=pathlib.Path,required=True)
    a.add_argument('--local-build-result-sha256',required=True)
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
    a.add_argument('--owned-environment',type=pathlib.Path,required=True)
    a.add_argument('--owned-environment-sha256',required=True)
    args=a.parse_args()
    global OWNED_ENVIRONMENT
    OWNED_ENVIRONMENT=(args.owned_environment,args.owned_environment_sha256,dict(run_id=args.expected_run_id,source_commit=args.expected_source_commit,launch_commit=args.expected_launch_commit))
    require_outer_context(args.strict_outer_supervised)
    b, frozen=load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile)
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
    need(0 < limits['max_active_cycles'] <= 1000000000, 'driver cycle bound')
    need(0 < limits['wall_seconds'] <= 21600 and 0 < limits['cpu_seconds'] <= 21600, 'bounded job time')
    need(0 < limits['address_space_bytes'] <= 16*1024**3, 'bounded process AS')
    execution_limits=owned_execution_limits(limits,args.calibration_wall_seconds)
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
    summary=dict(status='INCOMPLETE',layer=b['layer'],artifact_manifest_sha256=args.artifact_manifest_sha256,artifact_identity=frozen['artifact_identity'],local_build_provenance=download,local_build_result_sha256=args.local_build_result_sha256,runtime_bundle_sha256=runtime_bundle_sha,startup_abi=abi,common=common,profiles=[],numeric_acceptance='NO_NEW_TOLERANCE_STRICT_BITWISE_DIAGNOSTICS_ONLY',final_rtl_executed=False)
    summary['execution_admission']={'scope':'CALIBRATION_SAME_FULL_M128_STIMULUS' if args.calibration_wall_seconds is not None else 'ORIGINAL_FULL_M128_DIAGNOSTIC','original_limits':dict(limits),'effective_limits':execution_limits,'outer_cleanup_proof_required':True,'peak_resource_qualification':'INCOMPLETE_SAMPLED','numerical_pass':False}
    for p,runtime,obs,want,route_ref in prepared:
        r=dict(profile=p['id'],status='INCOMPLETE',coverage_policy=b['coverage_policy']);summary['profiles'].append(r)
        try:
            # Reverify common frozen identity before AND after every process.
            load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile)
            verify_local_build(args,frozen)
            verify_runtime_abi(args,frozen)
            need(sha(args.runtime_bundle)==runtime_bundle_sha,'runtime bundle changed')
            for v in list(common.values())+[p[k] for k in ('runtime','views','reference_result','provider_receipt')]: pin(v)
            target=args.output/('profile'+str(p['id']));log=args.output/('profile'+str(p['id'])+'.log')
            rc=execute(files['binary'],runtime,target,log,execution_limits);r['exit_code']=rc
            load_binding(args.artifact_manifest,args.artifact_manifest_sha256,args.runtime_bundle,args.profile)
            verify_local_build(args,frozen)
            verify_runtime_abi(args,frozen)
            need(sha(args.runtime_bundle)==runtime_bundle_sha,'runtime bundle changed')
            for v in list(common.values())+[p[k] for k in ('runtime','views','reference_result','provider_receipt')]: pin(v)
            need(rc==0,'DUT process failure')
            text=log.read_text();terminal='COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile='+str(p['id'])+' '
            need(text.count(terminal)==1,'clean real DUT terminal receipt')
            # Every declared stage observation must exist with exact byte size.
            for name,(_,_,size,_) in obs.items():
                f=target/(name+'.actual.bin');need(f.is_file() and f.stat().st_size==size,'missing stage write coverage '+name)
            r['comparisons']={}
            for name,data in want.items():
                _,address,size,dtype=obs[name]
                marker=f'HOST_FINAL_OUTPUT name={name} address={address} bytes={size} dtype={dtype} coverage=ACKNOWLEDGED_EVERY_BYTE'
                need(text.count(marker)==1,'final acknowledged write receipt '+name)
                r['comparisons'][name]=compare((target/(name+'.final.bin')).read_bytes(),data)
            if route_ref is not None:
                need(text.count('HOST_FINAL_ROUTE_MAP bytes=8192 coverage=ACKNOWLEDGED_EVERY_BYTE')==1,'actual route map coverage')
                r['router']=router_compare((target/'router_token_map.final.bin').read_bytes(),*route_ref[:2])
                need(text.count('HOST_FINAL_ROUTER_LOGITS bytes=65536 dtype=BF16 coverage=ACKNOWLEDGED_EVERY_BYTE')==1,'actual router logits coverage')
                r['router']['bf16_dense_logits']=compare((target/'router_logits_bf16.final.bin').read_bytes(),route_ref[2])
            r['status']='BITWISE_MATCH_DIAGNOSTIC' if all(x['byte_mismatches']==0 for x in r['comparisons'].values()) and (route_ref is None or (r['router']['ids']['byte_mismatches']==0 and r['router']['normalized_bf16_weights']['byte_mismatches']==0 and r['router']['bf16_dense_logits']['byte_mismatches']==0)) else 'BITWISE_MISMATCH_DIAGNOSTIC'
        except Exception as e: r['error']=str(e);r['error_class']=type(e).__name__
        (args.output/'RESULT.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Never assert Chisel/RTL numerical PASS from unapproved diagnostic policy.
    print(json.dumps(summary,indent=2))
    raise SystemExit(2)

if __name__=='__main__': main()
