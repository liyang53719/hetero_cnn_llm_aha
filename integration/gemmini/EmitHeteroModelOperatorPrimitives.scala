package gemmini

import chisel3.RawModule
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Path, Paths}

object EmitHeteroModelOperatorPrimitives extends App {
  require(args.length == 1, "expected output directory")
  val outputDirectory: Path = Paths.get(args(0))
  Files.createDirectories(outputDirectory)
  val roots: Seq[(String, () => RawModule)] = Seq(
    "HeteroStableTopK" -> (() => new HeteroStableTopK(maxK = 512, indexBits = 16)),
    "HeteroStableIndexSorter" -> (() => new HeteroStableIndexSorter(maxItems = 512, indexBits = 16)),
    "HeteroStableArgmax" -> (() => new HeteroStableArgmax(indexBits = 20)),
    "HeteroSparseGatherRunCoalescer" -> (() => new HeteroSparseGatherRunCoalescer()),
    "HeteroMtpVerifyCommit" -> (() => new HeteroMtpVerifyCommit()),
    "HeteroGdnOperatorPrimitive" -> (() => new HeteroGdnOperatorPrimitive()),
    "HeteroMoeOperatorPrimitive" -> (() => new HeteroMoeOperatorPrimitive()),
    "HeteroMoeDispatchPlanner" -> (() => new HeteroMoeDispatchPlanner()),
    "HeteroNgramHash" -> (() => new HeteroNgramHash()),
    "HeteroBilinearPositionPlanner" -> (() => new HeteroBilinearPositionPlanner()),
    "HeteroSpatialMergeAddressGenerator" -> (() => new HeteroSpatialMergeAddressGenerator()),
    "HeteroGatedResidualOperatorPrimitive" -> (() => new HeteroGatedResidualOperatorPrimitive()),
    "HeteroPleOperatorPrimitive" -> (() => new HeteroPleOperatorPrimitive()),
    "HeteroQsaOperatorPrimitive" -> (() => new HeteroQsaOperatorPrimitive()),
    "HeteroVisionPatchEmbedOperatorPrimitive" -> (() => new HeteroVisionPatchEmbedOperatorPrimitive()),
    "HeteroVisionTransformerBlockOperatorPrimitive" -> (() => new HeteroVisionTransformerBlockOperatorPrimitive()),
    "HeteroVisionPatchMergeOperatorPrimitive" -> (() => new HeteroVisionPatchMergeOperatorPrimitive()),
    "HeteroQwen2DecoderBlockOperatorPrimitive" -> (() => new HeteroQwen2DecoderBlockOperatorPrimitive()),
    "HeteroQwen35DenseAttentionOperatorPrimitive" -> (() => new HeteroQwen35DenseAttentionOperatorPrimitive()),
    "HeteroLanguageModelBoundaryOperatorPrimitive" -> (() => new HeteroLanguageModelBoundaryOperatorPrimitive()),
    "HeteroMtpDraftTargetOperatorPrimitive" -> (() => new HeteroMtpDraftTargetOperatorPrimitive()),
    "HeteroMtpStateAction" -> (() => new HeteroMtpStateAction()),
    "HeteroVisionEncoderLoopController" -> (() => new HeteroVisionEncoderLoopController()),
    "HeteroQwen35LayerController" -> (() => new HeteroQwen35LayerController()),
    "HeteroQwen38LayerController" -> (() => new HeteroQwen38LayerController())
  )
  roots.foreach { case (name, generator) =>
    val systemVerilog = ChiselStage.emitSystemVerilog(generator())
    Files.writeString(outputDirectory.resolve(s"$name.sv"), systemVerilog, StandardCharsets.UTF_8)
  }
  Files.writeString(outputDirectory.resolve("MANIFEST.txt"), roots.map(_._1).mkString("\n") + "\n", StandardCharsets.UTF_8)
}
