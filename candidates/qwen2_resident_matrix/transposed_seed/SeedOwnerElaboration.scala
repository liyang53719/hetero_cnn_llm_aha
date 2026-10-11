// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Actual composed owners, fixed SRAMs and retained service. No FPU stand-in:
  * exact retained BlackBoxes remain external for this source/frontend gate.
  */
class TransposedSeedHarness(seedEnabled:Boolean,burstWrites:Boolean) extends Module {
  val io=IO(new DenseOwnerIO(burstWrites,transposed=true,enableAccumulatorSeed=seedEnabled))
  val dense:DenseOwnerIO=if(seedEnabled)Module(new TransposedDenseSeedOwner(burstWrites)).io
    else Module(new TransposedDenseOwner(burstWrites)).io
  val matrix=Module(new MatrixPipelineService(enableTransposedDense=true,enableAccumulatorSeed=seedEnabled))
  dense.job<>io.job;io.done<>dense.done;io.memory<>dense.memory;dense.response<>io.response
  io.burst<>dense.burst;dense.burstResponse<>io.burstResponse
  if(burstWrites){io.writeRequest.get<>dense.writeRequest.get;io.writeData.get<>dense.writeData.get;dense.writeResponse.get<>io.writeResponse.get}
  if(seedEnabled){dense.prefixWorkspace.get:=io.prefixWorkspace.get;matrix.io.port.seed.get<>dense.matrix.seed.get}
  matrix.io.port.group<>dense.matrix.group;matrix.io.port.step<>dense.matrix.step
  dense.matrix.result<>matrix.io.port.result;dense.matrix.done<>matrix.io.port.done
  matrix.io.port.abort:=dense.matrix.abort;dense.physicalSteps:=matrix.io.acceptedSteps
  io.resetRequired:=dense.resetRequired||matrix.io.resetRequired
  io.issueCycles:=dense.issueCycles;io.operandStalls:=dense.operandStalls;io.profile:=dense.profile
  // DenseOwnerIO is used only as a public shape; the actual matrix is internal.
  io.matrix.group.valid:=false.B;io.matrix.group.bits:=0.U.asTypeOf(io.matrix.group.bits)
  io.matrix.step.valid:=false.B;io.matrix.step.bits:=0.U.asTypeOf(io.matrix.step.bits)
  io.matrix.result.ready:=false.B;io.matrix.done.ready:=false.B;io.matrix.abort:=false.B
  if(seedEnabled){
    io.matrix.seed.get.begin.valid:=false.B;io.matrix.seed.get.begin.bits:=0.U.asTypeOf(new MatrixAccumulatorSeedRequest)
    io.matrix.seed.get.beat.valid:=false.B;io.matrix.seed.get.beat.bits:=0.U.asTypeOf(new MatrixAccumulatorSeedBeat)
    io.matrix.seed.get.ack.ready:=false.B
  }
}

object SeedOwnerElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  def emit(name:String,module: => RawModule):Unit=Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  for(burst<-Seq(false,true);seed<-Seq(false,true)){
    emit("seed_owner_"+(if(seed)"enabled_"else"disabled_")+(if(burst)"burst"else"single"),new TransposedSeedHarness(seed,burst))
  }
  for(transposed<-Seq(false,true))emit("service_disabled_"+transposed,new MatrixPipelineService(enableTransposedDense=transposed))
  emit("service_seed_enabled",new MatrixPipelineService(enableTransposedDense=true,enableAccumulatorSeed=true))
  println("PASS: actual seed owner/banks/service CHIRRTL only; no retained RTL execution")
}
