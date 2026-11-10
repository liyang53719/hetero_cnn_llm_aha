import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.continuous._
// One-shot sequential testbench scheduler, not the production authority router.
// Actual phase1/2 result bundles flow directly across each accepting handshake.
class ColdInitToPhase17Chain extends Module {
 val io=IO(new GdnRuntimeChunkLoadPrepV2Port)
 val phase2Done=IO(Valid(new GdnRuntimeChunkDerivedAndPairV2Result))
 val transposeDone=IO(Decoupled(new GdnRuntimeChunkTransposeV2Result))
 val finalDone=IO(Decoupled(new GdnChunkStateTransferResult))
 val stateDone=IO(Valid(new GdnChunkStateTransferResult))
 val phase5Done=IO(Decoupled(new GdnRuntimeChunkExecuteResult))
 val initializer=Module(new GdnChunkStateTransferOwner)
 val load=Module(new GdnRuntimeChunkLoadPrepV2Owner)
 val owner=Module(new GdnRuntimeChunkDerivedAndPairV2Owner)
 val transpose=Module(new GdnRuntimeChunkTransposeV2Owner)
 val execute=Module(new GdnRuntimeChunkExecuteOwnerV8)
 val scalar=Module(new BlockScalarFloatPolicyV2)
 val bank=Module(new UnifiedVectorElement32BankV4)
 val raw=Module(new GdnRuntimeRawPrepOwnerV7)
 val rawActive=RegInit(true.B);val rawStarted=RegInit(false.B);val rawFinished=RegInit(false.B)
 val rawDrained=RegInit(false.B)
 val rawResult=Reg(new GdnRuntimeRawPrepResultV7)
 val rawDone=IO(Valid(new GdnRuntimeRawPrepResultV7))
 rawDone.valid:=rawFinished;rawDone.bits:=rawResult
 raw.io.job.valid:=io.job.valid && !rawStarted
 raw.io.job.bits:=0.U.asTypeOf(raw.io.job.bits)
 raw.io.job.bits.tokens:=io.job.bits.context.tokens;raw.io.job.bits.tag:=io.job.bits.context.tag
 raw.io.job.bits.conv:="h6000000".U;raw.io.job.bits.ab:="h7000000".U
 raw.io.job.bits.aLog:="h8000000".U;raw.io.job.bits.dtBias:="h9000000".U
 raw.io.job.bits.output:=io.job.bits.context.input
 raw.io.job.bits.layout.keyHeads:=io.job.bits.keyHeads;raw.io.job.bits.layout.valueHeads:=io.job.bits.valueHeads
 raw.io.job.bits.layout.layoutVersion:=1.U;raw.io.job.bits.layout.rowBytes:=io.job.bits.valueHeads*1600.U
 raw.io.prepare.ready:=true.B;raw.io.done.ready:=true.B;raw.io.parentFault:=false.B
 when(raw.io.job.fire){rawStarted:=true.B}
 when(raw.io.done.fire){rawDrained:=raw.io.resourcesDrained;rawResult:=raw.io.done.bits;rawActive:=false.B;rawFinished:=true.B}
 val stage=RegInit(0.U(2.W));val accepted=Reg(new GdnRuntimeChunkLoadPrepV2Job)
 val layout=Wire(new GdnRuntimeChunkLayout)
 layout.keyHeads:=accepted.keyHeads;layout.valueHeads:=accepted.valueHeads
 layout.layoutId:=0.U;layout.layoutVersion:=1.U;layout.rowBytes:=accepted.valueHeads*1600.U
 val coreMemory=Wire(Decoupled(new MemoryRequest))
 val coreResponse=Wire(Decoupled(new MemoryResponse))
 val initializing=RegInit(true.B);val started=RegInit(false.B)
 val exporting=RegInit(false.B);val exportPending=RegInit(false.B);val restartLoad=RegInit(false.B)
 val lastState=Reg(new GdnChunkStageReceipt);val lastOutput=Reg(new GdnChunkStageReceipt)
 val transferActive=initializing || exporting
 initializer.io.job.valid:=(rawFinished && !started) || exportPending
 io.job.ready:=raw.io.job.ready && !rawStarted
 initializer.io.job.bits:=0.U.asTypeOf(initializer.io.job.bits)
 initializer.io.job.bits.activeHeads:=Mux(rawStarted,accepted.valueHeads,io.job.bits.valueHeads)
 initializer.io.job.bits.context:=Mux(rawStarted,accepted.context,io.job.bits.context)
 initializer.io.job.bits.head:=Mux(rawStarted,accepted.head,io.job.bits.head)
 initializer.io.job.bits.operation:=Mux(exporting,1.U,0.U)
 initializer.io.job.bits.nextStateReady:=lastState;initializer.io.job.bits.outputReady:=lastOutput
 when(initializer.io.job.fire && exporting){exportPending:=false.B}
 initializer.io.committed:=io.committed
 when(initializer.io.job.fire && !started){started:=true.B}
 load.io.job.valid:=(initializer.io.done.valid && initializing) || restartLoad
 initializer.io.done.ready:=Mux(initializing,load.io.job.ready,finalDone.ready && exporting)
 finalDone.valid:=initializer.io.done.valid && exporting;finalDone.bits:=initializer.io.done.bits
 load.io.job.bits:=accepted
 load.io.job.bits.prepReady:=0.U.asTypeOf(load.io.job.bits.prepReady)
 load.io.job.bits.prepReady.tag:=rawResult.tag;load.io.job.bits.prepReady.tokens:=rawResult.accepted.tokens
 load.io.job.bits.prepReady.input:=rawResult.accepted.output;load.io.job.bits.prepReady.writeBytes:=rawResult.writeBytes
 load.io.job.bits.prepReady.preparedComplete:=rawResult.outputCommitted && rawResult.status===0.U
 load.io.job.bits.prepReady.drained:=rawFinished && rawDrained
 load.io.job.bits.prepReady.layoutVersion:=rawResult.accepted.layout.layoutVersion
 load.io.job.bits.prepReady.rowBytes:=rawResult.accepted.layout.rowBytes
 load.io.job.bits.prepReady.keyHeads:=rawResult.accepted.layout.keyHeads;load.io.job.bits.prepReady.valueHeads:=rawResult.accepted.layout.valueHeads
 load.io.job.bits.previousStateReady:=lastState
 load.io.job.bits.previousOutputReady:=lastOutput
 when(load.io.job.fire){restartLoad:=false.B}
 val initialReceipt=load.io.job.bits.initialReady
 initialReceipt.tag:=initializer.io.done.bits.tag
 initialReceipt.expectedGeneration:=initializer.io.done.bits.expectedGeneration
 initialReceipt.head:=initializer.io.done.bits.head
 initialReceipt.chunk:=0.U;initialReceipt.phase:=0.U
 initialReceipt.status:=initializer.io.done.bits.status
 initialReceipt.scratchAckBytes:=initializer.io.done.bits.writeBytes
 initialReceipt.outputAckBytes:=0.U;initialReceipt.stateAckBytes:=0.U
 initialReceipt.drained:=initializer.io.done.bits.localDrained && initializer.io.done.bits.transferComplete
 val stateResult=Reg(new GdnChunkStateTransferResult)
 when(initializer.io.done.fire && initializing){initializing:=false.B;stateResult:=initializer.io.done.bits}
 stateDone.valid:= !initializing;stateDone.bits:=stateResult
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
 val pendingExecute=RegInit(false.B)
 val previousExecute=Reg(new GdnRuntimeChunkExecuteResult)
 execute.io.job.valid:=Mux(stage===2.U,transpose.io.done.valid,pendingExecute && stage===3.U)
 transpose.io.done.ready:=execute.io.job.ready && stage===2.U
 val first=stage===2.U
 execute.io.job.bits.context:=Mux(first,transpose.io.done.bits.decay.context,previousExecute.context)
 execute.io.job.bits.layout:=Mux(first,transpose.io.done.bits.decay.layout,previousExecute.layout)
 execute.io.job.bits.head:=Mux(first,transpose.io.done.bits.decay.head,previousExecute.receipt.head)
 execute.io.job.bits.chunk:=Mux(first,transpose.io.done.bits.decay.chunk,previousExecute.receipt.chunk)
 execute.io.job.bits.phase:=Mux(first,5.U,previousExecute.receipt.phase+1.U)
 execute.io.job.bits.predecessorContext:=Mux(first,transpose.io.done.bits.decay.context,previousExecute.context)
 execute.io.job.bits.predecessorLayout:=Mux(first,transpose.io.done.bits.decay.layout,previousExecute.layout)
 execute.io.job.bits.predecessor:=Mux(first,transpose.io.done.bits.phase4,previousExecute.receipt)
 execute.io.job.bits.decay:=derivedResult.decay
 when(execute.io.job.fire){pendingExecute:=false.B}
 when(execute.io.done.fire && execute.io.done.bits.receipt.phase<17.U){previousExecute:=execute.io.done.bits;pendingExecute:=true.B}
 val transResult=Reg(new GdnRuntimeChunkTransposeV2Result)
 when(transpose.io.done.fire){transResult:=transpose.io.done.bits;stage:=3.U}
 transposeDone.valid:=stage===3.U;transposeDone.bits:=transResult
 phase5Done.valid:=execute.io.done.valid;phase5Done.bits:=execute.io.done.bits
 execute.io.done.ready:=true.B
 when(execute.io.done.fire && execute.io.done.bits.receipt.phase===16.U){lastState:=execute.io.done.bits.receipt}
 when(execute.io.done.fire && execute.io.done.bits.receipt.phase===17.U){
  lastOutput:=execute.io.done.bits.receipt
  when(accepted.chunk===0.U){accepted.chunk:=1.U;stage:=0.U;restartLoad:=true.B}
   .otherwise{exporting:=true.B;exportPending:=true.B}
 }
 io.resetRequired:=initializer.io.resetRequired || load.io.resetRequired || owner.io.resetRequired || transpose.io.resetRequired || execute.io.resetRequired
 coreMemory.valid:=Mux(stage===0.U,load.io.memory.valid,Mux(stage===1.U,owner.io.memory.valid,Mux(stage===2.U,transpose.io.memory.valid,execute.io.memory.valid)))
 coreMemory.bits:=Mux(stage===0.U,load.io.memory.bits,Mux(stage===1.U,owner.io.memory.bits,Mux(stage===2.U,transpose.io.memory.bits,execute.io.memory.bits)))
 load.io.memory.ready:=coreMemory.ready && stage===0.U;owner.io.memory.ready:=coreMemory.ready && stage===1.U;transpose.io.memory.ready:=coreMemory.ready && stage===2.U;execute.io.memory.ready:=coreMemory.ready && stage===3.U
 load.io.response.valid:=coreResponse.valid && stage===0.U;owner.io.response.valid:=coreResponse.valid && stage===1.U;transpose.io.response.valid:=coreResponse.valid && stage===2.U;execute.io.response.valid:=coreResponse.valid && stage===3.U
 load.io.response.bits:=coreResponse.bits;owner.io.response.bits:=coreResponse.bits;transpose.io.response.bits:=coreResponse.bits;execute.io.response.bits:=coreResponse.bits
 coreResponse.ready:=Mux(stage===0.U,load.io.response.ready,Mux(stage===1.U,owner.io.response.ready,Mux(stage===2.U,transpose.io.response.ready,execute.io.response.ready)))
 scalar.io.request.valid:=Mux(stage===0.U,load.io.scalar.request.valid,owner.io.scalar.request.valid && stage===1.U)
 scalar.io.request.bits:=Mux(stage===0.U,load.io.scalar.request.bits,owner.io.scalar.request.bits)
 load.io.scalar.request.ready:=scalar.io.request.ready && stage===0.U;owner.io.scalar.request.ready:=scalar.io.request.ready && stage===1.U
 load.io.scalar.result.valid:=scalar.io.result.valid && stage===0.U;owner.io.scalar.result.valid:=scalar.io.result.valid && stage===1.U
 load.io.scalar.result.bits:=scalar.io.result.bits;owner.io.scalar.result.bits:=scalar.io.result.bits
 scalar.io.result.ready:=Mux(stage===0.U,load.io.scalar.result.ready,owner.io.scalar.result.ready && stage===1.U)
 io.scalar.request.valid:=false.B;io.scalar.request.bits:=0.U.asTypeOf(io.scalar.request.bits);io.scalar.result.ready:=false.B
 io.memory.valid:=Mux(transferActive,initializer.io.memory.valid,coreMemory.valid)
 io.memory.bits:=Mux(transferActive,initializer.io.memory.bits,coreMemory.bits)
 initializer.io.memory.ready:=io.memory.ready && transferActive
 coreMemory.ready:=io.memory.ready && !transferActive
 initializer.io.response.valid:=io.response.valid && transferActive
 initializer.io.response.bits:=io.response.bits
 coreResponse.valid:=io.response.valid && !transferActive;coreResponse.bits:=io.response.bits
 io.response.ready:=Mux(transferActive,initializer.io.response.ready,coreResponse.ready)
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
 // RawPrep owns the same scalar/bank/memory before any initializer or chunk work.
 raw.io.scalar.request.ready:=scalar.io.request.ready && rawActive
 raw.io.scalar.result.valid:=scalar.io.result.valid && rawActive;raw.io.scalar.result.bits:=scalar.io.result.bits
 raw.io.formatRequest.ready:=bank.io.request.ready && rawActive
 raw.io.formatResult.valid:=bank.io.result.valid && rawActive
 raw.io.formatResult.bits.value:=bank.io.result.bits.payload.value(0)(31,16)
 raw.io.formatResult.bits.error:=bank.io.result.bits.payload.error
 raw.io.memory.ready:=io.memory.ready && rawActive
 raw.io.response.valid:=io.response.valid && rawActive;raw.io.response.bits:=io.response.bits
 when(rawActive){
  scalar.io.request.valid:=raw.io.scalar.request.valid;scalar.io.request.bits:=raw.io.scalar.request.bits
  scalar.io.result.ready:=raw.io.scalar.result.ready
  load.io.scalar.request.ready:=false.B;owner.io.scalar.request.ready:=false.B
  load.io.scalar.result.valid:=false.B;owner.io.scalar.result.valid:=false.B
  bank.io.request.valid:=raw.io.formatRequest.valid;bank.io.request.bits.payload.policy:=4.U
  bank.io.request.bits.payload.multiply:=false.B
  for(i<-0 until 32){bank.io.request.bits.payload.a(i):=(if(i==0)raw.io.formatRequest.bits.value else 0.U);bank.io.request.bits.payload.b(i):=0.U}
  bank.io.result.ready:=raw.io.formatResult.ready;req.ready:=false.B;result.valid:=false.B
  io.memory.valid:=raw.io.memory.valid;io.memory.bits:=raw.io.memory.bits;io.response.ready:=raw.io.response.ready
  initializer.io.memory.ready:=false.B;initializer.io.response.valid:=false.B;coreMemory.ready:=false.B;coreResponse.valid:=false.B
 }
 when(raw.io.resetRequired){io.resetRequired:=true.B}

}

