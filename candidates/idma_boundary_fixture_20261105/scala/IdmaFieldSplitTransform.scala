package heteronpu.continuous.model
import firrtl2.ir._
import firrtl2.PrimOps
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest

/** Simulation representation only. Run before official low compilation.
  * Caller supplies an independently pinned original ExtModule hash; never
  * learn/accept the current hash in place. No production source is modified. */
object IdmaFieldSplitTransform {
 private def sha(s:String)=MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(b=>f"${b&255}%02x").mkString
 private def ref(n:String):Expression=Reference(n)
 private def model(n:String):Expression=SubField(ref("model"),n)
 private def connect(a:Expression,b:Expression)=Connect(NoInfo,a,b)
 private def cat(xs:Vector[Expression]):Expression={
  require(xs.nonEmpty)
  if(xs.size==1)xs.head else {
   val n=xs.size/2
   DoPrim(PrimOps.Cat,Seq(cat(xs.take(n)),cat(xs.drop(n))),Seq.empty,UnknownType)
  }
 }
 def apply(c:Circuit,expectedExtModuleSha:String):Circuit={
  IdmaSplitLayout.checkLayout()
  require(expectedExtModuleSha.matches("[0-9a-f]{64}"),"independent original extmodule pin required")
  require(!c.modules.exists(_.name==IdmaSplitLayout.modelName),"fresh distinct private model name")
  val found=c.modules.collect{case e:ExtModule if e.defname=="idma_backend_rw_axi_flat_wrap"=>e}
  require(found.size==1,"one retained iDMA definition")
  val e=found.head
  require(sha(e.serialize)==expectedExtModuleSha,"original iDMA ExtModule drift")
  require(e.params.isEmpty,"original no parameter override")
  val expected=(IdmaSplitLayout.controlPorts++IdmaSplitLayout.busWidths.toVector.map{case(n,w)=>
   Port(NoInfo,n,if(n.endsWith("_i"))Input else Output,IdmaSplitLayout.uint(w))})
  require(e.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==expected.map(p=>p.name->(p.direction,p.tpe)).toMap)
  require(e.ports.size==expected.size,"no duplicate ports")
  val statements=Vector.newBuilder[Statement]
  statements+=DefInstance(NoInfo,"model",IdmaSplitLayout.modelName,UnknownType)
  for(p<-IdmaSplitLayout.controlPorts){
   if(p.direction==Input)statements+=connect(model(p.name),ref(p.name))
   else statements+=connect(ref(p.name),model(p.name))
  }
  for(f<-IdmaSplitLayout.fields if f.direction==Input){
   val extract=DoPrim(PrimOps.Bits,Seq(ref(f.bus)),Seq(BigInt(f.lsb+f.width-1),BigInt(f.lsb)),IdmaSplitLayout.uint(f.width))
   statements+=connect(model(f.name),extract)
  }
  for((bus,_)<-IdmaSplitLayout.busWidths if bus.endsWith("_o")){
   val fs=IdmaSplitLayout.fields.filter(_.bus==bus).sortBy(f=> -f.lsb)
   statements+=connect(ref(bus),cat(fs.map(f=>model(f.name))))
  }
  val replacement=Module(e.info,e.name,e.ports,Block(statements.result()))
  val leaf=ExtModule(NoInfo,IdmaSplitLayout.modelName,IdmaSplitLayout.ports,IdmaSplitLayout.modelName,Seq.empty)
  val out=c.copy(modules=c.modules.map(m=>if(m eq e)replacement else m):+leaf)
  require(out.modules.dropRight(1).zip(c.modules).forall{case(a,b)=>(b eq e)||(a eq b)},"all other hardware AST objects unchanged")
  out
 }
}
