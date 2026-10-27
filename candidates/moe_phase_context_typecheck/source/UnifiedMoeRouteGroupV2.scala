// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private ALLOCATOR output, never a public Host/config grant or commit Boolean.
  * Parent owns disjointness/lifetime against every other scratch/DDR region.
  * The current common top has not yet wired that allocator: leave this port
  * ungranted until the actual allocation source is connected and qualified. */
class UnifiedMoeRouteAllocationV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val metadataBase=UInt(64.W);val allocationEnd=UInt(64.W)
}
class UnifiedMoeSelectedRouteV2 extends Bundle {
  val transactionId=UInt(64.W)
  val token=UInt(16.W);val rank=UInt(4.W)
  val expert=UInt(9.W);val weight=UInt(16.W)
}
class UnifiedMoeExpertGroupV2 extends Bundle {
  val transactionId=UInt(64.W);val allocationSequence=UInt(64.W)
  val expert=UInt(8.W);val groupRows=UInt(8.W);val firstRoute=UInt(11.W)
  val descriptorBase=UInt(64.W)
}
class UnifiedMoeRouteCommitV2 extends Bundle {
  val transactionId=UInt(64.W);val allocationSequence=UInt(64.W)
  val metadataBase=UInt(64.W);val routes=UInt(11.W)
  val acknowledgedWriteBytes=UInt(32.W);val status=UInt(8.W);val drained=Bool()
}
object UnifiedMoeRouteLayoutV2 {
  val Bytes=16384;val MirrorOffset=8192;val Version=2
  // Reserved23 | token7 | rank3 | expert8 | weightBF16 | groupRow7.
  def pack(token:UInt,rank:UInt,expert:UInt,weight:UInt,row:UInt):UInt=
    Cat(0.U(23.W),token(6,0),rank(2,0),expert(7,0),weight(15,0),row(6,0))
  def row(x:UInt):UInt=x(6,0)
  def weight(x:UInt):UInt=x(22,7)
  def expert(x:UInt):UInt=x(30,23)
  def rank(x:UInt):UInt=x(33,31)
  def token(x:UInt):UInt=x(40,34)
}

/** M<=128, fixed256 experts/top8 route packing. Runtime profiles3/4 use exactly
  * these wires and capacities. No MAC/ALU/Matrix/vector/SFU/metadata SRAM is
  * instantiated. The explicit DDR allocation is16KiB; count/prefix registers
  * add256*(8+11)=4864bits (608B), plus one64bit descriptor and control/identity.
  * Counts also supply stable per-expert row indices, so no second cursor table.
  *
  * Input comes AFTER all256 softmax ->top8 ->sum/div ->BF16 materialization.
  * This owner does not compute logits/softmax or invent a routing tolerance.
  * Each token's8 unique experts arrive in rank order; expert256 shared is NOT
  * one of these8 and is scheduled separately for every token by the parent.
  *
  * A single original SharedMemoryArbiter owns global physical tags. This local
  * sequence is only a client tag; no local reset is safe without stale isolation.
  * Every partial8B write is acknowledged before credit/commit.
  * Memory responses are registered (minimum next cycle after request.fire). Bad/unknown
  * memory return holds reset-only quarantine: never fabricate a completed map.
  */
