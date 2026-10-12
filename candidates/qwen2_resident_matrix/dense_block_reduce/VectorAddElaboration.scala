// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Handshake-only consumer: independent bank fault/abort inputs stand in for
  * the bank-side control. This does not instantiate or prove a bank bridge.
  * Error replies retire directly; only registered poison feeds back to abort.
  */
class VectorAddHandshakeHarness extends Module {
  val io=IO(new Bundle {
    val request=Flipped(chisel3.util.Decoupled(new SiluVectorInput(16)))
    val write=chisel3.util.Decoupled(Vec(16,UInt(32.W)))
    val abort=Input(Bool());val bankFault=Input(Bool())
    val errorRetired=Output(Bool());val drained=Output(Bool());val resetRequired=Output(Bool())
  })
  val owner=Module(new VectorSiluOwner(enableTileLoan=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,enableBinaryAdd=true))
  val p=owner.io.loan.get
  val poison=RegInit(false.B)
  val cancel=io.abort || io.bankFault || poison || p.resetRequired
  val arithmeticError=p.result.valid && p.result.bits.error
  val bad=cancel || arithmeticError
  p.abort:=cancel
  p.request.valid:=io.request.valid && !cancel
  p.request.bits.gate:=io.request.bits.gate;p.request.bits.up:=io.request.bits.up
  p.request.bits.binaryAdd.get:=true.B
  io.request.ready:=p.request.ready && !cancel
  io.write.valid:=p.result.valid && !bad
  io.write.bits:=p.result.bits.value
  p.result.ready:=bad || io.write.ready
  io.errorRetired:=p.result.fire && p.result.bits.error
  io.drained:=p.drained;io.resetRequired:=poison || p.resetRequired
  when(cancel || io.errorRetired){poison:=true.B}
  owner.io.job.valid:=false.B;owner.io.job.bits:=0.U.asTypeOf(new QwenOwnerJob)
  owner.io.done.ready:=true.B;owner.io.memory.ready:=false.B
  owner.io.response.valid:=false.B;owner.io.response.bits:=0.U.asTypeOf(new MemoryResponse)
}

/** Bounded real sixteen-lane arithmetic leaves only; no bank, Dense or Host.
  * Compile with the officially composed sources plus vector_add.patch.
  * The before profiles use renamed, unchanged prepatch leaf definitions.
  */
object VectorAddElaboration extends App {
  require(args.length==2)
  val out=Paths.get(args(0));require(out.isAbsolute);Files.createDirectories(out)
  val profile=args(1)
  val legacy=Qwen2NumericPolicy.LegacyV0
  val official=Qwen2NumericPolicy.Qwen2OfficialBf16V2
  def emit(module: => RawModule):Unit={
    val target=out.resolve(profile+".fir");require(!Files.exists(target))
    Files.writeString(target,ChiselStage.emitCHIRRTL(module))
  }
  profile match {
    case "vector_before_legacy"=>emit(new SiluVectorUnitAddBaseline(16,numericPolicy=legacy))
    case "vector_before_official"=>emit(new SiluVectorUnitAddBaseline(16,numericPolicy=official))
    case "vector_default"=>emit(new SiluVectorUnit(16))
    case "vector_disabled_legacy"=>emit(new SiluVectorUnit(16,numericPolicy=legacy,enableBinaryAdd=false))
    case "vector_disabled_official"=>emit(new SiluVectorUnit(16,numericPolicy=official,enableBinaryAdd=false))
    case "vector_enabled_legacy"=>emit(new SiluVectorUnit(16,numericPolicy=legacy,enableBinaryAdd=true))
    case "vector_enabled_official"=>emit(new SiluVectorUnit(16,numericPolicy=official,enableBinaryAdd=true))
    case "owner_before"=>emit(new VectorSiluOwnerAddBaseline(enableTileLoan=true,numericPolicy=official))
    case "owner_disabled"=>emit(new VectorSiluOwner(enableTileLoan=true,numericPolicy=official))
    case "handshake"=>emit(new VectorAddHandshakeHarness)
    case "owner_enabled"=>emit(new VectorSiluOwner(enableTileLoan=true,numericPolicy=official,enableBinaryAdd=true))
    case other=>throw new IllegalArgumentException("unknown vector Add leaf: "+other)
  }
  println("PASS vector Add CHIRRTL leaf: "+profile+"; no arithmetic execution or Dense/bank integration")
}
