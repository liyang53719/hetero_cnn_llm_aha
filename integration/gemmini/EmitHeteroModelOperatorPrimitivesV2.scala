package gemmini

import chisel3.RawModule
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}

/** Emits one collision-free SystemVerilog file per canonical V2 operator root. */
object EmitHeteroModelOperatorPrimitivesV2 extends App {
  require(args.length == 1, "expected output directory")
  val outputDirectory: Path = Paths.get(args(0))
  Files.createDirectories(outputDirectory)

  val roots: Seq[(String, () => RawModule)] = Seq(
    "HeteroMoeStableTopKV2" -> (() => new HeteroMoeStableTopKV2),
    "HeteroQsaStableTopKV2" -> (() => new HeteroQsaStableTopKV2),
    "HeteroQsaStableIndexSorterV2" -> (() => new HeteroQsaStableIndexSorterV2),
    "HeteroLanguageArgmaxV2" -> (() => new HeteroLanguageArgmaxV2),
    "HeteroSparseGatherRunCoalescer" -> (() => new HeteroSparseGatherRunCoalescer()),
    "HeteroMtpVerifyCommit" -> (() => new HeteroMtpVerifyCommit()),
    "HeteroMoeDispatchPlanner" -> (() => new HeteroMoeDispatchPlanner()),
    "HeteroNgramHash" -> (() => new HeteroNgramHash()),
    "HeteroBilinearPositionPlanner" -> (() => new HeteroBilinearPositionPlanner()),
    "HeteroSpatialMergeAddressGenerator" -> (() => new HeteroSpatialMergeAddressGenerator()),
    "HeteroQwen2DecoderBlockOperatorPrimitiveV2" -> (() => new HeteroQwen2DecoderBlockOperatorPrimitiveV2()),
    "HeteroQwen35DenseAttentionOperatorPrimitiveV2" -> (() => new HeteroQwen35DenseAttentionOperatorPrimitiveV2()),
    "HeteroGdnOperatorPrimitiveV2" -> (() => new HeteroGdnOperatorPrimitiveV2()),
    "HeteroMoeOperatorPrimitiveV2" -> (() => new HeteroMoeOperatorPrimitiveV2()),
    "HeteroGatedResidualOperatorPrimitiveV2" -> (() => new HeteroGatedResidualOperatorPrimitiveV2()),
    "HeteroPleOperatorPrimitiveV2" -> (() => new HeteroPleOperatorPrimitiveV2()),
    "HeteroQsaOperatorPrimitiveV2" -> (() => new HeteroQsaOperatorPrimitiveV2()),
    "HeteroVisionPatchEmbedOperatorPrimitiveV2" -> (() => new HeteroVisionPatchEmbedOperatorPrimitiveV2()),
    "HeteroVisionTransformerBlockOperatorPrimitiveV2" -> (() => new HeteroVisionTransformerBlockOperatorPrimitiveV2()),
    "HeteroVisionPatchMergeOperatorPrimitiveV2" -> (() => new HeteroVisionPatchMergeOperatorPrimitiveV2()),
    "HeteroLanguageModelBoundaryOperatorPrimitiveV2" -> (() => new HeteroLanguageModelBoundaryOperatorPrimitiveV2()),
    "HeteroMtpDraftTargetOperatorPrimitiveV2" -> (() => new HeteroMtpDraftTargetOperatorPrimitiveV2()),
    "HeteroMtpStateAction" -> (() => new HeteroMtpStateAction()),
    "HeteroVisionEncoderLoopController" -> (() => new HeteroVisionEncoderLoopController()),
    "HeteroQwen35LayerController" -> (() => new HeteroQwen35LayerController()),
    "HeteroQwen38LayerController" -> (() => new HeteroQwen38LayerController())
  )

  roots.foreach { case (name, generator) =>
    val systemVerilog = ChiselStage.emitSystemVerilog(generator())
    Files.writeString(
      outputDirectory.resolve(s"$name.sv"),
      systemVerilog,
      StandardCharsets.UTF_8
    )
  }

  Files.writeString(
    outputDirectory.resolve("MANIFEST.txt"),
    roots.map(_._1).mkString("\n") + "\n",
    StandardCharsets.UTF_8
  )

  val coverage = HeteroThreeModelOperatorCatalogV2.all
    .map(x => s"${x.model},${x.operator},${x.owner},${x.module}")
    .mkString("model,operator,owner,module\n", "\n", "\n")
  Files.writeString(
    outputDirectory.resolve("OPERATOR_COVERAGE.csv"),
    coverage,
    StandardCharsets.UTF_8
  )
}
