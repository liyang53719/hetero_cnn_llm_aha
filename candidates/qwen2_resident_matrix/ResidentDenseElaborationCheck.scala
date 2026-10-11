// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Compile separately with the source-bound optional read-hook patch applied.
  * Compare default/small CHIRRTL with ResidentDenseBaselineCheck after only
  * removing source-location annotations. Never invoke firtool or emit RTL.
  */
object ResidentDenseElaborationCheck extends App {
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("dense_default.fir"),ChiselStage.emitCHIRRTL(new StreamingDenseOwner))
  Files.writeString(out.resolve("dense_small.fir"),
    ChiselStage.emitCHIRRTL(new StreamingDenseOwner(maxK=1536,maxTokenTiles=1)))
  Files.writeString(out.resolve("dense_hook.fir"),
    ChiselStage.emitCHIRRTL(new StreamingDenseOwner(enableResidentReadHook=true)))
  Files.writeString(out.resolve("dense_hook_burst_writes.fir"),
    ChiselStage.emitCHIRRTL(new StreamingDenseOwner(burstWrites=true,enableResidentReadHook=true)))
  val rejected=scala.util.Try(ChiselStage.emitCHIRRTL(
    new StreamingDenseOwner(maxK=1536,maxTokenTiles=1,enableResidentReadHook=true)))
  require(rejected.isFailure,"source hook unexpectedly admitted absent A/C addresses")
  val reason=Iterator.iterate(rejected.failed.get)(_.getCause).takeWhile(_!=null).map(_.toString).mkString("\n")
  require(reason.contains("resident source hook requires all 1024 A/C addresses"),reason)
  Files.writeString(out.resolve("small_hook_rejected.txt"),reason+"\n")
  println("PASS: default-off, enabled ordinary/burst, and short-bank rejection frontend only")
}
