// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.experimental.expose
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.p0.LocalSramConfig
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Both arithmetic services are production RTL. The test can delay handshakes,
  * but cannot supply a Scalar or register-loan arithmetic result. */
class GdnRmsNormFixedBankArithmeticHarness(productionCore: Boolean = false,
                                           val useVectorEpilogue: Boolean = true,
                                           val useVectorReduction: Boolean = false) extends Module {
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
    // Test-only combinational observations of the ORIGINAL service instances.
    // No new production register or replacement arithmetic is introduced.
    val elemAluExecute = Output(Bool())
    val elemAluMul = Output(Bool())
    val elemAluAttemptMask = Output(UInt(16.W))
    val elemAluEffectiveMask = Output(UInt(16.W))
    val elemLoanReply = Output(Bool())
    val elemDdrActive = Output(Bool())
    val scalarAluExecute = Output(Bool())
    val scalarDividerPending = Output(Bool())
  })
  val owner = Module(new GdnRmsNormFixedBankOwner(useVectorEpilogue = useVectorEpilogue,
    useVectorReduction = useVectorReduction))
  val arithmetic = Wire(new GdnScalarClient)
  val loanService = Wire(Flipped(new ElementwiseLoanPort))
  val vectorUnavailable = Wire(Bool())
  def observeOriginalScalar(s: BlockScalarFloat): Unit = {
    val scalarStateTap = expose(s.state)
    io.scalarAluExecute := scalarStateTap === s.normal.litValue.U
    io.scalarDividerPending := scalarStateTap === s.divWait.litValue.U
  }
  def observeOriginalElementwise(e: ElementwiseRegisterLoan): Unit = {
    // Expose existing signals first; decode in this test harness rather than
    // constructing an expression with illegal cross-module signal references.
    val loanStateTap = expose(e.loanState)
    val ddrStateTap = expose(e.state)
    val opTap = expose(e.job.op)
    val tileTap = expose(e.tile)
    val calcIndexTap = expose(e.calcIndex)
    val ieeeBadTap = expose(e.ieeeBad)
    val strictBadTap = expose(e.strictBad)
    val addressErrorTap = expose(e.f.address_error_o)
    val abortTap = expose(e.loan.abort)
    val resetLoanTap = expose(e.loan.resetLoan)
    val primitive = loanStateTap === e.lPrimitive.litValue.U
    val ieee = loanStateTap === e.lIeee.litValue.U
    val normalize = loanStateTap === e.lNormalize.litValue.U
    val gamma = loanStateTap === e.lGamma.litValue.U
    val weighted = loanStateTap === e.lWeighted.litValue.U
    val loanExecute = primitive || ieee || normalize || gamma || weighted
    val ddrExecute = ddrStateTap === e.calculate.litValue.U && opTap =/= ElemOp.Copy.U
    val activeMask = VecInit((0 until 16).map(i => calcIndexTap + i.U < tileTap)).asUInt
    // Logical stage validity after numerical/cancel qualification. This is
    // NOT a physical register write-enable: e.g. lGamma can still update b
    // on an abort edge while loanFail replaces value/status/state.
    val loanEffective = loanExecute && !abortTap && !resetLoanTap &&
      !Mux(primitive || gamma, strictBadTap, ieeeBadTap)
    val ddrEffective = ddrExecute && !strictBadTap && !addressErrorTap.orR
    io.elemAluExecute := loanExecute || ddrExecute
    io.elemAluMul := opTap === ElemOp.Mul.U
    io.elemAluAttemptMask := Mux(loanExecute || ddrExecute, activeMask, 0.U)
    io.elemAluEffectiveMask := Mux(loanEffective || ddrEffective, activeMask, 0.U)
    io.elemLoanReply := loanStateTap === e.lReply.litValue.U
    io.elemDdrActive := ddrStateTap =/= e.idle.litValue.U
  }
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
    observeOriginalScalar(core.scalar)
    observeOriginalElementwise(core.lender.get)
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
    observeOriginalScalar(scalar)
    observeOriginalElementwise(lender)
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
  case class LoanStep(a: BigInt, b: BigInt, inverse: BigInt, result: BigInt,
                      op: Int = ElementwiseLoanOp.RmsEpilogue, phase: String = "epilogue")
  case class Recipe(output: Seq[Int], scalar: Seq[ScalarStep], loan: Seq[LoanStep])

  def apply(hidden: Seq[Int], weight: Seq[Int], useVectorEpilogue: Boolean = true,
            useVectorReduction: Boolean = false): Recipe = {
    require(hidden.size == Width && weight.size == Width, "this fixture is M1/H2048")
    val scalar = scala.collection.mutable.ArrayBuffer.empty[ScalarStep]
    val reductionLoan = scala.collection.mutable.ArrayBuffer.empty[LoanStep]
    def record(op: Int, a: Float, b: Float, result: Float): Float = {
      scalar += ScalarStep(op, bits(a), bits(b), bits(result)); result
    }
    def mul(a: Float, b: Float): Float = record(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
    def add(a: Float, b: Float): Float = record(ScalarOp.Add, a, b, (a + b).toFloat)
    val partials = Array.fill[Float](8, 4)(0f)
    if (useVectorReduction) {
      // Schedule only independent nodes together. Preserve each term and block
      // dependency and both FP32 rounding boundaries; this is NOT an FMA.
      // Hardware slot i maps to p=4*lane+residue in the original output layout.
      for (chunk <- 0 until 2; block <- 0 until 2; group <- 0 until 2) {
        var blockPartial = Vector.fill[Float](16)(0f)
        for (term <- 0 until 16) {
          val xs = Vector.tabulate(16) { i =>
            val lane = 4 * group + (i >> 2); val residue = i & 3
            fp(hidden(chunk * 1024 + block * 512 + term * 32 + residue * 8 + lane))
          }
          val next = xs.zip(blockPartial).map { case (x, partial) =>
            val square = (x * x).toFloat
            (partial + square).toFloat
          }
          reductionLoan += LoanStep(pack(xs.map(bits), 32), pack(blockPartial.map(bits), 32),
            BigInt(0), pack(next.map(bits), 32), ElementwiseLoanOp.SquareAccumulate, "reduction")
          blockPartial = next
        }
        val previous = Vector.tabulate(16) { i =>
          // Global block zero must execute the explicit +0 merge too.
          if (chunk == 0 && block == 0) 0f else partials(4 * group + (i >> 2))(i & 3)
        }
        val merged = previous.zip(blockPartial).map { case (a, b) => (a + b).toFloat }
        reductionLoan += LoanStep(pack(previous.map(bits), 32), pack(blockPartial.map(bits), 32),
          BigInt(0), pack(merged.map(bits), 32), ElementwiseLoanOp.Add, "reduction")
        for (i <- 0 until 16) partials(4 * group + (i >> 2))(i & 3) = merged(i)
      }
    } else {
      // owner.py: lane8/residue4/block4/term16, including every initial +0.
      for (chunk <- 0 until 2; lane <- 0 until 8; residue <- 0 until 4; block <- 0 until 2) {
        var partial = 0f
        for (term <- 0 until 16) {
          val index = chunk * 1024 + block * 512 + term * 32 + residue * 8 + lane
          val x = fp(hidden(index))
          partial = add(partial, mul(x, x))
        }
        partials(lane)(residue) = add(partials(lane)(residue), partial)
      }
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
    // Same three rounding boundaries in either service. Scalar epilogue
    // records the actual lane-major normalize/gamma/weighted request order.
    val weighted = hidden.zip(weight).map { case (x, w) =>
      if (useVectorEpilogue) {
        val normalized = (fp(x) * inverse).toFloat
        val gamma = (1f + fp(w)).toFloat
        (normalized * gamma).toFloat
      } else {
        val normalized = mul(fp(x), inverse)
        val gamma = add(1f, fp(w))
        mul(normalized, gamma)
      }
    }
    val loan = (0 until Width by 16).map { first =>
      LoanStep(pack(hidden.slice(first, first + 16).map(x => bits(fp(x))), 32),
        pack(weight.slice(first, first + 16).map(x => bits(fp(x))), 32), bits(inverse),
        pack(weighted.slice(first, first + 16).map(bits), 32))
    }
    val expectedScalar = (if (useVectorReduction) 44 else 4268) +
      (if (useVectorEpilogue) 0 else 6144)
    require(scalar.size == expectedScalar && loan.size == 128)
    require(reductionLoan.size == (if (useVectorReduction) 136 else 0))
    Recipe(weighted.map(bf).toVector, scalar.toVector,
      reductionLoan.toVector ++ (if (useVectorEpilogue) loan.toVector else Vector.empty))
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
                       cycles: BigInt, launchToDoneFireCycles: Long = -1L, sampledCycles: Long = -1L,
                       phaseCycles: Map[String, Long] = Map.empty,
                       arithmeticCycles: Map[String, Long] = Map.empty)
  def init(d: GdnRmsNormFixedBankArithmeticHarness): Unit = {
    d.clock.setTimeout(if (d.useVectorEpilogue) 5000000 else 32001000)
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
          label: String, fault: String = "none", extraFirstLoanHold: Int = 0,
          idealSupply: Boolean = false): RunReport = {
    val hasLoan = d.useVectorEpilogue || d.useVectorReduction
    val scalarReductionPerToken = if (d.useVectorReduction) 44 else 4268
    val scalarPerToken = scalarReductionPerToken + (if (d.useVectorEpilogue) 0 else 6144)
    val loansPerToken = (if (d.useVectorReduction) 136 else 0) + (if (d.useVectorEpilogue) 128 else 0)
    val timing = if (idealSupply) "ideal_supply_experiment" else "artificial_backpressure"
    val reduction = if (d.useVectorReduction) "vector" else "scalar"
    require(extraFirstLoanHold >= 0 && (hasLoan || extraFirstLoanHold == 0))
    require(!idealSupply || extraFirstLoanHold == 0, "ideal supply cannot add an artificial loan hold")
    require(Set("none", "read", "write", "abort-write", "wrong-tag-read", "wrong-tag-loan").contains(fault))
    require(hasLoan || fault != "wrong-tag-loan", "all-Scalar ablation has no loan to corrupt")
    require(hidden.nonEmpty && hidden.size % Width == 0 && hidden.size / Width <= 128)
    val tokens = hidden.size / Width
    val rows = hidden.grouped(Width).map(row =>
      GdnRmsNormFixedBankReference(row, weight, d.useVectorEpilogue, d.useVectorReduction)).toVector
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
    var launchEdge = Option.empty[Int]
    var doneFireEdge = Option.empty[Int]
    val phaseCycles = scala.collection.mutable.Map.empty[String, Long].withDefaultValue(0L)
    val arithmeticCycles = scala.collection.mutable.Map.empty[String, Long].withDefaultValue(0L)
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
      d.io.scalarHold.poke((!idealSupply &&
        (elapsed % 23 < 5 || (scalarRequests == 0 && scalarStalls < 3))).B)
      d.io.loanRequestHold.poke((!idealSupply &&
        (elapsed % 17 < 4 || (loans == 0 && loanRequestStalls < 3))).B)
      d.io.loanResultHold.poke((!idealSupply &&
        (elapsed % 19 < 6 || (loanResults == 0 && loanResultStalls < 3 + extraFirstLoanHold))).B)
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
      // Pure host observation: sample BEFORE pending-debt bookkeeping changes.
      // Every sampled edge from job.fire through done.fire has exactly one bin.
      val launchFire = bool(d.io.job.valid) && bool(d.io.job.ready)
      if (launchFire) { assert(launchEdge.isEmpty); launchEdge = Some(elapsed) }
      if (launchEdge.nonEmpty && doneFireEdge.isEmpty) {
        def scalarPhase(index: Int): String =
          if (index % scalarPerToken < scalarReductionPerToken) "reduction" else "epilogue"
        def loanPhase(index: Int): String = recipe.loan(index).phase
        def memoryPhase(index: Int): String = if (index % 256 < 64) "reduction" else "epilogue"
        def responsePhase(valid: Boolean, ready: Boolean): String =
          if (!valid) "response_wait" else if (ready) "response_fire" else "response_held"
        val category = if (launchFire) "launch_fire"
          else if (bool(d.io.done.valid)) {
            if (bool(d.io.done.ready)) "terminal_fire" else "terminal_held"
          } else if (pendingMemory.nonEmpty) {
            val request = pendingMemory.get
            val operation = if (request.write) "write" else "read"
            val response = if (bool(d.io.response.valid) && bool(d.io.response.ready) &&
              d.io.response.bits.tag.peek().litValue != request.tag) "stray_response_fire"
              else responsePhase(bool(d.io.response.valid), bool(d.io.response.ready))
            s"${memoryPhase(issued - 1)}_ddr_${operation}_$response"
          } else if (pendingScalar.nonEmpty) {
            val response = if (bool(d.io.scalarResultValid))
              responsePhase(valid = true, ready = bool(d.io.scalarResultReady))
              else if (bool(d.io.scalarAluExecute)) "alu_execute"
              else if (bool(d.io.scalarDividerPending)) "divider_pending"
              else "response_wait"
            s"${scalarPhase(pendingScalar.get)}_scalar_$response"
          } else if (pendingLoan.nonEmpty) {
            val response = if (bool(d.io.loanStrayAccepted)) "stray_response_fire"
              else if (bool(d.io.loanResultValid))
                responsePhase(valid = true, ready = bool(d.io.loanResultReady))
              else if (bool(d.io.elemAluExecute)) "alu_execute"
              else "response_wait"
            s"${loanPhase(pendingLoan.get._1)}_loan_$response"
          } else if (bool(d.io.memory.valid)) {
            val operation = if (bool(d.io.memory.bits.write)) "write" else "read"
            val offer = if (bool(d.io.memory.ready)) "request_fire" else "request_stalled"
            s"${memoryPhase(issued)}_ddr_${operation}_$offer"
          } else if (bool(d.io.scalarRequestValid)) {
            val offer = if (bool(d.io.scalarRequestReady)) "request_fire" else "request_stalled"
            s"${scalarPhase(scalarRequests)}_scalar_$offer"
          } else if (bool(d.io.loanRequestValid)) {
            val offer = if (bool(d.io.loanRequestReady)) "request_fire" else "request_stalled"
            s"${loanPhase(loans)}_loan_$offer"
          } else "owner_control_or_drain"
        // Wall intervals are (launch.fire, done.fire], so launch itself is
        // observed but not charged. These bins sum the edge-to-edge wall count.
        if (!launchFire) {
          phaseCycles(category) += 1L
          d.io.elemDdrActive.expect(false.B)
          val elemExecute = bool(d.io.elemAluExecute)
          val attemptMask = d.io.elemAluAttemptMask.peek().litValue
          val effectiveMask = d.io.elemAluEffectiveMask.peek().litValue
          val attemptLanes = attemptMask.bitCount.toLong
          val effectiveLanes = effectiveMask.bitCount.toLong
          assert((effectiveMask & ~attemptMask) == 0, "logically effective lanes must be executed lanes")
          assert(elemExecute == (attemptLanes > 0), "RMS ALU execution/mask mismatch")
          if (bool(d.io.loanBusy)) arithmeticCycles("elem_service_busy") += 1L
          if (bool(d.io.elemLoanReply)) arithmeticCycles("elem_reply_resident") += 1L
          if (bool(d.io.loanResultValid) && !bool(d.io.loanResultReady))
            arithmeticCycles("elem_result_held") += 1L
          if (elemExecute) {
            assert(pendingLoan.nonEmpty, "original core.elem executed without a live RMS loan")
            arithmeticCycles("elem_alu_execution_busy") += 1L
            arithmeticCycles("elem_alu_attempt_lane") += attemptLanes
            arithmeticCycles("elem_alu_effective_lane") += effectiveLanes
            val operation = if (bool(d.io.elemAluMul)) "mul" else "add"
            arithmeticCycles(s"elem_${operation}_execution") += 1L
            arithmeticCycles(s"elem_${operation}_attempt_lane") += attemptLanes
            arithmeticCycles(s"elem_${operation}_effective_lane") += effectiveLanes
          }
          if (bool(d.io.scalarAluExecute)) {
            assert(pendingScalar.nonEmpty, "original Scalar ALU executed without an accepted request")
            arithmeticCycles("scalar_alu_execution_busy") += 1L
          }
          if (bool(d.io.scalarDividerPending)) arithmeticCycles("scalar_divider_pending") += 1L
        }
        if (bool(d.io.done.valid) && bool(d.io.done.ready)) doneFireEdge = Some(elapsed)
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
      if (!hasLoan) {
        d.io.loanRequestValid.expect(false.B); d.io.loanBusy.expect(false.B)
        d.io.loanResultValid.expect(false.B)
      }
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
          s"$label Scalar request $scalarRequests differs from independent arithmetic recipe")
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
        d.io.loanRequest.op.expect(expected.op.U)
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
        val delay = if (idealSupply) 0 else 2 + issued % 5
        for (_ <- 0 until delay) {
          d.io.memory.valid.expect(true.B)
          assert(memoryBeat(d) == request, "DDR request changed under backpressure")
          step()
        }
        d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
        assert(pendingMemory.contains(request), "accepted request must create DDR debt")
        val last = request.write && request.address == OutputBase + tokens * 4096 - 64
        // Ideal supply has request.fire then response.fire on consecutive
        // sampled edges: two charged transaction cycles, no response_wait.
        // The historical 37-cycle last-ACK hold remains in the default profile.
        if (!idealSupply) step(if (last) 37 else delay)
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
      assert(scalarRequests == tokens * scalarPerToken && scalarResults == tokens * scalarPerToken, "exact Scalar accounting")
      assert(loans == tokens * loansPerToken && loanResults == tokens * loansPerToken, "exact register-loan accounting")
      assert(committed.toMap == expectedWrites, "all BF16 output beats must be ACKed")
      // Only artificial-stall coverage is inapplicable to ideal supply. All
      // numeric, request/result, drain, tag, ACK and completion checks remain.
      if (!idealSupply) {
        assert(scalarStalls > 0, "Scalar request stalls were not exercised")
        if (hasLoan) {
          assert(loanRequestStalls > 0 && loanResultStalls > 0,
            s"loan stall controls were not exercised: request=$loanRequestStalls result=$loanResultStalls")
        }
      }
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
    val launchToDoneFireCycles = (doneFireEdge.get - launchEdge.get).toLong
    val sampledCycles = launchToDoneFireCycles + 1L
    assert(phaseCycles.values.sum == launchToDoneFireCycles, "phase bins must sum edge-to-edge wall cycles")
    assert(sampledCycles == elapsed.toLong && launchToDoneFireCycles == (elapsed - 1).toLong,
      "preserve existing launch-to-done.fire and inclusive timing output")
    assert(phaseCycles("terminal_fire") == 1L)
    if (fault == "none") {
      val measuredOwnerCycles = launchToDoneFireCycles -
        phaseCycles("terminal_held") - phaseCycles("terminal_fire")
      assert(BigInt(measuredOwnerCycles) == held(3), "observed active phases must reconcile owner cycles")
      // Expected counts are CROSS-CHECKS of per-cycle internal taps; none of
      // these measurements is calculated by multiplying the loan count.
      val expectedVectorCycles = tokens.toLong *
        ((if (d.useVectorEpilogue) 384 else 0) + (if (d.useVectorReduction) 264 else 0))
      val expectedVectorMulLanes = tokens.toLong *
        ((if (d.useVectorEpilogue) 4096 else 0) + (if (d.useVectorReduction) 2048 else 0))
      val expectedVectorAddLanes = tokens.toLong *
        ((if (d.useVectorEpilogue) 2048 else 0) + (if (d.useVectorReduction) 2176 else 0))
      assert(arithmeticCycles("elem_alu_execution_busy") == expectedVectorCycles)
      assert(arithmeticCycles("elem_mul_effective_lane") == expectedVectorMulLanes)
      assert(arithmeticCycles("elem_add_effective_lane") == expectedVectorAddLanes)
      assert(arithmeticCycles("elem_alu_attempt_lane") == arithmeticCycles("elem_alu_effective_lane"))
      assert(arithmeticCycles("elem_service_busy") ==
        arithmeticCycles("elem_alu_execution_busy") + arithmeticCycles("elem_reply_resident"))
      val expectedScalarAluCycles = tokens.toLong * (scalarPerToken - 2)
      assert(arithmeticCycles("scalar_alu_execution_busy") == expectedScalarAluCycles)
    }
    println(s"H2048_ARITHMETIC_CYCLES label=$label timing=$timing reduction=$reduction observation=internal_state_taps " +
      arithmeticCycles.toSeq.sortBy(_._1).map { case (metric, count) => s"$metric=$count" }.mkString(" "))
    println(s"H2048_PHASE_CYCLES label=$label timing=$timing reduction=$reduction wall_cycles=$launchToDoneFireCycles " + phaseCycles.toSeq.sortBy(_._1).map {
      case (phase, count) => s"$phase=$count"
    }.mkString(" "))
    println(s"GDN_RMSNORM_FIXED_BANK_RTL label=$label status=$expectedStatus reads=$reads writes=$writes write_acks=$writeAcks scalar_requests=$scalarRequests scalar_results=$scalarResults loans=$loans loan_results=$loanResults cycles=${held(3)} actual_scalar=true actual_loan=$hasLoan timing=$timing reduction=$reduction epilogue=${if (d.useVectorEpilogue) "vector" else "scalar"} borrower_bank_bytes=6144 launch_to_done_fire_cycles=$launchToDoneFireCycles sampled_cycles=$sampledCycles terminal_held_cycles=${phaseCycles("terminal_held")}")
    RunReport(output, reads, writes, writeAcks, scalarRequests, scalarResults, loans, loanResults, held(3),
      launchToDoneFireCycles, sampledCycles, phaseCycles.toMap, arithmeticCycles.toMap)
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
