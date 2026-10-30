// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.JsonProtocol
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
/** Read-only observed descriptor, NOT an accepted canonical/SV/numeric gate.
  * Calls the existing gate's public semantic functions; never its locked main.
  * LOW ports are parsed from the unchanged original helper's bound extraction,
  * in a metadata-only container, not substituted for the actual emitted LOW.
  */
object ObservedHighDescriptor {
  private def read(p:String,cap:Long):String={val x=Paths.get(p);require(Files.isRegularFile(x)&& !Files.isSymbolicLink(x));require(Files.size(x)>0&&Files.size(x)<=cap);new String(Files.readAllBytes(x),UTF_8)}
  private def id(s:String):String={require(s.matches("[A-Za-z_$][A-Za-z0-9_$]*")&&s.length<=256,"bounded identifier");s}
  private def quoted(s:String):String="\""+s+"\""
  private def width(t:Type):BigInt=t match {
    case UIntType(IntWidth(n))=>n
    case SIntType(IntWidth(n))=>n
    case ClockType|ResetType|AsyncResetType=>BigInt(1)
    case _=>sys.error("LOW extracted port is not concrete ground type")
  }
  private def port(p:Port):String={
    val name=id(p.name);val w=width(p.tpe);require(w>0&&w<=65536)
    val direction=p.direction match {case Input=>"input";case Output=>"output"}
    val t=p.tpe.serialize;require(t.matches("(UInt|SInt)<[0-9]+>|Clock|Reset|AsyncReset"))
    "{\"name\":"+quoted(name)+",\"direction\":"+quoted(direction)+",\"type\":"+quoted(t)+",\"width\":"+w+"}"
  }
  private def write(p:String,text:String,cap:Int):Unit={val b=text.getBytes(UTF_8);require(b.length<=cap);Files.write(Paths.get(p),b,StandardOpenOption.CREATE_NEW)}
  def main(a:Array[String]):Unit={
    require(a.length==5,"HIGH annotations LOW-extracted-ports NEW-canonical-tsv NEW-details-json")
    val high=read(a(0),384L<<20);val annotations=read(a(1),16L<<20)
    val c=firrtl2.Parser.parse(high);require(c.main=="HostBlockTopV4")
    require(c.serialize==high,"official parser exact HIGH roundtrip including Info")
    require(c.modules.nonEmpty&&c.modules.size<=4096&&c.modules.map(_.name).distinct.size==c.modules.size)
    c.modules.foreach(m=>id(m.name))
    val as=JsonProtocol.deserialize(annotations)
    require(JsonProtocol.serialize(as)==annotations,"exact annotation roundtrip")
    require(as.size<=100000)
    val targetCount=as.count(_.isInstanceOf[firrtl2.options.TargetDirAnnotation])
    val classes=as.groupBy(_.getClass.getName).toSeq.sortBy(_._1).map{case(n,v)=>
      require(n.matches("[A-Za-z_$][A-Za-z0-9_.$]*")&&n.length<=256);quoted(n)+":"+v.size}
    val circuitSha=CanonicalHighGate.circuitSemanticSha(c)
    val annotationSha=CanonicalHighGate.annotationSemanticSha(annotations)
    val rows=Seq("TEMP_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1","main\t"+c.main,"circuit\t"+circuitSha,"annotations_order_preserved\t"+annotationSha)++c.modules.map(m=>"module\t"+m.name+"\t"+CanonicalHighGate.moduleSemanticSha(m))
    val extracted=read(a(2),1L<<20)
    // Original helper serializes exactly one port per line. No generated logic.
    require(extracted.linesIterator.forall(s=>s.trim.isEmpty||s.trim.startsWith("input ")||s.trim.startsWith("output ")))
    val portCircuit=firrtl2.Parser.parse("circuit ObservedPorts :\n  module ObservedPorts :\n"+extracted.linesIterator.filter(_.trim.nonEmpty).map(s=>"    "+s.trim).mkString("\n")+"\n")
    require(portCircuit.modules.size==1)
    val ports=portCircuit.modules.head.ports;require(ports.nonEmpty&&ports.size<=1024&&ports.map(_.name).distinct.size==ports.size)
    val details="{\"schema\":\"OBSERVED_HIGH_DESCRIPTOR_V1\",\"qualification\":\"OBSERVED_UNREVIEWED\",\"main\":\"HostBlockTopV4\",\"canonical_algorithm\":\"CanonicalHighGate_public_semantic_methods\",\"module_count\":"+c.modules.size+",\"annotation_count\":"+as.size+",\"target_dir_annotation_count\":"+targetCount+",\"retained_annotation_count\":"+(as.size-targetCount)+",\"annotation_classes\":{"+classes.mkString(",")+"},\"circuit_sha256\":"+quoted(circuitSha)+",\"ordered_annotations_sha256\":"+quoted(annotationSha)+",\"low_port_source\":\"ORIGINAL_HELPER_HASH_BOUND_EXTRACTION_NOT_FULL_LOW_REPARSE\",\"ports\":["+ports.map(port).mkString(",")+"]}\n"
    write(a(3),rows.mkString("","\n","\n"),256<<10)
    write(a(4),details,128<<10)
    println("OBSERVED_DESCRIPTOR_ONLY_NOT_ACCEPTANCE")
  }
}
