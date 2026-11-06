package chiseltest.simulator

import chisel3._
import firrtl2.{AnnotationSeq,CircuitState,EmittedFirrtlCircuitAnnotation}
import firrtl2.annotations.{Annotation,CircuitTarget,DeletedAnnotation,JsonProtocol}
import firrtl2.ir.{Circuit,ExtModule}
import firrtl2.options.{Dependency,TargetDirAnnotation}
import firrtl2.stage.{FirrtlCircuitAnnotation,FirrtlStage,RunFirrtlTransformAnnotation}
import firrtl2.transforms.DontTouchAnnotation
import firrtl2.logger.{Logger,LogLevel}
import heteronpu.continuous.{RetainedMatrixEndpoint,RetainedMatrixClockGate,RetainedIdmaWeightBurstAdapter}
import heteronpu.continuous.model.{IdmaFieldSplitTransform,IdmaPackedBoundarySplit}
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Path,Paths,StandardOpenOption}
import java.security.MessageDigest
import java.util.IdentityHashMap
import org.json4s._
import org.json4s.native.JsonMethods
import scala.jdk.CollectionConverters._

/** Small original-declaration fixtures only. No Host, native loading or tester. */
class LoweringOriginalMatrixPair extends RawModule {
  val dut=Module(new RetainedMatrixEndpoint(enableAccumulatorSeed=true))
  val io=IO(chiselTypeOf(dut.io));io<>dut.io
  val enable=IO(Input(Bool()));val scan=IO(Input(Bool()))
  val gate=Module(new RetainedMatrixClockGate)
  gate.io.clk_i:=io.clk_i;gate.io.en_i:=enable;gate.io.test_en_i:=scan;dut.io.clk_i:=gate.io.clk_o
  dontTouch(io);dontTouch(enable);dontTouch(scan)
}
class LoweringOriginalIdmaAdapter extends Module {
  val dut=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,streamCutThrough=true,burstWrites=true,commitTailRead=false))
  val io=IO(chiselTypeOf(dut.io));io<>dut.io;dontTouch(io)
}
class LoweringChiselDiagnostics extends Module {
  val io=IO(new Bundle {val in=Input(UInt(8.W));val out=Output(UInt(8.W))})
  io.out:=io.in;dontTouch(io)
  chisel3.assert(io.in=/=0.U)
  chisel3.assert(io.in=/=1.U,"assertion sentinel value=%d",io.in)
  chisel3.printf("keep user path /workspace/synthetic/literal.scala value=%d\n",io.in)
}

/** SOURCE-ONLY, UNEXECUTED differential CLI.
  * args: baseline|candidate basic|formal|matrix|idma|diagnostics independentlyPinnedIdmaExtSHA
  * Each invocation requires a fresh separately supervised working directory.
  * Same relative TargetDir string is used on both sides. An external consumer
  * compares complete artifacts and requires strict process/log cleanup.
  */
