// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Observation only: the existing harness still supplies both real services.
  * No changes to the owner, arithmetic, response values, or drain are made. */
class GdnRmsNormFixedBankCancellationHarness(productionCore: Boolean = false)
    extends GdnRmsNormFixedBankArithmeticHarness(productionCore) {
  val loanControls = IO(new Bundle {
    val abort = Output(Bool())
    val resetLoan = Output(Bool())
  })
  loanControls.abort := loanService.abort
  loanControls.resetLoan := loanService.resetLoan
}

/** Additive cancellation coverage. The original run(), its fault cases, and
  * all of its arithmetic/accounting assertions remain unchanged. */
trait GdnRmsNormFixedBankCancellationTestSupport extends GdnRmsNormFixedBankTestSupport {
  self: ChiselScalatestTester with Matchers =>
  import GdnRmsNormFixedBankReference._

  def runCancellation(d: GdnRmsNormFixedBankCancellationHarness,
                      hidden: Seq[Int], weight: Seq[Int], label: String,
                      fault: String): RunReport = {
    require(Set("scalar-pending", "loan-offer", "loan-terminal", "success-done").contains(fault))
    require(hidden.size == Width && weight.size == Width, "cancellation fixture is M1/H2048")
    val loanCancellation = fault == "loan-offer" || fault == "loan-terminal"
    val recipe = GdnRmsNormFixedBankReference(hidden, weight)
    def beats(base: BigInt, values: Seq[Int]): Map[BigInt, BigInt] = values.grouped(32).zipWithIndex.map {
      case (xs, index) => (base + index * 64) -> pack(xs.map(BigInt(_)), 16)
    }.toMap
    val readData = beats(InputBase, hidden) ++ beats(WeightBase, weight)
    val expectedWrites = beats(OutputBase, recipe.output)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    val memoryOrder = (0 until 64).map(i => (false, InputBase + i * 64)) ++
      (0 until 2).flatMap { chunk =>
        (0 until 32).map(i => (false, InputBase + chunk * 2048 + i * 64)) ++
          (0 until 32).map(i => (false, WeightBase + chunk * 2048 + i * 64)) ++
          (0 until 32).map(i => (true, OutputBase + chunk * 2048 + i * 64))
      }
    var elapsed = 0
    var issued = 0; var reads = 0; var writes = 0; var writeAcks = 0
    var scalarRequests = 0; var scalarResults = 0; var loans = 0; var loanResults = 0
    var pendingMemory = Option.empty[MemoryBeat]
    var pendingScalar = Option.empty[Int]
    var pendingLoan = Option.empty[(Int, BigInt)]
    var heldScalarRequest = Option.empty[Seq[BigInt]]
    var heldScalarResult = Option.empty[Seq[BigInt]]
    var heldLoanRequest = Option.empty[Seq[BigInt]]
    var heldLoanResult = Option.empty[Seq[BigInt]]
    var scalarStalls = 0; var loanRequestStalls = 0; var loanResultStalls = 0
    var injected = false
    var scalarHoldRemaining = 0; var scalarDebtHoldCycles = 0; var scalarTerminalHoldCycles = 0
    var offerHoldRemaining = 0; var cancelledOfferHoldCycles = 0
    var drainHoldRemaining = 0; var loanDrainHoldCycles = 0
    var loanAbortPulses = 0; var replacedHeldSuccesses = 0
    var expectAbortTerminal = Option.empty[BigInt]
    var injectedStray = false; var strayPackets = 0; var debtCyclesAfterStray = 0
    var sawHeldLoanSuccess = false
    def bool(x: Bool): Boolean = x.peek().litToBoolean
    def scalarRequest: Seq[BigInt] = Seq(d.io.scalarRequest.op.peek().litValue,
      d.io.scalarRequest.a.peek().litValue, d.io.scalarRequest.b.peek().litValue)
    def loanRequest: Seq[BigInt] = Seq(d.io.loanRequest.tag.peek().litValue,
      d.io.loanRequest.op.peek().litValue, d.io.loanRequest.a.peek().litValue,
      d.io.loanRequest.b.peek().litValue, d.io.loanRequest.inverse.peek().litValue)
    def loanResult: Seq[BigInt] = Seq(d.io.loanResult.tag.peek().litValue,
      d.io.loanResult.status.peek().litValue, d.io.loanResult.value.peek().litValue)
    def expectDebt(): Unit = {
      d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
      d.io.drained.expect(false.B); d.io.job.ready.expect(false.B)
    }
    def step(n: Int = 1): Unit = for (_ <- 0 until n) {
      assert(elapsed < 250000, s"$label timed out")
      d.io.scalarHold.poke((elapsed % 23 < 5 || (scalarRequests == 0 && scalarStalls < 3)).B)
      d.io.loanRequestHold.poke((elapsed % 17 < 4 || (loans == 0 && loanRequestStalls < 3)).B)
      d.io.loanResultHold.poke((elapsed % 19 < 6 || (loanResults == 0 && loanResultStalls < 3)).B)
      d.io.loanInjectStrayTag.poke(false.B)
      // Manual held-done cancellation below controls its own abort input.
      if (fault != "success-done") {
        d.io.abort.poke(false.B); d.io.clear.poke(false.B)
      }
      if (fault == "scalar-pending" && !injected && pendingScalar.nonEmpty) {
        assert(scalarRequests == 1 && scalarResults == 0,
          "Scalar cancellation must follow a real accepted request")
        injected = true; scalarHoldRemaining = 20; d.io.abort.poke(true.B)
      }
      if (scalarHoldRemaining > 0) {
        d.io.scalarHold.poke(true.B)
        assert(pendingScalar.nonEmpty, "abort/clear erased accepted Scalar debt")
        expectDebt()
        if (scalarHoldRemaining == 17) d.io.clear.poke(true.B)
        if (bool(d.io.scalarResultValid)) {
          d.io.scalarResult.expect(recipe.scalar(pendingScalar.get).result.U)
          d.io.scalarError.expect(false.B); scalarTerminalHoldCycles += 1
        }
        scalarDebtHoldCycles += 1; scalarHoldRemaining -= 1
      }
      if (fault == "loan-offer" && !injected && bool(d.io.loanRequestValid)) {
        assert(loans == 0 && pendingLoan.isEmpty, "offer cancellation must precede acceptance")
        injected = true; offerHoldRemaining = 20; d.io.abort.poke(true.B)
      }
      if (offerHoldRemaining > 0) {
        d.io.loanRequestHold.poke(true.B)
        d.io.loanRequestValid.expect(true.B); d.io.loanRequestAccepted.expect(false.B)
        d.loanControls.abort.expect(false.B); d.loanControls.resetLoan.expect(false.B)
        assert(loans == 0 && pendingLoan.isEmpty, "a held offer was accepted behind the interposer")
        expectDebt()
        if (offerHoldRemaining == 17) d.io.clear.poke(true.B)
        cancelledOfferHoldCycles += 1; offerHoldRemaining -= 1
      } else if (fault == "loan-offer" && injected && loans == 0) {
        // The real request must still be accepted after the cancelled hold.
        d.io.loanRequestHold.poke(false.B)
      }
      if (fault == "loan-terminal" && !injected && bool(d.io.loanResultValid)) {
        assert(pendingLoan.nonEmpty && loans == 1 && loanResults == 0,
          "held-terminal cancellation needs a real outstanding loan")
        val (index, tag) = pendingLoan.get
        d.io.loanResult.tag.expect(tag.U); d.io.loanResult.status.expect(Status.Ok.U)
        d.io.loanResult.value.expect(recipe.loan(index).result.U)
        d.io.loanResultHold.poke(true.B); d.io.abort.poke(true.B)
        injected = true; sawHeldLoanSuccess = true
      }
      val actualLoanAbort = bool(d.loanControls.abort)
      expectAbortTerminal.foreach { tag =>
        assert(!actualLoanAbort, "loan abort must be one pulse, not sticky")
        d.io.loanResultValid.expect(true.B)
        d.io.loanResult.tag.expect(tag.U)
        d.io.loanResult.status.expect(ElementwiseLoanOp.Aborted.U)
        d.io.loanResult.value.expect(0.U)
        d.io.loanResetRequired.expect(true.B)
        assert(pendingLoan.exists(_._2 == tag), "abort replacement lost the expected loan tag")
      }
      expectAbortTerminal = None
      if (actualLoanAbort) {
        assert(loanCancellation && injected && loans == 1 && pendingLoan.nonEmpty,
          "abort pulse must follow acceptance of this real cancelled loan")
        assert(loanAbortPulses == 0, "exactly one loan abort pulse is permitted")
        d.io.loanRequestValid.expect(false.B); d.io.loanRequestAccepted.expect(false.B)
        d.io.loanResultValid.expect(false.B); d.io.loanResultAccepted.expect(false.B)
        expectAbortTerminal = Some(pendingLoan.get._2)
        loanAbortPulses += 1; drainHoldRemaining = 20
      }
      if (drainHoldRemaining > 0) {
        d.io.loanResultHold.poke(true.B)
        assert(pendingLoan.nonEmpty, "abort/stray terminal discharged matching-result debt")
        expectDebt(); d.io.loanBusy.expect(true.B)
        if (loanAbortPulses == 1 && bool(d.io.loanResultValid) && !injectedStray) {
          // Copy the actual aborted terminal with a wrong tag. The actual
          // service terminal stays held and must still be drained later.
          d.io.loanInjectStrayTag.poke(true.B)
          d.io.loanStrayAccepted.expect(true.B); d.io.loanResultAccepted.expect(false.B)
          injectedStray = true
        } else if (injectedStray) debtCyclesAfterStray += 1
        loanDrainHoldCycles += 1; drainHoldRemaining -= 1
      }
      d.loanControls.resetLoan.expect(false.B)
      heldScalarRequest.foreach { old =>
        assert(bool(d.io.scalarRequestValid) && scalarRequest == old, "Scalar request changed while stalled")
      }
      val scalarResult = Seq(d.io.scalarResult.peek().litValue, d.io.scalarError.peek().litValue)
      heldScalarResult.foreach { old =>
        assert(bool(d.io.scalarResultValid) && scalarResult == old, "Scalar result changed while held")
      }
      heldLoanRequest.foreach { old =>
        assert(bool(d.io.loanRequestValid) && loanRequest == old, "loan offer changed while stalled/cancelled")
      }
      heldLoanResult.foreach { old =>
        if (actualLoanAbort) {
          // A service abort intentionally suppresses valid for one edge and
          // replaces success with Aborted/zero. This is the ONLY exception.
          assert(fault == "loan-terminal" && sawHeldLoanSuccess && old(1) == BigInt(Status.Ok),
            "unexpected replacement of a held loan result")
          assert(!bool(d.io.loanResultValid) && loanResult == old,
            "held success changed before the actual abort edge")
          replacedHeldSuccesses += 1
        } else {
          assert(bool(d.io.loanResultValid) && loanResult == old, "loan result changed while held")
        }
      }
      heldScalarRequest = if (bool(d.io.scalarRequestValid) && !bool(d.io.scalarRequestReady)) {
        scalarStalls += 1; Some(scalarRequest)
      } else None
      heldScalarResult = if (bool(d.io.scalarResultValid) && !bool(d.io.scalarResultReady)) Some(scalarResult) else None
      heldLoanRequest = if (bool(d.io.loanRequestValid) && !bool(d.io.loanRequestReady)) {
        loanRequestStalls += 1; Some(loanRequest)
      } else None
      heldLoanResult = if (bool(d.io.loanResultValid) && !bool(d.io.loanResultReady)) {
        loanResultStalls += 1; Some(loanResult)
      } else None
      val memoryAccept = bool(d.io.memory.valid) && bool(d.io.memory.ready)
      val anyServiceAccept = memoryAccept || bool(d.io.scalarRequestAccepted) || bool(d.io.loanRequestAccepted)
      assert(Seq(memoryAccept, bool(d.io.scalarRequestAccepted), bool(d.io.loanRequestAccepted)).count(x => x) <= 1,
        "multiple service requests accepted on one edge")
      if (pendingMemory.nonEmpty || pendingScalar.nonEmpty || pendingLoan.nonEmpty)
        assert(!anyServiceAccept, "new service request while a prior transaction remains outstanding")
      if (bool(d.io.scalarRequestAccepted)) {
        assert(pendingScalar.isEmpty && scalarRequests < recipe.scalar.size, "Scalar ownership/count")
        val expected = recipe.scalar(scalarRequests)
        assert(scalarRequest == Seq(BigInt(expected.op), expected.a, expected.b),
          s"$label Scalar request $scalarRequests differs from independent reduction recipe")
        pendingScalar = Some(scalarRequests); scalarRequests += 1
      }
      if (bool(d.io.scalarResultAccepted)) {
        assert(pendingScalar.nonEmpty, "unsolicited Scalar result")
        d.io.scalarError.expect(false.B)
        d.io.scalarResult.expect(recipe.scalar(pendingScalar.get).result.U)
        pendingScalar = None; scalarResults += 1
      }
      if (bool(d.io.loanRequestAccepted)) {
        assert(pendingLoan.isEmpty && loans < recipe.loan.size, "loan ownership/count")
        if (fault == "loan-offer") assert(injected && cancelledOfferHoldCycles == 20,
          "cancelled offer must survive all hold cycles before actual acceptance")
        val expected = recipe.loan(loans)
        d.io.loanRequest.tag.expect((issued + loanResults).U)
        d.io.loanRequest.op.expect(ElementwiseLoanOp.RmsEpilogue.U)
        d.io.loanRequest.a.expect(expected.a.U); d.io.loanRequest.b.expect(expected.b.U)
        d.io.loanRequest.inverse.expect(expected.inverse.U)
        pendingLoan = Some((loans, d.io.loanRequest.tag.peek().litValue)); loans += 1
      }
      if (bool(d.io.loanResultAccepted)) {
        assert(pendingLoan.nonEmpty, "unsolicited loan result")
        val (index, tag) = pendingLoan.get
        d.io.loanResult.tag.expect(tag.U)
        if (loanCancellation) {
          assert(loanAbortPulses == 1 && injectedStray && debtCyclesAfterStray >= 10,
            "cancelled loan must preserve debt through abort and the stray-tag drain interval")
          d.io.loanResult.status.expect(ElementwiseLoanOp.Aborted.U); d.io.loanResult.value.expect(0.U)
        } else {
          d.io.loanResult.status.expect(Status.Ok.U)
          d.io.loanResult.value.expect(recipe.loan(index).result.U)
        }
        pendingLoan = None; loanResults += 1
      }
      if (bool(d.io.loanStrayAccepted)) {
        assert(pendingLoan.nonEmpty && !bool(d.io.loanResultAccepted),
          "stray packet must not retire the real matching-tag loan terminal")
        strayPackets += 1
      }
      if (pendingMemory.nonEmpty) {
        d.io.memory.valid.expect(false.B); expectDebt()
      }
      if (memoryAccept) {
        assert(pendingMemory.isEmpty && issued < memoryOrder.size, "more than one DDR request outstanding")
        val request = memoryBeat(d)
        assert(request.tag == ((JobTag << 32) | (issued + loanResults)), "DDR/loan retirement sequence tag")
        assert((request.write, request.address) == memoryOrder(issued), s"$label DDR schedule at beat $issued")
        if (request.write) {
          assert(request.data == expectedWrites(request.address), s"$label BF16 write data at ${request.address}")
          assert(request.mask == FullMask && !committed.contains(request.address), "write mask/duplicate staging write")
          writes += 1
        } else {
          assert(readData.contains(request.address) && request.mask == 0, "read address/mask")
          reads += 1
        }
        pendingMemory = Some(request); issued += 1
      }
      if (bool(d.io.response.valid) && bool(d.io.response.ready)) {
        assert(pendingMemory.nonEmpty, "response without an accepted DDR request")
        val request = pendingMemory.get
        // A mismatched response would never discharge expected-tag debt.
        if (d.io.response.bits.tag.peek().litValue == request.tag) {
          if (request.write && !bool(d.io.response.bits.error)) {
            committed(request.address) = request.data; writeAcks += 1
          }
          pendingMemory = None
        }
      }
      d.clock.step(); elapsed += 1
    }
    def respond(request: MemoryBeat): Unit = {
      d.io.response.bits.data.poke((if (request.write) BigInt(0) else readData(request.address)).U)
      d.io.response.bits.tag.poke(request.tag.U); d.io.response.bits.error.poke(false.B)
      d.io.response.valid.poke(true.B)
      var guard = 0
      while (!bool(d.io.response.ready) && guard < 100) { step(); guard += 1 }
      assert(guard < 100, "owner did not accept the outstanding real DDR response")
      step(); d.io.response.valid.poke(false.B)
    }
    // Deliberately no reset: callers may invoke this immediately after clear.
    d.io.abort.poke(false.B); d.io.clear.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B); d.io.done.ready.poke(false.B)
    setJob(d); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(); d.io.job.valid.poke(false.B)
    while (!bool(d.io.done.valid) && elapsed < 250000) {
      if (!bool(d.io.memory.valid)) step()
      else {
        val request = memoryBeat(d)
        val delay = 2 + issued % 5
        for (_ <- 0 until delay) {
          d.io.memory.valid.expect(true.B)
          assert(memoryBeat(d) == request, "DDR request changed under backpressure")
          step()
        }
        d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
        assert(pendingMemory.contains(request), "accepted request must create DDR debt")
        val last = request.write && request.address == OutputBase + 4096 - 64
        step(if (last) 37 else delay)
        assert(pendingMemory.contains(request), "delay must retain the actual DDR obligation")
        respond(request)
      }
    }
    assert(bool(d.io.done.valid), s"$label completion timeout")
    assert(pendingMemory.isEmpty && pendingScalar.isEmpty && pendingLoan.isEmpty, "done before drain")
    d.io.loanBusy.expect(false.B); d.io.drained.expect(true.B)
    if (fault == "success-done") {
      d.io.done.bits.status.expect(Status.Ok.U); d.io.done.bits.outputCommitted.expect(true.B)
      d.io.done.bits.writeBytes.expect(4096.U)
      assert(reads == 192 && writes == 64 && writeAcks == 64, "M1 H2048 DDR accounting")
      assert(scalarRequests == 4268 && scalarResults == 4268, "exact Scalar accounting")
      assert(loans == 128 && loanResults == 128, "exact register-loan accounting")
      assert(committed.toMap == expectedWrites, "all exact BF16 output beats must have real successful ACKs")
      assert(scalarStalls > 0 && loanRequestStalls > 0 && loanResultStalls > 0,
        "all three service backpressure controls must be exercised")
      val success = completion(d)
      for (_ <- 0 until 7) {
        d.io.done.valid.expect(true.B); d.io.job.ready.expect(false.B)
        assert(completion(d) == success, "held successful completion changed before cancellation")
        step()
      }
      // Competing ready cannot publish success on the cancellation edge.
      d.io.abort.poke(true.B); d.io.done.ready.poke(true.B)
      d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
      step(); d.io.done.ready.poke(false.B); d.io.abort.poke(false.B)
      d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(ElementwiseLoanOp.Aborted.U)
      assert(completion(d)(0) == success(0) && completion(d)(2) == success(2) && completion(d)(3) == success(3),
        "cancelled held success must retain tag, ACKed bytes, and frozen cycle count")
      injected = true
    } else if (fault == "scalar-pending") {
      assert(scalarRequests == 1 && scalarResults == 1 && reads == 32 && writes == 0,
        "Scalar cancellation must drain exactly the accepted first request")
      assert(scalarDebtHoldCycles == 20 && scalarTerminalHoldCycles > 0,
        "real Scalar result/debt must remain held through abort and clear")
      assert(loans == 0 && loanResults == 0, "Scalar cancellation must not start a loan")
    } else {
      assert(reads == 128 && writes == 0 && writeAcks == 0, "loan cancellation must not publish a staging write")
      assert(scalarRequests == 4268 && scalarResults == 4268, "exact Scalar prefix before cancelled loan")
      assert(loans == 1 && loanResults == 1 && loanAbortPulses == 1,
        "cancelled loan must accept once, abort once, and drain once")
      assert(strayPackets == 1 && loanDrainHoldCycles == 20 && debtCyclesAfterStray >= 10,
        "wrong-tag packet cannot replace drain of the actual aborted loan terminal")
      if (fault == "loan-offer") assert(cancelledOfferHoldCycles == 20 && replacedHeldSuccesses == 0,
        "unaccepted offer must survive cancellation before real acceptance")
      if (fault == "loan-terminal") assert(sawHeldLoanSuccess && replacedHeldSuccesses == 1,
        "exact real success terminal must be replaced exactly once by actual service abort")
    }
    assert(injected, s"$label cancellation was not exercised")
    if (!loanCancellation) assert(loanAbortPulses == 0 && strayPackets == 0,
      "non-loan cancellation must not manufacture a loan abort/drain")
    d.io.done.bits.status.expect(ElementwiseLoanOp.Aborted.U); d.io.done.bits.tag.expect(JobTag.U)
    d.io.done.bits.writeBytes.expect((writeAcks * 64).U); d.io.done.bits.outputCommitted.expect(false.B)
    d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B); d.io.loanRequestValid.expect(false.B)
    val held = completion(d)
    for (_ <- 0 until 13) {
      d.io.done.valid.expect(true.B); d.io.job.ready.expect(false.B)
      assert(completion(d) == held, "aborted completion changed under backpressure")
      step()
    }
    d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B); d.io.locked.expect(true.B)
    d.io.loanResetRequired.expect(loanCancellation.B)
    d.io.drained.expect(true.B); d.io.loanBusy.expect(false.B)
    val output = committed.toSeq.sortBy(_._1).flatMap { case (_, beat) =>
      (0 until 32).map(lane => ((beat >> (lane * 16)) & 65535).toInt)
    }
    println(s"GDN_RMSNORM_FIXED_BANK_CANCEL_RTL label=$label fault=$fault status=${ElementwiseLoanOp.Aborted} reads=$reads writes=$writes write_acks=$writeAcks scalar_requests=$scalarRequests scalar_results=$scalarResults loans=$loans loan_results=$loanResults loan_abort_pulses=$loanAbortPulses wrong_tag_packets=$strayPackets replaced_held_success=$replacedHeldSuccesses cycles=${held(3)} actual_scalar=true actual_loan=true")
    RunReport(output, reads, writes, writeAcks, scalarRequests, scalarResults, loans, loanResults, held(3))
  }

  /** Only use after an actual aborted-loan terminal has drained and its owner
    * completion has retired. No reset is asserted anywhere in this helper. */
  def clearRealLoanPoison(d: GdnRmsNormFixedBankCancellationHarness, label: String): Unit = {
    d.reset.expect(false.B)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.loanRequestHold.poke(false.B); d.io.loanResultHold.poke(false.B)
    d.io.loanInjectStrayTag.poke(false.B); d.io.abort.poke(false.B); d.io.clear.poke(false.B)
    d.io.locked.expect(true.B); d.io.resetRequired.expect(true.B); d.io.loanResetRequired.expect(true.B)
    d.io.job.ready.expect(false.B); d.io.done.valid.expect(false.B)
    d.io.drained.expect(true.B); d.io.loanBusy.expect(false.B)
    var pulses = 0
    def quietStep(): Unit = {
      d.reset.expect(false.B)
      d.io.drained.expect(true.B); d.io.loanBusy.expect(false.B)
      d.io.memory.valid.expect(false.B); d.io.response.valid.expect(false.B)
      d.io.scalarRequestValid.expect(false.B); d.io.scalarResultValid.expect(false.B)
      d.io.loanRequestValid.expect(false.B); d.io.loanResultValid.expect(false.B)
      d.io.done.valid.expect(false.B); d.loanControls.abort.expect(false.B)
      if (d.loanControls.resetLoan.peek().litToBoolean) pulses += 1
      d.clock.step()
    }
    // Sticky poison must not clear merely because every real response drained.
    for (_ <- 0 until 7) {
      d.io.loanResetRequired.expect(true.B); d.io.job.ready.expect(false.B)
      d.loanControls.resetLoan.expect(false.B); quietStep()
    }
    d.io.clear.poke(true.B); quietStep(); d.io.clear.poke(false.B)
    var guard = 0
    while (!d.io.job.ready.peek().litToBoolean && guard < 12) {
      d.io.locked.expect(true.B); quietStep(); guard += 1
    }
    assert(guard < 12 && pulses == 1, "explicit clear must issue exactly one real loan recovery pulse")
    d.io.job.ready.expect(true.B); d.io.locked.expect(false.B)
    d.io.resetRequired.expect(false.B); d.io.loanResetRequired.expect(false.B)
    for (_ <- 0 until 7) {
      d.io.job.ready.expect(true.B); d.loanControls.resetLoan.expect(false.B); quietStep()
    }
    assert(pulses == 1, "loan recovery pulse must not repeat after clear deassertion")
    println(s"GDN_RMSNORM_FIXED_BANK_CLEAR_RTL label=$label loan_origin_poison=true loan_reset_pulses=$pulses module_reset=false recovered=true")
  }

  def exerciseCancellationPaths(d: GdnRmsNormFixedBankCancellationHarness, label: String): Unit = {
    val (hidden, weight) = GdnRmsNormFixedBankReference.synthetic
    init(d)
    runCancellation(d, hidden, weight, label + "-scalar-pending", "scalar-pending")
    init(d) // Previous real Scalar response and failed done have both retired.
    runCancellation(d, hidden, weight, label + "-loan-offer", "loan-offer")
    clearRealLoanPoison(d, label + "-clear-offer")
    // Same physical services, no module reset: actual next-job acceptance and
    // exact full Scalar reduction precede another actual successful loan.
    runCancellation(d, hidden, weight, label + "-loan-terminal-after-clear", "loan-terminal")
    clearRealLoanPoison(d, label + "-clear-terminal")
    // Full real computation and all 64 ACKs prove reuse after loan-origin
    // poison; cancellation then races ready on the held successful done.
    val report = runCancellation(d, hidden, weight, label + "-held-done-after-clear", "success-done")
    assert(report.output == GdnRmsNormFixedBankReference(hidden, weight).output)
  }
}

class GdnRmsNormFixedBankCancellationSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankCancellationTestSupport {
  "GdnRmsNormFixedBankOwner" should "retain real cancelled debt and clear real loan poison without module reset" in {
    test(new GdnRmsNormFixedBankCancellationHarness)
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
        exerciseCancellationPaths(d, "standalone-cancellation")
      }
  }
}
