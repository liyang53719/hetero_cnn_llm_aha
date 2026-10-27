// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Numerical/storage contract of the original official public21 chain.
  * This combinational decoder adds no arithmetic, feeder, or model-specific
  * elaboration. It is NOT a full-block scheduler or proof of execution.
  * Its caller must retain the original ordered reduction implementation;
  * interpreting `requiresOrderedQkvReduction` as plain Dense is incorrect.
  */
class Qwen2Public21BoundaryV2 extends Bundle {
  val valid = Bool()
  val dense = Bool()
  val virtualAttentionStage = Bool()
  val activationBf16Storage = Bool()
  val weightBf16Storage = Bool()
  val outputBf16Storage = Bool()
  val materializeDenseOutput = Bool()
  val requiresOrderedQkvReduction = Bool()
  val firstKEnd = UInt(16.W)
  val secondKBegin = UInt(16.W)
  val secondKEnd = UInt(16.W)
  val pairReverse = Bool()
  val inputBytesPerElement = UInt(3.W)
  val outputBytesPerElement = UInt(3.W)
}
object Qwen2Public21BoundaryV2 {
  def decode(context: UnifiedBlockDispatchV1, publicPc: UInt): Qwen2Public21BoundaryV2 = {
    val b = WireDefault(0.U.asTypeOf(new Qwen2Public21BoundaryV2))
    val (expected, known) = UnifiedRuntimeProfile.decode(context.launch.profileId)
    // Admit the existing true M128 contract, never 128 independent M1 jobs.
    // M16 is retained only because it is an original public21 diagnostic size.
    // Transaction0 is assigned by the real admission. Structural decode is not
    // authority: the caller must separately bind active plus the complete snapshot.
    b.valid := known && context.profile.asUInt === expected.asUInt &&
      context.launch.profileId === UnifiedProfileId.Qwen2Attention.U &&
      context.launch.version === 1.U &&
      context.launch.opcode === 0.U &&
      (context.launch.tokens === 16.U || context.launch.tokens === 128.U) && publicPc < 21.U
    val qkv = publicPc === 1.U || publicPc === 4.U || publicPc === 7.U
    val rounded = publicPc === 13.U || publicPc === 16.U || publicPc === 17.U || publicPc === 19.U
    b.dense := b.valid && (qkv || rounded)
    b.virtualAttentionStage := b.valid && (publicPc === 10.U || publicPc === 11.U)
    // BF16 values in FP32 containers are not packed BF16 storage. The bias
    // owner materializes Q/K/V AFTER the FP32 two-range ordered reduction.
    b.activationBf16Storage := false.B
    b.outputBf16Storage := false.B
    b.weightBf16Storage := b.dense
    b.materializeDenseOutput := b.valid && rounded
    b.requiresOrderedQkvReduction := b.valid && qkv
    b.firstKEnd := Mux(b.requiresOrderedQkvReduction, 1024.U, 0.U)
    b.secondKBegin := Mux(b.requiresOrderedQkvReduction, 1024.U, 0.U)
    b.secondKEnd := Mux(b.requiresOrderedQkvReduction, 1536.U, 0.U)
    b.pairReverse := b.requiresOrderedQkvReduction
    b.inputBytesPerElement := Mux(b.valid, 4.U, 0.U)
    b.outputBytesPerElement := Mux(b.valid, 4.U, 0.U)
    b
  }
}
