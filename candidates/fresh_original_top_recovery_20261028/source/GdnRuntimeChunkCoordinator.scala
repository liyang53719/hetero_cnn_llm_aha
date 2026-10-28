// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class GdnRuntimeChunkCoordinatorJob extends Bundle {
  val context=new GdnChunkJob
  val layout=new GdnRuntimeChunkLayout
  val numeric=new GdnRuntimeChunkNumericPolicy
  val prepReductionPolicy=UInt(2.W)
  val prepGatePolicy=UInt(2.W)
  val prepBinding=new GdnRuntimeChunkPrepBindingV8
}
class GdnRuntimeChunkCoordinatorResult extends Bundle {
  val accepted=new GdnRuntimeChunkCoordinatorJob
  val status=UInt(8.W)
  val stagedComplete=Bool()
  val completedHeadChunks=UInt(7.W)
  val jobsIssued=UInt(16.W)
  val jobsCompleted=UInt(16.W)
  val scratchAckBytes=UInt(64.W)
  val outputAckBytes=UInt(64.W)
  val stateAckBytes=UInt(64.W)
  val drained=Bool()
}
class GdnRuntimeChunkCoordinatorPort extends Bundle {
  val job=Flipped(Decoupled(new GdnRuntimeChunkCoordinatorJob))
  val committed=Input(new GdnChunkCommittedState)
  val committedSnapshot=Output(new GdnChunkCommittedState)
  val prepDone=Flipped(Decoupled(new GdnRuntimeRawPrepReceiptV8))
  val stateJob=Decoupled(new GdnChunkStateTransferJob)
  val stateDone=Flipped(Decoupled(new GdnChunkStateTransferResult))
  val loadJob=Decoupled(new GdnRuntimeChunkLoadPrepV2Job)
  val loadDone=Flipped(Decoupled(new GdnRuntimeChunkLoadPrepV2Result))
  val derivedJob=Decoupled(new GdnRuntimeChunkDerivedAndPairV2Job)
  val derivedDone=Flipped(Decoupled(new GdnRuntimeChunkDerivedAndPairV2Result))
  val transposeJob=Decoupled(new GdnRuntimeChunkTransposeV2Job)
  val transposeDone=Flipped(Decoupled(new GdnRuntimeChunkTransposeV2Result))
  val executeJob=Decoupled(new GdnRuntimeChunkExecuteJob)
  val executeDone=Flipped(Decoupled(new GdnRuntimeChunkExecuteResult))
  val fabricFault=Input(Bool())
  val fabricFaultStatus=Input(UInt(8.W))
  val fabricDrained=Input(Bool())
  val done=Decoupled(new GdnRuntimeChunkCoordinatorResult)
  val resetRequired=Output(Bool())
}

/** Actual phase/job FSM over existing fixed physical owners, not software
  * stage logs. Raw-prepared completion and every leaf result are captured from
  * Decoupled ports; each next request depends on an actual successful receipt.
  * M128 is two64-row chunks per head, never128 recurrent M1 jobs. No arithmetic
  * module or leaf module is instantiated: one shared fabric wires these ports.
  * The scheduler must select this job from its accepted profile, not host fields.
  *
  * Root publication is NOT this result: stagedComplete covers private staged
  * state/output only. Conv history/final residual and the parent's block fence
  * remain external. Late fault never mutates a held Decoupled terminal: sticky
  * resetRequired remains independently visible and must veto parent publication.
  * First terminal capture waits for real fabricDrained and gives current/sticky
  * fault priority. No rollback, safe cancellation or bounded watchdog recovery
  * is supplied; a stuck/faulted leaf can require coordinated global reset/drain.
  */
