package heteronpu.operator

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class OperatorPrimitivesSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "three-model operator primitive source gate"

  it should "pass all pure-Scala semantic and coverage checks" in {
    noException should be thrownBy ProgramValidation.validate()
    ThreeModelOperatorCatalog.roots.size shouldBe 18
    ThreeModelOperatorCatalog.qwen2.size shouldBe 30
    ThreeModelOperatorCatalog.qwen35.size should be >= 90
    ThreeModelOperatorCatalog.qwen38.size should be >= 140
  }

  private def initialize(dut: ProgramPrimitive): Unit = {
    dut.io.launch.valid.poke(false.B)
    dut.io.microOp.ready.poke(false.B)
    dut.io.completion.valid.poke(false.B)
    dut.io.completion.bits.tag.poke(0.U)
    dut.io.completion.bits.phase.poke(0.U)
    dut.io.completion.bits.status.poke(0.U)
    dut.io.result.ready.poke(false.B)
    for (i <- 0 until 16) dut.io.launch.bits.descriptors(i).poke((0x100 + i).U)
    for (i <- 0 until 8) dut.io.launch.bits.dimensions(i).poke((0x200 + i).U)
    dut.io.launch.bits.tag.poke("h5a3c".U)
    dut.io.launch.bits.mode.poke("h05".U)
    dut.clock.step(2)
  }

  private def launch(dut: ProgramPrimitive): Unit = {
    dut.io.launch.ready.expect(true.B)
    dut.io.launch.valid.poke(true.B)
    dut.clock.step()
    dut.io.launch.valid.poke(false.B)
  }

  private def runToCompletion(dut: ProgramPrimitive, program: Seq[MicroOpTemplate]): Unit = {
    var pending: Option[(BigInt, BigInt)] = None
    var issued = 0
    var done = false
    var cycle = 0

    while (!done && cycle < program.length * 12 + 40) {
      val issueReady = (cycle % 4) != 1
      val resultReady = (cycle % 5) != 2
      dut.io.microOp.ready.poke(issueReady.B)
      dut.io.result.ready.poke(resultReady.B)

      pending match {
        case Some((tag, phase)) =>
          dut.io.completion.valid.poke(true.B)
          dut.io.completion.bits.tag.poke(tag.U)
          dut.io.completion.bits.phase.poke(phase.U)
          dut.io.completion.bits.status.poke(0.U)
        case None =>
          dut.io.completion.valid.poke(false.B)
      }

      val issueFire = dut.io.microOp.valid.peek().litToBoolean && issueReady
      val completionFire = pending.nonEmpty && dut.io.completion.ready.peek().litToBoolean
      val resultFire = dut.io.result.valid.peek().litToBoolean && resultReady

      var issuedNow: Option[(BigInt, BigInt)] = None
      if (issueFire) {
        val expected = program(issued)
        dut.io.microOp.bits.kind.expect(expected.kind.U)
        dut.io.microOp.bits.flags.expect(expected.flags.U)
        dut.io.microOp.bits.phase.expect(issued.U)
        dut.io.microOp.bits.tag.expect("h5a3c".U)
        dut.io.microOp.bits.mode.expect("h05".U)
        dut.io.microOp.bits.src0.expect((0x100 + expected.src0).U)
        dut.io.microOp.bits.src1.expect((0x100 + expected.src1).U)
        dut.io.microOp.bits.src2.expect((0x100 + expected.src2).U)
        dut.io.microOp.bits.dst.expect((0x100 + expected.dst).U)
        dut.io.microOp.bits.m.expect((0x200 + expected.m).U)
        dut.io.microOp.bits.n.expect((0x200 + expected.n).U)
        dut.io.microOp.bits.k.expect((0x200 + expected.k).U)
        dut.io.microOp.bits.index0.expect(expected.index0.U)
        dut.io.microOp.bits.index1.expect(expected.index1.U)
        issuedNow = Some((dut.io.microOp.bits.tag.peek().litValue,
          dut.io.microOp.bits.phase.peek().litValue))
        issued += 1
      }

      if (resultFire) {
        dut.io.result.bits.tag.expect("h5a3c".U)
        dut.io.result.bits.status.expect(0.U)
        dut.io.result.bits.completedPhases.expect(program.length.U)
        done = true
      }

      dut.clock.step()
      if (completionFire) pending = None
      if (issuedNow.nonEmpty) pending = issuedNow
      cycle += 1
    }

    withClue(s"issued=$issued expected=${program.length} cycles=$cycle") {
      issued shouldBe program.length
      done shouldBe true
    }
    dut.io.protocolError.expect(false.B)
  }

  ThreeModelOperatorCatalog.roots.zipWithIndex.foreach { case (root, index) =>
    it should s"execute ${root.name} under deterministic issue/result backpressure" in {
      test(new ProgramPrimitive(root.program, s"HeteroPrimitiveTestRoot$index")) { dut =>
        initialize(dut)
        launch(dut)
        runToCompletion(dut, root.program)
      }
    }
  }

  it should "hold a micro-op stable while its consumer applies backpressure" in {
    val program = TextPrograms.Qwen2DecoderBlock
    test(new ProgramPrimitive(program, "HeteroBackpressureStabilityTest")) { dut =>
      initialize(dut)
      launch(dut)
      dut.io.microOp.ready.poke(false.B)
      dut.io.microOp.valid.expect(true.B)
      val firstKind = dut.io.microOp.bits.kind.peek().litValue
      val firstFlags = dut.io.microOp.bits.flags.peek().litValue
      val firstSrc0 = dut.io.microOp.bits.src0.peek().litValue
      val firstTag = dut.io.microOp.bits.tag.peek().litValue
      dut.clock.step(5)
      dut.io.microOp.valid.expect(true.B)
      dut.io.microOp.bits.kind.expect(firstKind.U)
      dut.io.microOp.bits.flags.expect(firstFlags.U)
      dut.io.microOp.bits.src0.expect(firstSrc0.U)
      dut.io.microOp.bits.tag.expect(firstTag.U)
    }
  }

  it should "fail fast on a completion tag mismatch" in {
    test(new ProgramPrimitive(TextPrograms.TokenEmbedding, "HeteroBadCompletionTagTest")) { dut =>
      initialize(dut)
      launch(dut)
      dut.io.microOp.ready.poke(true.B)
      dut.clock.step()
      dut.io.microOp.ready.poke(false.B)
      dut.io.completion.valid.poke(true.B)
      dut.io.completion.bits.tag.poke("h5a3d".U)
      dut.io.completion.bits.phase.poke(0.U)
      dut.io.completion.bits.status.poke(0.U)
      dut.io.completion.ready.expect(true.B)
      dut.clock.step()
      dut.io.completion.valid.poke(false.B)
      dut.io.result.ready.poke(false.B)
      dut.io.result.valid.expect(true.B)
      dut.io.result.bits.status.expect("he1".U)
      dut.io.protocolError.expect(true.B)
    }
  }

  it should "propagate a leaf execution error without issuing later phases" in {
    test(new ProgramPrimitive(TextPrograms.Qwen2DecoderBlock, "HeteroLeafErrorTest")) { dut =>
      initialize(dut)
      launch(dut)
      dut.io.microOp.ready.poke(true.B)
      dut.clock.step()
      dut.io.microOp.ready.poke(false.B)
      dut.io.completion.valid.poke(true.B)
      dut.io.completion.bits.tag.poke("h5a3c".U)
      dut.io.completion.bits.phase.poke(0.U)
      dut.io.completion.bits.status.poke("h27".U)
      dut.clock.step()
      dut.io.completion.valid.poke(false.B)
      dut.io.result.ready.poke(false.B)
      dut.io.result.valid.expect(true.B)
      dut.io.result.bits.status.expect("h27".U)
      dut.io.result.bits.completedPhases.expect(1.U)
      dut.io.protocolError.expect(false.B)
    }
  }
}
