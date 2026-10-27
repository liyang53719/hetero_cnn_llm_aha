// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private scheduler assignment. Not an externally writable host command or
  * allocator grant. Parent must originate this from accepted block dispatch
  * and the actual typed prepared-tensor allocation/producer. */
class UnifiedGdnBoundJobV3 extends Bundle {
  val block = new UnifiedBlockDispatchV1
  val job = new GdnRuntimeChunkCoordinatorJob
}
class UnifiedGdnBoundResultV3 extends Bundle {
  val transactionId = UInt(64.W)
  val profileId = UInt(3.W)
  val result = new GdnRuntimeChunkCoordinatorResult
  val resetRequired = Bool()
}

/** Private stage-family extension; the frozen V3 bundle widths do not change.
  * State copy was deliberately undefined by the earlier types-only candidate.
  * Value16 is allocated here explicitly, not inherited from Matrix stage1.
  * One Derived job:64 rows*(5 vector multiplies*8 beats +1 remaining Add)
  * +sum(row+1,row=0..63) pair Adds =2560+64+2080=4704.
  */
object UnifiedGdnRouteBindingV3 {
  val StateCopyStage = 16
  val DerivedVectorOperations = 64*(5*8+1) + (1 to 64).sum
  require(DerivedVectorOperations == 4704)
}

/** Original GDN control/data collection wired to one memory/scalar/vector
  * resource-client port each. No arithmetic primitive, Matrix, or payload SRAM
  * is instantiated. The outer common fabric must own/tag these ports; this is
  * not a replacement for its cross-client arbiter or reset isolation protocol.
  *
  * A route is formed ONLY by the collection's actual leaf job.fire observer,
  * checked against the retained whole private assignment and accepted profile.
  * Resource requests are backpressured until that route is installed. A raw
  * unknown reply quarantines debt; ordinary poison still lets an already-owned
  * legitimate leaf drain. There is no fake zero reply or watchdog completion.
  */
class UnifiedGdnRuntimeRouterV3 extends Module {
  val io = IO(new Bundle {
    val begin = Flipped(Decoupled(new UnifiedGdnBoundJobV3))
    val committed = Input(new GdnChunkCommittedState)
    val prepDone = Flipped(Decoupled(new GdnRuntimeInputPrepResult))
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalar = new UnifiedScalarClientV2
    val vectorRequest = Decoupled(new UnifiedVectorRequestV2)
    val vectorResult = Flipped(Decoupled(new UnifiedVectorResultV2))
    // Registered parent poison, never combinational feedback of this module's faultNow.
    val parentPoison = Input(Bool())
    val done = Decoupled(new UnifiedGdnBoundResultV3)
    val resetRequired = Output(Bool())
    val reserved = Output(Bool())
    val routeIdentity = Output(new UnifiedSharedOwnerIdentityV3)
    val routeValid = Output(Bool())
    val counts = Output(Vec(3,new UnifiedSharedOperationCountsV3)) // DDR/scalar/vector
    val resourcesDrained = Output(Bool())
  })
  val collection = Module(new GdnRuntimeChunkLeafCollection)
  val idle :: running :: holding :: locked :: Nil = Enum(4)
  val state=RegInit(idle)
  val accepted=Reg(new UnifiedGdnBoundJobV3)
  val terminal=Reg(new UnifiedGdnBoundResultV3)
  val poison=RegInit(false.B)
  val quarantine=RegInit(false.B)
  val route=Reg(new GdnRuntimeChunkRouteContext)
  val routeValid=RegInit(false.B)
  val identity=Reg(new UnifiedSharedOwnerIdentityV3)
  // This local owner sequence never resets between block jobs. It is NOT the
  // global DDR transport epoch; the one parent arbiter allocates that epoch.
  val nextOwner=RegInit(0.U(32.W))
  val vectorExpected=Reg(UInt(32.W))
  val counts=RegInit(VecInit(Seq.fill(3)(0.U.asTypeOf(new UnifiedSharedOperationCountsV3))))
  val faultNow=WireDefault(false.B)
  val unknownNow=WireDefault(false.B)
  val mState=RegInit(0.U(2.W));val sState=RegInit(0.U(2.W));val vState=RegInit(0.U(2.W))
  // states0 idle,1 captured physical offer,2 issued awaiting reply,3 held reply.
  val rawUnknownMemory=io.response.valid && (mState=/=2.U)
  val rawUnknownScalar=io.scalar.result.valid && (sState=/=2.U)
  val rawUnknownVector=io.vectorResult.valid && (vState=/=2.U)
  unknownNow:=rawUnknownMemory || rawUnknownScalar || rawUnknownVector
  val noTransportDebt=mState===0.U && sState===0.U && vState===0.U
  val noClientOffer= !collection.io.memory.map(_.request.valid).reduce(_||_) &&
    !collection.io.scalar.map(_.request.valid).reduce(_||_) &&
    !collection.io.vector.map(_.request.valid).reduce(_||_)
  val countsLegal=counts.map(c=>UnifiedSharedOperationBoundsV3.ordered(c) && !c.accepted(32) &&
    !c.issued(32) && !c.returned(32)).reduce(_&&_)
  val countsEqual=counts.map(UnifiedSharedOperationBoundsV3.countsRetired).reduce(_&&_)
  val noRawReply= !io.response.valid && !io.scalar.result.valid && !io.vectorResult.valid
  val drained=noTransportDebt && noClientOffer && noRawReply && countsLegal && countsEqual && !quarantine && !unknownNow
  io.resourcesDrained:=drained
  io.routeIdentity:=identity;io.routeValid:=routeValid && state===running
  io.counts:=counts
  io.reserved:=state=/=idle || io.begin.valid
  io.resetRequired:=poison || quarantine || faultNow || unknownNow || collection.io.resetRequired

