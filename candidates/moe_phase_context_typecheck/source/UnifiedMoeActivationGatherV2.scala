// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE original-scheduler job. postnormResult must be captured from the
  * actual original norm owner.result.fire, with fullcontext/ownerSequence side
  * ledger, never a Host-created packet. group must be the real RouteGroupV2
  * output (its entire map is already ACKed before the firstgroup). Scratch
  * fields come from the real accepted-context allocator; no allocator means no
  * job.valid. Type names alone do not establish either origin. */
class UnifiedMoeActivationGatherJobV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val group=new UnifiedMoeExpertGroupV2
  val postnormResult=new QwenOwnerResult
  val postnormOwnerSequence=UInt(32.W)
  val gatherOwnerSequence=UInt(32.W)
  val postnormBase=UInt(64.W)
  val metadataBase=UInt(64.W)
  val output=UInt(64.W);val allocationEnd=UInt(64.W)
}
class UnifiedMoeGatherCommitV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val group=new UnifiedMoeExpertGroupV2
  val gatherOwnerSequence=UInt(32.W)
  val output=UInt(64.W);val acknowledgedWriteBytes=UInt(64.W)
  val status=UInt(8.W);val drained=Bool()
}

/** Actual DDR descriptor -> token activation -> packed expert-group BF16 DDR.
  * FixedH2048 and M<=128 are runtime-qualifiedprofile fields, not Scala knobs.
  * Sharedexpert uses the original full-M postnorm directly, not this gather.
  * No Dense/ALU/vector/Scalar/Matrix is instantiated: one512bit stagingreg plus
  * context/identity/loop registers. Output DDR up to512KiB is an explicit
  * allocator-owned lifetime, NOT an additional onchip tensor SRAM.
  *
  * One descriptorread plus64 activationreads+64 acknowledgedwrites perrow.
  * Every outputbyte is copied from actual memoryresponse, no Host data input.
  * Commit exists only after all matching finalwriteACKs. The parent can then
  * use output as groupedDense A, preserving actual groupRows rather than
  * looping a completeblock M1. Scalar/router/expertactivation remainsseparate.
  */
