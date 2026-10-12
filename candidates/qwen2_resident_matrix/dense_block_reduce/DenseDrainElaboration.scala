// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Real shared-bank integration frontend, with explicit transaction inputs.
  * One Dense owner/bank allocation and one existing sixteen-lane Vector owner.
  * Matrix stays on the real service port; no Matrix array or second bank model.
  * This is a bounded wiring harness, not production Host/coordinator dispatch.
  */
class DenseKReductionHarness extends Module {
  val io=IO(new Bundle {
    val dense=new DenseOwnerIO(burstWrites=true,transposed=true,enableAccumulatorSeed=true,
      downChunks=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,enableKWindow=true)
    val sum=Flipped(Decoupled(new DenseTileSumInvocation));val abort=Input(Bool())
    val sumComplete=Output(Bool());val sumBusy=Output(Bool());val resetRequired=Output(Bool())
  })
  val dense=Module(new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,
    enableFfnWindow=true,enableFfnDrain=true,numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
    enableKWindow=true,enableDenseDrain=true))
  val vector=Module(new VectorSiluOwner(enableTileLoan=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,enableBinaryAdd=true))
  val bridge=Module(new DenseTileSumBridge)
  io.dense<>dense.io
  bridge.io.vector<>vector.io.loan.get
  vector.io.job.valid:=false.B;vector.io.job.bits:=0.U.asTypeOf(new QwenOwnerJob)
  vector.io.done.ready:=true.B;vector.io.memory.ready:=false.B
  vector.io.response.valid:=false.B;vector.io.response.bits:=0.U.asTypeOf(new MemoryResponse)

  val poison=RegInit(false.B)
  val route=bridge.io.busy
  val p=dense.io.tiles.get;val external=io.dense.tiles.get;val b=bridge.io.tiles
  val bad=io.abort || external.abort || poison || bridge.io.resetRequired ||
    dense.io.resetRequired || vector.io.resetRequired
  // Intent reserves the next idle bank edge; accepted Dense/window/drain
  // obligations and their completion channels keep running until retirement.
  val reserve=route || io.sum.valid || bad
  dense.io.job.valid:=io.dense.job.valid && !reserve
  io.dense.job.ready:=dense.io.job.ready && !reserve
  dense.io.window.get.request.valid:=io.dense.window.get.request.valid && !reserve
  io.dense.window.get.request.ready:=dense.io.window.get.request.ready && !reserve
  dense.io.drain.get.request.valid:=io.dense.drain.get.request.valid && !reserve
  io.dense.drain.get.request.ready:=dense.io.drain.get.request.ready && !reserve

  p.control.valid:=Mux(route,b.control.valid,external.control.valid && !reserve)
  p.control.bits:=Mux(route,b.control.bits,external.control.bits)
  b.control.ready:=route && p.control.ready;external.control.ready:= !reserve && p.control.ready
  p.write.valid:=Mux(route,b.write.valid,external.write.valid && !reserve)
  p.write.bits:=Mux(route,b.write.bits,external.write.bits)
  b.write.ready:=route && p.write.ready;external.write.ready:= !reserve && p.write.ready
  p.read.valid:=Mux(route,b.read.valid,external.read.valid && !reserve)
  p.read.bits:=Mux(route,b.read.bits,external.read.bits)
  b.read.ready:=route && p.read.ready;external.read.ready:= !reserve && p.read.ready
  p.response.ready:=Mux(route,b.response.ready,external.response.ready)
  b.response.valid:=route && p.response.valid;b.response.bits:=p.response.bits
  external.response.valid:= !route && p.response.valid;external.response.bits:=p.response.bits
  // Bank resetRequired is registered. Only registered outer poison feeds the
  // bridge abort; current arithmetic result.error must retire through ready.
  p.abort:=io.abort || external.abort || poison || (route && b.abort)
  b.busy:=p.busy;b.leased:=p.leased;b.drained:=p.drained;b.resetRequired:=p.resetRequired;b.state:=p.state
  bridge.io.abort:=io.abort || external.abort || poison
  val quiescent=dense.io.job.ready && !dense.io.window.get.busy && !dense.io.drain.get.busy &&
    p.drained && vector.io.loan.get.drained && !bad
  bridge.io.bankGranted:=route || quiescent
  bridge.io.start.valid:=io.sum.valid && quiescent
  bridge.io.start.bits:=io.sum.bits
  io.sum.ready:=bridge.io.start.ready && quiescent
  io.sumComplete:=bridge.io.complete && !bad
  io.sumBusy:=route;io.resetRequired:=bad
  when(bridge.io.resetRequired || dense.io.resetRequired || vector.io.resetRequired || io.abort || external.abort){poison:=true.B}
}

object DenseDrainElaboration extends App {
  require(args.length==2)
  val out=Paths.get(args(0));require(out.isAbsolute);Files.createDirectories(out)
  val profile=args(1)
  val official=Qwen2NumericPolicy.Qwen2OfficialBf16V2
  def emit(module: => RawModule):Unit={
    val target=out.resolve(profile+".fir");require(!Files.exists(target))
    Files.writeString(target,ChiselStage.emitCHIRRTL(module))
  }
  profile match {
    case "drain_parent"=>emit(new DenseDrainParent(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true))
    case "drain_disabled"=>emit(new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true))
    case "drain_enabled"=>emit(new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true,enableDenseDrain=true))
    case "drain_enabled_burst"=>emit(new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true,enableDenseDrain=true))
    case "combined_dense_sum"=>emit(new DenseKReductionHarness)
    case other=>throw new IllegalArgumentException("unknown bounded target: "+other)
  }
  println("PASS Dense drain CHIRRTL target: "+profile+"; no RTL or hardware execution")
}
