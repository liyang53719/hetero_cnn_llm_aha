// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._

/** Internal proposed chunk64 types only. No owner, execution port, decoder,
  * arithmetic resource or publication authority is implemented by this file.
  * Existing public M1/recurrent contracts are intentionally unchanged.
  */
object GdnChunkGeometry {
  val ChunkRows = 64
  val Heads = 16
  val KeyDim = 128
  val ValueDim = 128
  val BeatBytes = 64
  val PreparedRowBytes = 25600
  val StateBytes = 1048576
  val OutputRowBytes = 4096
  val AddressBits = 56
  val SupportedTokens: Set[Int] = Set(16, 128)
}

/** These IDs describe a required explicit numerical contract, not available
  * hardware modes. All dots/solves use ascending separate FP32 RNE Mul then Add
  * from +0, no FMA; cumsum resets per chunk. Exp is the existing negative-P7
  * saturation recipe. State never narrows to BF16; only core output does.
  * Policy 1's finite gradual-underflow control is NOT yet wired to Vector RTL.
  */
object GdnChunkVectorPolicy {
  val LegacyFatalUnderflow = 0
  val FiniteGradualUnderflow = 1
}

class GdnChunkJob extends Bundle {
  val tag = UInt(32.W)
  val tokens = UInt(16.W) // admitted values are exactly 16 or 128
  val cold = Bool()
  val expectedGeneration = UInt(32.W)
  val vectorPolicy = UInt(1.W)
  val input = UInt(64.W)
  val stateIn = UInt(64.W)
  val stateOut = UInt(64.W)
  val output = UInt(64.W)
  val scratch = UInt(64.W)
}

/** Snapshot supplied by the existing root owner, not a caller-selected
  * replacement for it. Cold requires invalid/generation=0; carried requires
  * valid, exact generation and exact stateIn. Root publication stays external.
  */
class GdnChunkCommittedState extends Bundle {
  val valid = Bool()
  val generation = UInt(32.W)
  val state = UInt(64.W)
}

/** A future implementation must derive this from its actual accepted request
  * and matching successful response, not from a software-provided success bit.
  * No port accepts these receipts in this source-only batch.
  */
class GdnChunkStageReceipt extends Bundle {
  val tag = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val head = UInt(4.W)
  val chunk = UInt(1.W)
  val phase = UInt(5.W)
  val status = UInt(8.W)
  val scratchAckBytes = UInt(64.W)
  val outputAckBytes = UInt(64.W)
  val stateAckBytes = UInt(64.W)
  val drained = Bool()
}

/** Held private-staging result. It deliberately has NO stateCommitted,
  * historyCommitted, generationAdvanced or newGeneration field. Even an exact
  * stagedComplete result cannot publish persistent roots: the original Host
  * terminal fence also needs Conv history, final residual and no outstanding
  * obligations. Arithmetic/transport that could produce this is not added here.
  */
class GdnChunkStagingResult extends Bundle {
  val tag = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val status = UInt(8.W)
  val stagedComplete = Bool()
  val stateOut = UInt(64.W)
  val output = UInt(64.W)
  val completedHeadChunks = UInt(6.W) // 16 or 32, never a publication count
  val scratchAckBytes = UInt(64.W)
  val stateAckBytes = UInt(64.W)
  val outputAckBytes = UInt(64.W)
  val drained = Bool()
}
