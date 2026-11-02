// Diagnostic source-only rebuild. Same official chiseltest 6.0.0 compilation
// path through Verilator harness/SV generation; NO backend/native/test launch.
package chiseltest.simulator.jna
import chiseltest.simulator.{Compiler,TopmoduleInfo,VerilatorBackendAnnotation,VerilatorCoverage}
import firrtl2.options.TargetDirAnnotation
import heteronpu.continuous.Public21DownOwnerProtocolHarness
import java.nio.file.{Files,Paths}

object Public21DownOwnerEmitOnly {
  def main(args:Array[String]):Unit={
    require(args.length==1,"new empty output directory required")
    val target=Paths.get(args(0)).toAbsolutePath.normalize()
    require(Files.isDirectory(target),"output directory must be created by supervisor")
    val listing=Files.list(target)
    try require(!listing.findAny().isPresent,"output directory must be empty") finally listing.close()
    val out=os.Path(target.toString)
    // Original ChiselScalatestTester finalAnnos: explicit VerilatorBackend,
    // default TargetDir, no writeVcd config. Original Chisel annotations empty.
    val annos=Seq(VerilatorBackendAnnotation,TargetDirAnnotation(out.toString))
    println("B_EMIT_ONLY_BEFORE_ELAB backend_started=false native_loaded=false")
    val (high,unusedDut)=Compiler.elaborate(()=>new Public21DownOwnerProtocolHarness,annos,firrtl.seqToAnnoSeq(Seq.empty[firrtl.annotations.Annotation]))
    val low=Compiler.toLowFirrtl(high)
    val info=TopmoduleInfo(low.circuit)
    require(info.name=="Public21DownOwnerProtocolHarness")
    // Official toLowFirrtl calls FirrtlStage.execute(Array("-E","low"),...).
    require(os.isFile(out/(info.name+".lo.fir")),"official LOW emission missing")
    // Original pinned Verilator version 5.032. No process is invoked to obtain
    // it here; enclosing runner must independently verify its actual tool pin.
    val cpp=VerilatorCppJNAHarnessGenerator.codeGen(info,out/(info.name+"."),out,5,32,false)
    os.write(out/(info.name+"-harness.cpp"),cpp)
    println("B_EMIT_ONLY_LOW_AND_HARNESS_DONE backend_started=false")
    Compiler.lowFirrtlToSystemVerilog(low,VerilatorCoverage.CoveragePasses)
    require(os.isFile(out/(info.name+".sv")),"official SV emission missing")
    println("B_EMIT_ONLY_COMPLETE backend_started=false native_loaded=false protocol_executed=false")
  }
}
