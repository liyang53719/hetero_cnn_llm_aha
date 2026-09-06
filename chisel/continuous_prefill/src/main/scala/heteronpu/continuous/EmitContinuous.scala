// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
import java.nio.charset.StandardCharsets
import heteronpu.p0.LocalSramConfig
object EmitContinuous extends App {
  require(args.length==1,"output directory is required")
  val dir=Paths.get(args(0));require(!Files.exists(dir),"preserve earlier generated outputs")
  Files.createDirectories(dir)
  val small=args(0).contains("_ci")
  val cfg=ChainConfig()
  val sram=if(small)LocalSramConfig(rowsPerBank=cfg.localBytes/256) else LocalSramConfig()
  Files.writeString(dir.resolve("ContinuousElementwiseTop.sv"),ChiselStage.emitSystemVerilog(new ContinuousElementwiseTop(cfg,sram),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")),StandardCharsets.UTF_8)
  Files.writeString(dir.resolve("DenseTileCursor.sv"),ChiselStage.emitSystemVerilog(new DenseTileCursor(),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")),StandardCharsets.UTF_8)
  Files.writeString(dir.resolve("CONFIG.txt"),s"clock_target_hz=800000000\ntile_elements=${cfg.tileElements}\nfabric_bytes=${sram.bytes}\nactive_tile_bytes=${cfg.localBytes}\nfull_model=false\n")
}
