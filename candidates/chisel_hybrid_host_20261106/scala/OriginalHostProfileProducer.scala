package chiseltest.simulator

import firrtl2.CircuitState
import firrtl2.annotations.JsonProtocol
import heteronpu.continuous.model.NativeLibraryPin
import java.lang.management.ManagementFactory
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path,Paths,LinkOption,StandardOpenOption}
import java.security.MessageDigest
import org.json4s._
import org.json4s.native.JsonMethods
import scala.jdk.CollectionConverters._

/** Source-only full-profile producer. No execution is admitted by this source.
  * CLI: admissionPath admissionSHA catalogPath catalogSHA matrixPath matrixSHA
  *      icgPath icgSHA idmaPath idmaSHA sourceManifestSHA loadedClassesSHA
  *      driver runtime profile maxActiveCycles wallSeconds fileClosure fileClosureSHA output
  * The owner must first verify the complete current loaded closure and every
  * native qualification lineage. This main cannot issue its own admission.
  */
object OriginalHostProfileProducer {
  val ExpectedHighSha="9130abce09a3ca5b27e4b92eadfa3b2a133d9d17825009f5b5d0ef673b97390f"
  val ExpectedAnnotationsSha="2bea49e84f2ca30a5409e33c33ae71772f67772269851ae271137feb55bf9303"
  val ExpectedPreparedSha="cd588b716f90aebdd0750c0013e0c056ec5b4022c76110a090c351a48298f568"
  val ExpectedIdmaExtSha="85b299b3b237b70a8450315f887a2f8aad53bd86c95fb8d9a2ff943173cb4193"
  val ExpectedCatalogSha="c300433ea9e1f7060971d41a72e4c2643a30406cd3452b52c6d6cc790bed423d"
  private val proofPins=Map(
    "original_successful_graph"->"448db1888acaca2e32d8d25e64affe72513229c340da80caee59ef970199c3ba",
    "r2_actual_differential_review"->"0adc0f031866bcdef6e3c8fba67f5ba3371626cdd41a24a0a1ad75c06cc953fa",
    "seven_library_tokens_review"->"86619f7f3f3745eebd3b2820953a10625c94b0a1e7285691ab71ffee2d696d97",
    "original_source_overlay"->"589e1e0f522aae929d25283b180ec566683254862f9537494aec26e2bd27efe1",
    "candidate_filename_catalog"->"70e583b6a1de9289cb34e63f93113aeb977b931d8738164581f2c9b94443eab7")
  private val libraryTokens=Set("src/main/scala/chisel3/stage/phases/Elaborate.scala",
    "src/main/scala/chisel3/util/Arbiter.scala","src/main/scala/chisel3/util/Counter.scala",
    "src/main/scala/chisel3/util/Decoupled.scala","src/main/scala/chisel3/util/Mux.scala",
    "src/main/scala/chisel3/util/OneHot.scala","src/main/scala/chisel3/util/Valid.scala")
  private def text(v:JValue):String=JsonMethods.compact(JsonMethods.render(v))
  private def hash(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def str(v:JValue):String=v match {case JString(s)=>s;case _=>throw new IllegalArgumentException("string field")}
  private def rows(v:JValue):List[JValue]=v match {case JArray(xs)=>xs;case _=>throw new IllegalArgumentException("array field")}
  private def unique(v:JValue):Unit=v match {
    case JObject(xs)=>require(xs.map(_._1).distinct.size==xs.size,"unique JSON fields");xs.foreach(x=>unique(x._2))
    case JArray(xs)=>xs.foreach(unique)
    case _=>()
  }
  private def pinnedJson(path:Path,sha:String,cap:Int=1024*1024):JValue={
    require(path.isAbsolute && Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS) && Files.size(path)<=cap,"bounded regular proof file")
    val bytes=Files.readAllBytes(path);require(hash(bytes)==sha,"independently fixed proof bytes")
    val v=JsonMethods.parse(new String(bytes,UTF_8));unique(v);v
  }
  private final case class Catalog(pairs:Vector[ExactHighSourceInfoRebinding.FilenamePair],unchanged:Set[String])
  private def catalog(path:Path,sha:String):Catalog={
    require(sha==ExpectedCatalogSha,"explicit independently reviewed filename catalog only")
    val c=pinnedJson(path,sha)
    require((c \ "schema")==JString("EXACT_ORIGINAL_HOST_FILENAME_ONLY_CATALOG_V1"))
    val evidence=c \ "evidence"
    require(evidence.asInstanceOf[JObject].obj.map(_._1).toSet==proofPins.keySet)
    proofPins.foreach {case(name,expected)=>
      val entry=evidence \ name;require(str(entry \ "sha256")==expected)
      val proof=pinnedJson(Paths.get(str(entry \ "path")),expected,4*1024*1024)
      if(name=="original_successful_graph"){
        require((proof \ "high_sha256")==JString(ExpectedHighSha) && (proof \ "annotations_sha256")==JString(ExpectedAnnotationsSha))
        require((proof \ "prepared_sha256")==JString(ExpectedPreparedSha) && (proof \ "symbol_count")==JInt(1979793))
        require((proof \ "source_commit")==JString("8d6bd0202d45513713d94c2c538df339ac4c2e22"))
        require((proof \ "launch_commit")==JString("f56175fe987e0eeef4bebf0ef01a03b91956252b"))
      }
    }
    val all=rows(c \ "pairs");require(all.size==162)
    val pairs=all.map {r=>
      val source=Paths.get(str(r \ "source_path"))
      require(HybridExecutionGate.hash(source)==str(r \ "source_sha256"),"all original162 source files remain exact")
      ExactHighSourceInfoRebinding.FilenamePair(str(r \ "local"),str(r \ "remote"))
    }.toVector
    val fixed=rows(c \ "unchanged_filenames").map(str)
    require(fixed.distinct.size==7 && fixed.toSet==libraryTokens,"only seven exact source-qualified library tokens")
    Catalog(pairs,fixed.toSet)
  }
  private final class EvidenceWriter(val root:Path) extends AutoCloseable {
    private val stream=Files.newBufferedWriter(root.resolve("SCALAR_PROVENANCE.jsonl"),UTF_8,StandardOpenOption.CREATE_NEW)
    private var traceBytes=0L;private var artifactBytes=0L;private var closed=false
    def emit(kind:String,body:JValue):Unit={
      require(!closed);val line=text(JObject(List("event"->JString(kind),"body"->body)))+"\n"
      val bytes=line.getBytes(UTF_8);require(bytes.length<=1024*1024 && traceBytes<=8L*1024*1024-bytes.length,"bounded scalar evidence")
      stream.write(line);stream.flush();traceBytes+=bytes.length
    }
    def file(name:String,content:String):JValue={
      require(name.matches("[A-Za-z0-9_.-]+"));val bytes=content.getBytes(UTF_8)
      require(bytes.length<=16*1024*1024 && artifactBytes<=48L*1024*1024-bytes.length,"bounded complete annotation/startup evidence")
      Files.write(root.resolve(name),bytes,StandardOpenOption.CREATE_NEW);artifactBytes+=bytes.length
      JObject(List("file"->JString(name),"bytes"->JInt(bytes.length),"sha256"->JString(hash(bytes))))
    }
    def close():Unit=if(!closed){closed=true;stream.close()}
  }
  private def metrics(stage:String):JValue={
    val memory=ManagementFactory.getMemoryMXBean
    val gc=ManagementFactory.getGarbageCollectorMXBeans.asScala
    JObject(List("stage"->JString(stage),"monotonicNanos"->JInt(System.nanoTime()),
      "heapUsed"->JInt(memory.getHeapMemoryUsage.getUsed),"heapCommitted"->JInt(memory.getHeapMemoryUsage.getCommitted),
      "heapMaximum"->JInt(memory.getHeapMemoryUsage.getMax),"nonHeapUsed"->JInt(memory.getNonHeapMemoryUsage.getUsed),
      "gcCount"->JInt(gc.map(_.getCollectionCount).filter(_>=0).sum),"gcMillis"->JInt(gc.map(_.getCollectionTime).filter(_>=0).sum),
      "gcOrMemoryReclamationClaimed"->JBool(false)))
  }
  private def sourceInfoEvidence(e:ExactHighSourceInfoRebinding.Evidence):JValue=JObject(List(
    "rawHighSha256"->JString(e.raw.sha256),"rawBytes"->JInt(e.raw.bytes),
    "reboundSha256"->e.rebound.map(x=>JString(x.sha256)).getOrElse(JNull),
    "reboundBytes"->e.rebound.map(x=>JInt(x.bytes)).getOrElse(JNull),
    "syntaxNodes"->JInt(e.syntaxNodes),"infoNodes"->JInt(e.infoNodes),"completed"->JBool(e.completedRebinding),
    "changedFilenames"->JArray(e.changedFilenameCounts.map(x=>JObject(List("local"->JString(x.localEscaped),"remote"->JString(x.remoteEscaped),"occurrences"->JInt(x.occurrences)))).toList),
    "unchangedFilenames"->JArray(e.unchangedFilenameCounts.map{case(f,n)=>JObject(List("filename"->JString(f),"occurrences"->JInt(n)))}.toList)))

