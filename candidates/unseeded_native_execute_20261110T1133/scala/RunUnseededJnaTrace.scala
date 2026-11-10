package heteronpu.continuous.model
import firrtl2.ir._
object RunUnseededJnaTrace extends App {
 val pin=NativeLibraryPin(args(0),args(1));val leaf=new UnseededRetainedMatrixNativeLeafV2(pin)
 val bb=new UnseededMatrixNativeBlackBoxV2("matrix",leaf,()=>())
 val iw=UnseededMatrixNativeLayoutV2.inputWidths;val ow=UnseededMatrixNativeLayoutV2.outputWidths
 var level=BigInt(0);var command=false;var step=false;var outputs=0;var completions=0;var reads=0L
 def get(port:String,v:Map[String,BigInt]):BigInt={val deps=bb.outputDependencies(port);bb.getOutput(deps.map(n=>if(n=="clk_i")level else v(n)),UIntType(IntWidth(ow(port))),port)}
 try {
  for(tick<-0 until 400){val cycle=tick/2;val next=BigInt(tick%2)
   val v=iw.keys.map(_->BigInt(0)).toMap++Map("rst_ni"->BigInt(if(cycle>=3)1 else 0),"cmd_valid_i"->BigInt(if(cycle>=4 && !command)1 else 0),"cmd_i"->(BigInt(0x123400)<<32|BigInt(0x20)),"step_valid_i"->BigInt(if(command && !step)1 else 0),"step_clear_i"->BigInt(1),"step_last_i"->BigInt(1),"command_last_tile_i"->BigInt(1),"step_a_i"->((0 until 16).map(i=>BigInt(0x3f80)<<(16*i)).sum),"step_b_i"->((0 until 32).map(i=>BigInt(0x3f80)<<(16*i)).sum),"out_ready_i"->BigInt(if(cycle>=32)1 else 0),"completion_ready_i"->BigInt(if(cycle>=36)1 else 0))
   v.toVector.sortBy(_._1).foreach{case(n,x)=>bb.inputChanged(n,x)}
   val pre=ow.keys.map(n=>n->get(n,v)).toMap
   val takeCmd=next==1 && v("cmd_valid_i")==1 && pre("cmd_ready_o")==1
   val takeStep=next==1 && v("step_valid_i")==1 && pre("step_ready_o")==1
   if(next==1 && pre("out_valid_o")==1 && v("out_ready_i")==1){for(i<-0 until 512)require(((pre("out_acc_o")>>(32*i))&BigInt("ffffffff",16))==BigInt("3f800000",16),"actual512 result");outputs+=1}
   if(next==1 && pre("completion_valid_o")==1 && v("completion_ready_i")==1)completions+=1
   level=next;ow.keys.toVector.sorted.foreach(n=>{get(n,v);reads+=1});command ||= takeCmd;step ||= takeStep
  }
  require(command && step && outputs==1 && completions==1,"trace coverage");require(bb.nativeEdgeCounts==(200L,199L),"physical edges")
  println(s"PASS_JNA_ADAPTER_TRACE ticks=400 reads=$reads output512=$outputs completion=$completions edges=${bb.nativeEdgeCounts} NOT_HOST_NOT_4096_FULL")
 } finally bb.finish()
}
