package gemmini

/** Pure-Scala structural checks that run before CIRCT emission. */
object HeteroModelOperatorProgramChecksV2 extends App {
  import HeteroPrimitiveCode._

  private val programs: Seq[(String, Seq[HeteroMicroInstruction])] = Seq(
    "qwen2_decoder" -> HeteroQwen2DecoderBlockProgramV2.program,
    "qwen35_dense_attention" -> HeteroQwen35DenseAttentionProgramV2.program,
    "gdn" -> HeteroGdnProgramV2.program,
    "moe" -> HeteroMoeProgramV2.program,
    "gated_residual" -> HeteroGatedResidualProgramV2.program,
    "ple" -> HeteroPleProgramV2.program,
    "qsa" -> HeteroQsaProgramV2.program,
    "vision_patch" -> HeteroVisionPatchProgramV2.program,
    "vision_block" -> HeteroVisionBlockProgramV2.program,
    "vision_merge" -> HeteroVisionMergeProgramV2.program,
    "language_boundary" -> HeteroLanguageModelBoundaryProgramV2.program,
    "mtp_draft_target" -> HeteroMtpDraftTargetProgramV2.program
  )

  private def ordered(program: Seq[HeteroMicroInstruction], required: Seq[Int]): Boolean = {
    var cursor = 0
    program.foreach { instruction =>
      if (cursor < required.length && instruction.kind == required(cursor)) cursor += 1
    }
    cursor == required.length
  }

  programs.foreach { case (name, program) =>
    require(program.nonEmpty, s"$name program is empty")
    require(program.map(_.phase) == program.indices.toSeq, s"$name phases are not dense/monotonic")
    require(program.forall(x => Seq(x.src0, x.src1, x.src2, x.dst).forall(v => v >= 0 && v < 16)), s"$name descriptor slot overflow")
    require(program.forall(x => Seq(x.m, x.n, x.k).forall(v => v >= 0 && v < 8)), s"$name dimension slot overflow")
    require(program.forall(x => x.index0 >= 0 && x.index0 < 65536 && x.index1 >= 0 && x.index1 < 65536), s"$name index literal overflow")
  }

  require(ordered(HeteroMoeProgramV2.program, Seq(StableTopK, OnlineSoftmax, VectorScatter)),
    "MoE selected logits must be normalized before dispatch")
  require(!HeteroGatedResidualProgramV2.program.exists(_.kind == Silu),
    "gated residual read/inject gates use sigmoid, not SiLU")
  require(HeteroGatedResidualProgramV2.program.count(_.kind == Sigmoid) >= 2,
    "gated residual requires read and inject sigmoid stages")
  require(HeteroGdnProgramV2.program.count(_.kind == Exp2) >= 2,
    "GDN natural-exp decay requires two exp2-based stages")
  require(HeteroGdnProgramV2.program.count(_.kind == StateRead) >= 2,
    "GDN requires causal-conv and recurrent-state reads")
  require(HeteroGdnProgramV2.program.count(_.kind == MatrixGemv) >= 2,
    "GDN requires memory and query state reads")
  require(HeteroGdnProgramV2.program.exists(_.kind == MatrixOuter),
    "GDN requires rank-1 recurrent-state update")
  require(ordered(HeteroQsaProgramV2.program, Seq(
    ReduceSum, Reciprocal, VectorMul, L2Norm, MatrixQk,
    VectorCompare, VectorSelect, ReduceSum, Rsqrt, VectorMul,
    StableTopK, VectorGather, StableSort, SparseGatherRun, KvGather
  )), "QSA block-selection algebra is incomplete")

  require(HeteroThreeModelOperatorCatalogV2.qwen2.nonEmpty)
  require(HeteroThreeModelOperatorCatalogV2.qwen35.nonEmpty)
  require(HeteroThreeModelOperatorCatalogV2.qwen38.nonEmpty)
  require(HeteroThreeModelOperatorCatalogV2.all.map(x => (x.model, x.operator)).distinct.size == HeteroThreeModelOperatorCatalogV2.all.size)

  println(s"PASS_MODEL_OPERATOR_PROGRAM_CHECKS_V2 programs=${programs.size} bindings=${HeteroThreeModelOperatorCatalogV2.all.size}")
}
