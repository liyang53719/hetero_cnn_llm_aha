// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Shared Scala type only. This Bundle owns no storage or arithmetic.
  * With transposed=false, names, directions and widths match the original
  * anonymous StreamingDenseOwner IO exactly. The candidate patch replaces
  * only that declaration, so elaboration selects ONE Dense implementation.
  */
class DenseOwnerIO(burstWrites:Boolean,transposed:Boolean=false,enableAccumulatorSeed:Boolean=false,downChunks:Boolean=false,enableFfnTiles:Boolean=false,enableFfnWindow:Boolean=false,enableFfnDrain:Boolean=false,enableKWindow:Boolean=false) extends Bundle {
  val drain=if(enableFfnDrain)Some(new FfnDrainPort)else None
  val window=if(enableFfnWindow)Some(new FfnWindowPort(enableFfnDrain,enableKWindow))else None
  val tiles=if(enableFfnTiles)Some(new FfnTilePort(enableMatrixProducerOrder=enableFfnWindow))else None
  val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
  val writeRequest=if(burstWrites)Some(Decoupled(new BurstWriteRequest))else None
  val writeData=if(burstWrites)Some(Decoupled(new BurstWriteBeat))else None
  val writeResponse=if(burstWrites)Some(Flipped(Decoupled(new MemoryResponse)))else None
  val prefixWorkspace=if(enableAccumulatorSeed)Some(Input(new TransposedPrefixWorkspace(if(downChunks)2560 else 1536)))else None
  val matrix=new MatrixStreamPort(enableTransposedDense=transposed,enableAccumulatorSeed=enableAccumulatorSeed)
  val physicalSteps=Input(UInt(64.W));val profile=Output(new DenseCycleProfile)
  val resetRequired=Output(Bool());val issueCycles=Output(UInt(64.W));val operandStalls=Output(UInt(64.W))
}

/** Internal completion is not a Host DDR completion. The original job retains
  * the full B row stride; ng/cols only select its Matrix context window. */
class FfnWindowRequest(enableKWindow:Boolean=false) extends Bundle {
  val kWindow=if(enableKWindow)Some(new DenseKWindowPolicy)else None
  val job=new QwenOwnerJob
  val identity=UInt(32.W);val ng=UInt(16.W);val cols=UInt(8.W);val slot=UInt(2.W);val reuseA=Bool()
}
class FfnWindowResult(enableCounters:Boolean=false,enableKWindow:Boolean=false) extends Bundle {
  val kWindow=if(enableKWindow)Some(new DenseKWindowPolicy)else None
  val cycles=if(enableCounters)Some(UInt(64.W))else None
  val usefulMacs=if(enableCounters)Some(UInt(64.W))else None
  val executedMacs=if(enableCounters)Some(UInt(64.W))else None
  val tag=UInt(32.W);val identity=UInt(32.W);val ng=UInt(16.W);val cols=UInt(8.W);val slot=UInt(2.W)
  val rows=UInt(8.W);val status=UInt(8.W);val committed=Bool();val producedBeats=UInt(11.W)
  val ddrWriteBytes=UInt(64.W)
}
class FfnWindowPort(enableCounters:Boolean=false,enableKWindow:Boolean=false) extends Bundle {
  val request=Flipped(Decoupled(new FfnWindowRequest(enableKWindow)));val result=Decoupled(new FfnWindowResult(enableCounters,enableKWindow))
  val invalidateLease=Input(Bool())
  val busy=Output(Bool());val leaseValid=Output(Bool());val resetRequired=Output(Bool())
}
class FfnALease extends Bundle {
  val base=UInt(64.W);val activationBf16=Bool();val rows=UInt(16.W);val k=UInt(16.W)
  val rowStride=UInt(64.W);val identity=UInt(32.W)
}

/** Independent typed Activation drain. No public Host command/completion ABI.
  * The complete job retains the full FP32 Gate/Up/Act spans and N=K=8960.
  * Slot 2 is fixed; only identity and a bounded column window are selectable.
  */
class FfnDrainRequest extends Bundle {
  val job=new QwenOwnerJob
  val identity=UInt(32.W);val ng=UInt(16.W);val cols=UInt(8.W)
}
class FfnDrainResult extends Bundle {
  val tag=UInt(32.W);val identity=UInt(32.W);val ng=UInt(16.W);val rows=UInt(8.W);val cols=UInt(8.W)
  val status=UInt(8.W);val committed=Bool();val consumedBeats=UInt(11.W);val ddrWriteBytes=UInt(64.W)
  val cycles=UInt(64.W);val usefulMacs=UInt(64.W);val executedMacs=UInt(64.W)
}
class FfnDrainPort extends Bundle {
  val request=Flipped(Decoupled(new FfnDrainRequest));val result=Decoupled(new FfnDrainResult)
  val abort=Input(Bool());val busy=Output(Bool());val resetRequired=Output(Bool())
}

/** Internal policy only: full Job K/strides/alias ranges/A lease never change.
  * A caller supplies the official shape-dependent split and pair order.
  * Disabled preserves ordinary window semantics; enabled emits raw FP32.
  */
class DenseKWindowPolicy extends Bundle {
  val enabled=Bool();val begin=UInt(16.W);val end=UInt(16.W)
  val pairReverse=Bool();val blockId=UInt(32.W)
}
