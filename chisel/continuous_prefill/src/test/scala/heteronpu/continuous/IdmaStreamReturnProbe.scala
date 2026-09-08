// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
/** Test-only wrapper: exactly one real pinned iDMA, public request/AXI ports. */
class IdmaStreamReturnProbe(cutThrough:Boolean) extends Module {
  val dut=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,streamCutThrough=cutThrough))
  val io=IO(chiselTypeOf(dut.io));io<>dut.io;dontTouch(io)
}
object EmitIdmaStreamReturnProbe extends App {
  require(args.length==2 && Set("0","1").contains(args(1)))
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("IdmaStreamReturnProbe.sv"),
    ChiselStage.emitSystemVerilog(new IdmaStreamReturnProbe(args(1)=="1"),
      firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