  val b=io.begin.bits
  val (decoded,known)=UnifiedRuntimeProfile.decode(b.block.launch.profileId)
  val beginLegal=known && decoded.asUInt===b.block.profile.asUInt && decoded.mixer===1.U &&
    (b.job.context.tokens===16.U || b.job.context.tokens===128.U) &&
    b.job.context.tokens===b.block.launch.tokens && b.job.layout.valueHeads===decoded.gdnValueHeads &&
    b.job.layout.keyHeads===decoded.gdnKeyHeads && b.job.context.tag===b.block.launch.tag &&
    b.job.context.cold===b.block.launch.cold && b.job.context.expectedGeneration===b.block.launch.expectedGeneration
  // An already-offered private job cannot be retracted by a late fault.
  // The upstream begin producer holds its bits until this same job handshake.
  // Fault before a new offer prevents it; fault after a held offer can require
  // isolation/reset when the downstream coordinator can no longer accept it.
  val beginFault=poison || quarantine || faultNow || unknownNow || collection.io.resetRequired
  val beginOffer=HeldDecoupledOffer(io.begin.valid && state===idle && beginLegal,
    collection.io.job.ready,beginFault)
  collection.io.job.bits:=b.job
  collection.io.job.valid:=beginOffer.valid
  io.begin.ready:=state===idle && Mux(beginLegal,
    beginOffer.valid && collection.io.job.ready,!beginFault)
  collection.io.committed:=io.committed
  collection.io.prepDone<>io.prepDone
  collection.io.fabricFault:=poison || quarantine || faultNow || unknownNow || io.parentPoison
  collection.io.fabricFaultStatus:=Status.Protocol.U
  collection.io.fabricDrained:=drained
  collection.io.done.ready:=state===running && drained
  io.done.valid:=state===holding;io.done.bits:=terminal

