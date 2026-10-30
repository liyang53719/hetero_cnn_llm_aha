package chiseltest.simulator
import java.nio.file.{Files,Paths}
import java.nio.charset.StandardCharsets.UTF_8
object DescriptorFixture {
 def main(a:Array[String]):Unit={
  val c=firrtl2.Parser.parse("circuit HostBlockTopV4 :\n  module HostBlockTopV4 :\n    input clock : Clock\n    input reset : UInt<1>\n    skip\n")
  Files.write(Paths.get("fixture-high.fir"),c.serialize.getBytes(UTF_8))
  val ann=Seq(firrtl2.options.TargetDirAnnotation("fixture-not-exported"))
  Files.write(Paths.get("fixture-ann.json"),firrtl2.annotations.JsonProtocol.serialize(ann).getBytes(UTF_8))
  Files.write(Paths.get("fixture-ports.fir"),"input clock : Clock\ninput reset : UInt<1>\noutput io_observation : UInt<32>\n".getBytes(UTF_8))
  ObservedHighDescriptor.main(Array("fixture-high.fir","fixture-ann.json","fixture-ports.fir","observed-canonical.tsv","observed-details.json"))
  val bytes=Files.readAllBytes(Paths.get("observed-canonical.tsv"))
  require(new String(bytes,UTF_8).contains("circuit\t"+CanonicalHighGate.circuitSemanticSha(c)))
  val detail=new String(Files.readAllBytes(Paths.get("observed-details.json")),UTF_8)
  require(detail.contains("\"module_count\":1")&&detail.contains("\"annotation_count\":1"))
  require(detail.contains("\"name\":\"clock\",\"direction\":\"input\",\"type\":\"Clock\",\"width\":1"))
  require(detail.contains("\"name\":\"io_observation\",\"direction\":\"output\",\"type\":\"UInt<32>\",\"width\":32"))
  println("TINY_OFFICIAL_PARSER_DESCRIPTOR_FIXTURE_PASS_NOT_REAL_IR")
 }
}
