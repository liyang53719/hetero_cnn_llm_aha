package chiseltest.simulator

import firrtl2.{AnnotationSeq,CircuitState,EmittedFirrtlCircuitAnnotation}
import firrtl2.annotations.DeletedAnnotation
import firrtl2.logger.Logger
import firrtl2.options.{CustomFileEmission,Dependency,Phase,StageOptions,StageOptionsView,Viewer}
import firrtl2.options.phases.{AddDefaults,Checks,DeletedWrapper,GetIncludes}
import firrtl2.stage.{FirrtlCircuitAnnotation,FirrtlStage,RunFirrtlTransformAnnotation}

/** ISOLATED, UNCOMPILED, UNEXECUTED CANDIDATE. Not connected to Host preparation.
  * Uses public official APIs. It preserves the exact original low emitter and
  * all compiler transforms; only Stage's terminal WriteOutputAnnotations is
  * omitted. The low emitter still allocates the complete serialized String.
  * Its transparent delegation phase name differs from Stage's anonymous phase;
  * raw DeletedAnnotation provenance must be inventoried, never impersonated.
  */
object OfficialLowFirrtlFinalWriterOmission {
  val Route="ISOLATED_OFFICIAL_LOW_PHASES_WITHOUT_TERMINAL_FILE_WRITER_V1"
  final case class Result(state:CircuitState,rawStageAnnotations:AnnotationSeq,
    emitted:EmittedFirrtlCircuitAnnotation,delegationPhaseName:String,
    qualified:Boolean=false,hostIntegrationPermitted:Boolean=false)

  private def admittedOriginalAnnotations(a:AnnotationSeq):Unit={
    // Same actual original high admission. This excludes include files,
    // custom transform/emitter requests, file initialization, BlackBox source
    // writers, output-annotation requests and user logging/plugin options.
    val permitted=Set("firrtl2.transforms.DontTouchAnnotation","firrtl2.options.TargetDirAnnotation")
    require(a.forall(x=>permitted(x.getClass.getName)),"exact original high annotation classes only")
    require(a.count(_.getClass.getName=="firrtl2.options.TargetDirAnnotation")==1,"one original target directory")
    require(a.exists(_.getClass.getName=="firrtl2.transforms.DontTouchAnnotation"),"original DontTouch annotations")
  }

  /** No additional annotations are accepted. Caller must separately admit
    * memory, CPU, output, exact source/classes and this candidate differential.
    */
  def lower(state:CircuitState):Result={
    admittedOriginalAnnotations(state.annotations)
    require(state.renames.isEmpty,"original input has no pending rename map")
    Compiler.requireTargetDir(state.annotations)
    // Byte-for-byte algorithm from pinned Compiler.toLowFirrtl/stateToAnnos:
    // preserve order and original objects, add the same default pass and circuit.
    val defaultPasses=Seq(Dependency(chiseltest.sequences.ConvertCirctSequenceIntrinsics))
    val defaults=defaultPasses.map(p=>RunFirrtlTransformAnnotation(p))
    val withoutCircuit=state.annotations.filterNot(_.isInstanceOf[FirrtlCircuitAnnotation])
    val inAnnos=defaults ++: (FirrtlCircuitAnnotation(state.circuit)+:withoutCircuit)
    val stage=new FirrtlStage
    val parsed=stage.shell.parse(Array("-E","low"),inAnnos)
    val withIncludes=DeletedWrapper(new GetIncludes).transform(parsed)
    // Same public official FirrtlPhase used by FirrtlStage.run. Its internal
    // CatchExceptions and DeletedWrapper phases remain unchanged.
    val runPhase=new Phase {
      override lazy val name:String=Route+".OfficialFirrtlPhaseDelegate"
      def transform(a:AnnotationSeq):AnnotationSeq=stage.phase.transform(a)
    }
    val result=Logger.makeScope(withIncludes){
      Seq[Phase](new AddDefaults,new Checks,runPhase)
        .map(p=>DeletedWrapper(p))
        .foldLeft(withIncludes)((a,p)=>p.transform(a))
    }
    // For the admitted original closure the only terminal custom write must
    // be the normal LowFirrtlEmitter result. Any additional emission means
    // the no-side-effect preconditions no longer hold: stop, do not strip it.
    val emitted=result.collect{case e:EmittedFirrtlCircuitAnnotation=>e}
    val custom=result.collect{case e:CustomFileEmission=>e}
    require(emitted.size==1 && custom.size==1 && (custom.head eq emitted.head),"one original low FIRRTL emission only")
    require(emitted.head.value.name==state.circuit.main && emitted.head.value.outputSuffix==".lo.fir","original low emitter identity")
    require(Viewer[StageOptions].view(result).annotationFileOut.isEmpty,"no requested annotation-file side effect")
    // Exact official conversion, including its documented internal-annotation
    // filter. No custom filter, reordering or DeletedAnnotation name rewrite.
    val low=Compiler.annosToState(result)
    require(!low.annotations.exists(_.isInstanceOf[DeletedAnnotation]),"official conversion filtered deleted provenance")
    Result(low,result,emitted.head,runPhase.name)
  }
}
