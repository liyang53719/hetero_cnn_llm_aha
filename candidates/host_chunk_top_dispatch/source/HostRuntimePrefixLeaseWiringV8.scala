// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Ordinary runtime RMS/Conv/RawPrep authority, never a MoE allocation or Host grant.
  * Real Guard logical acceptance captures provenance. Only the corresponding
  * physicalJob.fire acquires RMS/Conv leases; RawPrep defers until its real prepared DDR event; only its matching
  * physicalDone.fire retires them. Scope stage69/70/71 covers the WHOLE ordinary job.
  * Registers below are metadata, not a second dispatcher or numerical bank.
  */
object HostRuntimePrefixLeaseWiringV8 {
  class View extends Bundle {
    val owned=Bool();val localFault=Bool();val eventsPending=Bool();val resourcesDrained=Bool()
    val host=new HostCommandLaunchV4
    val transactionId=UInt(64.W);val job=new QwenOwnerJob
    // Read-only snapshot, NOT Decoupled: eligibility may be revoked on fault
    // or context change. No external/fabricated consume input exists.
    val prepReceipt=Valid(new GdnRuntimeRawPrepReceiptV8)
    val scalarAcquire=Valid(new UnifiedMoeArithmeticLeaseV5)
    val scalarRetire=Valid(new UnifiedMoeArithmeticRetireV5)
  }
  def connect(a:UnifiedMoeSharedArithmeticAdapterV5,g:HostRuntimeOwnerGuardV5,
      authority:HostRuntimeAuthoritySnapshotV4,k:QwenOwnerKernel,currentIndependentFault:Bool,scalarPort:UnifiedScalarClientV2):View={
    val out=Wire(new View)
    val logical=Reg(new QwenOwnerJob);val host=Reg(new HostCommandLaunchV4)
    val transaction=Reg(UInt(64.W));val physical=Reg(UInt(32.W))
    val waiting=RegInit(false.B);val owned=RegInit(false.B);val poison=RegInit(false.B)
    val acquirePending=RegInit(false.B);val retirePending=RegInit(false.B)
    val leaseEventSubmitted=RegInit(false.B);val awaitPrepare=RegInit(false.B)
    val retireStatus=Reg(UInt(8.W));val leases=Reg(Vec(2,new UnifiedMoeArithmeticLeaseV5))
    val prepReceiptValid=RegInit(false.B)
    val prepReceipt=Reg(new GdnRuntimeRawPrepReceiptV8)
    val slots=Seq(8,9)
    val busy=waiting || owned || awaitPrepare || acquirePending || retirePending || k.io.runtimePrepPrepare.get.valid ||
      slots.map(i=>a.io.status(i).active || a.io.status(i).retiring).reduce(_||_)
    val contextChanged=(waiting || owned) && (!authority.accepted ||
      authority.transaction=/=transaction || authority.launch.asUInt=/=host.asUInt)
    when(contextChanged || ((waiting || owned) &&
      (currentIndependentFault || authority.currentFault || g.io.localFault))){poison:=true.B}
    def isPrefix(kind:UInt):Bool=kind===QwenOwnerKind.GdnRmsNorm.U || kind===QwenOwnerKind.GdnConv.U || kind===QwenOwnerKind.GdnInputPrep.U
    val logicalStart=g.io.job.fire && isPrefix(g.io.job.bits.kind)
    // Acceptance authority is the original Guard handshake, not equality of
    // a raw job to a Host-provided packet. Its full snapshot is retained here.
    when(logicalStart){
      when(busy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        authority.currentFault || authority.ownerJob.asUInt=/=g.io.job.bits.asUInt){poison:=true.B}
      .otherwise{logical:=g.io.job.bits;host:=authority.launch;transaction:=authority.transaction;waiting:=true.B}
    }
    // A replacement producer invalidates the old private snapshot at the
    // real Guard logical acceptance, even if that replacement later fails.
    val prepReplacement=logicalStart && g.io.job.bits.kind===QwenOwnerKind.GdnInputPrep.U
    when(prepReplacement){prepReceiptValid:=false.B}
    val expected=WireDefault(logical);expected.tag:=g.io.physicalJob.bits.tag
    val normShape=logical.kind===QwenOwnerKind.GdnRmsNorm.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===logical.n &&
      Mux(host.profileId===1.U || host.profileId===2.U,logical.n===1024.U,
        (host.profileId===3.U || host.profileId===4.U) && logical.n===2048.U) &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)<<1)(63,0)
    val convShape=logical.kind===QwenOwnerKind.GdnConv.U &&
      logical.activationBf16 && logical.weightBf16 && logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===4.U &&
      Mux(host.profileId===1.U,logical.n===6144.U,host.profileId===3.U && logical.n===8192.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(((logical.m.pad(80)*logical.n.pad(80))<<1)+(logical.n.pad(80)<<3))(63,0)
    val prepShape=logical.kind===QwenOwnerKind.GdnInputPrep.U &&
      logical.activationBf16 && !logical.weightBf16 && !logical.outputBf16 &&
      logical.m>=1.U && logical.m<=128.U && logical.k===128.U &&
      Mux(host.profileId===1.U,logical.n===16.U,host.profileId===3.U && logical.n===32.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U && !logical.gdnRecurrentMode &&
      logical.writeBytes===(logical.m.pad(80)*logical.n.pad(80)*1600.U)(63,0)
    val logicalShape=normShape || convShape || prepShape
    val physicalExact=waiting && !owned && !g.io.phaseReserved && !contextChanged &&
      g.io.acceptedTransaction===transaction && g.io.physicalJob.bits.asUInt===expected.asUInt &&
      g.io.physicalJob.bits.tag=/="hffffffff".U && logicalShape
    val physicalOfferBad=g.io.physicalJob.valid && isPrefix(g.io.physicalJob.bits.kind) && !physicalExact
    when(physicalOfferBad){poison:=true.B}
    val packets=(0 until 2).map{i=>
      val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      p.authorityKind:=Mux(convShape,UnifiedArithmeticAuthorityKindV5.OrdinaryConv.U,UnifiedArithmeticAuthorityKindV5.OrdinaryNorm.U)
      p.allocationValid:=false.B;p.allocationSequence:=0.U // deliberately NOT a MoE allocation
      p.hostEpoch:=host.epoch;p.lease.identity.transactionId:=transaction
      p.lease.identity.ownerSequence:=g.io.physicalJob.bits.tag;p.lease.identity.stage:=Mux(convShape,70.U,69.U)
      p.lease.resource:=(if(i==0)2 else 1).U
      p.lease.expectedOperations:=logical.m.pad(32)*
        (if(i==0)Mux(convShape,logical.n.pad(32)*13.U,Mux(logical.n===1024.U,5228.U(32.W),10412.U(32.W)))else Mux(convShape,logical.n.pad(32)<<1,logical.n.pad(32)))
      p
    }
    // This is distinct from provenance/identity: a held Guard job is still
    // accepted under late fault, but may NOT acquire a fresh arithmetic lease.
    val acquireClean= !currentIndependentFault && !authority.currentFault && !g.io.localFault
    val start=g.io.physicalJob.fire && isPrefix(g.io.physicalJob.bits.kind)
    acquirePending:=false.B;retirePending:=false.B
    when(start){
      // Even rejected provenance cannot erase an ACTUALLY accepted Kernel job.
      // Retain its physical ownership and poison: no new memory effect or
      // arithmetic lease is allowed, and recovery may require joint reset.
      physical:=g.io.physicalJob.bits.tag;waiting:=false.B;owned:=true.B;awaitPrepare:=false.B;leaseEventSubmitted:=false.B
      when(!physicalExact || poison || !acquireClean){poison:=true.B}
      .elsewhen(prepShape){awaitPrepare:=true.B}
      .otherwise{acquirePending:=true.B;leaseEventSubmitted:=true.B;for(i<-0 until 2){leases(i):=packets(i)}}
    }
    // RawPrep must first obtain true Guard-owned DDR responses. Its prepare
    // event is the child retained job plus counts derived from cached A_log;
    // no Host expected-count hint or manufactured allocation is accepted.
    val prep=k.io.runtimePrepPrepare.get
    val retainedPhysical=WireDefault(logical);retainedPhysical.tag:=physical
    val expectedPrep=GdnRuntimeRawPrepJobV7.fromOwner(retainedPhysical)
    val prepBase=Mux(expectedPrep.reductionPolicy===1.U,908.U(32.W),910.U(32.W))
    val exactScalar=(logical.m.pad(64)*(logical.n.pad(64)*prepBase+prep.bits.nonnegativeALog.pad(64)))(31,0)
    val exactFormat=(logical.m.pad(32)*logical.n.pad(32))(31,0)
    val prepareExact=owned && awaitPrepare && prepShape && !contextChanged && !leaseEventSubmitted &&
      prep.bits.accepted.asUInt===expectedPrep.asUInt && prep.bits.nonnegativeALog<=logical.n &&
      prep.bits.acknowledgedALogReads===(logical.n>>4) &&
      prep.bits.scalarOperations===exactScalar && prep.bits.formatOperations===exactFormat &&
      exactScalar>0.U && exactScalar<=3731456.U && exactFormat>0.U && exactFormat<=4096.U
    val prepareBad=prep.valid && !prepareExact
    when(prepareBad){poison:=true.B}
    // Identity-valid held events may finish transport under a late independent
    // fault, but they do NOT receive new arithmetic authority in that case.
    prep.ready:=prepareExact && !acquirePending && !retirePending &&
      slots.map(i=> !a.io.status(i).active && !a.io.status(i).retiring).reduce(_&&_)
    val prepPackets=(0 until 2).map{i=>
      val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      p.authorityKind:=UnifiedArithmeticAuthorityKindV5.OrdinaryRawPrep.U
      p.allocationValid:=false.B;p.allocationSequence:=0.U;p.hostEpoch:=host.epoch
      p.lease.identity.transactionId:=transaction;p.lease.identity.ownerSequence:=physical
      p.lease.identity.stage:=71.U;p.lease.resource:=(if(i==0)2 else 1).U
      p.lease.expectedOperations:=(if(i==0)prep.bits.scalarOperations else prep.bits.formatOperations)
      p
    }
    when(prep.fire){
      awaitPrepare:=false.B
      when(poison || !acquireClean){poison:=true.B}
        .otherwise{acquirePending:=true.B;leaseEventSubmitted:=true.B;for(i<-0 until 2){leases(i):=prepPackets(i)}}
    }
    val terminalExact=g.io.physicalDone.bits.tag===physical && !contextChanged
    when(owned && g.io.physicalDone.valid && !terminalExact){poison:=true.B}
    when(owned && g.io.physicalDone.fire){
      when(!terminalExact){poison:=true.B}
      .otherwise{
        when(prepShape && g.io.physicalDone.bits.status===Status.Ok.U && !leaseEventSubmitted){poison:=true.B}
        owned:=false.B;awaitPrepare:=false.B;retirePending:=leaseEventSubmitted;leaseEventSubmitted:=false.B
        retireStatus:=g.io.physicalDone.bits.status
      }
    }
    // Observe the actual RawPrep child terminal, not the generic owner result
    // with its accepted payload discarded. Same-cycle physicalDone.fire binds
    // it to the retained real Guard owner P and accepted host transaction.
    // Fault capture is registered ONLY: no event -> localFault -> ready loop.
    val prepEvent=k.io.runtimePrepDoneFire.get
    val prepEventExact=owned && prepShape && !contextChanged &&
      g.io.physicalDone.fire && terminalExact &&
      prepEvent.bits.tag===physical && prepEvent.bits.accepted.asUInt===expectedPrep.asUInt &&
      g.io.physicalDone.bits.tag===prepEvent.bits.tag &&
      g.io.physicalDone.bits.status===prepEvent.bits.status &&
      g.io.physicalDone.bits.writeBytes===prepEvent.bits.writeBytes &&
      g.io.physicalDone.bits.cycles===prepEvent.bits.cycles
    val prepEventSuccess=prepEventExact && leaseEventSubmitted && !awaitPrepare &&
      prepEvent.bits.status===Status.Ok.U && prepEvent.bits.outputCommitted &&
      prepEvent.bits.writeBytes===logical.writeBytes &&
      prepEvent.bits.writeBytes===(expectedPrep.tokens.pad(64)*expectedPrep.layout.rowBytes.pad(64))(63,0)
    val receiptCurrent=authority.accepted && authority.transaction===prepReceipt.producer.transactionId &&
      authority.launch.epoch===prepReceipt.producer.hostEpoch && authority.launch.asUInt===host.asUInt
    val receiptFault=poison || currentIndependentFault || authority.currentFault || g.io.localFault || a.io.resetRequired
    when(prepEvent.valid){
      when(!prepEventExact || (prepEvent.bits.status===Status.Ok.U && !prepEventSuccess) || prepReceiptValid){
        poison:=true.B;prepReceiptValid:=false.B
      }.elsewhen(prepEventSuccess && !receiptFault){
        prepReceipt.producer.transactionId:=transaction
        prepReceipt.producer.hostEpoch:=host.epoch
        prepReceipt.producer.ownerSequence:=physical
        prepReceipt.result:=prepEvent.bits
        prepReceiptValid:=true.B
      }
    }
    // A fault or changed lifetime can never leave a stale eligible snapshot.
    // This is metadata invalidation, not cancellation of a held service offer.
    when(receiptFault || (prepReceiptValid && !receiptCurrent)){prepReceiptValid:=false.B}
    // One registered stage prevents actual-fire rejection feedback cycles.
    // Both events preserve their original order; status is from its real fire.
    for(i<-0 until 2){
      if(i==0){
        out.scalarAcquire.valid:=acquirePending;out.scalarAcquire.bits:=leases(i)
        out.scalarRetire.valid:=retirePending;out.scalarRetire.bits.lease:=leases(i);out.scalarRetire.bits.status:=retireStatus
      }else{
        a.io.acquire(slots(i)).valid:=acquirePending;a.io.acquire(slots(i)).bits:=leases(i)
        a.io.retire(slots(i)).valid:=retirePending;a.io.retire(slots(i)).bits.lease:=leases(i)
        a.io.retire(slots(i)).bits.status:=retireStatus
      }
    }
    // A leaf-local offer is not yet an exposed shared-service obligation.
    // Two bits preserve only previously published requests through late fault;
    // CURRENT independent fault blocks first publication without cancelling
    // a held request. Adapter's own current fault still blocks fresh captures
    // internally; feeding it back into these valid gates would form a cycle.
    val firstFault=currentIndependentFault || poison || contextChanged || physicalOfferBad || prepareBad || g.io.localFault
    val scalar=k.io.runtimeRms.get.scalar
    val scalarPublish=HeldDecoupledOffer(scalar.request.valid,scalarPort.request.ready,firstFault)
    scalarPort.request.valid:=scalarPublish.valid;scalarPort.request.bits:=scalar.request.bits
    scalar.request.ready:=scalarPort.request.ready && scalarPublish.valid
    scalar.result<>scalarPort.result
    val format=k.io.runtimeRms.get.formatRequest
    val formatPublish=HeldDecoupledOffer(format.valid,a.io.formatRequest(3).ready,firstFault)
    a.io.formatRequest(3).valid:=formatPublish.valid;a.io.formatRequest(3).bits:=format.bits
    format.ready:=a.io.formatRequest(3).ready && formatPublish.valid
    k.io.runtimeRms.get.formatResult<>a.io.formatResult(3)
    out.owned:=owned;out.host:=host;out.transactionId:=transaction
    out.job:=logical;out.job.tag:=physical
    out.prepReceipt.bits:=prepReceipt
    // Producer success does not retire slot8/9 leases. Wait for their ACTUAL
    // existing retirement/drain before a later owner may borrow the resources.
    out.prepReceipt.valid:=prepReceiptValid && receiptCurrent && !receiptFault && !prepReplacement && !busy &&
      slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_) && k.io.runtimeRms.get.resourcesDrained
    out.localFault:=poison || contextChanged || physicalOfferBad || prepareBad
    out.eventsPending:=acquirePending || retirePending || awaitPrepare || prep.valid || scalarPublish.held || formatPublish.held
    out.resourcesDrained:= !busy && !scalarPublish.held && !formatPublish.held && slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_) &&
      k.io.runtimeRms.get.resourcesDrained
    out
  }
}
