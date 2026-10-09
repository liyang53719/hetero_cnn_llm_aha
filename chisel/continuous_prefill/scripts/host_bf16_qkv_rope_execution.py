#!/usr/bin/env python3
"""Independent seven-command ACK, predecessor, physical DDR and native audit.

Artifact validation alone does not establish DUT identity or a numerical pass.
Only run_case binds a new execution to the exact built RTL/binary/source set.
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import numpy as np
import host_bf16_qkv_rope_fixture as fixture_tools
from host_bf16_qkv_rope_fixture import ROOT, NAMES, SOURCES, require, file_sha as sha

BUILD_STATUS = 'BUILT_HOST_QKV_QKNORM_ROPE_NOT_NUMERICAL_PASS'
MODES = ('pass','last-write-error','activation-read-error','weight-read-error','gate-write-error','output-alias','reset-recovery')
PREFIX = 'HOST_QKV_ROPE_'
SCHEMA = {
    'BEGIN': 'run mode epoch commands',
    'READ_DEP': 'run pc cycle address bytes producer',
    'WRITE_REQUEST': 'run pc cycle address bytes final',
    'WRITE_ACK': 'run pc cycle address bytes error final',
    'HOLD': 'run pc cycle word',
    'COMMAND': 'run pc cycle engine status signal ack_bytes published',
    'RESULT_HOLD': 'run cycle epoch pc status completed',
    'END': 'run status epoch result_pc completions successful issued_jobs metadata_reads read_beats read_ack_beats write_beats write_ack_beats ack_bytes published_bytes useful_macs idma_transfers read_bursts write_bursts reset_required',
    'RECOVERY': 'same_dut unchanged_ddr reference_injection commands',
}


def _initial(fixture,h,cs,spans,mode):
    memory=bytearray(bytes.fromhex('3cc35aa5')*((h['limit']-h['base'])//4))
    def load(name,address,length):
        raw=(fixture/name).read_bytes();require(len(raw)==length and h['base']<=address and address+length<=h['limit'],'input allocation')
        memory[address-h['base']:address-h['base']+length]=raw
    load('host_commands.bin',h['cb'],h['cl']-h['cb']);load('host_descriptors.bin',h['db'],h['dl']-h['db'])
    load('activation.bf16le',h['aa'],h['rows']*2048)
    for c in cs[:3]:load('weight_'+c['name']+'.bf16le',c['constant'],c['constant_bytes'])
    load('q_gamma.bf16le',h['gamma_q'],512);load('k_gamma.bf16le',h['gamma_k'],512)
    load('trig.bf16le',h['trig']+h['position']*128,128)
    if mode=='output-alias':
        address=spans[0]['begin']-h['first']*1024;offset=h['db']+39*16-h['base']
        memory[offset+7:offset+13]=(address&((1<<48)-1)).to_bytes(6,'little');memory[offset+15]=address>>48
    return memory


def _events(log):
    result=[]
    for line in Path(log).read_text().splitlines():
        if not line.startswith(PREFIX):continue
        tokens=line.split();kind=tokens[0][len(PREFIX):];require(kind in SCHEMA,'unknown/failure event '+kind)
        pairs=[x.split('=',1) for x in tokens[1:]];require(all(len(x)==2 for x in pairs),'event field syntax')
        fields=dict(pairs);require(len(fields)==len(pairs) and set(fields)==set(SCHEMA[kind].split()),'duplicate/unknown/missing event fields')
        result.append((kind,fields))
    require(result,'no driver events');return result


def _expect(fields,**values):require(all(fields.get(k)==str(v) for k,v in values.items()),'event value drift: '+str(values))
def _inside(a,n,b,length):return n>0 and b<=a and a+n<=b+length

def _metrics(actual,native):
    a=np.frombuffer(actual,dtype='<u2');b=np.frombuffer(native,dtype='<u2');require(a.shape==b.shape and a.size,'native geometry')
    error=np.abs((a.astype('<u4')<<16).view('<f4').astype(np.float64)-(b.astype('<u4')<<16).view('<f4').astype(np.float64))
    require(np.isfinite(error).all(),'nonfinite native comparison')
    return dict(elements=int(a.size),bit_differences=int(np.count_nonzero(a!=b)),max_abs=float(error.max()),mean_abs=float(error.mean()),
                max_abs_limit=0.03125,mean_abs_limit=0.005,pass_gate=bool(error.max()<=0.03125 and error.mean()<=0.005))


def _native(fixture,actual):
    q=np.frombuffer(actual['q'],dtype='<u2').reshape(8,512);nq=np.frombuffer((fixture/'native_q.bf16le').read_bytes(),dtype='<u2').reshape(8,512)
    metrics={'q_content':_metrics(q[:,:256].tobytes(),nq[:,:256].tobytes()),'q_gate':_metrics(q[:,256:].tobytes(),nq[:,256:].tobytes())}
    require(actual['gate']==q[:,256:].tobytes(),'NormQ gate is not actual Dense Q gate bytes')
    for name in ('k','v','norm_q','norm_k'):metrics[name]=_metrics(actual[name],(fixture/('native_'+name+'.bf16le')).read_bytes())
    for role,heads in (('q',8),('k',2)):
        rope=np.frombuffer(actual['rope_'+role],dtype='<u2').reshape(heads,256);norm=np.frombuffer(actual['norm_'+role],dtype='<u2').reshape(heads,256)
        require(np.array_equal(rope[:,64:],norm[:,64:]),'RoPE tail differs from actual Norm predecessor')
        metrics['rope_'+role+'_prefix']=_metrics(rope[:,:64].tobytes(),(fixture/('native_rope_'+role+'_prefix.bf16le')).read_bytes())
    require(all(metrics[n]['pass_gate'] for n in ('q_content','q_gate','k','v')),'native projection operator threshold failure')
    # Composed SFU inputs can differ from native-framework predecessors. Their
    # diagnostics cannot replace the original same-input Norm/RoPE gates.
    for name in ('norm_q','norm_k','rope_q_prefix','rope_k_prefix'):
        metrics[name]['acceptance_claimed']=False
    return metrics


def verify_execution(fixture,outputs,log,mode,*,admit=True,session=None,reference_session=None,attention_reference_session=None):
    fixture,outputs,log=map(Path,(fixture,outputs,log));require(mode in MODES,'unknown mode')
    require(outputs.is_dir() and not outputs.is_symlink() and log.is_file() and not log.is_symlink(),'physical evidence path')
    for path in outputs.rglob('*'):
        require(not path.is_symlink() and (path.is_file() or path==outputs/'recovery' and path.is_dir()),'symlink/nonregular output artifact')
    authorities=dict(session=session,reference_session=reference_session,attention_reference_session=attention_reference_session)
    admitted=fixture_tools.verify(fixture,**authorities) if admit else None
    manifest=json.loads((fixture/'manifest.json').read_text());h,cs,spans=fixture_tools.layout(fixture)
    for name,record in manifest['files'].items():
        require(Path(name).name==name,'fixture evidence path escape')
        raw=fixture_tools.checked(fixture/name,record['sha256']);require(len(raw)==record['bytes'],'fixture evidence byte length')
    require([s['name'] for s in spans]==list(NAMES) and sum(s['bytes'] for s in spans)==24576,'output inventory')
    refs={s['name']:(fixture/('independent_'+s['name']+'.bf16le')).read_bytes() for s in spans}
    require(all(len(refs[s['name']])==s['bytes'] for s in spans),'terminal length')
    events=_events(log);cursor=0;reports=[]
    for run,selected in enumerate((mode,'pass') if mode=='reset-recovery' else (mode,)):
        root=outputs if run==0 else outputs/'recovery';fault=1 if selected=='output-alias' else 0 if selected=='reset-recovery' else 3 if selected=='gate-write-error' else 6
        st=0 if selected=='pass' else 9 if selected=='output-alias' else 3;expected_count=7 if selected=='pass' else fault+1
        require(cursor<len(events) and events[cursor][0]=='BEGIN','missing BEGIN');_expect(events[cursor][1],run=run,mode=selected,epoch=9+run,commands=7);cursor+=1
        expected=_initial(fixture,h,cs,spans,selected);published=set();pc=0;pending=None;last_cycle=-1;last_hold=-1;holds=0
        accepted=[0]*7;acked=[0]*7;final_acks=[0]*7;written=set();dependencies=set();requests=0;write_beats=0;error_acks=0;result_holds=0;result_cycle=-1;snapshots={}
        dependency_beats=0;dependency_bursts=0
        totals=[sum(s['bytes'] for s in spans if s['pc']==i) for i in range(7)]
        while cursor<len(events) and events[cursor][0]!='END':
            kind,e=events[cursor];cursor+=1;require(kind not in ('BEGIN','RECOVERY'),'unexpected lifecycle event');_expect(e,run=run)
            cycle=int(e['cycle']);require(cycle>=last_cycle,'event cycle reversal');last_cycle=cycle
            if kind=='RESULT_HOLD':
                require(pc==expected_count and pending is None and cycle>result_cycle,'early/duplicate result hold');result_cycle=cycle;result_holds+=1
                _expect(e,epoch=9+run,pc=expected_count-1,status=st,completed=len(published));continue
            require(result_holds==0 and pc<expected_count and int(e['pc'])==pc,'wrong/late command identity')
            c=cs[pc]
            if kind=='READ_DEP':
                require(pc>=3 and holds==0 and pending is None and error_acks==0,'dependency read outside execution/after fault')
                address,n,producer=(int(e[k]) for k in ('address','bytes','producer'))
                require(n%64==0 and n<=1024 and address%64==0 and _inside(address,n,c['input'],c['input_bytes']),'dependency address/window')
                matches=[s for s in spans if _inside(address,n,s['begin'],s['bytes'])]
                require(len(matches)==1 and matches[0]['pc']==producer and producer in published,'read before actual predecessor publication')
                dependencies.update(range(address,address+n));dependency_beats+=n//64;dependency_bursts+=1;continue
            if kind=='WRITE_REQUEST':
                require(pending is None and holds==0 and error_acks==0,'overlapping/late/post-fault write request');address,n,final=(int(e[k]) for k in ('address','bytes','final'))
                require(n in range(64,1025,64) and address%64==0 and (address%4096)+n<=4096,'AXI write geometry')
                matches=[s for s in spans if s['pc']==pc and _inside(address,n,s['begin'],s['bytes'])]
                require(len(matches)==1 and not any(a in written for a in range(address,address+n)),'write span/duplicate physical address')
                accepted[pc]+=n;require(accepted[pc]<=totals[pc] and final==int(accepted[pc]==totals[pc]),'incorrect final multi-span write')
                pending=(address,n,final,cycle,matches[0]);requests+=1;write_beats+=n//64;continue
            if kind=='WRITE_ACK':
                require(pending is not None and holds==0,'ACK without request');address,n,final,requested,span=pending
                _expect(e,address=address,bytes=n,final=final);error=int(e['error']);require(error in (0,1) and cycle>requested,'early/invalid ACK')
                if final:require(cycle-requested>=53,'final write ACK delay missing')
                if error:
                    error_acks+=1;require(pc==fault and selected in ('last-write-error','gate-write-error'),'unexpected B error')
                    require((selected=='last-write-error' and final==1) or (selected=='gate-write-error' and span['name']=='gate' and address+n==span['begin']+span['bytes']),'wrong injected write target')
                else:
                    offset=address-span['begin'];expected[address-h['base']:address-h['base']+n]=refs[span['name']][offset:offset+n]
                    written.update(range(address,address+n));acked[pc]+=n;final_acks[pc]+=final
                pending=None;continue
            if kind=='HOLD':
                require(pending is None and cycle>last_hold,'early/duplicate completion hold');last_hold=cycle;holds+=1
                status=0 if selected=='pass' or pc<fault else st
                _expect(e,word=pc|(c['engine']<<29)|(status<<32)|(c['signal']<<40));continue
            require(kind=='COMMAND' and pending is None and holds>=11 and cycle>last_hold,'unknown/early completion')
            status=0 if selected=='pass' or pc<fault else st
            _expect(e,engine=c['engine'],status=status,signal=c['signal'],ack_bytes=acked[pc],published=int(status==0))
            if status==0:
                require(acked[pc]==accepted[pc]==totals[pc] and final_acks[pc]==1,'command completed before all primary/side ACKs')
                if pc>=3:require(all(a in dependencies for a in range(c['input'],c['input']+c['input_bytes'])),'missing actual input reads')
                published.add(pc)
            else:
                require(final_acks[pc]==0,'failed command published final ACK')
                if selected in ('output-alias','activation-read-error','weight-read-error','reset-recovery'):
                    require(accepted[pc]==acked[pc]==0,'rejected alias/initial read fault wrote memory')
            filename='writable_after_command'+str(pc)+'.bin';raw=(root/filename).read_bytes()
            require(raw==expected[h['scratch']-h['base']:],'physical snapshot mismatch: '+filename);snapshots[filename]=sha(root/filename)
            pc+=1;holds=0;last_hold=-1;dependencies=set()
        require(cursor<len(events) and pc==expected_count and pending is None and result_holds==7,'missing result/completion/drain')
        end=events[cursor][1];cursor+=1
        jobs=1 if selected=='output-alias' else expected_count;metadata=sum(1+c['records'] for c in cs[:expected_count]);macs=sum(spans[j]['bytes']//2*1024 for j in published if j<3)
        _expect(end,run=run,status=st,epoch=9+run,result_pc=expected_count-1,completions=expected_count,successful=len(published),issued_jobs=jobs,
                metadata_reads=metadata,write_beats=write_beats,write_ack_beats=write_beats,ack_bytes=sum(acked),published_bytes=sum(totals[j] for j in published),
                useful_macs=macs,write_bursts=requests,reset_required=int(selected!='pass'))
        require(int(end['read_beats'])==int(end['read_ack_beats']) and int(end['read_beats'])>=metadata+dependency_beats
                and int(end['read_bursts'])>=metadata+dependency_bursts and int(end['read_beats'])>=int(end['read_bursts'])
                and int(end['idma_transfers'])==int(end['read_bursts'])+requests,'read/iDMA counts')
        require(error_acks==int(selected in ('last-write-error','gate-write-error')),'missing/extra error ACK')
        require((root/'ddr_after.bin').read_bytes()==expected,'final physical DDR mismatch')
        actual={}
        for s in spans:
            name=s['name'];actual[name]=(root/('actual_'+name+'.bf16le')).read_bytes()
            require(actual[name]==expected[s['begin']-h['base']:s['begin']-h['base']+s['bytes']],'actual dump/physical mismatch')
            require((root/('reference_'+name+'.bf16le')).read_bytes()==refs[name],'driver reference differs from pinned integer/C terminal')
        native=_native(fixture,actual) if selected=='pass' else None
        expected_files={'ddr_after.bin',*snapshots,*('actual_'+n+'.bf16le' for n in NAMES),*('reference_'+n+'.bf16le' for n in NAMES)}
        if mode=='reset-recovery' and run==0:expected_files.add('recovery')
        require(set(p.name for p in root.iterdir())==expected_files,'unknown/missing output artifact')
        reports.append(dict(mode=selected,status=st,successful_commands=len(published),ack_bytes=sum(acked),published_bytes=sum(totals[j] for j in published),
                            independent_terminal_checked=True,physical_ddr_bytes_checked=len(expected),writable_snapshot_sha256=snapshots,
                            ddr_after_sha256=sha(root/'ddr_after.bin'),actual_sha256={n:sha(root/('actual_'+n+'.bf16le')) for n in NAMES},native_operator_metrics=native))
    if mode=='reset-recovery':
        require(cursor<len(events) and events[cursor][0]=='RECOVERY','missing same-DUT recovery');_expect(events[cursor][1],same_dut=1,unchanged_ddr=1,reference_injection=0,commands=7);cursor+=1
    require(cursor==len(events),'extra execution events')
    return dict(status='PASS_HOST_QKV_QKNORM_ROPE_ARTIFACT_AUDIT_ONLY',scope='QKV_QKNORM_PARTIAL_ROPE_ONLY',mode=mode,runs=reports,
                actual_dut_identity_verified=False,numerical_acceptance_eligible=False,full_block_supported=False,
                fixture_sha256=sha(fixture/'manifest.json'),log_sha256=sha(log),source_admission=admitted,
                original_operator_gate_pass=manifest['original_operator_gate_pass'],
                original_operator_checks=manifest['original_operator_checks'],
                input_sha256=manifest['input_sha256'],
                native_full_block_failures=manifest['native_full_block_failures'])


def _build_identity(build,required_sources=None):
    ready=json.loads((build/'build_ready.json').read_text());require(ready['status']==BUILD_STATUS and ready['numerical_pass'] is False,'build-only receipt required')
    require(sha(build/'obj/VHostBlockTop')==ready['binary_sha256'] and sha(build/'generated/HostBlockTop.sv')==ready['rtl_sha256'],'binary/RTL drift')
    require(sha(build/'sources.sha256.json')==ready['source_manifest_sha256'],'source manifest drift')
    sources=json.loads((build/'sources.sha256.json').read_text())
    require(all(sources.get(name)==sha(ROOT/name) for name in SOURCES),'seven-command source closure missing or changed')
    if required_sources is not None:
        require(all(sources.get(name)==digest==sha(ROOT/name) for name,digest in required_sources.items()),'live reference source closure missing or changed')
    return {str(p):sha(p) for p in (build/'build_ready.json',build/'obj/VHostBlockTop',build/'generated/HostBlockTop.sv',build/'sources.sha256.json',build/'hardfloat.sha256.json')}


def run_case(build,fixture,mode='pass',*,label=None,session=None,reference_session=None,attention_reference_session=None,timeout_seconds=3600):
    build,fixture=Path(build),Path(fixture);require(mode in MODES,'unknown case');label=mode if label is None else label
    require(isinstance(label,str) and label and all(c.isalnum() or c in '_-' for c in label),'invalid label')
    require(type(timeout_seconds) is int and 1<=timeout_seconds<=3600,'invalid bounded case timeout')
    authorities=dict(session=session,reference_session=reference_session,attention_reference_session=attention_reference_session)
    admission=fixture_tools.verify(fixture,**authorities)
    require(admission['original_operator_gate_pass'] is True,'BLOCKED_ORIGINAL_NORM_ROPE_OPERATOR_GATE')
    identity=_build_identity(build,admission['source_sha256'])
    def sources_check(stage):
        ready=json.loads((build/'build_ready.json').read_text())
        with (build/(label+'_'+stage+'_source_verify.log')).open('w') as log:
            subprocess.run([sys.executable,str(ROOT/'chisel/continuous_prefill/scripts/production_source_identity.py'),'verify',str(ROOT),str(build),ready['hardfloat_source']],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    sources_check('initial');output=build/label;log=build/(label+'.log');require(not output.exists() and not log.exists(),'fresh execution output required')
    try:
        with log.open('w') as stream:
            process=subprocess.run([str(build/'obj/VHostBlockTop'),str(fixture),str(output),mode],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        (build/(label+'.exit')).write_text('TIMEOUT\n')
        raise ValueError('production chain timeout: '+label+' mode='+mode) from error
    (build/(label+'.exit')).write_text(str(process.returncode)+'\n');require(process.returncode==0,'seven-command actual execution failed')
    result=verify_execution(fixture,output,log,mode,**authorities);require(_build_identity(build,admission['source_sha256'])==identity,'DUT changed during execution');sources_check('final')
    result.update(status='PASS_PRODUCTION_HOST_QKV_QKNORM_ROPE_CASE',actual_dut_identity_verified=True,numerical_acceptance_eligible=mode in ('pass','reset-recovery'),
                  source_immutability_verified=True,binary_sha256=identity[str(build/'obj/VHostBlockTop')],rtl_sha256=identity[str(build/'generated/HostBlockTop.sv')],build_ready_sha256=identity[str(build/'build_ready.json')])
    (build/(label+'.result.json')).write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('fixture','outputs','log'):p.add_argument(name,type=Path)
    p.add_argument('mode',choices=MODES);a=p.parse_args();print(json.dumps(verify_execution(a.fixture,a.outputs,a.log,a.mode),indent=2))
