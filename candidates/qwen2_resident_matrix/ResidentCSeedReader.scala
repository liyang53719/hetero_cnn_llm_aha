// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** WORK-ONLY: the proposed resident 1024-word A/C + 512-word B partition.
  * These are owner-local wires, not Host commands or a DDR/SharedL2 protocol.
  */
class ResidentSeedShape extends Bundle {
  val m=UInt(8.W)
  val n=UInt(16.W)
  val k=UInt(16.W)
}

class ResidentSeedDescriptor extends Bundle {
  val seed=new MatrixAccumulatorSeedRequest
  val slot=UInt(2.W)
  val tileRow=UInt(3.W)
  val nBase=UInt(16.W)
  val prefixK=UInt(16.W)
}

class ResidentSeedLookup extends Bundle {
  val slot=UInt(2.W)
  val tileRow=UInt(3.W)
}

/** Direct selected owner state, never metadata supplied by the command.
  * committed is set only after all physical prefix writes acknowledge.
  * leaseHeld refers to THIS lookup and descriptor identity. Owner holds it
  * until release, or indefinitely after quarantine until coordinated reset.
  */
class ResidentSeedOwnerMetadata extends Bundle {
  val committed=Bool()
  val prefixK=UInt(16.W)
  val ownerN=UInt(16.W)
  val generation=UInt(32.W)
  val leaseHeld=Bool()
}

/** Bounded actual synchronous-SRAM reader, without SRAM or arithmetic.
  * One 512-bit assembly register, two back-to-back same-bank 256-bit reads.
  * readEnable at cycle t means readData is sampled at cycle t+1. No ready,
  * variable latency, return tag, or imaginary second bank port is assumed.
  * grant/drain/acquire must be wired to the real resident owner, not constants.
  */
