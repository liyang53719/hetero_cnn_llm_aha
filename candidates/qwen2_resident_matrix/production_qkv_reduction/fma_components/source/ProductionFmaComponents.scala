// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import chisel3.RawModule
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}
/** Only the four existing retained-lane arithmetic providers; no Host or job. */
object ProductionFmaComponents extends App {
  require(args.length==2,"fresh output directory and explicit pinned firtool required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  def emit(name:String,gen:()=>RawModule):Unit={
    println(s"FMA_COMPONENT_BEGIN $name")
    val text=ChiselStage.emitSystemVerilog(gen(),args=Array("--firtool-binary-path",args(1)),
      firtoolOpts=Array("--preserve-values=all","-disable-all-randomization"))
    val bytes=text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length
    println(s"FMA_COMPONENT_SIZE $name bytes=$bytes")
    require(bytes<=8*1024*1024,"component SV 8MiB cap")
    Files.writeString(out.resolve(name+".sv"),text)
    println(s"FMA_COMPONENT_WRITTEN $name")
  }
  emit("HeteroBF16FmaPre",()=>new HeteroBF16FmaPre)
  emit("HeteroBF16FmaMul",()=>new HeteroBF16FmaMul)
  emit("HeteroBF16FmaPost",()=>new HeteroBF16FmaPost)
  emit("HeteroBF16FmaRound",()=>new HeteroBF16FmaRound)
}
