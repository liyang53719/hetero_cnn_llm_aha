// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Geometry/echo checks only. The parent MUST supply the real private allocator
  * lease after accepted postnorm owner.result.fire and the live resource fence.
  * A matching packet, a legal transaction0 or a valid address is NOT authority.
  * No Host-written grant, transformed weight or fabricated norm receipt enters.
  */
object UnifiedMoeRuntimeLeaseGeometryV4 {
  val MaxGroups=256;val ReservedOwners=1+5*MaxGroups
  def router(l:HostMoeRuntimePhaseLeaseV5):UnifiedMoeRouterPipelineCommandV2={
    val r=WireDefault(0.U.asTypeOf(new UnifiedMoeRouterPipelineCommandV2))
    r.dense.context:=l.context;r.dense.postnorm:=l.postnormBase
    r.dense.weight:=l.weights(HostMoeWeightRoleV4.Router).address
    r.dense.output:=l.routerLogits;r.dense.allocationEnd:=l.allocationEnd
    r.dense.ownerSequence:=l.firstOwnerSequence
    r.allocation.context:=l.context;r.allocation.allocationSequence:=l.allocationSequence
    r.allocation.metadataBase:=l.metadataBase;r.allocation.allocationEnd:=l.allocationEnd
    r
  }
  def legal(l:HostMoeRuntimePhaseLeaseV5):Bool={
    val c=l.context;val m=c.tokens;val j=l.postnormJob
    val (p,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
    val source=j.kind===QwenOwnerKind.GdnRmsNorm.U && j.tag===l.postnormOwnerSequence &&
      j.dst===l.postnormBase && j.dst===c.input.address && j.a===l.residualBase &&
      j.a===c.residual.address && j.tag===c.postnormOwnerSequence && j.m===m && j.k===2048.U && j.n===2048.U &&
      j.activationBf16 && j.weightBf16 && j.outputBf16 && j.writeBytes===(m.pad(64)<<12) &&
      l.postnormResult.tag===j.tag && l.postnormResult.status===Status.Ok.U &&
      l.postnormResult.writeBytes===j.writeBytes
    val regions=Seq((l.metadataBase,16384L),(l.descriptorBase,16384L),
      (l.routerLogits,65536L),(l.gatheredInput,524288L),(l.gateOutput,131072L),
      (l.upOutput,131072L),(l.activationOutput,131072L),(l.routedDown,4194304L),
      (l.sharedDown,524288L),(l.mergedOutput,524288L))
    def overlaps(a:UInt,an:UInt,b:UInt,bn:UInt):Bool=
      a.pad(96)<b.pad(96)+bn.pad(96) && b.pad(96)<a.pad(96)+an.pad(96)
    val arena=l.allocationBase>=c.host.regions(3).base && l.allocationBase<l.allocationEnd &&
      l.allocationEnd<=(BigInt(1)<<56).U && l.allocationBase(5,0)===0.U && l.allocationEnd(5,0)===0.U
    val geometry=regions.map{case(b,n)=>b=/=0.U && b(5,0)===0.U &&
      b>=l.allocationBase && b.pad(96)+n.U<=l.allocationEnd.pad(96)}.reduce(_&&_)
    val disjoint=(for(i<-regions.indices;k<-0 until i)yield
      !overlaps(regions(i)._1,regions(i)._2.U,regions(k)._1,regions(k)._2.U)).reduce(_&&_)
    // Phase views are actual typed metadata, never fabricated full-block input/state/KV.
    // Protect the complete input/residual/final-output spans throughout routed staging.
    val phaseViews=Seq(c.input,c.residual,c.output)
    val phaseViewsLegal=phaseViews.map(t=>t.dtype===5.U && t.rank===2.U &&
      t.dims(0)===m && t.dims(1)===2048.U && t.dims(2)===1.U && t.dims(3)===1.U &&
      t.elementCount===(m.pad(64)<<11) && t.payloadBytes===(m.pad(64)<<12) &&
      t.address=/=0.U && t.address(5,0)===0.U &&
      t.paddedEnd.pad(96)===t.address.pad(96)+t.payloadBytes.pad(96) &&
      t.paddedEnd<=(BigInt(1)<<56).U).reduce(_&&_)
    val live=phaseViews.map(t=>(t.address,t.paddedEnd-t.address)) ++
      l.weights.map(w=>(w.address,w.payloadBytes))
    val liveOK=live.map{case(b,n)=>b=/=0.U && b(5,0)===0.U && n=/=0.U &&
      b.pad(96)+n.pad(96)<=(BigInt(1)<<56).U}.reduce(_&&_)
    val preserve=(for((b,n)<-regions;(rb,rn)<-live)yield !overlaps(b,n.U,rb,rn)).reduce(_&&_)
    // The four roles consumed here are pinned BF16 [K,N]/[E,K,N] views. All
    // eight role provenance/permissions remain the actual parent's obligation.
    val usedWeights=(0 until 4).map{i=>
      val w=l.weights(i);val e=i!=0;val k=if(i==3)512 else 2048;val n=if(i==0)256 else if(i==3)2048 else 512
      val count=BigInt(k)*n*(if(e)256 else 1)
      val dims=if(e)w.rank===3.U && w.dims(0)===256.U && w.dims(1)===k.U && w.dims(2)===n.U && w.dims(3)===1.U
        else w.rank===2.U && w.dims(0)===k.U && w.dims(1)===n.U && w.dims(2)===1.U && w.dims(3)===1.U
      w.dtype===5.U && dims && w.elementCount===count.U && w.payloadBytes===(count*2).U &&
        w.paddedEnd.pad(96)>=w.address.pad(96)+w.payloadBytes && w.paddedEnd<=(BigInt(1)<<56).U
    }.reduce(_&&_)
    known && (c.host.profileId===3.U || c.host.profileId===4.U) && p.asUInt===c.profile.asUInt &&
      c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.host) && m>=1.U && m<=128.U &&
      p.hidden===2048.U && p.expertCount===256.U && p.expertsPerToken===8.U &&
      p.expertFfn===512.U && p.sharedFfn===512.U && p.mlp===1.U &&
      l.allocationSequence=/=0.U && l.firstOwnerSequence>l.postnormPhysicalSequence &&
      l.firstOwnerSequence.pad(33)+(ReservedOwners-1).U<"hffffffff".U(33.W) &&
      source && phaseViewsLegal && arena && geometry && disjoint && liveOK && preserve && usedWeights &&
      UnifiedMoeRouterPipelineCommandV2.legal(router(l))
  }
}

