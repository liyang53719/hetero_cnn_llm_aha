// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.JsonProtocol
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest
/** Read-only official parser identity inventory. No elaboration, transform, SV or simulation. */
object InspectFreshHostBackendInputs {
 private def sha(b:Array[Byte])=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
 private def sha(s:String):String=sha(s.getBytes(StandardCharsets.UTF_8))
 def main(args:Array[String]):Unit={
  require(args.length==3,"exact high, annotations and new output directory")
  val raw=Files.readAllBytes(Paths.get(args(0)))
  require(raw.length==98842098 && sha(raw)=="391774e80482befb9004f78ffb3cbbc6497f2a392e9729e97e648071026bd267","independently measured fresh high")
  val ab=Files.readAllBytes(Paths.get(args(1)))
  require(ab.length==1353384 && sha(ab)=="e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee","independently measured fresh annotations")
  val out=Paths.get(args(2));require(!Files.exists(out),"fresh output only");Files.createDirectories(out)
  def save(n:String,s:String):Unit=Files.write(out.resolve(n),s.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW)
  val c=firrtl2.Parser.parse(new String(raw,StandardCharsets.UTF_8))
  require(java.util.Arrays.equals(c.serialize.getBytes(StandardCharsets.UTF_8),raw),"exact official parser roundtrip")
  require(c.main=="HostBlockTopV4" && c.modules.map(_.name).distinct.size==c.modules.size,"fixed unique original Host")
  val annotations=JsonProtocol.deserialize(new String(ab,StandardCharsets.UTF_8))
  require(java.util.Arrays.equals(JsonProtocol.serialize(annotations).getBytes(StandardCharsets.UTF_8),ab),"complete annotation roundtrip")
  require(annotations.size==8985 && annotations.count(_.isInstanceOf[firrtl2.transforms.DontTouchAnnotation])==8984,"fresh annotation classes/counts")
  val targets=annotations.collect{case a:firrtl2.transforms.DontTouchAnnotation=>a.target}
  require(targets.forall(t=>t.circuit=="HostBlockTopV4" && t.path.isEmpty && Set("HostBlockTopV4","Qwen2ContinuousBlock","SiluVectorUnit","VectorSiluOwner")(t.module)),"only measured modules, no hidden hierarchy target")
  require(!targets.exists(t=>t.module=="MatrixResultFifo" || (t.module=="Qwen2ContinuousBlock" && t.ref=="denseAcc")),"no target into transformed storage")
  require(annotations.collect{case a:firrtl2.options.TargetDirAnnotation=>a.directory}==Seq("host-diagnostic"),"original diagnostic output annotation")
  val names=Seq("Qwen2ContinuousBlock","MatrixResultFifo","SiluVectorUnit","VectorSiluOwner")
  val rows=names.map {name=>
   val xs=c.modules.collect{case m:Module if m.name==name=>m};require(xs.size==1,"one actual module "+name)
   val text=xs.head.serialize;save(name+".fir",text);s"$name\t${text.getBytes(StandardCharsets.UTF_8).length}\t${sha(text)}"
  }
  save("MODULE_IDENTITIES.tsv",rows.mkString("module\tbytes\tsha256\n","\n","\n"))
  save("ANNOTATION_TARGETS.txt",targets.map(_.serialize).sorted.mkString("","\n","\n"))
  save("SCOPE.txt","PASS_OFFICIAL_PARSER_IDENTITY_INVENTORY_ONLY; NO_TRANSFORM_ELABORATION_SV_SIMULATION_OR_NUMERICAL_PASS\n")
 }
}
