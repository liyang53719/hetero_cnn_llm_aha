package chiseltest.simulator

import firrtl2.AnnotationSeq
import firrtl2.annotations.JsonProtocol
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.AllNativeRetainedModelFactory
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
import org.json4s._
import org.json4s.native.JsonMethods
import treadle2.{BlackBoxFactoriesAnnotation,ClockInfoAnnotation,TreadleCircuitStateAnnotation,TreadleTester}

/** Passive post-constructor evidence. No poke, peek, getValue, step or eval.
  * ExecutionEngine does execute orphan assignments and MemoryInitializer during
  * construction. We inventory that work; absence of startup reset is not proof
  * that construction performed no evaluation. Missing native telemetry stays
  * unavailable and cannot authorize the original profile driver.
  */
object OriginalHostStartupAudit {
  private def encode(v:JValue):String=JsonMethods.compact(JsonMethods.render(v))
  private def sha(s:String):String=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(b=>f"${b&255}%02x").mkString
  private def cls(a:Any):String=a.getClass.getName.stripSuffix("$")
  private val forbidden=Set(
    "treadle2.CallResetAtStartupAnnotation","treadle2.RandomizeAtStartupAnnotation",
    "treadle2.RandomSeedAnnotation","treadle2.ValidIfIsRandomAnnotation",
    "treadle2.DataStorePlugInAnnotation","treadle2.ResetNameAnnotation",
    "firrtl2.annotations.MemoryRandomInitAnnotation","firrtl2.annotations.MemoryFileInlineAnnotation",
    "firrtl2.annotations.LoadMemoryAnnotation")
  private val initializers=Set("firrtl2.annotations.MemoryScalarInitAnnotation",
    "firrtl2.annotations.MemoryArrayInitAnnotation","firrtl2.annotations.PresetAnnotation",
    "firrtl2.annotations.PresetRegAnnotation")

  def rejectUnrequestedStartupOptions(a:AnnotationSeq):Unit=
    require(!a.exists(x=>forbidden(cls(x))),"unrequested random/file-load/plugin/startup-reset option")

  def annotationInventory(a:AnnotationSeq,circuits:Vector[(firrtl2.ir.Circuit,String)]):JValue={
    rejectUnrequestedStartupOptions(a)
    val counts=a.groupBy(cls).toVector.sortBy(_._1).map{case(n,x)=>n->JInt(x.size)}
    val embedded=a.flatMap{
      case FirrtlCircuitAnnotation(c)=>Some(c)
      case TreadleCircuitStateAnnotation(s)=>Some(s.circuit)
      case _=>None
    }.map{c=>
      val role=circuits.collectFirst{case(known,label)if known eq c=>label}
      require(role.nonEmpty,"each circuit-bearing annotation has an exact known preparation object")
      JObject(List("identityKind"->JString("EXACT_OBJECT_REFERENCE_IN_PINNED_PREPARATION_CHAIN"),"role"->JString(role.get)))
    }
    // The exact corrected circuit identity and independently pinned fresh
    // factory/clock are recorded separately, not serialized into a huge blob.
    val ordinary=a.filterNot(x=>x.isInstanceOf[FirrtlCircuitAnnotation]||x.isInstanceOf[TreadleCircuitStateAnnotation]||
      x.isInstanceOf[BlackBoxFactoriesAnnotation]||x.isInstanceOf[ClockInfoAnnotation])
    val content=JsonProtocol.serialize(ordinary)
    require(content.getBytes(UTF_8).length<=16*1024*1024,"bounded startup annotation inventory")
    JObject(List("classes"->JObject(counts.toList),"ordinaryContentSha256"->JString(sha(content)),
      "circuitBearingAnnotations"->JArray(embedded.toList),
      "preservedInitializationClasses"->JObject(counts.filter(x=>initializers(x._1)).toList)))
  }

  final case class Receipt(json:String,allNativeZeroEdgesDirectlyObserved:Boolean,
    nativeConstructorEvaluationCountsAvailable:Boolean,profileDriverAdmitted:Boolean)