/** Actual source-level control connection, ZERO arithmetic/physical resources.
  * Uses the one parent Dense/Scalar/format/selection/DDR fabric through logical
  * ports; does not instantiate any of those engines or a new hardware top.
  * Router -> actual expert group -> Gather DDR/ACK -> gate/up/activation/down
  * sequencer -> full64B descriptor write/ACK. This is routed-phase staging ONLY.
  * Routed completion can continue into the SAME sequencer for the shared
  * expert. N1 sigmoid gate, merge and block completion remain separate.
  * Existing arithmetic/tie qualifications are NOT changed by connecting wires.
  *
  * The parent reserves1289 owner IDs once; routed subrange1281 contains
  * router1 and at most256*(gather1+FFN4). Shared uses fixed1281..1284.
  * The parent globally reserves the full interval even if fewer experts occur.
  * nextOwnerSequence reports actual progress, NOT permission to reuse the tail.
  * Transport tags here are client-local; the original shared DDR arbiter must
  * own full transaction/owner attribution and its monotonic physical sequence.
  * All raw responses have minimum next-cycle latency. Faulted held offers are
  * never withdrawn. Missing/unknown response can require externally isolated
  * reset; no local watchdog fabricates a drained success or lease release.
  */
/** PRIVATE continuation: same retained lease, only after actual routed done.fire.
  * A copied identity is not an allocator/epoch grant. No FFN workplan from Host. */
