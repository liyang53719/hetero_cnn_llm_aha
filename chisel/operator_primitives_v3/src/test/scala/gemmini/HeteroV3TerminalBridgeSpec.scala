package gemmini

import chisel3._
import chiseltest._
import heteronpu.operator.{LeafCapabilities, PrimitiveKind}
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class HeteroV3TerminalBridgeSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "HeteroV3TerminalBridge"

  private def initialize(dut: HeteroV3TerminalBridge): Unit = {
    dut.io.clear.poke(true.B)
    dut.io.in.valid.poke(false.B)
    dut.io.terminal.ready.poke(false.B)
    dut.io.terminalCompletion.valid.poke(false.B)
    dut.io.completion.ready.poke(false.B)
    dut.clock.step()
    dut.io.clear.poke(false.B)
  }

  private def launch(dut: HeteroV3TerminalBridge, kind: Int, tag: Int, phase: Int, mode: Int = 0): Unit = {
    dut.io.in.bits.kind.poke(kind.U)
    dut.io.in.bits.flags.poke("h5a5a".U)
    dut.io.in.bits.phase.poke(phase.U)
    dut.io.in.bits.tag.poke(tag.U)
    dut.io.in.bits.mode.poke(mode.U)
    dut.io.in.bits.src0.poke(1.U)
    dut.io.in.bits.src1.poke(2.U)
    dut.io.in.bits.src2.poke(3.U)
    dut.io.in.bits.dst.poke(4.U)
    dut.io.in.bits.m.poke(5.U)
    dut.io.in.bits.n.poke(6.U)
    dut.io.in.bits.k.poke(7.U)
    dut.io.in.bits.index0.poke(8.U)
    dut.io.in.bits.index1.poke(9.U)
    dut.io.in.valid.poke(true.B)
    dut.io.in.ready.expect(true.B)
    dut.clock.step()
    dut.io.in.valid.poke(false.B)
  }

  private def retireOne(dut: HeteroV3TerminalBridge): Unit = {
    var waitCycles = 0
    while (!dut.io.terminal.valid.peek().litToBoolean && waitCycles < 16) {
      dut.clock.step()
      waitCycles += 1
    }
    dut.io.terminal.valid.expect(true.B)
    val tag = dut.io.terminal.bits.tag.peek().litValue
    val parent = dut.io.terminal.bits.parentPhase.peek().litValue
    val terminal = dut.io.terminal.bits.terminalPhase.peek().litValue
    dut.io.terminal.ready.poke(true.B)
    dut.clock.step()
    dut.io.terminal.ready.poke(false.B)
    dut.io.completion.valid.expect(false.B)
    dut.io.terminalCompletion.bits.tag.poke(tag.U)
    dut.io.terminalCompletion.bits.parentPhase.poke(parent.U)
    dut.io.terminalCompletion.bits.terminalPhase.poke(terminal.U)
    dut.io.terminalCompletion.bits.status.poke(0.U)
    dut.io.terminalCompletion.valid.poke(true.B)
    dut.io.terminalCompletion.ready.expect(true.B)
    dut.clock.step()
    dut.io.terminalCompletion.valid.poke(false.B)
  }

  it should "map every canonical leaf and wait for terminal completion" in {
    test(new HeteroV3TerminalBridge) { dut =>
      initialize(dut)
      val compositeCounts = Map(
        PrimitiveKind.Softplus -> 1,
        PrimitiveKind.Sigmoid -> 8,
        PrimitiveKind.Silu -> 9,
        PrimitiveKind.Gelu -> 1,
        PrimitiveKind.SignedSqrt -> 5,
        PrimitiveKind.ConfiguredGateAct -> 9
      )
      LeafCapabilities.all.zipWithIndex.foreach { case (capability, index) =>
        launch(dut, capability.kind, 0x1200 + index, index & 0xff)
        val count = compositeCounts.getOrElse(capability.kind, 1)
        for (_ <- 0 until count) retireOne(dut)
        dut.io.completion.valid.expect(true.B)
        dut.io.completion.bits.tag.expect((0x1200 + index).U)
        dut.io.completion.bits.phase.expect((index & 0xff).U)
        dut.io.completion.bits.status.expect(0.U)
        dut.io.completion.ready.poke(true.B)
        dut.clock.step()
        dut.io.completion.ready.poke(false.B)
        dut.io.busy.expect(false.B)
      }
    }
  }

  it should "serialize the stable sigmoid terminal sequence" in {
    test(new HeteroV3TerminalBridge) { dut =>
      initialize(dut)
      launch(dut, PrimitiveKind.Sigmoid, 0x55aa, 7)
      val expected = Seq(0x43, 0x46, 0x32, 0x48, 0x30, 0x37, 0x32, 0x45)
      expected.zipWithIndex.foreach { case (opcode, phase) =>
        while (!dut.io.terminal.valid.peek().litToBoolean) dut.clock.step()
        dut.io.terminal.bits.owner.expect(HeteroPrimitiveOwner.Sfu)
        dut.io.terminal.bits.opcode.expect(opcode.U)
        dut.io.terminal.bits.terminalPhase.expect(phase.U)
        retireOne(dut)
      }
      dut.io.completion.valid.expect(true.B)
    }
  }

  it should "reject unknown kinds without issuing a terminal request" in {
    test(new HeteroV3TerminalBridge) { dut =>
      initialize(dut)
      launch(dut, 0xff, 0x3344, 2)
      dut.clock.step()
      dut.io.terminal.valid.expect(false.B)
      dut.io.completion.valid.expect(true.B)
      dut.io.completion.bits.status.expect(4.U)
      dut.io.unsupported.expect(true.B)
    }
  }
}
