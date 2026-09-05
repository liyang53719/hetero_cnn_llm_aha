// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0
import chisel3.{RawModule, dontTouch}
import chisel3.reflect.DataMirror
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

object EmitP0Safety extends App {
  val out = if(args.nonEmpty) args(0) else "generated"
  Files.createDirectories(Paths.get(out))
  def design(): P0AllRoots = {
    val top = new P0AllRoots(LocalSramConfig())
    // These child modules are independently consumed as legacy scalar ABI roots.
    // Keep constant ports on the roots; do not post-process emitted SV or disable
    // optimization on the datapaths/memories.
    Seq[RawModule](top.root0, top.root1, top.root2, top.root3).foreach { root =>
      DataMirror.modulePorts(root).foreach { case (_, port) => dontTouch(port) }
    }
    top
  }
  ChiselStage.emitSystemVerilogFile(design(),
    args = Array("--target-dir",out),
    firtoolOpts = Array("--disable-all-randomization","--strip-debug-info"))
  println("P0_CHISEL_EMISSION_DONE roots=4 local_sram_bytes=1572864 nominal_hz=800000000")
}
