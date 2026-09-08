// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
/** Transport probe: the production adapter and the original pinned backend. */
class IdmaBurstWriteProbe extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new BurstWriteRequest))
    val data=Flipped(Decoupled(new BurstWriteBeat))
    val response=Decoupled(new MemoryResponse)
    val legacyRequest=Flipped(Decoupled(new MemoryRequest))
    val legacyResponse=Decoupled(new MemoryResponse)
    val axi=new BlockAxiMaster
    val resetRequired=Output(Bool());val transfers=Output(UInt(64.W))
  })
  val dma=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,burstWrites=true))
  dma.io.streamWriteRequest.get<>io.request;dma.io.streamWriteData.get<>io.data
  io.response<>dma.io.streamWriteResponse.get
  dma.io.request<>io.legacyRequest;io.legacyResponse<>dma.io.response
  dma.io.streamRequest.get.valid:=false.B;dma.io.streamRequest.get.bits:=0.U.asTypeOf(new BurstReadRequest)
  dma.io.streamResponse.get.ready:=true.B
  dma.io.window:=0.U.asTypeOf(new IdmaWeightWindow);dma.io.flush:=false.B
  io.axi<>dma.io.axi;io.resetRequired:=dma.io.resetRequired;io.transfers:=dma.io.transfers
  dontTouch(io)
}
object EmitIdmaBurstWriteProbe extends App {
  val p=Paths.get(args(0));require(p.isAbsolute && !Files.exists(p));Files.createDirectories(p)
  Files.writeString(p.resolve("IdmaBurstWriteProbe.sv"),ChiselStage.emitSystemVerilog(new IdmaBurstWriteProbe,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
