// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

/** Bounded leaf-only elaboration. Never selects or emits the original Top. */
object EmitGdnExecute32Chirrtl extends App {
  require(args.length == 1, "one output directory required")
  val text = circt.stage.ChiselStage.emitCHIRRTL(
    new GdnRuntimeChunkExecuteOwner32V1,
    Array.empty[String])
  java.nio.file.Files.write(java.nio.file.Paths.get(args(0), "GdnRuntimeChunkExecuteOwner32V1.fir"), text.getBytes("UTF-8"))
}
