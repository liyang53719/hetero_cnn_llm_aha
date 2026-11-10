import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.continuous._
// One-shot sequential testbench scheduler, not the production authority router.
// Actual phase1/2 result bundles flow directly across each accepting handshake.
class LoadPrepToPhase5Chain extends Module {
 val io=IO(new GdnRuntimeChunkLoadPrepV2Port)
 val phase2Done=IO(Valid(new GdnRuntimeChunkDerivedAndPairV2Result))
 val transposeDone=IO(Decoupled(new GdnRuntimeChunkTransposeV2Result))
 val phase5Done=IO(Decoupled(new GdnRuntimeChunkExecuteResult))
 val load=Module(new GdnRuntimeChunkLoadPrepV2Owner)
 val owner=Module(new GdnRuntimeChunkDerivedAndPairV2Owner)
 val transpose=Module(new GdnRuntimeChunkTransposeV2Owner)
 val execute=Module(new GdnRuntimeChunkExecuteOwnerV8)
 val scalar=Module(new BlockScalarFloatPolicyV2)
 val bank=Module(new UnifiedVectorElement32BankV4)
 val stage=RegInit(0.U(2.W));val accepted=Reg(new GdnRuntimeChunkLoadPrepV2Job)
 val layout=Wire(new GdnRuntimeChunkLayout)
 layout.keyHeads:=accepted.keyHeads;layout.valueHeads:=accepted.valueHeads
 layout.layoutId:=0.U;layout.layoutVersion:=1.U;layout.rowBytes:=accepted.valueHeads*1600.U
 load.io.job <> io.job
 when(io.job.fire){accepted:=io.job.bits}
 load.io.committed:=io.committed;owner.io.committed:=io.committed;transpose.io.committed:=io.committed;execute.io.committed:=io.committed
 owner.io.job.valid:=load.io.done.valid && stage===0.U
 load.io.done.ready:=owner.io.job.ready && stage===0.U
 owner.io.job.bits.context:=accepted.context;owner.io.job.bits.numeric:=accepted.numeric
 owner.io.job.bits.layout:=layout;owner.io.job.bits.head:=accepted.head;owner.io.job.bits.chunk:=accepted.chunk
 owner.io.job.bits.phase1Context:=accepted.context;owner.io.job.bits.phase1Layout:=layout
 owner.io.job.bits.phase1Ready:=load.io.done.bits
 val loadResult=Reg(new GdnRuntimeChunkLoadPrepV2Result)
 when(load.io.done.fire){loadResult:=load.io.done.bits;stage:=1.U}
 io.done.valid:=stage=/=0.U;io.done.bits:=loadResult
 transpose.io.job.valid:=owner.io.done.valid && stage===1.U
 owner.io.done.ready:=transpose.io.job.ready && stage===1.U
 transpose.io.job.bits.context:=owner.io.done.bits.decay.context
 transpose.io.job.bits.numeric:=owner.io.done.bits.numeric
 transpose.io.job.bits.layout:=owner.io.done.bits.decay.layout
 transpose.io.job.bits.head:=owner.io.done.bits.decay.head;transpose.io.job.bits.chunk:=owner.io.done.bits.decay.chunk
 transpose.io.job.bits.phase2Ready:=owner.io.done.bits
 val derivedResult=Reg(new GdnRuntimeChunkDerivedAndPairV2Result)
 when(owner.io.done.fire){derivedResult:=owner.io.done.bits;stage:=2.U}
 phase2Done.valid:=stage>=2.U;phase2Done.bits:=derivedResult
 execute.io.job.valid:=transpose.io.done.valid && stage===2.U
 transpose.io.done.ready:=execute.io.job.ready && stage===2.U
 execute.io.job.bits.context:=transpose.io.done.bits.decay.context
 execute.io.job.bits.layout:=transpose.io.done.bits.decay.layout
 execute.io.job.bits.head:=transpose.io.done.bits.decay.head
 execute.io.job.bits.chunk:=transpose.io.done.bits.decay.chunk
 execute.io.job.bits.phase:=5.U
 execute.io.job.bits.predecessorContext:=transpose.io.done.bits.decay.context
 execute.io.job.bits.predecessorLayout:=transpose.io.done.bits.decay.layout
 execute.io.job.bits.predecessor:=transpose.io.done.bits.phase4
 execute.io.job.bits.decay:=transpose.io.done.bits.decay
 val transResult=Reg(new GdnRuntimeChunkTransposeV2Result)
 when(transpose.io.done.fire){transResult:=transpose.io.done.bits;stage:=3.U}
 transposeDone.valid:=stage===3.U;transposeDone.bits:=transResult
 phase5Done <> execute.io.done
 io.resetRequired:=load.io.resetRequired || owner.io.resetRequired || transpose.io.resetRequired || execute.io.resetRequired
 io.memory.valid:=Mux(stage===0.U,load.io.memory.valid,Mux(stage===1.U,owner.io.memory.valid,Mux(stage===2.U,transpose.io.memory.valid,execute.io.memory.valid)))
 io.memory.bits:=Mux(stage===0.U,load.io.memory.bits,Mux(stage===1.U,owner.io.memory.bits,Mux(stage===2.U,transpose.io.memory.bits,execute.io.memory.bits)))
 load.io.memory.ready:=io.memory.ready && stage===0.U;owner.io.memory.ready:=io.memory.ready && stage===1.U;transpose.io.memory.ready:=io.memory.ready && stage===2.U;execute.io.memory.ready:=io.memory.ready && stage===3.U
 load.io.response.valid:=io.response.valid && stage===0.U;owner.io.response.valid:=io.response.valid && stage===1.U;transpose.io.response.valid:=io.response.valid && stage===2.U;execute.io.response.valid:=io.response.valid && stage===3.U
 load.io.response.bits:=io.response.bits;owner.io.response.bits:=io.response.bits;transpose.io.response.bits:=io.response.bits;execute.io.response.bits:=io.response.bits
 io.response.ready:=Mux(stage===0.U,load.io.response.ready,Mux(stage===1.U,owner.io.response.ready,Mux(stage===2.U,transpose.io.response.ready,execute.io.response.ready)))
 scalar.io.request.valid:=Mux(stage===0.U,load.io.scalar.request.valid,owner.io.scalar.request.valid && stage===1.U)
 scalar.io.request.bits:=Mux(stage===0.U,load.io.scalar.request.bits,owner.io.scalar.request.bits)
 load.io.scalar.request.ready:=scalar.io.request.ready && stage===0.U;owner.io.scalar.request.ready:=scalar.io.request.ready && stage===1.U
 load.io.scalar.result.valid:=scalar.io.result.valid && stage===0.U;owner.io.scalar.result.valid:=scalar.io.result.valid && stage===1.U
 load.io.scalar.result.bits:=scalar.io.result.bits;owner.io.scalar.result.bits:=scalar.io.result.bits
 scalar.io.result.ready:=Mux(stage===0.U,load.io.scalar.result.ready,owner.io.scalar.result.ready && stage===1.U)
 io.scalar.request.valid:=false.B;io.scalar.request.bits:=0.U.asTypeOf(io.scalar.request.bits);io.scalar.result.ready:=false.B
 // Exactly one original bank, leased sequentially to phase2 or phase5.
 val req=Wire(Decoupled(new UnifiedOrdinaryVectorRequestV5))
 val result=Wire(Decoupled(new UnifiedOrdinaryVectorResultV5))
 req.valid:=Mux(stage===3.U,execute.io.vectorRequest.valid,owner.io.vectorRequest.valid && stage===1.U)
 req.bits:=Mux(stage===3.U,execute.io.vectorRequest.bits,owner.io.vectorRequest.bits)
 owner.io.vectorRequest.ready:=req.ready && stage===1.U;execute.io.vectorRequest.ready:=req.ready && stage===3.U
 owner.io.vectorResult.valid:=result.valid && stage===1.U;execute.io.vectorResult.valid:=result.valid && stage===3.U
 owner.io.vectorResult.bits:=result.bits;execute.io.vectorResult.bits:=result.bits
 result.ready:=Mux(stage===3.U,execute.io.vectorResult.ready,owner.io.vectorResult.ready && stage===1.U)
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
 RawTester.test(new LoadPrepToPhase5Chain,Seq(backend)){d=>
  println(s"ELABORATED seconds=${(System.nanoTime()-start)/1e9}")
  def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case a:Aggregate=>a.getElements.foreach(zero);case _=>()}
  def readWords(file:String)=scala.collection.mutable.Map(scala.io.Source.fromFile(file).getLines().map{line=>val a=line.split("\t");BigInt(a(0),16)->BigInt(a(1),16)}.toSeq:_*)
  val mem=readWords("inputs.tsv");val expected=readWords("expected.tsv");expected ++= readWords("transpose_expected.tsv");expected ++= readWords("phase1_expected.tsv");expected ++= readWords("phase5_expected.tsv")
  zero(d.io.job.bits);zero(d.io.committed);zero(d.io.response.bits);zero(d.io.scalar.result.bits)
  d.io.job.valid.poke(false.B);d.io.memory.ready.poke(true.B);d.io.response.valid.poke(false.B);d.io.done.ready.poke(false.B)
  d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
  d.transposeDone.ready.poke(false.B);d.phase5Done.ready.poke(false.B)
  d.clock.setTimeout(maxCycles+100);d.clock.step()
  val j=d.io.job.bits
  def context(c:GdnChunkJob):Unit={c.tag.poke(7.U);c.tokens.poke(128.U);c.cold.poke(true.B);c.input.poke("h1000000".U);c.stateIn.poke("h2000000".U);c.stateOut.poke("h3000000".U);c.output.poke("h4000000".U);c.scratch.poke("h10000000".U)}
  context(j.context);j.keyHeads.poke(16.U);j.valueHeads.poke(16.U)
  val p=j.prepReady;p.tag.poke(7.U);p.tokens.poke(128.U);p.input.poke("h1000000".U);p.writeBytes.poke((128*25600).U);p.preparedComplete.poke(true.B);p.drained.poke(true.B);p.layoutVersion.poke(1.U);p.rowBytes.poke(25600.U);p.keyHeads.poke(16.U);p.valueHeads.poke(16.U)
  j.initialReady.tag.poke(7.U);j.initialReady.phase.poke(0.U);j.initialReady.drained.poke(true.B);j.initialReady.scratchAckBytes.poke(65536.U)
  d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
  var pending:Option[(BigInt,BigInt)]=None;var cycles=0;var writes=0;var reads=0
  var phase4WrittenSnapshot=Set.empty[BigInt];var sawTransposeHandoff=false;val actualWrites=scala.collection.mutable.Set[BigInt]();var sawLoadHandoff=false;var sawHandoff=false;val actualLoadWrites=scala.collection.mutable.Set[BigInt]();val actualKeWrites=scala.collection.mutable.Set[BigInt]()
  val keBase=BigInt("10000000",16)+65536+233472
  val simStart=System.nanoTime()
  while(!d.phase5Done.valid.peek().litToBoolean && cycles<maxCycles){
   if(d.io.done.valid.peek().litToBoolean && !sawLoadHandoff){
    assert(writes==1600 && reads==1600 && pending.isEmpty,"phase1 handoff must follow all actual acknowledgments")
    assert(actualLoadWrites.size==1600);sawLoadHandoff=true
    val l=d.io.done.bits;l.stageComplete.expect(true.B);l.receipt.status.expect(0.U);l.receipt.drained.expect(true.B);l.receipt.phase.expect(1.U);l.receipt.scratchAckBytes.expect(102400.U);l.readBytes.expect(102400.U);l.addRequests.expect(64.U);l.addResults.expect(64.U);l.numeric.expect(j.numeric.peek());l.receipt.tag.expect(7.U);l.receipt.expectedGeneration.expect(0.U);l.receipt.head.expect(0.U);l.receipt.chunk.expect(0.U);l.receipt.outputAckBytes.expect(0.U);l.receipt.stateAckBytes.expect(0.U)
    println(s"ACTUAL_PHASE1_HANDOFF cycles=$cycles reads=$reads writes=$writes")
   }
   if(d.phase2Done.valid.peek().litToBoolean && !sawHandoff){
    assert(writes==4416 && reads==5281 && pending.isEmpty,"phase2 handoff must follow all real memory acknowledgments")
    assert(actualKeWrites.size==512);sawHandoff=true
    println(s"ACTUAL_PHASE2_HANDOFF cycles=$cycles reads=$reads writes=$writes")
   }
   if(d.transposeDone.valid.peek().litToBoolean && !sawTransposeHandoff){
    assert(reads==6305 && writes==5440 && pending.isEmpty,"transpose handoff precedes actual acknowledgments")
    assert(actualWrites.size==5440);phase4WrittenSnapshot=actualWrites.toSet;sawTransposeHandoff=true
    println(s"ACTUAL_PHASE4_HANDOFF cycles=$cycles reads=$reads writes=$writes")
   }
   d.io.response.valid.poke(pending.nonEmpty.B);pending.foreach{case(tag,data)=>d.io.response.bits.tag.poke(tag.U);d.io.response.bits.data.poke(data.U)}
   val consumed=pending.nonEmpty && d.io.response.ready.peek().litToBoolean
   var next:Option[(BigInt,BigInt)]=None
   if(d.io.memory.valid.peek().litToBoolean){
    val rq=d.io.memory.bits;val addr=rq.address.peek().litValue;val tag=rq.tag.peek().litValue
    if(rq.write.peek().litToBoolean){assert(expected.contains(addr),s"unexpected/repeated write $addr");assert(rq.data.peek().litValue==expected.remove(addr).get,s"raw FP32 mismatch address=$addr cycle=$cycles");rq.mask.expect(((BigInt(1)<<64)-1).U);mem(addr)=rq.data.peek().litValue;actualWrites+=addr;if(addr>=BigInt("10010000",16) && addr<BigInt("10010000",16)+102400)actualLoadWrites+=addr;if(addr>=keBase && addr<keBase+32768)actualKeWrites+=addr;writes+=1;next=Some(tag->BigInt(0))}
    else {if(sawTransposeHandoff)assert(phase4WrittenSnapshot.contains(addr),"phase5 read lacks actual prior-stage write");if(sawLoadHandoff && addr>=BigInt("10010000",16) && addr<BigInt("10010000",16)+102400)assert(actualLoadWrites.contains(addr),"downstream read lacks actual phase1 write");if(sawHandoff && addr>=keBase && addr<keBase+32768)assert(actualKeWrites.contains(addr),"transpose KE read lacks actual phase2 write");assert(mem.contains(addr),s"unexpected read $addr");reads+=1;next=Some(tag->mem(addr))}
   }
   d.clock.step();cycles+=1;if(consumed)pending=None;if(next.nonEmpty){assert(pending.isEmpty);pending=next}
   if(cycles%5000==0)println(s"PROGRESS cycles=$cycles reads=$reads writes=$writes seconds=${(System.nanoTime()-simStart)/1e9}")
  }
  val done=d.phase5Done.valid.peek().litToBoolean;val out=d.phase2Done.bits
  val er=out.expRequests.peek().litValue;val ec=out.expResults.peek().litValue;val ar=out.addRequests.peek().litValue;val ac=out.addResults.peek().litValue;val mr=out.mulRequests.peek().litValue;val mc=out.mulResults.peek().litValue
  println(s"CALIBRATION cycles=$cycles reads=$reads writes=$writes expRequests=$er expResults=$ec addRequests=$ar addResults=$ac mulRequests=$mr mulResults=$mc done=$done seconds=${(System.nanoTime()-simStart)/1e9}")
  if(done){out.stageComplete.expect(true.B);out.receipt.status.expect(0.U);out.receipt.drained.expect(true.B);out.readBytes.expect(235584.U);out.receipt.scratchAckBytes.expect(180224.U);out.expRequests.expect(2209.U);out.expResults.expect(2209.U);out.addRequests.expect(2144.U);out.addResults.expect(2144.U);out.mulRequests.expect(2560.U);out.mulResults.expect(2560.U);assert(expected.isEmpty)
   out.decay.valid.expect(true.B);out.decay.value.expect(BigInt(scala.io.Source.fromFile("decay.txt").mkString.trim,16).U)
   out.decay.context.expect(j.context.peek());out.decay.layout.keyHeads.expect(16.U);out.decay.layout.valueHeads.expect(16.U);out.decay.layout.layoutId.expect(0.U);out.decay.layout.layoutVersion.expect(1.U);out.decay.layout.rowBytes.expect(25600.U);out.decay.head.expect(0.U);out.decay.chunk.expect(0.U)
   out.numeric.expect(j.numeric.peek());out.receipt.tag.expect(7.U);out.receipt.expectedGeneration.expect(0.U);out.receipt.head.expect(0.U);out.receipt.chunk.expect(0.U);out.receipt.phase.expect(2.U)
   out.receipt.outputAckBytes.expect(0.U);out.receipt.stateAckBytes.expect(0.U);d.io.resetRequired.expect(false.B)
   val held=out.peek()
   for(_<-0 until 3){d.phase2Done.valid.expect(true.B);out.expect(held);d.io.memory.valid.expect(false.B);d.clock.step()}
   val actual=new java.io.PrintWriter("actual_memory.tsv");try {mem.toSeq.sortBy(_._1).foreach{case(a,v)=>actual.println(a.toString(16)+"\t"+v.toString(16))}}finally{actual.close()}
   val t=d.transposeDone.bits
   t.status.expect(0.U);t.drained.expect(true.B);t.stageComplete.expect(true.B);t.phase3Complete.expect(true.B);t.phase4Complete.expect(true.B)
   t.phase3ReadBytes.expect(32768.U);t.phase4ReadBytes.expect(32768.U);t.decay.expect(out.decay.peek());t.numeric.expect(out.numeric.peek())
   for((receipt,phase)<-Seq((t.phase3,3),(t.phase4,4))){receipt.tag.expect(7.U);receipt.expectedGeneration.expect(0.U);receipt.head.expect(0.U);receipt.chunk.expect(0.U);receipt.phase.expect(phase.U);receipt.status.expect(0.U);receipt.drained.expect(true.B);receipt.scratchAckBytes.expect(32768.U);receipt.outputAckBytes.expect(0.U);receipt.stateAckBytes.expect(0.U)}
   assert(sawLoadHandoff && sawHandoff);assert(reads==41377 && writes==5696,s"chain counts reads=$reads writes=$writes")
   val terminal=t.peek();for(_<-0 until 3){d.transposeDone.valid.expect(true.B);t.expect(terminal);d.io.memory.valid.expect(false.B);d.clock.step()}
   val f=d.phase5Done.bits
   f.context.expect(out.decay.context.peek());f.layout.expect(out.decay.layout.peek())
   f.stageComplete.expect(true.B);f.receipt.status.expect(0.U);f.receipt.drained.expect(true.B);f.receipt.phase.expect(5.U)
   f.receipt.tag.expect(7.U);f.receipt.expectedGeneration.expect(0.U);f.receipt.head.expect(0.U);f.receipt.chunk.expect(0.U)
   f.receipt.scratchAckBytes.expect(16384.U);f.receipt.outputAckBytes.expect(0.U);f.receipt.stateAckBytes.expect(0.U)
   f.readBytes.expect(2244608.U);f.vectorRequests.expect(65792.U);f.vectorResults.expect(65792.U);assert(sawTransposeHandoff)
   val finalHeld=f.peek();for(_<-0 until 3){d.phase5Done.valid.expect(true.B);f.expect(finalHeld);d.io.memory.valid.expect(false.B);d.clock.step()}
   println(s"PHASE5_PASS read_beats=35072 write_beats=256 vector_requests=65792 vector_results=65792 cycles=${f.cycles.peek().litValue}")
   println("CONNECTED_PHASE1_TO5_PASS head=0 chunk=0 policy=0 prepared_input=synthetic")}else{throw new AssertionError(s"INCOMPLETE_CHAIN cycles=$cycles reads=$reads writes=$writes")}
 }
}
