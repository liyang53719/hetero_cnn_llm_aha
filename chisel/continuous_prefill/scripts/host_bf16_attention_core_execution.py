#!/usr/bin/env python3
"""Strict physical artifact auditor, never a production/numerical PASS issuer.

A later runner must bind a fresh process to built RTL/binary/toolchain/source
identities plus live independent arithmetic authorities. This module establishes
only consistency of supplied trace/DDR artifacts and the pinned fixture.
"""
from pathlib import Path
import argparse
import json
import host_bf16_attention_core_fixture as fixtures
from host_bf16_attention_core_fixture import require, inside, safe_file, file_sha, PHASES

MODES=('pass','cache-v-write-error','context-write-error')
PREFIX='HOST_ATTN_'
FIELDS={
 'BEGIN':'run mode epoch commands old_length old_generation',
 'READ':'run pc cycle address bytes',
 'WRITE_REQUEST':'run pc cycle address bytes final',
 'WRITE_ACK':'run pc cycle address bytes error final physical_write',
 'HOLD':'run pc cycle word',
 'COMMAND':'run pc cycle engine status signal ack_bytes owner_pc checkpoint_accepted',
 'RESULT_HOLD':'run cycle epoch pc status completed',
 'END':'run status completions successful issued_jobs metadata_reads ack_bytes physical_bytes receipt_bytes useful_macs read_beats read_ack_beats write_beats write_ack_beats read_bursts write_bursts idma_transfers checkpoint_accepted inferred_length inferred_generation reset_required',
 'PAIR':'same_dut resets_between_launches reference_injection cache_prefill launches',
}

def parse_events(text):
    events=[]
    for line in text.splitlines():
        if not line.startswith(PREFIX):continue
        values=line.split();kind=values[0][len(PREFIX):]
        require(kind in FIELDS,'unknown/failure event: '+kind)
        pairs=[x.split('=',1) for x in values[1:]]
        require(all(len(p)==2 for p in pairs),'invalid event syntax')
        fields=dict(pairs)
        require(len(fields)==len(pairs) and set(fields)==set(FIELDS[kind].split()),'duplicate/missing/extra event field')
        for key,value in fields.items():
            if key!='mode':require(value.isascii() and value.isdecimal(),'nondecimal event value')
        events.append((kind,fields))
    require(events,'no actual driver events');return events

def expect(event,**expected):
    require(all(event.get(k)==str(v) for k,v in expected.items()),'trace value drift: '+str(expected))

def allowed_owner_pc(next_completion,physical_pc):
    return physical_pc==next_completion if next_completion<8 else next_completion==8 and physical_pc==10

def apply_ack(memory,base,span,reference,address,size,error,physical_write):
    """Reconstruct only the audit image, including uncommitted error staging.

    The actual driver stores actual W data on error. This expected-state helper
    cannot mutate DUT memory and cannot turn a failing B response into success.
    """
    require(type(error) is int and error in (0,1) and inside(address,size,span['begin'],span['bytes']), 'invalid B ACK span')
    require(len(reference)==span['bytes'] and type(physical_write) is int and physical_write in (0,1),'reference/physical store contract')
    if physical_write:
        offset=address-span['begin'];memory[address-base:address-base+size]=reference[offset:offset+size]