class ResidentCSeedReader extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new ResidentSeedDescriptor))
    val shape=Input(new ResidentSeedShape)
    val lookup=Output(new ResidentSeedLookup)
    val metadata=Input(new ResidentSeedOwnerMetadata)
    val acquire=Decoupled(new ResidentSeedDescriptor)
    val release=Valid(new ResidentSeedDescriptor)
    val quarantine=Valid(new ResidentSeedDescriptor)
    // ownerReady is false until owner/array reset and old responses drain.
    // A reader-only reset is NOT permission to clear owner leases/generations.
    val ownerReady=Input(Bool())
    val legacyDrained=Input(Bool())
    val portsGranted=Input(Bool())
    val abort=Input(Bool())
    val terminalReady=Input(Bool())
    val seed=new MatrixAccumulatorSeedPort
    val controllerCommitted=Flipped(Valid(new MatrixAccumulatorSeedRequest))
    val controllerResetRequired=Input(Bool())
    val completed=Valid(new ResidentSeedDescriptor)
    val abortController=Output(Bool())
    val resetRequired=Output(Bool())
    // Stop NEW legacy SRAM reads immediately; existing operand FIFO and matrix
    // work must still drain. This is not the controller's blockIssue signal.
    val stopLegacyReads=Output(Bool())
    val leasePinned=Output(Bool())
    val readEnable=Output(Bool())
    val readBank=Output(UInt(4.W))
    val readAddress=Output(UInt(10.W))
    val readData=Input(UInt(256.W))
  })

  val idle::acquiring::begin::readLow::captureLow::captureHigh::offer::waitAck::locked::Nil=Enum(9)
  val state=RegInit(idle)
  val descriptor=Reg(new ResidentSeedDescriptor)
  val shape=Reg(new ResidentSeedShape)
  val payload=Reg(UInt(512.W)) // the sole numerical payload storage
  val beatIndex=RegInit(0.U(8.W))
  val slice=RegInit(0.U(3.W))
  val cluster=RegInit(0.U(5.W))
  val pinned=RegInit(false.B)
  val began=RegInit(false.B)
  val ackSeen=RegInit(false.B)
  val poison=RegInit(false.B)
  val req=descriptor.seed
  val active=state=/=idle && state=/=locked
  val remainingRows=shape.m.pad(17)-(descriptor.tileRow.pad(17)<<4)
  val remainingCols=shape.n.pad(17)-descriptor.nBase.pad(17)
  val rows=Mux(remainingRows<16.U,remainingRows,16.U)
  val cols=Mux(remainingCols<256.U,remainingCols,256.U)
  val expectedMask=VecInit((0 until 8).map(i=>(i*32).U<cols)).asUInt
  val fullA=shape.k<=1536.U
  val cBase=Mux(fullA,shape.k>>1,128.U)
  val slots=Mux(fullA,1.U,3.U)
  val geometryLegal=shape.m>0.U && shape.m<=128.U && shape.n>0.U && shape.k>0.U &&
    shape.n(3,0)===0.U && shape.k(3,0)===0.U &&
    (descriptor.tileRow.pad(17)<<4)<shape.m && descriptor.nBase<shape.n &&
    descriptor.nBase(7,0)===0.U && descriptor.prefixK>0.U && descriptor.prefixK<shape.k &&
    descriptor.prefixK(7,0)===0.U && descriptor.slot<slots &&
    cBase.pad(18)+(slots.pad(18)<<8)<=1024.U &&
    req.context<5.U && req.sliceMask===expectedMask && req.sourceGeneration=/=0.U
  val metadataLegal=io.metadata.committed && io.metadata.prefixK===descriptor.prefixK &&
    io.metadata.ownerN===descriptor.nBase && io.metadata.generation===req.sourceGeneration
  val shapeStable=io.shape.asUInt===shape.asUInt
  val sourceFault=active && (io.abort || !io.ownerReady || !shapeStable ||
    (pinned && (!metadataLegal || !io.metadata.leaseHeld || !io.portsGranted || !io.legacyDrained)))
  val unexpectedAck=io.seed.ack.valid && (!began || ackSeen)
  // No combinational dependence on controllerCommitted here: its committed
  // pulse itself depends on !abort at the successful terminal ACK handshake.
  io.abortController:=poison || sourceFault || unexpectedAck
  val usable= !poison && !sourceFault && !unexpectedAck && !io.controllerResetRequired
  io.resetRequired:=poison || io.controllerResetRequired
  io.stopLegacyReads:=io.start.valid || state=/=idle || io.resetRequired
  io.leasePinned:=pinned
  io.start.ready:=state===idle && !io.resetRequired && !io.abort && io.ownerReady && !io.seed.ack.valid
  io.lookup.slot:=Mux(state===idle,io.start.bits.slot,descriptor.slot)
  io.lookup.tileRow:=Mux(state===idle,io.start.bits.tileRow,descriptor.tileRow)
  io.acquire.bits:=descriptor
  io.acquire.valid:=state===acquiring && usable && geometryLegal && metadataLegal &&
    !io.metadata.leaseHeld && io.legacyDrained
  io.seed.begin.valid:=state===begin && usable
  io.seed.begin.bits:=req
  io.seed.beat.valid:=state===offer && usable
  io.seed.beat.bits.groupTag:=req.groupTag
  io.seed.beat.bits.groupSequence:=req.groupSequence
  io.seed.beat.bits.sourceGeneration:=req.sourceGeneration
  io.seed.beat.bits.context:=req.context
  io.seed.beat.bits.index:=beatIndex
  io.seed.beat.bits.data:=payload
  val laterSlices=VecInit((0 until 8).map(i=>req.sliceMask(i) && i.U>slice)).asUInt
  io.seed.beat.bits.last:=cluster===31.U && !laterSlices.orR
  io.seed.beat.bits.error:=false.B // SyncReadMem has no transport-error wire
  // Drain a controller failure even before the reader reaches waitAck. In
  // locked, consume at most the already accepted begin's terminal response.
  io.seed.ack.ready:=began && !ackSeen && io.terminalReady

  val row=cluster(4,1)
  val firstCol=Cat(slice,cluster(0),0.U(4.W))
  val liveBeat=row<rows && firstCol<cols
  val baseAddress=cBase.pad(18)+(descriptor.slot.pad(18)<<8)+
    (descriptor.tileRow.pad(18)<<5)+(firstCol.pad(18)>>3)
  io.readEnable:=usable && pinned && (state===captureLow || (state===readLow && liveBeat))
  io.readBank:=row
  io.readAddress:=(baseAddress+Mux(state===captureLow,1.U,0.U))(9,0)
  val wordStart=firstCol.pad(10)+Mux(state===captureHigh,8.U,0.U)
  val normalized=VecInit((0 until 8).map(i=>
    Mux(row<rows && wordStart+i.U<cols,io.readData(i*32+31,i*32),0.U(32.W)))).asUInt
  val finite=(0 until 8).map(i=>normalized(i*32+30,i*32+23)=/=255.U).reduce(_&&_)

  def sameAck(a:MatrixAccumulatorSeedAck):Bool=
    a.groupTag===req.groupTag && a.groupSequence===req.groupSequence &&
      a.sourceGeneration===req.sourceGeneration && a.context===req.context
  val commitMatches=io.controllerCommitted.bits.asUInt===req.asUInt
  val success=io.seed.ack.fire && state===waitAck && usable && !io.seed.ack.bits.error &&
    sameAck(io.seed.ack.bits) && io.controllerCommitted.valid && commitMatches
  io.completed.valid:=success
  io.completed.bits:=descriptor
  io.release.valid:=success
  io.release.bits:=descriptor
  io.quarantine.valid:=poison && pinned
  io.quarantine.bits:=descriptor
  def fail():Unit={poison:=true.B;state:=locked}

  when(io.start.fire){
    descriptor:=io.start.bits;shape:=io.shape;beatIndex:=0.U;slice:=0.U;cluster:=0.U
    pinned:=false.B;began:=false.B;ackSeen:=false.B;state:=acquiring
  }
  when(state===acquiring && usable && (!geometryLegal || !metadataLegal || io.metadata.leaseHeld)){fail()}
  when(io.acquire.fire){pinned:=true.B;state:=begin}
  when(io.seed.begin.fire){began:=true.B;state:=readLow}
  when(state===readLow && usable){
    when(liveBeat){state:=captureLow}.otherwise{payload:=0.U;state:=offer}
  }
  when(state===captureLow && usable){
    payload:=Cat(0.U(256.W),normalized);state:=captureHigh
    when(!finite){fail()}
  }
  when(state===captureHigh && usable){
    payload:=Cat(normalized,payload(255,0));state:=offer
    when(!finite){fail()}
  }
  when(io.seed.beat.fire){
    when(io.seed.beat.bits.last){state:=waitAck}.otherwise{
      beatIndex:=beatIndex+1.U
      when(cluster===31.U){slice:=PriorityEncoder(laterSlices);cluster:=0.U}
        .otherwise{cluster:=cluster+1.U}
      state:=readLow
    }
  }
  when(io.seed.ack.fire){
    ackSeen:=true.B
    when(success){pinned:=false.B;began:=false.B;state:=idle}.otherwise{fail()}
  }
  when(io.controllerCommitted.valid && !success){fail()}
  when(sourceFault || unexpectedAck || io.controllerResetRequired){fail()}
  when(io.readEnable){
    assert(io.portsGranted && io.legacyDrained && pinned)
    assert(baseAddress>=cBase && baseAddress+1.U<1024.U)
  }
}

