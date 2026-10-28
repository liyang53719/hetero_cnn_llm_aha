// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** WORK-ONLY CANDIDATE. Internal owner traffic, never a Host command encoding.
  * The resident owner validates physical C slot, M/N/K, generation and aliasing
  * against its actual prefix/ownerN metadata BEFORE presenting begin.valid.
  * groupSequence is an owner-issued, non-wrapping group identity. It is separate
  * from job tag and from the source C-slot generation. Wrap requires coordinated
  * drain/reset; a controller-only reset never makes a stale response safe.
  */
class MatrixAccumulatorSeedRequest extends Bundle {
  val groupTag=UInt(32.W)
  val groupSequence=UInt(32.W)
  val sourceGeneration=UInt(32.W)
  val context=UInt(3.W)
  val sliceMask=UInt(8.W)
}

class MatrixAccumulatorSeedBeat extends Bundle {
  val groupTag=UInt(32.W)
  val groupSequence=UInt(32.W)
  val sourceGeneration=UInt(32.W)
  val context=UInt(3.W)
  val index=UInt(8.W)
  val data=UInt(512.W) // lane j is bits 32*j+31:32*j; no FP conversion
  val last=Bool()
  val error=Bool() // real resident SRAM read/transport error, not FMA flags
}

class MatrixAccumulatorSeedAck extends Bundle {
  val groupTag=UInt(32.W)
  val groupSequence=UInt(32.W)
  val sourceGeneration=UInt(32.W)
  val context=UInt(3.W)
  val error=Bool()
}

/** Producer orientation; service flips this port. It is present only when
  * enableAccumulatorSeed=true on the future MatrixStreamPort integration.
  */
class MatrixAccumulatorSeedPort extends Bundle {
  val begin=Decoupled(new MatrixAccumulatorSeedRequest)
  val beat=Decoupled(new MatrixAccumulatorSeedBeat)
  val ack=Flipped(Decoupled(new MatrixAccumulatorSeedAck))
}

class MatrixAccumulatorSeedLeafBeat extends Bundle {
  val context=UInt(3.W)
  val slice=UInt(3.W)
  val cluster=UInt(5.W)
  val data=UInt(512.W)
}
