package chiseltest.simulator

import firrtl2.AnnotationSeq
import firrtl2.ir.Type
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model._
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
import org.json4s._
import org.json4s.native.JsonMethods
import treadle2.{BlackBoxFactoriesAnnotation,ClockInfoAnnotation,ScalaBlackBox,ScalaBlackBoxFactory,TreadleCircuitStateAnnotation,TreadleTester}
import treadle2.executable.{ClockInfo,Transition}
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** Tiny original Matrix/ICG declaration constructor and first-frame test.
  * This is not the Host, production factory, pin IPC facade, service workload,
  * iDMA qualification, or profile/numerical acceptance. No RTL is altered.
  * CLI: matrixPath matrixSHA icgPath icgSHA bare|pair relativeOutputDirectory.
  */
object OriginalMatrixStartupProbe {
  private def json(v:JValue):String=JsonMethods.compact(JsonMethods.render(v))
  private def array(v:Seq[Long]):JValue=JArray(v.map(x=>JInt(x)).toList)
  private final class Calls(val delegate:ScalaBlackBox,record:JValue=>Unit,expectedReset:()=>Option[BigInt]) extends ScalaBlackBox {
    override val name:String=delegate.name
    var inputs=0L;var outputs=0L;var clocks=0L
    private val dependencies=scala.collection.mutable.Map.empty[String,Seq[String]]
    private val isMatrix=delegate.isInstanceOf[MatrixNativeBlackBox]
    // This mirrors only the pinned adapter's retained reset map for checking
    // callback causality. It is not a native reset/edge/evaluation counter.
    private var retainedReset=BigInt(0)
    override def completeName(n:String):String=delegate.completeName(n)
    override def setParams(p:Seq[firrtl2.ir.Param]):Unit=delegate.setParams(p)
    override def setPlusArgs(p:Seq[treadle2.blackboxes.PlusArg]):Unit=delegate.setPlusArgs(p)
    override def getDependencies:Seq[(String,Set[String])]=delegate.getDependencies
    override def outputDependencies(p:String):Seq[String]={val d=delegate.outputDependencies(p);dependencies(p)=d;d}
    private def checkReset():Unit=if(isMatrix){
      require(expectedReset().contains(retainedReset),"callback would evaluate stale or invented Matrix reset value")
    }
    override def inputChanged(p:String,v:BigInt):Unit={
      inputs+=1;val before=retainedReset;if(isMatrix && p=="rst_ni")retainedReset=v
      record(JObject(List("method"->JString("inputChanged"),"port"->JString(p),"value"->JInt(v),
        "sourceDerivedRetainedResetBefore"->JInt(before),"sourceDerivedRetainedResetAfter"->JInt(retainedReset))))
      checkReset();delegate.inputChanged(p,v)
    }
    override def getOutput(v:Seq[BigInt],t:Type,p:String):BigInt={
      outputs+=1;val names=dependencies.getOrElse(p,throw new IllegalStateException("missing exact compiled output dependencies"))
      require(names.size==v.size);val before=retainedReset
      names.zip(v).find(_._1=="rst_ni").foreach(x=>retainedReset=x._2)
      record(JObject(List("method"->JString("getOutput"),"port"->JString(p),
        "dependencyValues"->JObject(names.zip(v).map{case(n,x)=>n->JInt(x)}.toList),
        "sourceDerivedRetainedResetBefore"->JInt(before),"sourceDerivedRetainedResetAfter"->JInt(retainedReset))))
      checkReset();val out=delegate.getOutput(v,t,p)
      record(JObject(List("method"->JString("getOutputReturned"),"port"->JString(p),"value"->JInt(out))))
      out
    }
    override def clockChange(t:Transition,n:String):Unit={
      clocks+=1;record(JObject(List("method"->JString("clockChange"),"clock"->JString(n),"transition"->JString(t.toString))))
      delegate.clockChange(t,n)
    }
    override def finish():Unit=delegate.finish()
    def snapshot:JValue=JObject(List("inputChangedCalls"->JInt(inputs),"getOutputCalls"->JInt(outputs),"clockChangeCalls"->JInt(clocks)))
    def untouched:Boolean=inputs==0 && outputs==0 && clocks==0
  }
  def main(args:Array[String]):Unit={
    require(args.length==6,"matrixPath matrixSHA icgPath icgSHA bare|pair relativeOutputDirectory")
    require(Set("bare","pair")(args(4)))
    val paired=args(4)=="pair";val mp=NativeLibraryPin(args(0),args(1));val gp=NativeLibraryPin(args(2),args(3))
    val output=Paths.get(args(5));require(!output.isAbsolute && output.getNameCount==1 && output.toString!="." && output.toString!=".." && !Files.exists(output),"fresh owned relative output directory")
    Files.createDirectory(output)
    val (high,_)=Compiler.elaborate(()=>new NativeMatrixSchedulingProbe(paired),Seq(TargetDirAnnotation(args(5))),Seq.empty)
    val external=high.circuit.modules.collect{case e:firrtl2.ir.ExtModule=>e}
    val matrix=external.filter(_.defname==AllNativeRetainedModelFactory.matrixName)
    require(matrix.size==1 && external.size==(if(paired)2 else 1),"exact original declarations")
    require(matrix.head.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==MatrixNativeLayout.expectedPorts)
    require(matrix.head.params==Seq(firrtl2.ir.IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1))))
    val low=Compiler.toLowFirrtl(high)
    val original:AnnotationSeq=ClockInfoAnnotation(Seq(ClockInfo("io_clk_i")))+:(FirrtlCircuitAnnotation(low.circuit)+:low.annotations)
    val prepared=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(original)))
    val states=prepared.collect{case TreadleCircuitStateAnnotation(s)=>s};require(states.size==1)
    OriginalHostStartupAudit.rejectUnrequestedStartupOptions(prepared)
    OriginalHostStartupAudit.rejectUnrequestedStartupOptions(states.head.annotations)
    val calls=scala.collection.mutable.Map.empty[String,Calls]
    var callbackRecorder:Option[(String,JValue)=>Unit]=None
    var expectedFrameReset:Option[BigInt]=None
    val factory=new ScalaBlackBoxFactory {
      var endpoint:Option[MatrixNativeBlackBox]=None;var gate:Option[IcgNativeBlackBox]=None
      def complete():Unit=require(endpoint.nonEmpty && gate.nonEmpty==paired && boxes.size==(if(paired)2 else 1))
      override def createInstance(n:String,b:String):Option[ScalaBlackBox]={
        val leaf:ScalaBlackBox=b match{
          case "qwen2_matrix_command_endpoint"=>
            require(endpoint.isEmpty);val native=new RetainedMatrixNativeLeaf(mp)
            val x=try new MatrixNativeBlackBox(n,native,()=>complete()) catch{case t:Throwable=>try native.close()catch{case c:Throwable=>t.addSuppressed(c)};throw t}
            endpoint=Some(x);x
          case "tc_clk_gating"=>
            require(paired && gate.isEmpty);val native=new RetainedIcgNativeLeaf(gp)
            val x=try new IcgNativeBlackBox(n,native,()=>complete()) catch{case t:Throwable=>try native.close()catch{case c:Throwable=>t.addSuppressed(c)};throw t}
            gate=Some(x);x
          case _=>throw new IllegalArgumentException("unexpected native declaration")
        }
        val proxy=new Calls(leaf,event=>callbackRecorder.getOrElse(throw new IllegalStateException("missing callback trace"))(n,event),()=>expectedFrameReset)
        require(!calls.contains(n));calls(n)=proxy;Some(add(proxy))
      }
      def close():Unit={
        var failure:Throwable=null
        try endpoint.foreach(_.abortUnqualifiedConstruction())catch{case t:Throwable=>failure=t}
        try gate.foreach(_.abortUnqualifiedConstruction())catch{case t:Throwable=>if(failure==null)failure=t else failure.addSuppressed(t)}
        if(failure!=null)throw failure
      }
    }
    var tester:TreadleTester=null;var direct:RetainedMatrixNativeLeaf=null;var directGate:RetainedIcgNativeLeaf=null
    var failure:Throwable=null;var result:JValue=JNothing
    val tracePath=output.resolve("COMPLETE_FRAMES.jsonl")
    val writer=Files.newBufferedWriter(tracePath,UTF_8,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
    val frameDigest=java.security.MessageDigest.getInstance("SHA-256");var traceBytes=0L
    var currentFrame= -1;var callbackSequence=0L
    def emit(event:String,body:JValue):Unit={
      val line=json(JObject(List("event"->JString(event),"body"->body)))+"\n"
      val bytes=line.getBytes(UTF_8);traceBytes+=bytes.length;require(traceBytes<=8L*1024*1024,"bounded full tiny trace")
      writer.write(line);writer.flush();frameDigest.update(bytes)
    }
    def values(xs:Iterable[(String,BigInt)]):JValue=JObject(xs.toList.sortBy(_._1).map{case(n,v)=>n->JInt(v)})
    callbackRecorder=Some((instance:String,event:JValue)=>{
      callbackSequence+=1
      emit("native_callback",JObject(List("sequence"->JInt(callbackSequence),"frame"->JInt(currentFrame),"instance"->JString(instance),
        "expectedFrameResetN"->expectedFrameReset.map(JInt(_)).getOrElse(JNull),"callback"->event)))
    })
    try{
      emit("constructor_begin",JObject(List("paired"->JBool(paired))))
      tester=new TreadleTester(BlackBoxFactoriesAnnotation(Seq(factory))+:prepared);factory.complete()
      val e=tester.engine;require(e.ast eq states.head.circuit,"exact prepared tiny circuit")
      def passive(n:String):BigInt={val s=e.symbolTable(n);s.normalize(e.dataStore(s))}
      val orphans=e.scheduler.orphanedAssigns.map(_.symbol.name).toVector
      require(orphans.size<=4096,"bounded tiny constructor orphan evidence")
      val nativeOrphans=orphans.filter(n=>calls.keys.exists(p=>n==p||n.startsWith(p+".")))
      val matrixInitial=factory.endpoint.get.nativeEdgeCounts
      val icgInitial=factory.gate.map(_.nativeEdgeCounts)
      val circuitRefs=Vector(low.circuit->"ORIGINAL_TINY_LOW_PREPARATION_INPUT",states.head.circuit->"EXACT_TINY_PREPARED_CIRCUIT")
      val startup=JObject(List("actualBehavioralCallbacks"->JObject(calls.toList.sortBy(_._1).map{case(n,c)=>n->c.snapshot}),
        "orphanCount"->JInt(orphans.size),"orphanNamesSha256"->JString(HybridExecutionGate.textHash(orphans.mkString("\n"))),
        "allOrphanNames"->JArray(orphans.map(JString).toList),"nativeOrphans"->JArray(nativeOrphans.map(JString).toList),
        "matrixNativeEdges"->array(Vector(matrixInitial._1,matrixInitial._2)),"icgNativeEdges"->icgInitial.map(array).getOrElse(JNull),
        "passiveTopValues"->values(Vector("io_clk_i"->passive("io_clk_i"),"io_clk_i/prev"->passive("io_clk_i/prev"),"io_rst_ni"->passive("io_rst_ni"))),
        "inputsChanged"->JBool(e.inputsChanged),"cycleCount"->JInt(tester.clockStepper.getCycleCount),
        "pokedSymbols"->JArray(e.symbolsPokedSinceEvaluation.toVector.map(_.name).sorted.map(JString).toList),
        "outerAnnotations"->OriginalHostStartupAudit.annotationInventory(e.annotationSeq,circuitRefs),
        "stateAnnotations"->OriginalHostStartupAudit.annotationInventory(states.head.annotations,circuitRefs),
        "nativeEvaluationCallCountsAvailable"->JBool(false),"callbackCountsAreNativeEvalCounts"->JBool(false)))
      emit("constructor_observed",startup)
      require(e.inputsChanged && e.symbolsPokedSinceEvaluation.isEmpty && tester.clockStepper.getCycleCount==0)
      require(passive("io_clk_i")==0 && passive("io_clk_i/prev")==0)
      require(nativeOrphans.isEmpty && calls.values.forall(_.untouched),"actual constructor must make zero native behavioral callbacks")
      require(matrixInitial==(0L,0L));icgInitial.foreach(c=>require(c==Vector(0L,0L,0L,0L)))
      direct=new RetainedMatrixNativeLeaf(mp);if(paired)directGate=new RetainedIcgNativeLeaf(gp)
      ActualJvmProcessObservation.capture(output,"matrix_startup_before_first_frame")
      // clock, active-low reset, functional enable, scan enable. Nonclock
      // changes occur only with old/new clock low. Repeated high is a separate
      // idempotence stress, not a claim that the original Host emits it.
      val rows=Vector((0,1,0,0),(0,0,0,0),(1,0,0,0),(1,0,0,0),(0,0,0,0),
        (0,0,1,0),(1,0,1,0),(1,0,1,0),(0,0,1,0),(0,1,1,0),(1,1,1,0),
        (0,1,1,0),(0,1,0,0),(1,1,0,0),(0,1,0,0),(0,1,0,1),(1,1,0,1),(0,1,0,1))
      val trace=java.security.MessageDigest.getInstance("SHA-256")
      var last=rows.head
      rows.zipWithIndex.foreach{case((clk,rst,en,scan),index)=>
        currentFrame=index;expectedFrameReset=Some(BigInt(rst))
        require(index==0 || (last._1==0 && clk==0) || (last._2,last._3,last._4)==(rst,en,scan),"strict low-only input updates")
        val input=MatrixNativeLayout.inputWidths.keys.map(_->BigInt(0)).toMap.updated("rst_ni",BigInt(rst))
        emit("frame_input",JObject(List("index"->JInt(index),"clock"->JInt(clk),"matrixNonclockInputs"->values(input),"enable"->JInt(en),"scan"->JInt(scan))))
        val setters=input.toVector.sortBy(_._1);val ordered=if(index%2==0)setters else setters.reverse
        ordered.foreach{case(n,v)=>e.setValue("io_"+n,v)}
        e.setValue("enable",BigInt(en));e.setValue("testEnable",BigInt(scan));e.setValue("io_clk_i",BigInt(clk));e.evaluateCircuit()
        require(!e.inputsChanged,"one explicit evaluation settled all outputs")
        direct.drive(input);direct.evaluate()
        if(paired){directGate.drive(BigInt(en),BigInt(scan));directGate.evaluate();directGate.clock(BigInt(clk))}
        val gate=if(paired)directGate.read()else BigInt(clk);direct.clock(gate)
        val observedGate=e.getValue("observedGate")
        val expected=direct.read();val names=MatrixNativeLayout.outputs.map(_.name)
        val order=if(index%2==0)names else names.reverse
        val actual=order.map(n=>n->e.getValue("io_"+n)).toMap
        val repeated=order.map(n=>n->e.getValue("io_"+n)).toMap
        val adapterEdges=factory.endpoint.get.nativeEdgeCounts;val directEdges=direct.edgeCounts
        emit("frame_output",JObject(List("index"->JInt(index),"observedGate"->JInt(observedGate),"directGate"->JInt(gate),
          "allActualOutputs"->values(actual),"allRepeatedGetterOutputs"->values(repeated),"allDirectOutputs"->values(expected),
          "matrixNativeEdges"->array(Vector(adapterEdges._1,adapterEdges._2)),"directMatrixEdges"->array(Vector(directEdges._1,directEdges._2)),
          "icgNativeEdges"->factory.gate.map(g=>array(g.nativeEdgeCounts)).getOrElse(JNull),
          "directIcgEdges"->(if(paired)array(directGate.edgeCounts)else JNull),
          "actualBehavioralCallbacks"->JObject(calls.toList.sortBy(_._1).map{case(n,c)=>n->c.snapshot}))))
        require(observedGate==gate)
        order.foreach{n=>
          val value=actual(n);require(value==expected(n),s"first-frame differential row=$index port=$n")
          require(repeated(n)==value,"repeated getter is idempotent")
          trace.update((s"$index:$n:$value\n").getBytes(UTF_8))
        }
        require(factory.endpoint.get.nativeEdgeCounts==direct.edgeCounts,"actual Matrix transition counts")
        if(paired)require(factory.gate.get.nativeEdgeCounts==directGate.edgeCounts,"actual ICG input/gated transition counts")
        require(tester.clockStepper.getCycleCount==0,"manual eval did not call clockStepper")
        last=(clk,rst,en,scan)
      }
      result=JObject(List("schema"->JString("TINY_ORIGINAL_MATRIX_CONSTRUCTOR_FIRST_FRAME_V1"),
        "scope"->JString("API_STARTUP_AND_SCHEDULER_ONLY_NOT_HOST_OR_FACADE_OR_IDMA_ACCEPTANCE"),
        "paired"->JBool(paired),"matrixLibrarySha256"->JString(mp.sha256),"icgLibrarySha256"->JString(gp.sha256),
        "preparedCircuitSha256"->JString(HybridExecutionGate.textHash(e.ast.serialize)),"startup"->startup,
        "frames"->JInt(rows.size),"completeOutputTraceSha256"->JString(trace.digest().map(b=>f"${b&255}%02x").mkString),
        "matrixNativeEdgesAfter"->array(direct.edgeCounts.productIterator.map(_.asInstanceOf[Long]).toVector),
        "icgNativeEdgesAfter"->(if(paired)array(directGate.edgeCounts)else JNull),
        "fullHostExecuted"->JBool(false),"pinFacadeExecuted"->JBool(false),"numericalPass"->JBool(false)))
    }catch{case t:Throwable=>
      failure=t
      try emit("failure",JObject(List("class"->JString(t.getClass.getName),"message"->JString(Option(t.getMessage).getOrElse("").take(4096)))))
      catch{case logging:Throwable=>t.addSuppressed(logging)}
      throw t
    }finally{
      var cleanup:Throwable=null;var cleanupSucceeded=true
      def clean(action: => Unit):Unit=try action catch{case t:Throwable=>
        cleanupSucceeded=false
        if(failure!=null)failure.addSuppressed(t)else if(cleanup==null)cleanup=t else cleanup.addSuppressed(t)}
      clean{if(direct!=null)direct.close()};clean{if(directGate!=null)directGate.close()}
      clean{if(tester!=null)require(tester.finish,"tiny tester finish must succeed")};clean{factory.close()}
      clean{emit("cleanup",JObject(List("engineAndNativeCleanupComplete"->JBool(cleanupSucceeded),"executionChecksComplete"->JBool(failure==null))))}
      clean{writer.close()}
      if(cleanup!=null)throw cleanup
    }
    require(result!=JNothing)
    val receipt=JObject(List("result"->result,"fullTracePath"->JString(tracePath.toString),"fullTraceBytes"->JInt(traceBytes),
      "fullTraceSha256"->JString(frameDigest.digest().map(b=>f"${b&255}%02x").mkString),"engineAndNativeCleanupComplete"->JBool(true)))
    Files.write(output.resolve("STARTUP_FIRST_FRAME_RECEIPT.json"),(json(receipt)+"\n").getBytes(UTF_8),StandardOpenOption.CREATE_NEW)
    println("TINY_ORIGINAL_MATRIX_STARTUP_FIRST_FRAME_COMPLETED_AFTER_CLEANUP_NOT_HOST_ACCEPTANCE")
  }
}
