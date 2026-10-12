// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Reuse all previous bounded frontend profiles, then compare the exact
  * window-on/drain-off owner and elaborate only the actual drain owner.
  * No full Host/kernel elaboration, RTL or arithmetic execution.
  */
object DrainElaboration extends App {
  require(args.length==1)
  FfnWindowElaboration.main(args)
  val out=Paths.get(args(0))
  def emit(name:String,module: => RawModule):Unit=Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  emit("owner_window_baseline",new TransposedDenseDownOwnerWindowBaseline(enableFfnTiles=true,enableFfnWindow=true))
  emit("owner_drain",new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true))
  emit("owner_window_burst_baseline",new TransposedDenseDownOwnerWindowBaseline(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true))
  emit("owner_window_burst_disabled",new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true))
  emit("owner_drain_burst",new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true))
  emit("owner_drain_only",new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnDrain=true))
  println("PASS: independent typed act drain source/frontend only; no RTL execution")
}