object DerivedCheck extends App {
 val head=args.find(_.startsWith("--head=")).map(_.drop(7).toInt).getOrElse(0);require(head>=0 && head<16)
 val maxCycles=args.find(_.startsWith("--cycles=")).map(_.drop(9).toInt).getOrElse(8000000)
 val backend=if(args.contains("--verilator"))VerilatorBackendAnnotation else TreadleBackendAnnotation
 val start=System.nanoTime()
 RawTester.test(new ColdInitToPhase17Chain,Seq(backend)){d=>
  println(s"ELABORATED seconds=${(System.nanoTime()-start)/1e9}")
  def zero(x:Data):Unit=x match{case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case a:Aggregate=>a.getElements.foreach(zero);case _=>()}
  def readWords(file:String)=scala.collection.mutable.Map(scala.io.Source.fromFile(file).getLines().map{line=>val a=line.split("\t");BigInt(a(0),16)->BigInt(a(1),16)}.toSeq:_*)
  val mem=readWords("inputs.tsv");val expected=readWords("expected.tsv")
  val decays=scala.io.Source.fromFile("decay.txt").getLines().map(BigInt(_,16)).toVector
  zero(d.io.job.bits);zero(d.io.committed);zero(d.io.response.bits);zero(d.io.scalar.result.bits)
  d.io.job.valid.poke(false.B);d.io.memory.ready.poke(true.B);d.io.response.valid.poke(false.B);d.io.done.ready.poke(false.B)
  d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
  d.transposeDone.ready.poke(false.B);d.phase5Done.ready.poke(false.B);d.finalDone.ready.poke(false.B)
  d.clock.setTimeout(maxCycles+100);d.clock.step()
  val j=d.io.job.bits;val c=j.context
  c.tag.poke(7.U);c.tokens.poke(128.U);c.cold.poke(true.B);c.input.poke("h1000000".U);c.stateIn.poke("h2000000".U);c.stateOut.poke("h3000000".U);c.output.poke("h4000000".U);c.scratch.poke("h10000000".U)
  j.head.poke(head.U);j.keyHeads.poke(16.U);j.valueHeads.poke(16.U)
  d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
  var pending:Option[(BigInt,BigInt)]=None;var cycles=0;var writes=0;var reads=0
  val actualWrites=scala.collection.mutable.Set[BigInt]();val seen=scala.collection.mutable.Set[(Int,Int)]()
  val counts=Map(5->(35072,256,65792),6->(35072,256,65792),7->(17888,512,32768),8->(17888,512,32768),9->(69632,512,131072),10->(1024,512,512),11->(69632,512,131072),12->(34816,512,65536),13->(1024,512,512),14->(69632,1024,131072),15->(1024,1024,1024),16->(2048,1024,1024),17->(512,256,512))
  def common(r:GdnChunkStageReceipt,phase:Int,chunk:Int):Unit={r.tag.expect(7.U);r.expectedGeneration.expect(0.U);r.head.expect(head.U);r.chunk.expect(chunk.U);r.phase.expect(phase.U);r.status.expect(0.U);r.drained.expect(true.B);r.stateAckBytes.expect(0.U)}
  def layout(l:GdnRuntimeChunkLayout):Unit={l.keyHeads.expect(16.U);l.valueHeads.expect(16.U);l.layoutId.expect(0.U);l.layoutVersion.expect(1.U);l.rowBytes.expect(25600.U)}
  def exactTotals(chunk:Int,rd:Int,wr:Int):Unit={assert(reads==24833+chunk*361569+rd && writes==51200+1024+chunk*12864+wr && pending.isEmpty,s"counts chunk=$chunk reads=$reads writes=$writes pending=$pending")}
  def checkExecute():Unit={
   val f=d.phase5Done.bits;val phase=f.receipt.phase.peek().litValue.toInt;val chunk=f.receipt.chunk.peek().litValue.toInt
   assert(!seen.contains((chunk,phase)),s"duplicate completion chunk=$chunk phase=$phase")
   assert((1 until phase).forall(p=>seen.contains((chunk,p))))
   val (rd,wr,vc)=counts(phase);common(f.receipt,phase,chunk);f.context.expect(j.context.peek());layout(f.layout)
   f.stageComplete.expect(true.B);f.readBytes.expect((rd*64L).U);f.vectorRequests.expect(vc.U);f.vectorResults.expect(vc.U)
   f.receipt.scratchAckBytes.expect((if(phase==17)0 else wr*64L).U);f.receipt.outputAckBytes.expect((if(phase==17)wr*64L else 0).U)
   exactTotals(chunk,6305+(5 to phase).map(p=>counts(p)._1).sum,5440+(5 to phase).map(p=>counts(p)._2).sum)
   seen+=((chunk,phase));println(s"ACTUAL_EXECUTE_HANDOFF chunk=$chunk phase=$phase cycles=$cycles reads=$reads writes=$writes vectors=$vc ownerCycles=${f.cycles.peek().litValue}")
  }
  val simStart=System.nanoTime()
  while(!d.finalDone.valid.peek().litToBoolean && cycles<maxCycles){
   if(d.rawDone.valid.peek().litToBoolean && !seen.contains((-2,0))){
    assert(reads==24833 && writes==51200 && pending.isEmpty)
    d.rawDone.bits.tag.expect(7.U);d.rawDone.bits.status.expect(0.U);d.rawDone.bits.outputCommitted.expect(true.B)
    d.rawDone.bits.writeBytes.expect((128*25600).U);seen+=((-2,0));println(s"ACTUAL_RAWPREP_RECEIPT cycles=$cycles reads=$reads writes=$writes")
   }
   if(d.stateDone.valid.peek().litToBoolean && !seen.contains((-1,0))){
    assert(reads==24833 && writes==52224 && pending.isEmpty);val st=d.stateDone.bits
    st.tag.expect(7.U);st.expectedGeneration.expect(0.U);st.head.expect(head.U);st.operation.expect(0.U);st.status.expect(0.U);st.transferComplete.expect(true.B);st.localDrained.expect(true.B);st.readBytes.expect(0.U);st.writeBytes.expect(65536.U)
    seen+=((-1,0));println(s"ACTUAL_INITIALIZER_HANDOFF cycles=$cycles writes=$writes")
   }
   if(d.io.done.valid.peek().litToBoolean){val l=d.io.done.bits;val ch=l.receipt.chunk.peek().litValue.toInt;if(!seen.contains((ch,1))){
    assert(seen.contains((-1,0)));if(ch==1)assert(seen.contains((0,17)))
    exactTotals(ch,1600,1600);common(l.receipt,1,ch);l.stageComplete.expect(true.B);l.readBytes.expect(102400.U);l.receipt.scratchAckBytes.expect(102400.U);l.receipt.outputAckBytes.expect(0.U);l.addRequests.expect(64.U);l.addResults.expect(64.U);l.numeric.expect(j.numeric.peek())
    seen+=((ch,1));println(s"ACTUAL_PHASE1_HANDOFF chunk=$ch cycles=$cycles reads=$reads writes=$writes")
   }}
   if(d.phase2Done.valid.peek().litToBoolean){val f=d.phase2Done.bits;val ch=f.receipt.chunk.peek().litValue.toInt;if(!seen.contains((ch,2))){
    assert(seen.contains((ch,1)));exactTotals(ch,5281,4416);common(f.receipt,2,ch);f.stageComplete.expect(true.B);f.readBytes.expect(235584.U);f.receipt.scratchAckBytes.expect(180224.U);f.receipt.outputAckBytes.expect(0.U)
    f.expRequests.expect(2209.U);f.expResults.expect(2209.U);f.addRequests.expect(2144.U);f.addResults.expect(2144.U);f.mulRequests.expect(2560.U);f.mulResults.expect(2560.U);f.numeric.expect(j.numeric.peek())
    f.decay.valid.expect(true.B);f.decay.value.expect(decays(ch).U);f.decay.context.expect(j.context.peek());layout(f.decay.layout);f.decay.head.expect(head.U);f.decay.chunk.expect(ch.U)
    seen+=((ch,2));println(s"ACTUAL_PHASE2_HANDOFF chunk=$ch cycles=$cycles reads=$reads writes=$writes")
   }}
   if(d.transposeDone.valid.peek().litToBoolean){val t=d.transposeDone.bits;val ch=t.decay.chunk.peek().litValue.toInt;if(!seen.contains((ch,4))){
    assert(seen.contains((ch,2)));exactTotals(ch,6305,5440);t.status.expect(0.U);t.drained.expect(true.B);t.stageComplete.expect(true.B);t.phase3Complete.expect(true.B);t.phase4Complete.expect(true.B)
    t.phase3ReadBytes.expect(32768.U);t.phase4ReadBytes.expect(32768.U);t.decay.expect(d.phase2Done.bits.decay.peek());t.numeric.expect(j.numeric.peek())
    for((r,p)<-Seq((t.phase3,3),(t.phase4,4))){common(r,p,ch);r.scratchAckBytes.expect(32768.U);r.outputAckBytes.expect(0.U)}
    seen+=((ch,3));seen+=((ch,4));println(s"ACTUAL_PHASE4_HANDOFF chunk=$ch cycles=$cycles reads=$reads writes=$writes")
   }}
   if(d.phase5Done.valid.peek().litToBoolean)checkExecute()
   d.io.response.valid.poke(pending.nonEmpty.B);pending.foreach{case(tag,data)=>d.io.response.bits.tag.poke(tag.U);d.io.response.bits.data.poke(data.U)}
   val consumed=pending.nonEmpty && d.io.response.ready.peek().litToBoolean;var next:Option[(BigInt,BigInt)]=None
   if(d.io.memory.valid.peek().litToBoolean){
    d.io.memory.ready.expect(true.B);assert(pending.isEmpty,"more than one outstanding memory transaction")
    val rq=d.io.memory.bits;val addr=rq.address.peek().litValue;val tag=rq.tag.peek().litValue
    if(rq.write.peek().litToBoolean){assert(expected.contains(addr),s"unexpected/repeated write address=$addr cycle=$cycles")
     val observed=rq.data.peek().litValue;val want=expected.remove(addr).get
     assert(observed==want,s"numerical mismatch address=${addr.toString(16)} cycle=$cycles actual=${observed.toString(16)} expected=${want.toString(16)}")
     rq.mask.expect(((BigInt(1)<<64)-1).U);mem(addr)=observed;actualWrites+=addr;writes+=1;next=Some(tag->BigInt(0))
    }else{if(addr>=BigInt("10000000",16) || (addr>=BigInt("1000000",16) && addr<BigInt("1000000",16)+128*25600))assert(actualWrites.contains(addr),s"scratch read lacks actual accepted producer write address=$addr")
     assert(mem.contains(addr),s"unexpected read $addr");reads+=1;next=Some(tag->mem(addr))}
   }
   d.clock.step();cycles+=1;if(consumed)pending=None;if(next.nonEmpty){assert(pending.isEmpty);pending=next}
   if(cycles%200000==0)println(s"PROGRESS cycles=$cycles reads=$reads writes=$writes seconds=${(System.nanoTime()-simStart)/1e9}")
  }
  assert(d.finalDone.valid.peek().litToBoolean,s"INCOMPLETE_CHAIN cycles=$cycles reads=$reads writes=$writes")
  assert((0 to 1).forall(ch=>(1 to 17).forall(p=>seen.contains((ch,p)))))
  assert(expected.isEmpty && pending.isEmpty && reads==748995 && writes==78976);d.io.resetRequired.expect(false.B)
  val f=d.finalDone.bits;f.tag.expect(7.U);f.expectedGeneration.expect(0.U);f.head.expect(head.U);f.operation.expect(1.U);f.status.expect(0.U);f.readBytes.expect(65536.U);f.writeBytes.expect(65536.U);f.transferComplete.expect(true.B);f.localDrained.expect(true.B)
  val held=f.peek();for(_<-0 until 3){d.finalDone.valid.expect(true.B);f.expect(held);d.io.memory.valid.expect(false.B);d.clock.step()}
  val actual=new java.io.PrintWriter("actual_memory.tsv");try{mem.toSeq.sortBy(_._1).foreach{case(a,v)=>actual.println(a.toString(16)+"\t"+v.toString(16))}}finally{actual.close()}
  println(s"CONNECTED_RAWPREP_COLD_INIT_TWO_CHUNKS_EXPORT_PASS tokens=128 head=$head cycles=$cycles reads=$reads writes=$writes executeVectorCalls=1318912 phase17FormatCalls=1024 seconds=${(System.nanoTime()-simStart)/1e9}")
 }
}
