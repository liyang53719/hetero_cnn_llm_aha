// SPDX-License-Identifier: Apache-2.0
package heteronpu.experimental

import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import StrictFp32LaneFixtures.{Vector => LaneVector, _}

/** Source-only regression candidate. No backend has been run for this package.
  * Explicit Treadle backend; no external Verilator backend requested here.
  */
class StrictFp32MatrixLaneSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private def drive(d: StrictFp32MatrixLane, v: LaneVector, tag: BigInt, mode: Int = 1): Unit = {
    d.io.request.bits.tag.poke(tag.U)
    d.io.request.bits.mode.poke(mode.U)
    d.io.request.bits.a.poke(v.a.U)
    d.io.request.bits.b.poke(v.b.U)
    d.io.request.bits.acc.poke(v.acc.U)
  }

  private def initialize(d: StrictFp32MatrixLane): Unit = {
    d.io.request.valid.poke(false.B)
    d.io.result.ready.poke(false.B)
    drive(d, all.head, 0)
    d.reset.poke(true.B)
    d.clock.step(2)
    d.reset.poke(false.B)
    d.io.request.ready.expect(true.B)
    d.io.result.valid.expect(false.B)
    d.io.busy.expect(false.B)
  }

  private def accept(d: StrictFp32MatrixLane, v: LaneVector, tag: BigInt, mode: Int = 1): Unit = {
    d.io.request.ready.expect(true.B)
    drive(d, v, tag, mode)
    d.io.request.valid.poke(true.B)
    d.clock.step()
    d.io.request.valid.poke(false.B)
  }

  private def awaitReply(d: StrictFp32MatrixLane, expectedCycles: Int): Unit = {
    // Pre/Mul/Post/Round are each one edge per pass; rejection takes no pass.
    for (_ <- 0 until expectedCycles) {
      d.io.result.valid.expect(false.B)
      d.io.request.ready.expect(false.B)
      d.io.busy.expect(true.B)
      d.clock.step()
    }
    d.io.result.valid.expect(true.B)
    d.io.request.ready.expect(false.B)
    d.io.busy.expect(true.B)
  }

  private def expectReply(d: StrictFp32MatrixLane, v: LaneVector, tag: BigInt,
                          mode: Int = 1): Unit = {
    val r = d.io.result.bits
    val mulDone = v.passes >= 1
    val addDone = v.passes == 2
    r.tag.expect(tag.U)
    r.mode.expect(mode.U)
    r.status.expect(v.status.U)
    r.product.expect(v.product.U)
    r.productValid.expect(mulDone.B)
    r.value.expect(v.value.U)
    r.valueValid.expect(addDone.B)
    r.mulFlags.expect(v.mulFlags.U)
    r.mulFlagsValid.expect(mulDone.B)
    r.addFlags.expect(v.addFlags.U)
    r.addFlagsValid.expect(addDone.B)
    r.fmaFlags.expect(0.U)
    r.fmaFlagsValid.expect(false.B)
    r.passesCompleted.expect(v.passes.U)
    r.accCommit.expect((v.status == 0).B)
  }

  private def retire(d: StrictFp32MatrixLane): Unit = {
    d.io.request.valid.poke(false.B)
    d.io.result.ready.poke(true.B)
    d.clock.step()
    d.io.result.ready.poke(false.B)
    d.io.result.valid.expect(false.B)
    d.io.request.ready.expect(true.B)
    d.io.busy.expect(false.B)
  }

  it should "match all 52 frozen requests and retain every diagnostic under backpressure" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      initialize(d)
      all.zipWithIndex.foreach { case (v, index) =>
        withClue(s"${v.id}: ") {
          val tag = BigInt("80000000", 16) + index
          accept(d, v, tag)
          // A held competing request must not replace the accepted operands/tag.
          drive(d, all((index + 1) % all.size), tag ^ BigInt("ffffffff", 16))
          d.io.request.valid.poke(true.B)
          awaitReply(d, 4 * v.passes)
          for (_ <- 0 until 3) {
            expectReply(d, v, tag)
            d.io.result.valid.expect(true.B)
            d.io.request.ready.expect(false.B)
            d.clock.step()
          }
          expectReply(d, v, tag)
          retire(d)
        }
      }
    }
  }

  it should "retire without accepting a competing request on the same edge" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      initialize(d)
      val first = all.head
      val competing = all.find(_.id == "add_overflow_after_exact_mul").get
      accept(d, first, 500)
      awaitReply(d, 8)
      expectReply(d, first, 500)
      drive(d, competing, 501)
      d.io.request.valid.poke(true.B)
      d.io.result.ready.poke(true.B)
      // This lane has no same-edge refill: only the old result may fire.
      d.io.request.ready.expect(false.B)
      d.io.result.valid.expect(true.B)
      d.clock.step()
      // Withdraw before the next edge, when idle could legitimately accept it.
      d.io.request.valid.poke(false.B)
      d.io.result.ready.poke(false.B)
      d.io.request.ready.expect(true.B)
      for (_ <- 0 until 10) {
        d.io.result.valid.expect(false.B)
        d.io.busy.expect(false.B)
        d.clock.step()
      }
      accept(d, competing, 502)
      awaitReply(d, 8)
      expectReply(d, competing, 502)
      retire(d)
    }
  }

  it should "reject nonfinite operands before either pass without synthetic flags" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      initialize(d)
      val nonfinite = Seq("7f800000", "ff800000", "7fc00001", "7f800001")
      for ((bits, n) <- nonfinite.zipWithIndex; operand <- 0 until 3) {
        val bad = BigInt(bits, 16)
        // Finite a/b would overflow if admitted: invalid acc must win first.
        val base = all.find(_.id == "mul_overflow_cannot_be_fused_away").get
        val v = base.copy(id = s"reject-$n-$operand",
          a = if (operand == 0) bad else base.a,
          b = if (operand == 1) bad else base.b,
          acc = if (operand == 2) bad else base.acc,
          product = 0, value = 0, mulFlags = 0, addFlags = 0, passes = 0, status = 3)
        accept(d, v, 100 + 3 * n + operand)
        awaitReply(d, 0)
        expectReply(d, v, 100 + 3 * n + operand)
        retire(d)
      }
    }
  }

  it should "reject reserved modes and malformed legacy encodings without arithmetic" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      initialize(d)
      for ((mode, status) <- Seq((2, 1), (3, 1), (0, 2))) {
        val v = all.head.copy(product = 0, value = 0, mulFlags = 0,
          addFlags = 0, passes = 0, status = status)
        accept(d, v, mode + 200, mode)
        awaitReply(d, 0)
        expectReply(d, v, mode + 200, mode)
        retire(d)
      }
    }
  }

  it should "flush each of eight active stages and a held reply on reset, then recover" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      initialize(d)
      val v = all.find(_.id == "strict_zero_versus_fused_negative_residue").get
      for (elapsed <- 0 to 8) {
        accept(d, v, 300 + elapsed)
        if (elapsed > 0) d.clock.step(elapsed)
        d.io.result.valid.expect((elapsed == 8).B)
        // Even with both ends willing, reset gates every handshake immediately.
        drive(d, all.head, 999)
        d.io.request.valid.poke(true.B)
        d.io.result.ready.poke(true.B)
        d.reset.poke(true.B)
        d.io.request.ready.expect(false.B)
        d.io.result.valid.expect(false.B)
        d.io.busy.expect(false.B)
        d.clock.step()
        d.io.request.valid.poke(false.B)
        d.io.result.ready.poke(false.B)
        d.reset.poke(false.B)
        d.io.request.ready.expect(true.B)
        // Past work must never leak a stale reply after reset release.
        for (_ <- 0 until 10) {
          d.io.result.valid.expect(false.B)
          d.io.busy.expect(false.B)
          d.clock.step()
        }
        accept(d, all.head, 400 + elapsed)
        awaitReply(d, 8)
        expectReply(d, all.head, 400 + elapsed)
        retire(d)
      }
    }
  }
}
