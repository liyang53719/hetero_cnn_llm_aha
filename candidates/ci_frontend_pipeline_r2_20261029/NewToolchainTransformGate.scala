package chiseltest.simulator
import firrtl2.ir._
import heteronpu.continuous.model._
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
object NewToolchainTransformGate {
 def main(a:Array[String]):Unit={
  require(a.length==2,"fresh high and NEW summary")
  val high=firrtl2.Parser.parse(new String(Files.readAllBytes(Paths.get(a(0))),UTF_8))
  val core=high.modules.find(_.name=="Qwen2ContinuousBlock").get
  val fifo=high.modules.find(_.name=="MatrixResultFifo").get
  val cp="9e3ba17f1c0f6353480abe57ef1db050b30cb953241df943cdcd043701286ca2"
  val fp="eb44e4267684bbb9cf265e88ea89a6910dedd67b2bd2896bb6367928d4ecf831"
  require(CanonicalHighGate.moduleSemanticSha(core)==cp && CanonicalHighGate.moduleSemanticSha(fifo)==fp)
  val sentinel=Module(NoInfo,"Sentinel",Seq.empty,EmptyStmt)
  val input=Circuit(NoInfo,Seq(core,fifo,sentinel),"Qwen2ContinuousBlock")
  val result=PortableHostDenseAccMemoryLowering(PortableHostMatrixResultFifoMemoryLowering(input,fp),cp)
  // This expected identity came from locally executed ORIGINAL transforms, then
  // independently reviewed root receipt. Never learn it from this new runner.
  require(CanonicalHighGate.circuitSemanticSha(result)=="0a41c5788f155c271859027d96c535d41a00fc7f94dd35f6d24f5c6469816073","new toolchain transformed AST differs from approved original-transform output")
  require(result.modules.last eq sentinel)
  require(result.modules(0).info==core.info && result.modules(1).info==fifo.info,"fresh Info must survive")
  Files.write(Paths.get(a(1)),"PASS_TRANSFORM_CANONICAL_IDENTITY_ONLY_NO_SV_OR_NUMERICS\n".getBytes(UTF_8),StandardOpenOption.CREATE_NEW)
 }
}
