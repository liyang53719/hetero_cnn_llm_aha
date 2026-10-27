// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE actual routed/shared/sigmoid retirements, all bound to one retained
  * parent allocation/epoch. Matching copied bits do not supply these events. */
class UnifiedMoePhaseMergeRunV5 extends Bundle {
  val lease=new HostMoeRuntimePhaseLeaseV5
  val routed=new HostMoeRoutedPhaseResultV5
  val shared=new UnifiedMoeFfnGroupResultV3
  val sigmoid=new UnifiedMoeSharedSigmoidCommitV5
}
class UnifiedMoePhaseMergeCommitV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val ownerSequence=UInt(32.W);val output=UInt(64.W)
  val completedTokens=UInt(16.W);val completedTiles=UInt(14.W);val acknowledgedWriteBytes=UInt(64.W)
  val vectorIssued=UInt(33.W);val vectorReturned=UInt(33.W)
  val metadataIssued=UInt(11.W);val metadataReturned=UInt(11.W)
  val dataIssued=UInt(17.W);val dataReturned=UInt(17.W)
  val writerIssued=UInt(14.W);val writerReturned=UInt(14.W)
  val status=UInt(8.W);val drained=Bool()
}

/** Whole-M hidden-output merge owner. ZERO numerical engines. Real token map
  * and eight descriptor reads happen once per token, retained across64 tiles.
  * The ninth shared weight is read from actual packed sigmoid DDR, not1 or a
  * Host payload. Each actual nine-source tile result is written and ACKed
  * before advancing. No allocation is released here; residual/final fence is
  * separate. The three logical memory clients share the parent's ONE physical
  * SharedMemoryArbiter with nonreused physical tags; local tags are not global.
  * Vector uses ONE whole-phase owner1287 with full V3 serial/epoch matching in
  * the parent. Logical token/tile identities below are real retained side-ledger
  * state, not an immutable per-tile V2 lease or a new physical32-II1 resource.
  */
