// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE join of the actual token selection reader.result.fire, actual shared
  * FFN down-writeback.fire, and actual sigmoid-weight DDR read. The parent must
  * bind all three to one retained allocation/phase and reject current faults.
  * These compact fields are NOT fabricated QwenOwnerResult receipts and are not
  * a host grant. Full typed shared/N1 source and lifetime remain mandatory.
  */
class UnifiedMoeNineDownRouteV5 extends Bundle {
  val expert=UInt(9.W);val output=UInt(64.W);val ownerSequence=UInt(32.W)
  val groupRows=UInt(8.W);val groupRow=UInt(7.W);val weight=UInt(16.W)
}
class UnifiedMoeNineDownReadJobV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val identity=new MoeBf16TileIdentity
  val routes=Vec(9,new UnifiedMoeNineDownRouteV5)
}
class UnifiedMoeDownReadDoneV5 extends Bundle {
  val identity=new MoeBf16TileIdentity;val allocationSequence=UInt(64.W)
  val status=UInt(8.W);val returned=UInt(4.W);val drained=Bool()
}

/** Real 64-byte DDR read -> producer's actual route-tagged result payload.
  * No host data512, arithmetic, expert payload SRAM or transport-tag allocator.
  * This is a client of the original SINGLE SharedMemoryArbiter; that arbiter
  * owns cross-client/cross-job physical sequence and original-tag restoration.
  *
  * Captures only selected9 descriptors. The full128x8 route map and expert
  * commit table now come from the separate actual routed-selection DDR reader;
  * this payload reader does not invent the still-required shared/N1 producer.
  * Current capture repeats metadata per tile (no performance claim). */
