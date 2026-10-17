"""Development composer; reads pinned production and donor, emits isolated source only."""
from pathlib import Path
import argparse,difflib,hashlib,json
P='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
def one(s,a,b):
    if s.count(a)!=1:raise ValueError(('nonunique anchor',a[:100],s.count(a)))
    return s.replace(a,b,1)
def between(s,a,b):return s[s.index(a):s.index(b,s.index(a))]
def compose(base,donor,out):
    if out.exists() or out.is_symlink():raise ValueError('fresh output required')
    pins=json.loads(Path(__file__).with_name('SOURCE_PINS.json').read_text())
    roots={'production_source':base,'qk16_source':donor}
    for pin in pins:
        if hashlib.sha256((roots[pin['root']]/pin['path']).read_bytes()).hexdigest()!=pin['sha256']:
            raise ValueError('source pin mismatch: '+pin['path'])
    sources={n:(base/P/n).read_text() for n in ['Qwen2Block.scala','QwenOwnerProtocol.scala','MatrixPipeline.scala','HostBlockTop.scala']}
    d=(donor/P/'Qwen2Block.scala').read_text().replace('enablePackedQk16Keys','enableProductionPackedQk16')
    q=sources['Qwen2Block.scala']
    q=one(q,'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0) extends Module {','numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableProductionPackedQk16:Boolean=false) extends Module {\n  require(!enableProductionPackedQk16 || (ownerDriven && externalMatrix && Qwen2NumericPolicy.official(numericPolicy)), "production QK16 requires the official external-Matrix owner; capacity stays 1024")')
    q=one(q,'    val matrixAcceptedSteps=if(externalMatrix)Some(Input(UInt(64.W)))else None','    val matrixAcceptedSteps=if(externalMatrix)Some(Input(UInt(64.W)))else None\n    val packedQk=if(enableProductionPackedQk16)Some(new MatrixStreamPort)else None\n    val packedQkActive=if(enableProductionPackedQk16)Some(Output(Bool()))else None\n    val packedQkStepsDrained=if(enableProductionPackedQk16)Some(Input(Bool()))else None')
    # Append state names, never renumber existing official RMS states.
    q=one(q,'"normOfficialTerm","normOfficialBlock","normOfficialResidue","normOfficialLane")','"normOfficialTerm","normOfficialBlock","normOfficialResidue","normOfficialLane","attPackedIssue","attPackedSelect")')
    donor_regs=between(d,'  // New control only; existing acc[16]','  val fmA=')
    q=one(q,'  val fmA=',donor_regs+'  val fmA=')
    q=one(q,'val dot=state===st("attDot");val pv=', 'val dot=state===(if(enableProductionPackedQk16)st("attPackedIssue")else st("attDot"));val pv=')
    q=one(q,'matrixRequest.valid:=computing && !pending','matrixRequest.valid:=computing && !pending && !(enableProductionPackedQk16.B && dot)')
    q=one(q,'matrixFault:=fmDone && matrixResult.bits.error','matrixFault:=matrixResult.fire && matrixResult.bits.error')
    packed_logic=between(d,'    packedQk.foreach{c=>','\n\n  }else{')
    q=one(q,'    when(isDense&&fmDone){denseAcc:=matrixResult.bits.value}','    when(isDense&&fmDone){denseAcc:=matrixResult.bits.value}\n'+packed_logic)
    q=one(q,'io.result.valid:=state===st("finish");','io.result.valid:=state===st("finish") && !packedBusy && !packedFeedDebt;')
    q=one(q,'.elsewhen(j.m===0.U||j.m>s.maxTokens.U||j.n===0.U||j.n>s.maxRow.U||j.n(3,0)=/=0.U||j.writeBytes===0.U){fail(Status.Bounds.U)}', '.elsewhen(j.m===0.U||j.m>s.maxTokens.U||j.n===0.U||j.n>s.maxRow.U||j.n(3,0)=/=0.U||j.writeBytes===0.U){fail(Status.Bounds.U)}\n      .elsewhen(enableProductionPackedQk16.B && j.kind===QwenOwnerKind.Attention.U && j.m>128.U){fail(Status.Bounds.U)}')
    # Replace only QK portion; leave original head softmax/PV unchanged.
    old=between(q,'  when(state===st("attKey"))','  when(state===st("attExpRead"))')
    new=between(d,'  when(state===st("attKey")','  when(state===st("attExpRead"))')
    # Use the production full policy exactly once, not the partial-policy helper.
    reduce=between(new,'  when(state===st("attReduceDone"))','  if(!enableProductionPackedQk16){\n  when(state===st("attNextKey")')
    replacement='''  when(state===st("attReduceDone")){sum:=scalarValue;when(lane===15.U){
    val dotValue=materialize(scalarValue)
    when(enableProductionPackedQk16.B && !TensorMath.finite(dotValue)){packedSelectedFault:=true.B}
      .otherwise{calc(ScalarOp.Mul,dotValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}
  }.otherwise{lane:=lane+1.U;state:=st("attReduce")}}
  when(state===st("attScore") && (!enableProductionPackedQk16.B || (!poisoned && !packedQk.map(_.io.resetRequired).getOrElse(false.B) && !packedQk.map(_.io.port.done.valid).getOrElse(false.B)))){
    val score=materialize(scalarValue)
    when(enableProductionPackedQk16.B && !TensorMath.finite(score)){packedSelectedFault:=true.B}
    .otherwise{if(enableProductionPackedQk16){packedCommitted.get:=packedSelected.get+&1.U===packedKeys};scores.write(key+packedSelected.getOrElse(0.U),score);when(F32.less(maxScore,score)){maxScore:=score};state:=st("attNextKey")}
  }
'''
    new=one(new,reduce,replacement);q=one(q,old,new)
    old='when((state===st("denseCompute")||state===st("attDot")||state===st("attPVCompute")) && fmDone'
    new='when((state===st("denseCompute")||(state===(if(enableProductionPackedQk16)st("attPackedIssue")else st("attDot")) && (!enableProductionPackedQk16.B || depth===112.U))||state===st("attPVCompute")) && fmDone'
    q=one(q,old,new)
    tail=d[d.rindex('  packedQk.foreach{c=>'):d.rindex('\n}')]
    q=q[:q.rindex('\n}')]+ '\n'+tail+q[q.rindex('\n}'):]
    sources['Qwen2Block.scala']=q
    # Add only existing status output to production Matrix; retain seed/transpose.
    m=sources['MatrixPipeline.scala']
    m=one(m,'enableAccumulatorSeed:Boolean=false) extends Module {','enableAccumulatorSeed:Boolean=false,enablePackedDrainStatus:Boolean=false) extends Module {')
    m=one(m,'    val stallCycles=Output(UInt(64.W))\n    val resetRequired=Output(Bool())','    val stallCycles=Output(UInt(64.W))\n    val resetRequired=Output(Bool())\n    val packedStepsDrained=if(enablePackedDrainStatus)Some(Output(Bool()))else None')
    anchor='  val consumeOutput='
    m=one(m,anchor,'  // Existing metadata owns retirement; no new debt counter or payload.\n  if(enablePackedDrainStatus){io.packedStepsDrained.get:=work && !tags.io.deq.valid && !io.port.step.valid && !poison}\n'+anchor)
    sources['MatrixPipeline.scala']=m
    k=sources['QwenOwnerProtocol.scala']
    k=one(k,'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0) extends Module {','numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableProductionPackedQk16:Boolean=false) extends Module {\n  require(!enableProductionPackedQk16 || (pipelined && Qwen2NumericPolicy.official(numericPolicy) && !bf16Gdn && !bf16QkNormRope && !bf16AttentionCore && !enableH2048RmsBorrower), "production QK16 keeps the official Qwen2 owner profile")')
    k=one(k,'externalElementwiseLoan=enableH2048RmsBorrower,numericPolicy=numericPolicy))','externalElementwiseLoan=enableH2048RmsBorrower,numericPolicy=numericPolicy,enableProductionPackedQk16=enableProductionPackedQk16))')
    k=one(k,'new MatrixPipelineService(enableTransposedDense=enableTransposedDense,enableAccumulatorSeed=enableTransposedSeed)','new MatrixPipelineService(enableTransposedDense=enableTransposedDense,enableAccumulatorSeed=enableTransposedSeed,enablePackedDrainStatus=enableProductionPackedQk16)')
    # Before production debt trackers: they see final selected service fires.
    marker='    }\n    if(enablePublic21QkvReduction){\n      val r=qkvRouter.get'
    if marker not in k:
        raise ValueError('locate production reduction debt marker')
    mux='''    if(enableProductionPackedQk16){
      val p=core.io.packedQk.get;val select=core.io.packedQkActive.get
      core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get
      p.group.ready:=select && matrix.io.port.group.ready;p.step.ready:=select && matrix.io.port.step.ready
      p.result.valid:=select && matrix.io.port.result.valid;p.result.bits:=matrix.io.port.result.bits
      p.done.valid:=select && matrix.io.port.done.valid;p.done.bits:=matrix.io.port.done.bits
      when(select){
        assert(active && mode===0.U && !useDense,"packed QK lease belongs only to the original core")
        legacy.io.port.group.ready:=false.B;legacy.io.port.step.ready:=false.B
        legacy.io.port.result.valid:=false.B;legacy.io.port.done.valid:=false.B
        dense.matrix.group.ready:=false.B;dense.matrix.step.ready:=false.B
        dense.matrix.result.valid:=false.B;dense.matrix.done.valid:=false.B
        matrix.io.port.group.valid:=p.group.valid
        matrix.io.port.group.bits.opcode:=p.group.bits.opcode
        matrix.io.port.group.bits.sliceMask:=p.group.bits.sliceMask
        matrix.io.port.group.bits.tag:=p.group.bits.tag
        matrix.io.port.group.bits.transposedDense.foreach(_:=false.B)
        matrix.io.port.group.bits.groupSequence.foreach(_:=0.U)
        matrix.io.port.step.valid:=p.step.valid;matrix.io.port.step.bits:=p.step.bits
        matrix.io.port.result.ready:=p.result.ready;matrix.io.port.done.ready:=p.done.ready
        matrix.io.port.abort:=p.abort
        if(enableTransposedSeed){
          matrix.io.port.seed.get.begin.valid:=false.B;matrix.io.port.seed.get.beat.valid:=false.B
          matrix.io.port.seed.get.ack.ready:=false.B
          dense.matrix.seed.get.begin.ready:=false.B;dense.matrix.seed.get.beat.ready:=false.B
          dense.matrix.seed.get.ack.valid:=false.B
        }
      }
    }
'''
    k=one(k,marker,mux+marker)
    k=one(k,'when(r.io.reductionOwns){matrix.io.port.abort:=dense.matrix.abort || r.io.backendAbort}', 'when(r.io.reductionOwns){\n        if(enableProductionPackedQk16){assert(!core.io.packedQkActive.get,"QKV reduction and packed QK cannot share the Matrix lease")}\n        matrix.io.port.abort:=dense.matrix.abort || r.io.backendAbort\n      }')
    sources['QwenOwnerProtocol.scala']=k
    h=sources['HostBlockTop.scala']
    old='numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0) extends Module {'
    if h.count(old)!=2:raise ValueError('Host constructors')
    h=h.replace(old,'numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableProductionPackedQk16:Boolean=false) extends Module {')
    # Only append to owner and collection calls, not Commands policy wiring.
    h=h.replace('enablePublic21QkvReduction=enablePublic21QkvReduction,numericPolicy=numericPolicy))','enablePublic21QkvReduction=enablePublic21QkvReduction,numericPolicy=numericPolicy,enableProductionPackedQk16=enableProductionPackedQk16))')
    sources['HostBlockTop.scala']=h
    sources['PackedAttentionStreamClient.scala']=(donor/P/'PackedAttentionStreamClient.scala').read_text()
    out.mkdir(parents=True)
    records=[]
    for n,s in sources.items():
        target=out/P/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(s)
        original=(base/P/n).read_text() if (base/P/n).exists() else ''
        records.append(dict(path=P+n,base_sha256=hashlib.sha256(original.encode()).hexdigest() if original else None,post_sha256=hashlib.sha256(s.encode()).hexdigest()))
    return records
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--production-source',required=True);a.add_argument('--qk16-source',required=True);a.add_argument('--output',required=True);x=a.parse_args();print(json.dumps(compose(Path(x.production_source),Path(x.qk16_source),Path(x.output)),indent=2))
