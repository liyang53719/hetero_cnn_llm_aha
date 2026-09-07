// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Test-only same-port probe INCLUDING the production arbitration overhead.
  * The shared hub and pinned-iDMA adapter are unchanged production modules.
  * Only client one supplies payload, so no extra workload is invented.
  * desiredName preserves the existing C++ test ABI without editing emitted SV.
  */
class SharedIdmaWeightBurstProbe extends Module {
  override def desiredName = "IdmaWeightBurstProbe"
  val dma = Module(new RetainedIdmaWeightBurstAdapter(16))
  val hub = Module(new SharedMemoryArbiter(2))
  val io = IO(chiselTypeOf(dma.io))
  dontTouch(io)
  hub.io.requests(0).valid := false.B
  hub.io.requests(0).bits := 0.U.asTypeOf(new MemoryRequest)
  hub.io.responses(0).ready := true.B
  hub.io.requests(1) <> io.request
  io.response <> hub.io.responses(1)
  dma.io.request <> hub.io.memory
  hub.io.response <> dma.io.response
  dma.io.window := io.window
  dma.io.flush := io.flush
  io.axi <> dma.io.axi
  io.resetRequired := dma.io.resetRequired || hub.io.resetRequired
  io.transfers := dma.io.transfers
  io.readBeats := dma.io.readBeats
  io.writeBeats := dma.io.writeBeats
  io.readBursts := dma.io.readBursts
  io.cacheHits := dma.io.cacheHits
}
object EmitSharedIdmaWeightBurstProbe extends App {
  require(args.length == 1)
  val out = Paths.get(args(0))
  require(!Files.exists(out),"preserve old output")
  Files.createDirectories(out)
  Files.writeString(out.resolve("IdmaWeightBurstProbe.sv"),
    ChiselStage.emitSystemVerilog(new SharedIdmaWeightBurstProbe,
      firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
}
