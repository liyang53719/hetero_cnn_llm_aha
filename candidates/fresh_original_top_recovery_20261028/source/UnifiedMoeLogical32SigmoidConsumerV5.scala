// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE packed input assembled only from actual N1 Dense DDR readbacks.
  * logical32 is at most32 tokens, NOT physical32 arithmetic lanes. */
class UnifiedMoeLogical32SigmoidInputV5 extends Bundle {
  val data=UInt(512.W);val activeLanes=UInt(6.W)
}
class UnifiedMoeLogical32SigmoidResultV5 extends Bundle {
  val data=UInt(512.W);val activeLanes=UInt(6.W);val status=UInt(8.W);val drained=Bool()
  val scalarIssued=UInt(9.W);val scalarReturned=UInt(9.W)
  val formatIssued=UInt(7.W);val formatReturned=UInt(7.W)
  val primitiveFlags=UInt(5.W);val primitiveFlagResponses=UInt(9.W)
}

/** Functional shared-sigmoid candidate, ZERO Scalar/ALU/formatter instances.
  * The first four nodes match the existing shared SiLU candidate exactly:
  * e=P7(-abs(x)); d=FP32_RNE(1+e); r=FP32_RNE(1/d);
  * s=FP32_RNE((signbit(x)?e:1)*r); result=BF16_RNE(s).
  * Do NOT rewrite the negative branch to one Div(e,d), fuse nodes, or assume
  * this recipe equals Torch's Sigmoid. Actual numerical qualification remains
  * separate. No physical32-II1 throughput claim follows from the logical tile.
  * Per active token:4 shared Scalar accepts +1 shared format accept. The parent
  * retains full phase/allocation/owner/epoch/V3-serial attribution for both raw
  * services. Policy echo alone is NOT full ownership; mismatch never retires
  * the current scalar obligation. Services return no earlier than next cycle.
  * P7/Div primitiveFlagsValid=false does not expose all internal node flags.
  */
