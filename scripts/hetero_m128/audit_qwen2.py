"""Read-only source-architectural ratio bound for original Qwen2 M128."""
import argparse,json,hashlib
from fractions import Fraction
from pathlib import Path
from first_projection_contract import MACS,MAP_PATH,MAP_SHA,SOURCE_PINS,SOURCE_DIR,pinned,need,bits,ceildiv,extract,streaming_envelope

MAN='109072c5710e59c7855d778c22fbf697e6983f9ac1e6b4f686c22e0eda3adf22'
MFILE='round_20261119T1133/stimuli/Qwen2/manifest.json'
DENSE=(1,4,7,13,16,17,19)
OPS=(0x32,0x20,0x30,0x34,0x20,0x30,0x34,0x20,0x30,0x41,0x23,0x33,0x24,0x20,0x30,0x32,0x20,0x20,0x35,0x20,0x30)

def main(R):
    source={s:pinned(R,f'{SOURCE_DIR}/{s}',h).decode() for s,h in SOURCE_PINS.items()}
    anchors={
        'HostBlockTopV4.scala':['Pipelined streaming Dense is selected only when resident/transposed are off','pipelined && weightReadBeats==16 && !enableResidentFfn && !enableTransposedDown','one shared kernel','io.usefulMacs:=cmd.io.usefulMacs'],
        'HostBlockCommandsV4.scala':['Mux(dense||nativeProjection||gdnProjection,QwenOwnerKind.Dense.U','when(io.job.fire){jobs:=jobs+1.U;state:=waitDone}','when(io.done.fire){val r=io.done.bits','useful:=useful+r.usefulMacs','.elsewhen(qk||attentionQk)','.elsewhen(sm||attentionSoft)','when(pv){bound.a:=q.address'],
        'QwenOwnerProtocol.scala':['else Module(new StreamingDenseOwner(s.maxRow,burstWrites=burstWrites)).io','Mux(ordinaryJob.bits.kind===QwenOwnerKind.Dense.U,1.U','val canStart= !active','dense.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===1.U','when(ordinaryDone.fire){active:=false.B}'],
        'StreamingDense.scala':['val admittedRows=scratch.tokenTiles(j.k).pad(7)<<4','state:=aWait','when(aRow+1.U===rows){state:=setup}','state:=execute','state===execute&&status===0.U&&loadState===loadIdle&&nextLoadK<job.k','rowBase:=rowBase+rows','nBase:=0.U;aRow:=0.U;aBeat:=0.U;state:=aReq','useful:=useful+rowsIn(io.matrix.step.bits.context)*columns(io.matrix.step.bits.context)'],
        'DenseReadPlanner.scala':['budgetBytes:Int=768*1024','weightBytes=16*160*32','(budgetBytes-weightBytes)/(16*32)','aWordsPerBank*16/t','val perRow=Mux(io.nativeBf16,width>>5,width>>4)'],
        'RetainedIdma.scala':['class IdmaR extends Bundle','val data=UInt(512.W)'],
        'Qwen2Block.scala':['macs:=0.U','state===st("attDot")','state===st("attPVCompute")','when(key<token){key:=key+1.U'],
    }
    for s,checks in anchors.items():need(all(x in source[s] for x in checks),f'unchanged original source {s}')
    emit=R/'round_20261119T1233/host/EmitNewFixedHost.scala'
    em=emit.read_text()
    need('weightReadBeats=16,pipelined=true,numericPolicy=Qwen2NumericPolicy.LegacyV0' in em and 'retainedMatrix=true' in em and 'matrixColumns=256' in em and 'enableResidentFfn' not in em and 'enableTransposedDown' not in em,'exact baseline options')
    rawmap=json.loads(pinned(R,MAP_PATH,MAP_SHA))
    need(rawmap['matrix_macs']==4096,'original physical geometry')
    profile=rawmap['profiles'][0]
    need((profile['profile'],profile['tokens'])==(0,128),'original profile')
    d=json.loads(pinned(R,MFILE,MAN))
    need(d['attention_fusion']==[10,11,12] and d['shape']=={'H':1536,'F':8960,'HEADS':12,'KVHEADS':2,'HD':128,'MAX_TOKENS':1024},'original attention geometry')
    tab=[pinned(R,p['file'],p['sha256'],p['bytes']) for p in profile['segments'][:2]]
    command,descriptor=tab
    def rec(tab,i):
        need(0<=i<len(tab)//16,'bounded record')
        return int.from_bytes(tab[16*i:16*i+16],'little')
    def chain(i,k):
        t=rec(descriptor,i)
        need(bits(t,0,8)==k and bits(t,8,24)==0,'exact typed structure')
        return t,bits(t,32,24)
    def tensor(i,name):
        a,b=chain(i,1);s,c=chain(b,2);q,tail=chain(c,3)
        x=d['tensors'][name]
        rank=bits(a,116,4);shape=[bits(s,56+18*k,18) for k in range(rank)]
        address=bits(a,56,48)|(bits(a,120,8)<<48)
        strides=[bits(q,56+24*k,24) for k in range(3)]
        need(rank==2 and bits(a,108,4)==7 and shape==x['dims'] and strides==[shape[1],1,1] and address==x['address'],'matching pinned FP32 tensor, contiguous physical mapping')
        return shape,tail
    rows=[]
    for i,op in enumerate(OPS):
        w=rec(command,i)
        opword=0x220 if i in DENSE else op
        need(bits(w,0,8)==op and (i not in DENSE or bits(w,0,11)==opword) and (bits(w,24,16),bits(w,40,16))==(i,i+1),'complete exact dependency chain')
        m=d['schedule'][i]
        roots=[bits(w,56+24*k,24) for k in range(3)]
        need(m['pc']==i and roots==m['roots'],'manifest to Command128 exact roots')
        if i not in DENSE:continue
        a,b,y=[tensor(root,m[name]) for root,name in zip(roots,('a','b','dst'),strict=True)]
        M,K=a[0];N=b[0][1]
        need(M==128 and b[0][0]==K and y[0]==[M,N] and b[1]==y[1]==0xffffff,'exact typed Dense geometry')
        v,j=chain(a[1],0x10);aux,tail=chain(j,0x12)
        need(tuple(bits(v,off,n) for off,n in [(56,16),(72,16),(88,24),(112,16)])==(M,N,K,0) and tail==0xffffff and bits(aux,56,72)==0x4000040024ffffff,'matrix and original ABI policy')
        t=min(5,((768*1024-16*160*32)//(16*32))*16//K)
        cohorts=[min(16*t,M-b) for b in range(0,M,16*t)]
        beatsA=M*K*4//64;beatsB=K*N*4//64
        need(M*K*4%64==K*N*4%64==0 and N%256==0,'integral ideal bus/physical tiling')
        cost=beatsA+sum(max(beatsB,ceildiv(c*N*K,MACS)) for c in cohorts)
        rows.append(dict(pc=i,role=m['operation'],roots=roots,shape=[M,N,K],cohorts=cohorts,read_beats_A=beatsA,
          read_beats_B_per_cohort=beatsB,ideal_serial_A_then_W_or_compute_cycles_floor=cost,useful=M*N*K))
    need([a['pc'] for a in rows]==list(DENSE),'all seven Dense')
    U=sum(a['useful'] for a in rows)
    A=2*128*128*1536
    total=U+A
    one=extract(profile,command,descriptor)
    case=streaming_envelope(one['m'],one['n'],one['k'],4,4)
    need(rows[0]['ideal_serial_A_then_W_or_compute_cycles_floor']==case['mandatory_ideal_A_then_weight_epochs_cycle_floor'],'independent equality to PC1 earlier envelope')
    lower1=case['mandatory_ideal_A_then_weight_epochs_cycle_floor']+sum(ceildiv(a['useful'],MACS) for a in rows[1:])
    lower7=sum(a['ideal_serial_A_then_W_or_compute_cycles_floor'] for a in rows)
    return dict(scope='Source/table architectural upper bounds for unchanged original Qwen2 at ideal one 512-bit R/cycle; not simulation, timing prediction, target DDR or RTL result',
        exact_program_manifest_sha256=MAN,launch_map_sha256=MAP_SHA,source_sha256=SOURCE_PINS,baseline_emitter_sha256=hashlib.sha256(emit.read_bytes()).hexdigest(),
        dense=rows,attention_full_square_upper=A,attention_causal_pair_math_if_counted=128*129*1536,
        total_dense_useful=U,total_useful_upper=total,scalar_mac_in_exported_counters=False,idealized_other_ops_free_in_both_bounds=True,
        pc1_penalty_plus_other_dense_ideal_matrix_cycles=lower1,pc1_penalty_only_whole_independent_bound=str(Fraction(total,MACS*lower1)),
        all_dense_serial_read_compute_floor_cycles=lower7,all_dense_whole_independent_bound=str(Fraction(total,MACS*lower7)),
        hardware_executed=False,no_weights_read=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True,type=Path)
    print(json.dumps(main(p.parse_args().root.resolve()),indent=2,sort_keys=True))
