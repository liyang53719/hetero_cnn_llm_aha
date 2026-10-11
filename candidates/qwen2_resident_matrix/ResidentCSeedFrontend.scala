// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** WORK-ONLY direct source/controller composition for frontend elaboration.
  * Exactly the proposed sixteen A/C SyncReadMem(1024, UInt(256.W)) banks,
  * each with one .read invocation shared between ordinary and seed traffic.
  * No extra memory, FPU, matrix, fake endpoint, or private transport exists.
  * 512 KiB A/C is instantiated; the remaining proposed 256 KiB B allocation
  * and actual Matrix leaf endpoints are outside this focused frontend.
  *
  * Production has no resident owner lease arbiter yet. acquire, portsGranted,
  * metadata and ownerReady are explicit integration obligations, not proof
  * that StreamingDense has already been changed from its 1376/160 layout.
  */
class ResidentCSeedFrontend extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new ResidentSeedDescriptor))
    val shape=Input(new ResidentSeedShape)
    val lookup=Output(new ResidentSeedLookup)
    val metadata=Input(new ResidentSeedOwnerMetadata)
    val acquire=Decoupled(new ResidentSeedDescriptor)
    val release=Valid(new ResidentSeedDescriptor)
    val quarantine=Valid(new ResidentSeedDescriptor)
    val ownerReady=Input(Bool())
    val portsGranted=Input(Bool())
    val terminalReady=Input(Bool())
    val abort=Input(Bool())
    // Existing SRAM issue and write wiring. Actual normal readFire must become
    // legacyReadFire, so pendingK/context advance only on an accepted read.
    val legacyReadRequest=Input(Bool())
    val legacyReadAddress=Input(UInt(10.W))
    val legacyReadFire=Output(Bool())
    val legacyReadPending=Output(Bool())
    val legacyReadData=Output(Vec(16,UInt(256.W)))
    val legacyOperandsDrained=Input(Bool()) // actual !operands.deq.valid
    val aHighPending=Input(Bool()) // StreamingDense native A second write
    val aWriteEnable=Input(Bool())
    val aWriteBank=Input(UInt(4.W))
    val aWriteAddress=Input(UInt(10.W))
    val aWriteData=Input(UInt(256.W))
    val groupActive=Input(Bool())
    val groupTag=Input(UInt(32.W))
    val groupSequence=Input(UInt(32.W))
    val sliceMask=Input(UInt(8.W))
    val freeContexts=Input(UInt(5.W))
    val quiescent=Input(Bool()) // actual arithmetic tags/busy/result drain
    val leafBegin=Decoupled(new MatrixAccumulatorSeedRequest)
    val leafBeat=Decoupled(new MatrixAccumulatorSeedLeafBeat)
    val leafCommit=Decoupled(new MatrixAccumulatorSeedRequest)
    val leafAck=Flipped(Vec(8,Decoupled(new MatrixAccumulatorSeedAck)))
    val invalidate=Valid(new MatrixAccumulatorSeedRequest)
    val completed=Valid(new ResidentSeedDescriptor)
    val blockIssue=Output(Bool())
    val resetRequired=Output(Bool())
  })
  val reader=Module(new ResidentCSeedReader)
  val controller=Module(new MatrixAccumulatorSeedController)
  val ports=Module(new ResidentSeedBankReadMux)
  val aBanks=Seq.fill(16)(SyncReadMem(1024,UInt(256.W)))
  reader.io.start<>io.start
  reader.io.shape:=io.shape
  io.lookup:=reader.io.lookup
  reader.io.metadata:=io.metadata
  io.acquire<>reader.io.acquire
  io.release:=reader.io.release
  io.quarantine:=reader.io.quarantine
  reader.io.ownerReady:=io.ownerReady
  reader.io.portsGranted:=io.portsGranted
  reader.io.abort:=io.abort
  reader.io.terminalReady:=io.terminalReady
  reader.io.seed<>controller.io.seed
  reader.io.controllerCommitted:=controller.io.committed
  reader.io.controllerResetRequired:=controller.io.resetRequired
  io.completed:=reader.io.completed
  io.resetRequired:=reader.io.resetRequired || controller.io.resetRequired
  controller.io.groupActive:=io.groupActive
  controller.io.groupTag:=io.groupTag
  controller.io.groupSequence:=io.groupSequence
  controller.io.sliceMask:=io.sliceMask
  controller.io.freeContexts:=io.freeContexts
  controller.io.quiescent:=io.quiescent
  controller.io.abort:=io.abort || reader.io.abortController
  io.leafBegin<>controller.io.leafBegin
  io.leafBeat<>controller.io.leafBeat
  io.leafCommit<>controller.io.leafCommit
  controller.io.leafAck<>io.leafAck
  io.invalidate:=controller.io.invalidate
  io.blockIssue:=controller.io.blockIssue
  // Starting a source request stops new SRAM reads, but does not block old
  // operand FIFO/matrix work from draining before the seed controller begins.
  val legacyPending=RegNext(ports.io.legacyFire,false.B)
  val writeBusy=io.aHighPending || io.aWriteEnable
  reader.io.legacyDrained:= !legacyPending && io.legacyOperandsDrained && !writeBusy && io.quiescent
  ports.io.stopLegacyReads:=reader.io.stopLegacyReads
  ports.io.legacyRequest:=io.legacyReadRequest
  ports.io.legacyAddress:=io.legacyReadAddress
  ports.io.legacyPending:=legacyPending
  ports.io.conflictingWrite:=writeBusy
  ports.io.portsGranted:=io.portsGranted
  ports.io.seedEnable:=reader.io.readEnable
  ports.io.seedBank:=reader.io.readBank
  ports.io.seedAddress:=reader.io.readAddress
  reader.io.readData:=ports.io.seedData
  io.legacyReadFire:=ports.io.legacyFire
  io.legacyReadPending:=legacyPending
  for(i<-0 until 16){
    // Replace the original .read; never add a second .read to the old bank.
    val data=aBanks(i).read(ports.io.bankAddress(i),ports.io.bankEnable(i))
    ports.io.bankData(i):=data
    io.legacyReadData(i):=data
    when(io.aWriteEnable && io.aWriteBank===i.U){aBanks(i).write(io.aWriteAddress,io.aWriteData)}
  }
  when(reader.io.leasePinned){
    assert(!writeBusy,"resident prefix lease lost the actual A/C write port")
  }
}

/** Scala/Chisel frontend only. No firtool, RTL simulation, or numerical test. */
object ResidentCSeedElaborationCheck extends App {
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  Files.writeString(out.resolve("resident_c_seed_reader.fir"),ChiselStage.emitCHIRRTL(new ResidentCSeedReader))
  Files.writeString(out.resolve("resident_seed_bank_mux.fir"),ChiselStage.emitCHIRRTL(new ResidentSeedBankReadMux))
  Files.writeString(out.resolve("resident_c_seed_frontend.fir"),ChiselStage.emitCHIRRTL(new ResidentCSeedFrontend))
  println("PASS: actual one-cycle SyncReadMem source/controller frontend; no RTL or arithmetic execution")
}