class UnifiedMoeSharedFfnBeginV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
}
class UnifiedMoeSharedFfnRetirementV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val result=new UnifiedMoeFfnGroupResultV3
}
class UnifiedMoeRuntimeExpertLoopV4 extends Module {
  val io=IO(new Bundle {
    val rawScoreObservation=Output(Valid(new UnifiedMoeRouterScoreObservationV1))
    val begin=Flipped(Decoupled(new HostMoeRuntimePhaseLeaseV5))
    val done=Decoupled(new HostMoeRoutedPhaseResultV5)
    val sharedBegin=Flipped(Decoupled(new UnifiedMoeSharedFfnBeginV5))
    val sharedResult=Decoupled(new UnifiedMoeSharedFfnRetirementV5)
    val actualSharedDownFire=Output(Bool())
    val currentFault=Input(Bool()) // actual parent sticky fault, never a Host grant
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val routerDenseJob=Decoupled(new QwenOwnerJob)
    val routerDenseResult=Flipped(Decoupled(new QwenOwnerResult));val routerDenseResetRequired=Input(Bool())
    val ffnDenseJob=Decoupled(new QwenOwnerJob)
    val ffnDenseResult=Flipped(Decoupled(new QwenOwnerResult));val ffnDenseResetRequired=Input(Bool())
    val routerReadMemory=Decoupled(new MemoryRequest);val routerReadResponse=Flipped(Decoupled(new MemoryResponse))
    val routerReadResetRequired=Input(Bool())
    val routeMapMemory=Decoupled(new MemoryRequest);val routeMapResponse=Flipped(Decoupled(new MemoryResponse))
    val routeMapResetRequired=Input(Bool())
    val gatherMemory=Decoupled(new MemoryRequest);val gatherResponse=Flipped(Decoupled(new MemoryResponse))
    val gatherResetRequired=Input(Bool())
    val activationMemory=Decoupled(new MemoryRequest);val activationResponse=Flipped(Decoupled(new MemoryResponse))
    val activationResetRequired=Input(Bool())
    val descriptorMemory=Decoupled(new MemoryRequest);val descriptorResponse=Flipped(Decoupled(new MemoryResponse))
    val descriptorResetRequired=Input(Bool())
    val routerScalar=new UnifiedScalarClientV2;val activationScalar=new UnifiedScalarClientV2
    val routerFormatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val routerFormatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val activationFormatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val activationFormatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val selection=new UnifiedMoeRouterSelectionClientV2
    val routerScalarOrdinal=Output(UInt(32.W));val routerToken=Output(UInt(32.W));val routerPhase=Output(UInt(5.W))
    // Read-only provenance probes. None is an injection/commit input. Private
    // lease/job origin and parent resource-side attribution still require wiring.
    val acceptedLeaseFire=Output(Bool());val acceptedLease=Output(new HostMoeRuntimePhaseLeaseV5)
    val acceptedGroupFire=Output(Bool());val acceptedGroup=Output(new UnifiedMoeExpertGroupV2)
    val actualGatherStart=Output(Bool());val actualGatherJob=Output(new UnifiedMoeActivationGatherJobV2)
    val actualFfnStart=Output(Bool());val actualFfnJob=Output(new UnifiedMoeFfnGroupJobV3)
    val actualDownFire=Output(Bool());val actualDown=Output(new UnifiedMoeDenseWritebackV2)
    val descriptorAck=Output(Bool());val descriptorWord=Output(UInt(512.W))
  })
  val router=Module(new UnifiedMoeRouterPipelineBindingV2)
  io.rawScoreObservation:=router.io.rawScoreObservation
  val gather=Module(new UnifiedMoeActivationGatherV2)
  val ffn=Module(new UnifiedMoeFfnGroupSequencerV3)
  io.routerDenseJob<>router.io.denseJob;router.io.denseDone<>io.routerDenseResult
  router.io.denseResetRequired:=io.routerDenseResetRequired
  io.routerReadMemory<>router.io.readMemory;router.io.readResponse<>io.routerReadResponse
  router.io.readMemoryResetRequired:=io.routerReadResetRequired
  io.routeMapMemory<>router.io.mapMemory;router.io.mapResponse<>io.routeMapResponse
  router.io.mapMemoryResetRequired:=io.routeMapResetRequired
  io.routerScalar<>router.io.scalar;io.selection<>router.io.selection
  io.routerFormatRequest<>router.io.formatRequest;router.io.formatResult<>io.routerFormatResult
  io.routerScalarOrdinal:=router.io.scalarOperationOrdinal;io.routerToken:=router.io.arithmeticToken
  io.routerPhase:=router.io.arithmeticPhase
  io.gatherMemory<>gather.io.memory;gather.io.response<>io.gatherResponse
  gather.io.memoryResetRequired:=io.gatherResetRequired
  io.ffnDenseJob<>ffn.io.denseJob;ffn.io.denseResult<>io.ffnDenseResult
  ffn.io.denseResetRequired:=io.ffnDenseResetRequired
  io.activationMemory<>ffn.io.memory;ffn.io.response<>io.activationResponse
  ffn.io.memoryResetRequired:=io.activationResetRequired
  io.activationScalar<>ffn.io.scalar
  io.activationFormatRequest<>ffn.io.formatRequest;ffn.io.formatResult<>io.activationFormatResult

