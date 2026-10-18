// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import _root_.circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, LinkOption, Paths, StandardOpenOption}

/** New derived Host-only emitter. It does not restore the lost historical 95-source identity.
  * One elaboration gives the original Host and four FMA providers one common namespace.
  * HostBlockTop, not HostBlockCollection or any Kernel Bench, is the later execution top.
  * This entry point emits CHIRRTL only. It launches no job and invokes no firtool.
  */
object EmitCanonicalHost93 extends App {
  require(args.length == 1, "one fresh absolute CHIRRTL directory required")
  val out = Paths.get(args(0)).normalize()
  require(out.isAbsolute && !Files.exists(out, LinkOption.NOFOLLOW_LINKS), "fresh absolute output")
  require(Files.isDirectory(out.getParent, LinkOption.NOFOLLOW_LINKS), "existing output parent")
  val shape = QwenBlockShape(hidden=1536, ffn=8960, heads=12, kvHeads=2, headDim=128,
    maxTokens=1024, retainedMatrix=true, matrixColumns=256)
  println("CANONICAL_HOST93_CHIRRTL_BEGIN new_derived_source_identity=1 actual_job=none")
  val ir = ChiselStage.emitCHIRRTL(new HostBlockCollection(shape, weightReadBeats=16,
    pipelined=true, burstWrites=true, commitTailRead=false, overlapSilu=false,
    enableTransposedDown=true, enableResidentFfn=true, enablePublic21QkvReduction=true,
    numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2, enableProductionPackedQk16=true))
  val bytes = ir.getBytes(StandardCharsets.UTF_8)
  require(bytes.length <= 48*1024*1024, "48 MiB CHIRRTL cap")
  require("(?m)^circuit HostBlockCollection\\s*:".r.findFirstIn(ir).nonEmpty,
    "original common-namespace collection required")
  for (name <- Seq("HostBlockTop", "HeteroBF16FmaPre", "HeteroBF16FmaMul",
                   "HeteroBF16FmaPost", "HeteroBF16FmaRound")) {
    require(("(?m)^  module " + name + "\\s*:").r.findFirstIn(ir).nonEmpty,
      "missing original Host/provider definition: " + name)
  }
  Files.createDirectory(out)
  Files.write(out.resolve("HostBlockCollection.fir"), bytes, StandardOpenOption.CREATE_NEW)
  println(s"CANONICAL_HOST93_CHIRRTL_WRITTEN bytes=${bytes.length} execution_top=HostBlockTop")
}
