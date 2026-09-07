#!/usr/bin/env python3
"""Recheck every owner output and public command/descriptor byte.

This is an evidence consumer, never a DUT memory provider. Does not promote
synthetic weights, fused logical tensors, or a one-block run into model signoff.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.command import Command128,NULL_INDEX
from heteronpu.descriptor_chain import DescriptorRecord,validate_descriptor_chain
from heteronpu.l9_transport_contract import EXPECTED_LAYER0

def require(b,msg):
    if not b:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fields(line):
    pairs=re.findall(r'(\w+)=([^\s]+)',line);require(len(pairs)==len(dict(pairs)),'duplicate field');return dict(pairs)
def tagged(text,tag):return [fields(x) for x in text.splitlines() if x.startswith(tag+' ')]

def verify(out:Path,write_report:bool=True)->dict:
    require((out/'simulation.exit').read_text().strip()=='0','nonzero simulator exit')
    log=(out/'run.log').read_text();require(not re.search(r'HOST_BLOCK_FAIL|EXPECTED_ERROR|%Error|\bFatal\b',log),'failed/negative run')
    scope=json.loads((out/'generated/SCOPE.json').read_text());require(scope['host_commands'] and not scope['block_launch'] and scope['retained_matrix'] and scope['pinned_idma'],'wrong root')
    matrix_macs=scope.get('matrix_macs',512);require(type(matrix_macs) is int and matrix_macs in (512,4096),'Matrix specification')
    slices=matrix_macs//512
    f=json.loads((out/'fixture/manifest.json').read_text());H,F,G,J,D=(f['shape'][x] for x in ['H','F','HEADS','KVHEADS','HD']);T=f['tokens'];K=J*D;L=f.get('layers',1)
    require(type(L) is int and 1<=L<=3,'layer capacity');C=21*L
    require(f['commands']==C and f['descriptors']==215*L,'independent command/descriptor count')
    require((H,F,G,J,D) in [(64,128,2,1,32),(1536,8960,12,2,128)],'unknown shape');require(1<=T<=1024,'tokens')
    require(scope['hidden']==H and scope['ffn']==F,'elaboration mismatch')
    original=[x.opcode for x in EXPECTED_LAYER0]
    require([x['opcode'].lower() for x in f['schedule']]==original*L,'not original 21-op schedule per layer')
    td=out/'tensors';cb=(td/'host_commands.bin').read_bytes();db=(td/'host_descriptors.bin').read_bytes()
    require(cb==(out/'fixture/host_commands.bin').read_bytes() and db==(out/'fixture/host_descriptors.bin').read_bytes(),'executed metadata differs')
    require(len(cb)==((C*16+63)//64)*64 and len(db)==((f['descriptors']*16+63)//64)*64,'metadata length')
    rr={i:DescriptorRecord.unpack(int.from_bytes(db[i*16:i*16+16],'little')) for i in range(f['descriptors'])}
    for i,s in enumerate(f['schedule']):
        cmd=Command128.from_bytes(cb[i*16:i*16+16]);require(cmd.opcode.name==s['opcode'] and cmd.event_wait==i and cmd.event_signal==i+1,'public command mismatch')
        require([cmd.src0,cmd.src1,cmd.dst]==s['roots'],'root mismatch')
        for root,name in zip(s['roots'],[s['a'],s['b'],s['dst']]):
            if root==NULL_INDEX:require(name is None,'unexpected null');continue
            chain=validate_descriptor_chain(root,rr);t=f['tensors'][name]
            p=chain[0][1].payload;address=(p&((1<<48)-1))|((p>>64)<<48)
            dims=tuple((chain[1][1].payload>>(18*j))&0x3ffff for j in range(4))
            expected=tuple(t['dims'])+(1,)*(4-len(t['dims']))
            require(address==t['address'] and dims==expected and ((p>>52)&15)==7,'tensor binding mismatch')
    checks=tagged(log,'OWNER_TENSOR');ends=tagged(log,'HOST_BLOCK_ALL_OWNERS_PASS');completions=tagged(log,'OWNER_COMPLETION')
    require(len(ends)==1,'one full completion required');end=ends[0]
    require([int(x['pc']) for x in completions]==list(range(C)),'missing/duplicated/reordered completions')
    require(all(int(x['signal'])==i+1 for i,x in enumerate(completions)),'event mismatch')
    outputs=[(s['pc'],n) for s in f['schedule'] for n in s['outputs']]
    require([(int(x['pc']),x['name']) for x in checks]==outputs,'incomplete tensor coverage')
    expected_files={'input_x.f32le','host_commands.bin','host_descriptors.bin'}
    for _,n in outputs:expected_files|={n+'_actual.f32le',n+'_reference.f32le'}
    require({p.name for p in td.iterdir() if p.is_file()}==expected_files,'tensor file set mismatch')
    values=sum(f['tensors'][n]['words'] for _,n in outputs)
    require(values==L*T*(10*H+7*K+3*F),'independent output count mismatch')
    mac=T*(2*H*H+2*H*K+3*H*F)+T*(T+1)*H
    dense_steps=((T+15)//16)*(2*H*((H+31)//32)+2*H*((K+31)//32)+2*H*((F+31)//32)+F*((H+31)//32))
    executed=(dense_steps+T*(T+1)*H//16)*512
    mac*=L;executed*=L
    for k,v in dict(tokens=T,hidden=H,ffn=F,host_commands=C,completed=C,owner_jobs=19*L,matrix_commands=9*L,sfu_commands=11*L,kv_commands=L,
        checked_fp32=values,bit_differences=0,useful_macs=mac,executed_macs=executed,metadata_reads=C+f['descriptors'],write_ack_bytes=values*4,
        host_intermediate_writes=0,legacy_block_launch=0,original_matrix_instances=slices,original_idma_instances=1,score_ddr_accesses=0).items():
        require(int(end[k])==v,'counter mismatch '+k)
    require(int(end['read_bytes'])//64+int(end['write_ack_bytes'])//64==int(end['idma_transfers']),'iDMA conservation')
    require(int(end['request_stalls'])>0 and int(end['response_delay_cycles'])>0,'backpressure not covered')
    sv=(out/'generated/HostBlockTop.sv').read_text()
    if 'matrix_macs' in scope:
        from audit_matrix_topology import audit as topology_audit
        topology_audit(out/'generated/HostBlockTop.sv',matrix_macs)
        require(int(end['matrix_macs'])==matrix_macs and int(end['logical_matrix_engines'])==1,'peak/engine count mismatch')
    else:
        for module in ['qwen2_matrix_command_endpoint','idma_backend_rw_axi_flat_wrap']:
            require(len(re.findall(r'^\s+'+module+r'\s+\w+\s*\(',sv,re.M))==1,'wrong instance count '+module)
    require('module HeteroBF16FmaLane' not in sv,'standalone fallback arithmetic')
    sources=json.loads((out/'sources.sha256.json').read_text());require(all(isinstance(x,str) and re.fullmatch('[a-f0-9]{64}',x) for x in sources.values()),'source identity')
    for n in ['HostBlockCommands','QwenOwnerProtocol','Qwen2Block','HostBlockTop']:
        require('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'+n+'.scala' in sources,'missing DUT identity')
    idma=json.loads((out/'idma_identity.json').read_text());require(idma['commits']['idma']=='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d','iDMA drift')
    data={};details=[]
    for row,(pc,n) in zip(checks,outputs):
        count=f['tensors'][n]['words'];a=td/(n+'_actual.f32le');b=td/(n+'_reference.f32le');ab=a.read_bytes();bb=b.read_bytes()
        require(len(ab)==len(bb)==count*4 and ab==bb,'binary parity '+n)
        require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f',ab)),'nonfinite '+n)
        require(int(row['values'])==count and int(row['bit_differences'])==0,'log parity '+n)
        data[n]=ab;details.append(dict(pc=pc,tensor=n,values=count,sha256=sha(a)))
    # Independent checks recompute residuals from DUT producer dumps. For a
    # layer chain, the next X address is exactly previous Y; no memcpy is valid.
    rawx=(td/'input_x.f32le').read_bytes();require(len(rawx)==T*H*4,'input size')
    prefix=lambda layer: (f'l{layer}_' if 'layer_names' in f else '')
    for layer in range(L):
        pre=prefix(layer);require(data[pre+'cache_k']==data[pre+'k'] and data[pre+'cache_v']==data[pre+'v'],'KV copy continuity')
        if layer:
            prev=prefix(layer-1)+'y'
            require(f['tensors'][pre+'x']['address']==f['tensors'][prev]['address'],'layer input is not actual prior output address')
            rawx=data[prev]
        for dst,left,right in [('r',rawx,data[pre+'o']),('y',data[pre+'r'],data[pre+'down'])]:
            expect=b''.join(struct.pack('<f',a[0]+b[0]) for a,b in zip(struct.iter_unpack('<f',left),struct.iter_unpack('<f',right)))
            require(data[pre+dst]==expect,'actual-producer residual '+pre+dst)
    if L>1:
        ids=tagged(log,'LAYER_WEIGHT_ID');require([int(x['layer']) for x in ids]==list(range(L)),'missing layer weight identities')
        for name in ['wq','wg','wd']:require(len({x[name] for x in ids})==L,'weights repeated across layers: '+name)
    h=1469598103934665603
    for (u,) in struct.iter_unpack('<I',data[prefix(L-1)+'y']):h=((h^u)*1099511628211)&((1<<64)-1)
    require(h==int(end['output_fnv64'],16),'final hash')
    csvp=out/'all_owner_elements.csv.gz'
    if write_report:
        require(not csvp.exists(),'refuse comparison overwrite')
        with gzip.open(csvp,'wt',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['pc','tensor','index','actual_hex','reference_hex'])
            for pc,n in outputs:
                for i,(u,) in enumerate(struct.iter_unpack('<I',data[n])):writer.writerow([pc,n,i,f'{u:08x}',f'{u:08x}'])
    report={'schema':1,'status':'PASS_HOST_DRIVEN_QWEN2_OWNER_BLOCK','shape':f['shape'],'tokens':T,'matrix_macs':matrix_macs,'matrix_slices':slices,'logical_matrix_engines':1,'commands':C,'owner_jobs':19*L,'outputs':details,
        'checked_fp32':values,'bit_differences':0,'counters':end,'log_sha256':sha(out/'run.log'),'source_manifest_sha256':sha(out/'sources.sha256.json'),
        'generated_rtl_sha256':sha(out/'generated/HostBlockTop.sv'),'scope':{'all_original_opcode_sequence':True,'host_driven_each_owner':True,
        'full_21_record_original_gguf_image':False,'attention_streaming_fusion':([10,11,12] if L==1 else [[21*i+10,21*i+11,21*i+12] for i in range(L)]),'cold_contiguous_kv_only':True,'synthetic_weights':True,
        'official_model_quality':False,'multilayer':L>1,'full_network_q1024':False,'dc':False}}
    if L>1:report['layers']=L
    if write_report:
        report['full_comparison_sha256']=sha(csvp)
        with (out/'RESULT.json').open('x') as fjson:json.dump(report,fjson,indent=2);fjson.write('\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--read-only',action='store_true');a=p.parse_args()
    try:print(json.dumps(verify(a.output,not a.read_only),indent=2))
    except (ValueError,KeyError,OSError,TypeError) as e:raise SystemExit('HOST_BLOCK_EVIDENCE_FAILED: '+str(e))
