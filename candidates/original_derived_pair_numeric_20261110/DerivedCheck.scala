import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.continuous._
// Single-owner testbench routing, NOT the original production authority/router.
class DerivedActualArithmetic extends Module {
 val io=IO(new GdnRuntimeChunkDerivedAndPairV2Port)
 val owner=Module(new GdnRuntimeChunkDerivedAndPairV2Owner)
 val scalar=Module(new BlockScalarFloatPolicyV2)
 val bank=Module(new UnifiedVectorElement32BankV4)
 owner.io.job <> io.job;owner.io.committed:=io.committed
 io.memory <> owner.io.memory;owner.io.response <> io.response
 io.done <> owner.io.done;io.resetRequired:=owner.io.resetRequired
 scalar.io.request <> owner.io.scalar.request;owner.io.scalar.result <> scalar.io.result
 io.scalar.request.valid:=false.B;io.scalar.request.bits:=0.U.asTypeOf(io.scalar.request.bits);io.scalar.result.ready:=false.B
 io.vectorRequest.valid:=false.B;io.vectorRequest.bits:=0.U.asTypeOf(io.vectorRequest.bits);io.vectorResult.ready:=false.B
 val req=owner.io.vectorRequest;val result=owner.io.vectorResult
 val heldGradual=Reg(Bool());val heldPolicy=Reg(UInt(2.W));val heldFormat=Reg(Bool())
 when(req.fire){heldGradual:=req.bits.gradual;heldPolicy:=req.bits.payload.policy;heldFormat:=req.bits.formatOnly}
 bank.io.request.valid:=req.valid;req.ready:=bank.io.request.ready
 bank.io.request.bits.identity:=0.U.asTypeOf(bank.io.request.bits.identity)
 bank.io.request.bits.payload.policy:=Mux(req.bits.formatOnly,4.U,Mux(req.bits.gradual,3.U,req.bits.payload.policy))
 bank.io.request.bits.payload.multiply:=req.bits.payload.multiply
 for(i<-0 until 32){
  bank.io.request.bits.payload.a(i):=(if(i<16)req.bits.payload.a(i) else 0.U)
  bank.io.request.bits.payload.b(i):=(if(i<16)req.bits.payload.b(i) else 0.U)
 }
 result.valid:=bank.io.result.valid;bank.io.result.ready:=result.ready
 result.bits.formatOnly:=heldFormat;result.bits.gradual:=heldGradual
 result.bits.arithFlagsValid:=bank.io.result.bits.payload.arithFlagsValid
 result.bits.payload.policy:=heldPolicy;result.bits.payload.error:=bank.io.result.bits.payload.error
 for(i<-0 until 16){result.bits.payload.value(i):=bank.io.result.bits.payload.value(i);result.bits.payload.flags(i):=bank.io.result.bits.payload.arithFlags(i)}
}
object DerivedCheck extends App {
 val maxCycles=args.find(_.startsWith("--cycles=")).map(_.drop(9).toInt).getOrElse(400)
 val backend=if(args.contains("--verilator"))VerilatorBackendAnnotation else TreadleBackendAnnotation
 val start=System.nanoTime()
 RawTester.test(new DerivedActualArithmetic,Seq(backend)){d=>
  println(s"ELABORATED seconds=${(System.nanoTime()-start)/1e9}")
  def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case a:Aggregate=>a.getElements.foreach(zero);case _=>()}
  def readWords(file:String)=scala.collection.mutable.Map(scala.io.Source.fromFile(file).getLines().map{line=>val a=line.split("\t");BigInt(a(0),16)->BigInt(a(1),16)}.toSeq:_*)
  val mem=readWords("inputs.tsv");val expected=readWords("expected.tsv")
  zero(d.io.job.bits);zero(d.io.committed);zero(d.io.response.bits);zero(d.io.scalar.result.bits);zero(d.io.vectorResult.bits)
  d.io.job.valid.poke(false.B);d.io.memory.ready.poke(true.B);d.io.response.valid.poke(false.B);d.io.done.ready.poke(false.B)
  d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B);d.io.vectorRequest.ready.poke(false.B);d.io.vectorResult.valid.poke(false.B)
  d.clock.setTimeout(maxCycles+100);d.clock.step()
  val j=d.io.job.bits
  def context(c:GdnChunkJob):Unit={c.tag.poke(7.U);c.tokens.poke(128.U);c.cold.poke(true.B);c.input.poke("h1000000".U);c.stateIn.poke("h2000000".U);c.stateOut.poke("h3000000".U);c.output.poke("h4000000".U);c.scratch.poke("h10000000".U)}
  context(j.context);context(j.phase1Context)
  for(l<-Seq(j.layout,j.phase1Layout)){l.keyHeads.poke(16.U);l.valueHeads.poke(16.U);l.layoutVersion.poke(1.U);l.rowBytes.poke(25600.U)}
  val r=j.phase1Ready;r.stageComplete.poke(true.B);r.receipt.tag.poke(7.U);r.receipt.phase.poke(1.U);r.receipt.scratchAckBytes.poke(102400.U);r.receipt.drained.poke(true.B);r.addRequests.poke(64.U);r.addResults.poke(64.U);r.readBytes.poke(102400.U)
  d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
  var pending:Option[(BigInt,BigInt)]=None;var cycles=0;var writes=0;var reads=0
  val simStart=System.nanoTime()
  while(!d.io.done.valid.peek().litToBoolean && cycles<maxCycles){
   d.io.response.valid.poke(pending.nonEmpty.B);pending.foreach{case(tag,data)=>d.io.response.bits.tag.poke(tag.U);d.io.response.bits.data.poke(data.U)}
   val consumed=pending.nonEmpty && d.io.response.ready.peek().litToBoolean
   var next:Option[(BigInt,BigInt)]=None
   if(d.io.memory.valid.peek().litToBoolean){
    val rq=d.io.memory.bits;val addr=rq.address.peek().litValue;val tag=rq.tag.peek().litValue
    if(rq.write.peek().litToBoolean){assert(expected.contains(addr),s"unexpected/repeated write $addr");assert(rq.data.peek().litValue==expected.remove(addr).get,s"raw FP32 mismatch address=$addr cycle=$cycles");rq.mask.expect(((BigInt(1)<<64)-1).U);mem(addr)=rq.data.peek().litValue;writes+=1;next=Some(tag->BigInt(0))}
    else {assert(mem.contains(addr),s"unexpected read $addr");reads+=1;next=Some(tag->mem(addr))}
   }
   d.clock.step();cycles+=1;if(consumed)pending=None;if(next.nonEmpty){assert(pending.isEmpty);pending=next}
   if(cycles%100==0)println(s"PROGRESS cycles=$cycles reads=$reads writes=$writes seconds=${(System.nanoTime()-simStart)/1e9}")
  }
  val done=d.io.done.valid.peek().litToBoolean;val out=d.io.done.bits
  val er=out.expRequests.peek().litValue;val ec=out.expResults.peek().litValue;val ar=out.addRequests.peek().litValue;val ac=out.addResults.peek().litValue;val mr=out.mulRequests.peek().litValue;val mc=out.mulResults.peek().litValue
  println(s"CALIBRATION cycles=$cycles reads=$reads writes=$writes expRequests=$er expResults=$ec addRequests=$ar addResults=$ac mulRequests=$mr mulResults=$mc done=$done seconds=${(System.nanoTime()-simStart)/1e9}")
  if(done){out.stageComplete.expect(true.B);out.receipt.status.expect(0.U);out.receipt.drained.expect(true.B);out.readBytes.expect(235584.U);out.receipt.scratchAckBytes.expect(180224.U);out.expRequests.expect(2209.U);out.expResults.expect(2209.U);out.addRequests.expect(2144.U);out.addResults.expect(2144.U);out.mulRequests.expect(2560.U);out.mulResults.expect(2560.U);assert(expected.isEmpty)
   out.decay.valid.expect(true.B);out.decay.value.expect(BigInt(scala.io.Source.fromFile("decay.txt").mkString.trim,16).U)
   out.decay.context.expect(j.context.peek());out.decay.layout.expect(j.layout.peek());out.decay.head.expect(0.U);out.decay.chunk.expect(0.U)
   out.numeric.expect(j.numeric.peek());out.receipt.tag.expect(7.U);out.receipt.expectedGeneration.expect(0.U);out.receipt.head.expect(0.U);out.receipt.chunk.expect(0.U);out.receipt.phase.expect(2.U)
   out.receipt.outputAckBytes.expect(0.U);out.receipt.stateAckBytes.expect(0.U);d.io.resetRequired.expect(false.B)
   val held=out.peek()
   for(_<-0 until 3){d.io.done.valid.expect(true.B);out.expect(held);d.io.memory.valid.expect(false.B);d.clock.step()}
   val actual=new java.io.PrintWriter("actual_memory.tsv");try {mem.toSeq.sortBy(_._1).foreach{case(a,v)=>actual.println(a.toString(16)+"\t"+v.toString(16))}}finally{actual.close()}
   println("FULL_PHASE2_PASS head=0 chunk=0 policy=0")}else{assert(writes>0,"calibration did not reach numerical writes");println("PARTIAL_ONLY_NOT_PHASE2_PASS")}
 }
}
