// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Decoded recurrent-core job. This is not a public Host descriptor.
  * M=1 is intentional. Q/K/V are FP32 [heads,dimension]; Q is already L2
  * normalized and scaled by 1/sqrt(Dk), K is already L2 normalized. V is the
  * exact FP32 expansion of its producer. Gate records are 64 bytes/head:
  * {FP32 log-decay, FP32 beta, fourteen zero words}. State is native FP32
  * [heads,Dk,Dv]. No BF16 conversion is permitted at the state boundary.
  * Output is explicit RNE BF16 [heads,Dv]; stateOut stays FP32.
  * Output and stateOut must be private staging allocations. Only stateCommitted
  * authorizes publishing both spans and incrementing the caller's generation.
  */
class GdnRecurrentJob extends Bundle {
  val tokens = UInt(16.W)
  val heads = UInt(16.W)
  val keyDim = UInt(16.W)
  val valueDim = UInt(16.W)
  val query = UInt(64.W)
  val key = UInt(64.W)
  val value = UInt(64.W)
  val gates = UInt(64.W)
  val stateIn = UInt(64.W)
  val stateOut = UInt(64.W)
  val output = UInt(64.W)
  val cold = Bool()
  val expectedGeneration = UInt(32.W)
  val tag = UInt(32.W)
}
class GdnRecurrentResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val stateCommitted = Bool()
  val generation = UInt(32.W)
}
class GdnRecurrentOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnRecurrentJob))
  val currentGeneration = Input(UInt(32.W))
  val done = Decoupled(new GdnRecurrentResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}
