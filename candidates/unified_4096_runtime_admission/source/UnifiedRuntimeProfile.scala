// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** One physical design, not model-specific elaboration parameters. These are
  * controller limits; logical tensors and persistent state remain DDR-backed.
  * None of these maxima allocates a full activation/weight/cache tensor here.
  */
object UnifiedPhysicalLimits {
  val MatrixEndpoints = 8
  val MacsPerEndpoint = 512
  val MatrixMacs = MatrixEndpoints * MacsPerEndpoint
  val MatrixRows = 16
  val MatrixColumns = 256
  val MatrixContexts = 5
  val VectorLanes = 16
  val MaxBlockTokens = 128
  val MaxHidden = 2048
  val MaxDenseFfn = 8960
  val MaxAttentionHeads = 16
  val MaxKvHeads = 2
  val MaxHeadDim = 256
  val MaxGdnKeyHeads = 16
  val MaxGdnValueHeads = 32
  val GdnKeyDim = 128
  val GdnValueDim = 128
  val GdnChunkTokens = 64
  val MaxExperts = 256
  val MaxExpertsPerToken = 8
  val MaxExpertFfn = 512
  val AddressBits = 64
  val MemoryBeatBits = 512
}

object UnifiedProfileId {
  val Qwen2Attention = 0
  val Qwen35SmallGdn = 1
  val Qwen35SmallAttention = 2
  val Qwen35MoeGdn = 3
  val Qwen35MoeAttention = 4
}

/** All five profiles share this exact bundle. Inactive operator fields are 0.
  * gdnKeyHeads and gdnValueHeads must not be conflated: 35B repeats each of
  * its 16 Q/K heads across two of its 32 value heads.
  */
class UnifiedRuntimeProfile extends Bundle {
  val profileId = UInt(3.W)
  val mixer = UInt(2.W) // 0 attention, 1 GDN
  val mlp = UInt(2.W) // 0 dense, 1 sparse MoE plus shared expert
  val hidden = UInt(16.W)
  val ffn = UInt(16.W)
  val attentionHeads = UInt(6.W)
  val kvHeads = UInt(6.W)
  val headDim = UInt(9.W)
  val rotaryDim = UInt(9.W)
  val gdnKeyHeads = UInt(6.W)
  val gdnValueHeads = UInt(6.W)
  val gdnKeyDim = UInt(9.W)
  val gdnValueDim = UInt(9.W)
  val convKernel = UInt(3.W)
  val expertCount = UInt(9.W)
  val expertsPerToken = UInt(4.W)
  val expertFfn = UInt(16.W)
  val sharedFfn = UInt(16.W)
  val maxPosition = UInt(32.W)
}

/** Hardware decode, never a Scala constructor argument selecting a model.
  * A caller supplies only profileId, not an inconsistent set of dimensions.
  * Return validity separately; invalid IDs never alias an admitted profile.
  */
object UnifiedRuntimeProfile {
  def decode(id: UInt): (UnifiedRuntimeProfile, Bool) = {
    val p = WireDefault(0.U.asTypeOf(new UnifiedRuntimeProfile))
    p.profileId := id
    val valid = id <= UnifiedProfileId.Qwen35MoeAttention.U
    switch(id) {
      is(UnifiedProfileId.Qwen2Attention.U) {
        p.hidden := 1536.U; p.ffn := 8960.U
        p.attentionHeads := 12.U; p.kvHeads := 2.U
        p.headDim := 128.U; p.rotaryDim := 128.U
        p.maxPosition := 32768.U
      }
      is(UnifiedProfileId.Qwen35SmallGdn.U) {
        p.mixer := 1.U; p.hidden := 1024.U; p.ffn := 3584.U
        p.gdnKeyHeads := 16.U; p.gdnValueHeads := 16.U
        p.gdnKeyDim := 128.U; p.gdnValueDim := 128.U
        p.convKernel := 4.U; p.maxPosition := 262144.U
      }
      is(UnifiedProfileId.Qwen35SmallAttention.U) {
        p.hidden := 1024.U; p.ffn := 3584.U
        p.attentionHeads := 8.U; p.kvHeads := 2.U
        p.headDim := 256.U; p.rotaryDim := 64.U
        p.maxPosition := 262144.U
      }
      is(UnifiedProfileId.Qwen35MoeGdn.U) {
        p.mixer := 1.U; p.mlp := 1.U; p.hidden := 2048.U
        p.gdnKeyHeads := 16.U; p.gdnValueHeads := 32.U
        p.gdnKeyDim := 128.U; p.gdnValueDim := 128.U
        p.convKernel := 4.U
        p.expertCount := 256.U; p.expertsPerToken := 8.U
        p.expertFfn := 512.U; p.sharedFfn := 512.U
        p.maxPosition := 262144.U
      }
      is(UnifiedProfileId.Qwen35MoeAttention.U) {
        p.mlp := 1.U; p.hidden := 2048.U
        p.attentionHeads := 16.U; p.kvHeads := 2.U
        p.headDim := 256.U; p.rotaryDim := 64.U
        p.expertCount := 256.U; p.expertsPerToken := 8.U
        p.expertFfn := 512.U; p.sharedFfn := 512.U
        p.maxPosition := 262144.U
      }
    }
    (p, valid)
  }
}
