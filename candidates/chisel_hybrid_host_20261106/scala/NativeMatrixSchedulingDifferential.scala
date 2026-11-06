package chiseltest.simulator
import chisel3._
import firrtl2.{AnnotationSeq,CircuitState}
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.{RetainedMatrixEndpoint,RetainedMatrixClockGate}
import heteronpu.continuous.model._
import treadle2.{BlackBoxFactoriesAnnotation,ClockInfoAnnotation,ScalaBlackBox,ScalaBlackBoxFactory,TreadleCircuitStateAnnotation,TreadleTester}
import treadle2.executable.ClockInfo
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** Test harness around the ORIGINAL Chisel ExtModule declarations, not a
  * Matrix functional model or modified production service/Host. */
class NativeMatrixSchedulingProbe(gated:Boolean) extends RawModule {
 val dut=Module(new RetainedMatrixEndpoint(enableAccumulatorSeed=true))
 val io=IO(chiselTypeOf(dut.io));io<>dut.io
 val enable=IO(Input(Bool()));val testEnable=IO(Input(Bool()));val observedGate=IO(Output(Clock()))
 if(gated){val gate=Module(new RetainedMatrixClockGate);gate.io.clk_i:=io.clk_i
  gate.io.en_i:=enable;gate.io.test_en_i:=testEnable;dut.io.clk_i:=gate.io.clk_o;observedGate:=gate.io.clk_o
 }else{observedGate:=io.clk_i}
}
/** UNEXECUTED fixture: actual Treadle vs independent native state. Requires
  * independently qualified direct-port/C ABI/JNA traces before admission.
  * args: matrixPath matrixSHA icgPath icgSHA gated(0/1) vectors outputDir schedule(settle-first/single-eval).
  * Vectors: base64 words; gated variant prepends enable,testEnable (66 words).
  * Every output including invalid-cycle payload is compared without masking. */
