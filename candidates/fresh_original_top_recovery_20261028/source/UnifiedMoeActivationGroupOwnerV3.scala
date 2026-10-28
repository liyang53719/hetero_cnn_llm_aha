// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private scheduler packet: gate/up receipts MUST be the real original Dense
  * fence outputs, not host-written successfulWriteback booleans. Parent binds
  * both accepted jobs/dst/fullcontext/ownerSequence and allocated output range.
  */
class UnifiedMoeActivationGroupJobV3 extends Bundle {
  val gate=new UnifiedMoeDenseWritebackV2;val up=new UnifiedMoeDenseWritebackV2
  val output=UInt(64.W);val allocationEnd=UInt(64.W);val ownerSequence=UInt(32.W)
}
class UnifiedMoeActivationGroupCommitV3 extends Bundle {
  val context=new HostMoePhaseContextV4;val expert=UInt(9.W);val groupRows=UInt(8.W)
  val output=UInt(64.W);val ownerSequence=UInt(32.W)
  val status=UInt(8.W);val acknowledgedWriteBytes=UInt(64.W);val drained=Bool()
  val scalarIssued=UInt(33.W);val scalarReturned=UInt(33.W)
  val formatIssued=UInt(33.W);val formatReturned=UInt(33.W)
}

/** ONE whole expert group (1..128 rows), not repeated completeblock M1.
  * Actual gate/up writeACK receipts -> DDR reads -> zeroALU logical32 consumer
  * -> DDR writes -> every real matched writeACK -> private activation commit.
  * The sole original MemoryArbiter supplies physical transport sequencing;
  * local tags here remain monotonic and are restored only for this client.
  *
  * This FUNCTIONAL source is not a32laneII1 engine, and must not become a
  * performance acceptance target. No Scalar/Vector/format/Dense is duplicated.
  * Same physical definition handles runtime profiles3/4; nonMoE arithmetic
  * continues through its original qualified owner until explicitly mapped.
  */
