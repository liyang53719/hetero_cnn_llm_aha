// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private decoded job. Same fixed 32-lane banks for every runtime profile.
  * Add: BF16 [M,H], H=1024/2048. SigmoidMul: BF16 [M,Q*256], Q=8/16.
  * This leaf does not authenticate the producers: original Guard/Prefix actual
  * fires bind the complete Host/txn64/epoch and strict producer<consumer tags.
  */
class GdnRuntimeElementwiseJobV15 extends Bundle {
  val op=UInt(2.W);val tokens=UInt(16.W);val rowWidth=UInt(16.W)
  val a=UInt(64.W);val b=UInt(64.W);val output=UInt(64.W);val tag=UInt(32.W)
}
object GdnRuntimeElementwiseJobV15 {
  def fromOwner(j:QwenOwnerJob):GdnRuntimeElementwiseJobV15={
    val r=Wire(new GdnRuntimeElementwiseJobV15)
    r.op:=j.gdnElementwiseOp;r.tokens:=j.m;r.rowWidth:=j.n
    r.a:=j.a;r.b:=j.b;r.output:=j.dst;r.tag:=j.tag;r
  }
}
class GdnRuntimeElementwiseResultV15 extends Bundle {
  val accepted=new GdnRuntimeElementwiseJobV15
  val tag=UInt(32.W);val status=UInt(8.W);val writeBytes=UInt(64.W);val cycles=UInt(64.W)
  val outputAckBytes=UInt(64.W);val outputCommitted=Bool();val resourcesDrained=Bool()
  val scalarAccepted=UInt(32.W);val scalarReturned=UInt(32.W)
  val formatAccepted=UInt(32.W);val formatReturned=UInt(32.W)
  val memoryAccepted=UInt(32.W);val memoryReturned=UInt(32.W)
}
class QwenRuntimeElementwisePublicationV15 extends Bundle {
  val memory=Bool();val scalar=Bool();val format=Bool()
}
class GdnRuntimeElementwisePortV15 extends Bundle {
  val job=Flipped(Decoupled(new GdnRuntimeElementwiseJobV15))
  val done=Decoupled(new GdnRuntimeElementwiseResultV15)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val scalar=new UnifiedScalarClientV2
  val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
  val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
  val parentFault=Input(Bool());val published=Input(new QwenRuntimeElementwisePublicationV15)
  val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
}

/** Derived from original GdnElementwiseOwner.scala SHA256
  * 01b394526f75b9732c3e605652c64f3968851aca97258a3a640bc056de1f2fe3.
  * Original FP32 operands/order retained; original BF16 RNE sites now borrow
  * the SAME raw shared formatter. No local FPU, Matrix, formatter or DMA.
  * Attention is exp(-abs(g)),1+exp,1/denom,sign multiply, BF16(sigmoid),
  * context multiply, BF16(output): five Scalar and two format requests/lane.
  * No SiLU multiplication by gate and no GDN RMS normalization is inserted.
  * Residual is one FP32 Add and one BF16 materialization/lane. Negative gate
  * <=-80 remains Unsupported, never silently saturated. Scalar Legacy errors
  * remain errors; no invented UF/NX contract. Qwen2 FP32 storage is untouched.
  * Only successful real write ACKs count. Staging is not final block commit.
  */
