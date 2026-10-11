// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Actual composed owners, fixed SRAMs and retained service. No FPU stand-in:
  * exact retained BlackBoxes remain external for this source/frontend gate.
  */
class TransposedDownHarness(burstWrites:Boolean) extends Module {
  val io=IO(new DenseOwnerIO(burstWrites,transposed=true,enableAccumulatorSeed=true,downChunks=true))
  val dense:DenseOwnerIO=Module(new TransposedDenseDownOwner(burstWrites)).io
  val matrix=Module(new MatrixPipelineService(enableTransposedDense=true,enableAccumulatorSeed=true))
  dense.job<>io.job;io.done<>dense.done;io.memory<>dense.memory;dense.response<>io.response
  io.burst<>dense.burst;dense.burstResponse<>io.burstResponse
  if(burstWrites){io.writeRequest.get<>dense.writeRequest.get;io.writeData.get<>dense.writeData.get;dense.writeResponse.get<>io.writeResponse.get}
  dense.prefixWorkspace.get:=io.prefixWorkspace.get;matrix.io.port.seed.get<>dense.matrix.seed.get
  matrix.io.port.group<>dense.matrix.group;matrix.io.port.step<>dense.matrix.step
  dense.matrix.result<>matrix.io.port.result;dense.matrix.done<>matrix.io.port.done
  matrix.io.port.abort:=dense.matrix.abort;dense.physicalSteps:=matrix.io.acceptedSteps
  io.resetRequired:=dense.resetRequired||matrix.io.resetRequired
  io.issueCycles:=dense.issueCycles;io.operandStalls:=dense.operandStalls;io.profile:=dense.profile
  // DenseOwnerIO is used only as a public shape; the actual matrix is internal.
  io.matrix.group.valid:=false.B;io.matrix.group.bits:=0.U.asTypeOf(io.matrix.group.bits)
  io.matrix.step.valid:=false.B;io.matrix.step.bits:=0.U.asTypeOf(io.matrix.step.bits)
  io.matrix.result.ready:=false.B;io.matrix.done.ready:=false.B;io.matrix.abort:=false.B
  locally {
    io.matrix.seed.get.begin.valid:=false.B;io.matrix.seed.get.begin.bits:=0.U.asTypeOf(new MatrixAccumulatorSeedRequest)
    io.matrix.seed.get.beat.valid:=false.B;io.matrix.seed.get.beat.bits:=0.U.asTypeOf(new MatrixAccumulatorSeedBeat)
    io.matrix.seed.get.ack.ready:=false.B
  }
}

object DownOwnerElaboration extends App {
  require(args.length==1)
  SeedOwnerElaboration.main(args)
  val out=Paths.get(args(0))
  for(burst<-Seq(false,true)){
    val name="down_owner_enabled_"+(if(burst)"burst"else"single")
    Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(new TransposedDownHarness(burst)))
  }
  println("PASS: selected chunk-major Down owner frontend only; no RTL execution")
}