class GdnRuntimeChunkCoordinator extends Module {
  val io=IO(new GdnRuntimeChunkCoordinatorPort)
  val idle :: waitPrep :: issueInit :: waitInit :: issueLoad :: waitLoad :: issueDerived :: waitDerived :: issueTranspose :: waitTranspose :: issueExecute :: waitExecute :: issueExport :: waitExport :: drainFinish :: poisonWait :: finish :: locked :: Nil=Enum(18)
  val state=RegInit(idle)
  val accepted=Reg(new GdnRuntimeChunkCoordinatorJob)
  val root=Reg(new GdnChunkCommittedState)
  val head=RegInit(0.U(5.W));val chunk=RegInit(0.U(1.W));val phase=RegInit(5.U(5.W))
  val prep=Reg(new GdnRuntimeChunkPreparedReceipt)
  val initial=Reg(new GdnChunkStageReceipt)
  val stateReady=Reg(new GdnChunkStageReceipt);val outputReady=Reg(new GdnChunkStageReceipt)
  val predecessor=Reg(new GdnChunkStageReceipt)
  val loadReady=Reg(new GdnRuntimeChunkLoadPrepV2Result)
  val derivedReady=Reg(new GdnRuntimeChunkDerivedAndPairV2Result)
  val decay=Reg(new GdnRuntimeChunkPrivateDecay)
  val pending=RegInit(false.B)
  val activeExport=RegInit(false.B)
  val drainUnknown=RegInit(false.B)
  val poison=RegInit(false.B);val faultStatus=RegInit(Status.Ok.U(8.W))
  val lastLeafDrained=RegInit(true.B)
  val jobsIssued=RegInit(0.U(16.W));val jobsCompleted=RegInit(0.U(16.W))
  val headChunks=RegInit(0.U(7.W))
  val scratchBytes=RegInit(0.U(64.W));val outputBytes=RegInit(0.U(64.W));val stateBytes=RegInit(0.U(64.W))
  val terminal=Reg(new GdnRuntimeChunkCoordinatorResult)
  // Monotonic physical owners are allocated by the existing Guard. A receipt
  // is consumed only on this coordinator's REAL successful prepDone.fire;
  // never on caller valid or a software-supplied acceptance flag.
  val prepConsumed=RegInit(false.B)
  val lastPrepTransaction=Reg(UInt(64.W));val lastPrepOwner=Reg(UInt(32.W))
  val lastChunkOwner=Reg(UInt(32.W))
  val c=accepted.context;val p=accepted.layout
  val chunks=Mux(c.tokens===128.U,2.U(2.W),1.U(2.W))
  val waitingState=state===waitInit || state===waitExport
  val unexpected=(io.prepDone.valid && state=/=idle && state=/=waitPrep && state=/=poisonWait) ||
    (io.stateDone.valid && !(pending && waitingState)) ||
    (io.loadDone.valid && !(pending && state===waitLoad)) ||
    (io.derivedDone.valid && !(pending && state===waitDerived)) ||
    (io.transposeDone.valid && !(pending && state===waitTranspose)) ||
    (io.executeDone.valid && !(pending && state===waitExecute))
  // Poison-wait retains the original wait identity below, so active returns
  // can still be retired. Unexpected inactive terminals require outer recovery.
  val activeKind=RegInit(0.U(3.W)) // state/load/derived/transpose/execute =1..5
  val allLeafTerminalsQuiet= !io.prepDone.valid && !io.stateDone.valid && !io.loadDone.valid &&
    !io.derivedDone.valid && !io.transposeDone.valid && !io.executeDone.valid
  val faultNow=io.fabricFault || (unexpected && state=/=poisonWait) ||
    (state=/=idle && state=/=locked && io.committed.asUInt=/=root.asUInt)
  val nowStatus=Mux(io.fabricFault && io.fabricFaultStatus=/=Status.Ok.U,io.fabricFaultStatus,Status.Protocol.U)
  val stateOffer=HeldDecoupledOffer(state===issueInit || state===issueExport,io.stateJob.ready,poison || faultNow)
  val loadOffer=HeldDecoupledOffer(state===issueLoad,io.loadJob.ready,poison || faultNow)
  val derivedOffer=HeldDecoupledOffer(state===issueDerived,io.derivedJob.ready,poison || faultNow)
  val transposeOffer=HeldDecoupledOffer(state===issueTranspose,io.transposeJob.ready,poison || faultNow)
  val executeOffer=HeldDecoupledOffer(state===issueExecute,io.executeJob.ready,poison || faultNow)
  val heldCommitment=Seq(stateOffer,loadOffer,derivedOffer,transposeOffer,executeOffer).map(x=>x.held && !x.fire).reduce(_||_)

