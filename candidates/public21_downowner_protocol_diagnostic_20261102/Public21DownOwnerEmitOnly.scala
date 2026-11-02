// Diagnostic source-only rebuild. Same official chiseltest 6.0.0 compilation
// path through Verilator harness/SV generation; NO backend/native/test launch.
package chiseltest.simulator.jna
import chiseltest.simulator.{Compiler,TopmoduleInfo,VerilatorBackendAnnotation,VerilatorCoverage}
import firrtl2.options.TargetDirAnnotation
import heteronpu.continuous.Public21DownOwnerProtocolHarness
import java.nio.file.{Files,Paths}

object Public21DownOwnerEmitOnly {
  def main(args:Array[String]):Unit={
    var phase="ENTRY"
    try {
    require(args.length==1,"new empty output directory required")
    phase="VALIDATE_OUTPUT"
    val target=Paths.get(args(0)).toAbsolutePath.normalize()
    require(Files.isDirectory(target),"output directory must be created by supervisor")
    val listing=Files.list(target)
    try require(!listing.findAny().isPresent,"output directory must be empty") finally listing.close()
    val out=os.Path(target.toString)
    // Original ChiselScalatestTester finalAnnos: explicit VerilatorBackend,
    // default TargetDir, no writeVcd config. Original Chisel annotations empty.
    val relativeTarget=out.relativeTo(os.pwd).toString
    require((os.pwd/os.RelPath(relativeTarget))==out,"relative target must resolve to original output")
    val annos=Seq(VerilatorBackendAnnotation,TargetDirAnnotation(relativeTarget))
    println("B_EMIT_ONLY_BEFORE_ELAB backend_started=false native_loaded=false")
    phase="ELABORATE"
    val (high,unusedDut)=Compiler.elaborate(()=>new Public21DownOwnerProtocolHarness,annos,firrtl.seqToAnnoSeq(Seq.empty[firrtl.annotations.Annotation]))
    println("B_EMIT_ONLY_AFTER_ELAB backend_started=false native_loaded=false")
    phase="LOWER"
    val low=Compiler.toLowFirrtl(high)
    println("B_EMIT_ONLY_AFTER_LOW backend_started=false native_loaded=false")
    phase="TOP_INFO"
    val info=TopmoduleInfo(low.circuit)
    println(s"B_EMIT_ONLY_AFTER_INFO name_matches=${info.name=="Public21DownOwnerProtocolHarness"} low_exists=${os.isFile(out/(info.name+".lo.fir"))} backend_started=false native_loaded=false")
    require(info.name=="Public21DownOwnerProtocolHarness")
    // Official toLowFirrtl calls FirrtlStage.execute(Array("-E","low"),...).
    require(os.isFile(out/(info.name+".lo.fir")),"official LOW emission missing")
    // Original pinned Verilator version 5.032. No process is invoked to obtain
    // it here; enclosing runner must independently verify its actual tool pin.
    phase="HARNESS"
    val cpp=VerilatorCppJNAHarnessGenerator.codeGen(info,out/(info.name+"."),out,5,32,false)
    os.write(out/(info.name+"-harness.cpp"),cpp)
    println("B_EMIT_ONLY_LOW_AND_HARNESS_DONE backend_started=false")
    phase="SV"
    Compiler.lowFirrtlToSystemVerilog(low,VerilatorCoverage.CoveragePasses)
    require(os.isFile(out/(info.name+".sv")),"official SV emission missing")
    phase="COMPLETE"
    println("B_EMIT_ONLY_COMPLETE backend_started=false native_loaded=false protocol_executed=false")
    } catch {
      case error:Throwable =>
        // Diagnostics must not replace the original exception or successful gate.
        try BEmitPhaseDiagnostics.report(error,phase) catch { case _:Throwable => () }
        throw error
    }
  }
}

object BEmitPhaseDiagnostics {
  val sources=Set("Public21DownOwnerEmitOnly.scala","Public21DownOwnerProtocolHarness.scala","Public21DownOwnerCrossWindowProtocolOnlySpec.scala","DirectJnaAdapter.scala","DirectBContextFactory.scala","Public21DownOwnerDirectDriver.scala")
  val phases=Set("ENTRY","VALIDATE_OUTPUT","ELABORATE","LOWER","TOP_INFO","HARNESS","SV","COMPLETE")
  def report(error:Throwable,phase:String):Unit={
    val kind=error match {
      case _:IllegalArgumentException=>"ILLEGAL_ARGUMENT"
      case _:AssertionError=>"ASSERTION_ERROR"
      case _:OutOfMemoryError=>"OUT_OF_MEMORY"
      case _:LinkageError=>"LINKAGE_ERROR"
      case _=>"OTHER"
    }
    val frames=error.getStackTrace.iterator.filter(f=>sources.contains(f.getFileName) && f.getLineNumber>0).take(8).map(f=>ujson.Obj("source"->f.getFileName,"line"->f.getLineNumber)).toSeq
    val doc=ujson.Obj("schema"->"B_EMIT_PHASE_FAILURE_V1","phase"->(if(phases.contains(phase))phase else "ENTRY"),"exception_kind"->kind,"frames"->ujson.Arr.from(frames),"backend_started"->false,"native_loaded"->false)
    println("B_EMIT_ONLY_FAILURE "+doc.render())
  }
}
