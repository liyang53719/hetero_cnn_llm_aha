// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private accepted-scheduler recipe, not an independent host capability.
  * Recipe1 preserves the original CPU-default8lane/4residue block order for
  * H1024 and H2048. Qwen2 FP32-storage/public21 never uses this BF16 owner. */
class GdnRuntimeRmsNormJobV3 extends GdnRmsNormJob {
  val reductionRecipe=UInt(2.W)
  // Retained semantic phase, not a resource grant: inputNorm0 versus postNorm3.
  val phase=UInt(2.W)
}
object GdnRuntimeRmsNormJobV3 {
  def fromOwner(j:QwenOwnerJob):GdnRuntimeRmsNormJobV3={
    val r=Wire(new GdnRuntimeRmsNormJobV3)
    r.tokens:=j.m;r.hiddenWidth:=j.n;r.input:=j.a;r.weight:=j.b
    r.output:=j.dst;r.tag:=j.tag;r.reductionRecipe:=1.U;r.phase:=j.qkRole;r
  }
}
class GdnRuntimeRmsNormResultV16 extends GdnRmsNormResult {
  val accepted=new GdnRuntimeRmsNormJobV3
  val outputAckBytes=UInt(64.W);val resourcesDrained=Bool()
  val scalarAccepted=UInt(32.W);val scalarReturned=UInt(32.W)
  val formatAccepted=UInt(32.W);val formatReturned=UInt(32.W)
  val vectorAccepted=UInt(32.W);val vectorReturned=UInt(32.W)
  val memoryAccepted=UInt(32.W);val memoryReturned=UInt(32.W)
}
class QwenRuntimeRmsPublicationV16 extends Bundle {
  val memory=Bool();val scalar=Bool();val format=Bool();val vector=Bool()
}

/** TEMP: fixed32 shared-bank runtime RMS borrower; not numerical qualification.
  * Preserves CPU-default8lane/4residue/512block reduction DAG, including +0.
  * Existing input/weight/output banks and four memory transactions/beat retained.
  * Adds two32xFP32 working vectors (2048 bits); no arithmetic Module or bank.
  * One outstanding shared vector transaction; no II1 throughput claim.
  * Mean/epsilon/Div/Sqrt retain scalar service. Final BF16 format is policy4.
  * P0 FP32-storage uses its separate original owner, untouched here. */
