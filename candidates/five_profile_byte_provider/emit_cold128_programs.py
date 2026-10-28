#!/usr/bin/env python3
"""Source-derived Record128 programs. Emits metadata ONLY; never numerical PASS.
Readonly allocations require separately pinned real payload materialization.
No reference intermediates or selected expert IDs are accepted as inputs.
"""
import argparse, hashlib, json, math
from pathlib import Path
import attention_moe_policies as am
NULL=0xffffff
ALIGN=lambda x:(x+63)&~63
PROFILES={0:('Qwen2-1.5B',1536,8960,12,0),1:('Qwen3.5-0.8B-L0',1024,3584,0,16),2:('Qwen3.5-0.8B-L3',1024,3584,8,0),3:('Qwen3.5-35B-A3B-L0',2048,512,0,32),4:('Qwen3.5-35B-A3B-L3',2048,512,16,0)}
def rec(kind,payload,nxt=NULL):
    if not(0<=kind<256 and 0<=payload<1<<72 and 0<=nxt<=NULL):raise ValueError('record range')
    return kind|(nxt<<32)|(payload<<56)
def program_payload(op=0x30,inputs=2,it=5,ot=5,gdn=True):return op|(inputs<<16)|(1<<24)|(it<<32)|(ot<<36)|(16<<40)|((1 if gdn else 0)<<48)
def gpolicy(op,role=0):return 3|(op<<8)|(1<<24)|(role<<26)
class Builder:
    def __init__(self,p):
        self.profile=p; self.t={};self.records=[];self.commands=[];self.schedule=[]
        self.ro=0x100000;self.rw=0x1000000000
    def alloc(self,name,dims,ro=False,dtype=5,virtual=False):
        if name in self.t:raise ValueError('duplicate tensor')
        size=math.prod(dims)*(2 if dtype==5 else 4)
        a=ALIGN(self.ro if ro else self.rw)+64
        if ro:self.ro=a+ALIGN(size)
        else:self.rw=a+ALIGN(size)
        self.t[name]={'address':a,'dims':list(dims),'dtype':dtype,'bytes':size,'readonly':ro,'virtual':virtual,'initialization':'REAL_INPUT_OR_WEIGHT_REQUIRED' if ro else 'UNINITIALIZED_DUT_OUTPUT_OR_SCRATCH'}
        return name
    def tensor(self,name):
        t=self.t[name];dims=t['dims']+[1]*(4-len(t['dims']));a=t['address'];r=len(self.records)
        base=(a&((1<<48)-1))|(t['dtype']<<52)|(len(t['dims'])<<60)|((a>>48)<<64)
        strides=(dims[1]*dims[2]*dims[3],dims[2]*dims[3],dims[3])
        if any(x>=1<<18 for x in dims) or any(x>=1<<23 for x in strides):raise ValueError('tensor field range')
        self.records += [rec(1,base,r+1),rec(2,sum(x<<(18*i) for i,x in enumerate(dims)),r+2),rec(3,sum(x<<(24*i) for i,x in enumerate(strides)))]
        return r
    def emit(self,name,a,b,d,policies,opcode=0x30,extras=(),outputs=None):
        roots=[self.tensor(x) if x else NULL for x in (a,b,d)]
        er=[self.tensor(x) for x in extras]
        pp=policies(er) if callable(policies) else policies
        if pp:
            start=len(self.records); self.records[roots[0]+2]=(self.records[roots[0]+2]&~(NULL<<32))|(start<<32)
            self.records += [rec(k,v,start+i+1 if i+1<len(pp) else NULL) for i,(k,v) in enumerate(pp)]
        pc=len(self.commands);engine=2 if opcode in (0x20,0x23,0x24) else 4 if opcode==0x41 else 3
        self.commands.append(opcode|(engine<<8)|(pc<<24)|((pc+1)<<40)|(roots[0]<<56)|(roots[1]<<80)|(roots[2]<<104))
        self.schedule.append({'pc':pc,'name':name,'a':a,'b':b,'d':d,'roots':roots,'extras':list(extras),'outputs':outputs if outputs is not None else [d]})
    def gdn(self,name,op,role,a,b,d,extras=(),outputs=None):
        if op==2:
            m,n=self.t[d]['dims'];k=self.t[a]['dims'][1]; pp=[(0x10,m|(n<<16)|(k<<32)),(0x12,int('004000040020ffffff',16)),(0x21,gpolicy(op,role))]
        else:
            pp=lambda er:[(0x20,program_payload(it=7 if op==4 else 5,ot=7 if op==3 else 5)),(0x21,gpolicy(op,role))]+([(0x22 if op==1 else 0x23,er[0]|((er[1] if len(er)>1 else NULL)<<24))] if er else [])
        self.emit(name,a,b,d,pp,0x20 if op==2 else 0x30,extras,outputs)
    def dense(self,name,role,a,w,d):self.gdn(name,2,role,a,w,d)
    def finish(self):
        if len(self.commands)>64:raise ValueError('maxCommands')
        cb=b''.join(x.to_bytes(16,'little') for x in self.commands);db=b''.join(x.to_bytes(16,'little') for x in self.records)
        launch={'version':1,'profileId':self.profile,'commandBase':0x10000,'commandLimit':0x10000+ALIGN(len(cb)),'commands':len(self.commands),'descriptorBase':0x20000,'descriptorLimit':0x20000+ALIGN(len(db)),'descriptors':len(self.records),'epoch':1,'regions':[{'base':0x10000,'limit':0x100000,'read':True,'write':False},{'base':0x100000,'limit':ALIGN(self.ro),'read':True,'write':False},{'base':0x1000000000,'limit':ALIGN(self.rw),'read':True,'write':True},{'base':0x2000000000,'limit':0x2080000000,'read':True,'write':True}]}
        return cb,db,{'status':'METADATA_EMITTED_NOT_DUT_VALIDATED','commands_source_sha256':'d25425714cd0b123a0b5924568311f5faa8c9116a3026d53f3e5ebcfae0df108','requires_rank3_m128_scratch_admission':self.profile in (1,3),'tokens':128,'launch':launch,'schedule':self.schedule,'tensors':self.t,'intermediate_preloads':0,'expert_id_injection':False,'numeric_pass':False,'qknorm_recipe':('C2_Torch210CpuDefault256_EXISTING_REFERENCE_CONTRACT' if self.profile in (2,4) else None),'weights_materialized':False,'requires_real_readonly_payloads':True}