/** A combinational replacement for the existing A-bank .read argument mux.
  * The caller must still instantiate exactly ONE .read per physical A/C bank:
  *   bankData(i) := aBanks(i).read(bankAddress(i), bankEnable(i))
  * No memory is allocated here. Ordinary reads enable all 16 banks; a seed
  * read enables exactly one. A single registered bank index selects its t+1
  * result. legacyPending is StreamingDense's real pending, not a guessed tag.
  */
class ResidentSeedBankReadMux(addressBits:Int=10) extends Module {
  require(addressBits>=10)
  val io=IO(new Bundle {
    val stopLegacyReads=Input(Bool())
    val legacyRequest=Input(Bool())
    val legacyAddress=Input(UInt(addressBits.W))
    val legacyPending=Input(Bool())
    val conflictingWrite=Input(Bool())
    val portsGranted=Input(Bool())
    val seedEnable=Input(Bool())
    val seedBank=Input(UInt(4.W))
    val seedAddress=Input(UInt(10.W))
    val bankData=Input(Vec(16,UInt(256.W)))
    val bankEnable=Output(Vec(16,Bool()))
    val bankAddress=Output(Vec(16,UInt(addressBits.W)))
    val legacyFire=Output(Bool())
    val seedData=Output(UInt(256.W))
    val seedPending=Output(Bool())
  })
  val pendingBank=Reg(UInt(4.W))
  val pending=RegNext(io.seedEnable,false.B)
  when(io.seedEnable){pendingBank:=io.seedBank}
  io.legacyFire:=io.legacyRequest && !io.stopLegacyReads && !io.portsGranted
  for(i<-0 until 16){
    io.bankEnable(i):=io.legacyFire || (io.seedEnable && io.seedBank===i.U)
    io.bankAddress(i):=Mux(io.seedEnable,io.seedAddress,io.legacyAddress)
  }
  io.seedData:=io.bankData(pendingBank)
  io.seedPending:=pending
  when(io.seedEnable){
    assert(io.portsGranted && io.stopLegacyReads && !io.legacyPending && !io.conflictingWrite,
      "resident C reader did not acquire the existing A/C read port after drain")
    assert(!io.legacyFire)
  }
}

/** Optional owner-local hook in streaming_dense_read_hook.patch. The ordinary
  * owner itself computes grant from its actual read/operand/write/DMA state.
  * A/C layout, prefix metadata and reader/controller orchestration are still
  * the resident owner's responsibility. This is not a public memory ABI.
  */
class ResidentSeedReadHook extends Bundle {
  val pause=Input(Bool())
  val enable=Input(Bool())
  val bank=Input(UInt(4.W))
  val address=Input(UInt(10.W))
  val grant=Output(Bool())
  val data=Output(UInt(256.W))
  val pending=Output(Bool())
}