  val r=collection.io.route
  val routeShape=(r.kind===0.U && (r.phase===0.U || r.phase===18.U)) ||
    (r.kind===1.U && r.phase===1.U) || (r.kind===2.U && r.phase===2.U) ||
    (r.kind===3.U && r.phase===3.U) || (r.kind===4.U && r.phase>=5.U && r.phase<=17.U)
  val oldRouteComplete= !routeValid || (countsLegal && countsEqual && counts(2).returned===vectorExpected.pad(33))
  val routeBad=state=/=running || collection.io.routeMetadataFault || !routeShape ||
    r.context.asUInt=/=accepted.job.context.asUInt || r.head>=accepted.job.layout.valueHeads ||
    r.chunk>=Mux(accepted.job.context.tokens===128.U,2.U,1.U) || !noTransportDebt ||
    !noRawReply || !oldRouteComplete || !UnifiedSharedOperationBoundsV3.nextOwnerAvailable(nextOwner)
  when(collection.io.routeAccepted){
    // Every pulse is consumed as either a new exact route or a sticky fault;
    // an invalid pulse cannot replace an existing outstanding owner identity.
    when(routeBad || poison || quarantine || unknownNow || io.parentPoison ||
      collection.io.leafResetRequired.asUInt.orR){faultNow:=true.B}
      .otherwise {
        route:=r;routeValid:=true.B
        identity.transactionId:=accepted.block.transactionId;identity.ownerSequence:=nextOwner
        // State-copy family is explicit here, not the old Matrix stage1.
        identity.stage:=MuxLookup(r.kind,0.U(8.W))(Seq(0.U->UnifiedGdnRouteBindingV3.StateCopyStage.U,1.U->UnifiedSharedOperationBoundsV3.GdnLoad.U,2.U->UnifiedSharedOperationBoundsV3.GdnDerived.U,3.U->UnifiedSharedOperationBoundsV3.GdnTranspose.U,4.U->UnifiedSharedOperationBoundsV3.GdnExecute.U))
        identity.phase:=r.phase;identity.head:=r.head;identity.chunk:=r.chunk
        identity.token:=0.U;identity.tileOrdinal:=0.U
        nextOwner:=nextOwner+1.U
        val (_,n)=UnifiedSharedOperationBoundsV3.gdnPhaseVectorCount(r.phase)
        vectorExpected:=Mux(r.kind===2.U,UnifiedGdnRouteBindingV3.DerivedVectorOperations.U(32.W),Mux(r.kind===4.U,n,0.U(32.W)))
        counts.foreach(_:=0.U.asTypeOf(new UnifiedSharedOperationCountsV3))
      }
  }
  when(collection.io.routeMetadataFault || io.parentPoison || !countsLegal){faultNow:=true.B}
  // This is a register edge, not a combinational resetRequired->fabricFault
  // feedback loop. Immediate sideband remains visible to the parent fence.
  when(faultNow || collection.io.resetRequired){poison:=true.B}
  when(unknownNow){quarantine:=true.B;poison:=true.B}
  when(io.begin.fire){
    accepted:=b;routeValid:=false.B
    counts.foreach(_:=0.U.asTypeOf(new UnifiedSharedOperationCountsV3))
    when(beginLegal){state:=running}.otherwise{
      terminal:=0.U.asTypeOf(new UnifiedGdnBoundResultV3)
      terminal.transactionId:=b.block.transactionId;terminal.profileId:=b.block.launch.profileId
      terminal.result.accepted:=b.job;terminal.result.status:=Status.Unsupported.U
      terminal.result.drained:=true.B;state:=holding
    }
  }
  when(collection.io.done.fire){
    val sameJob=collection.io.done.bits.accepted.asUInt===accepted.job.asUInt
    val finalExport=routeValid && route.kind===GdnRuntimeChunkClient.State.U && route.phase===18.U &&
      (route.head +& 1.U)===accepted.job.layout.valueHeads &&
      route.chunk===Mux(accepted.job.context.tokens===128.U,1.U,0.U) && oldRouteComplete
    // A successful collection terminal must follow the real last-head export,
    // not merely zero vector debt (phase17 still has real DDR obligations).
    val falseSuccess=collection.io.done.bits.status===Status.Ok.U &&
      (!collection.io.done.bits.stagedComplete || !finalExport)
    val bad=poison || quarantine || faultNow || unknownNow || collection.io.resetRequired ||
      !collection.io.done.bits.drained || !sameJob || falseSuccess
    terminal.transactionId:=accepted.block.transactionId;terminal.profileId:=accepted.block.launch.profileId
    terminal.result:=collection.io.done.bits
    terminal.result.status:=Mux(bad,Status.Protocol.U,collection.io.done.bits.status)
    terminal.result.stagedComplete:=collection.io.done.bits.stagedComplete && !bad
    terminal.result.drained:=drained && collection.io.done.bits.drained && sameJob
    when(!sameJob){
      terminal.result.scratchAckBytes:=0.U;terminal.result.outputAckBytes:=0.U
      terminal.result.stateAckBytes:=0.U
    }
    terminal.resetRequired:=bad
    when(bad){poison:=true.B}
    routeValid:=false.B;state:=holding
  }
  when(io.done.fire){state:=Mux(poison || quarantine || faultNow || unknownNow || collection.io.resetRequired,locked,idle)}
  // Late fault never changes a held terminal. Parent must combine resetRequired
  // with its final publication fence and with admission of any NEW operation.

