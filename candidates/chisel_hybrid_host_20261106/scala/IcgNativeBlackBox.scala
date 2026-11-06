package heteronpu.continuous.model
import firrtl2.ir._
import treadle2.ScalaBlackBox
import treadle2.executable.Transition
/** UNQUALIFIED scheduling transport for original tc_clk_gating. All latch
  * behavior is evaluated inside generated native RTL, never recreated here. */
final class IcgNativeBlackBox(val name:String,native:RetainedIcgNativeLeaf,
 complete:()=>Unit) extends ScalaBlackBox {
 private val widths=Map("en_i"->1,"test_en_i"->1)
 private val values=scala.collection.mutable.Map("en_i"->BigInt(0),"test_en_i"->BigInt(0))
 private val seen=scala.collection.mutable.Set.empty[String]
 private val digest=java.security.MessageDigest.getInstance("SHA-256")
 private val transitions=java.security.MessageDigest.getInstance("SHA-256")
 private var level=BigInt(0);private var lowObserved=false;private var closed=false
 var positiveEdges=0L;var negativeEdges=0L
 def edgeSnapshotSha256:String=NativeEdgeSnapshot.current(digest) // rising capture only
 def transitionSnapshotSha256:String=NativeEdgeSnapshot.current(transitions)
 def nativeEdgeCounts:Vector[Long]=native.edgeCounts
 override def setParams(params:Seq[Param]):Unit=require(params.isEmpty,"original ICG default IS_FUNCTIONAL=1")
 override def getDependencies:Seq[(String,Set[String])]=Seq("en_i"->Set("clk_o"),"test_en_i"->Set("clk_o"))
 private def settle():Unit={native.drive(values("en_i"),values("test_en_i"));native.evaluate()}
 override def inputChanged(port:String,value:BigInt):Unit={
  require(!closed&&widths.contains(port));NativeApiChecks.bit(value)
  values(port)=value;seen+=port
  // Real native latch tracks every low-phase change; high changes cannot
  // alter its retained value. This statement implements neither behavior.
  settle()
 }
 override def clockChange(transition:Transition,clockName:String):Unit={
  require(!closed&&(clockName=="clk_i"||clockName==name+".clk_i"||clockName=="clk_o"||clockName==name+".clk_o"),"exact ICG callback")
 }
 override def outputDependencies(port:String):Seq[String]={require(port=="clk_o");Seq("clk_i")}
 override def getOutput(inputs:Seq[BigInt],tpe:Type,port:String):BigInt={
  require(!closed&&port=="clk_o"&&inputs.size==1)
  require(tpe==ClockType||tpe==UIntType(IntWidth(1)),"ICG one-bit clock output")
  val next=inputs.head;NativeApiChecks.bit(next)
  require(next==0||lowObserved,"actual low required before initial ICG high")
  if(next!=level){require(seen.toSet==widths.keySet,"both actual ICG inputs observed before edge");complete()}
  settle()
  if(next!=level)NativeEdgeSnapshot.updateTransition(transitions,widths,values.toMap,level,next)
  if(next!=level||next==0){
   if(level==0&&next==1){NativeEdgeSnapshot.update(digest,widths,values.toMap);positiveEdges+=1}
   if(level==1&&next==0)negativeEdges+=1
   native.clock(next)
  }
  if(next==0)lowObserved=true
  level=next
  require(native.edgeCounts.take(2)==Vector(positiveEdges,negativeEdges),"native/adapter ICG edges")
  native.read()
 }
 def abortUnqualifiedConstruction():Unit={if(!closed){closed=true;native.close()}}
 override def finish():Unit={if(!closed){try complete() finally abortUnqualifiedConstruction()}}
}
