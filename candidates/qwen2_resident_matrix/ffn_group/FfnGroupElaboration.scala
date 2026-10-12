// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Bounded frontend only: no Matrix/datapath root, RTL or arithmetic run. */
object FfnGroupElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  def emit(name:String,module: => RawModule):Unit=Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  emit("bridge_baseline",new FfnTileSiluBridgeBaseline)
  emit("bridge_disabled",new FfnTileSiluBridge)
  emit("coordinator",new FfnResidentCoordinator)
  val s=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
  emit("host_baseline",new HostBlockCommandsGroupBaseline(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true))
  emit("host_disabled",new HostBlockCommands(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true))
  emit("host_enabled",new HostBlockCommands(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true,enableResidentFfn=true))
  println("PASS: production coordinator and real Host parser frontend only; no full kernel/Host top, RTL, simulation or numerical acceptance")
}
