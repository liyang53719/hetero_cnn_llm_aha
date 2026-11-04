// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Actual Top control/data integration. One Guard, one shared Scalar8, one
  * existing bank's Vector10, and five clients on the one memory hub. None of
  * these wires creates a second arithmetic service or grants Host authority. */
object HostRuntimeChunkWiringV9 {
  class View extends Bundle {
    val localFault=Bool();val eventsPending=Bool();val resourcesDrained=Bool()
    val stagedReceipt=Valid(new GdnRuntimeChunkStagedReceiptV10)
  }
  def connect(a:UnifiedMoeSharedArithmeticAdapterV5,g:HostRuntimeOwnerGuardV5,
      authority:HostRuntimeAuthoritySnapshotV4,k:QwenOwnerKernel,
      prefix:HostRuntimePrefixLeaseWiringV8.View,prefixScalar:UnifiedScalarClientV2,
      hub:SharedMemoryArbiter,independentFault:Bool,enableChunk32:Boolean=false):View={
    val out=Wire(new View);val p=k.io.runtimeChunk.get
    val logical=Reg(new QwenOwnerJob);val host=Reg(new HostCommandLaunchV4)
    val transaction=Reg(UInt(64.W));val physical=Reg(UInt(32.W))
    val waiting=RegInit(false.B);val owned=RegInit(false.B);val poison=RegInit(false.B)
    val stagedValid=RegInit(false.B);val staged=Reg(new GdnRuntimeChunkStagedReceiptV10)
    val receipt=Reg(new GdnRuntimeRawPrepReceiptV8)
    val receiptOffer=RegInit(false.B);val receiptConsumed=RegInit(false.B)
    val everConsumed=RegInit(false.B);val lastProducer=Reg(UInt(32.W));val lastConsumer=Reg(UInt(32.W))
    val lastTransaction=Reg(UInt(64.W))
    val acquirePending=RegInit(false.B);val retirePending=RegInit(false.B)
    val leaseSubmitted=RegInit(false.B);val leases=Reg(Vec(if(enableChunk32)3 else 2,new UnifiedMoeArithmeticLeaseV5))
    val retireStatus=Reg(UInt(8.W))
    val scalarPending=RegInit(false.B);val scalarOwner=Reg(UInt(2.W)) // prefix0, load1, derived2
    val vectorPending=RegInit(false.B);val vectorOwner=Reg(UInt(1.W))
    val memoryPending=RegInit(VecInit(Seq.fill(5)(false.B)))
    val memoryTags=Reg(Vec(5,UInt(64.W)))
    val route=Reg(new GdnRuntimeChunkRouteContext);val routeValid=RegInit(false.B)
    val slots=if(enableChunk32)Seq(8,10,12)else Seq(8,10)
    val chunk32Pending=RegInit(false.B)
    val eventBusy=waiting || owned || receiptOffer || acquirePending || retirePending || leaseSubmitted
    val lifetimeChanged=(waiting || owned || receiptOffer || leaseSubmitted) &&
      (!authority.accepted || authority.transaction=/=transaction || authority.launch.asUInt=/=host.asUInt)
    val currentFault=independentFault || g.io.localFault || poison || lifetimeChanged
    // Register the entire reflected fault cone: adapter rawValid/shape/count
    // checks depend on our offer. Direct feedback here creates a comb loop.
    // Explicit cancel handles offers first exposed during this one-cycle delay.
    p.abort32.abort:=RegNext(enableChunk32.B &&
      (currentFault || authority.currentFault || a.io.resetRequired || p.resetRequired),false.B)
    p.abort32.memoryCancelled:=false.B;p.abort32.vectorCancelled:=false.B
    when(lifetimeChanged || ((waiting || owned) && (independentFault || authority.currentFault))){poison:=true.B}
    def chunk(j:QwenOwnerJob):Bool=HostRuntimeChunkJobV9.selected(j)
    val logicalStart=g.io.job.fire && chunk(g.io.job.bits)
    val saved=prefix.prepReceipt.bits
    val producerFresh= !everConsumed || (saved.producer.transactionId>=lastTransaction &&
      saved.producer.ownerSequence>lastProducer && saved.producer.ownerSequence>lastConsumer)
    when(logicalStart){
      stagedValid:=false.B
      // Full actual Guard acceptance, never caller-provided valid/equality alone.
      logical:=g.io.job.bits;host:=authority.launch;transaction:=authority.transaction
      receipt:=saved;waiting:=true.B;receiptConsumed:=false.B;routeValid:=false.B
      when(eventBusy || g.io.phaseReserved || !authority.accepted || !authority.ownerValidated ||
        authority.ownerJob.asUInt=/=g.io.job.bits.asUInt || authority.currentFault || independentFault ||
        !prefix.prepReceipt.valid || !producerFresh ||
        saved.producer.transactionId=/=authority.transaction || saved.producer.hostEpoch=/=authority.launch.epoch ||
        saved.result.accepted.output=/=g.io.job.bits.a || saved.result.accepted.tokens=/=g.io.job.bits.m){poison:=true.B}
    }
    val binding=Wire(new GdnRuntimeChunkPrepBindingV8)
    binding.transactionId:=transaction;binding.hostEpoch:=host.epoch
    binding.producerOwner:=receipt.producer.ownerSequence;binding.source:=receipt.result.accepted
    p.prepBinding:=binding
    val expected=WireDefault(logical);expected.tag:=g.io.physicalJob.bits.tag
    val shape=chunk(logical) && !logical.activationBf16 && !logical.weightBf16 && logical.outputBf16 &&
      (logical.m===16.U || logical.m===128.U) && logical.k===128.U &&
      Mux(host.profileId===1.U,logical.n===16.U,host.profileId===3.U && logical.n===32.U) &&
      logical.cold && logical.expectedGeneration===0.U && logical.currentGeneration===0.U &&
      logical.writeBytes===(logical.m.pad(64)*logical.n.pad(64)*256.U+logical.n.pad(64)*65536.U)(63,0)
    val physicalExact=waiting && !owned && !g.io.phaseReserved && !lifetimeChanged && shape &&
      g.io.acceptedTransaction===transaction && g.io.physicalJob.bits.asUInt===expected.asUInt &&
      g.io.physicalJob.bits.tag=/="hffffffff".U && receipt.producer.ownerSequence=/="hffffffff".U &&
      g.io.physicalJob.bits.tag>receipt.producer.ownerSequence &&
      (!everConsumed || g.io.physicalJob.bits.tag>lastConsumer)
    val start=g.io.physicalJob.fire && chunk(g.io.physicalJob.bits)
    when(g.io.physicalJob.valid && chunk(g.io.physicalJob.bits) && !physicalExact){poison:=true.B}
    when(start){
      physical:=g.io.physicalJob.bits.tag;waiting:=false.B;owned:=true.B
      when(!physicalExact || currentFault || authority.currentFault || !p.jobFire){poison:=true.B}
        .otherwise{receiptOffer:=true.B}
    }
    // Once published, this immutable real P receipt survives late fault and
    // backpressure. There is exactly one offer per accepted C, then no replay.
    p.prepDone.valid:=receiptOffer;p.prepDone.bits:=receipt
    acquirePending:=false.B;retirePending:=false.B
    val acceptedOwner=WireDefault(logical);acceptedOwner.tag:=physical
    val expectedJob=HostRuntimeChunkJobV9.fromOwner(acceptedOwner,binding)
    val chunkCount=Mux(logical.m===128.U,2.U(2.W),1.U(2.W))
    val exactScalar=logical.n.pad(32)*chunkCount*(Mux(host.profileId===3.U,832.U(32.W),64.U(32.W))+2209.U)
    val exactVector=if(enableChunk32) logical.n.pad(32)*chunkCount*4704.U
      else logical.n.pad(32)*chunkCount*663648.U+8.U*logical.m.pad(32)*logical.n.pad(32)
    val exactExecute32=logical.n.pad(32)*chunkCount*329472.U+4.U*logical.m.pad(32)*logical.n.pad(32)
    val packets=slots.indices.map{i=>
      val v=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      v.authorityKind:=(if(i==2)UnifiedArithmeticAuthorityKindV5.OrdinaryChunk32 else UnifiedArithmeticAuthorityKindV5.OrdinaryChunk).U
      v.allocationValid:=false.B;v.allocationSequence:=0.U;v.hostEpoch:=host.epoch
      v.lease.identity.transactionId:=transaction;v.lease.identity.ownerSequence:=physical;v.lease.identity.stage:=(if(i==2)79 else 72).U
      v.lease.resource:=(if(i==0)2 else 1).U
      v.lease.expectedOperations:=(if(i==0)exactScalar else if(i==1)exactVector else exactExecute32)
      v
    }
    when(p.jobFire =/= start){poison:=true.B}
    when(p.prepDone.fire){
      receiptOffer:=false.B
      when(!owned || receiptConsumed || leaseSubmitted || currentFault || authority.currentFault ||
        receipt.result.status=/=Status.Ok.U || !receipt.result.outputCommitted ||
        receipt.result.tag=/=receipt.producer.ownerSequence || receipt.result.accepted.tag=/=receipt.producer.ownerSequence ||
        receipt.result.accepted.output=/=logical.a || receipt.result.writeBytes=/=(logical.m.pad(64)*logical.n.pad(64)*1600.U)(63,0)){
        poison:=true.B
      }.otherwise{
        receiptConsumed:=true.B;everConsumed:=true.B;lastProducer:=receipt.producer.ownerSequence
        lastConsumer:=physical;lastTransaction:=transaction;acquirePending:=true.B;leaseSubmitted:=true.B
        for(i<-slots.indices){leases(i):=packets(i)}
      }
    }
    // Actual accepted leaf context is checked, not used to guess return owner.
    when(p.routeAccepted){
      when(!owned || !receiptConsumed || p.route.context.asUInt=/=expectedJob.context.asUInt || p.route.kind>4.U){poison:=true.B}
      route:=p.route;routeValid:=true.B
    }
    val liveRoute=Mux(p.routeAccepted,p.route,route)
    val liveRouteValid=routeValid || p.routeAccepted
    val routeExact=owned && receiptConsumed && liveRouteValid && liveRoute.context.asUInt===expectedJob.context.asUInt
    // Slot8 is shared with ordinary prefix; slot9 remains prefix-only.
    a.io.acquire(8).valid:=prefix.scalarAcquire.valid || acquirePending
    a.io.acquire(8).bits:=Mux(acquirePending,leases(0),prefix.scalarAcquire.bits)
    a.io.retire(8).valid:=prefix.scalarRetire.valid || retirePending
    a.io.retire(8).bits:=prefix.scalarRetire.bits
    when(retirePending){a.io.retire(8).bits.lease:=leases(0);a.io.retire(8).bits.status:=retireStatus}
    a.io.acquire(10).valid:=acquirePending;a.io.acquire(10).bits:=leases(1)
    a.io.retire(10).valid:=retirePending;a.io.retire(10).bits.lease:=leases(1);a.io.retire(10).bits.status:=retireStatus
    a.io.acquire(12).valid:=false.B;a.io.acquire(12).bits:=0.U.asTypeOf(a.io.acquire(12).bits)
    a.io.retire(12).valid:=false.B;a.io.retire(12).bits:=0.U.asTypeOf(a.io.retire(12).bits)
    if(enableChunk32){
      a.io.acquire(12).valid:=acquirePending;a.io.acquire(12).bits:=leases(2)
      a.io.retire(12).valid:=retirePending;a.io.retire(12).bits.lease:=leases(2);a.io.retire(12).bits.status:=retireStatus
    }
    when((acquirePending && prefix.scalarAcquire.valid) || (retirePending && prefix.scalarRetire.valid)){poison:=true.B}
    val leaseReady=leaseSubmitted && !acquirePending && slots.indices.map(i=>a.io.status(slots(i)).active &&
      !a.io.status(slots(i)).retiring && a.io.status(slots(i)).lease.asUInt===leases(i).asUInt).reduce(_&&_)
    // Serialize the two raw clients before the one existing tagged adapter.
    // Captured request.fire owner, never live valid or live route, steers return.
    val scalarChoiceHeld=RegInit(false.B);val scalarHeldChoice=Reg(UInt(1.W))
    val scalarChoice=Mux(scalarChoiceHeld,scalarHeldChoice,Mux(p.scalar(0).request.valid,0.U(1.W),1.U(1.W)))
    val scalarRequest=Mux(scalarChoice===0.U,p.scalar(0).request.bits,p.scalar(1).request.bits)
    val scalarIntent=p.scalar.map(_.request.valid).reduce(_||_)
    val scalarLegal=routeExact && Mux(scalarChoice===0.U,liveRoute.kind===1.U,liveRoute.kind===2.U)
    val scalarOffer=HeldDecoupledOffer(owned && scalarIntent && !scalarPending,
      a.io.scalar(3).request.ready, currentFault || !leaseReady || !scalarLegal)
    when(scalarOffer.valid){scalarChoiceHeld:= !a.io.scalar(3).request.ready;scalarHeldChoice:=scalarChoice}
    a.io.scalar(3).request.valid:=Mux(owned,scalarOffer.valid,prefixScalar.request.valid)
    a.io.scalar(3).request.bits:=Mux(owned,scalarRequest,prefixScalar.request.bits)
    prefixScalar.request.ready:= !owned && a.io.scalar(3).request.ready
    for(i<-0 until 2){
      p.scalar(i).request.ready:=owned && scalarOffer.valid && scalarChoice===i.U && a.io.scalar(3).request.ready
      p.scalar(i).result.valid:=a.io.scalar(3).result.valid && scalarPending && scalarOwner===(i+1).U
      p.scalar(i).result.bits:=a.io.scalar(3).result.bits
    }
    prefixScalar.result.valid:=a.io.scalar(3).result.valid && scalarPending && scalarOwner===0.U
    prefixScalar.result.bits:=a.io.scalar(3).result.bits
    a.io.scalar(3).result.ready:=scalarPending && MuxLookup(scalarOwner,false.B)(Seq(
      0.U->prefixScalar.result.ready,1.U->p.scalar(0).result.ready,2.U->p.scalar(1).result.ready))
    when(a.io.scalar(3).result.fire){scalarPending:=false.B}
    when(a.io.scalar(3).request.fire){
      when(scalarPending){poison:=true.B};scalarPending:=true.B
      scalarOwner:=Mux(owned,scalarChoice+&1.U,0.U)
    }
    when(a.io.scalar(3).result.valid && !scalarPending){poison:=true.B}
    val vectorChoiceHeld=RegInit(false.B);val vectorHeldChoice=Reg(UInt(1.W))
    val vectorChoice=Mux(vectorChoiceHeld,vectorHeldChoice,Mux(p.vector(0).request.valid,0.U(1.W),1.U(1.W)))
    val vectorIntent=p.vector.map(_.request.valid).reduce(_||_)
    val vectorLegal=routeExact && Mux(vectorChoice===0.U,liveRoute.kind===2.U,!enableChunk32.B && liveRoute.kind===4.U)
    val vectorOffer=HeldDecoupledOffer(owned && vectorIntent && !vectorPending,
      a.io.ordinaryVectorRequest.ready,currentFault || !leaseReady || !vectorLegal)
    when(vectorOffer.valid){vectorChoiceHeld:= !a.io.ordinaryVectorRequest.ready;vectorHeldChoice:=vectorChoice}
    a.io.ordinaryVectorRequest.valid:=vectorOffer.valid
    a.io.ordinaryVectorRequest.bits:=Mux(vectorChoice===0.U,p.vector(0).request.bits,p.vector(1).request.bits)
    for(i<-0 until 2){
      p.vector(i).request.ready:=vectorOffer.valid && vectorChoice===i.U && a.io.ordinaryVectorRequest.ready
      p.vector(i).result.valid:=a.io.ordinaryVectorResult.valid && vectorPending && vectorOwner===i.U
      p.vector(i).result.bits:=a.io.ordinaryVectorResult.bits
    }
    a.io.ordinaryVectorResult.ready:=vectorPending && Mux(vectorOwner===0.U,p.vector(0).result.ready,p.vector(1).result.ready)
    when(a.io.ordinaryVectorResult.fire){vectorPending:=false.B}
    when(a.io.ordinaryVectorRequest.fire){vectorPending:=true.B;vectorOwner:=vectorChoice}
    when(a.io.ordinaryVectorResult.valid && !vectorPending){poison:=true.B}
    when((scalarIntent && (!owned || !scalarLegal)) || (vectorIntent && !vectorLegal) ||
      (owned && (prefixScalar.request.valid || (scalarPending && scalarOwner===0.U))) ||
      PopCount(VecInit(p.scalar.map(_.request.valid)))>1.U || PopCount(VecInit(p.vector.map(_.request.valid)))>1.U){poison:=true.B}
    val chunk32Legal=enableChunk32.B && routeExact && liveRoute.kind===4.U
    val vector32Cancelled=WireDefault(false.B)
    val chunk32Offer=if(enableChunk32)CancellableHeldDecoupledOfferV1(
      owned && p.vector32.request.valid && !chunk32Pending,a.io.chunkVector32Request.ready,
      currentFault || !leaseReady || !chunk32Legal || p.abort32.vectorCancel,vector32Cancelled)
    else HeldDecoupledOffer(owned && p.vector32.request.valid && !chunk32Pending,
      a.io.chunkVector32Request.ready,currentFault || !leaseReady || !chunk32Legal)
    if(enableChunk32){
      a.io.chunk32Cancel.get:=p.abort32.vectorCancel && chunk32Offer.valid
      vector32Cancelled:=p.abort32.vectorCancel && !chunk32Pending &&
        ((!chunk32Offer.valid && !chunk32Offer.held) || a.io.chunk32Cancelled.get)
      p.abort32.vectorCancelled:=vector32Cancelled
      assert(!(vector32Cancelled && p.vector32.request.fire))
    }
    a.io.chunkVector32Request.valid:=chunk32Offer.valid
    a.io.chunkVector32Request.bits:=p.vector32.request.bits
    p.vector32.request.ready:=chunk32Offer.valid && a.io.chunkVector32Request.ready
    p.vector32.result.valid:=a.io.chunkVector32Result.valid && chunk32Pending
    p.vector32.result.bits:=a.io.chunkVector32Result.bits
    a.io.chunkVector32Result.ready:=chunk32Pending && p.vector32.result.ready
    when(a.io.chunkVector32Result.fire){chunk32Pending:=false.B}
    when(a.io.chunkVector32Request.fire){
      when(chunk32Pending){poison:=true.B};chunk32Pending:=true.B
    }
    when((a.io.chunkVector32Result.valid && !chunk32Pending) ||
      (p.vector32.request.valid && !chunk32Legal) ||
      (p.vector32.request.valid && vectorIntent)){poison:=true.B}
    val memoryHolds=Wire(Vec(5,Bool()))
    for(i<-0 until 5){
      val request=p.memory(i).request;val response=p.memory(i).response
      val address=request.bits.address.pad(80);val end=address+64.U
      def within(base:UInt,bytes:UInt):Bool=address>=base.pad(80) && end<=base.pad(80)+bytes.pad(80)
      val rights=host.regions.map(r=>address>=r.base.pad(80) && end<=r.limit.pad(80) &&
        Mux(request.bits.write,r.write,r.read)).reduce(_||_)
      val scratchBytes=logical.n.pad(80)*Mux(logical.m===128.U,1679360.U,872448.U)
      val scratch=within(logical.c,scratchBytes)
      val output=within(logical.dst,logical.m.pad(80)*logical.n.pad(80)*256.U)
      val stateOut=within(logical.gdnStateOut,logical.n.pad(80)*65536.U)
      val prepared=within(logical.a,logical.m.pad(80)*logical.n.pad(80)*1600.U)
      val stateIn= !logical.cold && within(logical.b,logical.n.pad(80)*65536.U)
      val legal=routeExact && liveRoute.kind===i.U && request.bits.tag(63,32)===physical &&
        request.bits.address(5,0)===0.U && end<=(BigInt(1)<<56).U && rights &&
        Mux(request.bits.write,(scratch || output || stateOut) && request.bits.mask.andR,
          (scratch || prepared || stateIn) && request.bits.mask===0.U)
      val memoryCancelled=WireDefault(false.B)
      val offer=if(enableChunk32 && i==GdnRuntimeChunkClient.Execute)
        CancellableHeldDecoupledOfferV1(request.valid,hub.io.requests(i+12).ready,
          currentFault || !legal || p.abort32.memoryCancel,memoryCancelled)
      else HeldDecoupledOffer(request.valid,hub.io.requests(i+12).ready,currentFault || !legal)
      if(enableChunk32 && i==GdnRuntimeChunkClient.Execute){
        // Execute ordinal4 + physical client offset12 = actual hub client16.
        hub.io.cancel.get:=p.abort32.memoryCancel && offer.valid
        memoryCancelled:=p.abort32.memoryCancel && !memoryPending(i) &&
          ((!offer.valid && !offer.held) || hub.io.cancelled.get)
        p.abort32.memoryCancelled:=memoryCancelled
        assert(!(memoryCancelled && request.fire))
      }
      memoryHolds(i):=offer.held
      hub.io.requests(i+12).valid:=offer.valid;hub.io.requests(i+12).bits:=request.bits
      request.ready:=offer.valid && hub.io.requests(i+12).ready
      val r=hub.io.responses(i+12)
      val exact=memoryPending(i) && r.bits.tag===memoryTags(i)
      response.valid:=r.valid && exact;response.bits:=r.bits;r.ready:=response.ready && exact
      when(r.valid && !exact){poison:=true.B}
      when(r.fire){memoryPending(i):=false.B}
      when(request.fire){
        when(memoryPending(i)){poison:=true.B};memoryPending(i):=true.B;memoryTags(i):=request.bits.tag
      }
      when(request.valid && !legal){poison:=true.B}
    }
    // Quiescence excludes active owner/lease reservations: otherwise both
    // waitPrep and final drain would deadlock waiting for their own retirement.
    val transportQuiet= !memoryPending.asUInt.orR && !memoryHolds.asUInt.orR &&
      !p.memory.map(x=>x.request.valid || x.response.valid).reduce(_||_) &&
      !p.scalar.map(x=>x.request.valid || x.result.valid).reduce(_||_) &&
      !p.vector.map(x=>x.request.valid || x.result.valid).reduce(_||_) &&
      !scalarPending && !vectorPending && !scalarOffer.held && !vectorOffer.held &&
      !chunk32Pending && !chunk32Offer.held && !p.vector32.request.valid && !p.vector32.result.valid &&
      slots.map(i=>a.io.status(i).resourcesDrained).reduce(_&&_)
    p.fabricDrained:=transportQuiet && !acquirePending && !retirePending
    // Break reflected Collection.resetRequired -> Top.phaseFault -> Collection
    // combinational loops. First shared publication uses currentFault above.
    p.fabricFault:=RegNext(independentFault || authority.currentFault || poison || p.resetRequired,false.B)
    when(p.doneFire.valid){
      val r=p.doneFire.bits
      val exact=owned && g.io.physicalDone.fire && g.io.physicalDone.bits.tag===physical &&
        g.io.physicalDone.bits.status===r.status &&
        g.io.physicalDone.bits.writeBytes===r.outputAckBytes+r.stateAckBytes &&
        r.accepted.asUInt===expectedJob.asUInt && r.drained && transportQuiet
      val countsExact=slots.indices.map(i=>a.io.status(slots(i)).lease.asUInt===leases(i).asUInt &&
        a.io.status(slots(i)).counts.returned===leases(i).lease.expectedOperations.pad(33)).reduce(_&&_)
      val successProof=leaseSubmitted && receiptConsumed && r.stagedComplete && countsExact
      when(!exact || (r.status===Status.Ok.U && !successProof)){poison:=true.B}
      .otherwise{
        // Only the full matching real terminal may retire. A malformed return
        // leaves ownership/debt in quarantine; it cannot refund a successful lease.
        when(r.status===Status.Ok.U && !currentFault && !authority.currentFault && !a.io.resetRequired){
          staged.producer.transactionId:=transaction;staged.producer.hostEpoch:=host.epoch
          staged.producer.ownerSequence:=physical;staged.result:=r;stagedValid:=true.B
        }
        owned:=false.B;routeValid:=false.B
        retirePending:=leaseSubmitted;leaseSubmitted:=false.B;retireStatus:=r.status
      }
    }
    val stagedCurrent=authority.accepted && authority.transaction===staged.producer.transactionId &&
      authority.launch.epoch===staged.producer.hostEpoch && authority.launch.asUInt===host.asUInt
    val stagedFault=currentFault || authority.currentFault || a.io.resetRequired || p.resetRequired
    when(stagedFault || (stagedValid && !stagedCurrent)){stagedValid:=false.B}
    out.stagedReceipt.bits:=staged
    out.stagedReceipt.valid:=stagedValid && stagedCurrent && !stagedFault && !logicalStart &&
      !eventBusy && transportQuiet && slots.map(i=> !a.io.status(i).active && !a.io.status(i).retiring).reduce(_&&_)
    out.localFault:=poison || lifetimeChanged
    out.eventsPending:=waiting || receiptOffer || acquirePending || retirePending || scalarOffer.held || vectorOffer.held || chunk32Offer.held || memoryHolds.asUInt.orR
    out.resourcesDrained:= !eventBusy && transportQuiet && slots.map(i=> !a.io.status(i).active && !a.io.status(i).retiring).reduce(_&&_)
    out
  }
}
