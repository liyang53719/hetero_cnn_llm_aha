// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
/** Test-only public-port wrapper. Backend is the original pinned iDMA RTL. */
class IdmaWeightBurstProbe extends Module {
  val dut=Module(new RetainedIdmaWeightBurstAdapter(16))
  val io=IO(chiselTypeOf(dut.io));io<>dut.io;dontTouch(io)
}
object EmitIdmaWeightBurstProbe extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("IdmaWeightBurstProbe.sv"),ChiselStage.emitSystemVerilog(new IdmaWeightBurstProbe,firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
}
