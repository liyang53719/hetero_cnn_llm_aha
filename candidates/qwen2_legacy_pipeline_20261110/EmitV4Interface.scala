import heteronpu.continuous._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
object EmitV4Interface extends App {
 val shape=QwenBlockShape(retainedMatrix=true,matrixColumns=256)
 Files.writeString(Paths.get(args(0)),ChiselStage.emitCHIRRTL(new HostBlockTopV4(shape,weightReadBeats=16,pipelined=true)))
}
