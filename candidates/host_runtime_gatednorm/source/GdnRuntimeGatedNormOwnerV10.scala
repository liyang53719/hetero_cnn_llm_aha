// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Runtime16/32-head successor of the original GdnRuntimeGatedNormOwner.
  * ALL scalar nodes, operands, policies, FP32 order and BF16 boundaries are
  * preserved. The two original local BF16 RNE sites now borrow the ONE shared
  * raw FP32 formatter; returning BF16 bits is not a second local rounding.
  * No Matrix, Scalar, ALU, SFU, formatter or memory service is instantiated.
  * Fixed payload storage remains gamma128 FP32 plus core/gate/output128 BF16.
  *
  * Each head: 128 squares + 128 ascending adds + mean/epsilon/sqrt/inverse
  * + 128 * eight original per-element scalar nodes = 1284 scalar requests.
  * Two original materialization sites per element = 256 format requests.
  * Every successful row requires four actual output ACKs. Completion cannot
  * bypass held service offers, matching replies or exact successful counts.
  * Unknown replies quarantine without debt refund; recovery needs joint reset.
  * The original sqrt/reciprocal/exp recipe is not an official torch-bit proof.
  */
class GdnRuntimeGatedNormOwnerV10 extends Module {
  val io=IO(new GdnRuntimeGatedNormPortV10)
  val idle :: readWeight :: waitWeight :: readCore :: waitCore :: readGate :: waitGate :: scalarIssue :: scalarWait :: formatIssue :: formatWait :: writeOutput :: waitOutput :: finish :: report :: locked :: Nil=Enum(16)
  val state=RegInit(idle)
  val square :: sum :: mean :: epsilon :: root :: inverse :: normalize :: weight :: exp :: denominator :: sigmoidInverse :: sigmoidSign :: activate :: gated :: Nil=Enum(14)
  val operation=RegInit(square)
  val job=Reg(new GdnRuntimeGatedNormJobV10)
  val weights=Reg(Vec(128,UInt(32.W)))
  val core=Reg(Vec(128,UInt(16.W)));val gate=Reg(Vec(128,UInt(16.W)));val output=Reg(Vec(128,UInt(16.W)))
  val head=RegInit(0.U(5.W));val token=RegInit(0.U(7.W));val beat=RegInit(0.U(3.W));val lane=RegInit(0.U(7.W))
  val accumulator=RegInit(0.U(32.W));val value=Reg(UInt(32.W));val invRms=Reg(UInt(32.W))
  val weighted=Reg(UInt(32.W));val exponential=Reg(UInt(32.W))
  val sequence=RegInit(0.U(32.W));val memoryAccepted=RegInit(0.U(32.W))
  val scalarAccepted=RegInit(0.U(32.W));val scalarReturned=RegInit(0.U(32.W))
  val formatAccepted=RegInit(0.U(32.W));val formatReturned=RegInit(0.U(32.W))
  val status=RegInit(Status.Ok.U(8.W));val bytes=RegInit(0.U(64.W));val cycles=RegInit(0.U(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val terminal=Reg(new GdnRuntimeGatedNormResultV10)
  val rows=job.tokens.pad(64)*job.heads.pad(64)
  val expectedBytes=rows<<8
  val expectedScalar=(rows*1284.U)(31,0)
  val expectedFormat=(rows<<8)(31,0)
  val expectedMemory=(8.U+rows*12.U)(31,0)
  val memoryOffer=state===readWeight || state===readCore || state===readGate || state===writeOutput
  val memoryDebt=state===waitWeight || state===waitCore || state===waitGate || state===waitOutput
  val expectedTag=Cat(job.tag,sequence)
  val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  val unknownScalar=io.scalar.result.valid && (state=/=scalarWait || io.scalar.result.bits.policy=/=requestPolicy)
  val unknownFormat=io.formatResult.valid && state=/=formatWait
  val unknown=unknownMemory || unknownScalar || unknownFormat
  val currentFault=io.parentFault || unknown
  when(unknown){quarantine:=true.B}
  when(currentFault){poison:=true.B;when(state=/=report && status===Status.Ok.U){status:=Status.Protocol.U}}
  val quiet= !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid
  val noService= !memoryOffer && !memoryDebt && state=/=scalarIssue && state=/=scalarWait && state=/=formatIssue && state=/=formatWait
  io.resourcesDrained:=noService && quiet && !quarantine && !unknown
  io.resetRequired:=poison || quarantine || currentFault
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal

  val rowOffset=((token.pad(64)*job.heads)+head.pad(64))<<8
  val beatOffset=beat.pad(64)<<6
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || quarantine)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write:=state===writeOutput
  io.memory.bits.address:=MuxLookup(state,job.core+rowOffset+beatOffset)(Seq(
    readWeight->(job.weight+beatOffset),readGate->(job.gate+rowOffset+beatOffset),
    writeOutput->(job.output+rowOffset+beatOffset)))
  val outputBeats=output.asUInt.asTypeOf(Vec(4,UInt(512.W)))
  io.memory.bits.data:=Mux(state===writeOutput,outputBeats(beat(1,0)),0.U)
  io.memory.bits.mask:=Mux(state===writeOutput,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=expectedTag
  io.response.ready:=memoryDebt && !quarantine && !unknownMemory

  val x=Cat(core(lane),0.U(16.W));val z=Cat(gate(lane),0.U(16.W))
  val scalarHeld=HeldDecoupledOffer(state===scalarIssue,io.scalar.request.ready,poison || currentFault || quarantine)
  io.scalar.request.valid:=scalarHeld.valid
  io.scalar.request.bits.policy:=requestPolicy
  io.scalar.request.bits.payload.op:=MuxLookup(operation,ScalarOp.MulIeeeRne.U)(Seq(
    sum->ScalarOp.Add.U,epsilon->ScalarOp.Add.U,root->ScalarOp.Sqrt.U,
    inverse->ScalarOp.Div.U,exp->ScalarOp.ExpNegative.U,
    denominator->ScalarOp.Add.U,sigmoidInverse->ScalarOp.Div.U))
  io.scalar.request.bits.payload.a:=MuxLookup(operation,value)(Seq(
    square->x,sum->accumulator,mean->accumulator,
    inverse->F32.lit(1),normalize->x,weight->weights(lane),exp->z,
    denominator->F32.lit(1),sigmoidInverse->F32.lit(1),gated->weighted))
  io.scalar.request.bits.payload.b:=MuxLookup(operation,value)(Seq(
    square->x,mean->F32.lit(1.0/128),epsilon->F32.lit(1e-6),
    root->0.U,normalize->invRms,exp->0.U,denominator->exponential,
    sigmoidSign->Mux(z(31),exponential,F32.lit(1)),activate->z))
  io.scalar.result.ready:=state===scalarWait && !quarantine && !unknownScalar
  val formatHeld=HeldDecoupledOffer(state===formatIssue,io.formatRequest.ready,poison || currentFault || quarantine)
  io.formatRequest.valid:=formatHeld.valid;io.formatRequest.bits.value:=value
  io.formatResult.ready:=state===formatWait && !quarantine && !unknownFormat
  // First publication is vetoed by the CURRENT fault; an already visible
  // request and its payload survive late fault until real request.fire.
  when((poison || currentFault) && !quarantine){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===scalarIssue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
    when(state===formatIssue && !formatHeld.held && !io.formatRequest.fire){state:=finish}
  }
  when(state=/=idle && state=/=report && state=/=locked){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={when(status===Status.Ok.U){status:=code};poison:=true.B;state:=finish}

  when(io.job.fire){
    job:=io.job.bits;head:=0.U;token:=0.U;beat:=0.U;lane:=0.U
    sequence:=0.U;memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U
    formatAccepted:=0.U;formatReturned:=0.U;status:=Status.Ok.U;bytes:=0.U;cycles:=0.U
    val j=io.job.bits;val vectorBytes=(j.tokens*j.heads).pad(66)<<8;val weightBytes=512.U(66.W)
    def badSpan(base:UInt,size:UInt):Bool=base(5,0)=/=0.U || base.pad(66)+size>(BigInt(1)<<56).U
    def overlap(a:UInt,na:UInt,b:UInt,nb:UInt):Bool=a.pad(66)<b.pad(66)+nb && b.pad(66)<a.pad(66)+na
    val badAddress=badSpan(j.core,vectorBytes) || badSpan(j.gate,vectorBytes) || badSpan(j.weight,weightBytes) || badSpan(j.output,vectorBytes)
    val unsafeWrites=overlap(j.output,vectorBytes,j.core,vectorBytes) || overlap(j.output,vectorBytes,j.gate,vectorBytes) || overlap(j.output,vectorBytes,j.weight,weightBytes)
    when(j.tokens===0.U || j.tokens>128.U || (j.heads=/=16.U && j.heads=/=32.U) || badAddress || unsafeWrites){fail(Status.Bounds.U)}
      .otherwise{state:=readWeight}
  }
  when(io.memory.fire){
    memoryAccepted:=memoryAccepted+1.U
    state:=MuxLookup(state,waitCore)(Seq(readWeight->waitWeight,readGate->waitGate,writeOutput->waitOutput))
  }
  when(io.response.fire){
    val r=io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    // ACK accounting is independent of late poison: successful physical writes
    // already happened, but can never turn poisoned staging into publication.
    when(state===waitOutput && !r.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        when(state===waitWeight){
          for(i<-0 until 16)weights(Cat(beat,i.U(4.W))):=r.data((i+1)*32-1,i*32)
          when(beat===7.U){beat:=0.U;state:=readCore}.otherwise{beat:=beat+1.U;state:=readWeight}
        }
        when(state===waitCore || state===waitGate){
          for(i<-0 until 32){
            val v=r.data((i+1)*16-1,i*16)
            when(state===waitCore){core(Cat(beat(1,0),i.U(5.W))):=v}
              .otherwise{gate(Cat(beat(1,0),i.U(5.W))):=v}
          }
          when(beat===3.U){
            beat:=0.U
            when(state===waitCore){state:=readGate}
              .otherwise{accumulator:=0.U;lane:=0.U;operation:=square;state:=scalarIssue}
          }.otherwise{beat:=beat+1.U;state:=Mux(state===waitCore,readCore,readGate)}
        }
        when(state===waitOutput){
          when(beat===3.U){
            beat:=0.U
            when(head+&1.U===job.heads){
              head:=0.U
              when(token+&1.U===job.tokens){state:=finish}.otherwise{token:=token+1.U;state:=readCore}
            }.otherwise{head:=head+1.U;state:=readCore}
          }.otherwise{beat:=beat+1.U;state:=writeOutput}
        }
      }
  }
  when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;state:=scalarWait}
  when(io.scalar.result.fire){
    val r=io.scalar.result.bits.value
    scalarReturned:=scalarReturned+1.U
    when(io.scalar.result.bits.error || !TensorMath.finite(r)){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{
        state:=scalarIssue;value:=r
        switch(operation){
          is(square){operation:=sum}
          is(sum){
            accumulator:=r
            when(lane===127.U){lane:=0.U;operation:=mean}.otherwise{lane:=lane+1.U;operation:=square}
          }
          is(mean){operation:=epsilon}
          is(epsilon){operation:=root}
          is(root){operation:=inverse}
          is(inverse){invRms:=r;operation:=normalize}
          is(normalize){state:=formatIssue} // original F32.bf(r), now shared raw formatter
          is(weight){
            weighted:=r;operation:=exp
            when(!TensorMath.finite(z) || (z(31) && z(30,0)>=F32.lit(80))){fail(Status.Numerical.U)}
          }
          is(exp){exponential:=r;operation:=denominator}
          is(denominator){operation:=sigmoidInverse}
          is(sigmoidInverse){operation:=sigmoidSign}
          is(sigmoidSign){operation:=activate}
          is(activate){operation:=gated}
          is(gated){state:=formatIssue} // original TensorMath.bf16Rne(r), now SAME formatter
        }
      }
  }
  when(io.formatRequest.fire){formatAccepted:=formatAccepted+1.U;state:=formatWait}
  when(io.formatResult.fire){
    val r=io.formatResult.bits
    formatReturned:=formatReturned+1.U
    when(r.error || r.value(14,7)===255.U){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .elsewhen(operation===normalize){value:=Cat(r.value,0.U(16.W));operation:=weight;state:=scalarIssue}
      .elsewhen(operation===gated){
        output(lane):=r.value
        when(lane===127.U){beat:=0.U;state:=writeOutput}
          .otherwise{lane:=lane+1.U;operation:=normalize;state:=scalarIssue}
      }.otherwise{fail(Status.Protocol.U)}
  }
  when(state===finish && io.resourcesDrained){
    val exact=bytes===expectedBytes && memoryAccepted===expectedMemory && sequence===expectedMemory &&
      scalarAccepted===expectedScalar && scalarReturned===expectedScalar && formatAccepted===expectedFormat && formatReturned===expectedFormat
    val complete=status===Status.Ok.U && !poison && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag;terminal.writeBytes:=bytes;terminal.cycles:=cycles
    terminal.status:=Mux(status===Status.Ok.U && (!exact || poison || currentFault),Status.Protocol.U,status)
    terminal.outputCommitted:=complete
    when(status===Status.Ok.U && !exact){poison:=true.B}
    state:=report
  }
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid,io.formatRequest.valid))<=1.U)
}
