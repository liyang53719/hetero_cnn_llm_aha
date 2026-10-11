// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Compile this file with the unmodified production StreamingDense.scala.
  * Deliberately does not mention any candidate parameter or type.
  */
object ResidentDenseBaselineCheck extends App {
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("dense_default.fir"),ChiselStage.emitCHIRRTL(new StreamingDenseOwner))
  Files.writeString(out.resolve("dense_small.fir"),
    ChiselStage.emitCHIRRTL(new StreamingDenseOwner(maxK=1536,maxTokenTiles=1)))
  println("PASS: original StreamingDense default/small frontend only")
}
