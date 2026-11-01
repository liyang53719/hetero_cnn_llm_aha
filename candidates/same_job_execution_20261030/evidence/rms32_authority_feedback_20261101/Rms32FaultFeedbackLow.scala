package chiseltest.simulator

import heteronpu.continuous.Rms32FaultFeedbackFixture
import firrtl2.options.TargetDirAnnotation

/** Actual helper/adapter boundary lowering, not full HostBlockTop qualification.
  * Invoke identically with old or fixed production helper classes FIRST on the
  * classpath. Any official failure is propagated; no exception is relabelled
  * PASS and no CheckCombLoops annotation/pass is removed. No simulation/SV. */
object Rms32FaultFeedbackLow {
  def main(args:Array[String]):Unit={
    require(args.isEmpty,"fixed feedback fixture; no runtime bypass switches")
    println("RMS32_FEEDBACK_PHASE ELABORATE_BEGIN");Console.out.flush()
    val (high,_)=Compiler.elaborate(()=>new Rms32FaultFeedbackFixture,
      Seq(TargetDirAnnotation("feedback-official-low")),Seq.empty)
    println("RMS32_FEEDBACK_PHASE ELABORATE_COMPLETE");Console.out.flush()
    println("RMS32_FEEDBACK_PHASE OFFICIAL_LOW_BEGIN");Console.out.flush()
    val low=Compiler.toLowFirrtl(high)
    require(low.circuit.main=="Rms32FaultFeedbackFixture","actual fixture top")
    println(s"RMS32_FEEDBACK_OFFICIAL_LOW_COMPLETE modules=${low.circuit.modules.size} scope=BOUNDARY_OFFICIAL_LOW_ONLY numerical_pass=false full_top_pass=false")
    Console.out.flush()
  }
}
