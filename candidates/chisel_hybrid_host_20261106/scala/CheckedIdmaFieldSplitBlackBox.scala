package heteronpu.continuous.model
import firrtl2.ir._
import treadle2.ScalaBlackBox
import treadle2.executable.Transition

/** Independently named copy with checked-native lifecycle type only.
  * Original candidate scheduler/input/edge behavior is unchanged.
  * Candidate, unqualified ordering adapter. Native state is never updated by
  * clock callbacks, inputChanged, or read-only getters more than once per
  * actual clock transition. The state-output dependency anchors input updates.
  * Must pass real Treadle/leaf differential before any Host acceptance. */
final class CheckedIdmaFieldSplitBlackBox(val name:String,native:CheckedRetainedIdmaNativeLeaf,
  complete:()=>Unit) extends ScalaBlackBox {
 private val inputWidths=IdmaSplitLayout.ports.filter(p=>p.direction==Input&&p.name!="clk_i").map{p=>
  val UIntType(IntWidth(w))=p.tpe;p.name->w.toInt}.toMap
 private val outputWidths=IdmaSplitLayout.ports.filter(_.direction==Output).map{p=>
  val UIntType(IntWidth(w))=p.tpe;p.name->w.toInt}.toMap
 private val values=scala.collection.mutable.Map(inputWidths.keys.map(_->BigInt(0)).toSeq:_*)
 private val seen=scala.collection.mutable.Set.empty[String]
 private var lastClock=BigInt(0);private var lowObserved=false;private var closed=false
 private val edgeDigest=java.security.MessageDigest.getInstance("SHA-256")
 def edgeSnapshotSha256:String=IdmaEdgeSnapshot.current(edgeDigest)
 var positiveEdges:Long=0L
 private val q=Seq("clk_i","rst_ni")
 private val rd="axi_read_rsp_i__";private val wr="axi_write_rsp_i__"
 override def setParams(params:Seq[Param]):Unit=require(params.isEmpty,"no private model parameters")
 override def getDependencies:Seq[(String,Set[String])]=
  inputWidths.keys.toSeq.sorted.filterNot(_=="rst_ni").map(_->Set("req_ready_o"))
 override def inputChanged(port:String,value:BigInt):Unit={
  require(!closed&&inputWidths.contains(port),"known live scalar input")
  require(value>=0&&value.bitLength<=inputWidths(port),"input width")
  values(port)=value;seen+=port
 }
 override def clockChange(transition:Transition,clockName:String):Unit={
  require(clockName=="clk_i"||clockName==name+".clk_i","exact native leaf clock")
  // Deliberately no state mutation: sibling callback order is unspecified.
 }
 override def outputDependencies(port:String):Seq[String]={
  require(outputWidths.contains(port),"known scalar output")
  port match {
   case "rsp_valid_o" => q++Seq(wr+"b_valid","req_valid_i","length_i")
   case "rsp_error_o" => q++Seq(rd+"r_valid",rd+"r_resp",wr+"b_valid",wr+"b_resp","req_valid_i","length_i")
   case "axi_read_req_o__r_ready" => q++Seq(rd+"r_last",wr+"w_ready")
   case "busy_o" => q++Seq(wr+"w_ready") // conservative before cone qualification
   case _ => q
  }
 }
 private def pack(bus:String):BigInt=IdmaSplitLayout.fields.filter(_.bus==bus).foldLeft(BigInt(0)){case(a,f)=>a|(values(f.name)<<f.lsb)}
 private def drive():Unit={
  native.drive(values("rst_ni")==1,values("req_valid_i")==1,values("src_addr_i"),values("dst_addr_i"),
   values("length_i").toLong,values("rsp_ready_i")==1,pack("axi_read_rsp_i"),pack("axi_write_rsp_i"))
  native.evaluate()
 }
 private def observeClock(level:BigInt,resetN:BigInt):Unit={
  require(level==0||level==1);require(resetN==0||resetN==1)
  values("rst_ni")=resetN;seen+="rst_ni"
  if(level==1 && !lowObserved)throw new IllegalArgumentException("actual low clock required before first rise")
  if(lastClock==0&&level==1){
   require(seen.toSet==inputWidths.keySet,"all complete pre-edge inputs observed")
   complete();IdmaEdgeSnapshot.update(edgeDigest,values.toMap);drive();native.clock(true);positiveEdges+=1
  }else if(lastClock==1&&level==0){drive();native.clock(false)}
  else drive() // combinational settle only, no edge
  if(level==0)lowObserved=true
  lastClock=level
 }
 override def getOutput(inputs:Seq[BigInt],tpe:Type,port:String):BigInt={
  require(!closed);val deps=outputDependencies(port)
  require(inputs.size==deps.size)
  // An explicitly declared combinational dependency must already be assigned
  // by the scheduler; silently reusing its old value is never acceptable.
  for((d,v)<-deps.zip(inputs).drop(2))require(values(d)==v,"scheduler input assignment/order mismatch "+d)
  val UIntType(IntWidth(width))=tpe;require(width==outputWidths(port))
  observeClock(inputs(0),inputs(1))
  val o=native.read()
  val v=port match {
   case "req_ready_o"=>if(o.requestReady)BigInt(1)else BigInt(0)
   case "rsp_valid_o"=>if(o.responseValid)BigInt(1)else BigInt(0)
   case "rsp_error_o"=>if(o.responseError)BigInt(1)else BigInt(0)
   case "busy_o"=>BigInt(o.busy)
   case other=>
    val f=IdmaSplitLayout.fields.find(_.name==other).get
    val packed=if(f.bus=="axi_read_req_o")o.readRequest else o.writeRequest
    (packed>>f.lsb)&((BigInt(1)<<f.width)-1)
  }
  require(v>=0&&v.bitLength<=outputWidths(port));v
 }
 def abortUnqualifiedConstruction():Unit={if(!closed){try native.close() finally {closed=true}}}
 override def finish():Unit={if(!closed){try complete() finally {abortUnqualifiedConstruction()}}}
}
