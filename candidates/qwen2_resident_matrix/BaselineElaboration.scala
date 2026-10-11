package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

object BaselineElaboration extends App {
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("fifo_default.fir"),ChiselStage.emitCHIRRTL(new MatrixResultFifo))
  Files.writeString(out.resolve("service_default.fir"),ChiselStage.emitCHIRRTL(new MatrixPipelineService))
}
