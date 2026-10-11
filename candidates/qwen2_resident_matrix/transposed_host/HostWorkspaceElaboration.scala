// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Only the real Host command parser is elaborated. The actual complete
  * HostBlockTop and QwenOwnerKernel are Scala-typechecked but never elaborated.
  * No arithmetic proxy, RTL emission, simulator or EDA is part of this gate.
  */
object HostWorkspaceElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));Files.createDirectories(out)
  val ordinary=QwenBlockShape(retainedMatrix=true,matrixColumns=256,maxTokens=128)
  val native=QwenBlockShape.qwen35Qkv()
  for(qkv<-Seq(false,true)){
    val shape=if(qkv)native else ordinary
    val profile=if(qkv)"qkv"else"ordinary"
    def baseline()={
      val m=new HostBlockCommandsBaseline(shape,eventSlots=32,maxCommands=21,bf16Weights=true,bf16Qkv=qkv)
      require(m.io.launch.bits.getWidth==833,"frozen Host launch ABI")
      m
    }
    def candidate(enabled:Boolean)={
      val m=new HostBlockCommands(shape,eventSlots=32,maxCommands=21,bf16Weights=true,bf16Qkv=qkv,enableTransposedDown=enabled)
      require(m.io.launch.bits.getWidth==833,"Host launch ABI must remain 833 bits")
      require(m.io.prefixWorkspace.isDefined==enabled,"workspace is internal and default-off")
      if(enabled)require(m.io.prefixWorkspace.get.getWidth==173,"typed workspace width")
      m
    }
    Files.writeString(out.resolve(profile+"_baseline.fir"),ChiselStage.emitCHIRRTL(baseline()))
    Files.writeString(out.resolve(profile+"_disabled.fir"),ChiselStage.emitCHIRRTL(candidate(false)))
    Files.writeString(out.resolve(profile+"_enabled.fir"),ChiselStage.emitCHIRRTL(candidate(true)))
  }
  println("PASS: bounded actual HostBlockCommands CHIRRTL; full top typecheck only")
}
