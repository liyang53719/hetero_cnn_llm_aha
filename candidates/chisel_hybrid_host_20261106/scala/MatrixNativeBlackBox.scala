package heteronpu.continuous.model
import firrtl2.ir._
import treadle2.ScalaBlackBox
import treadle2.executable.Transition
/** UNQUALIFIED native scheduling adapter. The source-derived state anchor must
  * pass actual Treadle and connected ICG differential before Host execution.
  * Input setters never clock; callbacks never clock. A clock-aware getter
  * observes each real transition once, with the complete retained input set. */
final class MatrixNativeBlackBox(val name:String,native:RetainedMatrixNativeLeaf,
 complete:()=>Unit) extends ScalaBlackBox {
 private val widths=MatrixNativeLayout.inputWidths
 private val values=scala.collection.mutable.Map(widths.keys.map(_->BigInt(0)).toSeq:_*)
 private val seen=scala.collection.mutable.Set.empty[String]
 private val digest=java.security.MessageDigest.getInstance("SHA-256")
 private val transitions=java.security.MessageDigest.getInstance("SHA-256")
 private var level=BigInt(0);private var lowObserved=false;private var closed=false
 var positiveEdges=0L;var negativeEdges=0L
 def edgeSnapshotSha256:String=NativeEdgeSnapshot.current(digest) // rising capture only
 def transitionSnapshotSha256:String=NativeEdgeSnapshot.current(transitions)
 def nativeEdgeCounts:(Long,Long)=native.edgeCounts
 override def setParams(params:Seq[Param]):Unit=
  require(params==Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1))),"exact native seed parameter")
 override def getDependencies:Seq[(String,Set[String])]=
  widths.keys.toVector.sorted.filterNot(_=="rst_ni").map(_->Set("out_valid_o"))
 private def settle():Unit={native.drive(values.toMap);native.evaluate()}
 override def inputChanged(port:String,value:BigInt):Unit={
  require(!closed&&widths.contains(port),"known live Matrix input "+port)
  require(value>=0&&value.bitLength<=widths(port),"Matrix input width")
  values(port)=value;seen+=port
  // In particular reset assertion at held high/low reaches async RTL now.
  // No clock pin or simulator time can change here.
  settle()
 }
 override def clockChange(transition:Transition,clockName:String):Unit={
  require(clockName=="clk_i"||clockName==name+".clk_i","exact Matrix clock identity")
  require(!closed,"live Matrix callback")
 }
 private val q=Seq("clk_i","rst_ni")
 private val seedBlock=Seq("seed_begin_valid_i","seed_beat_valid_i","seed_commit_valid_i","seed_abort_i")
 override def outputDependencies(port:String):Seq[String]={
  require(MatrixNativeLayout.outputWidths.contains(port),"known Matrix output")
  port match {
   case "cmd_ready_o"=>q++seedBlock
   case "step_ready_o"=>q++Seq("step_context_i","out_ready_i")++seedBlock
   // Selected begin_fix readiness excludes the current input_write path.
   case "seed_begin_ready_o"=>q++Seq("seed_abort_i")
   case "seed_beat_ready_o"|"seed_commit_ready_o"=>q++Seq("step_context_i","step_valid_i","out_ready_i")++seedBlock
   case _=>q
  }
 }
 private def observeClock(next:BigInt,reset:BigInt):Unit={
  NativeApiChecks.bit(next);NativeApiChecks.bit(reset)
  require(next==0||lowObserved,"actual low-clock observation required before first Matrix high")
  values("rst_ni")=reset;seen+="rst_ni"
  if(next!=level){
   require(seen.toSet==widths.keySet,"all actual Matrix inputs observed before edge")
   complete()
  }
  settle() // all pre-edge data at OLD clock, including asynchronous reset
  if(next!=level)NativeEdgeSnapshot.updateTransition(transitions,widths,values.toMap,level,next)
  if(next!=level||next==0){
   if(level==0&&next==1){NativeEdgeSnapshot.update(digest,widths,values.toMap);positiveEdges+=1}
   if(level==1&&next==0)negativeEdges+=1
   native.clock(next) // repeated low is explicit observation, never an edge
  }
  if(next==0)lowObserved=true
  level=next
  require(native.edgeCounts==((positiveEdges,negativeEdges)),"native/adapter Matrix edge count")
 }
 override def getOutput(inputs:Seq[BigInt],tpe:Type,port:String):BigInt={
  require(!closed);val deps=outputDependencies(port);require(inputs.size==deps.size)
  val UIntType(IntWidth(width))=tpe;require(width==MatrixNativeLayout.outputWidths(port))
  for((n,v)<-deps.zip(inputs).drop(2))require(values(n)==v,"Matrix scheduler input assignment/order mismatch "+n)
  observeClock(inputs.head,inputs(1))
  native.read()(port)
 }
 def abortUnqualifiedConstruction():Unit={if(!closed){closed=true;native.close()}}
 override def finish():Unit={if(!closed){try complete() finally abortUnqualifiedConstruction()}}
}
