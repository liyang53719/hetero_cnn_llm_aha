package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
// Generated verbatim expression extraction: not a production architecture or full-controller test.
class AttentionPolicyCountExpressionMicro extends Module {
  val io=IO(new Bundle {val op=Input(UInt(8.W));val tensorIndices=Input(Vec(9,UInt(24.W)));val policies=Input(Vec(4,UInt(24.W)));val count=Output(UInt(3.W));val distinct=Output(Bool())})
  val opcode=io.op
  case class Prefix(prefixIndices:Seq[UInt])
  val tensors=(0 until 3).map(i=>Prefix((0 until 3).map(j=>io.tensorIndices(3*i+j))))
  val policyIndices=io.policies.toSeq
  val attentionDistinct=Wire(Bool())
  val isMatrix=opcode===0x20.U||opcode===0x23.U||opcode===0x24.U
  val isSoftmax=opcode===0x33.U;val kv=opcode===0x41.U
  val attentionPolicySlot=Mux(kv,0.U,Mux(isMatrix,2.U,1.U))
  val attentionContextSlot=attentionPolicySlot+1.U
  val countPolicy=attentionContextSlot+&1.U
  val indices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(4)
  val used=indices.indices.map(i=>if(i<9) !((i/3)==1).B || !isSoftmax else (i-9).U<countPolicy)
  attentionDistinct:=(for(i<-indices.indices;j<-i+1 until indices.size)yield !used(i)|| !used(j)||indices(i)=/=indices(j)).reduce(_&&_)
  require(countPolicy.getWidth==3,"carry bit must be retained")
  io.count:=countPolicy;io.distinct:=attentionDistinct
}
object AttentionPolicyCountExpressionTest extends App {
 var cases=0
 RawTester.test(new AttentionPolicyCountExpressionMicro,Seq(TreadleBackendAnnotation)){d=>
  def check(op:Int,values:Seq[Int],expected:Boolean):Unit={
   d.io.op.poke(op.U);for(i<-0 until 9)d.io.tensorIndices(i).poke(values(i).U);for(i<-0 until 4)d.io.policies(i).poke(values(9+i).U)
   val n=if(op==0x41)2 else if(Set(0x20,0x23,0x24)(op))4 else 3
   d.io.count.expect(n.U);d.io.distinct.expect(expected.B);cases+=1
  }
  val base=(0 until 13).map(_+100)
  // Exhaust all opcode boundaries and every alias pair. Independent membership oracle.
  for(op<-0 until 256){
   check(op,base,true)
   val n=if(op==0x41)2 else if(Set(0x20,0x23,0x24)(op))4 else 3
   def active(i:Int)=if(i<9) !(op==0x33 && i>=3 && i<6) else i-9<n
   for(i<-0 until 13;j<-i+1 until 13)check(op,base.updated(j,base(i)),!(active(i)&&active(j)))
  }
 }
 println(s"PASS_CONTROL_EXPRESSION_ONLY cases=$cases; no full-controller reachability, block arithmetic, utilization or final RTL claim")
}
