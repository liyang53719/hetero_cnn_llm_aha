// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

/** Emits frontend CHIRRTL only. No firtool, SystemVerilog or simulation. */
object AHoldElaborate extends App {
  require(args.length==1,"AHoldElaborate requires a fresh output directory")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  for(reuse<-Seq(false,true);full<-Seq(false,true)) {
    val owner=()=>new TransposedDenseDownOwner(
      burstWrites=full,enableFfnTiles=full,enableFfnWindow=full,
      enableFfnDrain=full,enableKWindow=full,enableDenseDrain=full,
      enableRawKv=full,enableAHold=reuse)
    Files.writeString(out.resolve(s"owner_hold${if(reuse)1 else 0}_full${if(full)1 else 0}.fir"),
      ChiselStage.emitCHIRRTL(owner()))
  }
}