class UnifiedMoeActivationGroupOwnerV3 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new UnifiedMoeActivationGroupJobV3))
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val sourceResetRequired=Input(Bool())
    val done=Decoupled(new UnifiedMoeActivationGroupCommitV3)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val logicalTile=Output(UInt(11.W));val arithmeticLane=Output(UInt(5.W));val arithmeticNode=Output(UInt(3.W))
  })
  val core=Module(new UnifiedMoeLogical32SwiGluConsumerV3) // control/registers only; zeroALU
  io.scalar.request<>core.io.scalar.request;core.io.scalar.result<>io.scalar.result
  io.formatRequest<>core.io.formatRequest;core.io.formatResult<>io.formatResult
  val idle::prepareGate::prepareUp::offerMemory::waitMemory::startCore::waitCore::prepareWrite::report::locked::Nil=Enum(10)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeActivationGroupJobV3)
  val tile=Reg(UInt(11.W));val totalTiles=Reg(UInt(12.W));val kind=Reg(UInt(2.W))
  val gateData=Reg(UInt(512.W));val upData=Reg(UInt(512.W));val writeData=Reg(UInt(512.W))
  val mem=Reg(new MemoryRequest);val sequence=RegInit(0.U(64.W));val pendingTag=Reg(UInt(64.W))
  val out=Reg(new UnifiedMoeActivationGroupCommitV3)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknownMemory=io.response.valid && state=/=waitMemory
  val unknownCore=core.io.result.valid && state=/=waitCore
  when(unknownMemory||unknownCore||io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.sourceResetRequired){poison:=true.B}
  // No combinational resetRequired -> externalPoison -> resetRequired loop.
  core.io.externalPoison:=poison||io.sourceResetRequired||io.memoryResetRequired
  val fault=poison||quarantine||unknownMemory||unknownCore||io.memoryResetRequired||
    io.sourceResetRequired||core.io.resetRequired
  io.resetRequired:=fault;io.contextReserved:=state=/=idle||io.job.valid
  io.logicalTile:=tile;io.arithmeticLane:=core.io.lane;io.arithmeticNode:=core.io.node
  io.job.ready:=state===idle && !fault && !core.io.busy
  io.memory.valid:=state===offerMemory;io.memory.bits:=mem
  io.response.ready:=state===waitMemory && !quarantine && !io.memoryResetRequired
  // This private child handshake is Decoupled, not an Irrevocable physical
  // offer. Fault before start.fire has no child obligation to fabricate/drain.
  core.io.begin.valid:=state===startCore && !fault
  core.io.begin.bits.gate:=gateData;core.io.begin.bits.up:=upData
  core.io.result.ready:=state===waitCore && !quarantine
  io.done.valid:=state===report;io.done.bits:=out
  val in=io.job.bits;val g=in.gate;val u=in.up;val c=g.context
  val (p,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
  val bytes=g.groupRows.pad(96)*512.U*2.U
  val ge=g.output.pad(96)+bytes;val ue=u.output.pad(96)+bytes;val oe=in.output.pad(96)+bytes
  val disjoint= !(g.output.pad(96)<ue && u.output.pad(96)<ge) &&
    !(g.output.pad(96)<oe && in.output.pad(96)<ge) && !(u.output.pad(96)<oe && in.output.pad(96)<ue)
  val each=Seq(g,u).map(r=>r.successfulWriteback && r.result.status===Status.Ok.U &&
    r.result.tag===r.ownerSequence && r.result.writeBytes===bytes && r.ownerSequence=/="hffffffff".U).reduce(_&&_)
  val legal=known && c.profile.asUInt===p.asUInt && p.mlp===1.U && p.hidden===2048.U &&
    p.expertFfn===512.U && p.sharedFfn===512.U && p.expertCount===256.U && p.expertsPerToken===8.U &&
    c.version===HostMoePhaseContextV4.Version.U && c.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.host) &&
    c.tokens>=1.U && c.tokens<=128.U && g.expert<=256.U &&
    g.groupRows>=1.U && g.groupRows<=c.tokens && (g.expert=/=256.U || g.groupRows===c.tokens) &&
    u.context.asUInt===c.asUInt && u.expert===g.expert && u.groupRows===g.groupRows && g.stage===0.U && u.stage===1.U &&
    g.ownerSequence=/=u.ownerSequence && in.ownerSequence=/="hffffffff".U &&
    in.ownerSequence=/=g.ownerSequence && in.ownerSequence=/=u.ownerSequence && each && disjoint &&
    Seq(g.output,u.output,in.output).map(a=>a=/=0.U && a(5,0)===0.U).reduce(_&&_) &&
    Seq(ge,ue,oe).map(_<=(BigInt(1)<<56).U).reduce(_&&_) &&
    in.output>=c.host.regions(3).base && oe<=in.allocationEnd.pad(96) &&
    sequence.pad(65)+g.groupRows.pad(65)*48.U<=(BigInt(1)<<64).U-1.U
  def fail(status:UInt):Unit={
    poison:=true.B;out.status:=status
    val drained= !quarantine && !unknownMemory && !unknownCore && !core.io.quarantine
    out.drained:=drained;state:=Mux(drained,report,locked)
  }
  when(io.job.fire){
    job:=in;tile:=0.U;totalTiles:=g.groupRows.pad(12)<<4
    out:=0.U.asTypeOf(new UnifiedMoeActivationGroupCommitV3)
    out.context:=c;out.expert:=g.expert;out.groupRows:=g.groupRows
    out.output:=in.output;out.ownerSequence:=in.ownerSequence
    when(legal){state:=prepareGate}.otherwise{fail(Status.Dependency.U)}
  }
  when(state===prepareGate || state===prepareUp || state===prepareWrite){
    when(fault){fail(Status.Dependency.U)}.otherwise{
      mem:=0.U.asTypeOf(new MemoryRequest);mem.tag:=sequence
      mem.address:=Mux(state===prepareGate,job.gate.output,Mux(state===prepareUp,job.up.output,job.output))+(tile.pad(64)<<6)
      mem.write:=state===prepareWrite;mem.data:=writeData
      mem.mask:=Mux(state===prepareWrite,"hffffffffffffffff".U,0.U)
      kind:=Mux(state===prepareGate,0.U,Mux(state===prepareUp,1.U,2.U));state:=offerMemory
    }
  }
  when(io.memory.fire){pendingTag:=mem.tag;sequence:=sequence+1.U;state:=waitMemory}
  when(io.response.fire){
    when(io.response.bits.tag=/=pendingTag || io.response.bits.error){
      poison:=true.B;quarantine:=true.B;state:=locked // no false writecredit or drain
    }.otherwise{
      when(kind===2.U){out.acknowledgedWriteBytes:=out.acknowledgedWriteBytes+64.U}
      when(fault){fail(Status.Dependency.U)}.elsewhen(kind===0.U){gateData:=io.response.bits.data;state:=prepareUp}
      .elsewhen(kind===1.U){upData:=io.response.bits.data;state:=startCore}
      .otherwise{
        when(tile.pad(12)+1.U===totalTiles){
          val expectedScalars=job.gate.groupRows.pad(33)*3072.U
          val expectedFormats=job.gate.groupRows.pad(33)*1024.U
          val exact=out.acknowledgedWriteBytes+64.U===job.gate.groupRows.pad(64)*1024.U &&
            out.scalarIssued===expectedScalars && out.scalarReturned===expectedScalars &&
            out.formatIssued===expectedFormats && out.formatReturned===expectedFormats
          out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=true.B
          when(!exact){poison:=true.B};state:=report
        }.otherwise{tile:=tile+1.U;state:=prepareGate}
      }
    }
  }
  when(state===startCore && fault){fail(Status.Dependency.U)}
  when(core.io.begin.fire){state:=waitCore}
  when(core.io.result.fire){
    val r=core.io.result.bits
    out.scalarIssued:=out.scalarIssued+r.scalarIssued;out.scalarReturned:=out.scalarReturned+r.scalarReturned
    out.formatIssued:=out.formatIssued+r.formatIssued;out.formatReturned:=out.formatReturned+r.formatReturned
    when(!r.drained){poison:=true.B;quarantine:=true.B;state:=locked}
    .elsewhen(r.status=/=Status.Ok.U || fault){fail(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U))}
    .otherwise{writeData:=r.data;state:=prepareWrite}
  }
  when(io.done.fire){state:=Mux(fault,locked,idle)}
  // Real error may report acknowledged prefix bytes, but NEVER authorizes down.
  // Raw unknown/error memory needs external isolation; no synthetic completion.
  // Held commit stays immutable on late fault. Parent checks CURRENT poison
  // before creating a NEW down offer and at the final shared block fence.
}

