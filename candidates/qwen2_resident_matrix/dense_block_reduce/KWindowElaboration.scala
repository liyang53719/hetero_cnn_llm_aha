// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Actual owner/banks only. Matrix is the unchanged external service port.
  * No production coordinator, public Host hookup, RTL, synthesis or simulation.
  * DenseKWindowParent is an unmodified pre-patch owner renamed by the source
  * composition runner, with the same desiredName for exact default-off checks.
  */
object KWindowElaboration extends App {
  require(args.length==2)
  val out=Paths.get(args(0));require(out.isAbsolute)
  Files.createDirectories(out)
  val profile=args(1)
  def emit(module: => RawModule):Unit={
    val target=out.resolve(profile+".fir");require(!Files.exists(target))
    Files.writeString(target,ChiselStage.emitCHIRRTL(module))
  }
  val official=Qwen2NumericPolicy.Qwen2OfficialBf16V2
  profile match {
    case "parent_default"=>emit(new DenseKWindowParent(enableFfnTiles=true,enableFfnWindow=true))
    case "disabled_default"=>emit(new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnWindow=true))
    case "parent_official"=>emit(new DenseKWindowParent(enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official))
    case "disabled_official"=>emit(new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official))
    case "enabled_official"=>emit(new TransposedDenseDownOwner(enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true))
    case "enabled_burst"=>emit(new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,numericPolicy=official,enableKWindow=true))
    case other=>throw new IllegalArgumentException("unknown bounded target: "+other)
  }
  println("PASS CHIRRTL frontend: "+profile+"; actual owner/banks, no RTL execution")
}
