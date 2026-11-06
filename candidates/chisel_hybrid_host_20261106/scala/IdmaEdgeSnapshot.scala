package heteronpu.continuous.model
import firrtl2.ir._
import java.security.MessageDigest
import java.nio.charset.StandardCharsets.UTF_8
/** Full, deterministic input identity at each real positive edge, never data
  * supplied to the DUT. Useful for detecting stale/missing input sampling. */
object IdmaEdgeSnapshot {
 val inputs=IdmaSplitLayout.ports.filter(p=>p.direction==Input&&p.name!="clk_i").sortBy(_.name)
 def update(d:MessageDigest,values:Map[String,BigInt]):Unit={
  require(values.keySet==inputs.map(_.name).toSet)
  for(p<-inputs){
   val UIntType(IntWidth(w))=p.tpe;val width=w.toInt;val x=values(p.name)
   require(x>=0&&x.bitLength<=width)
   d.update(p.name.getBytes(UTF_8));d.update(0.toByte)
   d.update(((width>>8)&255).toByte);d.update((width&255).toByte)
   for(i<-((width+7)/8-1) to 0 by -1)d.update(((x>>(8*i))&255).toByte)
  }
 }
 def current(d:MessageDigest):String=d.clone().asInstanceOf[MessageDigest].digest().map(b=>f"${b&255}%02x").mkString
 def fromPacked(resetN:BigInt,valid:BigInt,src:BigInt,dst:BigInt,length:BigInt,ready:BigInt,read:BigInt,write:BigInt):Map[String,BigInt]={
  val controls=Map("rst_ni"->resetN,"req_valid_i"->valid,"src_addr_i"->src,"dst_addr_i"->dst,"length_i"->length,"rsp_ready_i"->ready)
  controls++IdmaSplitLayout.fields.filter(_.direction==Input).map{f=>
   val packed=if(f.bus=="axi_read_rsp_i")read else write
   f.name->((packed>>f.lsb)&((BigInt(1)<<f.width)-1))}.toMap
 }
}