class UnifiedMoeActivationGatherV2 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new UnifiedMoeActivationGatherJobV2))
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool())
    val done=Decoupled(new UnifiedMoeGatherCommitV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val idle::descriptor::waitDescriptor::activation::waitActivation::write::waitWrite::report::Nil=Enum(8)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeActivationGatherJobV2)
  val result=Reg(new UnifiedMoeGatherCommitV2)
  val row=Reg(UInt(7.W));val token=Reg(UInt(7.W));val beat=Reg(UInt(6.W))
  val data=Reg(UInt(512.W));val written=RegInit(0.U(64.W))
  val sequence=RegInit(0.U(64.W));val pendingTag=Reg(UInt(64.W))
  val lastOwner=Reg(UInt(32.W));val ownerSeen=RegInit(false.B)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val waiting=state===waitDescriptor || state===waitActivation || state===waitWrite
  val offered=state===descriptor || state===activation || state===write
  val unknown=io.response.valid && !waiting
  when(unknown || io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  io.resetRequired:=poison||quarantine||unknown||io.memoryResetRequired
  io.contextReserved:=state=/=idle || io.job.valid
  io.job.ready:=state===idle && !io.resetRequired
  val in=io.job.bits;val c=in.context;val g=in.group
  val (p,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
  val bytes=g.groupRows.pad(96)*p.hidden*2.U
  val inputEnd=in.postnormBase.pad(96)+c.tokens.pad(96)*p.hidden*2.U
  val outputEnd=in.output.pad(96)+bytes
  val metadataEnd=in.metadataBase.pad(96)+16384.U
  val aligned=Seq(in.postnormBase,in.output,in.metadataBase).map(x=>x=/=0.U && x(5,0)===0.U).reduce(_&&_)
  val noAlias= !(in.output.pad(96)<inputEnd && in.postnormBase.pad(96)<outputEnd) &&
    !(in.output.pad(96)<metadataEnd && in.metadataBase.pad(96)<outputEnd) &&
    !(in.postnormBase.pad(96)<metadataEnd && in.metadataBase.pad(96)<inputEnd)
  val legal=known && p.asUInt===c.profile.asUInt && p.mlp===1.U && p.hidden===2048.U &&
    p.expertCount===256.U && p.expertsPerToken===8.U &&
    c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.host) && c.tokens>=1.U && c.tokens<=128.U &&
    g.transactionId===c.transactionId && g.allocationSequence=/=0.U &&
    g.groupRows>=1.U && g.groupRows<=c.tokens &&
    g.firstRoute.pad(12)+g.groupRows<=(c.tokens.pad(12)<<3) &&
    g.descriptorBase.pad(96)===in.metadataBase.pad(96)+8192.U+(g.firstRoute.pad(96)<<3) &&
    in.postnormBase===c.input.address && inputEnd===c.input.paddedEnd.pad(96) &&
    in.postnormOwnerSequence===c.postnormOwnerSequence &&
    in.postnormResult.tag===in.postnormOwnerSequence && in.postnormResult.status===Status.Ok.U &&
    in.postnormResult.writeBytes===c.tokens.pad(64)*p.hidden*2.U &&
    in.gatherOwnerSequence=/="hffffffff".U && (!ownerSeen || in.gatherOwnerSequence>lastOwner) &&
    aligned && noAlias && in.output>=c.host.regions(3).base && in.metadataBase>=c.host.regions(3).base &&
    outputEnd<=in.allocationEnd.pad(96) &&
    Seq(inputEnd,outputEnd,metadataEnd).map(_<=(BigInt(1)<<56).U).reduce(_&&_) &&
    sequence.pad(65)+g.groupRows.pad(65)*129.U<=(BigInt(1)<<64).U-1.U
  val descriptorAddress=job.group.descriptorBase+(row.pad(64)<<3)
  io.memory.valid:=offered // never withdraw an offeredpacket on a subsequentfault
  io.memory.bits.write:=state===write
  io.memory.bits.address:=Mux(state===descriptor,Cat(descriptorAddress(63,6),0.U(6.W)),
    Mux(state===activation,job.postnormBase+(token.pad(64)<<12)+(beat.pad(64)<<6),
      job.output+(row.pad(64)<<12)+(beat.pad(64)<<6)))
  io.memory.bits.data:=data
  io.memory.bits.mask:=Mux(state===write,"hffffffffffffffff".U,0.U)
  io.memory.bits.tag:=sequence
  io.response.ready:=waiting && !quarantine && !io.memoryResetRequired
  io.done.valid:=state===report;io.done.bits:=result
  when(io.job.fire){
    job:=in;row:=0.U;beat:=0.U;written:=0.U
    result:=0.U.asTypeOf(new UnifiedMoeGatherCommitV2)
    result.context:=c;result.group:=g;result.gatherOwnerSequence:=in.gatherOwnerSequence;result.output:=in.output
    when(legal){lastOwner:=in.gatherOwnerSequence;ownerSeen:=true.B;state:=descriptor}
    .otherwise{result.status:=Status.Bounds.U;result.drained:=true.B;state:=report}
  }
  when(io.memory.fire){
    pendingTag:=sequence;sequence:=sequence+1.U
    when(state===descriptor){state:=waitDescriptor}
    .elsewhen(state===activation){state:=waitActivation}
    .otherwise{state:=waitWrite}
  }
  when(io.response.fire){
    when(io.response.bits.tag=/=pendingTag || io.response.bits.error){
      poison:=true.B;quarantine:=true.B // no fake writecredit or outputcommit
    }.otherwise{
      when(state===waitDescriptor){
        val word=(io.response.bits.data>>(descriptorAddress(5,3)<<6))(63,0)
        val good=word(63,41)===0.U && UnifiedMoeRouteLayoutV2.expert(word)===job.group.expert &&
          UnifiedMoeRouteLayoutV2.row(word)===row && UnifiedMoeRouteLayoutV2.token(word)<job.context.tokens &&
          !UnifiedMoeRouteLayoutV2.weight(word)(15) && UnifiedMoeRouteLayoutV2.weight(word)<="h3f80".U
        when(good){token:=UnifiedMoeRouteLayoutV2.token(word);beat:=0.U;state:=activation}
        .otherwise{
          // Matched memory read itself retired. Semanticdescriptorerror is a
          // held failure, never a successfulpackedinput; no childDense started.
          poison:=true.B;result.status:=Status.Protocol.U;result.drained:=true.B
          result.acknowledgedWriteBytes:=written;state:=report
        }
      }.elsewhen(state===waitActivation){data:=io.response.bits.data;state:=write}
      .elsewhen(state===waitWrite){
        written:=written+64.U
        when(beat===63.U){
          when(row.pad(8)+1.U===job.group.groupRows){
            result.status:=Status.Ok.U;result.drained:=true.B;result.acknowledgedWriteBytes:=written+64.U;state:=report
          }.otherwise{row:=row+1.U;state:=descriptor}
        }.otherwise{beat:=beat+1.U;state:=activation}
      }
    }
  }
  when(io.done.fire){state:=idle}
  // Memoryreturns must be registered, minimum nextcycle afterrequest.fire.
  // An unknown/mismatched physicalreturn may neverdrain: parentwatchdog and
  // externalreset isolation are mandatory. Latefault cannotrewriteheldresult;
  // the common blockfinalfence must inspect stickyresetRequired separately.
}

/** Readonly common-top probe, never an injectionport or a secondtarget. Parent
  * connects these to the real job/memory/ACK/completion fires at fixedinterface;
  * synthetic and checkpoint phases keep the samehardware/probe definitions. */
class UnifiedMoeGatherObservationV2 extends Bundle {
  val jobFire=Bool();val job=new UnifiedMoeActivationGatherJobV2
  val memoryFire=Bool();val memory=new MemoryRequest
  val responseFire=Bool();val response=new MemoryResponse
  val doneValid=Bool();val doneFire=Bool();val done=new UnifiedMoeGatherCommitV2
  val resetRequired=Bool()
}