  def capture(tester:TreadleTester,prepared:OriginalHostTreadleBinding.Prepared,
    factory:AllNativeRetainedModelFactory):Receipt={
    val engine=tester.engine
    require(engine.ast eq prepared.correctedState.circuit,"same repaired startup circuit")
    factory.requireCompleteBinding()
    val circuits=prepared.preparationInputCircuit.toVector.map(_->"ORIGINAL_BOUNDARY_LOW_PREPARATION_INPUT")++
      Vector(prepared.correctedState.circuit->"EXACT_CORRECTED_PREPARED_CIRCUIT")
    val outerInventory=annotationInventory(engine.annotationSeq,circuits)
    val stateInventory=annotationInventory(prepared.correctedState.annotations,circuits)
    require(engine.inputsChanged && engine.symbolsPokedSinceEvaluation.isEmpty,"untouched constructor engine")
    require(tester.clockStepper.getCycleCount==0,"no automatic startup cycles")
    def passive(name:String):BigInt={
      val s=engine.symbolTable(name)
      s.normalize(engine.dataStore(s))
    }
    val top=Vector("clock","clock/prev","reset").map(n=>n->passive(n))
    require(top.forall(_._2==0),"initial top clock/previous-clock/reset values")

    // These are the exact assignment objects already executed by the pinned
    // constructor, not a second evaluation or a guessed static schedule.
    val orphans=engine.scheduler.orphanedAssigns
    require(orphans.size<=2000000,"bounded original orphan census")
    val digest=MessageDigest.getInstance("SHA-256")
    val nativeOrphans=scala.collection.mutable.ArrayBuffer.empty[String]
    orphans.foreach{a=>
      val n=a.symbol.name
      require(n.length<=4096,"bounded symbol name")
      digest.update(n.getBytes(UTF_8));digest.update(0.toByte)
      if(prepared.bindings.keys.exists(p=>n==p||n.startsWith(p+".")))nativeOrphans+=n
    }
    require(nativeOrphans.isEmpty,"constructor orphan assignments must not touch native instances")
    val orphanSha=digest.digest().map(b=>f"${b&255}%02x").mkString

    // Bound and retain actual prepared graph reset ancestry. This verifies the
    // input ancestor, not reset polarity; low-frame differential must prove
    // the actual rst_ni == !reset value before any profile is accepted.
    val resets=prepared.bindings.toVector.filterNot(_._2==AllNativeRetainedModelFactory.icgName).sortBy(_._1).map{case(path,_)=>
      val name=path+".rst_ni"
      val start=engine.symbolTable(name)
      val seen=scala.collection.mutable.HashSet.empty[treadle2.executable.Symbol]
      val todo=scala.collection.mutable.Queue(start)
      var edges=0
      while(todo.nonEmpty){
        val s=todo.dequeue()
        if(seen.add(s)){
          require(seen.size<=4096,"bounded native reset ancestry")
          engine.symbolTable.parentsOf.getEdges(s).foreach{p=>
            edges+=1;require(edges<=65536,"bounded native reset dependency edges")
            if(!seen(p))todo.enqueue(p)
          }
        }
      }
      val ancestors=seen.toVector.map(_.name).sorted
      val inputs=ancestors.filter(engine.symbolTable.inputPortsNames.contains)
      require(inputs==Vector("reset"),"each original native reset has only top reset input ancestry")
      JObject(List("port"->JString(name),"ancestorCount"->JInt(ancestors.size),
        "ancestorSha256"->JString(sha(ancestors.mkString("\n"))),"topInputAncestors"->JArray(inputs.map(JString).toList),
        "passiveInitialValue"->JInt(passive(name)),"polarityDifferentialExecuted"->JBool(false)))
    }
    require(resets.size==9,"eight Matrix and one iDMA reset ancestries")

    val live=JsonMethods.parse(factory.edgeAuditJson) match{
      case JObject(rows)=>require(rows.size==17 && rows.map(_._1).toSet==prepared.bindings.keySet,"all seventeen unique startup audits");rows.toMap
      case _=>throw new IllegalArgumentException("native audit object")
    }
    def zero(v:JValue):Unit=v match{
      case JInt(n)=>require(n==0,"constructor observed an unexpected edge")
      case _=>throw new IllegalArgumentException("integer edge counter required")
    }
    def zeros(v:JValue,count:Int):Unit=v match{
      case JArray(xs)=>require(xs.size==count,"complete native edge counter tuple");xs.foreach(zero)
      case _=>throw new IllegalArgumentException("native edge counter tuple required")
    }
    prepared.bindings.foreach{case(path,kind)=>
      val row=live(path)
      zero(row\"rises")
      if(kind==AllNativeRetainedModelFactory.matrixName){zero(row\"falls");zeros(row\"nativeEdges",2)}
      if(kind==AllNativeRetainedModelFactory.icgName){zero(row\"falls");zeros(row\"nativeInputAndGatedEdges",4)}
    }
    val json=encode(JObject(List("schema"->JString("PASSIVE_ORIGINAL_HOST_CONSTRUCTOR_AUDIT_V1"),
      "preparedSha256"->JString(prepared.preparedSha),
      "sourceManifestSha256"->JString(prepared.pins.sourceManifestSha),"loadedClassesSha256"->JString(prepared.pins.loadedClassesSha),
      "nativeFactoryContract"->JsonMethods.parse(factory.factoryContractJson),
      "outerAnnotations"->outerInventory,"stateAnnotations"->stateInventory,
      "topPassiveValues"->JObject(top.map{case(n,v)=>n->JInt(v)}.toList),"clockStepperCycles"->JInt(0),
      "inputsChanged"->JBool(engine.inputsChanged),"pokedSymbols"->JInt(engine.symbolsPokedSinceEvaluation.size),
      "constructorOrphanAssignmentsExecuted"->JInt(orphans.size),"orphanNamesSha256"->JString(orphanSha),
      "nativeOrphanAssignments"->JArray(Nil),"nativeResetAncestry"->JArray(resets.toList),
      "liveNativeEdgeAudit"->JObject(live.toList.sortBy(_._1)),
      "nativeIdmaEdgeCountersAvailable"->JBool(false),"nativeConstructorEvaluationCountsAvailable"->JBool(false),
      "noNativeOrphanCallArgument"->JString("SOURCE_BOUND_ARGUMENT_ONLY_NOT_NATIVE_EVALUATION_TELEMETRY"),
      "profileDriverAdmitted"->JBool(false),"numericalPass"->JBool(false))))
    Receipt(json,false,false,false)
  }
}
