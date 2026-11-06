package heteronpu.continuous.model
import firrtl2.ir._
/** Generated transport layout. No behavioral Matrix dependency. */
object MatrixNativeLayout {
 val contractSha256="5947915ca5b81f372d50965582c668afdd2a2d8bb6484cf89c2d302adb296325"
 val abiVersion=65536
 val inputWords=63; val outputWords=533
 final case class Field(name:String,width:Int,offset:Int) { val words=(width+31)/32 }
 val inputs=Vector(
  Field("rst_ni",1,0),
  Field("cmd_valid_i",1,1),
  Field("cmd_i",128,2),
  Field("step_valid_i",1,6),
  Field("step_context_i",3,7),
  Field("step_clear_i",1,8),
  Field("step_last_i",1,9),
  Field("command_last_tile_i",1,10),
  Field("step_a_i",256,11),
  Field("step_b_i",512,19),
  Field("out_ready_i",1,35),
  Field("completion_ready_i",1,36),
  Field("seed_begin_valid_i",1,37),
  Field("seed_context_i",3,38),
  Field("seed_group_tag_i",32,39),
  Field("seed_group_sequence_i",32,40),
  Field("seed_source_generation_i",32,41),
  Field("seed_beat_valid_i",1,42),
  Field("seed_cluster_i",5,43),
  Field("seed_data_i",512,44),
  Field("seed_commit_valid_i",1,60),
  Field("seed_abort_i",1,61),
  Field("seed_ack_ready_i",1,62)
 )
 val outputs=Vector(
  Field("cmd_ready_o",1,0),
  Field("step_ready_o",1,1),
  Field("out_valid_o",1,2),
  Field("out_context_o",3,3),
  Field("out_last_o",1,4),
  Field("out_acc_o",16384,5),
  Field("completion_valid_o",1,517),
  Field("completion_data_o",56,518),
  Field("protocol_error_o",1,520),
  Field("seed_begin_ready_o",1,521),
  Field("seed_beat_ready_o",1,522),
  Field("seed_commit_ready_o",1,523),
  Field("seed_ack_valid_o",1,524),
  Field("seed_ack_context_o",3,525),
  Field("seed_ack_group_tag_o",32,526),
  Field("seed_ack_group_sequence_o",32,527),
  Field("seed_ack_source_generation_o",32,528),
  Field("seed_ack_error_o",1,529),
  Field("seed_reset_required_o",1,530),
  Field("arithmetic_busy_o",5,531),
  Field("arithmetic_out_valid_o",1,532)
 )
 val inputWidths=inputs.map(f=>f.name->f.width).toMap
 val outputWidths=outputs.map(f=>f.name->f.width).toMap
 val expectedPorts:Map[String,(Direction,Type)]=
  (inputs.map(f=>f.name->((Input:Direction),(UIntType(IntWidth(f.width)):Type))) ++
   outputs.map(f=>f.name->((Output:Direction),(UIntType(IntWidth(f.width)):Type))) :+
   ("clk_i"->((Input:Direction),(ClockType:Type)))).toMap
 def encode(values:Map[String,BigInt]):Array[Int]={
  require(values.keySet==inputWidths.keySet,"complete Matrix snapshot")
  val words=new Array[Int](inputWords)
  for(f<-inputs){val v=values(f.name);require(v>=0&&v.bitLength<=f.width,"Matrix input width "+f.name)
   for(i<-0 until f.words)words(f.offset+i)=((v>>(32*i))&BigInt("ffffffff",16)).toInt}
  words
 }
 def decode(words:Array[Int]):Map[String,BigInt]={
  require(words.length==outputWords)
  outputs.map{f=>val v=(0 until f.words).foldLeft(BigInt(0)){(a,i)=>a|(BigInt(words(f.offset+i).toLong&0xffffffffL)<<(32*i))}
   require(v.bitLength<=f.width,"Matrix output width "+f.name);f.name->v}.toMap
 }
}