class UnifiedMoeDownTileReaderV5 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new UnifiedMoeNineDownReadJobV5))
    val route=Decoupled(new UnifiedTaggedMoeRouteV5)
    val dispatch=Flipped(Decoupled(new UnifiedTaggedMoeDispatchV5))
    val returned=Decoupled(new UnifiedTaggedMoeReturnV5)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val currentFault=Input(Bool())
    val done=Decoupled(new UnifiedMoeDownReadDoneV5)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool());val jobLegal=Output(Bool())
  })
  val idle::routes::dispatch::offer::waitRead::returnData::report::locked::Nil=Enum(8)
  val state=RegInit(idle);val identity=Reg(new MoeBf16TileIdentity)
  val allocation=Reg(UInt(64.W));val sequence=RegInit(0.U(64.W))
  // 9 compact selected descriptors, NOT nine expert tensor payloads.
  val bases=Reg(Vec(9,UInt(64.W)));val row=Reg(Vec(9,UInt(7.W)))
  val experts=Reg(Vec(9,UInt(9.W)));val weights=Reg(Vec(9,UInt(16.W)))
  val hidden=Reg(UInt(16.W));val routeIndex=Reg(UInt(4.W));val returned=RegInit(0.U(4.W))
  val pendingTag=Reg(UInt(4.W));val mem=Reg(new MemoryRequest)
  val data=Reg(UInt(512.W));val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val out=Reg(new UnifiedMoeDownReadDoneV5)
  val c=io.job.bits.context
  val (p,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
  val common=known && p.asUInt===c.profile.asUInt && p.mlp===1.U &&
    p.expertCount===256.U && p.expertsPerToken===8.U && p.hidden===2048.U &&
    c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U &&
    HostCommandLaunchV4.known(c.host) && c.tokens>=1.U && c.tokens<=128.U &&
    io.job.bits.allocationSequence=/=0.U && io.job.bits.identity.transactionId===c.transactionId &&
    io.job.bits.identity.token<c.tokens && io.job.bits.identity.tileOrdinal<(p.hidden>>5) &&
    sequence.pad(65)+9.U<=(BigInt(1)<<64).U-1.U
  val each=(0 until 9).map{i=>
    val d=io.job.bits.routes(i)
    val expectedBytes=d.groupRows.pad(64)*p.hidden*2.U
    val end=d.output.pad(96)+expectedBytes
    val unique=(0 until i).map{j=>
      val old=io.job.bits.routes(j)
      val oldEnd=old.output.pad(96)+(old.groupRows.pad(96)*p.hidden<<1)
      old.expert=/=d.expert && old.ownerSequence=/=d.ownerSequence &&
        !(d.output.pad(96)<oldEnd && old.output.pad(96)<end)
    }.foldLeft(true.B)(_&&_)
    d.groupRows>=1.U && d.groupRows<=c.tokens && d.groupRow<d.groupRows &&
      d.output=/=0.U && d.output(5,0)===0.U && end<=(BigInt(1)<<56).U &&
      d.ownerSequence=/="hffffffff".U && unique && !d.weight(15) && d.weight<="h3f80".U &&
      (if(i==8)d.expert===256.U && d.groupRows===c.tokens && d.groupRow===io.job.bits.identity.token
       else d.expert<256.U)
  }.reduce(_&&_)
  io.jobLegal:=common && each
  // Raw unknown memory responses are reset-only quarantine. Do not issue a new
  // read while an old valid can become mislabelled; preserve an already-offered
  // request but never grant that old response its newly accepted credit.
  val unknownReply=io.response.valid && state=/=waitRead
  when(unknownReply){poison:=true.B;quarantine:=true.B}
  when(io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.currentFault){poison:=true.B}
  io.job.ready:=state===idle && !poison && !io.memoryResetRequired && !io.currentFault && !io.response.valid
  io.resetRequired:=poison||quarantine||io.memoryResetRequired||unknownReply||io.currentFault
  io.contextReserved:=state=/=idle || io.job.valid
  io.route.valid:=state===routes
  io.route.bits.identity:=identity;io.route.bits.allocationSequence:=allocation;io.route.bits.payload.expert:=experts(routeIndex)
  io.route.bits.payload.weight:=Cat(0.U(16.W),weights(routeIndex));io.route.bits.payload.shared:=routeIndex===8.U
  io.dispatch.ready:=state===dispatch && !quarantine && !io.memoryResetRequired && !io.response.valid
  io.memory.valid:=state===offer;io.memory.bits:=mem
  io.response.ready:=state===waitRead && !quarantine && !io.memoryResetRequired
  io.returned.valid:=state===returnData;io.returned.bits.identity:=identity;io.returned.bits.allocationSequence:=allocation
  io.returned.bits.payload.routeTag:=pendingTag;io.returned.bits.payload.data:=data
  io.done.valid:=state===report;io.done.bits:=out
  when(io.job.fire){
    identity:=io.job.bits.identity;allocation:=io.job.bits.allocationSequence;hidden:=p.hidden;returned:=0.U;routeIndex:=0.U
    out:=0.U.asTypeOf(new UnifiedMoeDownReadDoneV5);out.identity:=io.job.bits.identity;out.allocationSequence:=io.job.bits.allocationSequence
    for(i<-0 until 9){bases(i):=io.job.bits.routes(i).output;row(i):=io.job.bits.routes(i).groupRow
      experts(i):=io.job.bits.routes(i).expert;weights(i):=io.job.bits.routes(i).weight}
    when(common && each){state:=routes}.otherwise{out.status:=Status.Dependency.U;out.drained:=true.B;state:=report}
  }
  when(io.route.fire){when(routeIndex===8.U){state:=dispatch}.otherwise{routeIndex:=routeIndex+1.U}}
  when(io.dispatch.fire){
    val d=io.dispatch.bits;val t=d.payload.routeTag;val safe=Mux(t<9.U,t,0.U)
    val matches=d.identity.asUInt===identity.asUInt && d.allocationSequence===allocation && t===returned && t<9.U &&
      d.payload.token===identity.token && d.payload.expert===experts(safe) &&
      d.payload.weight===Cat(0.U(16.W),weights(safe)) && d.payload.shared===(t===8.U) && d.payload.last===(t===8.U)
    when(!matches){poison:=true.B;state:=locked}.otherwise{
      pendingTag:=t;mem:=0.U.asTypeOf(new MemoryRequest)
      mem.address:=bases(safe)+(row(safe).pad(64)*hidden<<1)+(identity.tileOrdinal.pad(64)<<6)
      // Nonreused client-local sequence; physical arbiter replaces it with its global
      // nonreused transport sequence and restores it only to this owner.
      mem.tag:=sequence
      state:=offer
    }
  }
  when(io.memory.fire){sequence:=sequence+1.U;state:=waitRead}
  when(io.response.fire){
    when(io.response.bits.error || io.response.bits.tag=/=mem.tag || io.memoryResetRequired){
      poison:=true.B;quarantine:=true.B;state:=locked
    }.otherwise{data:=io.response.bits.data;state:=returnData}
  }
  when(io.returned.fire){
    returned:=returned+1.U
    when(returned===8.U){out.status:=Mux(io.resetRequired,Status.Protocol.U,Status.Ok.U);out.returned:=9.U;out.drained:= !quarantine && !unknownReply && !io.memoryResetRequired;state:=report}
      .otherwise{state:=dispatch}
  }
  when(io.done.fire){state:=Mux(io.resetRequired,locked,idle)}
  // Ordinary currentFault marks poison but allows already-started valid
  // dispatch/read/return obligations to drain; no new job can start. Unknown
  // attribution or memory reset remains quarantine and never grants credit.
  // Existing HeteroMoeResult has no error field. Never turn a failed DDR read
  // into zero data posing as a valid expert. Failed reads expose sticky fault,
  // leave the producer dispatch obligation unretired, and require parent
  // watchdog/isolation. There is no invented bounded failure/drain completion.
}