  /** This scope owns the original tuple/DUT/high AST. Only the rebound state
    * escapes. The evidence callback captures writer only, never a Circuit.
    */
  private def elaborateRebound(c:Catalog,out:EvidenceWriter):CircuitState={
    out.emit("phase",metrics("before_original_elaboration"))
    val high=OriginalHostTreadleBinding.elaborateOriginalHigh()
    out.emit("phase",metrics("after_original_elaboration"))
    require(HybridExecutionGate.textHash(JsonProtocol.serialize(high.annotations))==ExpectedAnnotationsSha,"fixed original annotation content/order")
    val rebound=ExactHighSourceInfoRebinding.rebind(high,c.pairs,c.unchanged,ExpectedHighSha,
      ExactHighSourceInfoRebinding.Limits(4000000,8000000,512,512L*1024*1024),e=>out.emit("source_info_rebinding",sourceInfoEvidence(e)))
    require(rebound.rebound.sha256==ExpectedHighSha && (rebound.state.annotations eq high.annotations))
    rebound.state
  }
  private def pinsJson(p:OriginalHostTreadleBinding.SourcePins):JValue=JObject(List(
    "highSha"->JString(p.highSha),"annotationsSha"->JString(p.annotationsSha),"idmaExtModuleSha"->JString(p.idmaExtModuleSha),
    "sourceManifestSha"->JString(p.sourceManifestSha),"loadedClassesSha"->JString(p.loadedClassesSha)))
  private def cleanupJson(c:OriginalHostTreadleBinding.CleanupReceipt):JValue=JObject(List(
    "engine"->JString(c.engine),"pins"->pinsJson(c.pins),"preparedSha"->JString(c.preparedSha),
    "bindingsJson"->JString(c.bindingsJson),"factoryContractJson"->JString(c.factoryContractJson),
    "startupAuditJson"->JString(c.startupAuditJson),"liveEdgeAuditJson"->JString(c.liveEdgeAuditJson),
    "engineAndNativeCleanupComplete"->JBool(c.engineAndNativeCleanupComplete),"numericalPass"->JBool(c.numericalPass)))
  private def reportJson(r:OriginalHostPinDriver.Report):JValue=JObject(List(
    "engine"->JString(r.engine),"frames"->JInt(r.frames),"risingEdges"->JInt(r.risingEdges),"fallingEdges"->JInt(r.fallingEdges),
    "completeInputOutputTraceSha256"->JString(r.completeInputOutputTraceSha256),"driverExit"->JInt(r.driverExit),
    "finalRequested"->JBool(r.finalRequested),"binarySha256"->JString(r.binarySha256),"runtimeSha256"->JString(r.runtimeSha256),
    "logSha256"->JString(r.logSha256),"transport"->JString(r.transport),"numericalPass"->JBool(r.numericalPass),
    "actualChildPid"->JInt(r.actualChildPid),"actualChildStartTicks"->JString(r.actualChildStartTicks),
    "actualDriverArgv"->JArray(r.actualDriverArgv.map(JString).toList)))
  private def verifyFiles(path:Path,expected:String):JValue={
    val c=pinnedJson(path,expected,16*1024*1024)
    require((c \ "schema")==JString("HYBRID_PROFILE_EXECUTION_FILE_CLOSURE_V1"))
    val files=rows(c \ "files");require(files.nonEmpty && files.size<=20000)
    val paths=files.map(x=>str(x \ "path"));require(paths.distinct.size==paths.size)
    val allowed=Set("scala_source","class","tool","native","driver","runtime","input_only","weight","program","config","view","material_receipt")
    files.foreach{x=>val p=Paths.get(str(x \ "path"));require(allowed(str(x \ "role")),"no reference-only/expected bytes in DUT closure")
      require((x \ "bytes")==JInt(Files.size(p)) && HybridExecutionGate.hash(p)==str(x \ "sha256"),"fresh exact file closure")}
    rows(c \ "aliases").foreach{x=>val p=Paths.get(str(x \ "path"))
      require(Files.isSymbolicLink(p)&&Files.readSymbolicLink(p).toString==str(x \ "link")&&p.toRealPath().toString==str(x \ "target"),"exact declared closure alias")}
    require(str(c \ "java_class_path")==System.getProperty("java.class.path"),"actual current JVM classpath")
    c
  }
  private def loadedClasses(out:EvidenceWriter):Unit={
    val names=Vector("heteronpu.continuous.HostBlockTopV4","heteronpu.continuous.model.AllNativeRetainedModelFactory",
      "chiseltest.simulator.OriginalHostTreadleBinding$","chiseltest.simulator.OriginalHostFrameTransport$",
      "chiseltest.simulator.Compiler$","treadle2.TreadleTester","treadle2.executable.SymbolTable","firrtl2.CircuitState")
    val rows=names.map{n=>val c=Class.forName(n, false, this.getClass.getClassLoader);val source=c.getProtectionDomain.getCodeSource
      require(source!=null);JObject(List("class"->JString(n),"codeSource"->JString(source.getLocation.toURI.toString),
        "loader"->JString(Option(c.getClassLoader).map(_.getClass.getName).getOrElse("BOOTSTRAP"))))}
    out.file("ACTUAL_CORE_CLASS_ORIGINS.json",text(JArray(rows.toList)))
  }
  private def observeJvm(out:EvidenceWriter,label:String):Unit={
    // Passive actual current-JVM evidence; no hardware getter/eval/clock calls.
    ActualJvmProcessObservation.capture(out.root,label)
  }

