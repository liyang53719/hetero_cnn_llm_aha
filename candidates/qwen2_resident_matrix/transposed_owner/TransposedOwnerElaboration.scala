// SPDX-License-Identifier: Apache-2.0
// Frontend composition of real owners and the real patched service. The eight
// retained endpoints keep their exact existing BlackBox ABI; no FPU model.
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class DenseOwnerSelectionHarness(enabled:Boolean,burstWrites:Boolean) extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
    val writeRequest=if(burstWrites)Some(Decoupled(new BurstWriteRequest))else None
    val writeData=if(burstWrites)Some(Decoupled(new BurstWriteBeat))else None
    val writeResponse=if(burstWrites)Some(Flipped(Decoupled(new MemoryResponse)))else None
    val resetRequired=Output(Bool());val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
  })
  // The same typed elaboration selection used by owner_selection.patch.
  val dense:DenseOwnerIO=if(enabled)Module(new TransposedDenseOwner(burstWrites)).io
    else Module(new StreamingDenseOwner(8960,burstWrites=burstWrites)).io
  val matrix=Module(new MatrixPipelineService(enableTransposedDense=enabled))
  dense.job<>io.job;io.done<>dense.done;io.memory<>dense.memory;dense.response<>io.response
  io.burst<>dense.burst;dense.burstResponse<>io.burstResponse
  if(burstWrites){io.writeRequest.get<>dense.writeRequest.get;io.writeData.get<>dense.writeData.get;dense.writeResponse.get<>io.writeResponse.get}
  matrix.io.port.group<>dense.matrix.group
  matrix.io.port.step<>dense.matrix.step
  dense.matrix.result<>matrix.io.port.result;dense.matrix.done<>matrix.io.port.done
  matrix.io.port.abort:=dense.matrix.abort;dense.physicalSteps:=matrix.io.acceptedSteps
  io.resetRequired:=dense.resetRequired || matrix.io.resetRequired
  io.pipelineIssues:=matrix.io.wideSteps;io.pipelineStalls:=matrix.io.stallCycles
}

/** Expose just the original anonymous IO shape to prove the shared type adds
  * no fields when disabled. OriginalDenseIO is extracted from frozen source.
  */
class DenseOwnerIOShapeCheck(burstWrites:Boolean) extends Module {
  val io=IO(Input(new Bundle {
    val original=new OriginalDenseIO(burstWrites)
    val shared=new DenseOwnerIO(burstWrites)
  }))
  require(io.original.elements.keySet==io.shared.elements.keySet)
  for(name<-io.original.elements.keys){
    require(io.original.elements(name).getWidth==io.shared.elements(name).getWidth,name)
  }
  require(io.original.getWidth==io.shared.getWidth)
  require(io.shared.matrix.group.bits.transposedDense.isEmpty)
}

object TransposedOwnerElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  def emit(name:String,module: => RawModule):Unit=
    Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  for(burst<-Seq(false,true)){
    val mode=if(burst)"burst"else"single"
    emit("io_shape_"+mode,new DenseOwnerIOShapeCheck(burst))
    emit("original_dense_"+mode,new OriginalStreamingDenseOwner(8960,burstWrites=burst))
    emit("shared_io_dense_"+mode,new StreamingDenseOwner(8960,burstWrites=burst))
    emit("owner_normal_"+mode,new DenseOwnerSelectionHarness(false,burst))
    emit("owner_transposed_"+mode,new DenseOwnerSelectionHarness(true,burst))
  }
  emit("can_start_disabled",new ActualKernelCanStartProbe(false))
  emit("can_start_enabled",new ActualKernelCanStartProbe(true))
  println("PASS: actual owner + banks + eight-endpoint service frontend; no RTL or arithmetic executed")
}
