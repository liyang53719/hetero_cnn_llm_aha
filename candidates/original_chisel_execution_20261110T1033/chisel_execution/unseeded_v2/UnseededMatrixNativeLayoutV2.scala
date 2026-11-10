package heteronpu.continuous.model
import firrtl2.ir._
/** Generated transport layout. No behavioral Matrix dependency. */
object UnseededMatrixNativeLayoutV2 {
 val contractSha256="2702823111f4b275fdb56465e82152b107484c4139fe0d1f953251bfd2de9e9a"
 val abiVersion=131072
 val inputWords=37; val outputWords=521
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
