package heteronpu.operator

import PrimitiveFlags._
import PrimitiveKind._

/** Text-path operator programs shared by Qwen2, Qwen3.5 and Qwen3.8.
  *
  * The programs deliberately contain no model dimensions.  Runtime dimensions
  * and tensor roots are selected from OperatorLaunch.  Projection selectors,
  * branch selectors and constant selectors are carried in index0/index1.
  */
object TextPrograms {
  val TokenEmbedding: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(EmbeddingLookup, flags = Last, src0 = 0, src1 = 1, dst = 2, m = 0, n = 1)
  )

  /** Complete Qwen2 decoder block: RMSNorm, biased QKV, RoPE/GQA attention,
    * SwiGLU MLP and both residual edges.
    *
    * dim slots: 0=tokens, 1=hidden, 2=qHeads, 3=kvHeads,
    * 4=headDim, 5=intermediate, 6=context, 7=unused.
    */
  val Qwen2DecoderBlock: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(RmsNorm, src0 = 0, src1 = 1, dst = 8, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 2, k = 1, index0 = 0),
    MicroOpTemplate(VectorAdd, ApplyBias, src0 = 6, src1 = 3, dst = 6, m = 0, n = 2, index0 = 0),
    MicroOpTemplate(Rope, src0 = 6, src1 = 4, dst = 6, m = 0, n = 2, k = 4, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 1),
    MicroOpTemplate(VectorAdd, ApplyBias, src0 = 6, src1 = 3, dst = 6, m = 0, n = 3, index0 = 1),
    MicroOpTemplate(Rope, src0 = 6, src1 = 4, dst = 6, m = 0, n = 3, k = 4, index0 = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 2),
    MicroOpTemplate(VectorAdd, ApplyBias, src0 = 6, src1 = 3, dst = 6, m = 0, n = 3, index0 = 2),
    MicroOpTemplate(KvAppend, Stateful, src0 = 6, dst = 5, m = 0, n = 3, k = 4),
    MicroOpTemplate(KvGather, Stateful, src0 = 5, dst = 7, m = 0, n = 6, k = 4),
    MicroOpTemplate(MatrixQk, of(Causal, Gqa), src0 = 6, src1 = 7, dst = 9, m = 2, n = 6, k = 4),
    MicroOpTemplate(VectorMul, src0 = 9, src1 = 14, dst = 9, m = 2, n = 6, index0 = 0),
    MicroOpTemplate(ApplyMask, Causal, src0 = 9, src1 = 14, dst = 9, m = 0, n = 6, index0 = 1),
    MicroOpTemplate(OnlineSoftmax, Causal, src0 = 9, src1 = 14, dst = 9, m = 2, n = 6),
    MicroOpTemplate(MatrixPv, Gqa, src0 = 9, src1 = 7, dst = 10, m = 2, n = 4, k = 6),
    MicroOpTemplate(MatrixGemm, src0 = 10, src1 = 11, dst = 10, m = 0, n = 1, k = 1),
    MicroOpTemplate(VectorAdd, src0 = 0, src1 = 10, dst = 10, m = 0, n = 1),
    MicroOpTemplate(RmsNorm, src0 = 10, src1 = 12, dst = 8, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 13, dst = 6, m = 0, n = 5, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 13, dst = 7, m = 0, n = 5, k = 1, index0 = 1),
    MicroOpTemplate(Silu, src0 = 6, dst = 6, m = 0, n = 5),
    MicroOpTemplate(VectorMul, src0 = 6, src1 = 7, dst = 6, m = 0, n = 5),
    MicroOpTemplate(MatrixGemm, src0 = 6, src1 = 13, dst = 8, m = 0, n = 1, k = 5, index0 = 2),
    MicroOpTemplate(VectorAdd, src0 = 10, src1 = 8, dst = 8, m = 0, n = 1),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Dense full-attention block used every fourth layer in Qwen3.5.
    * It includes the model-specific Q/K RMSNorm, partial interleaved MRoPE and
    * sigmoid attention-output gate before O projection.
    */
  val Qwen35DenseAttention: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(RmsNorm, src0 = 0, src1 = 1, dst = 8, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 2, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 2),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 3, dst = 7, m = 0, n = 2, k = 1, index0 = 3),
    MicroOpTemplate(RmsNorm, src0 = 6, src1 = 4, dst = 6, m = 0, n = 2, k = 4, index0 = 0),
    MicroOpTemplate(RmsNorm, src0 = 6, src1 = 4, dst = 6, m = 0, n = 3, k = 4, index0 = 1),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 6, src1 = 5, dst = 6, m = 0, n = 2, k = 4, index0 = 0),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 6, src1 = 5, dst = 6, m = 0, n = 3, k = 4, index0 = 1),
    MicroOpTemplate(KvAppend, Stateful, src0 = 6, dst = 9, m = 0, n = 3, k = 4),
    MicroOpTemplate(KvGather, Stateful, src0 = 9, dst = 10, m = 0, n = 6, k = 4),
    MicroOpTemplate(MatrixQk, of(Causal, Gqa), src0 = 6, src1 = 10, dst = 11, m = 2, n = 6, k = 4),
    MicroOpTemplate(VectorMul, src0 = 11, src1 = 14, dst = 11, m = 2, n = 6, index0 = 0),
    MicroOpTemplate(ApplyMask, Causal, src0 = 11, src1 = 14, dst = 11, m = 0, n = 6),
    MicroOpTemplate(OnlineSoftmax, Causal, src0 = 11, dst = 11, m = 2, n = 6),
    MicroOpTemplate(MatrixPv, Gqa, src0 = 11, src1 = 10, dst = 12, m = 2, n = 4, k = 6),
    MicroOpTemplate(Sigmoid, src0 = 7, dst = 7, m = 0, n = 2, k = 4),
    MicroOpTemplate(VectorMul, src0 = 12, src1 = 7, dst = 12, m = 0, n = 2, k = 4),
    MicroOpTemplate(MatrixGemm, src0 = 12, src1 = 13, dst = 12, m = 0, n = 1, k = 2),
    MicroOpTemplate(VectorAdd, src0 = 0, src1 = 12, dst = 12, m = 0, n = 1),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Gated-DeltaNet primitive shared by Qwen3.5 and Qwen3.8.
    *
    * The exact recurrence represented here is:
    *   q,k <- L2Norm(q,k); q <- q/sqrt(d)
    *   decay <- exp(-exp(A_log) * softplus(a + dt_bias))
    *   beta <- sigmoid(b)
    *   S <- decay*S
    *   delta <- beta*(v - S^T*k)
    *   S <- S + k*delta^T
    *   y <- S^T*q
    * followed by RMSNorm, descriptor-selected SiLU/sigmoid output gate and
    * output projection.  The causal-convolution and recurrent matrices use
    * independent state descriptors.
    */
  val GatedDeltaNet: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(RmsNorm, src0 = 0, src1 = 1, dst = 8, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 2, dst = 6, m = 0, n = 2, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 3, dst = 7, m = 0, n = 3, k = 1, index0 = 1),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 4, dst = 7, m = 0, n = 3, k = 1, index0 = 2),
    MicroOpTemplate(MatrixGemm, src0 = 8, src1 = 5, dst = 7, m = 0, n = 3, k = 1, index0 = 3),
    MicroOpTemplate(StateRead, Stateful, src0 = 9, dst = 10, m = 6),
    MicroOpTemplate(DepthwiseConv, of(Stateful, Causal, ApplyActivation), src0 = 6, src1 = 11, src2 = 10, dst = 6, m = 0, n = 2, k = 6),
    MicroOpTemplate(StateWrite, Stateful, src0 = 10, dst = 9, m = 6),
    MicroOpTemplate(L2Norm, src0 = 6, dst = 6, m = 0, n = 2, k = 4, index0 = 0),
    MicroOpTemplate(L2Norm, src0 = 6, dst = 6, m = 0, n = 2, k = 4, index0 = 1),
    MicroOpTemplate(Rsqrt, src0 = 14, dst = 10, k = 4, index0 = 0),
    MicroOpTemplate(VectorMul, src0 = 6, src1 = 10, dst = 6, m = 0, n = 2, k = 4, index0 = 0),
    MicroOpTemplate(VectorAdd, src0 = 7, src1 = 14, dst = 7, m = 0, n = 3, index0 = 1),
    MicroOpTemplate(Softplus, src0 = 7, dst = 7, m = 0, n = 3, index0 = 1),
    MicroOpTemplate(VectorMul, src0 = 14, src1 = 14, dst = 10, n = 3, index0 = 2),
    MicroOpTemplate(Exp2, src0 = 10, dst = 10, n = 3, index0 = 0),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 7, dst = 10, n = 3, index0 = 1),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 14, dst = 10, n = 3, index0 = 3),
    MicroOpTemplate(Exp2, src0 = 10, dst = 10, n = 3, index0 = 1),
    MicroOpTemplate(Sigmoid, src0 = 7, dst = 7, m = 0, n = 3, index0 = 2),
    MicroOpTemplate(StateRead, Stateful, src0 = 12, dst = 13, m = 3, n = 4, k = 5),
    MicroOpTemplate(VectorMul, Stateful, src0 = 13, src1 = 10, dst = 13, m = 3, n = 4, k = 5),
    MicroOpTemplate(MatrixGemv, src0 = 13, src1 = 6, dst = 10, m = 3, n = 5, k = 4, index0 = 0),
    MicroOpTemplate(VectorSub, src0 = 6, src1 = 10, dst = 10, m = 0, n = 3, k = 5, index0 = 2),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 7, dst = 10, m = 0, n = 3, k = 5, index0 = 2),
    MicroOpTemplate(MatrixOuter, Stateful, src0 = 6, src1 = 10, src2 = 13, dst = 13, m = 3, n = 4, k = 5),
    MicroOpTemplate(MatrixGemv, src0 = 13, src1 = 6, dst = 10, m = 3, n = 5, k = 4, index0 = 1),
    MicroOpTemplate(RmsNorm, src0 = 10, src1 = 14, dst = 10, m = 0, n = 3, k = 5),
    MicroOpTemplate(ConfiguredGateAct, of(Configurable), src0 = 7, dst = 7, m = 0, n = 3, k = 5, index0 = 0),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 7, dst = 10, m = 0, n = 3, k = 5),
    MicroOpTemplate(MatrixGemm, src0 = 10, src1 = 14, dst = 10, m = 0, n = 1, k = 3, index0 = 4),
    MicroOpTemplate(VectorAdd, src0 = 0, src1 = 10, dst = 10, m = 0, n = 1),
    MicroOpTemplate(StateWrite, Stateful, src0 = 13, dst = 12, m = 3, n = 4, k = 5),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Top-K routed and shared expert block.  k is runtime-selected (8 for
    * Qwen3.5 and 10 for Qwen3.8); selected router logits are normalized before
    * dispatch and expert results are weighted during route reduction.
    */
  val Moe: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(RmsNorm, src0 = 0, src1 = 1, dst = 6, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 6, src1 = 2, dst = 7, m = 0, n = 2, k = 1),
    MicroOpTemplate(StableTopK, src0 = 7, dst = 8, m = 0, n = 2, k = 3),
    MicroOpTemplate(OnlineSoftmax, src0 = 8, dst = 8, m = 0, n = 3),
    // RoutedExpert distinguishes MoE route dispatch from an ordinary tensor
    // scatter without adding a public command field.
    MicroOpTemplate(VectorScatter, RoutedExpert, src0 = 6, src1 = 8, dst = 9, m = 0, n = 3, k = 1),
    MicroOpTemplate(StateRead, Stateful, src0 = 14, dst = 14, n = 2),
    MicroOpTemplate(DmaRead, of(RoutedExpert), src0 = 3, src1 = 9, src2 = 14, dst = 10, m = 6, n = 4, k = 1),
    MicroOpTemplate(MatrixGemm, of(RoutedExpert), src0 = 9, src1 = 10, dst = 11, m = 6, n = 4, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, of(RoutedExpert), src0 = 9, src1 = 10, dst = 12, m = 6, n = 4, k = 1, index0 = 1),
    MicroOpTemplate(Silu, RoutedExpert, src0 = 11, dst = 11, m = 6, n = 4),
    MicroOpTemplate(VectorMul, RoutedExpert, src0 = 11, src1 = 12, dst = 11, m = 6, n = 4),
    MicroOpTemplate(MatrixGemm, RoutedExpert, src0 = 11, src1 = 10, dst = 11, m = 6, n = 1, k = 4, index0 = 2),
    MicroOpTemplate(VectorFma, RoutedExpert, src0 = 11, src1 = 8, src2 = 13, dst = 13, m = 0, n = 1, k = 3),
    MicroOpTemplate(DmaRead, SharedExpert, src0 = 4, src2 = 14, dst = 10, m = 0, n = 5, k = 1),
    MicroOpTemplate(MatrixGemm, SharedExpert, src0 = 6, src1 = 10, dst = 11, m = 0, n = 5, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, SharedExpert, src0 = 6, src1 = 10, dst = 12, m = 0, n = 5, k = 1, index0 = 1),
    MicroOpTemplate(Silu, SharedExpert, src0 = 11, dst = 11, m = 0, n = 5),
    MicroOpTemplate(VectorMul, SharedExpert, src0 = 11, src1 = 12, dst = 11, m = 0, n = 5),
    MicroOpTemplate(MatrixGemm, SharedExpert, src0 = 11, src1 = 10, dst = 11, m = 0, n = 1, k = 5, index0 = 2),
    MicroOpTemplate(MatrixGemv, SharedExpert, src0 = 6, src1 = 5, dst = 12, m = 0, n = 1, k = 1),
    MicroOpTemplate(Sigmoid, SharedExpert, src0 = 12, dst = 12, m = 0),
    MicroOpTemplate(VectorMul, SharedExpert, src0 = 11, src1 = 12, dst = 11, m = 0, n = 1),
    MicroOpTemplate(VectorAdd, src0 = 13, src1 = 11, dst = 13, m = 0, n = 1),
    MicroOpTemplate(VectorAdd, src0 = 0, src1 = 13, dst = 13, m = 0, n = 1),
    MicroOpTemplate(StateWrite, Stateful, src0 = 14, dst = 14, n = 2),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )
}

class HeteroTokenEmbeddingPrimitiveV3
  extends ProgramPrimitive(TextPrograms.TokenEmbedding, "HeteroTokenEmbeddingPrimitiveV3")
class HeteroQwen2DecoderBlockPrimitiveV3
  extends ProgramPrimitive(TextPrograms.Qwen2DecoderBlock, "HeteroQwen2DecoderBlockPrimitiveV3")
class HeteroQwen35DenseAttentionPrimitiveV3
  extends ProgramPrimitive(TextPrograms.Qwen35DenseAttention, "HeteroQwen35DenseAttentionPrimitiveV3")
class HeteroGatedDeltaNetPrimitiveV3
  extends ProgramPrimitive(TextPrograms.GatedDeltaNet, "HeteroGatedDeltaNetPrimitiveV3")
class HeteroMoePrimitiveV3
  extends ProgramPrimitive(TextPrograms.Moe, "HeteroMoePrimitiveV3")
