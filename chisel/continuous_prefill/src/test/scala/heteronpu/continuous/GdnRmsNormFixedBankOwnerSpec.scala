// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.p0.LocalSramConfig
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Both arithmetic services are production RTL. The test can delay handshakes,
  * but cannot supply a Scalar or register-loan arithmetic result. */
class GdnRmsNormFixedBankArithmeticHarness(productionCore: Boolean = false) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnRmsNormJob))
    val done = Decoupled(new GdnRmsNormResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val abort = Input(Bool())
    val clear = Input(Bool())
    val drained = Output(Bool())
    val locked = Output(Bool())
    val resetRequired = Output(Bool())
    val scalarHold = Input(Bool())
    val loanRequestHold = Input(Bool())
    val loanResultHold = Input(Bool())
    // Protocol-only injection: copy the real held terminal with a stray tag,
    // without acknowledging or replacing the actual arithmetic terminal.
    val loanInjectStrayTag = Input(Bool())
    val loanStrayAccepted = Output(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestValid = Output(Bool())
    val scalarRequestReady = Output(Bool())
    val scalarRequestAccepted = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultValid = Output(Bool())
    val scalarResultReady = Output(Bool())
    val scalarResultAccepted = Output(Bool())
    val scalarError = Output(Bool())
    val loanRequest = Output(new ElementwiseLoanRequest)
    val loanRequestValid = Output(Bool())
    val loanRequestReady = Output(Bool())
    val loanRequestAccepted = Output(Bool())
    val loanResult = Output(new ElementwiseLoanResult)
    val loanResultValid = Output(Bool())
    val loanResultReady = Output(Bool())
    val loanResultAccepted = Output(Bool())
    val loanBusy = Output(Bool())
    val loanResetRequired = Output(Bool())
  })
  val owner = Module(new GdnRmsNormFixedBankOwner())
  val arithmetic = Wire(new GdnScalarClient)
  val loanService = Wire(Flipped(new ElementwiseLoanPort))
  val vectorUnavailable = Wire(Bool())
  if (productionCore) {
    // The original core's exact default elementwise bank configuration is kept.
    // This small legacy shape bounds unrelated core logic; no full-block claim.
    val shape = QwenBlockShape(64, 128, 2, 1, 32, 16)
    val core = Module(new Qwen2ContinuousBlock(shape, ownerDriven = true,
      externalScalar = true, externalElementwiseLoan = true))
    core.io.launch.valid := false.B; core.io.launch.bits := 0.U.asTypeOf(core.io.launch.bits)
    core.io.ownerJob.get.valid := false.B
    core.io.ownerJob.get.bits := 0.U.asTypeOf(core.io.ownerJob.get.bits)
    core.io.result.ready := false.B; core.io.memory.ready := false.B
    core.io.response.valid := false.B; core.io.response.bits := 0.U.asTypeOf(core.io.response.bits)
    core.io.scalarService.get <> arithmetic
    core.io.elementwiseLoan.get <> loanService
    vectorUnavailable := core.io.elementwiseResetRequired.get
    assert(!core.io.memory.valid && !core.io.response.ready && !core.io.result.valid,
      "RMS borrower must not activate the legacy core DDR path")
    when(loanService.request.valid || loanService.busy || loanService.result.valid ||
      vectorUnavailable || loanService.abort || loanService.resetLoan) {
      assert(!core.io.ownerJob.get.ready, "core admission must exclude loan offers, debt, and poison")
    }
  } else {
    val scalar = Module(new BlockScalarFloat)
    scalar.io.request <> arithmetic.request; arithmetic.result <> scalar.io.result
    arithmetic.error := scalar.io.error
    val lender = Module(new ElementwiseRegisterLoan(
      ChainConfig(tileElements = 32), LocalSramConfig(rowsPerBank = 2, addressBits = 3)))
    lender.loan <> loanService
    vectorUnavailable := lender.io.resetRequired
    lender.io.job.valid := false.B
    lender.io.job.bits := 0.U.asTypeOf(lender.io.job.bits)
    lender.io.done.ready := false.B; lender.io.memory.ready := false.B
    lender.io.response.valid := false.B; lender.io.response.bits := 0.U.asTypeOf(lender.io.response.bits)
    assert(!lender.io.memory.valid && !lender.io.response.ready && !lender.io.done.valid,
      "RMS register borrower must not activate the lender DDR path")
  }

  owner.io.job <> io.job
  io.done <> owner.io.done
  io.memory <> owner.io.memory
  owner.io.response <> io.response
  owner.io.abort := io.abort
  owner.io.clear := io.clear
  io.drained := owner.io.drained
  io.locked := owner.io.locked
  io.resetRequired := owner.io.resetRequired
  owner.io.vectorUnavailable := vectorUnavailable

  arithmetic.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  arithmetic.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := arithmetic.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := arithmetic.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := arithmetic.result.bits
  owner.io.scalar.error := arithmetic.error
  arithmetic.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := owner.io.scalar.request.bits
  io.scalarRequestValid := owner.io.scalar.request.valid
  io.scalarRequestReady := owner.io.scalar.request.ready
  io.scalarRequestAccepted := arithmetic.request.fire
  io.scalarResult := arithmetic.result.bits
  io.scalarResultValid := arithmetic.result.valid
  io.scalarResultReady := arithmetic.result.ready
  io.scalarResultAccepted := arithmetic.result.fire
  io.scalarError := arithmetic.error

  loanService.request.valid := owner.io.loan.request.valid && !io.loanRequestHold
  loanService.request.bits := owner.io.loan.request.bits
  owner.io.loan.request.ready := loanService.request.ready && !io.loanRequestHold
  owner.io.loan.result.valid := loanService.result.valid && (io.loanInjectStrayTag || !io.loanResultHold)
  owner.io.loan.result.bits := loanService.result.bits
  owner.io.loan.result.bits.tag := loanService.result.bits.tag ^ io.loanInjectStrayTag.asUInt
  loanService.result.ready := owner.io.loan.result.ready && !io.loanResultHold && !io.loanInjectStrayTag
  loanService.abort := owner.io.loan.abort
  loanService.resetLoan := owner.io.loan.resetLoan
  owner.io.loan.busy := loanService.busy
  owner.io.loan.resetRequired := loanService.resetRequired
  io.loanRequest := owner.io.loan.request.bits
  io.loanRequestValid := owner.io.loan.request.valid
  io.loanRequestReady := owner.io.loan.request.ready
  io.loanRequestAccepted := loanService.request.fire
  io.loanResult := loanService.result.bits
  io.loanResultValid := loanService.result.valid
  io.loanResultReady := loanService.result.ready
  io.loanResultAccepted := loanService.result.fire
  io.loanStrayAccepted := owner.io.loan.result.fire && io.loanInjectStrayTag
  io.loanBusy := loanService.busy
  io.loanResetRequired := loanService.resetRequired

}