def audit(fixture,outputs,log,mode):
    require(mode in MODES,'unsupported mode');fixture,outputs,log=map(Path,(fixture,outputs,log))
    admission=fixtures.verify(fixture);layout=admission['layout'];h=layout['header'];base=h['base']
    require(outputs.is_dir() and not outputs.is_symlink() and log.is_file() and not log.is_symlink(),'execution evidence paths')
    require(all(not p.is_symlink() for p in outputs.rglob('*')),'symlink execution evidence')
    memory=bytearray(bytes.fromhex('3cc35aa5')*((h['limit']-base)//4))
    for p in layout['preloads']:
        raw=safe_file(fixture,p['file']).read_bytes();require(len(raw)==p['bytes'],'preload bytes')
        require(inside(p['address'],len(raw),base,h['scratch']-base),'preload into writable memory')
        memory[p['address']-base:p['address']-base+len(raw)]=raw
    events=parse_events(log.read_text());cursor=0;reports=[];committed=0;all_written=set()
    for run,phase in enumerate(PHASES):
        l=layout['launches'][run];cs=l['commands'];spans=l['spans'];root=outputs/phase
        refs={s['name']:safe_file(fixture,'expected/'+phase+'/'+s['name']+'.bf16le').read_bytes() for s in spans}
        failing=run==1 and mode!='pass';fault=7 if mode=='cache-v-write-error' else 10
        expected_pcs=list(range(12)) if not failing else list(range(8)) if fault==7 else [*range(8),10]
        expected_success=len(expected_pcs)-int(failing);last_pc=expected_pcs[-1]
        require(cursor<len(events) and events[cursor][0]=='BEGIN','missing launch BEGIN')
        expect(events[cursor][1],run=run,mode=mode,epoch=9+run,commands=12,old_length=run,old_generation=run);cursor+=1
        require(committed==run,'second launch before accepted preceding core fence')
        sequence=0;pending=None;holds=0;last_hold=-1;last_cycle=-1;result_holds=0;last_result_cycle=-1;checkpoint=0;error_acks=0
        accepted=[0]*12;acked=[0]*12;final_acks=[0]*12;reads=[set() for _ in range(12)]
        published=set();written=set();write_beats=0;write_requests=0;read_beats=0;read_requests=0;snapshots={}
        totals=[sum(s['bytes'] for s in spans if s['pc']==pc) for pc in range(12)]
        while cursor<len(events) and events[cursor][0]!='END':
            kind,e=events[cursor];cursor+=1;require(kind not in ('PAIR','BEGIN'),'unexpected lifecycle event')
            expect(e,run=run);cycle=int(e['cycle']);require(cycle>=last_cycle,'cycle reversal');last_cycle=cycle
            if kind=='RESULT_HOLD':
                require(sequence==len(expected_pcs) and pending is None and cycle>last_result_cycle,'result before command/fence completion or duplicate hold')
                last_result_cycle=cycle
                expect(e,epoch=9+run,pc=last_pc,status=3 if failing else 0,completed=expected_success)
                result_holds+=1;continue
            require(result_holds==0 and sequence<len(expected_pcs),'traffic/completion after terminal result')
            pc=int(e['pc']);expected_pc=expected_pcs[sequence];next_public=sequence if sequence<8 else 8 if failing else sequence
            if kind in ('READ','WRITE_REQUEST','WRITE_ACK'):
                require(holds==0 and allowed_owner_pc(next_public,pc),'wrong execution pc or traffic under completion hold')
                address,size=int(e['address']),int(e['bytes'])
                require(size in range(64,1025,64) and address%64==0 and address%4096+size<=4096,'AXI physical geometry')
            if kind=='READ':
                require(pending is None and error_acks==0,'read overlapping write/after fault')
                c=cs[pc];src=inside(address,size,c['input'],c['input_bytes']);constant=inside(address,size,c['constant'],c['constant_bytes'])
                require(src or constant,'read outside actual typed input')
                if pc==10 and constant:
                    require(7 in published,'cache read before append completion')
                    require(inside(address,size,h['cache'],(run+1)*1024) or inside(address,size,h['cache']+h['capacity']*1024,(run+1)*1024),'inactive cache suffix read')
                    require(all(a in all_written|written for a in range(address,address+size,64)),'cache read before actual current/prior ACK')
                elif pc>=3 and (src or pc==7):
                    producers=[s for s in spans if inside(address,size,s['begin'],s['bytes'])]
                    require(len(producers)==1 and producers[0]['pc'] in published,'consumer before actual predecessor completion')
                reads[pc].update(range(address,address+size,64));read_beats+=size//64;read_requests+=1;continue
            if kind=='WRITE_REQUEST':
                require(pending is None and error_acks==0,'overlapping/after-fault write')
                matches=[s for s in spans if s['pc']==pc and inside(address,size,s['begin'],s['bytes'])]
                require(len(matches)==1 and not any(a in all_written|written for a in range(address,address+size,64)),'duplicate/wrong physical write')
                accepted[pc]+=size;final=int(e['final']);require(accepted[pc]<=totals[pc] and final==int(accepted[pc]==totals[pc]),'wrong final owner write')
                pending=(pc,address,size,final,cycle,matches[0]);write_requests+=1;write_beats+=size//64;continue
            if kind=='WRITE_ACK':
                require(pending is not None,'B ACK without write request');owner,address,size,final,request_cycle,span=pending
                expect(e,pc=owner,address=address,bytes=size,final=final,physical_write=1);error=int(e['error'])
                require(error in (0,1) and cycle>request_cycle and (not final or cycle-request_cycle>=53),'early/invalid B ACK')
                if error:
                    require(failing and owner==fault and final==1 and span['name']==('cache_v' if fault==7 else 'context') and address+size==span['begin']+span['bytes'],'wrong fault target')
                    error_acks+=1
                else:
                    acked[owner]+=size;final_acks[owner]+=final
                written.update(range(address,address+size,64))
                apply_ack(memory,base,span,refs[span['name']],address,size,error,1);pending=None;continue
            require(pc==expected_pc and pending is None,'unexpected completion pc or before all B ACKs')
            c=cs[pc];status=3 if failing and pc==fault else 0
            if kind=='HOLD':
                require(cycle>last_hold,'duplicate hold cycle');last_hold=cycle;holds+=1
                expect(e,word=pc|(c['engine']<<29)|(status<<32)|(c['signal']<<40));continue
            require(kind=='COMMAND' and holds>=(37 if pc==11 else 11) and cycle>last_hold,'unknown/early public completion')
            owner=10 if 8<=pc<=10 else pc
            if status==0:
                if pc!=11:
                    require(acked[owner]==accepted[owner]==totals[owner] and final_acks[owner]==1,'public completion before full owner ACK')
                    src=cs[owner]
                    ranges=[]
                    if 3<=owner<=7:ranges=[(src['input'],src['input_bytes']),(src['constant'],src['constant_bytes'])]
                    if owner==10:ranges=[(src['input'],src['input_bytes']),(h['cache'],(run+1)*1024),(h['cache']+h['capacity']*1024,(run+1)*1024)]
                    require(all(a in reads[owner] for start,size in ranges for a in range(start,start+size,64)),'missing actual dependency reads')
                published.add(pc)
            else:require(error_acks==1 and final_acks[owner]==0,'failed owner/final ACK inconsistency')
            if pc==11:
                require(not failing and sum(acked)==30720 and len(published)==12,'checkpoint before full attention core')
                checkpoint=1;committed+=1
            expect(e,engine=c['engine'],status=status,signal=c['signal'],ack_bytes=acked[pc],owner_pc=owner,checkpoint_accepted=checkpoint)
            name='writable_after_command'+str(pc)+'.bin';path=safe_file(root,name)
            require(path.read_bytes()==memory[h['scratch']-base:],'full writable snapshot/reference/old output drift: '+name);snapshots[name]=file_sha(path)
            sequence+=1;holds=0;last_hold=-1
        require(cursor<len(events) and sequence==len(expected_pcs) and pending is None and result_holds==7,'incomplete launch/result holds')
        e=events[cursor][1];cursor+=1
        metadata=sum(1+cs[pc]['records'] for pc in range(last_pc+1))
        completed_owners=[pc for pc in range(12) if totals[pc] and (not failing or pc<fault)]
        receipt=sum(totals[pc] for pc in completed_owners)
        macs=sum(totals[pc]//2*1024 for pc in completed_owners if pc<3)+((run+1)*4096 if 10 in completed_owners else 0)
        expect(e,run=run,status=3 if failing else 0,completions=len(expected_pcs),successful=expected_success,issued_jobs=8 if failing and fault==7 else 9,
               metadata_reads=metadata,ack_bytes=sum(acked),physical_bytes=sum(accepted),receipt_bytes=receipt,useful_macs=macs,write_beats=write_beats,write_ack_beats=write_beats,
               write_bursts=write_requests,checkpoint_accepted=checkpoint,inferred_length=committed,inferred_generation=committed,reset_required=int(failing))
        require(int(e['read_beats'])==int(e['read_ack_beats'])==metadata+read_beats and int(e['read_bursts'])==metadata+read_requests,'physical read counters')
        require(int(e['idma_transfers'])==int(e['read_bursts'])+write_requests and error_acks==int(failing),'sole transport/fault count')
        final=safe_file(root,'ddr_after.bin');require(final.read_bytes()==memory,'full final DDR mismatch')
        for s in spans:
            require(safe_file(root,'actual_'+s['name']+'.bf16le').read_bytes()==memory[s['begin']-base:s['begin']-base+s['bytes']],'actual output/physical store drift')
        require({p.name for p in root.iterdir()}=={'ddr_after.bin',*snapshots,*('actual_'+s['name']+'.bf16le' for s in spans)},'output artifact inventory')
        all_written.update(written)
        reports.append(dict(phase=phase,status=3 if failing else 0,checkpoint_accepted=bool(checkpoint),inferred_committed_length=committed,
                            successful_owner_receipt_bytes=receipt,physical_ack_bytes=sum(acked),physical_written_bytes=sum(accepted),snapshot_sha256=snapshots,ddr_sha256=file_sha(final)))
    require(cursor<len(events) and events[cursor][0]=='PAIR','missing same-DUT pair receipt')
    expect(events[cursor][1],same_dut=1,resets_between_launches=0,reference_injection=0,cache_prefill=0,launches=2);cursor+=1
    require(cursor==len(events) and {p.name for p in outputs.iterdir()}==set(PHASES),'extra pair events/artifacts')
    return dict(status='CONSISTENT_ATTENTION_CORE_ARTIFACTS_ONLY',actual_dut_identity_verified=False,numerical_acceptance_eligible=False,
                cache_registers_directly_observed=False,full_block_supported=False,model_m128_accepted=False,mode=mode,runs=reports,
                fixture_sha256=admission['manifest_sha256'],log_sha256=file_sha(log))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('fixture','outputs','log'):p.add_argument(name,type=Path)
    p.add_argument('--mode',choices=MODES,default='pass');a=p.parse_args()
    print(json.dumps(audit(a.fixture,a.outputs,a.log,a.mode),indent=2))
