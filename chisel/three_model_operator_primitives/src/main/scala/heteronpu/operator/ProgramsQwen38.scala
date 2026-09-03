package heteronpu.operator

import PrimitiveFlags._
import PrimitiveKind._

/** Qwen3.8-Flash-Next-only primitives: four-stream hyper connections, PLE,
  * QSA and the final hyper-stream merge.
  */
object Qwen38Programs {
  /** Read side of a four-branch gated residual/hyper connection.
    *
    * This is intentionally independent from the write side so Attention and
    * MoE can launch, checkpoint and rollback their stream transactions
    * separately.  It includes the complete learned gate path:
    * group RMSNorm -> low-rank down -> 1/branches scale -> SiLU -> up ->
    * sigmoid -> branch weighted sum -> average.
    */
  val GatedResidualRead: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(StateRead, Stateful, src0 = 0, dst = 4, m = 0, n = 1, k = 2),
    MicroOpTemplate(GroupRmsNorm, src0 = 4, src1 = 1, dst = 5, m = 0, n = 1, k = 2),
    MicroOpTemplate(LayoutTransform, src0 = 5, dst = 5, m = 0, n = 1, k = 2, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 5, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 0),
    MicroOpTemplate(Reciprocal, src0 = 14, dst = 7, k = 2, index0 = 0),
    MicroOpTemplate(VectorMul, src0 = 6, src1 = 7, dst = 6, m = 0, n = 3),
    MicroOpTemplate(Silu, src0 = 6, dst = 6, m = 0, n = 3),
    MicroOpTemplate(MatrixGemm, src0 = 6, src1 = 3, dst = 7, m = 0, n = 2, k = 3, index0 = 1),
    MicroOpTemplate(Sigmoid, src0 = 7, dst = 7, m = 0, n = 2),
    MicroOpTemplate(VectorMul, src0 = 5, src1 = 7, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(ReduceSum, src0 = 8, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(Reciprocal, src0 = 14, dst = 7, k = 2, index0 = 1),
    MicroOpTemplate(VectorMul, Last, src0 = 8, src1 = 7, dst = 9, m = 0, n = 1)
  )

  /** Write/inject side of one hyper connection.
    * inject_b = stream_b + block * (2 * sigmoid(up(SiLU(down(norm(stream))/B))))
    */
  val GatedResidualWrite: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(StateRead, Stateful, src0 = 0, dst = 4, m = 0, n = 1, k = 2),
    MicroOpTemplate(GroupRmsNorm, src0 = 4, src1 = 1, dst = 5, m = 0, n = 1, k = 2),
    MicroOpTemplate(LayoutTransform, src0 = 5, dst = 5, m = 0, n = 1, k = 2, index0 = 1),
    MicroOpTemplate(MatrixGemm, src0 = 5, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 0),
    MicroOpTemplate(Reciprocal, src0 = 14, dst = 7, k = 2, index0 = 0),
    MicroOpTemplate(VectorMul, src0 = 6, src1 = 7, dst = 6, m = 0, n = 3),
    MicroOpTemplate(Silu, src0 = 6, dst = 6, m = 0, n = 3),
    MicroOpTemplate(MatrixGemm, src0 = 6, src1 = 3, dst = 7, m = 0, n = 2, k = 3, index0 = 1),
    MicroOpTemplate(Sigmoid, src0 = 7, dst = 7, m = 0, n = 2),
    MicroOpTemplate(VectorMul, src0 = 7, src1 = 14, dst = 7, m = 0, n = 2, index0 = 2),
    MicroOpTemplate(VectorBroadcast, Broadcast, src0 = 8, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(VectorMul, src0 = 8, src1 = 7, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(VectorAdd, Stateful, src0 = 4, src1 = 8, dst = 9, m = 0, n = 1, k = 2),
    MicroOpTemplate(StateWrite, Stateful, src0 = 9, dst = 0, m = 0, n = 1, k = 2),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Per-Layer Embedding path with EOS-aware n-gram history, sparse row
    * retrieval, learned key/value gating and an independent dilated causal
    * depthwise-convolution state.
    */
  val Ple: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(StateRead, Stateful, src0 = 0, dst = 8, m = 3),
    MicroOpTemplate(VectorCompare, src0 = 8, src1 = 14, dst = 9, m = 0, index0 = 0),
    MicroOpTemplate(VectorSelect, src0 = 9, src1 = 8, src2 = 14, dst = 8, m = 0, n = 3, index0 = 0),
    MicroOpTemplate(NgramHash, src0 = 8, src1 = 1, dst = 9, m = 0, n = 3, k = 4),
    MicroOpTemplate(DmaRead, Sparse, src0 = 2, src1 = 9, src2 = 14, dst = 10, m = 0, n = 4, k = 5),
    MicroOpTemplate(EmbeddingLookup, Sparse, src0 = 10, src1 = 9, dst = 10, m = 0, n = 4, k = 5),
    MicroOpTemplate(MatrixGemm, src0 = 10, src1 = 3, dst = 11, m = 0, n = 1, k = 5, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 10, src1 = 4, dst = 12, m = 0, n = 1, k = 5, index0 = 1),
    MicroOpTemplate(GroupRmsNorm, src0 = 11, src1 = 14, dst = 11, m = 0, n = 1, k = 2, index0 = 0),
    MicroOpTemplate(GroupRmsNorm, src0 = 5, src1 = 14, dst = 13, m = 0, n = 1, k = 2, index0 = 1),
    MicroOpTemplate(MatrixQk, src0 = 13, src1 = 11, dst = 13, m = 2, n = 0, k = 1),
    MicroOpTemplate(Rsqrt, src0 = 14, dst = 9, k = 1, index0 = 1),
    MicroOpTemplate(VectorMul, src0 = 13, src1 = 9, dst = 13, m = 0, n = 2),
    MicroOpTemplate(SignedSqrt, src0 = 13, dst = 13, m = 0, n = 2),
    MicroOpTemplate(Sigmoid, src0 = 13, dst = 13, m = 0, n = 2),
    MicroOpTemplate(VectorMul, src0 = 12, src1 = 13, dst = 12, m = 0, n = 1, k = 2),
    MicroOpTemplate(GroupRmsNorm, src0 = 12, src1 = 14, dst = 12, m = 0, n = 1, k = 2, index0 = 2),
    MicroOpTemplate(StateRead, Stateful, src0 = 6, dst = 13, n = 1, k = 6),
    MicroOpTemplate(DepthwiseConv, of(Stateful, Causal), src0 = 12, src1 = 7, src2 = 13, dst = 13, m = 0, n = 1, k = 6, index0 = 3),
    MicroOpTemplate(StateWrite, Stateful, src0 = 13, dst = 6, n = 1, k = 6),
    MicroOpTemplate(VectorAdd, src0 = 12, src1 = 13, dst = 12, m = 0, n = 1),
    MicroOpTemplate(StateWrite, Stateful, src0 = 8, dst = 0, m = 3),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Qwen Sparse Attention selection and sparse attention payload.
    *
    * Index keys are compressed in groups, averaged, normalized and compared
    * with normalized index queries.  Scores are clamped non-negative, reduced
    * across index heads and scaled before stable Top-K.  Selected tokens are
    * expanded, sorted and coalesced before sparse KV gather.  No full score
    * matrix is required.
    */
  val Qsa: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 1, dst = 8, m = 0, n = 2, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 1, dst = 9, m = 0, n = 2, k = 1, index0 = 1),
    MicroOpTemplate(L2Norm, src0 = 8, dst = 8, m = 0, n = 2, k = 3),
    MicroOpTemplate(L2Norm, src0 = 9, dst = 9, m = 0, n = 2, k = 3),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 8, src1 = 14, dst = 8, m = 0, n = 2, k = 3),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 9, src1 = 14, dst = 9, m = 0, n = 2, k = 3),
    MicroOpTemplate(StateWrite, Stateful, src0 = 9, dst = 2, m = 0, n = 3),
    MicroOpTemplate(ReduceSum, src0 = 2, dst = 10, m = 0, n = 3, index0 = 4),
    MicroOpTemplate(Reciprocal, src0 = 14, dst = 11, index0 = 4),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 11, dst = 10, m = 0, n = 3),
    MicroOpTemplate(L2Norm, src0 = 10, dst = 10, m = 0, n = 3),
    MicroOpTemplate(MatrixQk, src0 = 8, src1 = 10, dst = 10, m = 2, n = 0, k = 3),
    MicroOpTemplate(VectorCompare, src0 = 10, src1 = 14, dst = 11, index0 = 5),
    MicroOpTemplate(VectorSelect, src0 = 11, src1 = 10, src2 = 14, dst = 10, index0 = 5),
    MicroOpTemplate(ReduceSum, src0 = 10, dst = 10, m = 0, n = 0, k = 2),
    MicroOpTemplate(Rsqrt, src0 = 14, dst = 11, k = 3, index0 = 6),
    MicroOpTemplate(VectorMul, src0 = 10, src1 = 11, dst = 10, m = 0, n = 0),
    MicroOpTemplate(StableTopK, src0 = 10, dst = 3, m = 0, n = 7, index0 = 5),
    MicroOpTemplate(VectorGather, Sparse, src0 = 2, src1 = 3, dst = 3, m = 0, n = 7, index0 = 4),
    MicroOpTemplate(StableSort, src0 = 3, dst = 3, m = 0, n = 7),
    MicroOpTemplate(SparseGatherRun, Sparse, src0 = 3, dst = 4, m = 0, n = 7, index0 = 4),
    MicroOpTemplate(KvGather, of(Stateful, Sparse), src0 = 5, src1 = 4, dst = 6, m = 0, n = 7, k = 6),
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 7, dst = 8, m = 0, n = 4, k = 1, index0 = 0),
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 7, dst = 9, m = 0, n = 5, k = 1, index0 = 1),
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 7, dst = 9, m = 0, n = 5, k = 1, index0 = 2),
    MicroOpTemplate(MatrixGemm, src0 = 0, src1 = 7, dst = 11, m = 0, n = 4, k = 1, index0 = 3),
    MicroOpTemplate(RmsNorm, src0 = 8, src1 = 14, dst = 8, m = 0, n = 4, k = 6, index0 = 0),
    MicroOpTemplate(RmsNorm, src0 = 9, src1 = 14, dst = 9, m = 0, n = 5, k = 6, index0 = 1),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 8, src1 = 14, dst = 8, m = 0, n = 4, k = 6),
    MicroOpTemplate(Rope, of(PartialRotary, MropeInterleaved), src0 = 9, src1 = 14, dst = 9, m = 0, n = 5, k = 6),
    MicroOpTemplate(KvAppend, Stateful, src0 = 9, dst = 5, m = 0, n = 5, k = 6),
    MicroOpTemplate(MatrixQk, of(Causal, Sparse, Gqa), src0 = 8, src1 = 6, dst = 12, m = 4, n = 7, k = 6),
    MicroOpTemplate(VectorMul, src0 = 12, src1 = 14, dst = 12, m = 4, n = 7, index0 = 2),
    MicroOpTemplate(ApplyMask, of(Causal, Sparse), src0 = 12, src1 = 6, dst = 12, m = 0, n = 7),
    MicroOpTemplate(OnlineSoftmax, of(Causal, Sparse), src0 = 12, src1 = 6, dst = 12, m = 4, n = 7, k = 6),
    MicroOpTemplate(MatrixPv, of(Sparse, Gqa), src0 = 12, src1 = 6, dst = 12, m = 4, n = 6, k = 7),
    MicroOpTemplate(Sigmoid, src0 = 11, dst = 11, m = 0, n = 4, k = 6),
    MicroOpTemplate(VectorMul, src0 = 12, src1 = 11, dst = 12, m = 0, n = 4, k = 6),
    MicroOpTemplate(MatrixGemm, src0 = 12, src1 = 13, dst = 12, m = 0, n = 1, k = 4, index0 = 4),
    MicroOpTemplate(StateCommit, of(Stateful, Commit, Last), src0 = 15, dst = 15)
  )

  /** Final four-stream merger used before the Qwen3.8 language head. */
  val FinalHyperMerge: Seq[MicroOpTemplate] = Seq(
    MicroOpTemplate(StateRead, Stateful, src0 = 0, dst = 4, m = 0, n = 1, k = 2),
    MicroOpTemplate(GroupRmsNorm, src0 = 4, src1 = 1, dst = 5, m = 0, n = 1, k = 2),
    MicroOpTemplate(LayoutTransform, src0 = 5, dst = 5, m = 0, n = 1, k = 2, index0 = 2),
    MicroOpTemplate(MatrixGemm, src0 = 5, src1 = 2, dst = 6, m = 0, n = 3, k = 1, index0 = 0),
    MicroOpTemplate(Silu, src0 = 6, dst = 6, m = 0, n = 3),
    MicroOpTemplate(MatrixGemm, src0 = 6, src1 = 3, dst = 7, m = 0, n = 2, k = 3, index0 = 1),
    MicroOpTemplate(Sigmoid, src0 = 7, dst = 7, m = 0, n = 2),
    MicroOpTemplate(VectorMul, src0 = 5, src1 = 7, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(ReduceSum, src0 = 8, dst = 8, m = 0, n = 1, k = 2),
    MicroOpTemplate(RmsNorm, Last, src0 = 8, src1 = 14, dst = 9, m = 0, n = 1)
  )
}

class HeteroQwen38GatedResidualReadPrimitiveV3
  extends ProgramPrimitive(Qwen38Programs.GatedResidualRead, "HeteroQwen38GatedResidualReadPrimitiveV3")
class HeteroQwen38GatedResidualWritePrimitiveV3
  extends ProgramPrimitive(Qwen38Programs.GatedResidualWrite, "HeteroQwen38GatedResidualWritePrimitiveV3")
class HeteroPlePrimitiveV3
  extends ProgramPrimitive(Qwen38Programs.Ple, "HeteroPlePrimitiveV3")
class HeteroQsaPrimitiveV3
  extends ProgramPrimitive(Qwen38Programs.Qsa, "HeteroQsaPrimitiveV3")
class HeteroQwen38FinalHyperMergePrimitiveV3
  extends ProgramPrimitive(Qwen38Programs.FinalHyperMerge, "HeteroQwen38FinalHyperMergePrimitiveV3")
