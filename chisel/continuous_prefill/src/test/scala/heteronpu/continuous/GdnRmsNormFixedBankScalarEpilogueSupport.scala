// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import org.scalatest.matchers.should.Matchers

/** Requires the same-bank Scalar-epilogue candidate's updated harness. Its
  * production core, original Scalar and original elementwise bank are retained.
  * These extra outputs only observe the existing loan recovery controls.
  */
class GdnRmsNormFixedBankScalarEpilogueHarness
    extends GdnRmsNormFixedBankArithmeticHarness(productionCore = true, useVectorEpilogue = false) {
  val controls = IO(new Bundle {
    val loanAbort = Output(Bool())
    val loanReset = Output(Bool())
  })
  controls.loanAbort := loanService.abort
  controls.loanReset := loanService.resetLoan
}

object GdnRmsNormFixedBankScalarEpilogueFixtures {
  import GdnRmsNormFixedBankReference._
  // Replacing sixteen 4s with twelve tiny/zero lanes and four 8s preserves
  // FP32 sum-of-squares = 32768. The real RMS inverse rounds to exactly 0.25.
  // All supplied memory values are ordinary typed BF16 inputs and weights.
  val finiteHidden: Vector[Int] = Vector.fill(Width)(0x4080).patch(0, Vector(
    0x0000, 0x8000, 0x0002, 0x8002, 0x0006, 0x8006,
    0x0004, 0x8004, 0x0080, 0x8080, 0x0003, 0x8003,
    0x4100, 0x4100, 0x4100, 0x4100), 16)
  val finiteWeight: Vector[Int] = Vector.fill(Width)(0).updated(16, 0x3b80).updated(17, 0x3c40)
  // BF16 subnormal ties 0.5 ulp -> even zero; 1.5 ulp -> even 2;
  // exact min subnormal, normal-to-subnormal, 0.75 ulp, and normal RNE ties.
  val finitePrefix: Vector[Int] = Vector(
    0x0000, 0x8000, 0x0000, 0x8000, 0x0002, 0x8002,
    0x0001, 0x8001, 0x0020, 0x8020, 0x0001, 0x8001,
    0x4000, 0x4000, 0x4000, 0x4000, 0x3f80, 0x3f82)
  val overflowHidden: Vector[Int] = Vector.fill(Width)(0x4080).updated(0, 0x4081)
  def overflowWeight(fp32Nonfinite: Boolean): Vector[Int] =
    Vector.fill(Width)(0).updated(0, if (fp32Nonfinite) 0x7f7f else 0x7f7e)

  /** Host-only fixture assertions, never connected to arithmetic responses. */
  def checkFixtures(): Unit = {
    val finite = GdnRmsNormFixedBankReference(finiteHidden, finiteWeight, useVectorEpilogue = false)
    require(finite.scalar(4267).result == bits(0.25f), "finite fixture needs an exact real-RMS inverse")
    require(finite.output.take(18) == finitePrefix)
    // Check the actual FP32 halfway values, not only the final BF16 encodings.
    require(finite.scalar(4268 + 3 * 2 + 2).result == BigInt("00008000", 16))
    require(finite.scalar(4268 + 3 * 4 + 2).result == BigInt("00018000", 16))
    require(finite.scalar(4268 + 3 * 16 + 2).result == BigInt("3f808000", 16))
    require(finite.scalar(4268 + 3 * 17 + 2).result == BigInt("3f818000", 16))
    for (nonfinite <- Seq(false, true)) {
      val recipe = GdnRmsNormFixedBankReference(overflowHidden, overflowWeight(nonfinite),
        useVectorEpilogue = false)
      require(recipe.scalar(4268).result == BigInt("3f80ffe0", 16))
      require(recipe.scalar(4270).result == BigInt(if (nonfinite) "7f800000" else "7f7ffbc0", 16))
      require(recipe.output.head == 0x7f80)
    }
  }
}

/** Target the first lane of each new epilogue phase after the complete real
  * reduction and first input/weight reread. No output DDR write can precede
  * these targets. Every request and matching real result is checked in order.
  */
trait GdnRmsNormFixedBankScalarEpilogueSupport extends GdnRmsNormFixedBankTestSupport {
  self: ChiselScalatestTester with Matchers =>
  import GdnRmsNormFixedBankReference._

