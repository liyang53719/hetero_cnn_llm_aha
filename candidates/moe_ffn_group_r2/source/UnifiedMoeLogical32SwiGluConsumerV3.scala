// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedMoeLogical32SwiGluInputV3 extends Bundle {
  val gate=UInt(512.W);val up=UInt(512.W)
}
class UnifiedMoeLogical32SwiGluResultV3 extends Bundle {
  val data=UInt(512.W);val status=UInt(8.W);val drained=Bool()
  val scalarIssued=UInt(9.W);val scalarReturned=UInt(9.W)
  val formatIssued=UInt(7.W);val formatReturned=UInt(7.W)
  val primitiveFlags=UInt(5.W);val primitiveFlagResponses=UInt(9.W)
}

/** Logical32 means one BF16 DDR beat, NOT32 physical arithmetic lanes.
  * Functional microsequencer only:192 shared Scalar requests and64 shared
  * format requests on success. It instantiates ZERO arithmetic resources.
  * The parent owns the sole shared services and retains complete owner identity
  * through actual requests/results; these raw ports are private, not host IO.
  *
  * Exact candidate node order per element:
  * e=P7(-abs(x)); d=RNE(1+e); r=RNE(1/d);
  * s=RNE((x<0?e:1)*r); z=RNE(x*s); b=BF16_RNE(z);
  * p=RNE(expand(b)*expand(up)); out=BF16_RNE(p).
  * No fused node or unmaterialized SiLU is substituted. This is NOT yet a
  * qualified Torch SiLU approximation or a32laneII1 performance implementation.
  * Unknown replies quarantine; held requests never withdraw on later fault.
  */
class UnifiedMoeLogical32SwiGluConsumerV3 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoeLogical32SwiGluInputV3))
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val externalPoison=Input(Bool())
    val result=Decoupled(new UnifiedMoeLogical32SwiGluResultV3)
    val resetRequired=Output(Bool());val quarantine=Output(Bool())
    val busy=Output(Bool());val lane=Output(UInt(5.W));val node=Output(UInt(3.W))
  })
  val idle::prepare::offer::waitScalar::prepareFormat::offerFormat::waitFormat::report::locked::Nil=Enum(9)
  val state=RegInit(idle);val input=Reg(new UnifiedMoeLogical32SwiGluInputV3)
  val lane=Reg(UInt(5.W));val phase=Reg(UInt(3.W));val firstFormat=Reg(Bool())
  val expValue=Reg(UInt(32.W));val denominator=Reg(UInt(32.W));val reciprocal=Reg(UInt(32.W))
  val sigmoid=Reg(UInt(32.W));val silu=Reg(UInt(32.W));val rawFormat=Reg(UInt(32.W))
  val values=Reg(Vec(32,UInt(16.W)));val req=Reg(new UnifiedScalarRequestV2)
  val out=Reg(new UnifiedMoeLogical32SwiGluResultV3)
  val poison=RegInit(false.B);val quarantined=RegInit(false.B)
  val unknown=(io.scalar.result.valid && state=/=waitScalar) || (io.formatResult.valid && state=/=waitFormat)
  when(unknown){poison:=true.B;quarantined:=true.B}
  when(io.externalPoison){poison:=true.B}
  val fault=poison||quarantined||unknown||io.externalPoison
  val x=Cat((input.gate>>(lane<<4))(15,0),0.U(16.W))
  val up=Cat((input.up>>(lane<<4))(15,0),0.U(16.W))
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
    poison:=true.B;state:=Mux(quarantined||unknown,locked,report)
  }
  when(io.begin.fire){
    input:=io.begin.bits;lane:=0.U;phase:=0.U
    out:=0.U.asTypeOf(new UnifiedMoeLogical32SwiGluResultV3)
    val finite=(0 until 32).map(i=>io.begin.bits.gate(i*16+14,i*16+7)=/="hff".U &&
      io.begin.bits.up(i*16+14,i*16+7)=/="hff".U).reduce(_&&_)
    when(finite){state:=prepare}.otherwise{finishError(Status.Numerical.U)}
  }
  when(state===prepare){
    when(fault){finishError(Status.Dependency.U)}.otherwise{
      req:=0.U.asTypeOf(new UnifiedScalarRequestV2)
      req.payload.op:=ScalarOp.MulIeeeRne.U
      switch(phase){
        is(0.U){req.policy:=UnifiedScalarPolicyV2.GradualDecay.U;req.payload.op:=ScalarOp.ExpNegative.U
          req.payload.a:=Cat(1.U(1.W),x(30,0))}
        is(1.U){req.payload.op:=ScalarOp.Add.U;req.payload.a:="h3f800000".U;req.payload.b:=expValue}
        is(2.U){req.payload.op:=ScalarOp.Div.U;req.payload.a:="h3f800000".U;req.payload.b:=denominator}
        is(3.U){req.payload.a:=Mux(x(31),expValue,"h3f800000".U);req.payload.b:=reciprocal}
        is(4.U){req.payload.a:=x;req.payload.b:=sigmoid}
        is(5.U){req.payload.a:=silu;req.payload.b:=up}
      }
      state:=offer
    }
  }
  when(io.scalar.request.fire){out.scalarIssued:=out.scalarIssued+1.U;state:=waitScalar}
  when(io.scalar.result.fire){
    val r=io.scalar.result.bits
    when(r.policy=/=req.policy){
      // A different policy echo is NOT evidence that this pending request
      // returned. Consume the bad packet, retain issued/returned imbalance,
      // and expose an invalid UNDRAINED Protocol result until isolation.
      // Do not attribute its primitive flags or data to the current owner.
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
        is(3.U){sigmoid:=r.value;phase:=4.U}
        is(4.U){rawFormat:=r.value;firstFormat:=true.B;state:=prepareFormat}
        is(5.U){rawFormat:=r.value;firstFormat:=false.B;state:=prepareFormat}
      }
      }
    }
  }
  when(state===prepareFormat){when(fault){finishError(Status.Dependency.U)}.otherwise{state:=offerFormat}}
  when(io.formatRequest.fire){out.formatIssued:=out.formatIssued+1.U;state:=waitFormat}
  when(io.formatResult.fire){
    out.formatReturned:=out.formatReturned+1.U
    val r=io.formatResult.bits;val bad=r.error || r.value(14,7)==="hff".U
    when(bad||fault){finishError(Mux(bad,Status.Numerical.U,Status.Dependency.U))}.otherwise{
      when(firstFormat){silu:=Cat(r.value,0.U(16.W));phase:=5.U;state:=prepare}
      .otherwise{
        values(lane):=r.value
        when(lane===31.U){
          // Current last value bypasses the register update only for packaging.
          out.data:=Cat(r.value,Cat((0 until 31).reverse.map(i=>values(i))))
          val exact=out.scalarIssued===192.U && out.scalarReturned===192.U &&
            out.formatIssued===64.U && out.formatReturned===63.U
          out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=true.B
          when(!exact){poison:=true.B};state:=report
        }.otherwise{lane:=lane+1.U;phase:=0.U;state:=prepare}
      }
    }
  }
  when(io.result.fire){state:=Mux(fault,locked,idle)}
  // Held result fields remain stable; a late fault is an independent sticky
  // sideband. Parent must gate NEW DDR/down admission with current poison.
  // Unknown service response never produces synthetic drain or numeric output.
}
