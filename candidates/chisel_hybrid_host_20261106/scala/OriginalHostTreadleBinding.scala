package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState}
import firrtl2.annotations.JsonProtocol
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model._
import heteronpu.continuous.{HostBlockTopV4,QwenBlockShape,Qwen2NumericPolicy}
import firrtl2.options.TargetDirAnnotation
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import java.nio.file.{Files,Path}
import org.json4s._
import org.json4s.native.JsonMethods
import treadle2.{AllowCyclesAnnotation,BlackBoxFactoriesAnnotation,CallResetAtStartupAnnotation,ClockInfoAnnotation,TreadleCircuitStateAnnotation,TreadleTester}
import treadle2.executable.ClockInfo
import treadle2.stage.phases.{GetFirrtlAst,SetImplicitOutputInfo}

/** Hybrid ORIGINAL Chisel Host plus ORIGINAL native RTL leaves.
  * Not pure Chisel, not emitted Host RTL, not a numerical acceptance authority.
  * The supervisor must admit prepare separately; connect requires completed
  * native/half-cycle/adapter qualifications and a current resource grant.
  */
object OriginalHostTreadleBinding {
  val Engine = "HYBRID_ORIGINAL_CHISEL_HOST_NATIVE_ORIGINAL_RTL_LEAVES_V1"
  private def sha(s:String):String=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(b=>f"${b&255}%02x").mkString
  private def check(s:CircuitState):Unit={
    require(!s.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported original annotation")
    require(!s.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),"no second circuit")
    noExecutionOptions(s.annotations)
  }
  private def noExecutionOptions(a:AnnotationSeq):Unit={
    OriginalHostStartupAudit.rejectUnrequestedStartupOptions(a)
    require(!a.contains(AllowCyclesAnnotation),"allowCycles must remain false")
    require(!a.contains(CallResetAtStartupAnnotation),"driver owns every physical reset/edge")
    require(!a.exists(_.isInstanceOf[BlackBoxFactoriesAnnotation]),"no prior metadata/functional factory")
    require(!a.exists(_.isInstanceOf[ClockInfoAnnotation]),"original clock is supplied once after repair")
  }
  private def originalAnnotationJson(text:String):Unit={
    require(text.getBytes(UTF_8).length<=16*1024*1024,"original annotation byte cap")
    val entries=JsonMethods.parse(text) match {case JArray(xs)=>xs;case _=>throw new IllegalArgumentException("annotation array")}
    var targetDirs=0;var dontTouches=0
    entries.foreach {
      case JObject(fields)=>
        require(fields.map(_._1).distinct.size==fields.size,"unique original annotation JSON keys")
        val f=fields.toMap
        f.get("class") match {
          case Some(JString("firrtl2.transforms.DontTouchAnnotation"))=>
            require(f.keySet==Set("class","target") && f("target").isInstanceOf[JString],"exact original DontTouch encoding");dontTouches+=1
          case Some(JString("firrtl2.options.TargetDirAnnotation"))=>
            require(f.keySet==Set("class","directory") && f("directory").isInstanceOf[JString],"exact original TargetDir encoding");targetDirs+=1
          case _=>throw new IllegalArgumentException("unapproved original annotation class")
        }
      case _=>throw new IllegalArgumentException("annotation object")
    }
    require(targetDirs==1 && dontTouches>0,"same one target directory and original DontTouch annotations")
  }
  final case class SourcePins(highSha:String,annotationsSha:String,idmaExtModuleSha:String,
    sourceManifestSha:String,loadedClassesSha:String) {
    require(productIterator.forall {case s:String=>s.matches("[0-9a-f]{64}");case _=>false},"fresh independently checked identities")
  }
  final class Prepared private[OriginalHostTreadleBinding](
    val correctedState:CircuitState,val annotations:AnnotationSeq,val pins:SourcePins,
    val preparedSha:String,val bindings:Map[String,String],val provenance:String,val repairWork:String,
    val preparationInputCircuit:Option[firrtl2.ir.Circuit])

  // Source-only integrated revision. Each method returns only the objects
  // required by the next phase. This does not claim immediate GC or strip any
  // annotation. Original transformed AST checks and one-use grant are retained.
  private final case class Selection(state:CircuitState,bindings:Map[String,String],wrapperName:String)
  private final case class Lowered(state:CircuitState,bindings:Map[String,String],wrapperName:String)
  private final case class Boundary(state:CircuitState,bindings:Map[String,String],topology:BoundaryIntegrationGuards.Topology)

