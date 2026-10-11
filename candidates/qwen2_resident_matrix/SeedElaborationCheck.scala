package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class SeedPortShapeCheck extends Module {
  val io=IO(Input(new MatrixAccumulatorSeedPort))
  require(io.begin.bits.getWidth==107)
  require(io.beat.bits.getWidth==621)
  require(io.ack.bits.getWidth==100)
  require(io.beat.bits.data.getWidth==512)
}

object SeedElaborationCheck extends App {
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("seed_port.fir"),ChiselStage.emitCHIRRTL(new SeedPortShapeCheck))
  Files.writeString(out.resolve("seed_controller.fir"),ChiselStage.emitCHIRRTL(new MatrixAccumulatorSeedController))
  println("PASS: seed controller source elaboration only; no array connection, RTL or arithmetic execution")
}
