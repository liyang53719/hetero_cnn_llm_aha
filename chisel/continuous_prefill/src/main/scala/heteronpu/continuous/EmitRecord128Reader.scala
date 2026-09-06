// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

object EmitRecord128Reader extends App {
  require(args.length==1,"new output directory required")
  val out=Paths.get(args(0));require(!Files.exists(out),"preserve previous generated outputs")
  Files.createDirectories(out)
  Files.writeString(out.resolve("Record128IdmaTop.sv"),ChiselStage.emitSystemVerilog(new Record128IdmaTop,
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
}
