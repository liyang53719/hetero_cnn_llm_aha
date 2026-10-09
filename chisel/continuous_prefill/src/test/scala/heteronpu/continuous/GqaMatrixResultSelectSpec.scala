// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.util.Random

/** Test-only combinational adapter around the production selector and its exact
  * previous expression. The handshake is a transparent test wrapper, not the
  * GQA owner's transaction machinery; Bf16CausalGqaOwnerSpec covers that machinery.
  * Only the 32 selected output lanes are packed by the candidate adapter.
  */
class GqaMatrixResultSelectProbe extends Module {
  val io = IO(new Bundle {
    val input = Flipped(Decoupled(Vec(16, Vec(256, UInt(32.W)))))
    val row = Input(UInt(4.W))
    val beat = Input(UInt(3.W))
    val resultQk = Input(Bool())
    val output = Decoupled(UInt(1024.W))
    val reference = Output(UInt(1024.W))
  })

  // Mirror the owner's choice: QK always reads beat zero; PV reads beat.
  val selectedBeat = Mux(io.resultQk, 0.U(3.W), io.beat)
  val candidate = GqaMatrixResultSelect(io.input.bits, io.row, selectedBeat)
  val reference = VecInit(io.input.bits.map(_.asUInt))(io.row)
    .asTypeOf(Vec(8, UInt(1024.W)))(selectedBeat)
    .asTypeOf(Vec(32, UInt(32.W)))
  io.output.bits := candidate.asUInt
  io.reference := reference.asUInt
  io.output.valid := io.input.valid
  io.input.ready := io.output.ready
}

class GqaMatrixResultSelectSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private val wordMask = BigInt("ffffffff", 16)
  private val rows = 16
  private val beats = 8
  private val lanes = 32

  "GqaMatrixResultSelect" should "preserve every raw lane and QK/PV selection independently of valid and ready" in {
    test(new GqaMatrixResultSelectProbe).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      // Every loop is bounded; the cycle watchdog also catches accidental waits.
      d.clock.setTimeout(8192)
      d.io.input.valid.poke(false.B)
      d.io.output.ready.poke(false.B)
      d.io.row.poke(0.U)
      d.io.beat.poke(0.U)
      d.io.resultQk.poke(false.B)

      // Keep raw UInt bits throughout: Float conversions could canonicalize NaNs
      // and would obscure signed zero and subnormal preservation.
      val specials = Vector(
        "00000000", "80000000", // positive and negative zero
        "00000001", "80000001", "007fffff", "807fffff", // subnormals
        "00800000", "80800000", // smallest normal values
        "7f800000", "ff800000", // infinities
        "7fc00000", "ffc00000", "7fc01234", "ffc05678", // quiet NaNs
        "7f800001", "ff800001", "7fa12345", "ffa54321", // signaling NaNs
        "7f7fffff", "ff7fffff", // largest finite values
        "3f800000", "bf800000", "3f000000", "bf000000",
        "3f800001", "bf800001", "00800001", "80800001",
        "12345678", "87654321", "aaaaaaaa", "55555555"
      ).map(BigInt(_, 16))
      val rng = new Random(0x47514153454cL)
      val patterns = Seq(
        "coordinate tags" -> Array.tabulate(rows, beats * lanes) { (r, c) =>
          BigInt(0xa5a50000L | (r * beats * lanes + c).toLong)
        },
        "inverted coordinate tags" -> Array.tabulate(rows, beats * lanes) { (r, c) =>
          wordMask ^ BigInt(0xa5a50000L | (r * beats * lanes + c).toLong)
        },
        "raw FP32 specials" -> Array.tabulate(rows, beats * lanes) { (r, c) =>
          specials((r * 3 + (c / lanes) * 5 + c % lanes) % specials.size)
        },
        "seeded random bits" -> Array.tabulate(rows, beats * lanes) { (_, _) =>
          BigInt(rng.nextInt().toLong & 0xffffffffL)
        }
      )
      val handshakes = Seq((false, false), (false, true), (true, false), (true, true))
      var checkedSelectors = 0
      var checkedHandshakes = 0

      def select(r: Int, b: Int, qk: Boolean): Unit = {
        d.io.row.poke(r.U)
        d.io.beat.poke(b.U)
        d.io.resultQk.poke(qk.B)
      }

      def check(data: Array[Array[BigInt]], r: Int, b: Int, qk: Boolean,
                valid: Boolean, ready: Boolean, label: String): Unit = {
        val selected = if (qk) 0 else b
        // Independent lane-index model also checks Chisel's packing direction.
        val expected = (0 until lanes).foldLeft(BigInt(0)) { (word, lane) =>
          word | (data(r)(selected * lanes + lane) << (32 * lane))
        }
        withClue(s"$label row=$r beat=$b resultQk=$qk valid=$valid ready=$ready: ") {
          d.io.output.bits.expect(expected.U(1024.W))
          d.io.reference.expect(expected.U(1024.W))
          d.io.output.valid.expect(valid.B)
          d.io.input.ready.expect(ready.B)
        }
      }

      for ((label, data) <- patterns) {
        d.io.input.valid.poke(false.B)
        d.io.output.ready.poke(false.B)
        // Poke the 4096 input words only once per pattern, then sweep selectors.
        for (r <- 0 until rows; c <- 0 until beats * lanes) {
          d.io.input.bits(r)(c).poke(data(r)(c).U(32.W))
        }
        // Four row bits and three beat bits have exactly 16 and 8 encodings.
        // This covers their complete domains; there is no out-of-range encoding
        // to test and no truncating poke of an unrepresentable row or beat.
        for (qk <- Seq(false, true); r <- 0 until rows; b <- 0 until beats) {
          select(r, b, qk)
          checkedSelectors += 1
          for ((valid, ready) <- handshakes) {
            d.io.input.valid.poke(valid.B)
            d.io.output.ready.poke(ready.B)
            // Check before a clock edge: invalid and stalled cycles still expose
            // the same combinational selection, with no hidden enable or state.
            check(data, r, b, qk, valid, ready, label)
            d.clock.step()
            checkedHandshakes += 1
          }
        }
      }
      checkedSelectors shouldBe patterns.size * 2 * rows * beats
      checkedHandshakes shouldBe checkedSelectors * handshakes.size

      val data = patterns.last._2
      // Hold the entire source tile stable over multiple backpressured cycles,
      // then release it. Include endpoint rows/beats and nonzero QK beat inputs.
      for ((r, b, qk) <- Seq((0, 0, false), (15, 7, false), (0, 7, true), (15, 3, true))) {
        select(r, b, qk)
        d.io.input.valid.poke(true.B)
        d.io.output.ready.poke(false.B)
        for (_ <- 0 until 7) {
          check(data, r, b, qk, valid = true, ready = false, label = "held source tile")
          d.clock.step()
        }
        d.io.output.ready.poke(true.B)
        check(data, r, b, qk, valid = true, ready = true, label = "released source tile")
        d.clock.step()
      }

      // Change only a few words after the exhaustive sweeps. Changes must become
      // visible without an edge even when valid is low, including beat boundaries.
      d.io.input.valid.poke(false.B)
      d.io.output.ready.poke(false.B)
      for ((r, c) <- Seq((0, 0), (0, 31), (0, 32), (0, 255),
                         (15, 0), (15, 31), (15, 224), (15, 255))) {
        val b = c / lanes
        select(r, b, qk = false)
        data(r)(c) = data(r)(c) ^ wordMask
        d.io.input.bits(r)(c).poke(data(r)(c).U(32.W))
        check(data, r, b, qk = false, valid = false, ready = false, label = "changed raw word")
        select(r, b, qk = true)
        check(data, r, b, qk = true, valid = false, ready = false, label = "QK still selects beat zero")
        d.clock.step()
      }
    }
  }
}
