// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Shared Scala type only. This Bundle owns no storage or arithmetic.
  * With transposed=false, names, directions and widths match the original
  * anonymous StreamingDenseOwner IO exactly. The candidate patch replaces
  * only that declaration, so elaboration selects ONE Dense implementation.
  */
class DenseOwnerIO(burstWrites:Boolean,transposed:Boolean=false) extends Bundle {
  val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
  val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
  val burst=Decoupled(new BurstReadRequest);val burstResponse=Flipped(Decoupled(new BurstReadResponse))
  val writeRequest=if(burstWrites)Some(Decoupled(new BurstWriteRequest))else None
  val writeData=if(burstWrites)Some(Decoupled(new BurstWriteBeat))else None
  val writeResponse=if(burstWrites)Some(Flipped(Decoupled(new MemoryResponse)))else None
  val matrix=new MatrixStreamPort(enableTransposedDense=transposed)
  val physicalSteps=Input(UInt(64.W));val profile=Output(new DenseCycleProfile)
  val resetRequired=Output(Bool());val issueCycles=Output(UInt(64.W));val operandStalls=Output(UInt(64.W))
}