class UnifiedMoePhaseMergeOwnerV5 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoePhaseMergeRunV5))
    val metadataMemory=Decoupled(new MemoryRequest);val metadataResponse=Flipped(Decoupled(new MemoryResponse))
    val metadataResetRequired=Input(Bool())
    val dataMemory=Decoupled(new MemoryRequest);val dataResponse=Flipped(Decoupled(new MemoryResponse))
    val dataResetRequired=Input(Bool())
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val externalPoison=Input(Bool()) // registered sticky
    val vectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    val done=Decoupled(new UnifiedMoePhaseMergeCommitV5)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val token=Output(UInt(8.W));val tileOrdinal=Output(UInt(6.W));val vectorOrdinal=Output(UInt(33.W))
  })
  val selection=Module(new UnifiedMoeRoutedSelectionReaderV5)
  val tile=Module(new UnifiedMoePhaseTileMergePortsV5)
  io.metadataMemory<>selection.io.memory;selection.io.response<>io.metadataResponse
  io.dataMemory<>tile.io.memory;tile.io.response<>io.dataResponse
  io.vectorRequest<>tile.io.vectorRequest;tile.io.vectorResult<>io.vectorResult
  selection.io.memoryResetRequired:=io.metadataResetRequired;tile.io.memoryResetRequired:=io.dataResetRequired
  val states=Enum(11)
  val idle=states(0);val prepareWeight=states(1);val startSelection=states(2);val waitSelection=states(3)
  val startTile=states(4);val waitTile=states(5);val prepareWrite=states(6)
  val offerMemory=states(7);val waitMemory=states(8);val report=states(9);val locked=states(10)
  val state=RegInit(idle);val job=Reg(new UnifiedMoePhaseMergeRunV5)
  val token=Reg(UInt(8.W));val tileIndex=Reg(UInt(6.W))
  val selected=Reg(new UnifiedMoeRoutedSelectionV5)
  val weightCache=Reg(UInt(512.W));val writeData=Reg(UInt(512.W))
  val mem=Reg(new MemoryRequest);val writeKind=Reg(Bool());val tag=Reg(UInt(64.W))
  val sequence=RegInit(0.U(64.W));val out=Reg(new UnifiedMoePhaseMergeCommitV5)
  val metadataBefore=Reg(UInt(11.W));val dataBefore=Reg(UInt(17.W));val vectorBefore=Reg(UInt(33.W))
  val haveLast=RegInit(false.B);val lastTransaction=Reg(UInt(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknownMemory=io.response.valid && state=/=waitMemory
  val unknownSelection=selection.io.result.valid && state=/=waitSelection
  val unknownTile=tile.io.result.valid && state=/=waitTile
  val anyMemoryReset=io.memoryResetRequired||io.metadataResetRequired||io.dataResetRequired
  when(unknownMemory||unknownSelection||unknownTile||anyMemoryReset){poison:=true.B;quarantine:=true.B}
  when(io.externalPoison||selection.io.resetRequired||tile.io.resetRequired){poison:=true.B}
  selection.io.currentFault:=poison||io.externalPoison
  tile.io.externalPoison:=poison||io.externalPoison
  val fault=poison||quarantine||unknownMemory||unknownSelection||unknownTile||anyMemoryReset||
    io.externalPoison||selection.io.resetRequired||tile.io.resetRequired
  io.resetRequired:=fault
  io.contextReserved:=state=/=idle||io.begin.valid||selection.io.contextReserved||tile.io.contextReserved
  io.begin.ready:=state===idle && !fault
  io.token:=token;io.tileOrdinal:=tileIndex;io.vectorOrdinal:=out.vectorIssued
  io.memory.valid:=state===offerMemory;io.memory.bits:=mem
  io.response.ready:=state===waitMemory && !quarantine && !io.memoryResetRequired
  io.done.valid:=state===report;io.done.bits:=out
  selection.io.job.bits:=UnifiedMoeRoutedReadJobV5.fromActualRoutedRetirement(job.lease,job.routed,token.pad(32))
  selection.io.result.ready:=state===waitSelection && !quarantine
  tile.io.begin.valid:=state===startTile && !fault
  tile.io.result.ready:=state===waitTile && !quarantine
  val proposedTile=WireDefault(0.U.asTypeOf(new UnifiedMoeNineDownReadJobV5))
  proposedTile.context:=job.lease.context;proposedTile.allocationSequence:=job.lease.allocationSequence
  proposedTile.identity.transactionId:=job.lease.context.transactionId
  proposedTile.identity.token:=token;proposedTile.identity.tileOrdinal:=tileIndex
  for(i<-0 until 8){
    proposedTile.routes(i).expert:=selected.routes(i).expert
    proposedTile.routes(i).output:=selected.routes(i).output
    proposedTile.routes(i).ownerSequence:=selected.routes(i).ownerSequence
    proposedTile.routes(i).groupRows:=selected.routes(i).groupRows
    proposedTile.routes(i).groupRow:=selected.routes(i).groupRow
    proposedTile.routes(i).weight:=selected.routes(i).weight
  }
  val sharedWeight=(weightCache>>(token(4,0)<<4))(15,0)
  proposedTile.routes(8).expert:=256.U;proposedTile.routes(8).output:=job.lease.sharedDown
  proposedTile.routes(8).ownerSequence:=job.shared.down.ownerSequence
  proposedTile.routes(8).groupRows:=job.lease.context.tokens
  proposedTile.routes(8).groupRow:=token(6,0);proposedTile.routes(8).weight:=sharedWeight
  tile.io.begin.bits:=proposedTile
  val in=io.begin.bits;val l=in.lease;val c=l.context;val sg=in.sigmoid
  val (_,routedLegal)=UnifiedMoeSharedFfnPlanV5.fromActualRoutedRetirement(l,in.routed)
  val (n1Source,n1Exact)=HostMoeSharedGatePlanV5.fromActualDense(l,sg.source.image,sg.source.acceptedJob,sg.source.result)
  val sigmoidExact=sg.context.asUInt===c.asUInt && sg.allocationSequence===l.allocationSequence &&
    sg.source.asUInt===n1Source.asUInt && n1Exact && sg.ownerSequence.pad(33)===l.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.SharedSigmoid.U &&
    sg.output===l.upOutput && sg.rows===c.tokens && sg.status===Status.Ok.U && sg.drained &&
    sg.acknowledgedWriteBytes===(c.tokens.pad(64)<<1) && sg.scalarIssued===(c.tokens.pad(33)<<2) &&
    sg.scalarReturned===sg.scalarIssued && sg.formatIssued===c.tokens && sg.formatReturned===sg.formatIssued &&
    sg.memoryIssued===c.tokens.pad(9)+((c.tokens.pad(9)+31.U)>>5) && sg.memoryReturned===sg.memoryIssued
  val expectedWrites=c.tokens.pad(65)<<6
  val writerBudget=expectedWrites+((c.tokens.pad(65)+31.U)>>5)
  val legal=UnifiedMoeRuntimeLeaseGeometryV4.legal(l) && routedLegal &&
    UnifiedMoeSharedFfnPlanV5.completed(l,in.shared) && sigmoidExact &&
    l.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W) &&
    sequence.pad(65)+writerBudget<=(BigInt(1)<<64).U-1.U &&
    (!haveLast || c.transactionId>lastTransaction)
  def fail(status:UInt,drained:Bool):Unit={poison:=true.B;out.status:=status;out.drained:=drained;state:=report}
  val cleanLocal= !quarantine && !unknownMemory && !unknownSelection && !unknownTile && !anyMemoryReset &&
    !selection.io.resetRequired && !tile.io.resetRequired
  when(io.begin.fire){
    job:=in;token:=0.U;tileIndex:=0.U;out:=0.U.asTypeOf(new UnifiedMoePhaseMergeCommitV5)
    out.context:=c;out.allocationSequence:=l.allocationSequence
    out.ownerSequence:=l.firstOwnerSequence+HostMoeOwnerRangeV5.Merge.U;out.output:=l.mergedOutput
    when(legal){haveLast:=true.B;lastTransaction:=c.transactionId;state:=prepareWeight}
    .otherwise{fail(Status.Dependency.U,true.B)}
  }
  when(state===prepareWeight || state===prepareWrite){
    when(fault){fail(Status.Dependency.U,cleanLocal)}.otherwise{
      mem:=0.U.asTypeOf(new MemoryRequest);mem.tag:=sequence
      mem.address:=Mux(state===prepareWeight,job.sigmoid.output+((token.pad(64)>>5)<<6),
        job.lease.mergedOutput+(token.pad(64)<<12)+(tileIndex.pad(64)<<6))
      mem.write:=state===prepareWrite;mem.data:=Mux(state===prepareWrite,writeData,0.U)
      mem.mask:=Mux(state===prepareWrite,"hffffffffffffffff".U,0.U)
      writeKind:=state===prepareWrite;state:=offerMemory
    }
  }
  when(io.memory.fire){tag:=mem.tag;sequence:=sequence+1.U;out.writerIssued:=out.writerIssued+1.U;state:=waitMemory}
  when(io.response.fire){
    when(io.response.bits.tag=/=tag || io.response.bits.error){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
    .otherwise{
      out.writerReturned:=out.writerReturned+1.U
      when(writeKind){out.acknowledgedWriteBytes:=out.acknowledgedWriteBytes+64.U}
      when(fault){fail(Status.Dependency.U,cleanLocal)}
      .elsewhen(!writeKind){weightCache:=io.response.bits.data;state:=startSelection}
      .otherwise{
        out.completedTiles:=out.completedTiles+1.U
        when(tileIndex===63.U){
          out.completedTokens:=out.completedTokens+1.U
          when(token.pad(16)+1.U===job.lease.context.tokens){
            val m=job.lease.context.tokens;val tiles=m.pad(33)<<6
            val exact=out.completedTiles.pad(33)+1.U===tiles && out.completedTokens+1.U===m &&
              out.acknowledgedWriteBytes+64.U===(m.pad(64)<<12) &&
              out.vectorIssued===tiles*36.U && out.vectorReturned===out.vectorIssued &&
              out.metadataIssued===m.pad(11)*9.U && out.metadataReturned===out.metadataIssued &&
              out.dataIssued===tiles*9.U && out.dataReturned===out.dataIssued &&
              out.writerIssued===tiles+((m.pad(33)+31.U)>>5) && out.writerReturned+1.U===out.writerIssued
            out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=exact
            when(!exact){poison:=true.B};state:=report
          }.otherwise{
            token:=token+1.U;tileIndex:=0.U
            state:=Mux(token(4,0)===31.U,prepareWeight,startSelection)
          }
        }.otherwise{tileIndex:=tileIndex+1.U;state:=startTile}
      }
    }
  }
  when(state===startSelection){
    when(fault){fail(Status.Dependency.U,cleanLocal)}
    .elsewhen(sharedWeight(15)||sharedWeight>"h3f80".U){fail(Status.Numerical.U,true.B)}
  }
  // Source invalidity above must block the same-edge private child handshake.
  selection.io.job.valid:=state===startSelection && !fault && !sharedWeight(15) && sharedWeight<="h3f80".U
  when(selection.io.job.fire){metadataBefore:=out.metadataIssued;state:=waitSelection}
  when(io.metadataMemory.fire){out.metadataIssued:=out.metadataIssued+1.U}
  when(selection.io.result.fire){
    val r=selection.io.result.bits
    val exact=r.context.asUInt===job.lease.context.asUInt && r.allocationSequence===job.lease.allocationSequence &&
      r.token===token && r.readIssued.pad(11)===out.metadataIssued-metadataBefore && r.readReturned===r.readIssued
    when(!exact || !r.drained){quarantine:=true.B;fail(Status.Protocol.U,false.B)}.otherwise{
      out.metadataReturned:=out.metadataReturned+r.readReturned
      when(r.status=/=Status.Ok.U || fault){fail(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U),cleanLocal)}
      .elsewhen(r.readIssued=/=9.U){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
      .otherwise{selected:=r;state:=startTile}
    }
  }
  when(state===startTile && fault){fail(Status.Dependency.U,cleanLocal)}
  when(tile.io.begin.fire){dataBefore:=out.dataIssued;vectorBefore:=out.vectorIssued;state:=waitTile}
  when(io.dataMemory.fire){out.dataIssued:=out.dataIssued+1.U}
  when(io.vectorRequest.fire){out.vectorIssued:=out.vectorIssued+1.U}
  when(tile.io.result.fire){
    val r=tile.io.result.bits
    val exact=r.identity.asUInt===proposedTile.identity.asUInt && r.allocationSequence===job.lease.allocationSequence &&
      r.accepted===r.issued && r.returned===r.issued && r.issued.pad(33)===out.vectorIssued-vectorBefore &&
      out.dataIssued-dataBefore===9.U
    when(!exact || !r.drained){quarantine:=true.B;fail(Status.Protocol.U,false.B)}.otherwise{
      out.vectorReturned:=out.vectorReturned+r.returned;out.dataReturned:=out.dataReturned+9.U
      when(r.status=/=Status.Ok.U || fault){fail(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U),cleanLocal)}
      .elsewhen(r.issued=/=36.U){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
      .otherwise{writeData:=r.data;state:=prepareWrite}
    }
  }
  when(io.done.fire){state:=Mux(fault|| !out.drained,locked,idle)}
  // Held done never mutates due to late fault. Parent must gate NEW residual
  // offers and eventual allocation/phase/block release with current poison and
  // true global drain. Unknown/missing debts may require externally isolated
  // reset, not fake completion. Child/physical raw offers are never withdrawn.
}