def common(p):
    _,h,f,heads,vh=PROFILES[p];b=Builder(p)
    for name,dims,dt in [('input',(128,h),5),('input_gamma',(1,h),5),('post_gamma',(1,h),5)]:b.alloc(name,dims,True,dt)
    b.alloc('input_norm',(128,h));b.gdn('input_norm',8,0,'input','input_gamma','input_norm')
    if vh:
        c=4096+vh*128;vw=vh*128
        for role,n,name in [(0,c,'qkv'),(1,vw,'z'),(2,vh*2,'ab')]:
            b.alloc(name+'_weight',(h,n),True);b.alloc(name,(128,n));b.dense(name,role,'input_norm',name+'_weight',name)
        for name,dims,dt in [('conv_weight',(c,4),5),('history_in',(c,4),5),('a_log',(1,vh),7),('dt_bias',(1,vh),5),('state_in',(vh,16384),7),('gated_gamma',(1,128),7)]:b.alloc(name,dims,True,dt)
        for name,dims,dt in [('conv',(128,c),5),('history_out',(c,4),5),('prepared',(128,vh*400),7),('chunk',(128,vw),5),('state_out',(vh,16384),7),('chunk_scratch',(vh,128,3280),7),('gated_norm',(128,vw),5)]:b.alloc(name,dims,False,dt)
        b.gdn('conv',1,0,'qkv','conv_weight','conv',('history_in','history_out'),['conv','history_out'])
        b.gdn('rawprep',3,0,'conv','ab','prepared',('a_log','dt_bias'))
        b.gdn('chunk',4,0,'prepared','state_in','chunk',('state_out','chunk_scratch'),['chunk','state_out'])
        b.gdn('gated_norm',5,0,'chunk','z','gated_norm',('gated_gamma',))
        mixer='gated_norm';ow=vw
    else:
        for role,n,name in [(0,heads*512,'q'),(1,512,'k'),(2,512,'v')]:
            b.alloc(name+'_weight',(h,n),True);b.alloc(name,(128,n));b.dense(name,role,'input_norm',name+'_weight',name)
        for name,dims in [('q_gamma',(1,256)),('k_gamma',(1,256)),('trig',(128,64))]:b.alloc(name,dims,True)
        for name,dims in [('qn',(128,heads*256)),('kn',(128,512)),('qgate',(128,heads*256)),('qr',(128,heads*256)),('kr',(128,512)),('cache',(2,128,512)),('score',(heads,128,128)),('prob',(heads,128,128)),('context',(128,heads*256)),('gated_context',(128,heads*256))]:b.alloc(name,dims,virtual=name in ('score','prob'))
        b.emit('qknorm_q','q','q_gamma','qn',lambda er:am.qknorm(0,er[0],recipe=0xC2),0x32,('qgate',),['qn','qgate'])
        b.emit('qknorm_k','k','k_gamma','kn',am.qknorm(1,recipe=0xC2),0x32)
        b.emit('rope_q','qn','trig','qr',am.rope(0),0x34)
        b.emit('rope_k','kn','trig','kr',am.rope(1),0x34)
        b.emit('kv_append','kr','v','cache',am.attention_core(0),0x41)
        b.emit('qk','qr','cache','score',am.attention_core(1),0x23)
        b.emit('softmax','score',None,'prob',am.attention_core(2),0x33)
        b.emit('pv','prob','cache','context',am.attention_core(3),0x24)
        b.emit('attention_gate','qgate','context','gated_context',am.attention_output(0))
        mixer='gated_context';ow=heads*256
    b.alloc('o_weight',(ow,h),True);b.alloc('o',(128,h));b.dense('output_projection',3,mixer,'o_weight','o')
    b.alloc('residual1',(128,h))
    if vh:b.gdn('residual1',9,0,'input','o','residual1')
    else:b.emit('residual1','input','o','residual1',am.attention_output(1))
    b.alloc('post_norm',(128,h));b.gdn('post_norm',8,1,'residual1','post_gamma','post_norm')
    if p in (1,2):
        for role,name in [(4,'gate'),(5,'up')]:
            b.alloc(name+'_weight',(h,f),True);b.alloc(name,(128,f));b.dense(name,role,'post_norm',name+'_weight',name)
        b.alloc('silu',(128,f));b.gdn('silu',9,1,'gate','up','silu')
        b.alloc('down_weight',(f,h),True);b.alloc('down',(128,h));b.dense('down',6,'silu','down_weight','down')
        b.alloc('output',(128,h));b.gdn('residual2',9,2,'residual1','down','output')
    else:
        # MoE uses the exact postnorm output TypedTensor, including prefix IDs.
        post_root=b.schedule[-1]['roots'][2]
        roots=[]
        for role,shape in enumerate(am.MOE_SHAPES):
            name=f'moe_weight_{role}';b.alloc(name,shape,True);roots.append(b.tensor(name))
        b.alloc('moe_shared_gate_padded',(2048,32),True);padroot=b.tensor('moe_shared_gate_padded')
        manifest_root=len(b.records)
        for role,root in enumerate(roots):
            kind,payload=am.moe_manifest_payload(role,root,padroot if role==7 else None)
            b.records.append(rec(kind,payload,manifest_root+role+1 if role<7 else NULL))
        b.alloc('output',(128,h));outroot=b.tensor('output');pc=len(b.commands)
        b.commands.append(0x50|(3<<8)|(pc<<24)|((pc+1)<<40)|(post_root<<56)|(manifest_root<<80)|(outroot<<104))
        b.schedule.append(dict(pc=pc,name='moe_full',a='post_norm',b=None,d='output',roots=[post_root,manifest_root,outroot],extras=[f'moe_weight_{r}' for r in range(8)]+['moe_shared_gate_padded'],outputs=['output']))
    if vh:b.gdn('final_fence',6,0,'history_out','state_out','output',outputs=[])
    else:b.emit('final_fence','cache','input','output',am.attention_fence(),outputs=[])
    return b,None
if __name__=='__main__':
    from parent_inputs import path_for_sha
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    pins=json.loads(Path(__file__).with_name('PROGRAM_PINS.json').read_text())['profiles']
    d=args.out/'profile0';d.mkdir()
    for fn,row in pins[0]['files'].items():
        data=path_for_sha(row['sha256'],row['bytes']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('profile0 parent identity')
        (d/fn).write_bytes(data)
    for p in range(1,5):
        b,blocked=common(p);cb,db,m=b.finish();m['blocker']=blocked;m['complete_program_emitted']=blocked is None
        m['sha256']={'commands':hashlib.sha256(cb).hexdigest(),'descriptors':hashlib.sha256(db).hexdigest()}
        raw=json.dumps(m,indent=2)+'\n';data={'commands.bin':cb,'descriptors.bin':db,'manifest.json':raw.encode()}
        for fn,value in data.items():
            row=pins[p]['files'][fn]
            if len(value)!=row['bytes'] or hashlib.sha256(value).hexdigest()!=row['sha256']:raise ValueError('exact generated_v5 metadata identity')
        d=args.out/f'profile{p}';d.mkdir()
        for fn,value in data.items():(d/fn).write_bytes(value)
