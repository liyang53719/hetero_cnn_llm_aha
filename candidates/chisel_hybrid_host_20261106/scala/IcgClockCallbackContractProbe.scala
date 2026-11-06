package chiseltest.simulator

import java.nio.file.Paths
import heteronpu.continuous.model._
import treadle2.executable.{Transition,NoTransition,PositiveEdge,NegativeEdge}

/** Tiny API contract test only. No clock drive, data drive or evaluation.
  * The actual original native ICG exists only to check callback edge isolation.
  * Unknown names and calls after checked close must remain rejected.
  */
object IcgClockCallbackContractProbe {
 def main(args:Array[String]):Unit={
  require(args.length==2,"exact ICG library path and SHA")
  val native=new RetainedIcgNativeLeaf(NativeLibraryPin(args(0),args(1)))
  var adapter:IcgNativeBlackBox=null
  val transitions=Vector[Transition](NoTransition,PositiveEdge,NegativeEdge)
  val known=Vector("clk_i","gate.clk_i","clk_o","gate.clk_o")
  val unknown=Vector("","other","gate.extra","other.clk_i","other.clk_o","gate.clk_o.extra")
  var accepted=0;var rejected=0;var closedRejected=0;var failure:Throwable=null
  try{
   adapter=new IcgNativeBlackBox("gate",native,()=>())
   val initial=native.edgeCounts
   require(initial==Vector(0L,0L,0L,0L),"constructor has no native transitions")
   ActualJvmProcessObservation.capture(Paths.get("."),"icg_clock_callbacks")
   for(t<-transitions;n<-known){
    adapter.clockChange(t,n);accepted+=1
    require(native.edgeCounts==initial,"clock notification must not drive native edges")
   }
   for(t<-transitions;n<-unknown){
    var failed=false
    try adapter.clockChange(t,n) catch{case _:IllegalArgumentException=>failed=true}
    require(failed,"unknown clock name must be rejected");rejected+=1
    require(native.edgeCounts==initial,"rejected callback must not drive native edges")
   }
  }catch{case t:Throwable=>failure=t;throw t}finally{
   try {if(adapter!=null)adapter.abortUnqualifiedConstruction()else native.close()} catch{case cleanup:Throwable=>
    if(failure!=null)failure.addSuppressed(cleanup)else throw cleanup}
  }
  for(t<-transitions;n<-known){
   var failed=false
   try adapter.clockChange(t,n) catch{case _:IllegalArgumentException=>failed=true}
   require(failed,"closed adapter must reject every callback");closedRejected+=1
  }
  require(accepted==12 && rejected==18 && closedRejected==12)
  println("ICG_EXACT_CLOCK_CALLBACK_CONTRACT_ONLY accepted=12 unknownRejected=18 closedRejected=12 nativeEdges=0,0,0,0 cleanup=true nativeEvalCountUnavailable=true")
 }
}
