// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chisel3.util.experimental.BoringUtils

/** B ONLY, UNCOMPILED. Real Router/Coordinator/SumBridge/selected DownOwner/banks.
  * Matrix service, vector arithmetic and DDR are EXTERNAL protocol responders.
  * No MatrixPipelineService/4096 MAC instantiation and no numerical qualification.
  */
class Public21DownOwnerProtocolHarness extends Module {
  val router=Module(new Public21QkvReductionRouter)
  val owner=Module(new TransposedDenseDownOwner(burstWrites=true,
    enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
    enableKWindow=true,enableDenseDrain=true))
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
    val writeRequest=Decoupled(new BurstWriteRequest);val writeData=Decoupled(new BurstWriteBeat)
    val writeResponse=Flipped(Decoupled(new MemoryResponse))
    val matrix=new MatrixStreamPort(enableTransposedDense=true,enableAccumulatorSeed=true)
    val vector=Flipped(new FfnSiluLoanPort(enableBinaryAdd=true))
    val prefixWorkspace=Input(new TransposedPrefixWorkspace(2560))
    val backendReset=Input(Bool());val abort=Input(Bool())
    val resetRequired=Output(Bool());val reductionOwns=Output(Bool())
    val windowAccepted=Output(Valid(new FfnWindowRequest(enableKWindow=true)))
    val windowReturned=Output(Valid(new FfnWindowResult(enableCounters=true,enableKWindow=true)))
    val drainReturned=Output(Valid(new FfnDrainResult))
    val tileState=Output(Vec(3,new FfnTileState(enableMatrixProducerOrder=true)))
    val tileWrite=Output(Valid(new FfnTileBeat))
    val tileDrained=Output(Bool())
  })
  router.io.job<>io.job;io.done<>router.io.done
  // This test submits only public21Reduction=true; ordinary routing stays real.
  owner.io.job<>router.io.ordinaryJob;router.io.ordinaryDone<>owner.io.done
  owner.io.window.get<>router.io.window;owner.io.drain.get<>router.io.drain
  owner.io.tiles.get<>router.io.tiles;io.vector<>router.io.vector
  io.memory<>owner.io.memory;owner.io.response<>io.response
  io.burst<>owner.io.burst;owner.io.burstResponse<>io.burstResponse
  io.writeRequest<>owner.io.writeRequest.get;io.writeData<>owner.io.writeData.get
  owner.io.writeResponse.get<>io.writeResponse
  io.matrix<>owner.io.matrix
  io.matrix.abort:=owner.io.matrix.abort || router.io.backendAbort
  owner.io.prefixWorkspace.get:=io.prefixWorkspace
  router.io.backendReset:=io.backendReset;router.io.residentHost.abort:=io.abort
  router.io.residentHost.request.valid:=false.B;router.io.residentHost.request.bits:=0.U.asTypeOf(router.io.residentHost.request.bits)
  router.io.residentHost.result.ready:=false.B
  router.io.resident.request.ready:=false.B;router.io.resident.result.valid:=false.B
  router.io.resident.result.bits:=0.U.asTypeOf(router.io.resident.result.bits)
  router.io.resident.busy:=false.B;router.io.resident.resetRequired:=false.B
  router.io.residentHandoff.valid:=false.B;router.io.residentHandoff.bits:=0.U.asTypeOf(new QwenOwnerJob)
  router.io.residentWindow.request.valid:=false.B;router.io.residentWindow.request.bits:=0.U.asTypeOf(router.io.residentWindow.request.bits)
  router.io.residentWindow.result.ready:=false.B;router.io.residentWindow.invalidateLease:=false.B
  router.io.residentDrain.request.valid:=false.B;router.io.residentDrain.request.bits:=0.U.asTypeOf(router.io.residentDrain.request.bits)
  router.io.residentDrain.result.ready:=false.B;router.io.residentDrain.abort:=false.B
  router.io.residentTiles.control.valid:=false.B;router.io.residentTiles.control.bits:=0.U.asTypeOf(router.io.residentTiles.control.bits)
  router.io.residentTiles.read.valid:=false.B;router.io.residentTiles.read.bits:=0.U.asTypeOf(router.io.residentTiles.read.bits)
  router.io.residentTiles.write.valid:=false.B;router.io.residentTiles.write.bits:=0.U.asTypeOf(router.io.residentTiles.write.bits)
  router.io.residentTiles.response.ready:=false.B;router.io.residentTiles.abort:=false.B
  router.io.residentVector.request.valid:=false.B;router.io.residentVector.request.bits:=0.U.asTypeOf(router.io.residentVector.request.bits)
  router.io.residentVector.result.ready:=false.B;router.io.residentVector.abort:=false.B
  // Same event-derived fences as original OwnerProtocol, not constant grants.
  val matrixDebt=RegInit(false.B);val seedDebt=RegInit(false.B)
  val readDebt=RegInit(false.B);val writeDebt=RegInit(false.B);val memoryDebt=RegInit(false.B)
  val mask=Reg(UInt(8.W));val physicalSteps=RegInit(0.U(64.W))
  when(io.matrix.group.fire){assert(!matrixDebt);matrixDebt:=true.B;mask:=io.matrix.group.bits.sliceMask}
  when(io.matrix.done.fire){assert(matrixDebt);matrixDebt:=false.B}
  when(io.matrix.step.fire){physicalSteps:=physicalSteps+PopCount(mask)}
  owner.io.physicalSteps:=physicalSteps
  when(io.matrix.seed.get.begin.fire){assert(!seedDebt);seedDebt:=true.B}
  when(io.matrix.seed.get.ack.fire){assert(seedDebt);seedDebt:=false.B}
  when(io.burst.fire){assert(!readDebt && io.burst.bits.beats===1.U);readDebt:=true.B}
  when(io.burstResponse.fire){assert(readDebt);readDebt:=false.B}
  when(io.writeRequest.fire){assert(!writeDebt);writeDebt:=true.B}
  when(io.writeResponse.fire){assert(writeDebt);writeDebt:=false.B}
  when(io.memory.fire){assert(!memoryDebt);memoryDebt:=true.B}
  when(io.response.fire){assert(memoryDebt);memoryDebt:=false.B}
  router.io.matrixDrained:= !matrixDebt && !seedDebt && !io.matrix.result.valid && !io.matrix.done.valid
  router.io.dmaDrained:= !readDebt && !writeDebt && !memoryDebt
  io.resetRequired:=router.io.resetRequired || owner.io.resetRequired;io.reductionOwns:=router.io.reductionOwns
  io.windowAccepted.valid:=owner.io.window.get.request.fire;io.windowAccepted.bits:=owner.io.window.get.request.bits
  io.windowReturned.valid:=owner.io.window.get.result.fire;io.windowReturned.bits:=owner.io.window.get.result.bits
  io.drainReturned.valid:=owner.io.drain.get.result.fire;io.drainReturned.bits:=owner.io.drain.get.result.bits
  io.tileState:=owner.io.tiles.get.state;io.tileDrained:=owner.io.tiles.get.drained
  // Internal RMW write observed through BoringUtils, not the external bridge-only port.
  val diagnostic=IO(Output(new Bundle {
    val state=UInt(4.W);val status=UInt(8.W);val terminalIssued=UInt(5.W)
    val captured=UInt(3.W);val written=UInt(3.W);val contexts=UInt(3.W)
    val windowPhase=UInt(3.W);val nBase=UInt(16.W);val prefixWriteIndex=UInt(8.W)
    val writeContext=UInt(3.W);val groupSequence=UInt(32.W);val bankReset=Bool()
    val firstStatus=UInt(8.W);val firstState=UInt(4.W);val firstTerminalIssued=UInt(5.W)
    val firstCaptured=UInt(3.W);val firstWritten=UInt(3.W);val firstBankReset=Bool()
  }))
  def observe(source:Data,sink:Data,name:String):Unit={BoringUtils.addSource(source,name);BoringUtils.addSink(sink,name)}
  diagnostic.state:=0.U;diagnostic.status:=0.U;diagnostic.terminalIssued:=0.U
  diagnostic.captured:=0.U;diagnostic.written:=0.U;diagnostic.contexts:=0.U
  diagnostic.windowPhase:=0.U;diagnostic.nBase:=0.U;diagnostic.prefixWriteIndex:=0.U
  diagnostic.writeContext:=0.U;diagnostic.groupSequence:=0.U;diagnostic.bankReset:=false.B
  io.tileWrite.valid:=false.B;io.tileWrite.bits:=0.U.asTypeOf(new FfnTileBeat)
  observe(owner.state,diagnostic.state,"b_owner_state");observe(owner.status,diagnostic.status,"b_owner_status")
  observe(owner.terminalIssued,diagnostic.terminalIssued,"b_terminal_issued")
  observe(owner.captured,diagnostic.captured,"b_captured");observe(owner.written,diagnostic.written,"b_written")
  observe(owner.contexts,diagnostic.contexts,"b_contexts");observe(owner.windowPhase.get,diagnostic.windowPhase,"b_window_phase")
  observe(owner.nBase,diagnostic.nBase,"b_nbase");observe(owner.prefixWriteIndex,diagnostic.prefixWriteIndex,"b_prefix_index")
  observe(owner.writeContext,diagnostic.writeContext,"b_write_context");observe(owner.groupSequence,diagnostic.groupSequence,"b_group_sequence")
  observe(owner.banks.io.tiles.get.resetRequired,diagnostic.bankReset,"b_bank_reset")
  // Use an internal Boolean wire for the fire expression's annotation target.
  val writeObserved=WireDefault(false.B)
  BoringUtils.addSource(owner.banks.io.tiles.get.write.valid,"b_tile_write_valid")
  BoringUtils.addSink(writeObserved,"b_tile_write_valid")
  val writeReady=WireDefault(false.B)
  BoringUtils.addSource(owner.banks.io.tiles.get.write.ready,"b_tile_write_ready")
  BoringUtils.addSink(writeReady,"b_tile_write_ready")
  io.tileWrite.valid:=writeObserved && writeReady
  observe(owner.banks.io.tiles.get.write.bits,io.tileWrite.bits,"b_tile_write_bits")
  val seen=RegInit(false.B);val fs=RegInit(0.U(8.W));val st=RegInit(0.U(4.W));val ti=RegInit(0.U(5.W))
  val ca=RegInit(0.U(3.W));val wr=RegInit(0.U(3.W));val br=RegInit(false.B)
  when(!seen && (diagnostic.status=/=0.U || diagnostic.bankReset)){
    seen:=true.B;fs:=diagnostic.status;st:=diagnostic.state;ti:=diagnostic.terminalIssued
    ca:=diagnostic.captured;wr:=diagnostic.written;br:=diagnostic.bankReset
  }
  diagnostic.firstStatus:=fs;diagnostic.firstState:=st;diagnostic.firstTerminalIssued:=ti
  diagnostic.firstCaptured:=ca;diagnostic.firstWritten:=wr;diagnostic.firstBankReset:=br
}
