package chiseltest.simulator

import firrtl2.{CircuitState,CDefMemory,CDefMPort,MRead}
import firrtl2.annotations.{CircuitTarget,JsonProtocol}
import firrtl2.ir._
import firrtl2.options.{TargetDirAnnotation,InputAnnotationFileAnnotation,OutputAnnotationFileAnnotation,Dependency}
import firrtl2.stage.{FirrtlFileAnnotation,RunFirrtlTransformAnnotation}
import firrtl2.transforms.DontTouchAnnotation
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest
import scala.collection.mutable.ArrayBuffer

/** SOURCE-ONLY small structural/hash fixture. No lowering or native execution.
  * CLI: historicalRemoteExtPath actualCapturedLocalExtPath. Both exact small
  * artifacts are SHA-pinned below. Requires a fresh owned working directory.
  */
object SourceInfoRebindingDifferential {
  import ExactHighSourceInfoRebinding._
  private val local="local/\u6e90\ud83d\ude00.scala"
  private val remote="remote/\u6e90\ud83d\ude00.scala"
  private val limits=Limits(10000,20000,128,4*1024*1024)
  private def sha(s:String)=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(x=>f"${x&255}%02x").mkString
  private def fixture(file:String):CircuitState={
    val i=new MultiInfo(Seq(FileInfo.fromEscaped(file+" 0007:009"),NoInfo,
      new MultiInfo(Seq(FileInfo.fromEscaped("fixed/library.scala 1:2"),FileInfo.fromEscaped(file+" 8:2")))))
    val u=UIntType(IntWidth(8));val clk=Reference("clock",ClockType);val one=UIntLiteral(1,IntWidth(1));val zero=UIntLiteral(0,IntWidth(8))
    val ports=Seq(Port(i,"clock",Input,ClockType),Port(NoInfo,"reset",Input,UIntType(IntWidth(1))),Port(i,"out",Output,u))
    val innerEmpty=Block(Seq(EmptyStmt))
    val deeper=Block(Seq(EmptyStmt,innerEmpty))
    val nested=Block(Seq(EmptyStmt,DefWire(i,"nestedWire",u),deeper))
    val body=Block(Seq(EmptyStmt,nested,DefWire(i,"wire",u),DefRegister(i,"reg",u,clk,Reference("reset"),zero),
      DefNode(i,"node",zero),DefInstance(i,"ext","Leaf"),
      DefMemory(i,"memory",u,4,1,1,Seq("r"),Seq("w"),Seq.empty),
      CDefMemory(i,"chirrtlMemory",u,4,true),CDefMPort(i,"mport",u,"chirrtlMemory",Seq(zero,clk),MRead),
      Conditionally(i,one,Block(Seq(EmptyStmt,Block(Seq(Connect(i,Reference("out"),Reference("reg")),EmptyStmt)),EmptyStmt)),EmptyStmt),
      IsInvalid(i,Reference("wire")),Attach(i,Seq(Reference("wire"))),
      Stop(i,0,clk,one),Print(i,StringLit(local),Seq.empty,clk,one),
      Verification(Formal.Assert,i,clk,one,one,StringLit(local))))
    val leaf=ExtModule(i,"Leaf",Seq(Port(i,"data",Input,u)),"Leaf",Seq(StringParam("SOURCE_TEXT",StringLit(local))))
    val c=Circuit(i,Seq(leaf,Module(i,"TinyInfo",ports,body)),"TinyInfo")
    CircuitState(c,Seq(TargetDirAnnotation("target"),DontTouchAnnotation(CircuitTarget(c.main).module(c.main).ref("out"))))
  }
  def main(args:Array[String]):Unit={
    require(args.length==2 && !Files.exists(Paths.get("RESULT.json")))
    val reports=ArrayBuffer.empty[String];val observations=ArrayBuffer.empty[Evidence]
    var artifactBytes=0L
    def save(name:String,content:String):Unit={
      val bytes=content.getBytes(UTF_8);require(bytes.length<=1024*1024,"bounded complete fixture artifact")
      require(artifactBytes<=8L*1024*1024-bytes.length,"bounded aggregate incremental fixture evidence")
      Files.write(Paths.get(name),bytes,StandardOpenOption.CREATE_NEW);artifactBytes+=bytes.length
    }
    def evidenceJson(e:Evidence):org.json4s.JValue={
      org.json4s.JObject(List("rawSha256"->org.json4s.JString(e.raw.sha256),"rawBytes"->org.json4s.JInt(e.raw.bytes),
        "reboundSha256"->e.rebound.map(x=>org.json4s.JString(x.sha256)).getOrElse(org.json4s.JNull),
        "syntaxNodes"->org.json4s.JInt(e.syntaxNodes),"infoNodes"->org.json4s.JInt(e.infoNodes),
        "completedRebinding"->org.json4s.JBool(e.completedRebinding),
        "changed"->org.json4s.JArray(e.changedFilenameCounts.map{x=>org.json4s.JObject(List(
          "local"->org.json4s.JString(x.localEscaped),"remote"->org.json4s.JString(x.remoteEscaped),"occurrences"->org.json4s.JInt(x.occurrences)))}.toList),
        "unchanged"->org.json4s.JArray(e.unchangedFilenameCounts.map{case(n,c)=>org.json4s.JObject(List("filename"->org.json4s.JString(n),"occurrences"->org.json4s.JInt(c)))}.toList)))
    }
    def record(e:Evidence):Unit={
      observations+=e
      save(f"observation_${observations.size}%04d.json",org.json4s.native.JsonMethods.compact(org.json4s.native.JsonMethods.render(evidenceJson(e))))
    }
    val a=fixture(local);val expected=fixture(remote);val expectedHash=sha(expected.circuit.serialize)
    save("synthetic.raw.fir",a.circuit.serialize);save("synthetic.expected.fir",expected.circuit.serialize)
    val result=rebind(a,Vector(FilenamePair(local,remote)),Set("fixed/library.scala"),expectedHash,limits,record)
    require(result.state.circuit.serialize==expected.circuit.serialize,"exact independent fixture bytes")
    require(result.state.annotations eq a.annotations)
    require(JsonProtocol.serialize(result.state.annotations)==JsonProtocol.serialize(a.annotations))
    require(result.raw.sha256==sha(a.circuit.serialize) && result.rebound.sha256==expectedHash)
    require(observations.size==2 && !observations.head.completedRebinding && observations.last.completedRebinding)
    def statementCount(s:Statement):Long={
      var children=0L;s.foreachStmt(x=>children+=statementCount(x));1L+children
    }
    val exactSyntaxCount=1L+a.circuit.modules.map{m=>1L+m.ports.size+(m match{
      case x:Module=>statementCount(x.body)
      case _:ExtModule=>0L
    })}.sum
    require(result.syntaxNodes==exactSyntaxCount,"all original nested Block and EmptyStmt containers counted")
    reports+="paired complete fixture, nested Blocks/EmptyStmt identity and exact syntax-node census"
    def originalExt(path:String,expectedSha:String,expectedBytes:Long):CircuitState={
      val p=Paths.get(path);require(Files.size(p)==expectedBytes,"exact original Ext artifact byte size")
      val bytes=Files.readAllBytes(p);val s=new String(bytes,UTF_8);require(sha(s)==expectedSha)
      val name="idma_backend_rw_axi_flat_wrap"
      val c=firrtl2.Parser.parse("circuit "+name+" :\n"+s.linesIterator.map("  "+_).mkString("\n")+"\n")
      require(c.modules.size==1 && c.modules.head.serialize==s,"exact original Ext parse roundtrip")
      CircuitState(c,Seq(TargetDirAnnotation("target"),DontTouchAnnotation(CircuitTarget(name).module(name).ref("clk_i"))))
    }
    val oldExt=originalExt(args(0),"85b299b3b237b70a8450315f887a2f8aad53bd86c95fb8d9a2ff943173cb4193",678)
    val localExt=originalExt(args(1),"b40e61c5ba679e163b12d2129a5c5ef6bc37cde6614e9ea7fee3ee7e8e817e4d",704)
    val oldFile=oldExt.circuit.modules.head.info.asInstanceOf[FileInfo].split._1
    val localFile=localExt.circuit.modules.head.info.asInstanceOf[FileInfo].split._1
    save("original_idma.raw.fir",localExt.circuit.serialize);save("original_idma.expected.fir",oldExt.circuit.serialize)
    val extResult=rebind(localExt,Vector(FilenamePair(localFile,oldFile)),Set.empty,sha(oldExt.circuit.serialize),limits,record)
    require(extResult.state.circuit.modules.head.serialize==oldExt.circuit.modules.head.serialize,"actual original Ext byte identity after only structured rebinding")
    reports+="pinned actual captured original iDMA Ext704-byte local/678-byte remote pair"
    for(c<-Seq(a.circuit,expected.circuit))require(digest(c,4*1024*1024).sha256==sha(c.serialize))
    val unicode="ASCII\u6e90\ud83d\ude00end\ud800!\udc00"
    for(n<-1 until unicode.length){
      require(digestChunks(Iterator(unicode.take(n),unicode.drop(n)),1024).sha256==sha(unicode),"UTF-8 writer split boundary "+n)
    }
    reports+="official lazy hash parity and every UTF-16 split boundary"
    def denied(name:String,expectedClass:Class[_ <: Exception]=classOf[IllegalArgumentException])(f: => Unit):Throwable={
      var failure:Throwable=null;try f catch{case t:Exception=>require(expectedClass.isInstance(t),"unexpected negative failure type: "+name+" "+t.getClass.getName);failure=t}
      require(failure!=null,"negative accepted: "+name);reports+=("rejected "+name);failure
    }
    def attempt(s:CircuitState=a,p:Vector[FilenamePair]=Vector(FilenamePair(local,remote)),unchanged:Set[String]=Set("fixed/library.scala"),
      hash:String=expectedHash,cap:Limits=limits,writer:Evidence=>Unit=record):Unit={rebind(s,p,unchanged,hash,cap,writer);()}
    denied("unknown filename"){attempt(unchanged=Set.empty)}
    denied("duplicate source"){attempt(p=Vector(FilenamePair(local,remote),FilenamePair(local,"other.scala")))}
    denied("duplicate destination"){attempt(p=Vector(FilenamePair(local,remote),FilenamePair("other.scala",remote)))}
    denied("chained paths"){attempt(p=Vector(FilenamePair(local,remote),FilenamePair(remote,"other.scala")))}
    denied("unchanged collision"){attempt(unchanged=Set("fixed/library.scala",remote))}
    denied("wrong fixed hash"){attempt(hash="0"*64)}
    denied("changed hardware"){attempt(s=a.copy(circuit=a.circuit.copy(main="Changed")))}
    denied("no line or column"){attempt(s=a.copy(circuit=a.circuit.copy(info=FileInfo.fromEscaped(local))))}
    denied("Info node cap"){attempt(cap=limits.copy(maxInfoNodes=1))}
    denied("syntax node cap"){attempt(cap=limits.copy(maxSyntaxNodes=1))}
    denied("depth cap"){attempt(cap=limits.copy(maxDepth=1))}
    denied("byte cap"){attempt(cap=limits.copy(maxSerializedBytes=1))}
    denied("evidence write failure",classOf[IllegalStateException]){attempt(writer=_=>throw new IllegalStateException("evidence sink failure"))}
    var writes=0
    val primary=denied("mapping plus evidence failure"){
      attempt(hash="0"*64,writer=_=>{writes+=1;if(writes==2)throw new IllegalStateException("secondary evidence failure")})
    }
    require(primary.getMessage.contains("fixed remote full high identity") && primary.getSuppressed.length==1)
    val badAnnotations=Seq(InputAnnotationFileAnnotation("must_not_read.json"),OutputAnnotationFileAnnotation("must_not_write.json"),
      FirrtlFileAnnotation("must_not_read.fir"),RunFirrtlTransformAnnotation(Dependency(chiseltest.sequences.ConvertCirctSequenceIntrinsics)),TargetDirAnnotation("second"))
    badAnnotations.foreach{anno=>
      val s=a.copy(annotations=a.annotations:+anno)
      denied("rebinding annotation "+anno.getClass.getName){attempt(s=s)}
      denied("lowering annotation "+anno.getClass.getName){OfficialLowFirrtlFinalWriterOmission.lower(s);()}
    }
    require(!Files.exists(Paths.get("target")) && !Files.exists(Paths.get("must_not_write.json")),"negative gates caused no compiler/file side effects")
    save("synthetic.rebound.fir",result.state.circuit.serialize)
    save("original_idma.rebound.fir",extResult.state.circuit.serialize)
    val observedJson=org.json4s.JArray(observations.map(evidenceJson).toList)
    save("OBSERVATIONS.json",org.json4s.native.JsonMethods.compact(org.json4s.native.JsonMethods.render(observedJson)))
    val output=org.json4s.JObject(List("status"->org.json4s.JString("SMALL_STRUCTURAL_DIFFERENTIAL_PENDING_SUPERVISOR_CLEANUP"),
      "checks"->org.json4s.JArray(reports.map(org.json4s.JString).toList),"rawSha256"->org.json4s.JString(result.raw.sha256),
      "reboundSha256"->org.json4s.JString(result.rebound.sha256),"nativeLoaded"->org.json4s.JBool(false),
      "hostElaborated"->org.json4s.JBool(false),"runtimeQualified"->org.json4s.JBool(false)))
    save("RESULT.json",org.json4s.native.JsonMethods.compact(org.json4s.native.JsonMethods.render(output)))
  }
}