object NativeMatrixSchedulingDifferential {
 def main(args:Array[String]):Unit={
  require(args.length==8);require(args(4)=="0"||args(4)=="1")
  require(Set("settle-first","single-eval")(args(7)));val singleEval=args(7)=="single-eval"
  val gated=args(4)=="1";val mp=NativeLibraryPin(args(0),args(1));val gp=NativeLibraryPin(args(2),args(3))
  val rows=NativeLeafTrace.rows(args(5),if(gated)66 else 64)
  val (high,_)=Compiler.elaborate(()=>new NativeMatrixSchedulingProbe(gated),Seq(TargetDirAnnotation(args(6))),Seq.empty)
  val originals=high.circuit.modules.collect{case e:firrtl2.ir.ExtModule=>e}
  val matrix=originals.filter(_.defname==AllNativeRetainedModelFactory.matrixName);require(matrix.size==1)
  require(matrix.head.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==MatrixNativeLayout.expectedPorts)
  require(matrix.head.params==Seq(firrtl2.ir.IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1))))
  require(originals.size==(if(gated)2 else 1),"exact original declarations")
  val low=Compiler.toLowFirrtl(high)
  val ann:AnnotationSeq=ClockInfoAnnotation(Seq(ClockInfo("io_clk_i")))+:(FirrtlCircuitAnnotation(low.circuit)+:low.annotations)
  val prepared=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(ann)))
  val states=prepared.collect{case TreadleCircuitStateAnnotation(s)=>s};require(states.size==1)
  val factory=new ScalaBlackBoxFactory {
   var endpoint:Option[MatrixNativeBlackBox]=None;var gate:Option[IcgNativeBlackBox]=None
   def complete():Unit=require(endpoint.nonEmpty && (gate.nonEmpty==gated) && boxes.size==(if(gated)2 else 1))
   override def createInstance(n:String,b:String):Option[ScalaBlackBox]={
    val result:ScalaBlackBox=b match {
     case "qwen2_matrix_command_endpoint"=>require(endpoint.isEmpty);val x=new MatrixNativeBlackBox(n,new RetainedMatrixNativeLeaf(mp),()=>complete());endpoint=Some(x);x
     case "tc_clk_gating"=>require(gated&&gate.isEmpty);val x=new IcgNativeBlackBox(n,new RetainedIcgNativeLeaf(gp),()=>complete());gate=Some(x);x
     case _=>throw new IllegalArgumentException("unknown original leaf")
    };Some(add(result))
   }
   def cleanup():Unit={try endpoint.foreach(_.abortUnqualifiedConstruction())finally gate.foreach(_.abortUnqualifiedConstruction())}
  }
  var tester:TreadleTester=null;var direct:RetainedMatrixNativeLeaf=null;var gate:RetainedIcgNativeLeaf=null
  var failure:Throwable=null
  try{
   tester=new TreadleTester(BlackBoxFactoriesAnnotation(Seq(factory))+:prepared);factory.complete()
   require(tester.engine.ast eq states.head.circuit,"exact prepared circuit")
   direct=new RetainedMatrixNativeLeaf(mp);if(gated)gate=new RetainedIcgNativeLeaf(gp)
   ActualJvmProcessObservation.capture(java.nio.file.Paths.get("."),if(gated)"matrix_treadle_pair"else"matrix_treadle_bare")
   var oldGate=BigInt(0);val digest=java.security.MessageDigest.getInstance("SHA-256")
   val transitions=java.security.MessageDigest.getInstance("SHA-256")
   var oldInputClock=BigInt(0)
   val gateRises=java.security.MessageDigest.getInstance("SHA-256");val gateTransitions=java.security.MessageDigest.getInstance("SHA-256")
   for((raw,index)<-rows.zipWithIndex){
    val row=if(gated)raw.drop(2)else raw;val inputs=NativeLeafTrace.matrixInputs(row)
    val en=if(gated)raw(0)else BigInt(1);val test=if(gated)raw(1)else BigInt(0)
    val setters=inputs.toVector.sortBy(_._1)
    val ordered=if(index%2==0)setters else setters.reverse
    if(singleEval){
     // EXACT Host facade policy: each input assigned once, clock last, one
     // evaluateCircuit; output getValue cannot trigger an extra evaluation.
     for((n,v)<-ordered)tester.engine.setValue("io_"+n,v)
     tester.engine.setValue("enable",en);tester.engine.setValue("testEnable",test)
     tester.engine.setValue("io_clk_i",row.head);tester.engine.evaluateCircuit()
    }else{
     for((n,v)<-ordered)tester.poke("io_"+n,v)
     tester.poke("enable",en);tester.poke("testEnable",test)
     tester.peek("io_out_valid_o") // separate old-clock settle variant
    }
    direct.drive(inputs);direct.evaluate()
    if(gated){gate.drive(en,test);gate.evaluate();gate.clock(row.head)}
    val nextGate=if(gated)gate.read()else row.head
    if(!singleEval)tester.poke("io_clk_i",row.head)
    direct.clock(nextGate)
    def get(n:String):BigInt=if(singleEval)tester.engine.getValue(n)else tester.peek(n)
    require(get("observedGate")==nextGate,"real ICG output at each half-cycle")
    val expected=direct.read();val names=MatrixNativeLayout.outputs.map(_.name)
    for(n<-if(index%2==0)names else names.reverse){val actual=get("io_"+n)
     require(actual==expected(n),s"native/Treadle row=$index output=$n")
     require(get("io_"+n)==actual,"repeated getter changed state")}
    if(oldGate==0&&nextGate==1)NativeEdgeSnapshot.update(digest,MatrixNativeLayout.inputWidths,inputs)
    if(oldGate!=nextGate)NativeEdgeSnapshot.updateTransition(transitions,MatrixNativeLayout.inputWidths,inputs,oldGate,nextGate)
    require(factory.endpoint.get.nativeEdgeCounts==direct.edgeCounts,"connected pair actual Matrix edge counts")
    require(factory.endpoint.get.edgeSnapshotSha256==NativeEdgeSnapshot.current(digest),"complete actual positive-edge inputs")
    require(factory.endpoint.get.transitionSnapshotSha256==NativeEdgeSnapshot.current(transitions),"complete actual all-transition inputs")
    if(gated){
     val widths=Map("en_i"->1,"test_en_i"->1);val values=Map("en_i"->en,"test_en_i"->test)
     if(oldInputClock==0&&row.head==1)NativeEdgeSnapshot.update(gateRises,widths,values)
     if(oldInputClock!=row.head)NativeEdgeSnapshot.updateTransition(gateTransitions,widths,values,oldInputClock,row.head)
     require(factory.gate.get.nativeEdgeCounts==gate.edgeCounts,"actual ICG input/gated edge counts")
     require(factory.gate.get.edgeSnapshotSha256==NativeEdgeSnapshot.current(gateRises),"ICG complete positive-edge inputs")
     require(factory.gate.get.transitionSnapshotSha256==NativeEdgeSnapshot.current(gateTransitions),"ICG complete all-transition inputs")
    }
    oldInputClock=row.head
    oldGate=nextGate
   }
  }catch{case t:Throwable=>failure=t;throw t}finally{
   var cleanupFailure:Throwable=null
   def clean(action: => Unit):Unit=try action catch{case t:Throwable=>
    if(failure!=null)failure.addSuppressed(t)
    else if(cleanupFailure==null)cleanupFailure=t else cleanupFailure.addSuppressed(t)}
   clean{if(direct!=null)direct.close()}
   clean{if(gate!=null)gate.close()}
   clean{if(tester!=null)require(tester.finish,"Treadle finish status must be true")}
   clean{factory.cleanup()}
   if(cleanupFailure!=null)throw cleanupFailure
  }
  // Reached only after every output check AND successful engine/native cleanup.
  println("NATIVE_MATRIX_TREADLE_DIFFERENTIAL_EXECUTED_NOT_FULL_HOST gated="+gated+" rows="+rows.size+" schedule="+args(7))
 }
}
