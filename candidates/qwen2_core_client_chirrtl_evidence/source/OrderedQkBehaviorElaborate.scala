// Explicit CHIRRTL-only structural stage; no firtool or SV emission here.
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths,StandardOpenOption}
object OrderedQkBehaviorElaborate extends App {
  require(args.length==2,"ordered 0|1 and fresh .fir output required")
  val selected=args(0) match {case "0"=>false;case "1"=>true;case _=>throw new IllegalArgumentException("ordered 0|1")}
  val out=Paths.get(args(1));require(!Files.exists(out),"do not overwrite evidence")
  val circuit=ChiselStage.emitCHIRRTL(new OrderedQkBehaviorCore(selected))
  Files.writeString(out,circuit,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
  println(s"CORE_CHIRRTL_ONLY ordered=$selected bytes=${Files.size(out)} no_sv_emitter=true")
}
