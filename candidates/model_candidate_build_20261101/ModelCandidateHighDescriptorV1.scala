// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.JsonProtocol
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest

/** Read-only actual identity observation. Its output is NOT an independently
  * accepted baseline and authorizes neither execution nor numerical acceptance.
  * Reuses original public semantic methods: ONLY Info/TargetDir are excluded;
  * module and annotation order, targets, all logic and types are preserved. */
object ModelCandidateHighDescriptorV1 {
  val Header="MODEL_CANDIDATE_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1"
  def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  def read(path:String,cap:Long):Array[Byte]={
    val p=Paths.get(path);require(Files.isRegularFile(p)&& !Files.isSymbolicLink(p),"regular observed input")
    require(Files.size(p)>0&&Files.size(p)<=cap,"bounded observed input");Files.readAllBytes(p)
  }
  def write(path:String,b:Array[Byte],cap:Int):Unit={require(b.length<=cap,"bounded descriptor output");Files.write(Paths.get(path),b,StandardOpenOption.CREATE_NEW)}
  def id(s:String):String={require(s.matches("[A-Za-z_$][A-Za-z0-9_$]*")&&s.length<=256,"bounded actual identifier");s}
  def rows(c:Circuit,annotations:String):Array[Byte]={
    require(c.main=="HostBlockTopV4"&&c.modules.nonEmpty&&c.modules.size<=4096)
    require(c.modules.map(_.name).distinct.size==c.modules.size);c.modules.foreach(m=>id(m.name))
    (Seq(Header,"main\t"+c.main,"circuit\t"+CanonicalHighGate.circuitSemanticSha(c),
      "annotations_order_preserved\t"+CanonicalHighGate.annotationSemanticSha(annotations))++
      c.modules.map(m=>"module\t"+m.name+"\t"+CanonicalHighGate.moduleSemanticSha(m))).mkString("","\n","\n").getBytes(UTF_8)
  }
  def main(a:Array[String]):Unit=ModelCandidateDiagnosticV1.run("canonical_full"){
    ModelCandidateDiagnosticV1.phase("INPUT_BOUNDS_OR_PIN")
    require(a.length==5,"HIGH annotations NEW-canonical.tsv NEW-details.json NEW-ordered-annotations.json")
    val raw=read(a(0),384L<<20);val ann=read(a(1),16L<<20)
    ModelCandidateDiagnosticV1.number("high_bytes",raw.length);ModelCandidateDiagnosticV1.hash("high_sha256",sha(raw))
    ModelCandidateDiagnosticV1.number("annotation_bytes",ann.length);ModelCandidateDiagnosticV1.hash("annotations_sha256",sha(ann))
    ModelCandidateDiagnosticV1.phase("HIGH_ROUNDTRIP")
    val c=firrtl2.Parser.parse(new String(raw,UTF_8));require(java.util.Arrays.equals(c.serialize.getBytes(UTF_8),raw),"exact HIGH roundtrip including Info")
    ModelCandidateDiagnosticV1.number("module_count",c.modules.size);ModelCandidateDiagnosticV1.phase("ANNOTATION_ROUNDTRIP")
    val as=JsonProtocol.deserialize(new String(ann,UTF_8));require(JsonProtocol.serialize(as)==new String(ann,UTF_8),"exact annotation roundtrip")
    ModelCandidateDiagnosticV1.number("annotation_count",as.size);ModelCandidateDiagnosticV1.phase("ANNOTATION_CLASS_TARGET")
    require(as.nonEmpty&&as.size<=100000,"bounded actual annotation count")
    val dirs=as.count(_.isInstanceOf[firrtl2.options.TargetDirAnnotation]);require(dirs==1,"one actual TargetDir")
    ModelCandidateDiagnosticV1.number("target_dir_count",dirs)
    val kept=JsonProtocol.serialize(as.filterNot(_.isInstanceOf[firrtl2.options.TargetDirAnnotation])).getBytes(UTF_8)
    require(kept.length<=2*1024*1024,"bounded complete ordered annotation metadata; never truncate")
    ModelCandidateDiagnosticV1.phase("CANONICAL_IDENTITY")
    val canonical=rows(c,new String(ann,UTF_8))
    ModelCandidateDiagnosticV1.hash("canonical_sha256",sha(canonical))
    val modules=ujson.Arr.from(c.modules.map(m=>ujson.Obj("name"->id(m.name),"sha256"->CanonicalHighGate.moduleSemanticSha(m))))
    val details=ujson.Obj("schema"->"MODEL_CANDIDATE_HIGH_DESCRIPTOR_V1","scope"->"OBSERVED_UNREVIEWED_NOT_NUMERICAL_OR_STRUCTURE_ACCEPTANCE",
      "main"->c.main,"high"->ujson.Obj("bytes"->raw.length,"sha256"->sha(raw)),
      "annotations"->ujson.Obj("bytes"->ann.length,"sha256"->sha(ann),"count"->as.size,"target_dir_count"->dirs,"ordered_sha256"->sha(kept),"ordered_bytes"->kept.length),
      "canonical_tsv"->ujson.Obj("bytes"->canonical.length,"sha256"->sha(canonical)),"circuit_sha256"->CanonicalHighGate.circuitSemanticSha(c),"modules"->modules)
    ModelCandidateDiagnosticV1.phase("METADATA_BOUNDS")
    write(a(2),canonical,512<<10);write(a(3),(ujson.write(details,indent=2)+"\n").getBytes(UTF_8),1<<20);write(a(4),kept,2<<20)
    println("MODEL_CANDIDATE_DESCRIPTOR_OBSERVED_UNREVIEWED_NOT_ACCEPTANCE")
  }
}

