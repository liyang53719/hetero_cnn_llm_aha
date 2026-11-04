package chiseltest.simulator

import firrtl2.{CircuitState,Parser}
import firrtl2.annotations.JsonProtocol
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.{IdmaFieldSplitTransform,StructuralMetadataFactory}
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths}
import java.security.MessageDigest
import org.json4s.{JArray,JObject,JString}
import org.json4s.native.JsonMethods
import treadle2.TreadleCircuitStateAnnotation
import treadle2.executable.SymbolTable
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
    private var tail=""
    private def inspect(text:String):Unit={
      val joined=tail+text
      if(Seq("WARNING:","Warning:","SymbolTable:TODO:").exists(joined.contains))unsupported=true
      tail=joined.takeRight(64)
    }
    override def write(b:Int):Unit={bytes+=1;require(bytes<=8L*1024*1024,"diagnostic byte cap");inspect((b&255).toChar.toString)}
    override def write(b:Array[Byte],off:Int,len:Int):Unit={bytes+=len;require(bytes<=8L*1024*1024,"diagnostic byte cap");inspect(new String(b,off,len,UTF_8))}
  }
  def main(args:Array[String]):Unit={
    val savedOut=System.out;val savedErr=System.err
    val sink=new DiagnosticSink;val muted=new PrintStream(sink,true,"UTF-8")
    var stage="admission";var result="FAIL_STRUCTURAL_GRAPH_ONLY stage=admission";var failed=true
    try {
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        require(args.length==5,"high path,high SHA,annotations path,annotations SHA,original iDMA extmodule SHA")
        require(Files.getFileStore(Paths.get(args(0)).toAbsolutePath).getUsableSpace>=8L*1024*1024*1024,"unchanged8GiB reserve")
        stage="read"
        val highText=readPinned(args(0),args(1),512L*1024*1024)
        val annotationText=readPinned(args(2),args(3),16L*1024*1024)
        checkInputAnnotations(annotationText)
        stage="parse"
        val circuit=Parser.parse(highText)
        val annotations=JsonProtocol.deserialize(annotationText)
        require(circuit.serialize==highText,"exact original high parse/serialize roundtrip")
        require(JsonProtocol.serialize(annotations)==annotationText,"exact original annotation roundtrip")
        require(circuit.main=="HostBlockTopV4","actual original Host top")
        val high=CircuitState(circuit,annotations)
        check(high)
        stage="split"
        val split=IdmaFieldSplitTransform(high.circuit,args(4))
        val selected=high.copy(circuit=split)
        require(selected.annotations eq high.annotations,"preserved initialization annotations")
        val originalBindings=new StructuralMetadataFactory(split,seed=true).bindings
        stage="official_lower"
        val low=Compiler.toLowFirrtl(selected)
        check(low)
        require(new StructuralMetadataFactory(low.circuit,seed=true).bindings==originalBindings,"same lowered leaf inventory")
        require(TopmoduleInfo(low.circuit).clocks==Seq("clock"),"original clock")
        stage="official_prepare"
        val ann=FirrtlCircuitAnnotation(low.circuit)+:low.annotations
        val prepared=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(ann)))
        val states=prepared.collect{case TreadleCircuitStateAnnotation(s)=>s}
        require(states.size==1,"one actual prepared AST")
        require(!states.head.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported prepared annotation")
        val factory=new StructuralMetadataFactory(states.head.circuit,seed=true)
        require(factory.bindings==originalBindings,"same prepared leaf inventory")
        stage="symbol_table"
        val table=SymbolTable(states.head.circuit,Seq(factory),allowCycles=false)
        factory.requireComplete()
        require(!sink.unsupported,"unhandled/warning library diagnostic")
        stage="summary"
        result="PASS_DECLARED_CONE_TOPOLOGY_ONLY highSha="+args(1)+" annotationsSha="+args(3)+
          " preparedSha="+hash(states.head.circuit.serialize)+" symbols="+table.size+
          " leafBindings=17 nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false"
        failed=false
      }}
    }catch{case error:Throwable=>
      result="FAIL_STRUCTURAL_GRAPH_ONLY stage="+stage+" exceptionClassSha="+hash(error.getClass.getName)+
        " nativeInstances=0 evaluatedEdges=0 schedulingQualified=false fullHostAccepted=false"
    }finally{
      System.setOut(savedOut);System.setErr(savedErr)
    }
    savedOut.println(result+" suppressedDiagnosticBytes="+sink.bytes)
    savedOut.flush()
    if(failed)System.exit(2)
  }
}
