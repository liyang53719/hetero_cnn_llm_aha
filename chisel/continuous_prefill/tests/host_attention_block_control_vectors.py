"""Synthetic descriptor/control vectors. No model data or owner arithmetic."""
from pathlib import Path
import sys,json
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT / 'src'))
sys.path.insert(0,str(ROOT / 'chisel/continuous_prefill/scripts'))
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding, HostPartialRopeBinding
from host_bf16_attention_core_descriptor import AttentionContext, AttentionTensor, HostAttentionCoreBinding, build_host_attention_core_commands
from host_bf16_attention_block_descriptor import HostAttentionBlockBinding as B, AttentionBlockOperation as Op, build_host_attention_block_commands, _resources

def fixture(*, old=0, generation=0, scratch=0, final=None, capacity=256):
    ctx = AttentionContext(capacity, old, old, generation, old == 0)
    # Parameters are stable. Scratch coordinates deliberately reusable after commit.
    cursor = 0x100000
    def alloc(shape):
        nonlocal cursor
        t=AttentionTensor(cursor,shape); cursor += t.span[1]; return t
    weights=[alloc((1024,n)) for n in (4096,512,512)]
    gamma=[alloc((1,256)) for _ in range(2)]
    trig=alloc((256,64)); input_gamma=alloc((1,1024)); wo=alloc((2048,1024))
    post_gamma=alloc((1,1024)); wg=alloc((1024,3584)); wu=alloc((1024,3584)); wd=alloc((3584,1024))
    cursor = 0x2800000 + scratch
    raw=alloc((1,1024)); inp=alloc((1,1024)); q=alloc((1,4096)); k=alloc((1,512)); v=alloc((1,512))
    qn=alloc((1,2048)); kn=alloc((1,512)); gate=alloc((1,2048)); qr=alloc((1,2048)); kr=alloc((1,512))
    score=alloc((8,1,old+1)); prob=alloc((8,1,old+1)); context=alloc((1,2048)); gated=alloc((1,2048))
    o=alloc((1,1024)); r1=alloc((1,1024)); post=alloc((1,1024)); fg=alloc((1,3584)); fu=alloc((1,3584))
    silu=alloc((1,3584)); down=alloc((1,1024)); r2=AttentionTensor(0x3000000 if final is None else final,(1,1024))
    cache=AttentionTensor(0x3100000,(2,capacity,512))
    p=tuple(HostQkvBinding(role,1,0,1,inp.address,weights[role].address,t.address) for role,t in enumerate((q,k,v)))
    n=tuple(HostQkNormBinding(role,1,0,1,t.address,gamma[role].address,out.address,gate.address if role==0 else 0)
            for role,(t,out) in enumerate(((q,qn),(k,kn))))
    r=tuple(HostPartialRopeBinding(role,1,0,1,t.address,trig.address,out.address,256,old)
            for role,(t,out) in enumerate(((qn,qr),(kn,kr))))
    core=HostAttentionCoreBinding(1,0,1,capacity,old,old,generation,old==0,qr.address,kr.address,v.address,
                                 cache.address,score.address,prob.address,context.address)
    b=(B(Op.RMS_NORM,0,ctx,raw,input_gamma,inp), B(Op.ELEMENTWISE,0,ctx,gate,context,gated),
       B(Op.DENSE,0,ctx,gated,wo,o), B(Op.ELEMENTWISE,1,ctx,raw,o,r1),
       B(Op.RMS_NORM,1,ctx,r1,post_gamma,post), B(Op.DENSE,1,ctx,post,wg,fg),
       B(Op.DENSE,2,ctx,post,wu,fu), B(Op.ELEMENTWISE,2,ctx,fg,fu,silu),
       B(Op.DENSE,3,ctx,silu,wd,down), B(Op.ELEMENTWISE,3,ctx,r1,down,r2),
       B(Op.FENCE,0,ctx,cache,raw,r2))
    return p,n,r,core,b


def program(old=0,generation=0,mode='block'):
    args=fixture(old=old,generation=generation,final=0x3000000+generation*4096)
    p,n,r,core,block=args
    is_block=mode!='core'
    commands,records=(build_host_attention_block_commands(*args) if is_block else build_host_attention_core_commands(*args[:-1]))
    jobs=[]
    def job(pc,kind,**fields):
        jobs.append(dict(pc=pc,kind=kind,**fields))
    offset=int(is_block)
    if is_block: jobs.append(dict(pc=0,**block[0].job))
    for i,b in enumerate(p): job(i+offset,1,**b.job)
    for i,b in enumerate(n):
        f=b.job
        job(i+3+offset,14,a=f['input'],b=f['weight'],c=f['gateOutput'],dst=f['output'],m=1,n=8 if i==0 else 2,k=256,writeBytes=f['writeBytes'],qkRole=i,qkTrigTokens=1)
    for i,b in enumerate(r):
        f=b.job
        job(i+5+offset,15,a=f['input'],b=f['trig'],dst=f['output'],m=1,n=8 if i==0 else 2,k=256,writeBytes=f['writeBytes'],qkRole=i,qkPositionBase=old,qkTrigTokens=256)
    for pc,kind,fields in ((7+offset,7,core.jobs[0]),(10+offset,4,core.jobs[1])):
        job(pc,kind,a=fields['k'] if kind==7 else fields['q'],b=fields['v'] if kind==7 else core.cache_ddr,
            dst=core.cache_ddr if kind==7 else core.output_ddr,m=1,n=512 if kind==7 else 2048,k=256,
            writeBytes=fields['writeBytes'],cacheCapacity=core.capacity,cacheLength=old if kind==7 else old+1,
            expectedCacheLength=old,queryStart=old,expectedGeneration=generation,currentGeneration=generation,cold=old==0)
    if is_block:
        for pc,b in enumerate(block[1:-1],12): jobs.append(dict(pc=pc,**b.job))
    if mode=='preloaded':
        # An independently valid Q projection pointing at readonly raw hidden
        # must fail actual input-RMS producer provenance at PC1.
        from host_bf16_qkv_descriptor import build_host_qkv_descriptor
        from dataclasses import replace
        _,extra=build_host_qkv_descriptor(replace(p[0],activation_ddr=block[0].a.address),first_index=12,event_wait=1,event_signal=2)
        records.update(extra)
    if mode=='reversed_sigmoid':
        from host_bf16_attention_block_descriptor import build_host_attention_block_descriptor
        from dataclasses import replace
        _,extra=build_host_attention_block_descriptor(replace(block[1],a=block[1].b,b=block[1].a),first_index=172,event_wait=12,event_signal=13)
        records.update(extra)
    params=_resources(*args)[0]
    return dict(commands=[str(c.pack()) for c in commands],records=[str(records[i].pack()) for i in range(len(records))],
                jobs=jobs,gate=n[0].gate_output_ddr,context=core.output_ddr,parameters=[t.address for t in params[:12 if is_block else 6]],cache=core.cache_ddr,
                final=block[-1].d.address if is_block else core.output_ddr,old=old,generation=generation,
                finalWidth=1024 if is_block else 2048)

if __name__=='__main__':
    print(json.dumps(program(int(sys.argv[1]),int(sys.argv[2]),sys.argv[3] if len(sys.argv)>3 else 'block')))
