// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

object EmitP0Safety extends App {
  val out = if(args.nonEmpty) args(0) else "generated"
  Files.createDirectories(Paths.get(out))
  ChiselStage.emitSystemVerilogFile(new P0AllRoots(LocalSramConfig()),
    args = Array("--target-dir",out),
    firtoolOpts = Array("--disable-all-randomization","--strip-debug-info","--split-verilog"))
  println("P0_CHISEL_EMISSION_DONE roots=4 local_sram_bytes=1572864 nominal_hz=800000000")
}
