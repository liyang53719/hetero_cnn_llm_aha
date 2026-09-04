package heteronpu.operator

import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}

object ProgramValidation {
  import PrimitiveKind._

  def ordered(program: Seq[MicroOpTemplate], required: Seq[Int]): Boolean = {
    var cursor = 0
    program.foreach { op =>
      if (cursor < required.length && op.kind == required(cursor)) cursor += 1
    }
    cursor == required.length
  }

  def count(program: Seq[MicroOpTemplate], kind: Int): Int = program.count(_.kind == kind)

  def validate(): Unit = {
    val programs = ThreeModelOperatorCatalog.roots.map(r => r.name -> r.program)
    programs.foreach { case (name, program) =>
      require(program.nonEmpty, s"$name is empty")
      require(program.length <= 255, s"$name phase overflow")
      require((program.last.flags & PrimitiveFlags.Last) != 0, s"$name missing final Last")
      require(program.dropRight(1).forall(x => (x.flags & PrimitiveFlags.Last) == 0), s"$name early Last")
      require(program.forall(x => LeafCapabilities.supportedKinds.contains(x.kind)), s"$name uses unknown leaf")
    }

    require(ordered(TextPrograms.Qwen2DecoderBlock,
      Seq(RmsNorm, MatrixGemm, Rope, KvAppend, KvGather, MatrixQk,
        ApplyMask, OnlineSoftmax, MatrixPv, RmsNorm, MatrixGemm, Silu,
        VectorMul, MatrixGemm, VectorAdd)),
      "Qwen2 decoder algebra/order is incomplete")
    require(count(TextPrograms.Qwen2DecoderBlock, MatrixGemm) >= 7,
      "Qwen2 requires Q/K/V/O and Gate/Up/Down projections")
    require(count(TextPrograms.Qwen2DecoderBlock, Rope) == 2,
      "Qwen2 requires independent Q and K RoPE")

    require(ordered(TextPrograms.Qwen35DenseAttention,
      Seq(RmsNorm, MatrixGemm, RmsNorm, Rope, KvAppend, KvGather,
        MatrixQk, OnlineSoftmax, MatrixPv, Sigmoid, VectorMul, MatrixGemm, VectorAdd)),
      "Qwen3.5 dense-attention output-gate path is incomplete")
    require(count(TextPrograms.Qwen35DenseAttention, RmsNorm) >= 3,
      "Qwen3.5 dense attention requires input, Q and K normalization")
    require(TextPrograms.Qwen35DenseAttention.exists(x => x.kind == Rope &&
      (x.flags & PrimitiveFlags.PartialRotary) != 0 &&
      (x.flags & PrimitiveFlags.MropeInterleaved) != 0),
      "Qwen3.5 partial interleaved MRoPE is absent")

    require(ordered(TextPrograms.GatedDeltaNet,
      Seq(RmsNorm, MatrixGemm, StateRead, DepthwiseConv, StateWrite,
        L2Norm, Rsqrt, Softplus, Exp2, Exp2, Sigmoid, StateRead,
        MatrixGemv, VectorSub, MatrixOuter, MatrixGemv, RmsNorm,
        ConfiguredGateAct, VectorMul, MatrixGemm, StateWrite, StateCommit)),
      "Gated-DeltaNet recurrence is incomplete")
    require(count(TextPrograms.GatedDeltaNet, L2Norm) >= 2,
      "GDN requires Q and K L2 normalization")
    require(count(TextPrograms.GatedDeltaNet, Exp2) >= 2,
      "GDN natural-exp decay must use two exp2 stages")
    require(count(TextPrograms.GatedDeltaNet, MatrixGemv) >= 2,
      "GDN requires S^T*k and S^T*q")
    require(count(TextPrograms.GatedDeltaNet, MatrixOuter) == 1,
      "GDN requires exactly one rank-1 recurrent update")
    require(TextPrograms.GatedDeltaNet.exists(x => x.kind == ConfiguredGateAct &&
      (x.flags & PrimitiveFlags.Configurable) != 0),
      "GDN output gate must select SiLU/sigmoid at runtime")

    require(ordered(TextPrograms.Moe,
      Seq(RmsNorm, MatrixGemm, StableTopK, OnlineSoftmax, VectorScatter,
        DmaRead, MatrixGemm, Silu, VectorMul, MatrixGemm, VectorFma,
        DmaRead, MatrixGemm, Silu, VectorMul, MatrixGemm, Sigmoid,
        VectorMul, VectorAdd, VectorAdd)),
      "MoE routed/shared expert path is incomplete")
    require(TextPrograms.Moe.indexWhere(_.kind == StableTopK) <
      TextPrograms.Moe.indexWhere(_.kind == VectorScatter),
      "MoE dispatch must follow stable Top-K")
    require(TextPrograms.Moe.indexWhere(_.kind == OnlineSoftmax) <
      TextPrograms.Moe.indexWhere(_.kind == VectorScatter),
      "selected router logits must be normalized before dispatch")

    require(ordered(Qwen38Programs.GatedResidualRead,
      Seq(StateRead, GroupRmsNorm, LayoutTransform, MatrixGemm, Reciprocal,
        VectorMul, Silu, MatrixGemm, Sigmoid, VectorMul, ReduceSum,
        Reciprocal, VectorMul)),
      "Qwen3.8 hyper read low-rank gate chain is incomplete")
    require(ordered(Qwen38Programs.GatedResidualWrite,
      Seq(StateRead, GroupRmsNorm, MatrixGemm, Silu, MatrixGemm,
        Sigmoid, VectorBroadcast, VectorMul, VectorAdd, StateWrite, StateCommit)),
      "Qwen3.8 hyper write/inject chain is incomplete")
    require(Qwen38Programs.GatedResidualRead ne Qwen38Programs.GatedResidualWrite,
      "hyper read and write programs must be independently schedulable")

    require(ordered(Qwen38Programs.Ple,
      Seq(StateRead, VectorCompare, VectorSelect, NgramHash, DmaRead,
        EmbeddingLookup, MatrixGemm, GroupRmsNorm, MatrixQk, Rsqrt,
        SignedSqrt, Sigmoid, VectorMul, StateRead, DepthwiseConv,
        StateWrite, VectorAdd, StateWrite, StateCommit)),
      "PLE hash/fetch/gate/dilated-convolution path is incomplete")

    require(ordered(Qwen38Programs.Qsa,
      Seq(MatrixGemm, L2Norm, Rope, StateWrite, ReduceSum, Reciprocal,
        VectorMul, L2Norm, MatrixQk, VectorCompare, VectorSelect,
        ReduceSum, Rsqrt, VectorMul, StableTopK, VectorGather,
        StableSort, SparseGatherRun, KvGather, MatrixGemm, RmsNorm,
        Rope, KvAppend, MatrixQk, ApplyMask, OnlineSoftmax, MatrixPv,
        Sigmoid, VectorMul, MatrixGemm, StateCommit)),
      "QSA index selection and sparse-attention path is incomplete")
    require(Qwen38Programs.Qsa.exists(x => x.kind == StableTopK && x.index0 == 5),
      "QSA Top-512 policy selector is absent")
    require(Qwen38Programs.Qsa.exists(x => x.kind == MatrixQk &&
      (x.flags & PrimitiveFlags.Sparse) != 0), "QSA sparse QK is absent")

    require(ordered(VisionAndBoundaryPrograms.VisionTransformerBlock,
      Seq(LayerNorm, MatrixGemm, Rope, MatrixQk, ApplyMask,
        OnlineSoftmax, MatrixPv, MatrixGemm, VectorAdd, LayerNorm,
        MatrixGemm, Gelu, MatrixGemm, VectorAdd)),
      "vision transformer block is incomplete")
    require(VisionAndBoundaryPrograms.VisionTransformerBlock
      .filter(x => Seq(MatrixQk, OnlineSoftmax, MatrixPv).contains(x.kind))
      .forall(x => (x.flags & PrimitiveFlags.NonCausal) != 0),
      "vision attention must remain non-causal")

    require(ordered(VisionAndBoundaryPrograms.MtpVerifyResolve,
      Seq(MtpCompare, VectorCompare, VectorSelect, StateResolve)),
      "MTP verify/conditional-resolve transaction is incomplete")
    require(VisionAndBoundaryPrograms.MtpVerifyResolve.count(_.kind == StateResolve) == 1 &&
      !VisionAndBoundaryPrograms.MtpVerifyResolve.exists(_.kind == StateCommit),
      "MTP must issue exactly one dynamically selected commit/rollback phase")

    val tokenRoot = ThreeModelOperatorCatalog.all.find(_.operator == "token_embedding").map(_.root).get
    val headRoots = ThreeModelOperatorCatalog.all.filter(_.operator == "lm_head").map(_.root).toSet
    require(!headRoots.contains(tokenRoot), "input embedding and LM head must be separate launches")

    val q38ReadRoots = ThreeModelOperatorCatalog.qwen38
      .filter(_.operator.endsWith("hyper_state_read")).map(_.root).toSet
    val q38WriteRoots = ThreeModelOperatorCatalog.qwen38
      .filter(_.operator.endsWith("hyper_state_write")).map(_.root).toSet
    require(q38ReadRoots.intersect(q38WriteRoots).isEmpty,
      "Qwen3.8 hyper read and write must use separate roots")

    require(ThreeModelOperatorCatalog.qwen2.size == 30, "unexpected Qwen2 inventory count")
    require(ThreeModelOperatorCatalog.qwen35.size >= 90, "Qwen3.5 inventory is too coarse")
    require(ThreeModelOperatorCatalog.qwen38.size >= 140, "Qwen3.8 inventory is too coarse")

    Seq("qsa_stable_top512", "ple_ngram_hash", "final_hyper_weighted_reduce",
      "attention_hyper_lowrank_down", "moe_hyper_state_write").foreach { op =>
      require(ThreeModelOperatorCatalog.qwen38.exists(_.operator == op), s"missing Qwen3.8 operator $op")
    }
    Seq("gdn_outer_product_update", "moe_stable_top8",
      "attention_output_sigmoid_gate", "multimodal_token_scatter").foreach { op =>
      require(ThreeModelOperatorCatalog.qwen35.exists(_.operator == op), s"missing Qwen3.5 operator $op")
    }
  }
}

