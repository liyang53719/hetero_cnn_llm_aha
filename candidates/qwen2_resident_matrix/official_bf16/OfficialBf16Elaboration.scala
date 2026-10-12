// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import heteronpu.p0.LocalSramConfig
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Actual production leaves/parser only. No full core/Matrix, RTL or simulation. */
object OfficialBf16Elaboration extends App {
  require(args.length==2)
  val out=Paths.get(args(0));require(out.isAbsolute)
  Files.createDirectories(out)
  val profile=args(1)
  def emit(module: => RawModule):Unit={
    val target=out.resolve(profile+".fir");require(!Files.exists(target))
    Files.writeString(target,ChiselStage.emitCHIRRTL(module))
  }
  val s=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
  val c=ChainConfig(tileElements=32,tensorSlots=4,programDepth=4)
  val ram=LocalSramConfig(addressBits=3,rowsPerBank=2)
  val legacy=Qwen2NumericPolicy.LegacyV0
  val official=Qwen2NumericPolicy.Qwen2OfficialBf16V2
  profile match {
    case "host_parent"=>emit(new HostBlockCommandsOfficialParent(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true,enableResidentFfn=true))
    case "host_default"=>emit(new HostBlockCommands(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true,enableResidentFfn=true))
    case "host_legacy"=>emit(new HostBlockCommands(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true,enableResidentFfn=true,numericPolicy=legacy))
    case "host_official"=>emit(new HostBlockCommands(s,eventSlots=32,maxCommands=21,bf16Weights=true,enableTransposedDown=true,enableResidentFfn=true,numericPolicy=official))
    case "silu_parent"=>emit(new SiluVectorUnitOfficialParent(1))
    case "silu_default"=>emit(new SiluVectorUnit(1))
    case "silu_legacy"=>emit(new SiluVectorUnit(1,numericPolicy=legacy))
    case "silu_official"=>emit(new SiluVectorUnit(1,numericPolicy=official))
    case "elementwise_parent"=>emit(new ElementwiseMemoryEngineOfficialParent(c,ram))
    case "elementwise_default"=>emit(new ElementwiseMemoryEngine(c,ram))
    case "elementwise_legacy"=>emit(new ElementwiseMemoryEngine(c,ram,numericPolicy=legacy))
    case "elementwise_official"=>emit(new ElementwiseMemoryEngine(c,ram,numericPolicy=official))
    case other=>throw new IllegalArgumentException("unknown bounded target: "+other)
  }
  println("PASS CHIRRTL frontend target: "+profile+"; no arithmetic execution")
}