class UnifiedMoeLogical32SigmoidConsumerV5 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoeLogical32SigmoidInputV5))
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val externalPoison=Input(Bool())
    val result=Decoupled(new UnifiedMoeLogical32SigmoidResultV5)
    val resetRequired=Output(Bool());val quarantine=Output(Bool())
    val busy=Output(Bool());val lane=Output(UInt(5.W));val node=Output(UInt(2.W))
  })
  val idle::prepare::offer::waitScalar::prepareFormat::offerFormat::waitFormat::report::locked::Nil=Enum(9)
  val state=RegInit(idle);val input=Reg(new UnifiedMoeLogical32SigmoidInputV5)
  val lane=Reg(UInt(5.W));val phase=Reg(UInt(2.W))
  val expValue=Reg(UInt(32.W));val denominator=Reg(UInt(32.W));val reciprocal=Reg(UInt(32.W))
  val rawFormat=Reg(UInt(32.W));val values=Reg(Vec(32,UInt(16.W)))
  val req=Reg(new UnifiedScalarRequestV2);val out=Reg(new UnifiedMoeLogical32SigmoidResultV5)
  val poison=RegInit(false.B);val quarantined=RegInit(false.B)
  val unknown=(io.scalar.result.valid && state=/=waitScalar) || (io.formatResult.valid && state=/=waitFormat)
  when(unknown){poison:=true.B;quarantined:=true.B}
  when(io.externalPoison){poison:=true.B}
  val fault=poison||quarantined||unknown||io.externalPoison
  val x=Cat((input.data>>(lane<<4))(15,0),0.U(16.W))
  // Unconditional combinational packaging; inactive lanes were cleared at begin.
  val completedData=Cat((0 until 32).reverse.map(i=>Mux(lane===i.U,io.formatResult.bits.value,values(i))))
  io.begin.ready:=state===idle && !fault
  io.scalar.request.valid:=state===offer;io.scalar.request.bits:=req
  io.scalar.result.ready:=state===waitScalar && !quarantined
  io.formatRequest.valid:=state===offerFormat;io.formatRequest.bits.value:=rawFormat
  io.formatResult.ready:=state===waitFormat && !quarantined
  io.result.valid:=state===report;io.result.bits:=out
  io.resetRequired:=fault;io.quarantine:=quarantined||unknown
  io.busy:=state=/=idle;io.lane:=lane;io.node:=phase
  def finishError(status:UInt):Unit={
    out.status:=status;out.data:=0.U;out.drained:= !quarantined && !unknown
    poison:=true.B;state:=report
  }
  when(io.begin.fire){
    input:=io.begin.bits;lane:=0.U;phase:=0.U;values.foreach(_:=0.U)
    out:=0.U.asTypeOf(new UnifiedMoeLogical32SigmoidResultV5);out.activeLanes:=io.begin.bits.activeLanes
    val bounded=io.begin.bits.activeLanes>=1.U && io.begin.bits.activeLanes<=32.U
    val finite=(0 until 32).map(i=>i.U>=io.begin.bits.activeLanes ||
      io.begin.bits.data(i*16+14,i*16+7)=/="hff".U).reduce(_&&_)
    when(!bounded){finishError(Status.Bounds.U)}
    .elsewhen(!finite){finishError(Status.Numerical.U)}.otherwise{state:=prepare}
  }
  when(state===prepare){
    when(fault){finishError(Status.Dependency.U)}.otherwise{
      req:=0.U.asTypeOf(new UnifiedScalarRequestV2);req.payload.op:=ScalarOp.MulIeeeRne.U
      switch(phase){
        is(0.U){req.policy:=UnifiedScalarPolicyV2.GradualDecay.U;req.payload.op:=ScalarOp.ExpNegative.U
          req.payload.a:=Cat(1.U(1.W),x(30,0))}
        is(1.U){req.payload.op:=ScalarOp.Add.U;req.payload.a:="h3f800000".U;req.payload.b:=expValue}
        is(2.U){req.payload.op:=ScalarOp.Div.U;req.payload.a:="h3f800000".U;req.payload.b:=denominator}
        is(3.U){req.payload.a:=Mux(x(31),expValue,"h3f800000".U);req.payload.b:=reciprocal}
      }
      state:=offer
    }
  }
  when(io.scalar.request.fire){out.scalarIssued:=out.scalarIssued+1.U;state:=waitScalar}
  when(io.scalar.result.fire){
    val r=io.scalar.result.bits
    when(r.policy=/=req.policy){
      poison:=true.B;quarantined:=true.B
      out.status:=Status.Protocol.U;out.data:=0.U;out.drained:=false.B;state:=report
    }.otherwise{
      out.scalarReturned:=out.scalarReturned+1.U
      when(r.primitiveFlagsValid){out.primitiveFlags:=out.primitiveFlags|r.flags
        out.primitiveFlagResponses:=out.primitiveFlagResponses+1.U}
      val bad=r.error || !TensorMath.finite(r.value)
      when(bad||fault){finishError(Mux(bad,Status.Numerical.U,Status.Dependency.U))}.otherwise{
        state:=prepare
        switch(phase){
          is(0.U){expValue:=r.value;phase:=1.U}
          is(1.U){denominator:=r.value;phase:=2.U}
          is(2.U){reciprocal:=r.value;phase:=3.U}
          is(3.U){rawFormat:=r.value;state:=prepareFormat}
        }
      }
    }
  }
  when(state===prepareFormat){when(fault){finishError(Status.Dependency.U)}.otherwise{state:=offerFormat}}
  when(io.formatRequest.fire){out.formatIssued:=out.formatIssued+1.U;state:=waitFormat}
  when(io.formatResult.fire){
    out.formatReturned:=out.formatReturned+1.U
    val r=io.formatResult.bits;val bad=r.error || r.value(14,7)==="hff".U || r.value(15) || r.value>"h3f80".U
    when(bad||fault){finishError(Mux(bad,Status.Numerical.U,Status.Dependency.U))}.otherwise{
      values(lane):=r.value
      when(lane.pad(6)+1.U===input.activeLanes){
        val expected=input.activeLanes.pad(9)<<2
        val exact=out.scalarIssued===expected && out.scalarReturned===expected &&
          out.formatIssued===input.activeLanes && out.formatReturned+1.U===input.activeLanes
        out.data:=Mux(exact,completedData,0.U)
        out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=true.B
        when(!exact){poison:=true.B};state:=report
      }.otherwise{lane:=lane+1.U;phase:=0.U;state:=prepare}
    }
  }
  when(io.result.fire){state:=Mux(fault,locked,idle)}
  // Held physical request/result payloads never retract or mutate due to late
  // fault. Unknown pending service debt needs external isolation; observable
  // undrained error is not lease release, output authorization, or block done.
}