  /** One complete unchanged original profile, with a fresh factory/engine.
    * Does not generate references or decide numerical acceptance.
    */
  private def execute(prepared:OriginalHostTreadleBinding.Prepared,m:NativeLibraryPin,g:NativeLibraryPin,d:NativeLibraryPin,
    gate:HybridExecutionGate,out:EvidenceWriter,plan:OriginalHostPinDriver.Plan):Unit={
    val session=OriginalHostTreadleBinding.connect(prepared,m,g,d,gate)
    var failure:Throwable=null
    try{
      out.file("STARTUP_AUDIT.json",session.startupAudit.json)
      out.file("NATIVE_INVENTORY.json",session.factory.bindingInventoryJson)
      observeJvm(out,"after_construction");loadedClasses(out)
      out.emit("phase",metrics("before_original_driver"))
      var driverFailure:Throwable=null
      val report=try OriginalHostPinDriver.run(session,plan,gate) catch{case t:Throwable=>driverFailure=t;throw t}
        finally{try out.emit("phase",metrics("after_original_driver"))catch{case t:Throwable=>
          if(driverFailure!=null)driverFailure.addSuppressed(t)else throw t}}
      out.file("DRIVER_REPORT.json",text(reportJson(report)))
      observeJvm(out,"after_driver")
    }catch{case t:Throwable=>failure=t}
    finally{try session.close()catch{case t:Throwable=>if(failure!=null)failure.addSuppressed(t)else failure=t}}
    // Preserve real cleanup/counters even for a watchdog/driver failure. Such
    // evidence is incomplete execution, never a numerical mismatch or pass.
    try{
      val cleanup=session.cleanupReceipt
      out.file("ENGINE_CLEANUP.json",text(cleanupJson(cleanup)))
      out.file("FINAL_NATIVE_EDGE_AUDIT.json",cleanup.liveEdgeAuditJson)
    }catch{case t:Throwable=>if(failure!=null)failure.addSuppressed(t)else failure=t}
    if(failure!=null)throw failure
  }

