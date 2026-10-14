// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.p0.LocalSramConfig
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Checkpoint-independent tests of the production sixteen-lane register loan.
  * The oracle materializes the FP32 product before adding the FP32 partial.
  * Run alongside ElementwiseRegisterLoanSpec and the opt-in RMS replay gate.
  */
class ElementwiseSquareAccumulateLoanSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  private def fp(x: BigInt): Float = java.lang.Float.intBitsToFloat(x.toInt)
  private def hex(s: String): BigInt = BigInt(s, 16)
  private def pack(xs: Seq[BigInt]): BigInt = {
    require(xs.size == 16)
    xs.zipWithIndex.foldLeft(BigInt(0)) { case (a, (x, i)) => a | (x << (32 * i)) }
  }
  private def expected(xs: Seq[BigInt], partials: Seq[BigInt]): Seq[BigInt] =
    xs.zip(partials).map { case (x, p) =>
      val roundedSquare = bits((fp(x) * fp(x)).toFloat)
      bits((fp(p) + fp(roundedSquare)).toFloat)
    }
  private val zero = BigInt(0)
  private val one = bits(1f)
  private val zeros = Seq.fill(16)(zero)
  private val ones = Seq.fill(16)(one)

  "Elementwise SquareAccumulate loan" should "round square then Add separately and preserve poison, drain, arbitration and reuse" in {
    ElementwiseLoanOp.SquareAccumulate shouldBe 3
    test(new ElementwiseRegisterLoan(ChainConfig(tileElements = 32),
      LocalSramConfig(addressBits = 3, rowsPerBank = 2)))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      d.clock.setTimeout(20000)
      def setJob(op: Int, count: Int): Unit = {
        d.io.job.bits.op.poke(op.U); d.io.job.bits.tag.poke(99.U)
        d.io.job.bits.a.poke(0x1000.U); d.io.job.bits.b.poke(0x2000.U); d.io.job.bits.dst.poke(0x3000.U)
        d.io.job.bits.elementCount.poke(count.U)
        d.io.job.bits.aBf16.poke(false.B); d.io.job.bits.bBf16.poke(false.B); d.io.job.bits.dstBf16.poke(false.B)
      }
      d.io.job.valid.poke(false.B); setJob(ElemOp.Copy, 16); d.io.done.ready.poke(false.B)
      d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
      d.io.response.bits.tag.poke(0.U); d.io.response.bits.data.poke(0.U); d.io.response.bits.error.poke(false.B)
      d.loan.request.valid.poke(false.B); d.loan.result.ready.poke(false.B)
      d.loan.abort.poke(false.B); d.loan.resetLoan.poke(false.B)
      d.loan.request.bits.tag.poke(0.U); d.loan.request.bits.op.poke(0.U)
      d.loan.request.bits.a.poke(0.U); d.loan.request.bits.b.poke(0.U); d.loan.request.bits.inverse.poke(one.U)
      var edge = 0; var nextTag = 1; var currentTag = 0; var accepted = 0; var checked = 0
      def step(n: Int = 1): Unit = { require(n >= 0); if (n > 0) d.clock.step(n); edge += n }
      def quiet(): Unit = {
        d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B); d.io.done.valid.expect(false.B)
      }
      def live(): Unit = {
        quiet(); d.loan.busy.expect(true.B); d.loan.request.ready.expect(false.B); d.io.job.ready.expect(false.B)
      }
      def setRequest(op: Int, xs: Seq[BigInt], ps: Seq[BigInt], inverse: BigInt = one): Unit = {
        currentTag = nextTag; nextTag += 1
        d.loan.request.bits.tag.poke(currentTag.U); d.loan.request.bits.op.poke(op.U)
        d.loan.request.bits.a.poke(pack(xs).U); d.loan.request.bits.b.poke(pack(ps).U)
        d.loan.request.bits.inverse.poke(inverse.U); d.loan.request.valid.poke(true.B)
      }
      def capture(): Unit = {
        d.loan.request.ready.expect(true.B); accepted = edge; step()
        d.loan.request.valid.poke(false.B)
        // All fields must have been captured; no continuation or live-input dependency.
        d.loan.request.bits.tag.poke(0xbadcafe.U); d.loan.request.bits.op.poke(ElementwiseLoanOp.MulIeeeRne.U)
        d.loan.request.bits.a.poke(0.U); d.loan.request.bits.b.poke(0.U); d.loan.request.bits.inverse.poke(0.U)
      }
      def offer(op: Int, xs: Seq[BigInt], ps: Seq[BigInt], inverse: BigInt = one): Unit = {
        setRequest(op, xs, ps, inverse); capture(); live()
      }
      def awaitResult(): Unit = {
        var waited = 0
        while (!d.loan.result.valid.peek().litToBoolean && waited < 8) { live(); step(); waited += 1 }
        assert(waited < 8, "register loan failed to retire")
      }
      def checkResult(status: Int, values: Seq[BigInt]): Unit = {
        live(); d.loan.result.valid.expect(true.B)
        d.loan.result.bits.tag.expect(currentTag.U); d.loan.result.bits.status.expect(status.U)
        d.loan.result.bits.value.expect((if (status == Status.Ok) pack(values) else BigInt(0)).U)
        d.loan.resetRequired.expect((status != Status.Ok).B)
        d.io.resetRequired.expect((status != Status.Ok).B)
      }
      def retire(status: Int, values: Seq[BigInt], latency: Int = -1, hold: Int = 0): Unit = {
        awaitResult()
        if (latency >= 0) (edge - accepted) shouldBe latency
        checkResult(status, values)
        for (_ <- 0 until hold) {
          d.io.job.valid.poke(true.B); d.loan.request.valid.poke(true.B)
          checkResult(status, values); step(); checkResult(status, values)
        }
        d.io.job.valid.poke(false.B); d.loan.request.valid.poke(false.B)
        d.loan.result.ready.poke(true.B); step(); d.loan.result.ready.poke(false.B)
        d.loan.result.valid.expect(false.B); checked += 16
        if (status != Status.Ok) {
          d.loan.busy.expect(false.B); d.loan.resetRequired.expect(true.B)
          d.io.job.ready.expect(false.B); d.loan.request.ready.expect(false.B)
          // A stale DDR response blocks reset/unlock until it has been drained externally.
          d.io.response.valid.poke(true.B); d.loan.resetLoan.poke(true.B); step()
          d.loan.resetRequired.expect(true.B); d.loan.request.ready.expect(false.B)
          d.io.response.valid.poke(false.B); step(); d.loan.resetLoan.poke(false.B)
        }
        quiet(); d.loan.busy.expect(false.B); d.loan.resetRequired.expect(false.B)
        d.io.job.ready.expect(true.B); d.loan.request.ready.expect(true.B)
      }
      def square(xs: Seq[BigInt], ps: Seq[BigInt], hold: Int = 0): Unit = {
        offer(ElementwiseLoanOp.SquareAccumulate, xs, ps)
        d.loan.result.valid.expect(false.B); step() // materialize separately rounded square
        d.loan.result.valid.expect(false.B); live() // no partial result after first stage
        retire(Status.Ok, expected(xs, ps), latency = 3, hold = hold)
      }

      // Signed zero, normal RNE, cancellation, exact/inexact subnormals, and UF-to-zero.
      val xs = Seq("00000000", "80000000", "3f800000", "bf800000", "3f800001", "bf800001",
        "1f000000", "1f800001", "1a000000", "00000001", "00800000", "3f000000",
        "c0600000", "5f000000", "3fc00000", "40000000").map(hex)
      val ps = Seq("80000000", "80000000", "00000000", "3f800000", "bf800002", "bf800002",
        "00000001", "00000001", "00000001", "80000001", "00000001", "3f800000",
        "bdcccccd", "fe000000", "3e800000", "4b800000").map(hex)
      square(xs, ps, hold = 5)
      var previousAccepted = -1
      for (_ <- 0 until 3) {
        square(ones, zeros)
        if (previousAccepted >= 0) (accepted - previousAccepted) shouldBe 4
        previousAccepted = accepted
      }
      val random = new scala.util.Random(0x53514143L)
      for (_ <- 0 until 12) {
        val x = Seq.fill(16)(bits((random.nextFloat() - 0.5f) * 128f))
        val p = Seq.fill(16)(bits((random.nextFloat() - 0.5f) * 64f))
        square(x, p)
      }
      // The same bit vector gives +0 with two rounds and 2^-46 with fused x*x+p.
      val nfX = hex("3f800001"); val nfP = hex("bf800002")
      expected(Seq(nfX), Seq(nfP)).head shouldBe zero
      bits(java.lang.Math.fma(fp(nfX), fp(nfX), fp(nfP))) shouldBe hex("28800000")
      square(Seq.fill(16)(nfX), Seq.fill(16)(nfP))

      // Square UF/NX is accepted; the original strict Mul must reject the same product.
      val tiny = Seq.fill(16)(hex("1f800001"))
      bits((fp(tiny.head) * fp(tiny.head)).toFloat) shouldBe hex("00200001")
      offer(ElementwiseLoanOp.Mul, tiny, tiny); retire(Status.Numerical, Nil, latency = 2)
      square(tiny, zeros)
      // Exact tiny Add survives strict mode; adding 1 to 2^24 exercises allowed Add NX.
      square(ones, Seq.fill(16)(hex("4b800000")))

      // A bad lane at either stage rejects the entire 512-bit result, including
      // lanes before and after it. First-stage failure cannot proceed to Add.
      for (lane <- 0 until 16) {
        val badSquare = Seq("7f800000", "ff800000", "7fc12345", "7f800001", "5f800000")(lane % 5)
        offer(ElementwiseLoanOp.SquareAccumulate, ones.updated(lane, hex(badSquare)), zeros)
        retire(Status.Numerical, Nil, latency = 2, hold = if (lane == 15) 3 else 0)
        val badPartial = Seq("7f800000", "ff800000", "7fc12345", "7f800001")(lane % 4)
        offer(ElementwiseLoanOp.SquareAccumulate, ones, zeros.updated(lane, hex(badPartial)))
        d.loan.result.valid.expect(false.B); step(); d.loan.result.valid.expect(false.B)
        retire(Status.Numerical, Nil, latency = 3, hold = if (lane == 0) 3 else 0)
      }
      // Finite square, then Add overflow is a distinct second-stage failure.
      offer(ElementwiseLoanOp.SquareAccumulate, ones.updated(11, hex("5f000000")),
        zeros.updated(11, hex("7f7fffff")))
      retire(Status.Numerical, Nil, latency = 3)
      // Even a cancelling partial cannot rescue an overflowing square.
      offer(ElementwiseLoanOp.SquareAccumulate, ones.updated(6, hex("5f800000")),
        zeros.updated(6, hex("ff7fffff")))
      retire(Status.Numerical, Nil, latency = 2)

      // Every admission replaces the reused base marker, including old op6.
      for (op <- Seq(ElementwiseLoanOp.Add, ElementwiseLoanOp.Mul, ElementwiseLoanOp.MulIeeeRne,
        ElementwiseLoanOp.RmsEpilogue)) {
        square(ones, ones)
        val aa = Seq.tabulate(16)(i => bits(1f + i.toFloat / 16f))
        val bb = Seq.tabulate(16)(i => bits(i.toFloat / 32f))
        val inv = bits(0.75f)
        val result = aa.zip(bb).map { case (x, y) =>
          if (op == ElementwiseLoanOp.Add) bits((fp(x) + fp(y)).toFloat)
          else if (op == ElementwiseLoanOp.RmsEpilogue) {
            val normalized = bits((fp(x) * fp(inv)).toFloat)
            val gamma = bits((1f + fp(y)).toFloat)
            bits((fp(normalized) * fp(gamma)).toFloat)
          } else bits((fp(x) * fp(y)).toFloat)
        }
        offer(op, aa, bb, inv)
        retire(Status.Ok, result, latency = if (op == ElementwiseLoanOp.RmsEpilogue) 4 else 2)
      }
      for (badOp <- Seq(0, 4, 5)) {
        offer(badOp, ones, ones); retire(Status.Unsupported, Nil, latency = 1)
        square(ones, zeros)
      }
      // Reset/abort admission inhibition does not consume or mutate a waiting request.
      for (useReset <- Seq(false, true)) {
        setRequest(ElementwiseLoanOp.SquareAccumulate, xs, ps)
        if (useReset) d.loan.resetLoan.poke(true.B) else d.loan.abort.poke(true.B)
        d.loan.request.ready.expect(false.B); step(2); d.loan.result.valid.expect(false.B)
        if (useReset) d.loan.resetLoan.poke(false.B) else d.loan.abort.poke(false.B)
        capture(); retire(Status.Ok, expected(xs, ps), latency = 3)
      }
      // Both cancellation inputs win at square, Add and held reply, including
      // a same-edge otherwise-successful retirement. The terminal must still drain.
      for (useReset <- Seq(false, true); delay <- 0 to 2) {
        offer(ElementwiseLoanOp.SquareAccumulate, xs, ps); step(delay)
        if (delay == 2) d.loan.result.valid.expect(true.B)
        d.loan.result.ready.poke(true.B)
        if (useReset) d.loan.resetLoan.poke(true.B) else d.loan.abort.poke(true.B)
        d.loan.result.valid.expect(false.B); step(2)
        d.loan.resetRequired.expect(true.B); d.loan.result.valid.expect(false.B)
        if (useReset) d.loan.resetLoan.poke(false.B) else d.loan.abort.poke(false.B)
        d.loan.result.ready.poke(false.B)
        retire(ElementwiseLoanOp.Aborted, Nil, hold = 3)
        square(ones, ones)
      }
      // Cancellation also beats a numerical fault on either compute edge.
      for (useReset <- Seq(false, true); badStage <- 0 to 1) {
        val badXs = if (badStage == 0) ones.updated(3, hex("7f800000")) else ones
        val badPs = if (badStage == 1) zeros.updated(8, hex("7fc12345")) else zeros
        offer(ElementwiseLoanOp.SquareAccumulate, badXs, badPs); step(badStage)
        if (useReset) d.loan.resetLoan.poke(true.B) else d.loan.abort.poke(true.B)
        d.loan.result.valid.expect(false.B); step()
        if (useReset) d.loan.resetLoan.poke(false.B) else d.loan.abort.poke(false.B)
        retire(ElementwiseLoanOp.Aborted, Nil)
      }
      // A stale response blocks initial loan admission even when the engine is idle.
      setRequest(ElementwiseLoanOp.SquareAccumulate, xs, ps)
      d.io.response.valid.poke(true.B); d.loan.request.ready.expect(false.B); step(3)
      d.loan.result.valid.expect(false.B); d.io.response.ready.expect(false.B)
      d.io.response.valid.poke(false.B); capture(); retire(Status.Ok, expected(xs, ps), latency = 3)

      // DDR and loan offered on the same edge: DDR wins, resets reused base to
      // element offset zero, and retains exclusion through its accepted response.
      // Serve real DDR Add/Mul, after loans have overwritten a/b/raw/base.
      for (op <- Seq(ElemOp.Add, ElemOp.Mul)) {
        square(xs, ps)
        val aa = Seq.tabulate(16)(i => bits(1f + i.toFloat / 4f))
        val bb = Seq.tabulate(16)(i => bits(2f + i.toFloat / 16f))
        val out = pack(aa.zip(bb).map { case (x, y) =>
          bits(if (op == ElemOp.Add) (fp(x) + fp(y)).toFloat else (fp(x) * fp(y)).toFloat)
        })
        setJob(op, 16); d.io.job.valid.poke(true.B)
        setRequest(ElementwiseLoanOp.SquareAccumulate, xs, ps)
        d.io.job.ready.expect(true.B); d.loan.request.ready.expect(false.B); step()
        d.io.job.valid.poke(false.B)
        var reads = 0; var writes = 0; var guard = 0
        while (!d.io.done.valid.peek().litToBoolean && guard < 200) {
          d.loan.request.ready.expect(false.B); d.loan.result.valid.expect(false.B)
          if (d.io.memory.valid.peek().litToBoolean) {
            val write = d.io.memory.bits.write.peek().litToBoolean
            val address = d.io.memory.bits.address.peek().litValue
            val tag = d.io.memory.bits.tag.peek().litValue
            val response = if (write) {
              d.io.memory.bits.data.expect(out.U); d.io.memory.bits.mask.expect(((BigInt(1) << 64) - 1).U)
              address shouldBe BigInt(0x3000); writes += 1; BigInt(0)
            } else {
              reads += 1
              if (address == 0x1000) pack(aa) else { address shouldBe BigInt(0x2000); pack(bb) }
            }
            // Offered DDR requests remain stable while the loan is waiting.
            step(2); d.io.memory.valid.expect(true.B); d.io.memory.bits.tag.expect(tag.U)
            d.io.memory.bits.address.expect(address.U)
            d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
            // A resetLoan attempt cannot disrupt a DDR response wait.
            d.loan.resetLoan.poke(true.B); step(); d.loan.resetLoan.poke(false.B)
            d.io.response.ready.expect(true.B); d.loan.request.ready.expect(false.B)
            d.io.response.bits.tag.poke(tag.U); d.io.response.bits.data.poke(response.U)
            d.io.response.bits.error.poke(false.B); d.io.response.valid.poke(true.B)
            step(); d.io.response.valid.poke(false.B)
          } else step()
          guard += 1
        }
        assert(guard < 200); reads shouldBe 2; writes shouldBe 1
        d.io.done.bits.status.expect(Status.Ok.U); d.io.done.bits.writeBytes.expect(64.U)
        d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
        // The original stable single request finally becomes admissible.
        capture(); retire(Status.Ok, expected(xs, ps), latency = 3)
      }
      // DDR-originated poison cannot be cleared using resetLoan.
      setJob(ElemOp.Copy, 0); d.io.job.valid.poke(true.B)
      setRequest(ElementwiseLoanOp.SquareAccumulate, ones, zeros)
      d.io.job.ready.expect(true.B); d.loan.request.ready.expect(false.B); step()
      d.io.job.valid.poke(false.B); d.loan.request.valid.poke(false.B)
      d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Unsupported.U)
      d.loan.resetLoan.poke(true.B); step(); d.loan.resetLoan.poke(false.B)
      d.io.done.valid.expect(true.B); d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
      d.loan.resetLoan.poke(true.B); step(); d.loan.resetLoan.poke(false.B)
      d.io.resetRequired.expect(true.B); d.loan.request.ready.expect(false.B)
      // Coordinated global reset is safe here: no memory request is outstanding.
      d.reset.poke(true.B); step(2); d.reset.poke(false.B); step()
      square(xs, ps)
      println(s"ELEMENTWISE_SQUARE_ACCUMULATE_LOAN_RTL_PASS checked_lanes=$checked earliest_retirement_edges=3 initiation_interval=4 nonfused=true clocks=$edge local_scope_only=true")
    }
  }

  it should "keep exactly sixteen ALUs, five engine wide registers and unborrowed fabric response registers" in {
    val base = circt.stage.ChiselStage.emitCHIRRTL(new ElementwiseMemoryEngine())
    val loan = circt.stage.ChiselStage.emitCHIRRTL(new ElementwiseRegisterLoan())
    def module(s: String, name: String): String = {
      val lines = s.linesIterator.toSeq
      val start = lines.indexWhere(_.startsWith(s"  module $name :"))
      assert(start >= 0, s"missing module $name")
      lines.drop(start + 1).takeWhile(x => !x.startsWith("  module ") && !x.startsWith("  extmodule ")).mkString("\n")
    }
    def registers(s: String): Seq[String] = s.linesIterator
      .filter(x => x.trim.startsWith("reg ") || x.trim.startsWith("regreset "))
      .map(_.trim.takeWhile(_ != '@').trim).toSeq.sorted
    def wide(s: String): Seq[String] = registers(s).filter(_.contains("UInt<512>"))
    val baseEngine = module(base, "ElementwiseMemoryEngine")
    val loanEngine = module(loan, "ElementwiseRegisterLoan")
    def alus(s: String): Int = s.linesIterator.count(x => x.contains("inst ") && x.contains(" of HeteroFP32Alu"))
    alus(baseEngine) shouldBe 16; alus(loanEngine) shouldBe 16
    wide(baseEngine).size shouldBe 5; wide(loanEngine) shouldBe wide(baseEngine)
    wide(module(base, "SharedL2Fabric")).size shouldBe 2
    // Entire fabric text must match, not just its registers: no loan route borrows it.
    module(loan, "SharedL2Fabric") shouldBe module(base, "SharedL2Fabric")
    registers(baseEngine).diff(registers(loanEngine)) shouldBe empty
    val added = registers(loanEngine).diff(registers(baseEngine))
    added.size shouldBe 2
    added.exists(_.startsWith("regreset loanState : UInt<3>")) shouldBe true
    added.exists(_.startsWith("regreset loanPoison : UInt<1>")) shouldBe true
    println("ELEMENTWISE_SQUARE_ACCUMULATE_RESOURCE_PASS alus=16 engine_wide_regs=5 fabric_response_regs=2 loan_state_bits=3 post_route_qor=false")
  }
}