  io.job.ready:=state===idle && !poison && !io.fabricFault && !unexpected
  io.committedSnapshot:=root
  io.prepDone.ready:=state===waitPrep && !poison && !faultNow && io.fabricDrained
  io.stateJob.valid:=stateOffer.valid
  io.loadJob.valid:=loadOffer.valid
  io.derivedJob.valid:=derivedOffer.valid
  io.transposeJob.valid:=transposeOffer.valid
  io.executeJob.valid:=executeOffer.valid
  io.stateDone.ready:=pending && activeKind===1.U
  io.loadDone.ready:=pending && activeKind===2.U
  io.derivedDone.ready:=pending && activeKind===3.U
  io.transposeDone.ready:=pending && activeKind===4.U
  io.executeDone.ready:=pending && activeKind===5.U
  io.stateJob.bits.activeHeads:=p.valueHeads;io.stateJob.bits.context:=c;io.stateJob.bits.head:=head
  io.stateJob.bits.operation:=Mux(state===issueExport,1.U,0.U)
  io.stateJob.bits.nextStateReady:=stateReady;io.stateJob.bits.outputReady:=outputReady
  io.loadJob.bits.context:=c;io.loadJob.bits.numeric:=accepted.numeric
  io.loadJob.bits.keyHeads:=p.keyHeads;io.loadJob.bits.valueHeads:=p.valueHeads
  io.loadJob.bits.head:=head;io.loadJob.bits.chunk:=chunk;io.loadJob.bits.prepReady:=prep
  io.loadJob.bits.initialReady:=initial;io.loadJob.bits.previousStateReady:=stateReady;io.loadJob.bits.previousOutputReady:=outputReady
  io.derivedJob.bits.context:=c;io.derivedJob.bits.numeric:=accepted.numeric;io.derivedJob.bits.layout:=p
  io.derivedJob.bits.head:=head;io.derivedJob.bits.chunk:=chunk
  io.derivedJob.bits.phase1Context:=c;io.derivedJob.bits.phase1Layout:=p;io.derivedJob.bits.phase1Ready:=loadReady
  io.transposeJob.bits.context:=c;io.transposeJob.bits.numeric:=accepted.numeric;io.transposeJob.bits.layout:=p
  io.transposeJob.bits.head:=head;io.transposeJob.bits.chunk:=chunk;io.transposeJob.bits.phase2Ready:=derivedReady
  io.executeJob.bits.context:=c;io.executeJob.bits.layout:=p;io.executeJob.bits.head:=head;io.executeJob.bits.chunk:=chunk
  io.executeJob.bits.phase:=phase;io.executeJob.bits.predecessorContext:=c;io.executeJob.bits.predecessorLayout:=p
  io.executeJob.bits.predecessor:=predecessor;io.executeJob.bits.decay:=decay
  io.done.valid:=state===finish;io.done.bits:=terminal
  io.resetRequired:=poison || faultNow
  def fail(code:UInt):Unit={poison:=true.B;faultStatus:=code;state:=poisonWait}
  def exactIdentity(r:GdnChunkStageReceipt,expected:UInt):Bool=
    r.tag===c.tag && r.expectedGeneration===c.expectedGeneration && r.head===head && r.chunk===chunk && r.phase===expected
  def identity(r:GdnChunkStageReceipt,expected:UInt):Bool=
    exactIdentity(r,expected) && r.status===Status.Ok.U && r.drained
  def unknownReturn():Unit={drainUnknown:=true.B;lastLeafDrained:=false.B;fail(Status.Protocol.U)}
  def account(r:GdnChunkStageReceipt):Unit={
    scratchBytes:=scratchBytes+r.scratchAckBytes;outputBytes:=outputBytes+r.outputAckBytes;stateBytes:=stateBytes+r.stateAckBytes
  }
  def retire(drained:Bool):Unit={pending:=false.B;lastLeafDrained:=drained;jobsCompleted:=jobsCompleted+1.U}
  def capture(ok:Bool,code:UInt):Unit={
    terminal.accepted:=accepted;terminal.status:=code;terminal.stagedComplete:=ok
    terminal.completedHeadChunks:=headChunks;terminal.jobsIssued:=jobsIssued;terminal.jobsCompleted:=jobsCompleted
    terminal.scratchAckBytes:=scratchBytes;terminal.outputAckBytes:=outputBytes;terminal.stateAckBytes:=stateBytes
    terminal.drained:= !pending && !drainUnknown && lastLeafDrained && io.fabricDrained && allLeafTerminalsQuiet
    state:=finish
  }
  when(io.job.fire){
    accepted:=io.job.bits;root:=io.committed;head:=0.U;chunk:=0.U;phase:=5.U
    pending:=false.B;activeKind:=0.U;activeExport:=false.B;drainUnknown:=false.B;lastLeafDrained:=true.B
    jobsIssued:=0.U;jobsCompleted:=0.U;headChunks:=0.U;scratchBytes:=0.U;outputBytes:=0.U;stateBytes:=0.U
    initial:=0.U.asTypeOf(initial);stateReady:=0.U.asTypeOf(stateReady);outputReady:=0.U.asTypeOf(outputReady)
    val j=io.job.bits;val x=j.context
    val badRoot=x.expectedGeneration=/=io.committed.generation || Mux(x.cold,
      x.expectedGeneration=/=0.U || io.committed.valid,x.expectedGeneration===0.U || !io.committed.valid || x.stateIn=/=io.committed.state)
    when(badRoot){fail(Status.Dependency.U)}
      .elsewhen((x.tokens=/=16.U && x.tokens=/=128.U) || !GdnRuntimeChunkLayout.admitted(j.layout) || x.expectedGeneration==="hffffffff".U){fail(Status.Bounds.U)}
      .elsewhen(!GdnRuntimeChunkNumericPolicy.admitted(j.numeric) || j.prepReductionPolicy>1.U || j.prepGatePolicy>2.U){fail(Status.Unsupported.U)}
      .otherwise{state:=waitPrep}
  }
  when(io.prepDone.fire){
    val receipt=io.prepDone.bits;val r=receipt.result;val a=r.accepted
    val b=accepted.prepBinding;val producer=receipt.producer
    val fresh= !prepConsumed || (producer.transactionId>=lastPrepTransaction &&
      producer.ownerSequence>lastPrepOwner && producer.ownerSequence>lastChunkOwner && c.tag>lastChunkOwner)
    val good=r.status===Status.Ok.U && r.outputCommitted && fresh &&
      producer.transactionId===b.transactionId && producer.hostEpoch===b.hostEpoch &&
      producer.ownerSequence===b.producerOwner && producer.ownerSequence=/="hffffffff".U &&
      c.tag=/="hffffffff".U && c.tag>producer.ownerSequence &&
      r.tag===producer.ownerSequence && a.tag===producer.ownerSequence &&
      a.asUInt===b.source.asUInt && a.tokens===c.tokens &&
      a.layout.keyHeads===p.keyHeads && a.layout.valueHeads===p.valueHeads &&
      a.layout.layoutId===p.layoutId && a.layout.layoutVersion===p.layoutVersion &&
      a.layout.rowBytes===p.rowBytes && a.output===c.input &&
      a.reductionPolicy===accepted.prepReductionPolicy && a.gatePolicy===accepted.prepGatePolicy &&
      r.writeBytes===(c.tokens*p.rowBytes).pad(64)
    when(!good){fail(Mux(r.status===Status.Ok.U,Status.Dependency.U,r.status))}.otherwise{
      prepConsumed:=true.B;lastPrepTransaction:=producer.transactionId
      lastPrepOwner:=producer.ownerSequence;lastChunkOwner:=c.tag
      // This is the existing consumer-local stage receipt, not a rewritten
      // producer ACK. The original receipt/result retain P unchanged above.
      prep.tag:=c.tag;prep.expectedGeneration:=c.expectedGeneration;prep.tokens:=c.tokens;prep.input:=c.input
      prep.status:=Status.Ok.U;prep.writeBytes:=r.writeBytes;prep.preparedComplete:=true.B
      prep.drained:=io.fabricDrained;prep.recurrentMode:=false.B;prep.layoutId:=p.layoutId;prep.layoutVersion:=p.layoutVersion
      prep.rowBytes:=p.rowBytes;prep.keyHeads:=p.keyHeads;prep.valueHeads:=p.valueHeads
      state:=issueInit
    }
  }
  for((fire,kind,next)<-Seq((io.stateJob.fire,1,Mux(state===issueInit,waitInit,waitExport)),
    (io.loadJob.fire,2,waitLoad),(io.derivedJob.fire,3,waitDerived),(io.transposeJob.fire,4,waitTranspose),(io.executeJob.fire,5,waitExecute))){
    when(fire){pending:=true.B;activeKind:=kind.U;jobsIssued:=jobsIssued+1.U;state:=next}
  }
  when(io.stateJob.fire){activeExport:=state===issueExport}
  when(io.stateDone.fire){
    val r=io.stateDone.bits
    val exporting=activeExport
    val exact=r.tag===c.tag && r.expectedGeneration===c.expectedGeneration && r.head===head && r.operation===Mux(exporting,1.U,0.U)
    when(exact){retire(r.localDrained)}
    val good=r.tag===c.tag && r.expectedGeneration===c.expectedGeneration && r.head===head &&
      r.operation===Mux(exporting,1.U,0.U) && r.status===Status.Ok.U && r.transferComplete && r.localDrained &&
      r.writeBytes===65536.U && r.readBytes===Mux(!exporting && c.cold,0.U,65536.U)
    when(!exact){unknownReturn()}
      .elsewhen(poison || faultNow){state:=poisonWait}
      .elsewhen(!good){fail(Mux(r.status===Status.Ok.U,Status.Protocol.U,r.status))}
      .elsewhen(!exporting){
        initial.tag:=c.tag;initial.expectedGeneration:=c.expectedGeneration;initial.head:=head;initial.chunk:=0.U
        initial.phase:=0.U;initial.status:=Status.Ok.U;initial.scratchAckBytes:=r.writeBytes
        initial.outputAckBytes:=0.U;initial.stateAckBytes:=0.U;initial.drained:=r.localDrained
        scratchBytes:=scratchBytes+r.writeBytes;state:=issueLoad
      }.otherwise{
        stateBytes:=stateBytes+r.writeBytes
        when(head+&1.U===p.valueHeads){state:=drainFinish}
          .otherwise{head:=head+1.U;chunk:=0.U;phase:=5.U;state:=issueInit}
      }
  }
  when(io.loadDone.fire){
    val r=io.loadDone.bits
    val exact=exactIdentity(r.receipt,1.U) && r.numeric.asUInt===accepted.numeric.asUInt
    when(exact){retire(r.receipt.drained)}
    when(!exact){unknownReturn()}
      .elsewhen(poison || faultNow){state:=poisonWait}
      .elsewhen(!r.stageComplete || !identity(r.receipt,1.U) || r.numeric.asUInt=/=accepted.numeric.asUInt){fail(Mux(r.receipt.status===Status.Ok.U,Status.Dependency.U,r.receipt.status))}
      .otherwise{loadReady:=r;account(r.receipt);state:=issueDerived}
  }
  when(io.derivedDone.fire){
    val r=io.derivedDone.bits
    val exact=exactIdentity(r.receipt,2.U) && r.numeric.asUInt===accepted.numeric.asUInt && r.decay.context.asUInt===c.asUInt && r.decay.layout.asUInt===p.asUInt && r.decay.head===head && r.decay.chunk===chunk
    when(exact){retire(r.receipt.drained)}
    when(!exact){unknownReturn()}
      .elsewhen(poison || faultNow){state:=poisonWait}
      .elsewhen(!r.stageComplete || !identity(r.receipt,2.U) || r.numeric.asUInt=/=accepted.numeric.asUInt){fail(Mux(r.receipt.status===Status.Ok.U,Status.Dependency.U,r.receipt.status))}
      .otherwise{derivedReady:=r;decay:=r.decay;account(r.receipt);state:=issueTranspose}
  }
  when(io.transposeDone.fire){
    val r=io.transposeDone.bits
    val exact=exactIdentity(r.phase3,3.U) && exactIdentity(r.phase4,4.U) && r.numeric.asUInt===accepted.numeric.asUInt && r.decay.context.asUInt===c.asUInt && r.decay.layout.asUInt===p.asUInt && r.decay.head===head && r.decay.chunk===chunk
    when(exact){retire(r.drained)}
    when(!exact){unknownReturn()}
      .elsewhen(poison || faultNow){state:=poisonWait}
      .elsewhen(!r.stageComplete || !r.phase3Complete || !r.phase4Complete || !identity(r.phase3,3.U) ||
        !identity(r.phase4,4.U) || r.numeric.asUInt=/=accepted.numeric.asUInt){fail(Mux(r.status===Status.Ok.U,Status.Dependency.U,r.status))}
      .otherwise{scratchBytes:=scratchBytes+r.phase3.scratchAckBytes+r.phase4.scratchAckBytes
        predecessor:=r.phase4;decay:=r.decay;phase:=5.U;state:=issueExecute}
  }
  when(io.executeDone.fire){
    val r=io.executeDone.bits
    val exact=exactIdentity(r.receipt,phase) && r.context.asUInt===c.asUInt && r.layout.asUInt===p.asUInt
    when(exact){retire(r.receipt.drained)}
    when(!exact){unknownReturn()}
      .elsewhen(poison || faultNow){state:=poisonWait}
      .elsewhen(!r.stageComplete || !identity(r.receipt,phase) || r.context.asUInt=/=c.asUInt || r.layout.asUInt=/=p.asUInt){fail(Mux(r.receipt.status===Status.Ok.U,Status.Dependency.U,r.receipt.status))}
      .otherwise{
        account(r.receipt);predecessor:=r.receipt
        when(phase===16.U){stateReady:=r.receipt}
        when(phase===17.U){
          outputReady:=r.receipt;headChunks:=headChunks+1.U
          when(chunk+&1.U===chunks){state:=issueExport}
            .otherwise{chunk:=chunk+1.U;phase:=5.U;state:=issueLoad}
        }.otherwise{phase:=phase+1.U;state:=issueExecute}
      }
  }
  val expectedHeadChunks=p.valueHeads*chunks
  val expectedJobs=p.valueHeads*(2.U+16.U*chunks)
  val totalsGood=headChunks===expectedHeadChunks && jobsIssued===expectedJobs && jobsCompleted===expectedJobs &&
    scratchBytes===(p.valueHeads*(65536.U+chunks*806912.U)).pad(64) &&
    outputBytes===(c.tokens*p.valueHeads*256.U).pad(64) && stateBytes===(p.valueHeads*65536.U).pad(64)
  when(state===drainFinish && !pending && !drainUnknown && io.fabricDrained && allLeafTerminalsQuiet && lastLeafDrained && !faultNow && !poison){
    when(totalsGood){capture(true.B,Status.Ok.U)}.otherwise{fail(Status.Protocol.U)}
  }
  when(state===poisonWait && !pending && !drainUnknown && io.fabricDrained && allLeafTerminalsQuiet && lastLeafDrained){capture(false.B,faultStatus)}
  // Late fault is independent poison, never a mutation of terminal.bits/valid.
  when(faultNow){
    poison:=true.B
    when(!poison){faultStatus:=nowStatus}
    when(state=/=finish && state=/=locked && !heldCommitment){state:=poisonWait}
  }
  when(io.done.fire){state:=Mux(terminal.status===Status.Ok.U && !poison && !faultNow,idle,locked)}
  assert(PopCount(Seq(io.stateJob.fire,io.loadJob.fire,io.derivedJob.fire,io.transposeJob.fire,io.executeJob.fire))<=1.U)
}
