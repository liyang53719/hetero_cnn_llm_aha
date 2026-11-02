// Tiny HOST-API/Boring diagnostic only: no original bank/owner, no B qualification.
package chiseltest.simulator.jna
import chisel3._
import chisel3.util.experimental.BoringUtils
import chiseltest.simulator.{Compiler,TopmoduleInfo,VerilatorBackendAnnotation,VerilatorCoverage}
import firrtl2.options.TargetDirAnnotation
import java.nio.file.{Files,Paths}
class Public21EmitApiProbeChild extends Module {
  val io=IO(new Bundle {val in=Input(UInt(32.W));val out=Output(UInt(32.W))})
  val observedRegister=RegNext(io.in,0.U(32.W));io.out:=observedRegister
}
class Public21EmitApiProbe extends Module {
  val io=IO(new Bundle {val in=Input(UInt(32.W));val out=Output(UInt(32.W));val observed=Output(UInt(32.W))})
  val child=Module(new Public21EmitApiProbeChild);child.io.in:=io.in;io.out:=child.io.out
  val sink=WireDefault(0.U(32.W));BoringUtils.addSource(child.observedRegister,"b_emit_api_probe");BoringUtils.addSink(sink,"b_emit_api_probe");io.observed:=sink
}
object Public21EmitApiProbeMain {
  def main(args:Array[String]):Unit={
    require(args.length==1,"new empty probe output directory")
    val target=Paths.get(args(0)).toAbsolutePath.normalize();require(Files.isDirectory(target))
    val listing=Files.list(target);try require(!listing.findAny().isPresent) finally listing.close()
    val out=os.Path(target.toString)
    val relativeTarget=out.relativeTo(os.pwd).toString
    require((os.pwd/os.RelPath(relativeTarget))==out,"relative target must resolve to original output")
    val annos=Seq(VerilatorBackendAnnotation,TargetDirAnnotation(relativeTarget))
    println("B_API_PROBE_BEFORE_ELAB protocol_executed=false")
    val (high,unusedDut)=Compiler.elaborate(()=>new Public21EmitApiProbe,annos,firrtl.seqToAnnoSeq(Seq.empty[firrtl.annotations.Annotation]))
    println("B_API_PROBE_AFTER_ELAB protocol_executed=false")
    val low=Compiler.toLowFirrtl(high)
    println("B_API_PROBE_AFTER_LOW protocol_executed=false")
    val info=TopmoduleInfo(low.circuit)
    println(s"B_API_PROBE_AFTER_INFO name_matches=${info.name=="Public21EmitApiProbe"} low_exists=${os.isFile(out/(info.name+".lo.fir"))} protocol_executed=false")
    require(info.name=="Public21EmitApiProbe");require(os.isFile(out/(info.name+".lo.fir")))
    val cpp=VerilatorCppJNAHarnessGenerator.codeGen(info,out/(info.name+"."),out,5,32,false)
    os.write(out/(info.name+"-harness.cpp"),cpp)
    Compiler.lowFirrtlToSystemVerilog(low,VerilatorCoverage.CoveragePasses)
    require(os.isFile(out/(info.name+".sv")))
    println("B_API_PROBE_COMPLETE protocol_executed=false backend_started=false")
  }
}