object UnifiedMoeActivationDownPlanV3 {
  def decode(a:UnifiedMoeActivationGroupCommitV3,weight:UInt,dst:UInt,ownerSequence:UInt,
      currentResetRequired:Bool):
      (UnifiedMoeExpertDenseCommandV2,Bool)={
    val c=WireDefault(0.U.asTypeOf(new UnifiedMoeExpertDenseCommandV2))
    c.context:=a.context;c.expert:=a.expert;c.groupRows:=a.groupRows;c.stage:=2.U
    c.input:=a.output;c.weight:=weight;c.output:=dst;c.firstOwnerSequence:=ownerSequence
    val (_,legal)=UnifiedMoeExpertDenseCommandV2.decode(c)
    val eligible=legal && !currentResetRequired && a.status===Status.Ok.U && a.drained &&
      a.acknowledgedWriteBytes===a.groupRows.pad(64)*1024.U &&
      a.scalarIssued===a.groupRows.pad(33)*3072.U && a.scalarReturned===a.scalarIssued &&
      a.formatIssued===a.groupRows.pad(33)*1024.U && a.formatReturned===a.formatIssued &&
      ownerSequence=/=a.ownerSequence
    // The fault argument MUST be the live source/memory/global sticky OR, not
    // a host field. Receipt origin still requires the real done.fire ledger.
    // Evaluate eligibility before creating a NEW offer; an already held Dense
    // offer remains stable and follows the parent's drain/isolation protocol.
    (c,eligible)
  }
}