object OperatorProgramChecks extends App {
  ProgramValidation.validate()
  println(
    s"PASS_THREE_MODEL_OPERATOR_PROGRAMS roots=${ThreeModelOperatorCatalog.roots.size} " +
      s"qwen2=${ThreeModelOperatorCatalog.qwen2.size} " +
      s"qwen35=${ThreeModelOperatorCatalog.qwen35.size} " +
      s"qwen38=${ThreeModelOperatorCatalog.qwen38.size}"
  )
}

/** Emits one collision-free SystemVerilog file per independently schedulable
  * operator root.  The local-agent RTL stage uses this emitter verbatim.
  */
object EmitOperatorPrimitives extends App {
  require(args.length == 1, "expected output directory")
  ProgramValidation.validate()
  val outputDirectory: Path = Paths.get(args(0))
  Files.createDirectories(outputDirectory)

  ThreeModelOperatorCatalog.roots.foreach { root =>
    val sv = ChiselStage.emitSystemVerilog(root.generator()).stripTrailing + "\n"
    Files.writeString(outputDirectory.resolve(s"${root.name}.sv"), sv, StandardCharsets.UTF_8)
  }

  Files.writeString(
    outputDirectory.resolve("MANIFEST.txt"),
    ThreeModelOperatorCatalog.roots
      .map(r => s"${r.name},${r.program.size}")
      .mkString("root,phases\n", "\n", "\n"),
    StandardCharsets.UTF_8
  )
  Files.writeString(
    outputDirectory.resolve("OPERATOR_COVERAGE.csv"),
    ThreeModelOperatorCatalog.all
      .map(x => s"${x.model},${x.operator},${x.owner},${x.root}")
      .mkString("model,operator,owner,root\n", "\n", "\n"),
    StandardCharsets.UTF_8
  )
  Files.writeString(
    outputDirectory.resolve("SOURCE_GATE.txt"),
    s"status=PASS_CHISEL_OPERATOR_SOURCE_GATE\n" +
      s"target_clock_hz=800000000\n" +
      s"root_count=${ThreeModelOperatorCatalog.roots.size}\n" +
      s"binding_count=${ThreeModelOperatorCatalog.all.size}\n",
    StandardCharsets.UTF_8
  )
}
