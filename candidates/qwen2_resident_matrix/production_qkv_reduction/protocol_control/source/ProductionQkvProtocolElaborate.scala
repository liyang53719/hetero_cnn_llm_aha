// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
object ProductionQkvProtocolElaborate extends App {
  require(args.length==1,"one fresh structure output directory required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("protocol.fir"),ChiselStage.emitCHIRRTL(new ProductionQkvProtocolHarness))
}
