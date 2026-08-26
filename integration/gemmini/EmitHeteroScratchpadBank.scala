package gemmini

import chisel3._
import chisel3.util.Decoupled
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

class HeteroTypedExtMemIO extends Bundle {
  val read_req = Decoupled(UInt(12.W))
  val read_resp = Flipped(Decoupled(UInt(128.W)))
  val write_req = Decoupled(new Bundle {
    val addr = UInt(12.W)
    val data = UInt(128.W)
    val mask = UInt(16.W)
  })
}

class HeteroScratchpadBankHarness extends Module {
  val io = IO(new Bundle {
    val read = Flipped(new ScratchpadReadIO(4096, 128))
    val write = Flipped(new ScratchpadWriteIO(4096, 128, 16))
    val ext_mem = new HeteroTypedExtMemIO
  })

  val bank = Module(new ScratchpadBank(
    n = 4096,
    w = 128,
    aligned_to = 1,
    single_ported = false,
    use_shared_ext_mem = true,
    is_dummy = false
  ))
  bank.io.read <> io.read
  bank.io.write <> io.write

  val ext = bank.io.ext_mem.get
  io.ext_mem.read_req.valid := ext.read_req.valid
  io.ext_mem.read_req.bits := ext.read_req.bits
  ext.read_req.ready := io.ext_mem.read_req.ready
  ext.read_resp.valid := io.ext_mem.read_resp.valid
  ext.read_resp.bits := io.ext_mem.read_resp.bits
  io.ext_mem.read_resp.ready := ext.read_resp.ready
  io.ext_mem.write_req.valid := ext.write_req.valid
  io.ext_mem.write_req.bits.addr := ext.write_req.bits.addr
  io.ext_mem.write_req.bits.data := ext.write_req.bits.data
  io.ext_mem.write_req.bits.mask := ext.write_req.bits.mask
  ext.write_req.ready := io.ext_mem.write_req.ready
}

/** Emits the exact pinned-Gemmini scratchpad-bank endpoint used by the L3
  * production adapter.  This deliberately avoids elaborating Rocket/Chipyard.
  */
object EmitHeteroScratchpadBank extends App {
  require(args.length == 1, "expected one output SystemVerilog path")
  val output = Paths.get(args(0))
  val systemVerilog = ChiselStage.emitSystemVerilog(
    new HeteroScratchpadBankHarness
  )
  Files.createDirectories(output.getParent)
  Files.writeString(output, systemVerilog, StandardCharsets.UTF_8)
}