  val mReq=Reg(new MemoryRequest);val mReply=Reg(new MemoryResponse)
  val mLeaf=Reg(UInt(3.W));val mOriginalTag=Reg(UInt(64.W))
  val mOwner=Reg(new UnifiedSharedOwnerIdentityV3)
  for(i<-0 until 5){
    collection.io.memory(i).request.ready:=state===running && routeValid && route.kind===i.U &&
      mState===0.U && !collection.io.routeAccepted && !quarantine && !unknownNow &&
      counts(0).accepted < "hffffffff".U(33.W)
    collection.io.memory(i).response.valid:=mState===3.U && mLeaf===i.U
    collection.io.memory(i).response.bits:=mReply
    when(collection.io.memory(i).request.fire){
      mReq:=collection.io.memory(i).request.bits;mOriginalTag:=collection.io.memory(i).request.bits.tag
      // Parent global transport remaps this private logical request identity.
      mReq.tag:=Cat(identity.ownerSequence,counts(0).accepted(31,0))
      mOwner:=identity;mLeaf:=i.U;mState:=1.U;counts(0).accepted:=counts(0).accepted+1.U
    }
    when(collection.io.memory(i).response.fire){mState:=0.U;counts(0).returned:=counts(0).returned+1.U}
    when(state===running && routeValid && !collection.io.routeAccepted &&
      collection.io.memory(i).request.valid && (route.kind=/=i.U || counts(0).accepted>="hffffffff".U(33.W))){faultNow:=true.B}
  }
  io.memory.valid:=mState===1.U;io.memory.bits:=mReq
  when(io.memory.fire){mState:=2.U;counts(0).issued:=counts(0).issued+1.U}
  val mMatch=io.response.bits.tag===mReq.tag
  when(io.response.valid && mState===2.U && !mMatch){unknownNow:=true.B}
  io.response.ready:=mState===2.U && mMatch && !quarantine && !unknownNow
  when(io.response.fire){
    mReply:=io.response.bits;mReply.tag:=mOriginalTag;mState:=3.U
    when(io.response.bits.error){faultNow:=true.B}
  }