class GdnRuntimeElementwiseOwnerV15 extends Module {
  val io=IO(new GdnRuntimeElementwisePortV15)
  val idle :: readA :: waitA :: readB :: waitB :: checkLane :: scalarIssue :: scalarWait :: formatIssue :: formatWait :: writeOutput :: waitOutput :: drain :: finish :: report :: locked :: Nil=Enum(16)
  val state=RegInit(idle)
  val add :: exp :: denominator :: inverse :: sign :: multiply :: Nil=Enum(6)
  val operation=RegInit(add)
  val job=Reg(new GdnRuntimeElementwiseJobV15)
  val inputA=Reg(Vec(32,UInt(16.W)));val inputB=Reg(Vec(32,UInt(16.W)));val output=Reg(Vec(32,UInt(16.W)))
  val remaining=Reg(UInt(32.W));val offset=RegInit(0.U(64.W));val lane=RegInit(0.U(5.W))
  val value=Reg(UInt(32.W));val exponential=Reg(UInt(32.W))
  val sequence=RegInit(0.U(32.W));val memoryAccepted=RegInit(0.U(32.W))
  val scalarAccepted=RegInit(0.U(32.W));val scalarReturned=RegInit(0.U(32.W))
  val formatAccepted=RegInit(0.U(32.W));val formatReturned=RegInit(0.U(32.W))
  val memoryPending=RegInit(false.B);val scalarPending=RegInit(false.B);val formatPending=RegInit(false.B)
  val memoryWrite=Reg(Bool());val memoryReadB=Reg(Bool())
  val status=RegInit(Status.Ok.U(8.W));val bytes=RegInit(0.U(64.W));val cycles=RegInit(0.U(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val terminal=Reg(new GdnRuntimeElementwiseResultV15)
  val faultNow=WireDefault(false.B);val faultCode=WireDefault(Status.Protocol.U(8.W))
  val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)
  val unknownMemory=io.response.valid && (!memoryPending || io.response.bits.tag=/=Cat(job.tag,sequence))
  val unknownScalar=io.scalar.result.valid && (!scalarPending || io.scalar.result.bits.policy=/=requestPolicy)
  val unknownFormat=io.formatResult.valid && !formatPending
  val unknown=unknownMemory || unknownScalar || unknownFormat
  val currentFault=io.parentFault || unknown
  def fail(code:UInt):Unit={faultNow:=true.B;faultCode:=code}
  when(unknown){quarantine:=true.B;fail(Status.Protocol.U)}
  when(io.parentFault){fail(Status.Protocol.U)}
  // Published observations only update registers/assertions. Never reflect
  // published-valid combinationally into raw-valid or resetRequired.
  def publishedOffer(intent:Bool,ready:Bool,published:Bool):HeldDecoupledOfferSignals={
    val held=RegInit(false.B)
    val visible=intent && ((!poison && !quarantine && !currentFault) || held)
    when(published){held:= !ready}
    assert(!published || visible,"actual publication requires retained raw intent")
    assert(!(visible && ready) || published,"raw acceptance must be real publication")
    assert(!held || intent,"published held offer may not be withdrawn")
    HeldDecoupledOfferSignals(visible,held,visible && ready)
  }
  val memoryIntent=state===readA || state===readB || state===writeOutput
  val memOffer=publishedOffer(memoryIntent,io.memory.ready,io.published.memory)
  val scalarOffer=publishedOffer(state===scalarIssue,io.scalar.request.ready,io.published.scalar)
  val formatOffer=publishedOffer(state===formatIssue,io.formatRequest.ready,io.published.format)
  val quiet= !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid
  io.job.ready:=state===idle && !poison && !quarantine && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  // Local faultNow is registered into poison below; feeding it to resetRequired
  // would close job.fire -> fail -> Kernel admission -> job.fire.
  io.resetRequired:=poison || quarantine || currentFault || status=/=Status.Ok.U
  io.resourcesDrained:= !memoryPending && !scalarPending && !formatPending &&
    !memOffer.held && !scalarOffer.held && !formatOffer.held &&
    !io.memory.valid && !io.scalar.request.valid && !io.formatRequest.valid && quiet && !quarantine && !unknown
  val x=Cat(inputA(lane),0.U(16.W));val y=Cat(inputB(lane),0.U(16.W))
  io.memory.valid:=memOffer.valid
  io.memory.bits.write:=state===writeOutput
  io.memory.bits.address:=Mux(state===writeOutput,job.output,Mux(state===readB,job.b,job.a))+offset
  io.memory.bits.data:=Mux(state===writeOutput,output.asUInt,0.U)
  io.memory.bits.mask:=Mux(state===writeOutput,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=Cat(job.tag,sequence)
  io.response.ready:=memoryPending && !unknownMemory
  io.scalar.request.valid:=scalarOffer.valid;io.scalar.request.bits.policy:=requestPolicy
  io.scalar.request.bits.payload.op:=MuxLookup(operation,ScalarOp.MulIeeeRne.U)(Seq(
    add->ScalarOp.Add.U,exp->ScalarOp.ExpNegative.U,denominator->ScalarOp.Add.U,inverse->ScalarOp.Div.U))
  io.scalar.request.bits.payload.a:=MuxLookup(operation,value)(Seq(
    add->x,exp->x,denominator->F32.lit(1),inverse->F32.lit(1)))
  io.scalar.request.bits.payload.b:=MuxLookup(operation,value)(Seq(
    add->y,exp->0.U,denominator->exponential,sign->Mux(x(31),exponential,F32.lit(1)),multiply->y))
  io.scalar.result.ready:=scalarPending && !unknownScalar
  io.formatRequest.valid:=formatOffer.valid;io.formatRequest.bits.value:=value
  io.formatResult.ready:=formatPending && !unknownFormat
  val elements=job.tokens.pad(64)*job.rowWidth.pad(64)
  val expectedScalar=elements*Mux(job.op===GdnElementwiseOp.SigmoidMul.U,5.U,1.U)
  val expectedFormat=elements*Mux(job.op===GdnElementwiseOp.SigmoidMul.U,2.U,1.U)
  val expectedMemory=(elements>>5)*3.U
  when(state=/=idle && state=/=finish && state=/=report && state=/=locked){cycles:=cycles+1.U}
  when(io.job.fire){
    val j=io.job.bits;job:=j;remaining:=j.tokens*j.rowWidth;offset:=0.U;lane:=0.U
    sequence:=0.U;memoryAccepted:=0.U;scalarAccepted:=0.U;scalarReturned:=0.U
    formatAccepted:=0.U;formatReturned:=0.U;status:=Status.Ok.U;bytes:=0.U;cycles:=0.U
    val span=(j.tokens*j.rowWidth).pad(66)<<1
    def bad(base:UInt):Bool=base(5,0)=/=0.U || base.pad(66)+span>(BigInt(1)<<56).U
    def overlap(a:UInt,b:UInt):Bool=a.pad(66)<b.pad(66)+span && b.pad(66)<a.pad(66)+span
    val validShape=(j.op===GdnElementwiseOp.Add.U && (j.rowWidth===1024.U || j.rowWidth===2048.U)) ||
      (j.op===GdnElementwiseOp.SigmoidMul.U && (j.rowWidth===2048.U || j.rowWidth===4096.U))
    when(!validShape || j.tokens===0.U || j.tokens>128.U || j.tag==="hffffffff".U ||
      bad(j.a) || bad(j.b) || bad(j.output) || overlap(j.output,j.a) || overlap(j.output,j.b)){fail(Status.Bounds.U)}
      .otherwise{state:=readA}
  }
  when(io.memory.fire){
    memoryAccepted:=memoryAccepted+1.U;memoryPending:=true.B
    memoryWrite:=state===writeOutput;memoryReadB:=state===readB
    state:=Mux(state===readA,waitA,Mux(state===readB,waitB,waitOutput))
  }
  when(io.response.fire){
    memoryPending:=false.B
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    when(memoryWrite && !io.response.bits.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(io.response.bits.error){fail(Status.Memory.U)}
      .elsewhen(!poison && !currentFault){
        when(!memoryWrite){
          for(i<-0 until 32){
            when(memoryReadB){inputB(i):=io.response.bits.data((i+1)*16-1,i*16)}
              .otherwise{inputA(i):=io.response.bits.data((i+1)*16-1,i*16)}
          }
          when(memoryReadB){lane:=0.U;state:=checkLane}.otherwise{state:=readB}
        }.otherwise{
          when(remaining===32.U){state:=finish}
            .otherwise{remaining:=remaining-32.U;offset:=offset+64.U;state:=readA}
        }
      }
  }
  when(state===checkLane){
    when(!TensorMath.finite(x) || !TensorMath.finite(y)){fail(Status.Numerical.U)}
      .elsewhen(job.op===GdnElementwiseOp.SigmoidMul.U && x(31) && x(30,0)>=F32.lit(80)){fail(Status.Unsupported.U)}
      .otherwise{operation:=Mux(job.op===GdnElementwiseOp.Add.U,add,exp);state:=scalarIssue}
  }
  when(io.scalar.request.fire){scalarAccepted:=scalarAccepted+1.U;scalarPending:=true.B;state:=scalarWait}
  when(io.scalar.result.fire){
    val r=io.scalar.result.bits.value;scalarPending:=false.B;scalarReturned:=scalarReturned+1.U
    when(io.scalar.result.bits.error || !TensorMath.finite(r)){fail(Status.Numerical.U)}
      .elsewhen(!poison && !currentFault){
        value:=r;state:=scalarIssue
        switch(operation){
          is(exp){exponential:=r;operation:=denominator}
          is(denominator){operation:=inverse}
          is(inverse){operation:=sign}
          is(sign){state:=formatIssue}
          is(add){state:=formatIssue}
          is(multiply){state:=formatIssue}
        }
      }
  }
  when(io.formatRequest.fire){formatAccepted:=formatAccepted+1.U;formatPending:=true.B;state:=formatWait}
  when(io.formatResult.fire){
    val r=io.formatResult.bits;formatPending:=false.B;formatReturned:=formatReturned+1.U
    when(r.error || r.value(14,7)===255.U){fail(Status.Numerical.U)}
      .elsewhen(!poison && !currentFault){
        when(operation===sign){value:=Cat(r.value,0.U(16.W));operation:=multiply;state:=scalarIssue}
          .otherwise{
            output(lane):=r.value
            when(lane===31.U){state:=writeOutput}.otherwise{lane:=lane+1.U;state:=checkLane}
          }
      }
  }
  when(state===drain && !memoryPending && !scalarPending && !formatPending && !quarantine){state:=finish}
  val heldOffer=(io.published.memory && !io.memory.ready) ||
    (io.published.scalar && !io.scalar.request.ready) || (io.published.format && !io.formatRequest.ready)
  when(faultNow || poison || currentFault){
    poison:=true.B
    when(state===idle && !io.job.fire){state:=locked}
    when((state=/=idle || io.job.fire) && state=/=finish && state=/=report && state=/=locked){
      when(faultNow && status===Status.Ok.U){status:=faultCode}
      when(heldOffer){state:=state}.elsewhen(state=/=drain){state:=drain}
    }
  }
  when(state===finish && io.resourcesDrained){
    val exact=scalarAccepted===expectedScalar && scalarReturned===expectedScalar &&
      formatAccepted===expectedFormat && formatReturned===expectedFormat &&
      memoryAccepted===expectedMemory && sequence===expectedMemory && bytes===(elements<<1)
    val complete=status===Status.Ok.U && !poison && !faultNow && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag;terminal.status:=Mux(status===Status.Ok.U && !complete,Status.Protocol.U,status)
    terminal.writeBytes:=bytes;terminal.outputAckBytes:=bytes;terminal.cycles:=cycles
    terminal.outputCommitted:=complete;terminal.resourcesDrained:=io.resourcesDrained
    terminal.scalarAccepted:=scalarAccepted;terminal.scalarReturned:=scalarReturned
    terminal.formatAccepted:=formatAccepted;terminal.formatReturned:=formatReturned
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    when(status===Status.Ok.U && !complete){poison:=true.B}
    state:=report
  }
  when(io.done.fire){state:=Mux(terminal.status===Status.Ok.U && !io.resetRequired,idle,locked)}
}
