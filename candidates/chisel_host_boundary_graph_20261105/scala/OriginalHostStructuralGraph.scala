package chiseltest.simulator

import firrtl2.{CircuitState,Parser}
import firrtl2.annotations.JsonProtocol
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.{IdmaFieldSplitTransform,IdmaPackedBoundarySplit,BoundaryIntegrationGuards,StructuralMetadataFactory,CycleWitnessRoles}
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths}
import java.security.MessageDigest
import java.lang.management.ManagementFactory
import scala.jdk.CollectionConverters._
import org.json4s.{JArray,JObject,JString}
import org.json4s.native.JsonMethods
import treadle2.TreadleCircuitStateAnnotation
import treadle2.executable.{SymbolTable,BoundedCycleWitness}
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** Source-only structural diagnostic. No simulator, native library, memory
  * contents, weight/reference input, waveform, or AST/annotation export.
  * Inputs must be the fresh reviewed actual162/seed-enabled original Host
  * high and annotation bytes; this utility cannot establish source provenance.
  * Parent resource supervisor/source-closure gate remains mandatory.
  */
object OriginalHostStructuralGraph {
  private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def hash(s:String):String=sha(s.getBytes(UTF_8))
  // Failure-only disclosure: exact reviewed static messages map to finite codes.
  // No message, stack, source name, path, AST, or message-derived hash is emitted.
  private val topologyGuardCodes=Map[String,String](
    "requirement failed: bounded exact hierarchy path" -> "TOPOLOGY_PATH_BOUNDS",
    "requirement failed: bounded integration statements" -> "TOPOLOGY_STATEMENT_BOUND",
    "requirement failed: exact generated wrapper/leaf binding" -> "TOPOLOGY_MODEL_BINDING",
    "requirement failed: one actual iDMA hierarchy path" -> "TOPOLOGY_IDMA_PATH_COUNT",
    "requirement failed: original high wrapper module identity" -> "TOPOLOGY_WRAPPER_IDENTITY",
    "requirement failed: same seventeen leaf paths" -> "TOPOLOGY_BINDING_COUNT",
    "requirement failed: unchanged split leaf ABI" -> "TOPOLOGY_LEAF_ABI",
    "requirement failed: unique exact instance segment" -> "TOPOLOGY_INSTANCE_SEGMENT"
  )
  private val transformGuardCodes=Map[String,String](
    "known bounded UInt required" -> "UNSIGNED_WIDTH_REQUIRED",
    "missing wrapper driver" -> "WRAPPER_DRIVER_MISSING",
    "requirement failed: alias cycle is not a repairable packed view" -> "ALIAS_CYCLE",
    "requirement failed: bounded alias projection" -> "ALIAS_PROJECTION_BOUND",
    "requirement failed: bounded caller expression children" -> "CALLER_CHILDREN_BOUND",
    "requirement failed: bounded caller expression depth" -> "CALLER_DEPTH_BOUND",
    "requirement failed: bounded caller expression expansion" -> "CALLER_EXPANSION_BOUND",
    "requirement failed: bounded caller expression identities" -> "CALLER_IDENTITY_BOUND",
    "requirement failed: bounded caller statements" -> "CALLER_STATEMENT_BOUND",
    "requirement failed: bounded expanded expression" -> "EXPANDED_EXPRESSION_BOUND",
    "requirement failed: bounded expression identities" -> "EXPRESSION_IDENTITY_BOUND",
    "requirement failed: bounded expression recursion" -> "EXPRESSION_RECURSION_BOUND",
    "requirement failed: bounded total caller expression occurrences" -> "CALLER_OCCURRENCE_BOUND",
    "requirement failed: bounded total expanded field expressions" -> "TOTAL_FIELD_EXPANSION_BOUND",
    "requirement failed: caller expression postorder" -> "CALLER_POSTORDER",
    "requirement failed: cyclic expression object" -> "CYCLIC_EXPRESSION_OBJECT",
    "requirement failed: distinct caller instances" -> "CALLER_INSTANCE_NAMES",
    "requirement failed: each caller has exactly one original packed input driver" -> "PACKED_INPUT_SINGLE_DRIVER",
    "requirement failed: exact mux widths" -> "MUX_WIDTHS",
    "requirement failed: exact nonoverlapping complete packed bus" -> "LAYOUT_BIT_COVERAGE",
    "requirement failed: exact original packed wrapper ABI" -> "PACKED_WRAPPER_ABI",
    "requirement failed: exact split leaf ABI including order" -> "SPLIT_LEAF_ABI",
    "requirement failed: fresh private field namespace" -> "PRIVATE_FIELD_NAMESPACE",
    "requirement failed: implicit coercion forbidden" -> "ALIAS_IMPLICIT_COERCION",
    "requirement failed: must be unconditional low FIRRTL" -> "UNCONDITIONAL_LOW_REQUIRED",
    "requirement failed: one non-invalid driver required" -> "ALIAS_SINGLE_DRIVER",
    "requirement failed: one original iDMA boundary only" -> "BOUNDARY_INSTANCE_FIELD_COUNT",
    "requirement failed: original wrapper input projection" -> "WRAPPER_INPUT_SLICE",
    "requirement failed: original wrapper output packing" -> "WRAPPER_OUTPUT_PACKING",
    "requirement failed: packed input driver width" -> "PACKED_INPUT_WIDTH",
    "requirement failed: projection range" -> "PROJECTION_RANGE",
    "requirement failed: transparent generated wrapper only" -> "TRANSPARENT_WRAPPER",
    "requirement failed: unchanged direct control passthrough" -> "CONTROL_PASSTHROUGH",
    "requirement failed: unchanged split model binding" -> "WRAPPER_MODEL_BINDING",
    "requirement failed: unique modules" -> "MODULE_UNIQUENESS",
    "requirement failed: unresolved packed boundary" -> "UNRESOLVED_PACKED_BOUNDARY",
    "requirement failed: wrapper unique drivers" -> "WRAPPER_UNIQUE_DRIVERS",
    "requirement failed: exact validif widths" -> "VALIDIF_WIDTHS",
"unsupported projected expression: VALID_IF" -> "PROJECTED_VALID_IF",
"unsupported projected expression: SUB_ACCESS" -> "PROJECTED_SUB_ACCESS",
"unsupported projected expression: INFO_EXPR" -> "PROJECTED_INFO_EXPR",
"unsupported projected expression: V_RANDOM" -> "PROJECTED_V_RANDOM",
"unsupported projected expression: OTHER" -> "PROJECTED_OTHER"
  )
  private def boundaryGuardCode(step:String,error:Throwable):String={
    if(error==null || error.getClass!=classOf[IllegalArgumentException])return "UNKNOWN"
    val message=error.getMessage
    if(message==null || message.length>160)return "UNKNOWN"
    val codes=step match {case "TOPOLOGY"=>topologyGuardCodes;case "TRANSFORM"=>transformGuardCodes;case _=>Map.empty[String,String]}
    codes.getOrElse(message,"UNKNOWN")
  }
  private def loaded(c:Class[_],location:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==Paths.get(location).toRealPath(),"actual graph class code location")
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class")
    require(in!=null);try{val b=in.readAllBytes();require(b.length<1024*1024);sha(b)}finally{in.close()}
  }
  private def readPinned(path:String,pin:String,cap:Long):String={
    require(pin.matches("[0-9a-f]{64}"),"reviewed independent SHA256 required")
    val p=Paths.get(path)
    require(p.isAbsolute && Files.isRegularFile(p),"absolute existing input file")
    require(Files.size(p)<=cap,"input byte cap")
    val bytes=Files.readAllBytes(p)
    require(bytes.length.toLong<=cap && sha(bytes)==pin,"actual input bytes/pin")
    val text=new String(bytes,UTF_8)
    require(java.util.Arrays.equals(text.getBytes(UTF_8),bytes),"exact UTF8")
    text
  }
  private def check(s:CircuitState):Unit={
    require(!s.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported annotation")
    require(!s.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),"second circuit annotation")
  }
  // Plain JSON validation precedes annotation class deserialization. No
  // arbitrary constructors or file/memory-init annotations are permitted.
  // Reject, never strip, unexpected original annotations.
  private def checkInputAnnotations(text:String):Unit={
    val entries=JsonMethods.parse(text) match {
      case JArray(xs)=>xs
      case _=>throw new IllegalArgumentException("annotation array required")
    }
    var targetDirs=0;var dontTouches=0
    entries.foreach {
      case JObject(fields)=>
        require(fields.map(_._1).distinct.size==fields.size,"unique annotation JSON keys")
        val f=fields.toMap
        f.get("class") match {
          case Some(JString("firrtl2.transforms.DontTouchAnnotation"))=>
            require(f.keySet==Set("class","target") && f("target").isInstanceOf[JString],"exact DontTouch encoding")
            dontTouches+=1
          case Some(JString("firrtl2.options.TargetDirAnnotation"))=>
            require(f.keySet==Set("class","directory") && f("directory").isInstanceOf[JString],"exact TargetDir encoding")
            targetDirs+=1
          case _=>throw new IllegalArgumentException("unapproved input annotation class")
        }
      case _=>throw new IllegalArgumentException("annotation object required")
    }
    require(targetDirs==1 && dontTouches>0,"one original target dir and original DontTouch annotations")
  }
  // Discard, rather than retain/export, detailed library diagnostics. The cap
  // bounds unexpected log volume. Runtime/OS logger redirection also belongs
  // to the parent supervisor. No exception message or stack is exported.
  private final class DiagnosticSink extends OutputStream {
    var bytes:Long=0L
    var unsupported:Boolean=false
    @volatile var cycleSeen:Boolean=false
    @volatile var onCycle:()=>Unit=()=>()
    private var tail=""
    private def inspect(text:String):Unit={
      val joined=tail+text
      if(!cycleSeen && joined.contains("Combinational loop detected at ")){cycleSeen=true;onCycle()}
      if(Seq("WARNING:","Warning:","SymbolTable:TODO:").exists(joined.contains))unsupported=true
      tail=joined.takeRight(64)
    }
    override def write(b:Int):Unit={bytes+=1;require(bytes<=8L*1024*1024,"diagnostic byte cap");inspect((b&255).toChar.toString)}
    override def write(b:Array[Byte],off:Int,len:Int):Unit={bytes+=len;require(bytes<=8L*1024*1024,"diagnostic byte cap");inspect(new String(b,off,len,UTF_8))}
  }
  private final class PhaseTelemetry(out:PrintStream,sink:DiagnosticSink) {
    private val start=System.nanoTime()
    private val os=ManagementFactory.getOperatingSystemMXBean.asInstanceOf[com.sun.management.OperatingSystemMXBean]
    private val collectors=ManagementFactory.getGarbageCollectorMXBeans.asScala.toVector
    private val memory=ManagementFactory.getMemoryMXBean
    private var phase="admission";private var records=0;private var active=false
    @volatile private var stopped=false
    @volatile var failed=false
    private def emit(kind:String):Unit={
      require(records<96,"bounded phase records")
      val heap=memory.getHeapMemoryUsage
      val cpu=os.getProcessCpuTime
      require(cpu>=0,"CPU metric available")
      val gcMillis=collectors.map(_.getCollectionTime).filter(_>=0).sum
      val gcCount=collectors.map(_.getCollectionCount).filter(_>=0).sum
      records+=1
      out.println("GRAPH_PHASE_V1 seq="+records+" kind="+kind+" phase="+phase+
        " wallMs="+((System.nanoTime()-start)/1000000L)+" cpuMs="+(cpu/1000000L)+
        " heapUsed="+heap.getUsed+" heapMax="+heap.getMax+
        " gcMillis="+gcMillis+" gcCount="+gcCount+" cycleSeen="+(if(sink.cycleSeen)1 else 0))
      out.flush()
      require(!out.checkError(),"phase output failed")
    }
    def begin(name:String):Unit=synchronized {require(!stopped && !active);phase=name;active=true;emit("BEGIN")}
    def end():Unit=synchronized {require(active && !stopped);emit("END");active=false}
    private val sampler=new Thread(new Runnable {def run():Unit={
      try {while(!stopped){Thread.sleep(30000L);PhaseTelemetry.this.synchronized {
        if(!stopped && active)emit("SAMPLE")
      }}}catch{case _:InterruptedException=>();case _:Throwable=>failed=true}
    }},"structural-phase-metrics")
    sampler.setDaemon(true)
    def startSampling():Unit=sampler.start()
    def cycleDetected():Unit={try {synchronized {if(!stopped && active)emit("CYCLE_SEEN")}}catch{case _:Throwable=>failed=true}}
    def stop():Unit={synchronized {stopped=true};sampler.interrupt();sampler.join(1000L);require(!sampler.isAlive,"sampler stopped")}
  }
  def main(args:Array[String]):Unit={
    val savedOut=System.out;val savedErr=System.err
    val sink=new DiagnosticSink;val muted=new PrintStream(sink,true,"UTF-8")
    var stage="admission";var result="FAIL_STRUCTURAL_GRAPH_ONLY stage=admission";var failed=true
    var boundaryStep="NONE"
    def boundaryFailure(error:Throwable):String=
      if(stage=="boundary_split")" boundaryStep="+boundaryStep+" boundaryGuard="+boundaryGuardCode(boundaryStep,error)else ""
    var telemetry:PhaseTelemetry=null
    def timed[T](name:String)(body: => T):T={
      stage=name;telemetry.begin(name);val value=body;telemetry.end();value
    }
    try {
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        telemetry=new PhaseTelemetry(savedOut,sink);sink.onCycle=()=>telemetry.cycleDetected();telemetry.startSampling()
        timed("admission") {
          require(args.length==10,"pinned high,annotations,iDMA and actual loaded class identities")
          require(args.slice(5,7).forall(_.matches("[0-9a-f]{64}")) && args(8).matches("[0-9a-f]{64}"))
          require(loaded(classOf[SymbolTable],args(7))==args(5) && loaded(SymbolTable.getClass,args(7))==args(6),"qualified graph SymbolTable bytes")
          require(loaded(IdmaPackedBoundarySplit.getClass,args(9))==args(8),"same boundary transform class as paired fixture")
          require(Files.getFileStore(Paths.get(args(0)).toAbsolutePath).getUsableSpace>=8L*1024*1024*1024,"unchanged8GiB reserve")
        }
        val (highText,annotationText)=timed("read") {
          val h=readPinned(args(0),args(1),512L*1024*1024)
          val a=readPinned(args(2),args(3),16L*1024*1024)
          checkInputAnnotations(a);(h,a)
        }
        val (circuit,annotations)=timed("parse") {(Parser.parse(highText),JsonProtocol.deserialize(annotationText))}
        val high=timed("roundtrip") {
          require(circuit.serialize==highText,"exact original high parse/serialize roundtrip")
          require(JsonProtocol.serialize(annotations)==annotationText,"exact original annotation roundtrip")
          require(circuit.main=="HostBlockTopV4","actual original Host top")
          val h=CircuitState(circuit,annotations);check(h);h
        }
        val (selected,originalBindings,wrapperName)=timed("split") {
          val originals=high.circuit.modules.collect{case e:firrtl2.ir.ExtModule if e.defname=="idma_backend_rw_axi_flat_wrap"=>e}
          require(originals.size==1,"one exact original iDMA ExtModule")
          val wrapper=originals.head.name
          val split=IdmaFieldSplitTransform(high.circuit,args(4))
          val selected=high.copy(circuit=split)
          require(selected.annotations eq high.annotations,"preserved initialization annotations")
          (selected,new StructuralMetadataFactory(split,seed=true).bindings,wrapper)
        }
        val low=timed("official_lower") {Compiler.toLowFirrtl(selected)}
        timed("lower_checks") {
          check(low)
          BoundaryIntegrationGuards.checkTypesAndFlows(low.circuit)
          require(new StructuralMetadataFactory(low.circuit,seed=true).bindings==originalBindings,"same lowered leaf inventory")
          require(TopmoduleInfo(low.circuit).clocks==Seq("clock"),"original clock")
        }
        val (boundary,topology)=timed("boundary_split") {
          boundaryStep="TOPOLOGY"
          val topology=BoundaryIntegrationGuards.topology(low.circuit,wrapperName,originalBindings)
          boundaryStep="TRANSFORM"
          (IdmaPackedBoundarySplit(low.circuit,wrapperName),topology)
        }
        val boundaryLow=timed("boundary_checks") {
          BoundaryIntegrationGuards.verify(low.circuit,boundary,topology,originalBindings)
          BoundaryIntegrationGuards.checkTypesAndFlows(boundary.circuit)
          val revised=low.copy(circuit=boundary.circuit)
          require(revised.annotations eq low.annotations,"original initialization annotations preserved by reference")
          check(revised)
          require(TopmoduleInfo(revised.circuit).clocks==Seq("clock"),"unchanged original clock")
          revised
        }
        val ann=FirrtlCircuitAnnotation(boundaryLow.circuit)+:boundaryLow.annotations
        val obtained=timed("get_firrtl_ast") {GetFirrtlAst.transform(ann)}
        val withInfo=timed("set_implicit_output_info") {SetImplicitOutputInfo.transform(obtained)}
        val prepared=timed("prepare_ast") {(new PrepareAst).transform(withInfo)}
        val (state,factory)=timed("prepared_checks") {
          val states=prepared.collect{case TreadleCircuitStateAnnotation(s)=>s}
          require(states.size==1,"one actual prepared AST")
          require(!states.head.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported prepared annotation")
          BoundaryIntegrationGuards.checkTypesAndFlows(states.head.circuit)
          require(TopmoduleInfo(states.head.circuit).clocks==Seq("clock"),"unchanged prepared original clock")
          val f=new StructuralMetadataFactory(states.head.circuit,seed=true)
          require(f.bindings==originalBindings,"same prepared leaf inventory")
          (states.head,f)
        }
        val table=timed("symbol_table") {
          val roles=CycleWitnessRoles(state.circuit,factory.bindings)
          var witnessCount=0
          val t=BoundedCycleWitness.withDiagnostic(roles,r=>{
            require(witnessCount==0,"one witness only");witnessCount+=1
            savedOut.println("GRAPH_CYCLE_WITNESS "+r.json);savedOut.flush()
            require(!savedOut.checkError(),"witness output failed")
          }) { SymbolTable(state.circuit,Seq(factory),allowCycles=false) }
          factory.requireComplete();require(!sink.unsupported,"unhandled/warning library diagnostic");t
        }
        val preparedSha=timed("summary_hash") {hash(state.circuit.serialize)}
        require(!telemetry.failed && !sink.cycleSeen,"telemetry failure or detected cycle")
        result="PASS_DECLARED_CONE_TOPOLOGY_ONLY highSha="+args(1)+" annotationsSha="+args(3)+
          " preparedSha="+preparedSha+" symbols="+table.size+
          " leafBindings=17 boundaryInstances=1 boundaryInputFields=26 boundaryAddedPorts=90 nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false"
        failed=false
      }}
    }catch{case error:Throwable=>
      result="FAIL_STRUCTURAL_GRAPH_ONLY stage="+stage+" exceptionClassSha="+hash(error.getClass.getName)+boundaryFailure(error)+
        " nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false"
    }finally{
      try {if(telemetry!=null){telemetry.stop();require(!telemetry.failed,"sampler metrics failed")}}catch{case error:Throwable=>
        failed=true;result="FAIL_STRUCTURAL_GRAPH_ONLY stage="+stage+" exceptionClassSha="+hash(error.getClass.getName)+boundaryFailure(error)+
          " nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false"
      }
      System.setOut(savedOut);System.setErr(savedErr)
    }
    savedOut.println(result+" suppressedDiagnosticBytes="+sink.bytes+" cycleSeen="+(if(sink.cycleSeen)1 else 0))
    savedOut.flush()
    if(failed)System.exit(2)
  }
}

