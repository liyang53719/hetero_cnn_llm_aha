// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._

/** New versioned ABI; it does not silently widen or reinterpret legacy kind4.
  * The five model choices are runtime values on the same wires. All pointers
  * are 64-bit. Weights, activation tiles, KV, MoE experts, and GDN persistent
  * state live in explicitly supplied DDR regions, not profile-sized registers.
  */
class UnifiedBlockLaunchV1 extends Bundle {
  val version = UInt(8.W)
  val opcode = UInt(8.W) // 0: one full block transaction; other values rejected
  val profileId = UInt(3.W)
  val tag = UInt(32.W)
  val tokens = UInt(16.W)
  val positionBase = UInt(32.W)
  val cacheCapacity = UInt(32.W)
  val cacheLength = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val cold = Bool()
  val input = UInt(64.W)
  val weights = UInt(64.W)
  val output = UInt(64.W)
  val scratch = UInt(64.W)
  val stateIn = UInt(64.W)
  val stateOut = UInt(64.W)
  val kvK = UInt(64.W)
  val kvV = UInt(64.W)
}

class UnifiedBlockDispatchV1 extends Bundle {
  val transactionId = UInt(64.W) // admission-assigned, non-wrapping within reset epoch
  val launch = new UnifiedBlockLaunchV1
  val profile = new UnifiedRuntimeProfile
}

/** Backend completion is an obligation, not a software success flag in a
  * complete top. Until the shared scheduler is wired, admission is only a
  * separately tested control component, never a full-block execution test.
  */
class UnifiedBlockCompletionV1 extends Bundle {
  val transactionId = UInt(64.W)
  val tag = UInt(32.W)
  val profileId = UInt(3.W)
  val status = UInt(8.W)
  val acknowledgedWriteBytes = UInt(64.W)
  val issuedSliceSteps = UInt(64.W) // issued slots, NOT completed/useful MACs
  val drained = Bool()
  val resetRequired = Bool()
}

class UnifiedBlockResultV1 extends Bundle {
  val transactionId = UInt(64.W)
  val version = UInt(8.W)
  val profileId = UInt(3.W)
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val controlCycles = UInt(64.W)
  val acknowledgedWriteBytes = UInt(64.W)
  val issuedSliceSteps = UInt(64.W)
  val resetRequired = Bool()
}

/** Common internal operation encoding to replace, rather than truncate into,
  * the exhausted legacy 4-bit owner kind. Physical implementations are shared
  * and time multiplexed; defining an opcode does not claim its implementation.
  */
object UnifiedOperation {
  val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4
  val Add=5; val Activation=6; val KvAppend=7; val GdnConv=8
  val GdnChunk=9; val GdnInputPrep=10; val GdnRmsNorm=11
  val GdnGatedNorm=12; val Elementwise=13; val QkNorm=14; val PartialRope=15
  val MoeRouter=16; val MoeExpert=17; val MoeReduce=18
}
