// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class Qwen2Public21TagAdapterV2Harness extends Module {
  val io = IO(new Bundle {
    val start=Input(Bool());val ready=Output(Bool())
    val transaction=Input(UInt(64.W));val sequence=Input(UInt(32.W));val role=Input(UInt(4.W))
    val legacyReady=Input(Bool());val legacyValid=Output(Bool());val legacyTag=Output(UInt(32.W))
    val doneValid=Input(Bool());val doneTag=Input(UInt(32.W));val doneBytes=Input(UInt(64.W))
    val resultReady=Input(Bool());val resultValid=Output(Bool());val resultStatus=Output(UInt(8.W));val resultTag=Output(UInt(32.W));val resultBytes=Output(UInt(64.W))
    val resultTransaction=Output(UInt(64.W));val resultSequence=Output(UInt(32.W))
    val resetRequired=Output(Bool())
  })
  val c=WireDefault(0.U.asTypeOf(new UnifiedRuntimeDenseCommandV2))
  val (p,_) = UnifiedRuntimeProfile.decode(0.U(3.W))
  c.context.profile:=p;c.context.transactionId:=io.transaction
  c.context.launch.version:=1.U;c.context.launch.tokens:=128.U
  c.role:=io.role;c.firstOwnerSequence:=io.sequence
  c.input:="h10000000".U;c.weight:="h20000000".U;c.output:="h30000000".U
  val a=Module(new Qwen2Public21TagAdapterV2)
  a.io.request.valid:=io.start;a.io.request.bits:=UnifiedRuntimeDensePlanV2.decode(c)
  io.ready:=a.io.request.ready
  a.io.legacyJob.ready:=io.legacyReady;io.legacyValid:=a.io.legacyJob.valid
  io.legacyTag:=a.io.legacyJob.bits.tag
  a.io.legacyDone.valid:=io.doneValid;a.io.legacyDone.bits:=0.U.asTypeOf(new QwenOwnerResult)
  a.io.legacyDone.bits.tag:=io.doneTag;a.io.legacyDone.bits.writeBytes:=io.doneBytes
  a.io.result.ready:=io.resultReady;io.resultValid:=a.io.result.valid
  io.resultTransaction:=a.io.result.bits.transactionId;io.resultSequence:=a.io.result.bits.ownerSequence
  io.resultStatus:=a.io.result.bits.result.status;io.resultTag:=a.io.result.bits.result.tag
  io.resultBytes:=a.io.result.bits.result.writeBytes
  io.resetRequired:=a.io.resetRequired
}
class Qwen2Public21TagAdapterV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "Original public21 tag adapter"
  it should "retain public PC while returning the full external identity under backpressure" in {
    test(new Qwen2Public21TagAdapterV2Harness){ d=>
      d.io.start.poke(false.B);d.io.doneValid.poke(false.B);d.io.legacyReady.poke(false.B)
      d.io.resultReady.poke(false.B);d.io.doneTag.poke(0.U);d.io.doneBytes.poke(0.U)
      d.io.transaction.poke("h100000001".U);d.io.sequence.poke(1234.U);d.io.role.poke(0.U)
      d.io.start.poke(true.B);d.io.ready.expect(true.B);d.clock.step();d.io.start.poke(false.B)
      d.io.legacyValid.expect(true.B);d.io.legacyTag.expect(65537.U)
      d.clock.step(2);d.io.legacyTag.expect(65537.U)
      d.io.legacyReady.poke(true.B);d.clock.step();d.io.legacyReady.poke(false.B)
      d.io.doneTag.poke(65537.U);d.io.doneBytes.poke((128L*1536*4).U)
      d.io.doneValid.poke(true.B);d.clock.step();d.io.doneValid.poke(false.B)
      d.io.resultValid.expect(true.B);d.io.resultTransaction.expect("h100000001".U)
      d.io.resultSequence.expect(1234.U);d.clock.step(2);d.io.resultValid.expect(true.B)
      d.io.resultReady.poke(true.B);d.clock.step();d.io.resetRequired.expect(false.B)
      // Old response must not be accepted as a later owner result.
      d.io.doneValid.poke(true.B);d.io.resetRequired.expect(true.B);d.clock.step()
      d.io.doneValid.poke(false.B);d.io.resetRequired.expect(true.B);d.io.ready.expect(false.B)
    }
  }
  it should "retain an offered job after stray done then reject its apparent success" in {
    test(new Qwen2Public21TagAdapterV2Harness){ d=>
      d.io.start.poke(false.B);d.io.doneValid.poke(false.B);d.io.legacyReady.poke(false.B)
      d.io.resultReady.poke(false.B);d.io.doneTag.poke(999.U);d.io.doneBytes.poke((128L*1536*4).U)
      d.io.transaction.poke(9.U);d.io.sequence.poke(8.U);d.io.role.poke(0.U)
      d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B)
      d.io.legacyValid.expect(true.B);d.io.legacyTag.expect(65537.U)
      d.io.doneValid.poke(true.B)
      d.io.legacyValid.expect(true.B);d.io.legacyTag.expect(65537.U);d.io.resetRequired.expect(true.B)
      d.clock.step(2);d.io.legacyValid.expect(true.B)
      // Offer survives even a same-cycle fire plus unsolicited completion.
      d.io.legacyReady.poke(true.B);d.clock.step()
      d.io.doneValid.poke(false.B);d.io.legacyReady.poke(false.B)
      // Wrong-tag completion does not discharge the accepted real job.
      d.io.doneTag.poke(999.U);d.io.doneValid.poke(true.B);d.clock.step()
      d.io.doneValid.poke(false.B);d.io.resultValid.expect(false.B)
      d.io.doneTag.poke(65537.U);d.io.doneValid.poke(true.B);d.clock.step();d.io.doneValid.poke(false.B)
      d.io.resultValid.expect(true.B);d.io.resultStatus.expect(Status.Protocol.U)
      d.io.resultReady.poke(true.B);d.clock.step();d.io.ready.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }
  it should "keep a held terminal payload stable under a late stray including retirement" in {
    test(new Qwen2Public21TagAdapterV2Harness){ d=>
      d.io.start.poke(false.B);d.io.doneValid.poke(false.B);d.io.legacyReady.poke(true.B)
      d.io.resultReady.poke(false.B);d.io.doneTag.poke(65537.U);d.io.doneBytes.poke((128L*1536*4).U)
      d.io.transaction.poke(19.U);d.io.sequence.poke(18.U);d.io.role.poke(0.U)
      d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B);d.clock.step()
      d.io.doneValid.poke(true.B);d.clock.step();d.io.doneValid.poke(false.B)
      d.io.resultValid.expect(true.B);d.io.resultStatus.expect(0.U)
      d.io.doneTag.poke(999.U);d.io.doneValid.poke(true.B)
      for (_ <- 0 until 2) {
        d.io.resultValid.expect(true.B);d.io.resultStatus.expect(0.U)
        d.io.resultTag.expect(65537.U);d.io.resultBytes.expect((128L*1536*4).U)
        d.io.resultTransaction.expect(19.U);d.io.resultSequence.expect(18.U)
        d.io.resetRequired.expect(true.B);d.clock.step()
      }
      d.io.resultReady.poke(true.B);d.io.resultValid.expect(true.B);d.clock.step()
      d.io.doneValid.poke(false.B);d.io.ready.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }

}

class Qwen2Public21EpochV2Harness extends Module {
  val io=IO(new Bundle {val epoch=Input(UInt(16.W));val exhausted=Output(Bool())})
  io.exhausted:=Qwen2Public21EpochV2.exhausted(io.epoch)
}
class Qwen2Public21EpochV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  it should "mark the exact nonwrapping epoch boundary" in {
    test(new Qwen2Public21EpochV2Harness){d=>
      for(e <- Seq(0,1,65534,65535)) {d.io.epoch.poke(e.U);d.io.exhausted.expect((e==65535).B)}
    }
  }
}
