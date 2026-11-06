package heteronpu.continuous.model
import java.nio.charset.StandardCharsets.UTF_8
import java.security.MessageDigest
/** Identity evidence only. Never feeds DUT data or certifies correct scheduling. */
object NativeEdgeSnapshot {
 def update(d:MessageDigest,widths:Map[String,Int],values:Map[String,BigInt]):Unit={
  require(values.keySet==widths.keySet,"complete nonclock input snapshot")
  for((name,width)<-widths.toVector.sortBy(_._1)){
   val value=values(name);require(value>=0&&value.bitLength<=width)
   d.update(name.getBytes(UTF_8));d.update(0.toByte)
   d.update(((width>>8)&255).toByte);d.update((width&255).toByte)
   for(i<-((width+7)/8-1) to 0 by -1)d.update(((value>>(8*i))&255).toByte)
  }
 }
 def updateTransition(d:MessageDigest,widths:Map[String,Int],values:Map[String,BigInt],oldLevel:BigInt,newLevel:BigInt):Unit={
  NativeApiChecks.bit(oldLevel);NativeApiChecks.bit(newLevel);require(oldLevel!=newLevel)
  d.update(oldLevel.toByte);d.update(newLevel.toByte);update(d,widths,values)
 }
 def current(d:MessageDigest):String=d.clone().asInstanceOf[MessageDigest].digest().map(b=>f"${b&255}%02x").mkString
}