/** Independent host-only recipe. Values calculated here are used solely by
  * assertions; none are connected to either arithmetic service's response. */
object GdnRmsNormFixedBankReference {
  val Width = 2048
  val InputBase = BigInt("310000000", 16)
  val WeightBase = BigInt("320000000", 16)
  val OutputBase = BigInt("330000000", 16)
  val JobTag = BigInt("89abcdef", 16)
  val FullMask = (BigInt(1) << 64) - 1
  def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  def bf(x: Float): Int = {
    val raw = bits(x).toLong
    (((raw + 0x7fffL + ((raw >>> 16) & 1L)) & 0xffffffffL) >>> 16).toInt
  }
  def pack(xs: Seq[BigInt], width: Int): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (acc, (value, index)) => acc | (value << (width * index))
  }
  case class ScalarStep(op: Int, a: BigInt, b: BigInt, result: BigInt)
  case class LoanStep(a: BigInt, b: BigInt, inverse: BigInt, result: BigInt)
  case class Recipe(output: Seq[Int], scalar: Seq[ScalarStep], loan: Seq[LoanStep])

  def apply(hidden: Seq[Int], weight: Seq[Int]): Recipe = {
    require(hidden.size == Width && weight.size == Width, "this fixture is M1/H2048")
    val scalar = scala.collection.mutable.ArrayBuffer.empty[ScalarStep]
    def record(op: Int, a: Float, b: Float, result: Float): Float = {
      scalar += ScalarStep(op, bits(a), bits(b), bits(result)); result
    }
    def mul(a: Float, b: Float): Float = record(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
    def add(a: Float, b: Float): Float = record(ScalarOp.Add, a, b, (a + b).toFloat)
    val partials = Array.fill[Float](8, 4)(0f)
    // owner.py: lane8/residue4/block4/term16. Every term and every merge
    // has an explicit FP32 rounding boundary, including the initial +0.
    for (chunk <- 0 until 2; lane <- 0 until 8; residue <- 0 until 4; block <- 0 until 2) {
      var partial = 0f
      for (term <- 0 until 16) {
        val index = chunk * 1024 + block * 512 + term * 32 + residue * 8 + lane
        val x = fp(hidden(index))
        partial = add(partial, mul(x, x))
      }
      partials(lane)(residue) = add(partials(lane)(residue), partial)
    }
    var total = 0f
    for (lane <- 0 until 8) {
      var laneTotal = 0f
      for (residue <- 0 until 4) laneTotal = add(laneTotal, partials(lane)(residue))
      total = add(total, laneTotal)
    }
    val mean = mul(total, 1f / Width)
    val variance = add(mean, 1e-6f)
    val root = record(ScalarOp.Sqrt, variance, 0f, java.lang.StrictMath.sqrt(variance.toDouble).toFloat)
    val inverse = record(ScalarOp.Div, 1f, root, (1f / root).toFloat)
    // The following three FP32 operations per element execute in the real loan.
    val weighted = hidden.zip(weight).map { case (x, w) =>
      val normalized = (fp(x) * inverse).toFloat
      val gamma = (1f + fp(w)).toFloat
      (normalized * gamma).toFloat
    }
    val loan = (0 until Width by 16).map { first =>
      LoanStep(pack(hidden.slice(first, first + 16).map(x => bits(fp(x))), 32),
        pack(weight.slice(first, first + 16).map(x => bits(fp(x))), 32), bits(inverse),
        pack(weighted.slice(first, first + 16).map(bits), 32))
    }
    require(scalar.size == 4268 && loan.size == 128)
    Recipe(weighted.map(bf).toVector, scalar.toVector, loan.toVector)
  }

  def synthetic: (Seq[Int], Seq[Int]) = {
    val hidden = Seq.tabulate(Width)(i => bf((((i * 37) % 211) - 105).toFloat / 32f))
      .updated(0, 0x0000).updated(1, 0x8000).updated(1023, bf(-3.25f)).updated(1024, bf(2.625f))
    val weight = Seq.tabulate(Width)(i => bf((((i * 13) % 97) - 48).toFloat / 64f))
      .updated(0, bf(-1f)).updated(1, bf(-2f)).updated(1023, bf(1.5f)).updated(1024, bf(-1.25f))
    (hidden, weight)
  }
}