class UnifiedMoeRouteGroupV2 extends Module {
  val io=IO(new Bundle {
    val allocation=Flipped(Decoupled(new UnifiedMoeRouteAllocationV2))
    val route=Flipped(Decoupled(new UnifiedMoeSelectedRouteV2))
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool())
    val group=Decoupled(new UnifiedMoeExpertGroupV2)
    val done=Decoupled(new UnifiedMoeRouteCommitV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val states=Enum(13)
  val idle=states(0);val clear=states(1);val accept=states(2);val writeToken=states(3)
  val waitToken=states(4);val prefix=states(5);val readToken=states(6);val waitRead=states(7)
  val writeGrouped=states(8);val waitGrouped=states(9);val emit=states(10);val report=states(11);val locked=states(12)
  val state=RegInit(idle);val grant=Reg(new UnifiedMoeRouteAllocationV2)
  val lastTransaction=RegInit(0.U(64.W)) // one route-map owner per admitted block txn
  val haveLastTransaction=RegInit(false.B) // txn0 is valid before the first legal allocation.fire
  val counts=Reg(Vec(256,UInt(8.W)));val starts=Reg(Vec(256,UInt(11.W)))
  val cursor=Reg(UInt(8.W));val total=Reg(UInt(11.W));val index=Reg(UInt(11.W))
  val prefixTotal=Reg(UInt(11.W));val record=Reg(UInt(64.W))
  val selected=Reg(Vec(8,UInt(8.W)))
  val sequence=RegInit(0.U(64.W));val pendingTag=Reg(UInt(64.W))
  val writeBytes=RegInit(0.U(32.W));val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val finalResult=Reg(new UnifiedMoeRouteCommitV2)
  val waiting=state===waitToken || state===waitRead || state===waitGrouped
  val offered=state===writeToken || state===readToken || state===writeGrouped
  val unknown=io.response.valid && !waiting
  when(unknown || io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  io.resetRequired:=poison||quarantine||unknown||io.memoryResetRequired
  io.contextReserved:=state=/=idle || io.allocation.valid
  val (shape,known)=UnifiedRuntimeProfile.decode(io.allocation.bits.context.host.profileId)
  val c=io.allocation.bits.context;val base=io.allocation.bits.metadataBase
  val end=base.pad(65)+UnifiedMoeRouteLayoutV2.Bytes.U
  // Private phase metadata carries real postnorm/residual/final-output spans.
  // Geometry/echo is not an allocator capability or a full-block launch.
  val phaseViews=Seq(c.input,c.residual,c.output)
  val phaseViewsLegal=phaseViews.map(t=>t.dtype===5.U && t.rank===2.U &&
    t.dims(0)===c.tokens && t.dims(1)===2048.U && t.dims(2)===1.U && t.dims(3)===1.U &&
    t.elementCount===(c.tokens.pad(64)<<11) && t.payloadBytes===(c.tokens.pad(64)<<12) &&
    t.address=/=0.U && t.address(5,0)===0.U &&
    t.paddedEnd.pad(96)===t.address.pad(96)+t.payloadBytes.pad(96) &&
    t.paddedEnd<=(BigInt(1)<<56).U).reduce(_&&_)
  val aliasIO=phaseViews.map(t=>base.pad(96)<t.paddedEnd.pad(96) &&
    t.address.pad(96)<end.pad(96)).reduce(_||_)
  val legal=known && phaseViewsLegal && shape.asUInt===c.profile.asUInt && shape.mlp===1.U &&
    shape.expertCount===256.U && shape.expertsPerToken===8.U && shape.hidden===2048.U &&
    (!haveLastTransaction || c.transactionId>lastTransaction) && c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.host) &&
    c.tokens>=1.U && c.tokens<=128.U &&
    io.allocation.bits.allocationSequence=/=0.U &&
    base=/=0.U && base(5,0)===0.U && base>=c.host.regions(3).base &&
    end<=io.allocation.bits.allocationEnd.pad(65) && end<=(BigInt(1)<<56).U && !aliasIO &&
    sequence.pad(65)+(c.tokens.pad(65)*24.U)<=(BigInt(1)<<64).U-1.U
  io.allocation.ready:=state===idle && !io.resetRequired
  io.route.ready:=state===accept && !io.resetRequired
  io.memory.valid:=offered // Already offered memory packet NEVER withdraws on fault.
  val slot=Mux(state===writeGrouped,
    starts(UnifiedMoeRouteLayoutV2.expert(record))+UnifiedMoeRouteLayoutV2.row(record),index)
  val byteAddress=grant.metadataBase+Mux(state===writeGrouped,8192.U,0.U)+(slot.pad(64)<<3)
  io.memory.bits.address:=Cat(byteAddress(63,6),0.U(6.W))
  io.memory.bits.write:=state=/=readToken
  io.memory.bits.data:=(record.pad(512)<<(slot(2,0)<<6))(511,0)
  io.memory.bits.mask:=Mux(state===readToken,0.U,(255.U(64.W)<<(slot(2,0)<<3))(63,0))
  io.memory.bits.tag:=sequence
  io.response.ready:=waiting && !quarantine && !io.memoryResetRequired
  io.group.valid:=state===emit && counts(cursor)=/=0.U // held offer survives faults
  io.group.bits.transactionId:=grant.context.transactionId
  io.group.bits.allocationSequence:=grant.allocationSequence
  io.group.bits.expert:=cursor;io.group.bits.groupRows:=counts(cursor)
  io.group.bits.firstRoute:=starts(cursor)
  io.group.bits.descriptorBase:=grant.metadataBase+8192.U+(starts(cursor).pad(64)<<3)
  io.done.valid:=state===report;io.done.bits:=finalResult
  when(io.allocation.fire){
    grant:=io.allocation.bits;cursor:=0.U;index:=0.U;writeBytes:=0.U;prefixTotal:=0.U
    total:=c.tokens<<3
    finalResult:=0.U.asTypeOf(new UnifiedMoeRouteCommitV2)
    finalResult.transactionId:=c.transactionId
    finalResult.allocationSequence:=io.allocation.bits.allocationSequence
    finalResult.metadataBase:=base
    when(legal){lastTransaction:=c.transactionId;haveLastTransaction:=true.B;state:=clear}.otherwise{finalResult.status:=Status.Bounds.U;finalResult.drained:=true.B;state:=report}
  }
  when(state===clear && !io.resetRequired){
    counts(cursor):=0.U;starts(cursor):=0.U
    when(cursor===255.U){state:=accept}.otherwise{cursor:=cursor+1.U}
  }
  when(io.route.fire){
    val r=io.route.bits;val rank=index(2,0)
    val duplicate=(0 until 8).map(i=>i.U<rank && selected(i)===r.expert(7,0)).reduce(_||_)
    val good=r.transactionId===grant.context.transactionId && r.token===(index>>3) &&
      r.rank===rank && r.expert<256.U && !r.weight(15) && r.weight<="h3f80".U &&
      !duplicate && counts(r.expert(7,0))<grant.context.tokens && sequence=/="hffffffffffffffff".U
    when(good){
      selected(rank):=r.expert(7,0)
      record:=UnifiedMoeRouteLayoutV2.pack(r.token,rank,r.expert,r.weight,counts(r.expert(7,0)))
      state:=writeToken
    }.otherwise{
      // No memory pending at route admission. Already written prefixes are NOT
      // a valid map. Error held completion marks no successful route commit.
      finalResult.status:=Status.Protocol.U;finalResult.drained:=true.B
      finalResult.acknowledgedWriteBytes:=writeBytes;poison:=true.B;state:=report
    }
  }
  when(io.memory.fire){
    pendingTag:=sequence;sequence:=sequence+1.U
    when(state===writeToken){state:=waitToken}
    .elsewhen(state===readToken){state:=waitRead}
    .otherwise{state:=waitGrouped}
  }
  when(io.response.fire){
    when(io.response.bits.tag=/=pendingTag || io.response.bits.error){
      poison:=true.B;quarantine:=true.B // No fake count, next request, commit, or drain.
    }.otherwise{
      when(state===waitToken){
        val e=UnifiedMoeRouteLayoutV2.expert(record)
        counts(e):=counts(e)+1.U;writeBytes:=writeBytes+8.U
        when(index+1.U===total){cursor:=0.U;prefixTotal:=0.U;state:=prefix}
        .otherwise{index:=index+1.U;state:=accept}
      }.elsewhen(state===waitRead){
        val value=(io.response.bits.data>>(index(2,0)<<6))(63,0)
        val e=UnifiedMoeRouteLayoutV2.expert(value)
        val valid=value(63,41)===0.U && UnifiedMoeRouteLayoutV2.token(value)===(index>>3) &&
          UnifiedMoeRouteLayoutV2.rank(value)===index(2,0) &&
          UnifiedMoeRouteLayoutV2.row(value)<counts(e) &&
          !UnifiedMoeRouteLayoutV2.weight(value)(15) && UnifiedMoeRouteLayoutV2.weight(value)<="h3f80".U &&
          starts(e)+UnifiedMoeRouteLayoutV2.row(value)<total && sequence=/="hffffffffffffffff".U
        when(valid){record:=value;state:=writeGrouped}
        .otherwise{poison:=true.B;quarantine:=true.B}
      }.elsewhen(state===waitGrouped){
        writeBytes:=writeBytes+8.U
        when(index+1.U===total){cursor:=0.U;state:=emit}
        .otherwise{index:=index+1.U;state:=readToken}
      }
    }
  }
  when(state===prefix && !io.resetRequired){
    starts(cursor):=prefixTotal;prefixTotal:=prefixTotal+counts(cursor)
    when(cursor===255.U){
      when(prefixTotal+counts(cursor)===total && sequence=/="hffffffffffffffff".U){index:=0.U;state:=readToken}
      .otherwise{poison:=true.B;quarantine:=true.B}
    }.otherwise{cursor:=cursor+1.U}
  }
  when(state===emit && (counts(cursor)===0.U || io.group.fire)){
    when(io.resetRequired){state:=locked}
    .elsewhen(cursor===255.U){
      finalResult.routes:=total;finalResult.acknowledgedWriteBytes:=writeBytes
      finalResult.status:=Status.Ok.U;finalResult.drained:=true.B;state:=report
    }.otherwise{cursor:=cursor+1.U}
  }
  when(io.done.fire){state:=idle} // sticky poison still blocks a new allocation.
}