  def main(args:Array[String]):Unit={
    require(args.length==20,"admission/SHA catalog/SHA Matrix/SHA ICG/SHA iDMA/SHA ScalaSourceSHA classSHA driver runtime profile cycles wall fileClosure/SHA output")
    val gate=HybridExecutionGate.load(Paths.get(args(0)),args(1))
    val pins=OriginalHostTreadleBinding.SourcePins(ExpectedHighSha,ExpectedAnnotationsSha,ExpectedIdmaExtSha,args(10),args(11))
    val m=NativeLibraryPin(args(4),args(5));val g=NativeLibraryPin(args(6),args(7));val d=NativeLibraryPin(args(8),args(9))
    val binary=Paths.get(args(12));val runtime=Paths.get(args(13));val profile=args(14).toInt;val cycles=args(15).toLong;val wall=args(16).toLong
    gate.requireEngineConstruction(pins,ExpectedPreparedSha,m,g,d);gate.requireDriverLaunch(binary,runtime,profile)
    val fileClosure=Paths.get(args(17));val before=verifyFiles(fileClosure,args(18))
    val c=catalog(Paths.get(args(2)),args(3));val root=Paths.get(args(19))
    require(!root.isAbsolute&&root.getNameCount==1&&root.toString!="."&&root.toString!=".."&& !Files.exists(root));Files.createDirectory(root)
    val out=new EvidenceWriter(root);var failure:Throwable=null;var completed=false
    try{
      out.file("PRE_EXECUTION_FILE_CLOSURE.json",text(before))
      out.emit("scope",JObject(List("engine"->JString(OriginalHostTreadleBinding.Engine),"profile"->JInt(profile),"numericalPass"->JBool(false))))
      val prepared=OriginalHostTreadleBinding.prepareFromGenerator(()=>elaborateRebound(c,out),pins,gate,n=>out.emit("phase",metrics(n)))
      out.file("PREPARED_IDENTITY.json",text(JObject(List("prepared_sha256"->JString(prepared.preparedSha),"fresh_repairs"->JInt(394),
        "bindings"->JObject(prepared.bindings.toList.sortBy(_._1).map{case(n,k)=>n->JString(k)}),
        "proofProvenance"->JString(prepared.provenance),"repairWork"->JString(prepared.repairWork)))))
      val absolute=root.toAbsolutePath
      val plan=OriginalHostPinDriver.Plan(binary,runtime,absolute.resolve("outputs"),absolute.resolve("DRIVER_STDERR.txt"),profile,cycles,wall,absolute.resolve("DRIVER_POPEN.json"))
      execute(prepared,m,g,d,gate,out,plan)
      val after=verifyFiles(fileClosure,args(18));require(after==before)
      out.file("POST_EXECUTION_FILE_CLOSURE.json",text(after))
      completed=true
    }catch{case t:Throwable=>failure=t;try out.emit("failure",JString(t.toString.take(4096)))catch{case c:Throwable=>t.addSuppressed(c)};throw t}
    finally{try out.close()catch{case t:Throwable=>if(failure!=null)failure.addSuppressed(t)else throw t}}
    require(completed)
    out.file("RESULT.json",text(JObject(List("schema"->JString("HYBRID_ORIGINAL_HOST_PROFILE_PRODUCER_V1"),
      "status"->JString("PROFILE_DRIVER_AND_ENGINE_CLOSED_PENDING_OWNING_VERIFICATION"),"engine"->JString(OriginalHostTreadleBinding.Engine),
      "profile"->JInt(profile),"complete_block_tokens"->JInt(128),"fileClosureSha256"->JString(args(18)),
      "sourceManifestSha256"->JString(args(10)),"loadedClassesSha256"->JString(args(11)),"numerical_pass"->JBool(false),"final_rtl_executed"->JBool(false)))))
  }
}
