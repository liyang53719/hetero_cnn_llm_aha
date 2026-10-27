// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private accepted-scheduler recipe, not an independent host capability.
  * Recipe1 preserves the original CPU-default8lane/4residue block order for
  * H1024 and H2048. Qwen2 FP32-storage/public21 never uses this BF16 owner. */
class GdnRuntimeRmsNormJobV3 extends GdnRmsNormJob { val reductionRecipe=UInt(2.W) }

/** Functional runtime successor of the original fixed-bank RMS borrower.
  * Three32x512bit banks, fourFP32 working registers; no arithmetic Module.
  * Output's first128B stores32 residues until inverse is known. A H1024 row
  * uses one1024-element chunk; H2048 uses two. Every512-element block is
  * accumulated separately, including all original +0 additions. Final BF16
  * materialization borrows the unique shared formatter (no local rounder).
  * The scalar-only schedule is NOT the proposed32lane performance design.
  * Shared services must be exclusive, nonzero-latency, exact-owner routers.
  * Unknown replies quarantine without refund. Reset requires real isolation.
  * Held offers and held terminal bits survive latefault; the parent must also
  * sample resetRequired/live transport drain before publishing any output. */
class GdnRuntimeRmsNormOwnerV3 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new GdnRuntimeRmsNormJobV3))
    val done=Decoupled(new GdnRmsNormResult)
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val parentFault=Input(Bool())
    val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
  })
  val states=Enum(12)
  val idle=states(0);val readInput=states(1);val waitInput=states(2)
  val readWeight=states(3);val waitWeight=states(4);val scalarIssue=states(5);val scalarWait=states(6)
  val formatIssue=states(7);val formatWait=states(8);val writeOutput=states(9);val waitOutput=states(10);val finish=states(11)
  val report=12.U(4.W);val locked=13.U(4.W)
  val state=RegInit(idle)
  val ops=Enum(12)
  val square=ops(0);val sum=ops(1);val residue=ops(2);val foldResidue=ops(3);val foldLane=ops(4)
  val mean=ops(5);val epsilon=ops(6);val root=ops(7);val inverse=ops(8);val normalize=ops(9);val gamma=ops(10);val weighted=ops(11)
  val operation=RegInit(square);val accepted=Reg(new GdnRuntimeRmsNormJobV3)
  val input=Reg(Vec(32,UInt(512.W)));val weights=Reg(Vec(32,UInt(512.W)));val output=Reg(Vec(32,UInt(512.W)))
  val accumulator=RegInit(0.U(32.W));val value=Reg(UInt(32.W));val normalized=RegInit(0.U(32.W));val invRms=Reg(UInt(32.W))
  val lane=RegInit(0.U(10.W));val beat=RegInit(0.U(5.W));val token=RegInit(0.U(7.W));val chunk=RegInit(false.B);val emitPass=RegInit(false.B)
  val sequence=RegInit(0.U(32.W));val bytes=RegInit(0.U(64.W));val cycles=RegInit(0.U(64.W))
  val status=RegInit(Status.Ok.U(8.W));val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val terminal=Reg(new GdnRmsNormResult)
  val active=state=/=idle && state=/=locked
  val memoryOffer=state===readInput || state===readWeight || state===writeOutput
  val memoryDebt=state===waitInput || state===waitWeight || state===waitOutput
  val expectedTag=Cat(accepted.tag,sequence)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  val unknownScalar=io.scalar.result.valid && (state=/=scalarWait || io.scalar.result.bits.policy=/=0.U)
  val unknownFormat=io.formatResult.valid && state=/=formatWait
  val unknown=unknownMemory || unknownScalar || unknownFormat
  val currentFault=io.parentFault || unknown
  when(unknown){quarantine:=true.B}
  when(currentFault){poison:=true.B;when(state=/=report && status===Status.Ok.U){status:=Status.Protocol.U}}
  io.resetRequired:=poison || quarantine || currentFault
  val quiet= !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid
  val noService= !memoryOffer && !memoryDebt && state=/=scalarIssue && state=/=scalarWait && state=/=formatIssue && state=/=formatWait
  io.resourcesDrained:=noService && quiet && !quarantine && !unknown
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  when(active && state=/=report){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={when(status===Status.Ok.U){status:=code};poison:=true.B;state:=finish}

  // Original reduction lane encoding: lane8/residue4/block2/term16.
  val reduceIndex=Cat(lane(4),lane(3,0),lane(6,5),lane(9,7))
  val inputIndex=Mux(emitPass,lane,reduceIndex)
  val inputWords=input(inputIndex(9,5)).asTypeOf(Vec(32,UInt(16.W)))
  val x=Cat(inputWords(inputIndex(4,0)),0.U(16.W))
  val partialIndex=Mux(operation===foldResidue,lane(4,0),Cat(lane(9,7),lane(6,5)))
  val partialBeat=Cat(0.U(4.W),partialIndex(4))
  val outputIndex=Mux(memoryOffer || memoryDebt,beat,Mux(!emitPass,partialBeat,lane(9,5)))
  val outputBeat=output(outputIndex)
  val partialWords=outputBeat.asTypeOf(Vec(16,UInt(32.W)))
  val previousPartial=partialWords(partialIndex(3,0))
  val previousResidue=Mux(!chunk && !lane(4),0.U(32.W),previousPartial)
  val weightWords=weights(lane(9,5)).asTypeOf(Vec(32,UInt(16.W)))
  val rowBytes=accepted.hiddenWidth.pad(64)<<1
  val rowOffset=token.pad(64)*rowBytes
  val chunkOffset=Mux(chunk,2048.U(64.W),0.U(64.W));val beatOffset=beat.pad(64)<<6
  val expectedBytes=accepted.tokens.pad(64)*rowBytes
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || quarantine)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write:=state===writeOutput
  io.memory.bits.address:=MuxLookup(state,accepted.input+rowOffset+chunkOffset+beatOffset)(Seq(
    readWeight->(accepted.weight+chunkOffset+beatOffset),writeOutput->(accepted.output+rowOffset+chunkOffset+beatOffset)))
  io.memory.bits.data:=Mux(state===writeOutput,outputBeat,0.U)
  io.memory.bits.mask:=Mux(state===writeOutput,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=expectedTag
  io.response.ready:=memoryDebt && !quarantine && !unknownMemory
  val scalarHeld=HeldDecoupledOffer(state===scalarIssue,io.scalar.request.ready,poison || currentFault || quarantine)
  io.scalar.request.valid:=scalarHeld.valid;io.scalar.request.bits.policy:=0.U
  io.scalar.request.bits.payload.op:=MuxLookup(operation,ScalarOp.Add.U)(Seq(square->ScalarOp.MulIeeeRne.U,mean->ScalarOp.MulIeeeRne.U,
    root->ScalarOp.Sqrt.U,inverse->ScalarOp.Div.U,normalize->ScalarOp.MulIeeeRne.U,weighted->ScalarOp.MulIeeeRne.U))
  io.scalar.request.bits.payload.a:=MuxLookup(operation,value)(Seq(square->x,sum->accumulator,residue->previousResidue,
    foldResidue->accumulator,foldLane->normalized,mean->normalized,inverse->F32.lit(1),normalize->x,gamma->F32.lit(1),weighted->normalized))
  io.scalar.request.bits.payload.b:=MuxLookup(operation,value)(Seq(square->x,residue->accumulator,foldResidue->previousPartial,
    foldLane->accumulator,mean->Mux(accepted.hiddenWidth===1024.U,F32.lit(1.0/1024),F32.lit(1.0/2048)),
    epsilon->F32.lit(1e-6),root->0.U,normalize->invRms,gamma->Cat(weightWords(lane(4,0)),0.U(16.W))))
  io.scalar.result.ready:=state===scalarWait && !quarantine && !unknownScalar
  val formatHeld=HeldDecoupledOffer(state===formatIssue,io.formatRequest.ready,poison || currentFault || quarantine)
  io.formatRequest.valid:=formatHeld.valid;io.formatRequest.bits.value:=value
  io.formatResult.ready:=state===formatWait && !quarantine && !unknownFormat
  // Never discard an already offered packet. New work stops at a real safe
  // boundary; matching pending responses still retire under ordinary poison.
  when((poison || currentFault) && !quarantine){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
    when(state===formatIssue && !formatHeld.held && !io.formatRequest.fire){state:=finish}
  }
  when(io.job.fire){
    accepted:=io.job.bits;sequence:=0.U;bytes:=0.U;cycles:=0.U;status:=Status.Ok.U
    beat:=0.U;token:=0.U;lane:=0.U;chunk:=false.B;emitPass:=false.B;accumulator:=0.U;normalized:=0.U;operation:=square
    val j=io.job.bits;val nb=(j.tokens.pad(80)*j.hiddenWidth)<<1;val wb=j.hiddenWidth.pad(80)<<1
    def bad(base:UInt,n:UInt):Bool=base(5,0)=/=0.U || base.pad(80)+n>(BigInt(1)<<56).U
    def overlap(a:UInt,n:UInt,b:UInt,m:UInt):Bool=a.pad(80)<b.pad(80)+m && b.pad(80)<a.pad(80)+n
    when(j.reductionRecipe=/=1.U){fail(Status.Unsupported.U)}
      .elsewhen(j.tokens===0.U || j.tokens>128.U || !(j.hiddenWidth===1024.U || j.hiddenWidth===2048.U) ||
        bad(j.input,nb) || bad(j.weight,wb) || bad(j.output,nb) || overlap(j.input,nb,j.weight,wb) ||
        overlap(j.input,nb,j.output,nb) || overlap(j.weight,wb,j.output,nb)){fail(Status.Bounds.U)}
      .otherwise{state:=readInput}
  }
  when(io.memory.fire){state:=MuxLookup(state,waitInput)(Seq(readWeight->waitWeight,writeOutput->waitOutput))}
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
              when(state===waitWeight){operation:=normalize;state:=scalarIssue}
                .elsewhen(emitPass){state:=readWeight}
                .otherwise{accumulator:=0.U;operation:=square;state:=scalarIssue}
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
  when(io.scalar.request.fire){state:=scalarWait}
  when(io.scalar.result.fire){
    val r=io.scalar.result.bits;val multiply=operation===square || operation===mean || operation===normalize || operation===weighted
    val fatalFlags=Mux(multiply,r.flags(4,2).orR,r.flags(4,1).orR)
    // ScalarV2 exports flags only for primitive Add/Mul. Div/Sqrt use its
    // existing error/finite contract; no invented valid flags for those SFUs.
    val needsFlags=operation=/=root && operation=/=inverse
    when(r.error || (needsFlags && (!r.primitiveFlagsValid || fatalFlags)) || !TensorMath.finite(r.value)){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        value:=r.value;state:=scalarIssue
        switch(operation){
          is(square){operation:=sum}
          is(sum){accumulator:=r.value;when(lane(3,0)===15.U){operation:=residue}.otherwise{lane:=lane+1.U;operation:=square}}
          is(residue){
            val patch=Wire(Vec(16,UInt(32.W)));patch:=partialWords;patch(partialIndex(3,0)):=r.value;output(partialBeat):=patch.asUInt;accumulator:=0.U
            when(lane===1023.U){lane:=0.U
              when(!chunk && accepted.hiddenWidth===2048.U){chunk:=true.B;beat:=0.U;operation:=square;state:=readInput}
                .otherwise{normalized:=0.U;operation:=foldResidue}
            }.otherwise{lane:=lane+1.U;operation:=square}
          }
          is(foldResidue){accumulator:=r.value;when(lane(1,0)===3.U){operation:=foldLane}.otherwise{lane:=lane+1.U}}
          is(foldLane){normalized:=r.value;accumulator:=0.U;when(lane===31.U){operation:=mean}.otherwise{lane:=lane+1.U;operation:=foldResidue}}
          is(mean){operation:=epsilon};is(epsilon){operation:=root};is(root){operation:=inverse}
          is(inverse){invRms:=r.value;emitPass:=true.B;chunk:=false.B;beat:=0.U;lane:=0.U;state:=readInput}
          is(normalize){normalized:=r.value;operation:=gamma};is(gamma){operation:=weighted}
          is(weighted){state:=formatIssue}
        }
      }
  }
  when(io.formatRequest.fire){state:=formatWait}
  when(io.formatResult.fire){
    when(io.formatResult.bits.error || io.formatResult.bits.value(14,7)===255.U){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        val patch=Wire(Vec(32,UInt(16.W)));patch:=outputBeat.asTypeOf(Vec(32,UInt(16.W)));patch(lane(4,0)):=io.formatResult.bits.value;output(lane(9,5)):=patch.asUInt
        when(lane===1023.U){beat:=0.U;state:=writeOutput}.otherwise{lane:=lane+1.U;operation:=normalize;state:=scalarIssue}
      }
  }
  when(state===finish && io.resourcesDrained){
    terminal.tag:=accepted.tag;terminal.status:=Mux(poison || currentFault, Mux(status===Status.Ok.U,Status.Protocol.U,status),status)
    terminal.writeBytes:=bytes;terminal.cycles:=cycles
    terminal.outputCommitted:=status===Status.Ok.U && !poison && !currentFault && bytes===expectedBytes
    when(status===Status.Ok.U && bytes=/=expectedBytes){terminal.status:=Status.Protocol.U;poison:=true.B}
    state:=report
  }
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid,io.formatRequest.valid))<=1.U)
}