object OfficialLoweringDifferential {
  private val Cap=16L*1024*1024
  private var written=0L
  private val evidence=Paths.get("evidence")
  private def sha(b:Array[Byte])=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def json(v:JValue)=JsonMethods.compact(JsonMethods.render(v))
  private def save(name:String,b:Array[Byte]):JValue={
    require(b.length<=4*1024*1024 && written+b.length<=Cap,"small fixture evidence cap")
    written+=b.length;val p=evidence.resolve(name)
    Files.write(p,b,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
    JObject(List("file"->JString(name),"bytes"->JInt(b.length),"sha256"->JString(sha(b))))
  }
  private def text(name:String,s:String):JValue=save(name,s.getBytes(UTF_8))
  private def files(root:Path):Vector[String]={
    if(!Files.exists(root))Vector.empty else {val s=Files.walk(root);try s.iterator.asScala.filter(p=>Files.isRegularFile(p)).map(p=>root.relativize(p).toString).toVector.sorted finally s.close()}
  }
  private def phaseFiles:Vector[String]=files(Paths.get(".")).filterNot(_.startsWith("evidence/"))
  private def withOrderLog[T](name:String)(f: => T):T={
    val path=evidence.resolve(name);val file=Files.newOutputStream(path,StandardOpenOption.CREATE_NEW)
    var count=0L
    val bounded=new OutputStream {
      override def write(b:Int):Unit={count+=1;written+=1;require(count<=2*1024*1024 && written<=Cap,"compiler order log cap");file.write(b)}
      override def write(b:Array[Byte],o:Int,n:Int):Unit={count+=n;written+=n;require(count<=2*1024*1024 && written<=Cap,"compiler order log cap");file.write(b,o,n)}
      override def close():Unit=file.close()
    }
    val ps=new PrintStream(bounded,false,"UTF-8")
    var failure:Throwable=null
    try Logger.makeScope(){
      // Observation-only logger configuration; no input/execution annotation
      // is added or removed. Nested official Logger.makeScope retains this
      // explicit class level, as pinned Logger.setOptions only adds overrides.
      Logger.setLevel("firrtl2.stage.phases.Compiler",LogLevel.Info);Logger.setOutput(ps)
      val value=f;ps.flush();require(!ps.checkError(),"complete compiler order log");value
    }catch{case t:Throwable=>failure=t;throw t}
    finally {try{ps.close();require(!ps.checkError(),"closed compiler log")}catch{case t:Throwable=>if(failure!=null)failure.addSuppressed(t)else throw t}}
  }
  private def parsed(formal:Boolean):CircuitState={
    val base=if(formal) """circuit TinyFormal :
  extmodule ResetSeen :
    input clock : Clock
    input reset : UInt<1>
    output out : UInt<1>
    defname = circt_has_been_reset
  module TinyFormal :
    input clock : Clock
    input reset : UInt<1>
    output out : UInt<1>
    inst seen of ResetSeen
    seen.clock <= clock
    seen.reset <= reset
    out <= seen.out
""" else """circuit TinyBasic :
  module TinyBasic :
    input clock : Clock
    input reset : UInt<1>
    input asyncReset : AsyncReset
    input in : { x : UInt<8>[2], y : UInt<1> }
    output out : UInt<8>
    reg sr : UInt<8>, clock with :
      reset => (reset, UInt<8>(3))
    reg ar : UInt<8>, clock with :
      reset => (asyncReset, UInt<8>(5))
    mem store :
      data-type => UInt<8>
      depth => 4
      reader => r
      writer => w
      read-latency => 1
      write-latency => 1
      read-under-write => undefined
    store.r.clk <= clock
    store.r.en <= UInt<1>(1)
    store.r.addr <= UInt<2>(0)
    store.w.clk <= clock
    store.w.en <= in.y
    store.w.addr <= UInt<2>(0)
    store.w.data <= in.x[0]
    store.w.mask <= UInt<1>(1)
    sr <= in.x[1]
    ar <= store.r.data
    out <= xor(sr, ar)
"""
    val c=firrtl2.Parser.parse(base)
    CircuitState(c,Seq(TargetDirAnnotation("target"),DontTouchAnnotation(CircuitTarget(c.main).module(c.main).ref("out"))))
  }
  def main(args:Array[String]):Unit={
    require(args.length==3 && Set("baseline","candidate")(args(0)) && Set("basic","formal","matrix","idma","diagnostics")(args(1)))
    require(java.nio.charset.Charset.defaultCharset()==UTF_8,"fixed baseline emitter default byte encoding")
    require(!Files.exists(evidence) && !Files.exists(Paths.get("target")),"fresh owned fixture directory")
    Files.createDirectory(evidence)
    val high=args(1)match{
      case "basic"=>parsed(false)
      case "formal"=>parsed(true)
      case "matrix"=>Compiler.elaborate(()=>new LoweringOriginalMatrixPair,Seq(TargetDirAnnotation("target")),Seq.empty)._1
      case "idma"=>Compiler.elaborate(()=>new LoweringOriginalIdmaAdapter,Seq(TargetDirAnnotation("target")),Seq.empty)._1
      case "diagnostics"=>Compiler.elaborate(()=>new LoweringChiselDiagnostics,Seq(TargetDirAnnotation("target")),Seq.empty)._1
    }
    val diagnosticLiterals=if(args(1)=="diagnostics"){
      val literals=scala.collection.mutable.ArrayBuffer.empty[String]
      def scan(s:firrtl2.ir.Statement):Unit={s match{case p:firrtl2.ir.Print=>literals+=p.string.string;case _=>()};s.foreachStmt(scan)}
      high.circuit.modules.foreach(_.foreachStmt(scan))
      val assertions=literals.filter(_.contains("Assertion failed"))
      require(assertions.size>=2 && assertions.forall(_.contains("OfficialLoweringDifferential.scala:")),"actual assertion macro embeds basename and line")
      require(assertions.forall(x=> !x.contains("/workspace/") && !x.contains("workspace/scratch/") && !x.contains("home/runner/work/")),"no full source filename inserted into assertion diagnostic literal")
      require(literals.exists(_.contains("keep user path /workspace/synthetic/literal.scala")),"user literal path preserved verbatim")
      text("diagnostic_literals.json",json(JArray(literals.map(JString).toList)))
    }else JNull
    val originalInput=text("original_input.fir",high.circuit.serialize)
    val inputAnnotations=text("original_input.annos.json",JsonProtocol.serialize(high.annotations))
    val idma=high.circuit.modules.collect{case e:ExtModule if e.defname=="idma_backend_rw_axi_flat_wrap"=>e}
    val selected=if(args(1)=="idma"){
      require(idma.size==1 && args(2)=="b40e61c5ba679e163b12d2129a5c5ef6bc37cde6614e9ea7fee3ee7e8e817e4d","independently captured original local iDMA pin")
      high.copy(circuit=IdmaFieldSplitTransform(high.circuit,args(2)))
    }else{require(args(2)=="none");high}
    val selectedInput=text("selected_input.fir",selected.circuit.serialize)
    val before=phaseFiles;require(before.isEmpty,"elaboration emitted no unaccounted file")
    val(raw,low,emitted,delegate)=if(args(0)=="candidate"){
      val r=withOrderLog("compiler_order.log"){OfficialLowFirrtlFinalWriterOmission.lower(selected)}
      (r.rawStageAnnotations,r.state,r.emitted,r.delegationPhaseName)
    }else{
      val defaults=Seq(RunFirrtlTransformAnnotation(Dependency(chiseltest.sequences.ConvertCirctSequenceIntrinsics)))
      val ann=defaults++:(FirrtlCircuitAnnotation(selected.circuit)+:selected.annotations)
      val r=withOrderLog("compiler_order.log"){(new FirrtlStage).execute(Array("-E","low"),ann)}
      val es=r.collect{case e:EmittedFirrtlCircuitAnnotation=>e};require(es.size==1)
      val converted=Compiler.annosToState(r)
      val initialActual=Files.readAllBytes(Paths.get("target",selected.circuit.main+".lo.fir"))
      require(java.util.Arrays.equals(initialActual,es.head.getBytes.toArray),"actual first baseline file equals exact emitted bytes")
      val direct=withOrderLog("direct_compiler_order.log"){Compiler.toLowFirrtl(selected)}
      require(direct.circuit.serialize==converted.circuit.serialize,"direct official Compiler returned circuit parity")
      require(JsonProtocol.serialize(direct.annotations)==JsonProtocol.serialize(converted.annotations),"direct official Compiler returned ordered annotation parity")
      require(java.util.Arrays.equals(initialActual,Files.readAllBytes(Paths.get("target",selected.circuit.main+".lo.fir"))),"both official paths wrote identical actual file bytes")
      (r,converted,es.head,"OFFICIAL_FIRRTL_STAGE_EXECUTE")
    }
    val after=phaseFiles
    require(after==(if(args(0)=="baseline")Vector("target/"+selected.circuit.main+".lo.fir")else Vector.empty),"only terminal low writer filesystem difference")
    if(args(1)=="formal"){
      require(!low.circuit.modules.exists{case e:ExtModule=>e.defname=="circt_has_been_reset";case _=>false},"official default pass removed its intrinsic")
      require(low.annotations.exists(_.getClass.getName.contains("Preset")),"official default pass initialization annotations retained")
    }
    val circuitObjects=new IdentityHashMap[Circuit,Integer]();var next=0
    def circuit(c:Circuit):JValue={
      var id=circuitObjects.get(c)
      if(id==null){id=Integer.valueOf(next);next+=1;circuitObjects.put(c,id);text(f"circuit_${id.intValue}%03d.fir",c.serialize)}
      JObject(List("object"->JInt(id.intValue),"inputObject"->JBool(c eq selected.circuit),"returnedObject"->JBool(c eq low.circuit)))
    }
    circuit(selected.circuit)
    def anno(a:Annotation):JValue={
      val content:JValue=a match{
        case FirrtlCircuitAnnotation(c)=>JObject(List("circuit"->circuit(c)))
        case DeletedAnnotation(name,inner)=>JObject(List("phase"->JString(name),"deleted"->anno(inner)))
        case e:EmittedFirrtlCircuitAnnotation=>JObject(List("name"->JString(e.value.name),"suffix"->JString(e.value.outputSuffix),"value"->JString(e.value.value)))
        case _=>JsonMethods.parse(JsonProtocol.serialize(Seq(a)))
      }
      JObject(List("class"->JString(a.getClass.getName),"inputAnnotationObjectIndices"->JArray(selected.annotations.zipWithIndex.collect{case(x,i)if x eq a=>JInt(i)}.toList),"content"->content))
    }
    val rawRecord=text("raw_annotations.json",json(JArray(raw.map(anno).toList)))
    val returnedRecord=text("returned_annotations.json",json(JArray(low.annotations.map(anno).toList)))
    val returnedCircuit=circuit(low.circuit)
    val emitter=text("emitted_annotation.fir",emitted.value.value)
    val actual=if(args(0)=="baseline")save("actual_closed_low_file.fir",Files.readAllBytes(Paths.get("target",selected.circuit.main+".lo.fir")))else JNull
    val boundary=if(args(1)=="idma"){
      val result=IdmaPackedBoundarySplit(low.circuit,idma.head.name)
      firrtl2.passes.CheckTypes.run(result.circuit);firrtl2.passes.CheckFlows.run(result.circuit)
      text("packed_boundary.fir",result.circuit.serialize)
    }else JNull
    require(selected.circuit.serialize==new String(Files.readAllBytes(evidence.resolve("selected_input.fir")),UTF_8),"original selected input remained unchanged")
    val receipt=JObject(List("status"->JString("SMALL_DIFFERENTIAL_ARTIFACTS_PENDING_EXTERNAL_COMPARISON_AND_SUPERVISOR"),
      "route"->JString(args(0)),"fixture"->JString(args(1)),"delegate"->JString(delegate),
      "originalInput"->originalInput,"inputAnnotations"->inputAnnotations,"selectedInput"->selectedInput,
      "rawAnnotations"->rawRecord,"returnedAnnotations"->returnedRecord,"returnedCircuit"->returnedCircuit,
      "emittedAnnotation"->emitter,"actualClosedLowFile"->actual,"packedBoundary"->boundary,
      "diagnosticLiterals"->diagnosticLiterals,
      "phaseFilesBefore"->JArray(before.map(JString).toList),"phaseFilesAfter"->JArray(after.map(JString).toList),
      "nativeLoaded"->JBool(false),"hostElaborated"->JBool(false),"runtimeQualified"->JBool(false)))
    text("RESULT.json",json(receipt))
  }
}
