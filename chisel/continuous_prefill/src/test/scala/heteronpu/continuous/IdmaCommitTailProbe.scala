// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
class IdmaCommitTailProbe extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new BurstReadRequest));val result=Decoupled(new BurstReadResponse)
    val legacyRequest=Flipped(Decoupled(new MemoryRequest));val legacyResult=Decoupled(new MemoryResponse)
    val axi=new BlockAxiMaster;val resetRequired=Output(Bool())
    val transfers=Output(UInt(64.W));val completed=Output(UInt(64.W))
  })
  val d=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,commitTailRead=true))
  d.io.streamRequest.get<>io.request;io.result<>d.io.streamResponse.get
  d.io.request<>io.legacyRequest;io.legacyResult<>d.io.response
  d.io.window:=0.U.asTypeOf(new IdmaWeightWindow);d.io.flush:=false.B;io.axi<>d.io.axi
  io.transfers:=d.io.transfers;io.completed:=d.io.completedTransfers;io.resetRequired:=d.io.resetRequired
  dontTouch(io)
}
object EmitIdmaCommitTailProbe extends App {
  val p=Paths.get(args(0));require(p.isAbsolute && !Files.exists(p));Files.createDirectories(p)
  Files.writeString(p.resolve("IdmaCommitTailProbe.sv"),ChiselStage.emitSystemVerilog(new IdmaCommitTailProbe,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