  val ss=Enum(15)
  val idle=ss(0);val offerRouter=ss(1);val groups=ss(2);val offerGather=ss(3);val waitGather=ss(4)
  val offerFfn=ss(5);val waitFfn=ss(6);val offerDescriptor=ss(7);val waitDescriptor=ss(8)
  val report=ss(9);val locked=ss(10)
  val awaitShared=ss(11);val offerShared=ss(12);val waitShared=ss(13);val reportShared=ss(14)
  val state=RegInit(idle);val lease=Reg(new HostMoeRuntimePhaseLeaseV5)
  val routerCommand=Reg(new UnifiedMoeRouterPipelineCommandV2)
  val gatherJob=Reg(new UnifiedMoeActivationGatherJobV2);val ffnJob=Reg(new UnifiedMoeFfnGroupJobV3)
  val group=Reg(new UnifiedMoeExpertGroupV2)
  val out=Reg(new HostMoeRoutedPhaseResultV5)
  val sharedOut=Reg(new UnifiedMoeSharedFfnRetirementV5)
  val committedGroups=RegInit(0.U(9.W));val committedRows=RegInit(0.U(11.W))
  val lastExpert=Reg(UInt(8.W));val expertSeen=RegInit(false.B)
  val nextOwner=Reg(UInt(32.W))
  val routerPending=RegInit(false.B);val routerRetired=RegInit(false.B)
  val gatherPending=RegInit(false.B);val ffnPending=RegInit(false.B)
  val descriptorPending=RegInit(false.B);val descriptor=Reg(new MemoryRequest)
  val transportSequence=RegInit(0.U(64.W)) // no reset/reuse without parent stale isolation
  val haveTransaction=RegInit(false.B);val lastTransaction=Reg(UInt(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknown=(router.io.retirement.valid && !routerPending) ||
    (gather.io.done.valid && !gatherPending) || (ffn.io.result.valid && !ffnPending) ||
    (io.descriptorResponse.valid && !descriptorPending)
  val childFault=router.io.resetRequired || gather.io.resetRequired || ffn.io.resetRequired
  val rr=router.io.retirement.bits
  val routerReceiptExact=rr.command.asUInt===routerCommand.asUInt &&
    rr.map.transactionId===lease.context.transactionId && rr.map.allocationSequence===lease.allocationSequence &&
    rr.map.metadataBase===lease.metadataBase
  val routerReceiptGood=routerReceiptExact && rr.childrenStarted && rr.status===Status.Ok.U && rr.localDrained &&
    rr.map.routes===(lease.context.tokens.pad(11)<<3)
  val badRouterReceipt=routerPending && router.io.retirement.valid && !routerReceiptGood
  val faultNow=io.currentFault || childFault || unknown || badRouterReceipt || io.descriptorResetRequired
  when(faultNow){poison:=true.B}
  when(unknown || io.descriptorResetRequired){quarantine:=true.B}
  val fault=poison || quarantine || faultNow
  // Only a register feeds control poison back to children: no combinational
  // resetRequired -> private-start -> child faultNow feedback cycle.
  router.io.externalPoison:=poison;ffn.io.sourceResetRequired:=poison
  io.resetRequired:=fault
  io.contextReserved:=state=/=idle || io.begin.valid || io.sharedBegin.valid || router.io.contextReserved ||
    gather.io.contextReserved || ffn.io.contextReserved || descriptorPending
  io.begin.ready:=state===idle && !fault && !router.io.contextReserved &&
    !gather.io.contextReserved && !ffn.io.contextReserved && !descriptorPending
  io.done.valid:=state===report;io.done.bits:=out
  io.sharedBegin.ready:=state===awaitShared && !fault && !routerPending && !gatherPending && !ffnPending &&
    !descriptorPending && !router.io.contextReserved && !gather.io.contextReserved && !ffn.io.contextReserved
  io.sharedResult.valid:=state===reportShared;io.sharedResult.bits:=sharedOut
  io.actualSharedDownFire:=false.B
  router.io.begin.valid:=state===offerRouter;router.io.begin.bits:=routerCommand
  router.io.group.ready:=state===groups && !fault && !routerRetired
  router.io.retirement.ready:=routerPending && !quarantine && state=/=report && state=/=locked
  gather.io.job.valid:=state===offerGather;gather.io.job.bits:=gatherJob
  gather.io.done.ready:=state===waitGather && gatherPending && !quarantine
  ffn.io.job.valid:=state===offerFfn || state===offerShared;ffn.io.job.bits:=ffnJob
  ffn.io.result.ready:=(state===waitFfn || state===waitShared) && ffnPending && !quarantine
  io.descriptorMemory.valid:=state===offerDescriptor;io.descriptorMemory.bits:=descriptor
  io.descriptorResponse.ready:=state===waitDescriptor && descriptorPending && !quarantine && !io.descriptorResetRequired
  io.acceptedLeaseFire:=io.begin.fire;io.acceptedLease:=io.begin.bits
  io.acceptedGroupFire:=router.io.group.fire;io.acceptedGroup:=router.io.group.bits
  io.actualGatherStart:=gather.io.job.fire;io.actualGatherJob:=gather.io.job.bits
  io.actualFfnStart:=ffn.io.job.fire;io.actualFfnJob:=ffn.io.job.bits
  io.actualDownFire:=false.B;io.actualDown:=ffn.io.result.bits.down
  io.descriptorAck:=false.B;io.descriptorWord:=descriptor.data
  def finishError(status:UInt,locallyDrained:Bool):Unit={
    out.status:=status;out.locallyDrained:=locallyDrained;out.resetRequired:=true.B
    out.groups:=committedGroups;out.routedRows:=committedRows;out.nextOwnerSequence:=nextOwner
    poison:=true.B;state:=report
  }
  val proposed=io.begin.bits
  val proposedRouter=UnifiedMoeRuntimeLeaseGeometryV4.router(proposed) // unconditional construction; fire still controls register capture
  val beginLegal=UnifiedMoeRuntimeLeaseGeometryV4.legal(proposed) &&
    proposed.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W) &&
    (!haveTransaction || proposed.context.transactionId>lastTransaction) &&
    transportSequence.pad(65)+256.U<=(BigInt(1)<<64).U-1.U
  when(io.begin.fire){
    lease:=proposed;routerCommand:=proposedRouter
    out:=0.U.asTypeOf(new HostMoeRoutedPhaseResultV5)
    out.transactionId:=proposed.context.transactionId;out.allocationSequence:=proposed.allocationSequence
    out.routedDownBase:=proposed.routedDown;out.nextOwnerSequence:=proposed.firstOwnerSequence
    committedGroups:=0.U;committedRows:=0.U;expertSeen:=false.B;routerRetired:=false.B
    nextOwner:=proposed.firstOwnerSequence+1.U
    when(beginLegal){haveTransaction:=true.B;lastTransaction:=proposed.context.transactionId;state:=offerRouter}
    .otherwise{out.status:=Status.Bounds.U;out.locallyDrained:=true.B;state:=report}
  }
  when(router.io.begin.fire){routerPending:=true.B;state:=groups}

  val g=router.io.group.bits
  val groupBytes=g.groupRows.pad(96)<<12
  val proposedDown=lease.routedDown.pad(96)+(g.firstRoute.pad(96)<<12)
  val groupLegal=g.transactionId===lease.context.transactionId && g.allocationSequence===lease.allocationSequence &&
    g.groupRows>=1.U && g.groupRows<=lease.context.tokens &&
    g.firstRoute===committedRows && g.firstRoute.pad(12)+g.groupRows<=(lease.context.tokens.pad(12)<<3) &&
    (!expertSeen || g.expert>lastExpert) && committedGroups<256.U &&
    g.descriptorBase.pad(96)===lease.metadataBase.pad(96)+8192.U+(g.firstRoute.pad(96)<<3) &&
    proposedDown+groupBytes<=lease.routedDown.pad(96)+4194304.U &&
    nextOwner.pad(33)+4.U<"hffffffff".U(33.W)
  when(router.io.group.fire){
    when(!groupLegal){finishError(Status.Protocol.U,false.B)}
    .otherwise{
      group:=g
      gatherJob:=0.U.asTypeOf(new UnifiedMoeActivationGatherJobV2)
      gatherJob.context:=lease.context;gatherJob.group:=g;gatherJob.postnormResult:=lease.postnormResult
      gatherJob.postnormOwnerSequence:=lease.postnormOwnerSequence;gatherJob.gatherOwnerSequence:=nextOwner
      gatherJob.postnormBase:=lease.postnormBase;gatherJob.metadataBase:=lease.metadataBase
      gatherJob.output:=lease.gatheredInput;gatherJob.allocationEnd:=lease.allocationEnd
      ffnJob:=0.U.asTypeOf(new UnifiedMoeFfnGroupJobV3)
      ffnJob.context:=lease.context;ffnJob.expert:=g.expert;ffnJob.groupRows:=g.groupRows
      ffnJob.firstOwnerSequence:=nextOwner+1.U;ffnJob.input:=lease.gatheredInput
      ffnJob.gateWeight:=lease.weights(HostMoeWeightRoleV4.ExpertGate).address+(g.expert.pad(64)<<21)
      ffnJob.upWeight:=lease.weights(HostMoeWeightRoleV4.ExpertUp).address+(g.expert.pad(64)<<21)
      ffnJob.downWeight:=lease.weights(HostMoeWeightRoleV4.ExpertDown).address+(g.expert.pad(64)<<21)
      ffnJob.gateOutput:=lease.gateOutput;ffnJob.upOutput:=lease.upOutput
      ffnJob.activationOutput:=lease.activationOutput;ffnJob.downOutput:=proposedDown(63,0)
      ffnJob.allocationEnd:=lease.allocationEnd;state:=offerGather
    }
  }
  when(gather.io.job.fire){gatherPending:=true.B;state:=waitGather}
  val (actualFfn,actualFfnLegal)=UnifiedMoeGatherFfnPlanV3.fromActualGather(gatherJob,gather.io.done.bits,ffnJob,fault)
  when(gather.io.done.fire){
    val r=gather.io.done.bits
    val exact=r.context.asUInt===gatherJob.context.asUInt && r.group.asUInt===gatherJob.group.asUInt &&
      r.gatherOwnerSequence===gatherJob.gatherOwnerSequence && r.output===gatherJob.output
    when(!exact){quarantine:=true.B;finishError(Status.Protocol.U,false.B)}
    .otherwise{
      gatherPending:=false.B
      when(actualFfnLegal){ffnJob:=actualFfn;state:=offerFfn}
      .otherwise{finishError(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U),false.B)}
    }
  }
  when(ffn.io.job.fire){ffnPending:=true.B;state:=Mux(state===offerShared,waitShared,waitFfn)}
  when(ffn.io.result.fire && state===waitFfn){
    val r=ffn.io.result.bits;val d=r.down
    val expectedBytes=group.groupRows.pad(64)<<12
    val exact=d.context.asUInt===lease.context.asUInt && d.expert===group.expert && d.stage===2.U &&
      d.groupRows===group.groupRows && d.ownerSequence===ffnJob.firstOwnerSequence+3.U &&
      d.output===ffnJob.downOutput && d.result.tag===d.ownerSequence
    val good=exact && r.status===Status.Ok.U && r.drained && r.downCommitted && r.completedStages===4.U &&
      d.successfulWriteback && d.result.status===Status.Ok.U && d.result.writeBytes===expectedBytes && !fault
    when(!exact){quarantine:=true.B;finishError(Status.Protocol.U,false.B)}
    .otherwise{
      ffnPending:=false.B
      when(good){
        io.actualDownFire:=true.B
        descriptor:=0.U.asTypeOf(new MemoryRequest)
        descriptor.address:=lease.descriptorBase+(group.expert.pad(64)<<6)
        descriptor.write:=true.B;descriptor.mask:="hffffffffffffffff".U
        descriptor.data:=UnifiedMoeDownDescriptorV4.pack(lease.context.transactionId,lease.allocationSequence,group.firstRoute,d)
        descriptor.tag:=transportSequence;state:=offerDescriptor
      }.otherwise{finishError(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U),false.B)}
    }
  }
  when(io.descriptorMemory.fire){descriptorPending:=true.B;transportSequence:=transportSequence+1.U;state:=waitDescriptor}
  when(io.descriptorResponse.fire){
    val r=io.descriptorResponse.bits
    when(r.tag=/=descriptor.tag || r.error){quarantine:=true.B;finishError(Status.Protocol.U,false.B)}
    .otherwise{
      descriptorPending:=false.B
      when(fault){finishError(Status.Dependency.U,false.B)}
      .otherwise{
        io.descriptorAck:=true.B;committedGroups:=committedGroups+1.U
        committedRows:=committedRows+group.groupRows;lastExpert:=group.expert;expertSeen:=true.B
        nextOwner:=nextOwner+5.U;state:=groups
      }
    }
  }
  // Router may retire while the LAST accepted expert group is still processing;
  // retain that proof independently. It never retires a group or descriptor.
  when(router.io.retirement.fire){
    when(!routerReceiptGood || fault){
      // Asynchronous to group processing: do NOT change its state here. A
      // physical descriptor offer (or already published child offer) may be
      // backpressured and must not disappear. Keep the unresolved router debt;
      // report at a safe boundary or wait visibly faulted for external isolation.
      poison:=true.B
      when(!routerReceiptExact){quarantine:=true.B}
    }.otherwise{routerPending:=false.B;routerRetired:=true.B}
  }
  when(state===groups && routerRetired){
    val allRows=committedRows===(lease.context.tokens.pad(11)<<3)
    val quiet= !routerPending && !gatherPending && !ffnPending && !descriptorPending &&
      !router.io.contextReserved && !gather.io.contextReserved && !ffn.io.contextReserved
    when(allRows && committedGroups>=1.U && quiet && !fault){
      out.status:=Status.Ok.U;out.locallyDrained:=true.B;out.resetRequired:=false.B
      out.groups:=committedGroups;out.routedRows:=committedRows;out.nextOwnerSequence:=nextOwner;state:=report
    }.elsewhen(fault || !allRows){finishError(Status.Protocol.U,false.B)}
  }
  // In a no-offer boundary a new fault is reported without inventing drain.
  // During an existing offer/wait, preserve that packet/obligation; visible
  // resetRequired remains held even when a provider never returns.
  when(state===groups && fault){finishError(Status.Dependency.U,false.B)}
  // An actual successful routed retirement is the ONLY route to this private
  // continuation. It is not a second begin and cannot reset transaction history.
  when(io.done.fire){
    state:=Mux(fault || !out.locallyDrained || out.status=/=Status.Ok.U || out.resetRequired,locked,awaitShared)
  }
  val (proposedShared,sharedPlanLegal)=UnifiedMoeSharedFfnPlanV5.fromActualRoutedRetirement(lease,out)
  val sharedIdentity=io.sharedBegin.bits.context.asUInt===lease.context.asUInt &&
    io.sharedBegin.bits.allocationSequence===lease.allocationSequence
  when(io.sharedBegin.fire){
    sharedOut:=0.U.asTypeOf(new UnifiedMoeSharedFfnRetirementV5)
    sharedOut.context:=lease.context;sharedOut.allocationSequence:=lease.allocationSequence
    when(sharedIdentity && sharedPlanLegal && !fault){ffnJob:=proposedShared;state:=offerShared}
    .otherwise{
      sharedOut.result.status:=Status.Dependency.U;sharedOut.result.drained:=true.B
      poison:=true.B;state:=reportShared
    }
  }
  when(ffn.io.result.fire && state===waitShared){
    val r=ffn.io.result.bits;val d=r.down
    val exact=d.context.asUInt===lease.context.asUInt && d.expert===256.U && d.stage===2.U &&
      d.groupRows===lease.context.tokens && d.output===lease.sharedDown &&
      d.ownerSequence===ffnJob.firstOwnerSequence+3.U
    sharedOut.result:=r
    when(!exact){
      sharedOut.result.status:=Status.Protocol.U;sharedOut.result.drained:=false.B
      sharedOut.result.downCommitted:=false.B;quarantine:=true.B;poison:=true.B
    }.otherwise{
      // Same actual sequencer result.fire. Current child fault/unknown is
      // conservatively NOT a proof of global drain even if its held payload
      // previously declared local drain; parent isolation may still be needed.
      val currentDrained=r.drained && !quarantine && !unknown && !childFault && !io.descriptorResetRequired
      ffnPending:= !currentDrained
      when(UnifiedMoeSharedFfnPlanV5.completed(lease,r) && !fault){io.actualSharedDownFire:=true.B}
      .otherwise{
        sharedOut.result.status:=Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U)
        sharedOut.result.drained:=currentDrained
        sharedOut.result.downCommitted:=false.B;poison:=true.B
      }
    }
    state:=reportShared
  }
  when(io.sharedResult.fire){state:=Mux(fault || !sharedOut.result.drained,locked,idle)}
  // Parent retains the entire1289 reservation and allocation across N1, merge
  // and residual. Shared result is intermediate; original begin must not be
  // reoffered by that parent until its final real release/current-fault fence.
}
