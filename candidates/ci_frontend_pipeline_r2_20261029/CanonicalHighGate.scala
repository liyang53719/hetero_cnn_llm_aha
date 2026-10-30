// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.JsonProtocol
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest
/** TEMP_UNCOMPILED: official AST only. Never regex-delete source text.
 * canonical excludes ONLY ir.Info and TargetDirAnnotation; no sorting, rename,
 * deduplication, lowering, expression rewrite or annotation-target filtering.
 * Semantic equality is not numerical equivalence or an emission qualification.
 */
object CanonicalHighGate {
 private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
 private def sha(s:String):String=sha(s.getBytes(UTF_8))
 private def stmt(s:Statement):Statement=s.mapStmt(stmt).mapInfo(_=>NoInfo)
 private def module(m:DefModule):DefModule=m match {
  case x:Module=>x.copy(info=NoInfo,ports=x.ports.map(_.copy(info=NoInfo)),body=stmt(x.body))
  case x:ExtModule=>x.copy(info=NoInfo,ports=x.ports.map(_.copy(info=NoInfo)))
  case _=>sys.error("Unknown module type: fail closed")
 }
 def moduleSemanticSha(m:DefModule):String=sha(module(m).serialize)
 def circuitSemanticSha(c:Circuit):String=sha(c.copy(info=NoInfo,modules=c.modules.map(module)).serialize)
 def annotationSemanticSha(s:String):String=sha(JsonProtocol.serialize(JsonProtocol.deserialize(s).filterNot(_.isInstanceOf[firrtl2.options.TargetDirAnnotation])))
 def main(a:Array[String]):Unit={
  require(a.length==6,"mode high annotations accepted-manifest accepted-sha NEW-output")
  require(Set("baseline","candidate")(a(0)))
  val raw=Files.readAllBytes(Paths.get(a(1)));val ann=Files.readAllBytes(Paths.get(a(2)))
  if(a(0)=="baseline") {
   require(sha(raw)=="391774e80482befb9004f78ffb3cbbc6497f2a392e9729e97e648071026bd267")
   require(sha(ann)=="e40aecae9e15a890acd6eacabd6974d9470434cc83b40c847a0d50096b2bdeee")
   require(a(3)=="NONE" && a(4)=="NONE")
  }
  val c=firrtl2.Parser.parse(new String(raw,UTF_8))
  require(c.main=="HostBlockTopV4" && c.modules.size==1056)
  require(c.modules.map(_.name).distinct.size==c.modules.size)
  val as=JsonProtocol.deserialize(new String(ann,UTF_8))
  require(as.size==(if(a(0)=="baseline") 8985 else 9022) && as.count(_.isInstanceOf[firrtl2.options.TargetDirAnnotation])==1)
  val keep=as.filterNot(_.isInstanceOf[firrtl2.options.TargetDirAnnotation])
  val clean=c.copy(info=NoInfo,modules=c.modules.map(module))
  val rows=Seq("TEMP_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1", "main\t"+clean.main,
    "circuit\t"+sha(clean.serialize),"annotations_order_preserved\t"+sha(JsonProtocol.serialize(keep))) ++
    clean.modules.map(m=>"module\t"+m.name+"\t"+sha(m.serialize))
  val bytes=rows.mkString("","\n","\n").getBytes(UTF_8)
  if(a(0)=="candidate") {
   require(a(4).matches("[0-9a-f]{64}"),"independently approved manifest hash required")
   val accepted=Files.readAllBytes(Paths.get(a(3)))
   require(sha(accepted)==a(4),"accepted manifest pin")
   require(java.util.Arrays.equals(bytes,accepted),"NON_METADATA_DIFFERENCE: stop; never repin")
  }
  Files.write(Paths.get(a(5)),bytes,StandardOpenOption.CREATE_NEW)
  println("CANONICAL_ONLY_NOT_NUMERICAL_OR_TRANSFORM_PASS\t"+sha(bytes))
 }
}