class GdnRuntimeRmsNormOwnerV3 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new GdnRuntimeRmsNormJobV3))
    val done=Decoupled(new GdnRuntimeRmsNormResultV16)
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val scalar=new UnifiedScalarClientV2
    val vectorRequest=Decoupled(new UnifiedVectorElement32PayloadV4)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorElement32ResultPayloadV4))
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val parentFault=Input(Bool());val published=Input(new QwenRuntimeRmsPublicationV16)
    val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
  })
  val states=Enum(12)
  val idle=states(0);val readInput=states(1);val waitInput=states(2)
  val readWeight=states(3);val waitWeight=states(4);val scalarIssue=states(5);val scalarWait=states(6)
  val vectorIssue=states(7);val vectorWait=states(8);val writeOutput=states(9);val waitOutput=states(10);val finish=states(11)
  val report=12.U(4.W);val locked=13.U(4.W)
  val state=RegInit(idle)
  val ops=Enum(13)
  val square=ops(0);val sum=ops(1);val residue=ops(2);val foldResidue=ops(3);val foldLane=ops(4)
  val mean=ops(5);val epsilon=ops(6);val root=ops(7);val inverse=ops(8);val normalize=ops(9);val gamma=ops(10);val weighted=ops(11);val materialize=ops(12)
  val operation=RegInit(square);val accepted=Reg(new GdnRuntimeRmsNormJobV3)
  val input=Reg(Vec(32,UInt(512.W)));val weights=Reg(Vec(32,UInt(512.W)));val output=Reg(Vec(32,UInt(512.W)))
  val accumVector=RegInit(VecInit(Seq.fill(32)(0.U(32.W))))
  val valueVector=Reg(Vec(32,UInt(32.W)))
  val accumulator=RegInit(0.U(32.W));val value=Reg(UInt(32.W));val normalized=RegInit(0.U(32.W));val invRms=Reg(UInt(32.W))
  val lane=RegInit(0.U(10.W));val beat=RegInit(0.U(5.W));val token=RegInit(0.U(7.W));val chunk=RegInit(false.B);val emitPass=RegInit(false.B)
  val sequence=RegInit(0.U(32.W));val bytes=RegInit(0.U(64.W));val cycles=RegInit(0.U(64.W))
  val status=RegInit(Status.Ok.U(8.W));val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val terminal=Reg(new GdnRuntimeRmsNormResultV16)
  val memoryAccepted=RegInit(0.U(32.W))
  val scalarAccepted=RegInit(0.U(32.W));val scalarReturned=RegInit(0.U(32.W))
  val formatAccepted=RegInit(0.U(32.W));val formatReturned=RegInit(0.U(32.W))
  val vectorAccepted=RegInit(0.U(32.W));val vectorReturned=RegInit(0.U(32.W))
  val vectorMultiply=operation===square || operation===normalize || operation===weighted
  val vectorPolicy=Mux(operation===materialize,4.U(3.W),Mux(vectorMultiply,3.U(3.W),0.U(3.W)))
  val active=state=/=idle && state=/=locked
  val memoryOffer=state===readInput || state===readWeight || state===writeOutput
  val memoryDebt=state===waitInput || state===waitWeight || state===waitOutput
  val expectedTag=Cat(accepted.tag,sequence)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  val unknownScalar=io.scalar.result.valid && (state=/=scalarWait || io.scalar.result.bits.policy=/=0.U)
  val unknownFormat=io.formatResult.valid
  val unknownVector=io.vectorResult.valid && (state=/=vectorWait || io.vectorResult.bits.policy=/=vectorPolicy)
  val unknown=unknownMemory || unknownScalar || unknownFormat || unknownVector
  val currentFault=io.parentFault || unknown
  when(unknown){quarantine:=true.B}
  when(currentFault){poison:=true.B;when(state=/=report && status===Status.Ok.U){status:=Status.Protocol.U}}
  io.resetRequired:=poison || quarantine || currentFault
  val quiet= !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid && !io.vectorResult.valid
  val noService= !memoryOffer && !memoryDebt && state=/=scalarIssue && state=/=scalarWait && state=/=vectorIssue && state=/=vectorWait
  io.resourcesDrained:=noService && quiet && !quarantine && !unknown
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  when(active && state=/=report){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={when(status===Status.Ok.U){status:=code};poison:=true.B;state:=finish}

  // lane(4)=512-element block within chunk; lane(3,0)=term0..15.
  // Vector i represents original (CPU lane=i/4,residue=i%4).
  val partials=Cat(output(1),output(0)).asTypeOf(Vec(32,UInt(32.W)))
  val outputBeat=output(beat)
  val reductionX=Wire(Vec(32,UInt(32.W)))
  val emitX=input(lane(9,5)).asTypeOf(Vec(32,UInt(16.W)))
  val emitWeight=weights(lane(9,5)).asTypeOf(Vec(32,UInt(16.W)))
  for(i <- 0 until 32){
    val index=Cat(lane(4),lane(3,0),(i%4).U(2.W),(i/4).U(3.W))
    val words=input(index(9,5)).asTypeOf(Vec(32,UInt(16.W)))
    reductionX(i):=Cat(words(index(4,0)),0.U(16.W))
  }
  val rowBytes=accepted.hiddenWidth.pad(64)<<1
  val rowOffset=token.pad(64)*rowBytes
  val chunkOffset=Mux(chunk,2048.U(64.W),0.U(64.W));val beatOffset=beat.pad(64)<<6
  val expectedBytes=accepted.tokens.pad(64)*rowBytes
  // Only actual downstream visibility creates a held external obligation.
  // A local intent suppressed by Top/Prefix on current fault must not strand
  // the leaf. Publication updates registers/assertions, never raw valid gates.
  def publishedOffer(intent:Bool,ready:Bool,published:Bool):HeldDecoupledOfferSignals={
    val held=RegInit(false.B)
    val visible=intent && ((!poison && !quarantine && !currentFault) || held)
    when(published){held:= !ready}
    assert(!published || visible,"RMS publication requires retained raw intent")
    assert(!(visible && ready) || published,"RMS acceptance must be actual publication")
    assert(!held || intent,"RMS published held offer may not be withdrawn")
    HeldDecoupledOfferSignals(visible,held,visible && ready)
  }
  val memoryHeld=publishedOffer(memoryOffer,io.memory.ready,io.published.memory)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write:=state===writeOutput
  io.memory.bits.address:=MuxLookup(state,accepted.input+rowOffset+chunkOffset+beatOffset)(Seq(
    readWeight->(accepted.weight+chunkOffset+beatOffset),writeOutput->(accepted.output+rowOffset+chunkOffset+beatOffset)))
  io.memory.bits.data:=Mux(state===writeOutput,outputBeat,0.U)
  io.memory.bits.mask:=Mux(state===writeOutput,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=expectedTag
  io.response.ready:=memoryDebt && !quarantine && !unknownMemory
  val scalarHeld=publishedOffer(state===scalarIssue,io.scalar.request.ready,io.published.scalar)
  io.scalar.request.valid:=scalarHeld.valid;io.scalar.request.bits.policy:=0.U
  io.scalar.request.bits.payload.op:=MuxLookup(operation,ScalarOp.Add.U)(Seq(
    mean->ScalarOp.MulIeeeRne.U,root->ScalarOp.Sqrt.U,inverse->ScalarOp.Div.U))
  io.scalar.request.bits.payload.a:=Mux(operation===mean,normalized,Mux(operation===inverse,F32.lit(1),value))
  io.scalar.request.bits.payload.b:=MuxLookup(operation,0.U)(Seq(
    mean->Mux(accepted.hiddenWidth===1024.U,F32.lit(1.0/1024),F32.lit(1.0/2048)),
    epsilon->F32.lit(1e-6),inverse->value))
  io.scalar.result.ready:=state===scalarWait && !quarantine && !unknownScalar
  val vectorHeld=publishedOffer(state===vectorIssue,io.vectorRequest.ready,io.published.vector)
  io.vectorRequest.valid:=vectorHeld.valid
  io.vectorRequest.bits.policy:=vectorPolicy;io.vectorRequest.bits.multiply:=vectorMultiply
  for(i <- 0 until 32){
    val foldResidueA=if(i<8) accumVector(i) else 0.U(32.W)
    val foldResidueB=if(i<8) partials(Cat(i.U(3.W),lane(1,0))) else 0.U(32.W)
    io.vectorRequest.bits.a(i):=MuxLookup(operation,0.U(32.W))(Seq(
      square->reductionX(i),sum->accumVector(i),
      residue->Mux(!chunk && !lane(4),0.U(32.W),partials(i)),
      foldResidue->foldResidueA,foldLane->(if(i==0) normalized else 0.U(32.W)),
      normalize->Cat(emitX(i),0.U(16.W)),gamma->F32.lit(1),
      weighted->accumVector(i),materialize->valueVector(i)))
    io.vectorRequest.bits.b(i):=MuxLookup(operation,0.U(32.W))(Seq(
      square->reductionX(i),sum->valueVector(i),residue->accumVector(i),
      foldResidue->foldResidueB,foldLane->(if(i==0) valueVector(lane(2,0)) else 0.U(32.W)),
      normalize->invRms,gamma->Cat(emitWeight(i),0.U(16.W)),weighted->valueVector(i)))
  }
  io.vectorResult.ready:=state===vectorWait && !quarantine && !unknownVector
  // Legacy scalar formatter port remains an explicitly unused interface.
  io.formatRequest.valid:=false.B;io.formatRequest.bits.value:=0.U
  io.formatResult.ready:=false.B
  // Never discard an already offered packet. New work stops at a real safe
  // boundary; matching pending responses still retire under ordinary poison.
  when((poison || currentFault) && !quarantine){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
    when(state===vectorIssue && !vectorHeld.held && !io.vectorRequest.fire){state:=finish}
  }
  when(io.job.fire){
    accepted:=io.job.bits;sequence:=0.U;bytes:=0.U;cycles:=0.U;status:=Status.Ok.U
    memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U;formatAccepted:=0.U;formatReturned:=0.U;vectorAccepted:=0.U;vectorReturned:=0.U
    accumVector:=VecInit(Seq.fill(32)(0.U(32.W)))
    beat:=0.U;token:=0.U;lane:=0.U;chunk:=false.B;emitPass:=false.B;accumulator:=0.U;normalized:=0.U;operation:=square
    val j=io.job.bits;val nb=(j.tokens.pad(80)*j.hiddenWidth)<<1;val wb=j.hiddenWidth.pad(80)<<1
    def bad(base:UInt,n:UInt):Bool=base(5,0)=/=0.U || base.pad(80)+n>(BigInt(1)<<56).U
    def overlap(a:UInt,n:UInt,b:UInt,m:UInt):Bool=a.pad(80)<b.pad(80)+m && b.pad(80)<a.pad(80)+n
    when(j.reductionRecipe=/=1.U || !(j.phase===0.U || j.phase===3.U)){fail(Status.Unsupported.U)}
      .elsewhen(j.tokens===0.U || j.tokens>128.U || j.tag==="hffffffff".U || !(j.hiddenWidth===1024.U || j.hiddenWidth===2048.U) ||
        bad(j.input,nb) || bad(j.weight,wb) || bad(j.output,nb) || overlap(j.input,nb,j.weight,wb) ||
        overlap(j.input,nb,j.output,nb) || overlap(j.weight,wb,j.output,nb)){fail(Status.Bounds.U)}
      .otherwise{state:=readInput}
  }
  when(io.memory.fire){memoryAccepted:=memoryAccepted+1.U;state:=MuxLookup(state,waitInput)(Seq(readWeight->waitWeight,writeOutput->waitOutput))}
  when(io.response.fire){
    val r=io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    when(state===waitOutput && !r.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        when(state===waitInput || state===waitWeight){
          val nonfinite=(0 until 32).map(i=>r.data(i*16+14,i*16+7)===255.U).reduce(_||_)
          when(nonfinite){fail(Status.Numerical.U)}.otherwise{
            when(state===waitWeight){weights(beat):=r.data}.otherwise{input(beat):=r.data}
            when(beat===31.U){beat:=0.U;lane:=0.U
              when(state===waitWeight){operation:=normalize;state:=vectorIssue}
                .elsewhen(emitPass){state:=readWeight}
                .otherwise{accumVector:=VecInit(Seq.fill(32)(0.U(32.W)));operation:=square;state:=vectorIssue}
            }.otherwise{beat:=beat+1.U;state:=Mux(state===waitWeight,readWeight,readInput)}
          }
        }
        when(state===waitOutput){
          when(beat===31.U){beat:=0.U;lane:=0.U
            when(!chunk && accepted.hiddenWidth===2048.U){chunk:=true.B;state:=readInput}
              .elsewhen(token+&1.U===accepted.tokens){
                when(bytes+64.U===expectedBytes){state:=finish}.otherwise{fail(Status.Protocol.U)}
              }.otherwise{token:=token+1.U;chunk:=false.B;emitPass:=false.B;accumulator:=0.U;normalized:=0.U;operation:=square;state:=readInput}
          }.otherwise{beat:=beat+1.U;state:=writeOutput}
        }
      }
  }
  when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;state:=scalarWait}
  when(io.scalar.result.fire){
    scalarReturned:=scalarReturned+1.U
    val r=io.scalar.result.bits
    val fatalFlags=Mux(operation===mean,r.flags(4,2).orR,r.flags(4,1).orR)
    val needsFlags=operation===mean || operation===epsilon
    when(r.error || (needsFlags && (!r.primitiveFlagsValid || fatalFlags)) || !TensorMath.finite(r.value)){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        value:=r.value;state:=scalarIssue
        switch(operation){
          is(mean){operation:=epsilon};is(epsilon){operation:=root};is(root){operation:=inverse}
          is(inverse){invRms:=r.value;emitPass:=true.B;chunk:=false.B;beat:=0.U;lane:=0.U;state:=readInput}
        }
      }
  }
  when(io.vectorRequest.fire){vectorAccepted:=vectorAccepted+1.U;state:=vectorWait}
  when(io.vectorResult.fire){
    vectorReturned:=vectorReturned+1.U
    val r=io.vectorResult.bits
    val badLane=(0 until 32).map{i=>
      !TensorMath.finite(r.value(i)) ||
      Mux(operation===materialize,r.value(i)(15,0)=/=0.U,
        Mux(vectorMultiply,r.arithFlags(i)(4,2).orR,r.arithFlags(i)(4,1).orR))
    }.reduce(_||_)
    val badFlags=r.formatFlagsValid || Mux(operation===materialize,r.arithFlagsValid,!r.arithFlagsValid)
    when(r.error || badFlags || badLane){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        state:=vectorIssue
        switch(operation){
          is(square){valueVector:=r.value;operation:=sum}
          is(sum){accumVector:=r.value
            when(lane(3,0)===15.U){operation:=residue}
              .otherwise{lane:=lane+1.U;operation:=square}}
          is(residue){
            output(0):=r.value.asUInt(511,0);output(1):=r.value.asUInt(1023,512)
            accumVector:=VecInit(Seq.fill(32)(0.U(32.W)))
            when(!lane(4)){lane:=16.U;operation:=square}
              .otherwise{lane:=0.U
                when(!chunk && accepted.hiddenWidth===2048.U){chunk:=true.B;beat:=0.U;operation:=square;state:=readInput}
                  .otherwise{normalized:=0.U;operation:=foldResidue}}
          }
          is(foldResidue){accumVector:=r.value
            when(lane===3.U){valueVector:=r.value;lane:=0.U;normalized:=0.U;operation:=foldLane}
              .otherwise{lane:=lane+1.U}}
          is(foldLane){normalized:=r.value(0)
            when(lane===7.U){operation:=mean;state:=scalarIssue}
              .otherwise{lane:=lane+1.U}}
          is(normalize){accumVector:=r.value;operation:=gamma}
          is(gamma){valueVector:=r.value;operation:=weighted}
          is(weighted){valueVector:=r.value;operation:=materialize}
          is(materialize){
            output(lane(9,5)):=VecInit((0 until 32).map(i=>r.value(i)(31,16))).asUInt
            when(lane===992.U){beat:=0.U;state:=writeOutput}
              .otherwise{lane:=lane+32.U;operation:=normalize}
          }
        }
      }
  }
  val expectedScalar=accepted.tokens.pad(64)*4.U
  val expectedVector=accepted.tokens.pad(64)*Mux(accepted.hiddenWidth===1024.U,206.U,400.U)
  val expectedFormat=accepted.tokens.pad(64)*accepted.hiddenWidth.pad(64)
  // Each row/chunk reads input for reduction, reads it again for emit, reads
  // gamma, then writes output: exactly four 64-byte transactions per beat.
  val expectedMemory=(expectedFormat>>5)<<2
  val countsExact=scalarAccepted.pad(64)===expectedScalar && scalarReturned.pad(64)===expectedScalar &&
    formatAccepted===0.U && formatReturned===0.U &&
    vectorAccepted.pad(64)===expectedVector && vectorReturned.pad(64)===expectedVector &&
    memoryAccepted.pad(64)===expectedMemory && sequence.pad(64)===expectedMemory
  when(state===finish && io.resourcesDrained){
    terminal.tag:=accepted.tag;terminal.status:=Mux(poison || currentFault, Mux(status===Status.Ok.U,Status.Protocol.U,status),status)
    terminal.accepted:=accepted;terminal.writeBytes:=bytes;terminal.cycles:=cycles
    terminal.outputAckBytes:=bytes;terminal.resourcesDrained:=io.resourcesDrained
    terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned
    terminal.formatAccepted:=formatAccepted;terminal.formatReturned:=formatReturned
    terminal.vectorAccepted:=vectorAccepted;terminal.vectorReturned:=vectorReturned
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    terminal.outputCommitted:=status===Status.Ok.U && !poison && !currentFault && bytes===expectedBytes && countsExact
    when(status===Status.Ok.U && (bytes=/=expectedBytes || !countsExact)){terminal.status:=Status.Protocol.U;poison:=true.B}
    state:=report
  }
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid,io.vectorRequest.valid,io.formatRequest.valid))<=1.U)
}
