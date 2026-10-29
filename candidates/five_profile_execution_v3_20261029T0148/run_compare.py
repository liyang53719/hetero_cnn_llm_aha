#!/usr/bin/env python3
"""Run existing external-AXI DUT once per profile; no model arithmetic.
No tolerance contract is assumed. Bitwise equality is a diagnostic, NOT block PASS.
Binding paths are explicit; all hardware artifacts and inputs must remain immutable.
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
    with open(log,'xb') as f:
        p=subprocess.Popen([str(binary),str(runtime),str(output),str(limits['max_active_cycles'])],stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=bounded)
        try:
            deadline=time.monotonic()+limits['wall_seconds']
            while True:
                # WNOWAIT retains the leader (including a zombie) as PGID anchor.
                state=os.waitid(os.P_PID,p.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if state is not None:
                    return state.si_status if state.si_code==os.CLD_EXITED else -state.si_status
                if time.monotonic()>=deadline: raise TimeoutError('DUT wall deadline')
                time.sleep(0.2)
        finally:
            # Kill owned original group before reaping its leader; escaped sessions
            # require the outer established cgroup/subreaper supervisor.
            try: os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait()


def main():
    a=argparse.ArgumentParser();a.add_argument('--binding',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--validate-only',action='store_true');args=a.parse_args()
    b=json.loads(args.binding.read_text());need(b['schema']=='FIVE_PROFILE_EXTERNAL_DUT_V1','binding version')
    need(b['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND','not final RTL replay')
    need(b['matrix_macs']==4096 and b['vector_lanes']==32,'fixed hardware resources')
    need(b['moe_reference_contract']=='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE','unapproved MoE contract')
    common=b['common'];need(set(common)=={'binary','sv','source_manifest','driver','build_receipt'},'common identity set')
    files={k:pin(v) for k,v in common.items()}
    receipt=json.loads(files['build_receipt'].read_text())
    need(receipt['config_only'] is False and receipt['software_arithmetic_substitution'] is False,'real DUT build only')
    for k in ('binary','sv','source_manifest','driver'):
        need(receipt[k+'_sha256']==common[k]['sha256'],'build provenance '+k)
    need(len(b['profiles'])==5 and [p['id'] for p in b['profiles']]==list(range(5)),'all five profiles')
    limits=b['limits']
    need(0 < limits['file_bytes'] <= 64*1024*1024, 'bounded log/output file cap')
    need(0 < limits['max_active_cycles'] <= 1000000000, 'driver cycle bound')
    need(0 < limits['wall_seconds'] <= 21600 and 0 < limits['cpu_seconds'] <= 21600, 'bounded job time')
    need(0 < limits['address_space_bytes'] <= 16*1024**3, 'bounded process AS')
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
    summary=dict(status='INCOMPLETE',layer=b['layer'],binding_sha256=sha(args.binding),common=common,profiles=[],numeric_acceptance='NO_NEW_TOLERANCE_STRICT_BITWISE_DIAGNOSTICS_ONLY',final_rtl_executed=False)
    for p,runtime,obs,want,route_ref in prepared:
        r=dict(profile=p['id'],status='INCOMPLETE');summary['profiles'].append(r)
        try:
            # Reverify common frozen identity before AND after every process.
            for v in list(common.values())+[p[k] for k in ('runtime','views','reference_result','provider_receipt')]: pin(v)
            target=args.output/('profile'+str(p['id']));log=args.output/('profile'+str(p['id'])+'.log')
            rc=execute(files['binary'],runtime,target,log,b['limits']);r['exit_code']=rc
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
        except Exception as e: r['error']=str(e)
        (args.output/'RESULT.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Never assert Chisel/RTL numerical PASS from unapproved diagnostic policy.
    print(json.dumps(summary,indent=2))
    raise SystemExit(2)

if __name__=='__main__': main()
