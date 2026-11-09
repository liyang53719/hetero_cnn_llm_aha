import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import heteronpu.continuous._
class LoadPrepWithOriginalAlu extends Module {
 val io=IO(new GdnRuntimeChunkLoadPrepV2Port)
 val owner=Module(new GdnRuntimeChunkLoadPrepV2Owner)
 owner.io.job <> io.job; owner.io.committed := io.committed
 io.memory <> owner.io.memory; owner.io.response <> io.response
 io.done <> owner.io.done; io.resetRequired := owner.io.resetRequired
 // Original ALU, one registered response, no software arithmetic substitution.
 val alu=Module(new gemmini.HeteroFP32Alu)
 alu.io.op:=false.B; alu.io.x:=owner.io.scalar.request.bits.payload.a; alu.io.y:=owner.io.scalar.request.bits.payload.b
 val pending=RegInit(false.B); val value=Reg(UInt(32.W)); val flags=Reg(UInt(5.W))
 owner.io.scalar.request.ready := !pending
 when(owner.io.scalar.request.fire){value:=alu.io.out;flags:=alu.io.exceptionFlags;pending:=true.B}
 when(owner.io.scalar.result.fire){pending:=false.B}
 owner.io.scalar.result.valid:=pending
 owner.io.scalar.result.bits.policy:=0.U;owner.io.scalar.result.bits.value:=value
 owner.io.scalar.result.bits.flags:=flags;owner.io.scalar.result.bits.primitiveFlagsValid:=true.B
 owner.io.scalar.result.bits.error:=flags(4,1).orR
 // Observation only: no external scalar return is used.
 io.scalar.request.valid:=owner.io.scalar.request.valid;io.scalar.request.bits:=owner.io.scalar.request.bits
 io.scalar.result.ready:=false.B
}
object LoadPrepCheck extends App {
 def pack(xs:Seq[Long]):BigInt=xs.zipWithIndex.foldLeft(BigInt(0)){case(a,(x,i))=>a|(BigInt(x)<<(32*i))}
 RawTester.test(new LoadPrepWithOriginalAlu,Seq(TreadleBackendAnnotation)){d=>
  def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case a:Aggregate=>a.getElements.foreach(zero);case _=>()}
  zero(d.io.job.bits);zero(d.io.committed);zero(d.io.response.bits);zero(d.io.scalar.result.bits)
  d.io.job.valid.poke(false.B);d.io.response.valid.poke(false.B);d.io.memory.ready.poke(true.B);d.io.done.ready.poke(false.B)
  d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
  d.clock.setTimeout(100000)
  for(policy<-0 to 1;chunk<-0 to 1){
   val j=d.io.job.bits;zero(j)
   j.context.tag.poke(7.U);j.context.tokens.poke(128.U);j.context.cold.poke(true.B)
   val input=BigInt("1000000",16);val scratch=BigInt("10000000",16)
   j.context.input.poke(input.U);j.context.stateIn.poke(BigInt("2000000",16).U);j.context.stateOut.poke(BigInt("3000000",16).U)
   j.context.output.poke(BigInt("4000000",16).U);j.context.scratch.poke(scratch.U)
   j.numeric.cumsum.poke(policy.U);j.numeric.decay.poke(policy.U);j.keyHeads.poke(16.U);j.valueHeads.poke(16.U);j.chunk.poke(chunk.U)
   val p=j.prepReady;p.tag.poke(7.U);p.tokens.poke(128.U);p.input.poke(input.U);p.writeBytes.poke((128*25600).U)
   p.preparedComplete.poke(true.B);p.drained.poke(true.B);p.layoutVersion.poke(1.U);p.rowBytes.poke(25600.U);p.keyHeads.poke(16.U);p.valueHeads.poke(16.U)
   for((r,phase)<-Seq((j.initialReady,0),(j.previousStateReady,16),(j.previousOutputReady,17))){r.tag.poke(7.U);r.phase.poke(phase.U);r.drained.poke(true.B);if(phase==17)r.outputAckBytes.poke(16384.U) else r.scratchAckBytes.poke(65536.U)}
   val mem=scala.collection.mutable.Map[BigInt,BigInt]();val expected=scala.collection.mutable.Map[BigInt,BigInt]()
   for(row<-0 until 64){val t=chunk*64+row;val src=input+t*25600;val dst=scratch+65536+chunk*806912
    mem(src+24576)=pack(Seq(Fixture.g(0)(t),Fixture.beta(0)(t)))
    expected(dst+row*64)=pack(Seq((if(policy==0)Fixture.p0 else Fixture.p1)(0)(t),Fixture.beta(0)(t)))
    for((data,role)<-Seq(Fixture.q,Fixture.k,Fixture.v).zipWithIndex;beat<-0 until 8){val words=pack(data(t).slice(beat*16,beat*16+16));mem(src+role*8192+beat*64)=words;expected(dst+Seq(4096,36864,69632)(role)+row*512+beat*64)=words}
   }
   d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
   var pending:Option[(BigInt,BigInt)]=None;var cycles=0;var writes=0;var reads=0
   while(!d.io.done.valid.peek().litToBoolean && cycles<20000){
    d.io.response.valid.poke(pending.nonEmpty.B);pending.foreach{case(tag,data)=>d.io.response.bits.tag.poke(tag.U);d.io.response.bits.data.poke(data.U)}
    val consumed=pending.nonEmpty && d.io.response.ready.peek().litToBoolean
    var next:Option[(BigInt,BigInt)]=None
    if(d.io.memory.valid.peek().litToBoolean){val r=d.io.memory.bits;val addr=r.address.peek().litValue;val tag=r.tag.peek().litValue
     if(r.write.peek().litToBoolean){assert(expected.contains(addr),s"unexpected write $addr");assert(r.data.peek().litValue==expected.remove(addr).get,s"write mismatch policy=$policy chunk=$chunk address=$addr");r.mask.expect(((BigInt(1)<<64)-1).U);writes+=1;next=Some(tag->BigInt(0))}
     else{assert(mem.contains(addr),s"unexpected read $addr");reads+=1;next=Some(tag->mem(addr))}
    }
    d.clock.step();if(consumed)pending=None;assert(pending.isEmpty || next.isEmpty);if(next.nonEmpty)pending=next;cycles+=1
   }
   d.io.response.valid.poke(false.B);assert(cycles<20000);assert(expected.isEmpty);assert(reads==1600 && writes==1600)
   d.io.done.bits.stageComplete.expect(true.B);d.io.done.bits.receipt.status.expect(0.U);d.io.done.bits.receipt.drained.expect(true.B)
   d.io.done.bits.addRequests.expect((if(policy==0)64 else 832).U);d.io.done.bits.addResults.expect((if(policy==0)64 else 832).U)
   println(s"PASS policy=$policy chunk=$chunk read_beats=$reads write_beats=$writes bit_checked_words=${writes*16} cycles=$cycles")
   d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B)
  }
 }
}
