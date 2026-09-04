package gemmini

import chisel3.RawModule
import chisel3.{ActualDirection, DontCare, Module, dontTouch}
import circt.stage.ChiselStage
import chisel3.reflect.DataMirror
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

/** Single source of truth for local-agent RTL elaboration.  Each key emits one
  * synthesizable module and never elaborates Rocket/Chipyard.
  */
object HeteroOperatorPrimitiveCatalog {
  val names: Seq[String] = Seq(
    "unsigned_divide",
    "unsigned_multiply",
    "streaming_topk",
    "tagged_gather_reorder",
    "moe_route_dispatch",
    "ple_ngram_hash",
    "qsa_block_selector",
    "causal_conv_address",
    "gdn_state_address",
    "norm_address",
    "gated_residual_address",
    "state_transaction",
    "mtp_verify",
    "composite_activation",
    "primitive_capability_decode",
    "primitive_leaf_expander",
    "terminal_model_operator_frontend",
    "fp32_pwl_segment_search",
    "block_pool_address",
    "mrope_section_map",
    "vision_window_address",
    "vision_patch_merge_address",
    "vision_bilinear_index",
    "vision_patch3d_address",
    "model_operator_sequencer"
  )

  def generator(name: String): RawModule = name match {
    case "unsigned_divide" => new HeteroUnsignedDivide(64)
    case "unsigned_multiply" => new HeteroUnsignedMultiply(32)
    case "streaming_topk" => new HeteroStreamingTopK(512, 32, 20)
    case "tagged_gather_reorder" => new HeteroTaggedGatherReorder(32, 64, 512, 32, 16)
    case "moe_route_dispatch" => new HeteroMoeRouteDispatch(16, 32, 10, 32, 512)
    case "ple_ngram_hash" => new HeteroPleNgramHash(16, 3, 32, 32, 32)
    case "qsa_block_selector" => new HeteroQsaBlockSelector(512, 20, 32, 5)
    case "causal_conv_address" => new HeteroCausalConvAddressGenerator(16384, 8, 8, 64, 32)
    case "gdn_state_address" => new HeteroGdnStateAddressGenerator(64, 256, 64)
    case "norm_address" => new HeteroNormAddressGenerator(8, 16384, 64)
    case "gated_residual_address" => new HeteroGatedResidualAddressGenerator(8, 16384, 32)
    case "state_transaction" => new HeteroStateTransaction(16, 16, 16)
    case "mtp_verify" => new HeteroMtpVerify(32, 32)
    case "composite_activation" => new HeteroCompositeActivationSequencer
    case "primitive_capability_decode" => new HeteroPrimitiveCapabilityDecode
    case "primitive_leaf_expander" => new HeteroPrimitiveLeafExpander
    case "terminal_model_operator_frontend" => new HeteroTerminalModelOperatorFrontend
    case "fp32_pwl_segment_search" => new HeteroFp32PwlSegmentSearch(64)
    case "block_pool_address" => new HeteroBlockPoolAddressGenerator(262144, 16, 256)
    case "mrope_section_map" => new HeteroMropeSectionMap(256)
    case "vision_window_address" => new HeteroVisionWindowAddressGenerator(4096, 1 << 24)
    case "vision_patch_merge_address" => new HeteroVisionPatchMergeAddressGenerator(4096, 8, 1 << 24)
    case "vision_bilinear_index" => new HeteroVisionBilinearIndex(24, 16)
    case "vision_patch3d_address" => new HeteroVisionPatch3dAddressGenerator(4096, 8, 16)
    case "model_operator_sequencer" => new HeteroModelOperatorSequencer
    case other => throw new IllegalArgumentException(s"unknown operator primitive: $other")
  }
}

object EmitHeteroOperatorPrimitiveCatalog extends App {
  if (args.length == 1 && args(0) == "--list") {
    HeteroOperatorPrimitiveCatalog.names.foreach(println)
  } else {
    require(args.length == 2, "usage: <primitive-name> <output-systemverilog-path> or --list")
    require(HeteroOperatorPrimitiveCatalog.names.contains(args(0)), s"unknown primitive ${args(0)}")
    val output = Paths.get(args(1))
    val systemVerilog = ChiselStage.emitSystemVerilog(HeteroOperatorPrimitiveCatalog.generator(args(0))).stripTrailing + "\n"
    Option(output.getParent).foreach(parent => Files.createDirectories(parent))
    Files.writeString(output, systemVerilog, StandardCharsets.UTF_8)
  }
}

/** Emits the complete catalog in one hierarchy so shared helper modules are
  * defined once. This top is a generation/collision target; the endpoint-bound
  * functional shell is built after protocol binding.
  */
class HeteroOperatorPrimitiveCatalogCombined extends Module {
  HeteroOperatorPrimitiveCatalog.names.foreach { name =>
    val child = Module(HeteroOperatorPrimitiveCatalog.generator(name))
    DataMirror.modulePorts(child).foreach { case (_, port) =>
      DataMirror.getLeafs(port).foreach { leaf =>
        DataMirror.directionOf(leaf) match {
          case ActualDirection.Input => leaf := DontCare
          case ActualDirection.Output => dontTouch(leaf)
          case _ =>
        }
      }
    }
  }
}

object EmitHeteroOperatorPrimitiveCombined extends App {
  require(args.length == 1, "usage: <output-systemverilog-path>")
  val output = Paths.get(args(0))
  val systemVerilog = ChiselStage.emitSystemVerilog(new HeteroOperatorPrimitiveCatalogCombined).stripTrailing + "\n"
  Option(output.getParent).foreach(parent => Files.createDirectories(parent))
  Files.writeString(output, systemVerilog, StandardCharsets.UTF_8)
}
