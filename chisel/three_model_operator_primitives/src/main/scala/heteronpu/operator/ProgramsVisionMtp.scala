package heteronpu.operator

import PrimitiveFlags._
import PrimitiveKind._

object VisionAndBoundaryPrograms {
  /** 3-D patch projection followed by descriptor-driven interpolated position
    * embedding.  MatrixConv carries temporal/spatial patch geometry.
    */
  val VisionPatchEmbed: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(MatrixConv, ApplyBias, src0 = 0, src1 = 1, dst = 2, m = 0, n = 1, k = 2, index0 = 3),
    MicroOpTemplate(BilinearPosition, src0 = 3, src1 = 4, dst = 5, m = 0, n = 1),
    MicroOpTemplate(VectorAdd, Last, src0 = 2, src1 = 5, dst = 6, m = 0, n = 1)
  )

  /** Qwen3.5/Qwen3.8 vision transformer block: two LayerNorms, windowed or
    * full non-causal attention with vision RoPE, GELU MLP and residual edges.
    */
  val VisionTransformerBlock: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(LayerNorm, src0 = 0, src1 = 1, dst = 2, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, ApplyBias, src0 = 2, src1 = 3, dst = 4, m = 0, n = 2, k = 1),
    MicroOpTemplate(Rope, NonCausal, src0 = 4, src1 = 5, dst = 4, m = 0, n = 2, k = 3),
    MicroOpTemplate(MatrixQk, NonCausal, src0 = 4, src1 = 4, dst = 6, m = 2, n = 2, k = 3),
    MicroOpTemplate(VectorMul, src0 = 6, src1 = 14, dst = 6, m = 2, n = 2, index0 = 0),
    MicroOpTemplate(ApplyMask, NonCausal, src0 = 6, src1 = 14, dst = 6, m = 2, n = 2, index0 = 1),
    MicroOpTemplate(OnlineSoftmax, NonCausal, src0 = 6, dst = 6, m = 2, n = 2),
    MicroOpTemplate(MatrixPv, NonCausal, src0 = 6, src1 = 4, dst = 7, m = 2, n = 1, k = 2),
    MicroOpTemplate(MatrixGemm, src0 = 7, src1 = 8, dst = 7, m = 0, n = 1, k = 1),
    MicroOpTemplate(VectorAdd, src0 = 0, src1 = 7, dst = 9, m = 0, n = 1),
    MicroOpTemplate(LayerNorm, src0 = 9, src1 = 10, dst = 2, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, ApplyBias, src0 = 2, src1 = 11, dst = 4, m = 0, n = 4, k = 1),
    MicroOpTemplate(Gelu, src0 = 4, dst = 4, m = 0, n = 4),
    MicroOpTemplate(MatrixGemm, ApplyBias, src0 = 4, src1 = 12, dst = 7, m = 0, n = 1, k = 4),
    MicroOpTemplate(VectorAdd, Last, src0 = 9, src1 = 7, dst = 13, m = 0, n = 1)
  )

  /** Spatial patch merger.  mode bit 1 selects post-shuffle normalization;
    * the LayoutTransform and SpatialMerge leaves use this mode to realize the
    * official pre- or post-shuffle view without changing the microprogram.
    */
  val VisionPatchMerge: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(LayoutTransform, Configurable, src0 = 0, dst = 2, m = 0, n = 1, index0 = 2),
    MicroOpTemplate(LayerNorm, Configurable, src0 = 2, src1 = 1, dst = 2, m = 0, n = 1),
    MicroOpTemplate(SpatialMerge, Configurable, src0 = 2, dst = 3, m = 0, n = 1, index0 = 2),
    MicroOpTemplate(MatrixGemm, ApplyBias, src0 = 3, src1 = 4, dst = 5, m = 0, n = 2, k = 1),
    MicroOpTemplate(Gelu, src0 = 5, dst = 5, m = 0, n = 2),
    MicroOpTemplate(MatrixGemm, of(ApplyBias, Last), src0 = 5, src1 = 6, dst = 7, m = 0, n = 3, k = 2)
  )

  /** Replace image/video placeholder token positions with projected vision
    * embeddings while preserving all non-vision text embeddings.
    */
  val MultimodalInject: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(VectorGather, src0 = 0, src1 = 1, dst = 4, m = 0, n = 1),
    MicroOpTemplate(MultimodalScatter, Last, src0 = 2, src1 = 3, src2 = 4, dst = 5, m = 0, n = 1)
  )

  /** Standalone final normalization for Qwen2/Qwen3.5.  Qwen3.8 uses its
    * dedicated FinalHyperMerge primitive and launches the LM head directly.
    */
  val FinalNorm: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(RmsNorm, Last, src0 = 0, src1 = 1, dst = 2, m = 0, n = 1)
  )

  /** Language head and deterministic argmax are independent from token input
    * embedding, so prefill/decode and MTP can schedule them separately.
    */
  val LmHeadArgmax: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(MatrixGemv, src0 = 0, src1 = 1, dst = 2, m = 0, n = 2, k = 1),
    MicroOpTemplate(Argmax, Last, src0 = 2, dst = 3, m = 0, n = 2)
  )

  /** Produce one or more speculative MTP candidates in a private generation.
    * The transaction is intentionally not committed here.
    */
  val MtpDraft: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(StateRead, Stateful, src0 = 0, dst = 6, m = 0, n = 1),
    MicroOpTemplate(EmbeddingLookup, src0 = 1, src1 = 2, dst = 7, m = 0, n = 1),
    MicroOpTemplate(VectorAdd, src0 = 6, src1 = 7, dst = 7, m = 0, n = 1),
    MicroOpTemplate(RmsNorm, src0 = 7, src1 = 3, dst = 7, m = 0, n = 1),
    MicroOpTemplate(MatrixGemm, src0 = 7, src1 = 4, dst = 8, m = 0, n = 1, k = 1),
    MicroOpTemplate(ConfiguredGateAct, Configurable, src0 = 8, dst = 8, m = 0, n = 1),
    MicroOpTemplate(MatrixGemv, src0 = 8, src1 = 5, dst = 9, m = 0, n = 2, k = 1),
    MicroOpTemplate(Argmax, src0 = 9, dst = 10, m = 0, n = 2),
    MicroOpTemplate(StateWrite, of(Stateful, Last), src0 = 8, src1 = 10, dst = 0, m = 0, n = 1)
  )

  /** Compare draft and target tokens, derive the accepted prefix and atomically
    * commit or roll back all state domains belonging to the MTP generation.
    */
  val MtpVerifyResolve: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(MtpCompare, Stateful, src0 = 0, src1 = 1, dst = 4, m = 0),
    MicroOpTemplate(VectorCompare, src0 = 0, src1 = 1, dst = 5, m = 0, index0 = 0),
    MicroOpTemplate(VectorSelect, src0 = 5, src1 = 0, src2 = 1, dst = 6, m = 0),
    // ProgramPrimitive replaces Commit/Rollback on this final phase with the
    // successful MtpCompare completion predicate. Exactly one state action is
    // issued; an unconditional rollback-then-commit is forbidden.
    MicroOpTemplate(StateResolve, of(Stateful, Last), src0 = 2, src1 = 4, dst = 2, m = 0)
  )
}

class HeteroVisionPatchEmbedPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.VisionPatchEmbed, "HeteroVisionPatchEmbedPrimitiveV3")
class HeteroVisionTransformerBlockPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.VisionTransformerBlock, "HeteroVisionTransformerBlockPrimitiveV3")
class HeteroVisionPatchMergePrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.VisionPatchMerge, "HeteroVisionPatchMergePrimitiveV3")
class HeteroMultimodalInjectPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.MultimodalInject, "HeteroMultimodalInjectPrimitiveV3")
class HeteroFinalNormPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.FinalNorm, "HeteroFinalNormPrimitiveV3")
class HeteroLmHeadArgmaxPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.LmHeadArgmax, "HeteroLmHeadArgmaxPrimitiveV3")
class HeteroMtpDraftPrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.MtpDraft, "HeteroMtpDraftPrimitiveV3")
class HeteroMtpVerifyResolvePrimitiveV3
  extends ProgramPrimitive(VisionAndBoundaryPrograms.MtpVerifyResolve,
    "HeteroMtpVerifyResolvePrimitiveV3", conditionalResolvePhase = Some(3))