  val sReq=Reg(new UnifiedScalarRequestV2);val sReply=Reg(new UnifiedScalarResultV2)
  val sLeaf=Reg(UInt(1.W));val sOwner=Reg(new UnifiedSharedOwnerIdentityV3)
  for(i<-0 until 2){
    val allowed=route.kind===(if(i==0)1 else 2).U
    collection.io.scalar(i).request.ready:=state===running && routeValid && allowed &&
      sState===0.U && !collection.io.routeAccepted && !quarantine && !unknownNow &&
      counts(1).accepted < "hffffffff".U(33.W)
    collection.io.scalar(i).result.valid:=sState===3.U && sLeaf===i.U
    collection.io.scalar(i).result.bits:=sReply
    when(collection.io.scalar(i).request.fire){
      sReq:=collection.io.scalar(i).request.bits;sOwner:=identity;sLeaf:=i.U;sState:=1.U
      counts(1).accepted:=counts(1).accepted+1.U
    }
    when(collection.io.scalar(i).result.fire){sState:=0.U;counts(1).returned:=counts(1).returned+1.U}
    when(state===running && routeValid && !collection.io.routeAccepted &&
      collection.io.scalar(i).request.valid && (!allowed || counts(1).accepted>="hffffffff".U(33.W))){faultNow:=true.B}
  }
  io.scalar.request.valid:=sState===1.U;io.scalar.request.bits:=sReq
  when(io.scalar.request.fire){sState:=2.U;counts(1).issued:=counts(1).issued+1.U}
  val sMatch=io.scalar.result.bits.policy===sReq.policy
  when(io.scalar.result.valid && sState===2.U && !sMatch){unknownNow:=true.B}
  io.scalar.result.ready:=sState===2.U && sMatch && !quarantine && !unknownNow
  when(io.scalar.result.fire){sReply:=io.scalar.result.bits;sState:=3.U;when(io.scalar.result.bits.error){faultNow:=true.B}}

  val vReq=Reg(new UnifiedVectorRequestV2);val vReply=Reg(new UnifiedVectorResultV2)
  val vLeaf=Reg(UInt(1.W));val vOwner=Reg(new UnifiedSharedOwnerIdentityV3)
  for(i<-0 until 2){
    val allowed=route.kind===(if(i==0)2 else 4).U
    collection.io.vector(i).request.ready:=state===running && routeValid && allowed &&
      vState===0.U && !collection.io.routeAccepted && !quarantine && !unknownNow &&
      UnifiedSharedOperationBoundsV3.mayAccept(counts(2),vectorExpected)
    collection.io.vector(i).result.valid:=vState===3.U && vLeaf===i.U
    collection.io.vector(i).result.bits:=vReply
    when(collection.io.vector(i).request.fire){
      vReq:=collection.io.vector(i).request.bits;vOwner:=identity;vLeaf:=i.U;vState:=1.U
      counts(2).accepted:=counts(2).accepted+1.U
    }
    when(collection.io.vector(i).result.fire){vState:=0.U;counts(2).returned:=counts(2).returned+1.U}
    when(state===running && routeValid && !collection.io.routeAccepted &&
      collection.io.vector(i).request.valid && (!allowed || counts(2).accepted>=vectorExpected.pad(33))){faultNow:=true.B}
  }
  io.vectorRequest.valid:=vState===1.U;io.vectorRequest.bits:=vReq
  when(io.vectorRequest.fire){vState:=2.U;counts(2).issued:=counts(2).issued+1.U}
  val vMatch=io.vectorResult.bits.policy===vReq.policy
  when(io.vectorResult.valid && vState===2.U && !vMatch){unknownNow:=true.B}
  io.vectorResult.ready:=vState===2.U && vMatch && !quarantine && !unknownNow
  when(io.vectorResult.fire){vReply:=io.vectorResult.bits;vState:=3.U;when(io.vectorResult.bits.error){faultNow:=true.B}}
  // Captured owner metadata is not reconstructed from changing route pins.
  when(mState=/=0.U && mOwner.asUInt=/=identity.asUInt){faultNow:=true.B}
  when(sState=/=0.U && sOwner.asUInt=/=identity.asUInt){faultNow:=true.B}
  when(vState=/=0.U && vOwner.asUInt=/=identity.asUInt){faultNow:=true.B}
}
