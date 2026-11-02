// Test-only bridge located in the official API package to respect Scala visibility.
package chiseltest.simulator.jna
import chiseltest.simulator.{SimulatorContext,TopmoduleInfo,PinInfo,VerilatorSimulator}
object DirectBContextFactory {
  def open(library:os.Path,output:os.Path,name:String,inputs:Seq[(String,Int,Boolean)],outputs:Seq[(String,Int,Boolean)],clocks:Seq[String]):SimulatorContext={
    val info=new TopmoduleInfo(name,inputs.map { case (n,w,s)=>new PinInfo(n,w,s) },outputs.map { case (n,w,s)=>new PinInfo(n,w,s) },clocks)
    val so=JNAUtils.compileAndLoadJNAClass(library)
    new JNASimulatorContext(so,output,info,VerilatorSimulator,Array.empty[String],None)
  }
}