/** Finite failure telemetry only. No exception text, path, IR, annotation body,
  * argv or arbitrary string is copied. All categories come from code phases. */
object ModelCandidateDiagnosticV1 {
  private val Reasons=Set("NONE","INPUT_BOUNDS_OR_PIN","HIGH_ROUNDTRIP","ANNOTATION_ROUNDTRIP","ANNOTATION_CLASS_TARGET",
    "CANONICAL_IDENTITY","FIXED_MODULE_HASH","FIXED_PROVIDER_BINDINGS","BANK_SUBTREE_HASH","FIFO_LOCAL_SHAPE",
    "DENSE_ACC_LOCAL_SHAPE","LOW_LOWERING","LOW_SERIALIZATION","FINAL_CONNECTORS","TOP_PORT_ABI","SV_EMISSION","METADATA_BOUNDS","INTERNAL_UNCLASSIFIED")
  private val NumberKeys=Set("high_bytes","annotation_bytes","module_count","annotation_count","target_dir_count","low_port_count","reachable_instance_count","fixed_module_index","bank_subtree_module_index","dense_bulk_writes","dense_zero_tiles","dense_zero_rows","dense_zero_elements")
  private val HashKeys=Set("high_sha256","annotations_sha256","canonical_sha256","failing_module_sha256")
  private var current="INTERNAL_UNCLASSIFIED"
  private val actual=ujson.Obj()
  def phase(reason:String):Unit={require(Reasons(reason));current=reason}
  def number(key:String,value:Long):Unit={require(NumberKeys(key)&&value>=0&&value<=9007199254740991L);actual(key)=ujson.Num(value.toDouble)}
  def hash(key:String,value:String):Unit={require(HashKeys(key)&&value.matches("[0-9a-f]{64}"));actual(key)=ujson.Str(value)}
  private def record(stage:String,status:String,reason:String):Unit={
    val doc=ujson.Obj("schema"->"MODEL_CANDIDATE_DIAGNOSTIC_V1","stage"->stage,"status"->status,"reason_code"->reason,"actual"->actual,
      "numerical_pass"->false,"post_build_structure_accepted"->false)
    ModelCandidateHighDescriptorV1.write("MODEL_CANDIDATE_DIAGNOSTIC.json",(ujson.write(doc,indent=2)+"\n").getBytes(UTF_8),8192)
  }
  def run(stage:String)(body: =>Unit):Unit={
    require(Set("canonical_full","transform_new_toolchain","emit_host")(stage))
    current="INTERNAL_UNCLASSIFIED";actual.obj.clear()
    try {body;record(stage,"OBSERVED_COMPLETE_UNREVIEWED","NONE")}
    catch {case scala.util.control.NonFatal(e)=>
      if(current=="DENSE_ACC_LOCAL_SHAPE" || e.isInstanceOf[heteronpu.continuous.model.CandidateDenseAccMemoryLoweringV2.DenseShapeRejected]){
        current="DENSE_ACC_LOCAL_SHAPE"
        import heteronpu.continuous.model.CandidateDenseAccMemoryLoweringV2
        val code=e match {
          case d:CandidateDenseAccMemoryLoweringV2.DenseShapeRejected=>
            d.counts.foreach{case(k,v)=>number(k,v)};d.code
          case _=>"INTERNAL_UNCLASSIFIED"
        }
        if(CandidateDenseAccMemoryLoweringV2.PredicateCodes(code))actual("dense_predicate_code")=ujson.Str(code)
        else actual("dense_predicate_code")=ujson.Str("INTERNAL_UNCLASSIFIED")
      }
      try {record(stage,"REJECTED_UNREVIEWED",current)}catch{case scala.util.control.NonFatal(_)=>()}
      throw e
    }
  }
}