  case class Cut(phase: Int, point: String, clearOnly: Boolean = false,
                 numerical: Boolean = false, targetBits: Option[BigInt] = None,
                 targetError: Boolean = false) {
    require(phase >= 0 && phase <= 2)
    require(Set("offer", "accepted", "held").contains(point))
    require(!clearOnly || point == "held")
    require(!numerical || (phase == 2 && point == "held" && !clearOnly))
    val target: Int = 4268 + phase
    val phaseName: String = Seq("normalize", "gamma", "weighted")(phase)
  }

  def runScalarPrefix(d: GdnRmsNormFixedBankScalarEpilogueHarness,
                      hidden: Seq[Int], weight: Seq[Int], label: String, cut: Cut): Unit = {
    require(!d.useVectorEpilogue && hidden.size == Width && weight.size == Width)
    val recipe = GdnRmsNormFixedBankReference(hidden, weight, useVectorEpilogue = false)
    cut.targetBits.foreach(expected => require(recipe.scalar(cut.target).result == expected))
    def beats(base: BigInt, values: Seq[Int]): Map[BigInt, BigInt] = values.grouped(32).zipWithIndex.map {
      case (xs, index) => (base + index * 64) -> pack(xs.map(BigInt(_)), 16)
    }.toMap
    val reads = beats(InputBase, hidden) ++ beats(WeightBase, weight)
    val readOrder = (0 until 64).map(i => InputBase + i * 64) ++
      (0 until 32).map(i => InputBase + i * 64) ++ (0 until 32).map(i => WeightBase + i * 64)
    var elapsed = 0; var memoryRequests = 0; var memoryResults = 0
    var scalarRequests = 0; var scalarResults = 0
    var pendingMemory = Option.empty[MemoryBeat]
    var pendingScalar = Option.empty[Int]
    var heldRequest = Option.empty[Seq[BigInt]]
    var heldResult = Option.empty[Seq[BigInt]]
    var offeredHoldCycles = 0; var acceptedWaitCycles = 0; var terminalHoldCycles = 0
    var cancelled = false; var earlyClear = false; var sawPreResultCancellation = false
    var targetAccepted = false; var targetRetired = false
    def bool(x: Bool): Boolean = x.peek().litToBoolean
    def request: Seq[BigInt] = Seq(d.io.scalarRequest.op.peek().litValue,
      d.io.scalarRequest.a.peek().litValue, d.io.scalarRequest.b.peek().litValue)
    def result: Seq[BigInt] = Seq(d.io.scalarResult.peek().litValue, d.io.scalarError.peek().litValue)
    def expectDebt(): Unit = {
      d.io.drained.expect(false.B); d.io.done.valid.expect(false.B)
      d.io.done.bits.outputCommitted.expect(false.B); d.io.job.ready.expect(false.B)
    }
    def cancelNow(): Unit = {
      require(!cut.numerical && !cancelled)
      if (cut.clearOnly) d.io.clear.poke(true.B) else d.io.abort.poke(true.B)
      cancelled = true
    }
    def step(): Unit = {
      assert(elapsed < 100000, s"$label timed out")
      d.reset.expect(false.B)
      d.io.abort.poke(false.B); d.io.clear.poke(false.B); d.io.scalarHold.poke(false.B)
      // Establish a held owner-side offer before allowing the genuine Scalar
      // handshake. The service interposer suppresses acceptance, not payload.
      // Do not gate the preceding primitive's still-outstanding result merely
      // because the next request ordinal already equals the target.
      if (!targetAccepted && scalarRequests == cut.target && pendingScalar.isEmpty) {
        d.io.scalarHold.poke(true.B)
        if (bool(d.io.scalarRequestValid)) {
          if (offeredHoldCycles < 8) {
            if (cut.point == "offer" && offeredHoldCycles == 1) cancelNow()
            if (cut.point == "offer" && offeredHoldCycles == 3) {
              d.io.clear.poke(true.B); earlyClear = true
            }
            d.io.scalarRequestAccepted.expect(false.B); expectDebt()
            offeredHoldCycles += 1
          } else d.io.scalarHold.poke(false.B)
        }
      }
      if (pendingScalar.contains(cut.target)) {
        d.io.scalarHold.poke(true.B)
        if (cut.point == "accepted" && acceptedWaitCycles == 0) {
          // This is the actual primitive's normal state immediately following
          // its real request.fire; no result has been fabricated or consumed.
          d.io.scalarResultValid.expect(false.B); d.io.scalarAluExecute.expect(true.B)
          cancelNow(); sawPreResultCancellation = true
        }
        if (bool(d.io.scalarResultValid)) {
          if (cut.point == "held" && terminalHoldCycles == 0 && !cut.numerical) cancelNow()
          if (!cut.numerical && terminalHoldCycles == 2) {
            d.io.clear.poke(true.B); earlyClear = true
          }
          if (terminalHoldCycles < 6) {
            d.io.scalarResultAccepted.expect(false.B); terminalHoldCycles += 1
          } else d.io.scalarHold.poke(false.B)
        }
        expectDebt(); acceptedWaitCycles += 1
      }
      heldRequest.foreach(old => assert(bool(d.io.scalarRequestValid) && request == old,
        "cancel/clear changed or withdrew an unaccepted Scalar offer"))
      heldResult.foreach(old => assert(bool(d.io.scalarResultValid) && result == old,
        "cancel/clear changed or withdrew the actual held Scalar terminal"))
      heldRequest = if (bool(d.io.scalarRequestValid) && !bool(d.io.scalarRequestReady)) Some(request) else None
      heldResult = if (bool(d.io.scalarResultValid) && !bool(d.io.scalarResultReady)) Some(result) else None

      d.io.loanRequestValid.expect(false.B); d.io.loanRequestAccepted.expect(false.B)
      d.io.loanResultValid.expect(false.B); d.io.loanResultAccepted.expect(false.B)
      d.io.loanBusy.expect(false.B); d.io.loanResetRequired.expect(false.B)
      d.io.elemAluExecute.expect(false.B); d.io.elemDdrActive.expect(false.B)
      d.controls.loanAbort.expect(false.B); d.controls.loanReset.expect(false.B)
      val memoryFire = bool(d.io.memory.valid) && bool(d.io.memory.ready)
      val scalarFire = bool(d.io.scalarRequestAccepted)
      assert(!(memoryFire && scalarFire), "more than one service accepted on an edge")
      if (pendingMemory.nonEmpty || pendingScalar.nonEmpty)
        assert(!memoryFire && !scalarFire, "new request while an earlier real service result is owed")
      if (scalarFire) {
        assert(scalarRequests <= cut.target && pendingScalar.isEmpty)
        val expected = recipe.scalar(scalarRequests)
        assert(request == Seq(BigInt(expected.op), expected.a, expected.b),
          s"$label Scalar request $scalarRequests differs from the independent recipe")
        pendingScalar = Some(scalarRequests)
        if (scalarRequests == cut.target) {
          assert(offeredHoldCycles == 8)
          targetAccepted = true
        }
        scalarRequests += 1
      }
      if (bool(d.io.scalarResultAccepted)) {
        assert(pendingScalar.nonEmpty, "unsolicited Scalar response")
        val index = pendingScalar.get
        d.io.scalarResult.expect(recipe.scalar(index).result.U)
        d.io.scalarError.expect((cut.numerical && index == cut.target && cut.targetError).B)
        if (index == cut.target) {
          assert(targetAccepted && terminalHoldCycles == 6 && !targetRetired)
          targetRetired = true
        }
        pendingScalar = None; scalarResults += 1
      }
      if (memoryFire) {
        val m = memoryBeat(d)
        assert(memoryRequests < readOrder.size && !m.write,
          "cancelled or failed first-lane epilogue must not issue an output write")
        assert(m.address == readOrder(memoryRequests) && m.mask == 0 && m.data == 0)
        assert(m.tag == ((JobTag << 32) | BigInt(memoryRequests)), "matching DDR sequence")
        pendingMemory = Some(m); memoryRequests += 1
      }
      if (bool(d.io.response.valid) && bool(d.io.response.ready)) {
        assert(pendingMemory.nonEmpty)
        d.io.response.bits.tag.expect(pendingMemory.get.tag.U)
        d.io.response.bits.data.expect(reads(pendingMemory.get.address).U)
        d.io.response.bits.error.expect(false.B)
        pendingMemory = None; memoryResults += 1
      }
      d.clock.step(); elapsed += 1
    }
    // No reset here: this is also called immediately after explicit recovery.
    d.io.abort.poke(false.B); d.io.clear.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.loanRequestHold.poke(false.B); d.io.loanResultHold.poke(false.B)
    d.io.loanInjectStrayTag.poke(false.B); d.io.memory.ready.poke(false.B)
    d.io.response.valid.poke(false.B); d.io.done.ready.poke(false.B)
    setJob(d); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(); d.io.job.valid.poke(false.B)
    while (!bool(d.io.done.valid) && elapsed < 100000) {
      if (!bool(d.io.memory.valid)) step()
      else {
        val m = memoryBeat(d)
        for (_ <- 0 until 2) {
          d.io.memory.valid.expect(true.B); assert(memoryBeat(d) == m); step()
        }
        d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
        assert(pendingMemory.contains(m)); step(); step()
        assert(pendingMemory.contains(m), "response delay erased DDR debt")
        d.io.response.bits.tag.poke(m.tag.U); d.io.response.bits.data.poke(reads(m.address).U)
        d.io.response.bits.error.poke(false.B); d.io.response.valid.poke(true.B)
        d.io.response.ready.expect(true.B); step(); d.io.response.valid.poke(false.B)
      }
    }
    assert(bool(d.io.done.valid) && targetAccepted && targetRetired)
    assert(pendingMemory.isEmpty && pendingScalar.isEmpty)
    assert(memoryRequests == 128 && memoryResults == 128)
    assert(scalarRequests == cut.target + 1 && scalarResults == cut.target + 1)
    assert(terminalHoldCycles == 6 && offeredHoldCycles == 8)
    if (!cut.numerical) {
      assert(cancelled && earlyClear, "cancel plus early clear must occur while real debt is held")
      if (cut.point == "accepted") assert(sawPreResultCancellation)
    } else assert(!cancelled && !earlyClear)
    val expectedStatus = if (cut.numerical) Status.Numerical else ElementwiseLoanOp.Aborted
    d.io.done.bits.tag.expect(JobTag.U); d.io.done.bits.status.expect(expectedStatus.U)
    d.io.done.bits.writeBytes.expect(0.U); d.io.done.bits.outputCommitted.expect(false.B)
    d.io.drained.expect(true.B); d.io.resetRequired.expect(true.B)
    val held = completion(d)
    for (_ <- 0 until 7) {
      d.io.done.valid.expect(true.B); d.io.job.ready.expect(false.B)
      assert(completion(d) == held); step()
    }
    d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
    d.io.locked.expect(true.B); d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B)
    d.io.drained.expect(true.B); d.io.loanResetRequired.expect(false.B)
    println(s"H2048_SCALAR_EPILOGUE_DIRECTED label=$label phase=${cut.phaseName} point=${cut.point} " +
      s"status=$expectedStatus scalar_requests=$scalarRequests scalar_results=$scalarResults " +
      s"read_requests=$memoryRequests read_results=$memoryResults writes=0 offered_hold=$offeredHoldCycles " +
      s"actual_terminal_hold=$terminalHoldCycles actual_scalar=true production_core=true module_reset=false")
  }

  /** Early clear is not remembered as permission to reopen the owner. Recovery
    * must happen after its failed completion retires and all real debt drains.
    */
  def clearScalarFailure(d: GdnRmsNormFixedBankScalarEpilogueHarness, label: String): Unit = {
    d.reset.expect(false.B)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.abort.poke(false.B); d.io.clear.poke(false.B); d.io.scalarHold.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    var resetPulses = 0
    def quietStep(): Unit = {
      d.reset.expect(false.B); d.io.drained.expect(true.B)
      d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
      d.io.scalarResultValid.expect(false.B); d.io.loanRequestValid.expect(false.B)
      d.io.loanResultValid.expect(false.B); d.io.loanBusy.expect(false.B)
      d.io.done.valid.expect(false.B); d.controls.loanAbort.expect(false.B)
      d.io.loanResetRequired.expect(false.B)
      if (d.controls.loanReset.peek().litToBoolean) resetPulses += 1
      d.clock.step()
    }
    for (_ <- 0 until 5) {
      d.io.locked.expect(true.B); d.io.resetRequired.expect(true.B); d.io.job.ready.expect(false.B)
      d.controls.loanReset.expect(false.B); quietStep()
    }
    d.io.clear.poke(true.B); quietStep(); d.io.clear.poke(false.B)
    var guard = 0
    while (!d.io.job.ready.peek().litToBoolean && guard < 12) { quietStep(); guard += 1 }
    assert(guard < 12 && resetPulses == 1, "explicit clear must complete exactly one recovery pulse")
    d.io.job.ready.expect(true.B); d.io.locked.expect(false.B); d.io.resetRequired.expect(false.B)
    for (_ <- 0 until 3) { d.controls.loanReset.expect(false.B); quietStep() }
    assert(resetPulses == 1)
    println(s"H2048_SCALAR_EPILOGUE_CLEAR label=$label module_reset=false recovered=true reset_pulses=$resetPulses")
  }
}