trait GdnRmsNormFixedBankTestSupport { self: ChiselScalatestTester with Matchers =>
  import GdnRmsNormFixedBankReference._
  case class MemoryBeat(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  case class RunReport(output: Seq[Int], reads: Int, writes: Int, writeAcks: Int,
                       scalarRequests: Int, scalarResults: Int, loans: Int, loanResults: Int,
                       cycles: BigInt)
  def init(d: GdnRmsNormFixedBankArithmeticHarness): Unit = {
    d.clock.setTimeout(5000000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.abort.poke(false.B); d.io.clear.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.loanRequestHold.poke(false.B); d.io.loanResultHold.poke(false.B)
    d.io.loanInjectStrayTag.poke(false.B)
    setJob(d)
    // Used only before a job, or after a fully drained and consumed terminal.
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
    d.io.job.ready.expect(true.B); d.io.drained.expect(true.B)
  }
  def setJob(d: GdnRmsNormFixedBankArithmeticHarness, tokens: Int = 1): Unit = {
    d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.hiddenWidth.poke(Width.U)
    d.io.job.bits.input.poke(InputBase.U); d.io.job.bits.weight.poke(WeightBase.U)
    d.io.job.bits.output.poke(OutputBase.U); d.io.job.bits.tag.poke(JobTag.U)
  }
  def memoryBeat(d: GdnRmsNormFixedBankArithmeticHarness): MemoryBeat = MemoryBeat(
    d.io.memory.bits.write.peek().litToBoolean, d.io.memory.bits.address.peek().litValue,
    d.io.memory.bits.data.peek().litValue, d.io.memory.bits.mask.peek().litValue,
    d.io.memory.bits.tag.peek().litValue)
  def completion(d: GdnRmsNormFixedBankArithmeticHarness): Seq[BigInt] = Seq(
    d.io.done.bits.tag.peek().litValue, d.io.done.bits.status.peek().litValue,
    d.io.done.bits.writeBytes.peek().litValue, d.io.done.bits.cycles.peek().litValue,
    d.io.done.bits.outputCommitted.peek().litValue)

  /** Fault modes operate on actual accepted DDR requests. An abort never
    * fabricates an ACK or erases the responder's pending accepted request. */
  def run(d: GdnRmsNormFixedBankArithmeticHarness, hidden: Seq[Int], weight: Seq[Int],
          label: String, fault: String = "none"): RunReport = {
    require(Set("none", "read", "write", "abort-write", "wrong-tag-read", "wrong-tag-loan").contains(fault))
    require(hidden.nonEmpty && hidden.size % Width == 0 && hidden.size / Width <= 128)
    val tokens = hidden.size / Width
    val rows = hidden.grouped(Width).map(row => GdnRmsNormFixedBankReference(row, weight)).toVector
    val recipe = Recipe(rows.flatMap(_.output), rows.flatMap(_.scalar), rows.flatMap(_.loan))
    require(recipe.scalar.isInstanceOf[scala.collection.IndexedSeq[_]] &&
      recipe.loan.isInstanceOf[scala.collection.IndexedSeq[_]], "large replay traces require indexed lookup")
    def beats(base: BigInt, values: Seq[Int]): Map[BigInt, BigInt] = values.grouped(32).zipWithIndex.map {
      case (xs, index) => (base + index * 64) -> pack(xs.map(BigInt(_)), 16)
    }.toMap
    val readData = beats(InputBase, hidden) ++ beats(WeightBase, weight)
    val expectedWrites = beats(OutputBase, recipe.output)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    val memoryOrder = (0 until tokens).flatMap { token =>
      val row = token * Width * 2
      (0 until 64).map(i => (false, InputBase + row + i * 64)) ++
        (0 until 2).flatMap { chunk =>
          (0 until 32).map(i => (false, InputBase + row + chunk * 2048 + i * 64)) ++
            (0 until 32).map(i => (false, WeightBase + chunk * 2048 + i * 64)) ++
            (0 until 32).map(i => (true, OutputBase + row + chunk * 2048 + i * 64))
        }
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
    var strayLoanHoldCycles = 0
    var strayLoanPackets = 0
    def bool(x: Bool): Boolean = x.peek().litToBoolean
    def scalarRequest: Seq[BigInt] = Seq(d.io.scalarRequest.op.peek().litValue,
      d.io.scalarRequest.a.peek().litValue, d.io.scalarRequest.b.peek().litValue)
    def loanRequest: Seq[BigInt] = Seq(d.io.loanRequest.tag.peek().litValue,
      d.io.loanRequest.op.peek().litValue, d.io.loanRequest.a.peek().litValue,
      d.io.loanRequest.b.peek().litValue, d.io.loanRequest.inverse.peek().litValue)
    def loanResult: Seq[BigInt] = Seq(d.io.loanResult.tag.peek().litValue,
      d.io.loanResult.status.peek().litValue, d.io.loanResult.value.peek().litValue)
    def step(n: Int = 1): Unit = for (_ <- 0 until n) {
      assert(elapsed < tokens * 250000, s"$label timed out")
      d.io.scalarHold.poke((elapsed % 23 < 5 || (scalarRequests == 0 && scalarStalls < 3)).B)
      d.io.loanRequestHold.poke((elapsed % 17 < 4 || (loans == 0 && loanRequestStalls < 3)).B)
      d.io.loanResultHold.poke((elapsed % 19 < 6 || (loanResults == 0 && loanResultStalls < 3)).B)
      d.io.loanInjectStrayTag.poke(false.B)
      if (fault == "wrong-tag-loan" && !injected && bool(d.io.loanResultValid)) {
        assert(pendingLoan.nonEmpty, "stray injection requires an actual held production terminal")
        injected = true; strayLoanHoldCycles = 20
        d.io.loanResultHold.poke(true.B); d.io.loanInjectStrayTag.poke(true.B)
        d.io.loanStrayAccepted.expect(true.B)
      } else if (strayLoanHoldCycles > 0) {
        d.io.loanResultHold.poke(true.B)
        d.io.done.valid.expect(false.B); d.io.drained.expect(false.B)
        d.io.job.ready.expect(false.B); d.io.loanBusy.expect(true.B)
        assert(pendingLoan.nonEmpty, "stray loan terminal discharged matching-result debt")
        strayLoanHoldCycles -= 1
      }
      heldScalarRequest.foreach { old =>
        assert(bool(d.io.scalarRequestValid) && scalarRequest == old, "Scalar request changed while stalled")
      }
      val scalarResult = Seq(d.io.scalarResult.peek().litValue, d.io.scalarError.peek().litValue)
      heldScalarResult.foreach { old =>
        assert(bool(d.io.scalarResultValid) && scalarResult == old, "Scalar result changed while held")
      }
      heldLoanRequest.foreach { old =>
        assert(bool(d.io.loanRequestValid) && loanRequest == old, "loan request changed while stalled")
      }
      heldLoanResult.foreach { old =>
        assert(bool(d.io.loanResultValid) && loanResult == old, "loan result changed while held")
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
        d.io.loanResult.tag.expect(tag.U); d.io.loanResult.status.expect(Status.Ok.U)
        d.io.loanResult.value.expect(recipe.loan(index).result.U)
        pendingLoan = None; loanResults += 1
      }
      if (bool(d.io.loanStrayAccepted)) {
        assert(!bool(d.io.loanResultAccepted), "stray packet must not retire the actual production terminal")
        strayLoanPackets += 1
      }
      if (pendingMemory.nonEmpty) {
        d.io.memory.valid.expect(false.B)
        d.io.done.valid.expect(false.B)
        d.io.done.bits.outputCommitted.expect(false.B)
        d.io.drained.expect(false.B)
      }
      if (bool(d.io.memory.valid) && bool(d.io.memory.ready)) {
        assert(pendingMemory.isEmpty && issued < memoryOrder.size, "more than one DDR request outstanding")
        val request = memoryBeat(d)
        // The owner shares its retirement sequence between DDR and loan.
        assert(request.tag == ((JobTag << 32) | (issued + loanResults)), "DDR/loan retirement sequence tag")
        assert((request.write, request.address) == memoryOrder(issued), s"$label DDR schedule at beat $issued")
        if (request.write) {
          assert(request.data == expectedWrites(request.address), s"$label BF16 write data at ${request.address}")
          assert(request.mask == FullMask, "write mask")
          assert(!committed.contains(request.address), "duplicate staging write")
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
        // A wrong-tag packet is consumed but cannot cancel the expected-tag debt.
        if (d.io.response.bits.tag.peek().litValue == request.tag) {
          if (request.write && !bool(d.io.response.bits.error)) {
            committed(request.address) = request.data; writeAcks += 1
          }
          pendingMemory = None
        }
      }
      d.clock.step(); elapsed += 1
    }
    def respond(request: MemoryBeat, error: Boolean = false, wrongTag: Boolean = false): Unit = {
      d.io.response.bits.data.poke((if (request.write) BigInt(0) else readData(request.address)).U)
      d.io.response.bits.tag.poke((request.tag ^ (if (wrongTag) BigInt(1) else BigInt(0))).U)
      d.io.response.bits.error.poke(error.B); d.io.response.valid.poke(true.B)
      var guard = 0
      while (!bool(d.io.response.ready) && guard < 100) { step(); guard += 1 }
      assert(guard < 100, "owner did not accept the outstanding response")
      step(); d.io.response.valid.poke(false.B)
    }
    setJob(d, tokens); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(); d.io.job.valid.poke(false.B)
    while (!bool(d.io.done.valid) && elapsed < tokens * 250000) {
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
        val last = request.write && request.address == OutputBase + tokens * 4096 - 64
        // No response is valid during this interval, including the delayed last ACK.
        step(if (last) 37 else delay)
        val hit = !injected && (fault match {
          case "read" | "wrong-tag-read" => !request.write
          case "write" | "abort-write" => request.write
          case _ => false
        })
        if (hit) injected = true
        if (hit && fault == "abort-write") {
          // The real accepted write remains outstanding through abort and clear.
          d.io.abort.poke(true.B); step(); d.io.abort.poke(false.B)
          d.io.clear.poke(true.B); step(3); d.io.clear.poke(false.B)
          step(19)
          assert(pendingMemory.contains(request), "abort/clear erased the accepted write")
          d.io.done.valid.expect(false.B); d.io.drained.expect(false.B); d.io.job.ready.expect(false.B)
          respond(request)
        } else if (hit && fault == "wrong-tag-read") {
          respond(request, wrongTag = true)
          step(19)
          assert(pendingMemory.contains(request), "wrong-tag packet retired unmatched DDR debt")
          d.io.done.valid.expect(false.B); d.io.drained.expect(false.B)
          respond(request)
        } else respond(request, error = hit && (fault == "read" || fault == "write"))
      }
    }
    assert(bool(d.io.done.valid), s"$label completion timeout")
    assert(pendingMemory.isEmpty && pendingScalar.isEmpty && pendingLoan.isEmpty, "done before drain")
    d.io.loanBusy.expect(false.B); d.io.drained.expect(true.B)
    val expectedStatus = fault match {
      case "none" => Status.Ok
      case "wrong-tag-read" | "wrong-tag-loan" => Status.Protocol
      case "abort-write" => ElementwiseLoanOp.Aborted
      case _ => Status.Memory
    }
    d.io.done.bits.status.expect(expectedStatus.U); d.io.done.bits.tag.expect(JobTag.U)
    d.io.done.bits.writeBytes.expect((writeAcks * 64).U)
    d.io.done.bits.outputCommitted.expect((fault == "none").B)
    d.io.memory.valid.expect(false.B)
    if (fault == "none") {
      assert(reads == tokens * 192 && writes == tokens * 64 && writeAcks == tokens * 64, "H2048 DDR accounting")
      assert(scalarRequests == tokens * 4268 && scalarResults == tokens * 4268, "exact Scalar accounting")
      assert(loans == tokens * 128 && loanResults == tokens * 128, "exact register-loan accounting")
      assert(committed.toMap == expectedWrites, "all BF16 output beats must be ACKed")
      assert(scalarStalls > 0 && loanRequestStalls > 0 && loanResultStalls > 0, s"stall controls were not exercised: scalar=$scalarStalls loan_request=$loanRequestStalls loan_result=$loanResultStalls")
    } else {
      assert(injected, s"$label fault was not exercised")
      if (fault == "abort-write") assert(writes == 1 && writeAcks == 1, "accepted write must be ACKed after abort")
      if (fault == "write") assert(writes == 1 && writeAcks == 0, "failed write ACK is not committed")
      if (fault == "wrong-tag-loan") {
        assert(strayLoanPackets == 1 && loans == 1 && loanResults == 1 && writes == 0,
          "protocol interposer must preserve and later drain exactly one actual loan terminal")
      }
    }
    val held = completion(d)
    for (_ <- 0 until 13) {
      d.io.done.valid.expect(true.B); d.io.job.ready.expect(false.B)
      assert(completion(d) == held, "completion changed under backpressure")
      step()
    }
    d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((fault == "none").B)
    d.io.resetRequired.expect((fault != "none").B)
    d.io.locked.expect((fault != "none").B)
    val output = committed.toSeq.sortBy(_._1).flatMap { case (_, beat) =>
      (0 until 32).map(lane => ((beat >> (lane * 16)) & 65535).toInt)
    }
    println(s"GDN_RMSNORM_FIXED_BANK_RTL label=$label status=$expectedStatus reads=$reads writes=$writes write_acks=$writeAcks scalar_requests=$scalarRequests scalar_results=$scalarResults loans=$loans loan_results=$loanResults cycles=${held(3)} launch_to_done_fire_cycles=${elapsed - 1} sampled_cycles=$elapsed terminal_held_cycles=13 actual_scalar=true actual_loan=true")
    RunReport(output, reads, writes, writeAcks, scalarRequests, scalarResults, loans, loanResults, held(3))
  }

  def rejectBounds(d: GdnRmsNormFixedBankArithmeticHarness, which: Int): Unit = {
    init(d)
    which match {
      case 0 => d.io.job.bits.hiddenWidth.poke(1024.U)
      case 1 => d.io.job.bits.tokens.poke(0.U)
      case 2 => d.io.job.bits.output.poke(InputBase.U)
      case 3 => d.io.job.bits.input.poke((InputBase + 2).U)
      case 4 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
      case _ => throw new IllegalArgumentException("unknown bounds case")
    }
    d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
    var guard = 0
    while (!d.io.done.valid.peek().litToBoolean && guard < 10) {
      d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
      d.io.loanRequestValid.expect(false.B); d.clock.step(); guard += 1
    }
    d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
    d.io.done.bits.writeBytes.expect(0.U); d.io.done.bits.outputCommitted.expect(false.B)
    d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
    d.io.loanRequestValid.expect(false.B); d.io.drained.expect(true.B)
    d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect(false.B); d.io.locked.expect(true.B)
  }
}

/** No local checkpoint or native fixture is needed for this synthetic gate.
  * Authentic-input replay is a separate suite with independently pinned files. */
class GdnRmsNormFixedBankOwnerSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  "GdnRmsNormFixedBankOwner" should "run M1 H2048 through the production Scalar and borrowed sixteen ALUs" in {
    test(new GdnRmsNormFixedBankArithmeticHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val (hidden, weight) = GdnRmsNormFixedBankReference.synthetic
      init(d)
      val report = run(d, hidden, weight, "synthetic-finite-varied-M1-H2048")
      assert(report.output == GdnRmsNormFixedBankReference(hidden, weight).output)
      for (fault <- Seq("read", "write", "abort-write", "wrong-tag-read", "wrong-tag-loan")) {
        init(d); run(d, hidden, weight, fault, fault)
      }
      for (which <- 0 until 5) rejectBounds(d, which)
    }
  }
}