  private def selectHigh(high:CircuitState,pins:SourcePins,gate:HybridExecutionGate,checkpoint:String=>Unit):Selection={
    gate.requirePreparation(pins)
    check(high)
    require(high.annotations.forall(a=>Set("firrtl2.transforms.DontTouchAnnotation","firrtl2.options.TargetDirAnnotation")(a.getClass.getName)),"original object-class whitelist before any transform")
    val originalAnnotations=JsonProtocol.serialize(high.annotations)
    originalAnnotationJson(originalAnnotations)
    require(high.circuit.main=="HostBlockTopV4","selected original Host")
    val highDigest=ExactHighSourceInfoRebinding.digest(high.circuit,512L*1024*1024)
    require(highDigest.sha256==pins.highSha,"fresh actual162/seed-enabled original high identity")
    require(sha(originalAnnotations)==pins.annotationsSha,"same original annotation order/content")
    val originals=high.circuit.modules.collect {case e:firrtl2.ir.ExtModule if e.defname=="idma_backend_rw_axi_flat_wrap"=>e}
    require(originals.size==1,"one original iDMA ExtModule")
    val wrapperName=originals.head.name
    val split=IdmaFieldSplitTransform(high.circuit,pins.idmaExtModuleSha)
    val selected=high.copy(circuit=split)
    require(selected.annotations eq high.annotations,"same original annotations")
    val originalBindings=new StructuralMetadataFactory(split,seed=true).bindings
    checkpoint("original_high_verified_and_idma_fields_split")
    Selection(selected,originalBindings,wrapperName)
  }
  private def officialLowState(state:CircuitState):CircuitState={
    // Exact qualified official composition; only terminal file writer omitted.
    // Its emitted String/raw annotation result is not returned to the caller.
    OfficialLowFirrtlFinalWriterOmission.lower(state).state
  }
  private def lowerSelection(selection:Selection,checkpoint:String=>Unit):Lowered={
    val low=officialLowState(selection.state)
    check(low)
    BoundaryIntegrationGuards.checkTypesAndFlows(low.circuit)
    require(new StructuralMetadataFactory(low.circuit,seed=true).bindings==selection.bindings,"same lowered seventeen leaves")
    require(TopmoduleInfo(low.circuit).clocks==Seq("clock"),"original clock")
    checkpoint("official_low_state_returned_without_terminal_file_write")
    Lowered(low,selection.bindings,selection.wrapperName)
  }
  private def makeBoundary(lowered:Lowered,checkpoint:String=>Unit):Boundary={
    val low=lowered.state
    val topology=BoundaryIntegrationGuards.topology(low.circuit,lowered.wrapperName,lowered.bindings)
    val boundary=IdmaPackedBoundarySplit(low.circuit,lowered.wrapperName)
    BoundaryIntegrationGuards.verify(low.circuit,boundary,topology,lowered.bindings)
    BoundaryIntegrationGuards.checkTypesAndFlows(boundary.circuit)
    val boundaryLow=low.copy(circuit=boundary.circuit)
    require(boundaryLow.annotations eq low.annotations,"original annotations preserved by reference")
    check(boundaryLow)
    require(TopmoduleInfo(boundaryLow.circuit).clocks==Seq("clock"),"unchanged original clock")
    CycleWitnessRoles(boundaryLow.circuit,lowered.bindings)
    checkpoint("original_packed_boundary_and_type_flow_clock_checks_verified")
    Boundary(boundaryLow,lowered.bindings,topology)
  }
  private def prepareBoundary(boundary:Boundary,pins:SourcePins,checkpoint:String=>Unit):Prepared={
    val boundaryLow=boundary.state;val originalBindings=boundary.bindings;val topology=boundary.topology
    val ann=FirrtlCircuitAnnotation(boundaryLow.circuit)+:boundaryLow.annotations
    val obtained=GetFirrtlAst.transform(ann)
    val withInfo=SetImplicitOutputInfo.transform(obtained)
    val observed=new ObservedPrepareAst(394)
    val prepared=observed.transform(withInfo)
    val grant=observed.takeGrant()
    require(observed.evidence.length<=256 && observed.budgetEvidence.length<=512 &&
      observed.sizingEvidence.length<=512 && observed.consumerEvidence.length<=512 &&
      observed.formalEvidence.length<=256 && observed.anchorEvidence.length<=160 &&
      observed.p54WorkEvidence.length<=160,"same bounded observer evidence")
    val states=prepared.collect {case TreadleCircuitStateAnnotation(s)=>s}
    require(states.size==1,"single actual prepared state")
    require(!states.head.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported prepared annotation")
    val repair=ClockInitRepresentationRepair.applyWithProvenance(boundaryLow.circuit,states.head,prepared,394,grant)
    require(repair.corrected==394,"exact fresh proof-bound corrections")
    val correctedState=repair.state
    require(correctedState.renames.isEmpty,"no rename map")
    require(correctedState.annotations eq states.head.annotations,"same original initialization annotations")
    require(firrtl2.passes.CheckTypes.run(correctedState.circuit) eq correctedState.circuit,"types unchanged")
    require(firrtl2.passes.CheckFlows.run(correctedState.circuit) eq correctedState.circuit,"flows unchanged")
    require(TopmoduleInfo(correctedState.circuit).clocks==Seq("clock"),"same prepared original clock")
    require(new StructuralMetadataFactory(correctedState.circuit,seed=true).bindings==originalBindings,"same repaired seventeen leaves")
    CycleWitnessRoles.prepared(correctedState.circuit,originalBindings,topology)
    OriginalHostPorts.verify(correctedState.circuit)
    // CRITICAL: replace the single annotation, not just a local state variable.
    val repairedAnnotations=prepared.map {
      case TreadleCircuitStateAnnotation(s)=>
        require(s eq states.head,"same observed state object")
        TreadleCircuitStateAnnotation(correctedState)
      case other=>other
    }
    require(repairedAnnotations.collect {case TreadleCircuitStateAnnotation(s)=>s}.head eq correctedState)
    noExecutionOptions(repairedAnnotations)
    // Do not retain a second large AST solely for auditing. Keep its reference
    // only when the unchanged execution annotations already keep it alive.
    val inputAlreadyRetained=(correctedState.annotations++repairedAnnotations).exists{
      case FirrtlCircuitAnnotation(c)=>c eq boundaryLow.circuit
      case TreadleCircuitStateAnnotation(s)=>s.circuit eq boundaryLow.circuit
      case _=>false
    }
    val preparedSha=sha(correctedState.circuit.serialize)
    require(preparedSha==OriginalHostConstructionFeasibility.ExpectedPreparedSha,"fixed successful original prepared identity")
    checkpoint("fresh_394_repair_and_fixed_prepared_hash_verified")
    new Prepared(correctedState,repairedAnnotations,pins,preparedSha,
      originalBindings,observed.evidence,repair.workV2,if(inputAlreadyRetained)Some(boundaryLow.circuit)else None)
  }
  /** Only the generator route gives the integrated main a caller stack which
    * never captures a high AST. The generator must capture only scalar inputs.
    */
  def prepareFromGenerator(high:()=>CircuitState,pins:SourcePins,gate:HybridExecutionGate,checkpoint:String=>Unit):Prepared={
    gate.requirePreparation(pins)
    prepareBoundary(makeBoundary(lowerSelection(selectHigh(high(),pins,gate,checkpoint),checkpoint),checkpoint),pins,checkpoint)
  }
  /** Compatibility entry; a caller supplying a high AST still owns its lifetime. */
  def prepare(high:CircuitState,pins:SourcePins,gate:HybridExecutionGate):Prepared=
    prepareFromGenerator(()=>high,pins,gate,_=>())

  final class Session private[OriginalHostTreadleBinding](val tester:TreadleTester,
    val prepared:Prepared,val factory:AllNativeRetainedModelFactory,
    val startupAudit:OriginalHostStartupAudit.Receipt) extends AutoCloseable {
    private var closed=false
    private var engineInUse=false
    private var completedCleanup:Option[CleanupReceipt]=None
    def cleanupReceipt:CleanupReceipt=synchronized {
      require(!engineInUse,"no receipt while engine active")
      completedCleanup.getOrElse(throw new IllegalStateException("no successful engine/native cleanup receipt"))
    }
    private[simulator] def withEngine[T](gate:HybridExecutionGate)(body: => T):T={
      gate.requireStartupDriverAdmission(prepared.pins,startupAudit)
      synchronized {require(!closed && !engineInUse,"one live exclusive engine consumer");engineInUse=true}
      try body finally synchronized {engineInUse=false}
    }
    def close():Unit=synchronized {if(!closed){
      // A timed-out IPC thread may still be inside native eval. Never free its
      // handles concurrently. Retain them for the owning supervisor to kill.
      require(!engineInUse,"engine still in use; outer process cleanup required, native handles retained")
      closed=true
      var failure:Throwable=null
      var audit=""
      // Native counters are readable only while the original handles are live.
      try audit=factory.edgeAuditJson catch {case t:Throwable=>failure=t}
      try require(tester.finish,"Treadle finished with unsuccessful execution") catch {case t:Throwable=>if(failure==null)failure=t else failure.addSuppressed(t)}
      try factory.close() catch {case t:Throwable=>if(failure==null)failure=t else failure.addSuppressed(t)}
      if(failure!=null)throw failure
      completedCleanup=Some(CleanupReceipt(Engine,prepared.pins,prepared.preparedSha,
        factory.bindingInventoryJson,factory.factoryContractJson,startupAudit.json,audit,true))
    }}
  }
  final case class CleanupReceipt(engine:String,pins:SourcePins,preparedSha:String,
    bindingsJson:String,factoryContractJson:String,startupAuditJson:String,liveEdgeAuditJson:String,
    engineAndNativeCleanupComplete:Boolean,numericalPass:Boolean=false)
  /** Safe byte entry: whitelist JSON BEFORE arbitrary annotation constructors.
    * No parser or lowering runs before the owning resource/source admission.
    */
  def preparePinned(highPath:Path,annotationsPath:Path,pins:SourcePins,gate:HybridExecutionGate):Prepared={
    gate.requirePreparation(pins)
    require(Files.size(highPath)<=512L*1024*1024 && Files.size(annotationsPath)<=16L*1024*1024,"original read byte caps")
    require(HybridExecutionGate.hash(highPath)==pins.highSha && HybridExecutionGate.hash(annotationsPath)==pins.annotationsSha,"original input file pins")
    val highText=new String(Files.readAllBytes(highPath),UTF_8)
    val annotationText=new String(Files.readAllBytes(annotationsPath),UTF_8)
    require(sha(highText)==pins.highSha && sha(annotationText)==pins.annotationsSha,"exact UTF8 input bytes")
    originalAnnotationJson(annotationText)
    val circuit=firrtl2.Parser.parse(highText)
    val annotations=JsonProtocol.deserialize(annotationText)
    require(circuit.serialize==highText && JsonProtocol.serialize(annotations)==annotationText,"exact original parse/serialize roundtrip")
    prepare(CircuitState(circuit,annotations),pins,gate)
  }
  /** Same selected original constructor, compiled from the current162-source
    * closure. Avoids diagnostic high/low saves and high parse/reconstruction.
    * The integrated caller performs qualified rebinding before preparation.
    * Full compiler/output/RSS admission remains mandatory.
    */
  def elaborateOriginalHigh():CircuitState={
    val shape=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
    val high={
      val (state,_)=Compiler.elaborate(()=>new HostBlockTopV4(shape,weightReadBeats=16,pipelined=true,
        burstWrites=true,commitTailRead=false,overlapSilu=false,
        enableTransposedDown=true,enableResidentFfn=true,enablePublic21QkvReduction=true,
        numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
        enableProductionPackedQk16=true,enableOrderedVectorQkFold=true,enableChunk32=true),
        Seq(TargetDirAnnotation("host-diagnostic")),Seq.empty)
      state
    }
    high
  }
  def connect(prepared:Prepared,matrix:NativeLibraryPin,icg:NativeLibraryPin,idma:NativeLibraryPin,
    gate:HybridExecutionGate):Session={
    gate.requireEngineConstruction(prepared.pins,prepared.preparedSha,matrix,icg,idma)
    noExecutionOptions(prepared.annotations)
    noExecutionOptions(prepared.correctedState.annotations)
    require(AllNativeRetainedModelFactory.validateInventory(prepared.correctedState.circuit)==prepared.bindings,"same native inventory")
    // Fresh factory only. The metadata validators above were never instantiated.
    val factory=new AllNativeRetainedModelFactory(prepared.correctedState.circuit,matrix,icg,idma)
    val annotations=BlackBoxFactoriesAnnotation(Seq(factory)) +:
      ClockInfoAnnotation(Seq(ClockInfo("clock"))) +: prepared.annotations
    require(!annotations.contains(AllowCyclesAnnotation),"allowCycles=false")
    var tester:TreadleTester=null
    try {
      tester=new TreadleTester(annotations)
      require(tester.engine.ast eq prepared.correctedState.circuit,"engine consumes exact correctedState.circuit")
      factory.requireCompleteBinding()
      require(factory.bindingInventory==prepared.bindings,"all exact seventeen original bindings")
      val startupAudit=OriginalHostStartupAudit.capture(tester,prepared,factory)
      new Session(tester,prepared,factory,startupAudit)
    }catch{case failure:Throwable=>
      try {if(tester!=null)tester.finish} catch{case t:Throwable=>failure.addSuppressed(t)}
      try factory.abortUnqualifiedConstruction() catch{case t:Throwable=>failure.addSuppressed(t)}
      throw failure
    }
  }
}
