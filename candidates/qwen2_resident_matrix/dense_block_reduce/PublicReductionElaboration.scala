// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Full Dense request/result connected to the real shared owner and Vector loan.
  * Matrix and DDR remain the actual backend ports. Their accepted obligations
  * below retire only on the corresponding physical response/done handshake.
  * This is a frontend integration harness, not Host parser dispatch or RTL.
  * Coordinated reset includes these external backends; no local abort clears
  * an accepted obligation or establishes stale-response freshness.
  */
class PublicDenseReductionHarness extends Module {
  val io=IO(new Bundle {
    val dense=new DenseBlockReductionPort
    val prefixWorkspace=Input(new TransposedPrefixWorkspace(2560))
    val matrix=new MatrixStreamPort(enableTransposedDense=true,enableAccumulatorSeed=true)
    val burst=Decoupled(new BurstReadRequest)
    val burstResponse=Flipped(Decoupled(new BurstReadResponse))
    val writeRequest=Decoupled(new BurstWriteRequest)
    val writeData=Decoupled(new BurstWriteBeat)
    val writeResponse=Flipped(Decoupled(new MemoryResponse))
    val physicalSteps=Input(UInt(64.W))
    val backendReset=Input(Bool())
    val backendAbort=Output(Bool())
    val matrixDrained=Output(Bool());val dmaDrained=Output(Bool())
    val handoff=Output(Valid(new QwenOwnerJob))
  })
  val owner=Module(new TransposedDenseDownOwner(burstWrites=true,enableFfnTiles=true,
    enableFfnWindow=true,enableFfnDrain=true,numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
    enableKWindow=true,enableDenseDrain=true))
  val vector=Module(new VectorSiluOwner(enableTileLoan=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,enableBinaryAdd=true))
  val coordinator=Module(new DenseBlockReductionCoordinator)
  io.dense<>coordinator.io.dense
  coordinator.io.window<>owner.io.window.get
  coordinator.io.drain<>owner.io.drain.get
  coordinator.io.tiles<>owner.io.tiles.get
  coordinator.io.vector<>vector.io.loan.get
  io.matrix<>owner.io.matrix
  io.burst<>owner.io.burst;io.burstResponse<>owner.io.burstResponse
  io.writeRequest<>owner.io.writeRequest.get;io.writeData<>owner.io.writeData.get
  io.writeResponse<>owner.io.writeResponse.get
  owner.io.prefixWorkspace.get:=io.prefixWorkspace;owner.io.physicalSteps:=io.physicalSteps
  owner.io.job.valid:=false.B;owner.io.job.bits:=0.U.asTypeOf(new QwenOwnerJob)
  owner.io.done.ready:=true.B
  owner.io.memory.ready:=false.B;owner.io.response.valid:=false.B
  owner.io.response.bits:=0.U.asTypeOf(new MemoryResponse)
  vector.io.job.valid:=false.B;vector.io.job.bits:=0.U.asTypeOf(new QwenOwnerJob)
  vector.io.done.ready:=true.B;vector.io.memory.ready:=false.B
  vector.io.response.valid:=false.B;vector.io.response.bits:=0.U.asTypeOf(new MemoryResponse)

  // One controlled outstanding transaction per physical backend is the
  // existing owner/adapter contract. No payload is copied into these fences.
  val matrixOutstanding=RegInit(false.B)
  val readOutstanding=RegInit(false.B)
  val writeOutstanding=RegInit(false.B)
  when(io.matrix.group.fire){matrixOutstanding:=true.B}
  when(io.matrix.done.fire){matrixOutstanding:=false.B}
  when(io.burst.fire){readOutstanding:=true.B}
  when(io.burstResponse.fire){readOutstanding:=false.B}
  when(io.writeRequest.fire){writeOutstanding:=true.B}
  when(io.writeResponse.fire){writeOutstanding:=false.B}
  when(io.matrix.group.fire){assert(!matrixOutstanding,"second Matrix group before physical done")}
  when(io.matrix.done.fire){assert(matrixOutstanding,"Matrix done without accepted group")}
  when(io.burst.fire){assert(!readOutstanding && io.burst.bits.beats===1.U,"bounded owner read obligation")}
  when(io.burstResponse.fire){assert(readOutstanding,"DMA read response without accepted descriptor")}
  when(io.writeRequest.fire){assert(!writeOutstanding,"second write before physical ACK")}
  when(io.writeResponse.fire){assert(writeOutstanding,"write ACK without accepted descriptor")}
  io.matrixDrained:= !matrixOutstanding
  io.dmaDrained:= !readOutstanding && !writeOutstanding
  coordinator.io.matrixDrained:=io.matrixDrained
  coordinator.io.dmaDrained:=io.dmaDrained

  // Owner.resetRequired can reflect our current outgoing drain.abort. Cross a
  // register before returning it as a backend fault; external reset is separate.
  val backendFault=RegInit(false.B)
  when(owner.io.resetRequired || vector.io.resetRequired || io.backendReset){backendFault:=true.B}
  coordinator.io.backendReset:=io.backendReset || backendFault
  io.backendAbort:=coordinator.io.backendAbort
  io.matrix.abort:=owner.io.matrix.abort || coordinator.io.backendAbort
  io.handoff:=coordinator.io.handoff
}

object PublicReductionElaboration extends App {
  require(args.length==2)
  val out=Paths.get(args(0));require(out.isAbsolute);Files.createDirectories(out)
  val profile=args(1)
  val target=out.resolve(profile+".fir");require(!Files.exists(target))
  profile match {
    case "public_dense_reduction"=>Files.writeString(target,ChiselStage.emitCHIRRTL(new PublicDenseReductionHarness))
    case other=>throw new IllegalArgumentException("unknown public reduction target: "+other)
  }
  println("PASS public Dense coordinator/shared-owner CHIRRTL; no RTL or hardware execution")
}
