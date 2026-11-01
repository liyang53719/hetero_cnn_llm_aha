package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.{JsonProtocol,CircuitTarget}
import firrtl2.options.TargetDirAnnotation
import firrtl2.transforms.DontTouchAnnotation
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.nio.charset.StandardCharsets.UTF_8
object ModelCandidateHelperFixture extends App {
  require(args.length==1&&Set("success","failure","module_order")(args(0)))
  def write(p:String,s:String):Unit=Files.write(Paths.get(p),s.getBytes(UTF_8),StandardOpenOption.CREATE_NEW)
  def read(p:String)=new String(Files.readAllBytes(Paths.get(p)),UTF_8)
  val modules=Seq(Module(NoInfo,"HostBlockTopV4",Seq(Port(NoInfo,"clock",Input,ClockType)),EmptyStmt),Module(NoInfo,"UnusedFixture",Seq.empty,EmptyStmt))
  val high=Circuit(NoInfo,modules,"HostBlockTopV4")
  val ann=JsonProtocol.serialize(Seq(TargetDirAnnotation("host-diagnostic"),DontTouchAnnotation(CircuitTarget("HostBlockTopV4").module("HostBlockTopV4").ref("clock"))))
  write("tiny-high.fir",high.serialize);write("tiny-annotations.json",ann)
  if(args(0)=="success"){
    ModelCandidateHighDescriptorV1.main(Array("tiny-high.fir","tiny-annotations.json","canonical.tsv","details.json","ordered-annotations.json"))
    val d=ujson.read(read("details.json"));require(d("modules").arr.size==2&&d("main").str=="HostBlockTopV4")
    require(d("scope").str=="OBSERVED_UNREVIEWED_NOT_NUMERICAL_OR_STRUCTURE_ACCEPTANCE")
    require(d("annotations")("count").num==2&&d("annotations")("target_dir_count").num==1)
    require(read("canonical.tsv")==new String(ModelCandidateHighDescriptorV1.rows(high,ann),UTF_8))
    require(JsonProtocol.deserialize(read("ordered-annotations.json")).size==1)
    val diag=ujson.read(read("MODEL_CANDIDATE_DIAGNOSTIC.json"));require(diag("status").str=="OBSERVED_COMPLETE_UNREVIEWED"&&diag("reason_code").str=="NONE")
  }else{
    var rejected=false
    try {
      if(args(0)=="failure")ModelCandidateHighDescriptorV1.main(Array("PRIVATE_SECRET_SENTINEL_missing.fir","tiny-annotations.json","canonical.tsv","details.json","ordered-annotations.json"))
      else{
        val rows=new String(ModelCandidateHighDescriptorV1.rows(high,ann),UTF_8).split("\n").toSeq
        val changed=(rows.take(4)++rows.drop(4).reverse).mkString("","\n","\n")
        write("reordered.tsv",changed)
        ModelCandidateTransformGateV1.main(Array("tiny-high.fir","reordered.tsv",ModelCandidateHighDescriptorV1.sha(changed.getBytes(UTF_8)),"transform.json"))
      }
    }catch{case scala.util.control.NonFatal(_)=>rejected=true}
    require(rejected,"strict deliberate counterexample rejected")
    val raw=read("MODEL_CANDIDATE_DIAGNOSTIC.json");require(!raw.contains("PRIVATE_SECRET_SENTINEL")&&raw.getBytes(UTF_8).length<=8192)
    val d=ujson.read(raw);require(d("status").str=="REJECTED_UNREVIEWED")
    require(d("reason_code").str==(if(args(0)=="failure")"INPUT_BOUNDS_OR_PIN" else "CANONICAL_IDENTITY"))
    require(!d("numerical_pass").bool&& !d("post_build_structure_accepted").bool)
  }
  println("TINY_AST_DESCRIPTOR_AND_FINITE_DIAGNOSTIC_"+args(0)+"_PASS_NOT_HOST_OR_NUMERIC_QUALIFICATION")
}
