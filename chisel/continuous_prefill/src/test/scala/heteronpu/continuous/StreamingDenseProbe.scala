// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}
/** Test wrapper only: real production Dense feeder, eight arithmetic slices,
  * and exactly the same single pinned iDMA used by the Host production root.
  */
class StreamingDenseProbe(burstWrites:Boolean=false,commitTailRead:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val axi=new BlockAxiMaster;val resetRequired=Output(Bool())
    val physicalSteps=Output(UInt(64.W));val wideSteps=Output(UInt(64.W));val streamedBeats=Output(UInt(64.W))
  })
  val dense=Module(new StreamingDenseOwner(128,burstWrites=burstWrites));val matrix=Module(new MatrixPipelineService)
  val dma=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,burstWrites=burstWrites,commitTailRead=commitTailRead))
  dense.io.job<>io.job;io.done<>dense.io.done
  dense.io.matrix<>matrix.io.port;dense.io.physicalSteps:=matrix.io.acceptedSteps
  dma.io.request<>dense.io.memory;dense.io.response<>dma.io.response
  dma.io.streamRequest.get<>dense.io.burst;dense.io.burstResponse<>dma.io.streamResponse.get
  if(burstWrites){dma.io.streamWriteRequest.get<>dense.io.writeRequest.get;dma.io.streamWriteData.get<>dense.io.writeData.get;dense.io.writeResponse.get<>dma.io.streamWriteResponse.get}
  dma.io.window:=0.U.asTypeOf(new IdmaWeightWindow);dma.io.flush:=io.job.fire
  io.axi<>dma.io.axi;io.resetRequired:=dense.io.resetRequired||matrix.io.resetRequired||dma.io.resetRequired
  io.physicalSteps:=matrix.io.acceptedSteps;io.wideSteps:=matrix.io.wideSteps;io.streamedBeats:=dma.io.streamedBeats
  dontTouch(io)
}
class StreamingDenseCollection(burstWrites:Boolean=false,commitTailRead:Boolean=false) extends Module {
  val top=Module(new StreamingDenseProbe(burstWrites,commitTailRead));val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitStreamingDenseProbe extends App {
  val p=Paths.get(args(0));require(p.isAbsolute && !Files.exists(p));Files.createDirectories(p)
  Files.writeString(p.resolve("StreamingDenseProbe.sv"),ChiselStage.emitSystemVerilog(new StreamingDenseCollection(args.length>1 && args(1)=="1",args.length>2 && args(2)=="1"),firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
