// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Direct production-core admission test. No replacement arithmetic, owner
  * terminal, reduced elementwise configuration, or internal signal pokes.
  * Host arithmetic supplies assertion expectations only; memory responses carry
  * original operands or a matching write ACK, never a computed owner result.
  */
class GdnRmsCoreLoanAdmissionSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  private def pack(xs: Seq[Float]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (word, (value, lane)) => word | (bits(value) << (32 * lane))
  }

  "Production core elementwise loan admission" should
    "serialize simultaneous offers, held terminals, and one real DDR Add" in {
    // This bounds unrelated core logic while retaining its exact ChainConfig()
    // and LocalSramConfig(rowsPerBank = elemCfg.localBytes / 256), plus Scalar.
    test(new Qwen2ContinuousBlock(QwenBlockShape(64, 128, 2, 1, 32, 16),
      ownerDriven = true, externalScalar = true, externalElementwiseLoan = true))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      d.clock.setTimeout(2000)
      val owner = d.io.ownerJob.get
      val loan = d.io.elementwiseLoan.get
      val scalar = d.io.scalarService.get
      val ownerTag = BigInt("1234abcd", 16)
      val firstLoanTag = BigInt("a5010001", 16)
      val secondLoanTag = BigInt("a5010002", 16)
      val fullMask = (BigInt(1) << 64) - 1
      val aAddress = BigInt(0x1000); val bAddress = BigInt(0x2000); val dstAddress = BigInt(0x3000)
      val xs = Seq.tabulate(16)(i => 1f + i.toFloat / 4f)
      val ys = Seq.tabulate(16)(i => 2f + i.toFloat / 16f)
      val loanA = Seq.tabulate(16)(i => -2f + i.toFloat / 4f)
      val loanB = Seq.tabulate(16)(i => 1f + i.toFloat / 8f)

      d.io.launch.valid.poke(false.B)
      d.io.launch.bits.base.poke(0.U); d.io.launch.bits.limit.poke(0.U)
      d.io.launch.bits.tokens.poke(0.U); d.io.launch.bits.epoch.poke(0.U)
      owner.valid.poke(false.B)
      // QwenOwnerJob is a flat UInt/Bool ABI. Initialize every current field,
      // including inactive typed-profile fields, using only leaf test pokes.
      owner.bits.elements.foreach {
        case (_, value: Bool) => value.poke(false.B)
        case (_, value: UInt) => value.poke(0.U)
        case (name, _) => fail(s"uninitialized owner field $name")
      }
      owner.bits.kind.poke(QwenOwnerKind.Add.U); owner.bits.m.poke(1.U); owner.bits.n.poke(16.U)
      owner.bits.a.poke(aAddress.U); owner.bits.b.poke(bAddress.U); owner.bits.dst.poke(dstAddress.U)
      owner.bits.writeBytes.poke(64.U); owner.bits.tag.poke(ownerTag.U)
      d.io.result.ready.poke(false.B); d.io.memory.ready.poke(false.B)
      d.io.response.valid.poke(false.B)
      d.io.response.bits.tag.poke(0.U); d.io.response.bits.data.poke(0.U); d.io.response.bits.error.poke(false.B)
      scalar.request.valid.poke(false.B); scalar.request.bits.op.poke(ScalarOp.Add.U)
      scalar.request.bits.a.poke(bits(1.25f).U); scalar.request.bits.b.poke(bits(2.5f).U)
      scalar.result.ready.poke(false.B)
      loan.request.valid.poke(false.B); loan.result.ready.poke(false.B)
      loan.abort.poke(false.B); loan.resetLoan.poke(false.B)
      loan.request.bits.tag.poke(firstLoanTag.U); loan.request.bits.op.poke(ElementwiseLoanOp.Add.U)
      loan.request.bits.a.poke(pack(loanA).U); loan.request.bits.b.poke(pack(loanB).U)
      loan.request.bits.inverse.poke(bits(1f).U)

      var clocks = 0; var ownerAccepted = 0; var ownerRetired = 0
      var loansAccepted = 0; var loansRetired = 0
      var memoryAccepted = 0; var responsesAccepted = 0; var writeAcks = 0; var commits = 0
      var scalarAccepted = 0; var scalarRetired = 0
      var pendingOwner = Option.empty[QwenOwnerJob]
      var pendingLoan = Option.empty[ElementwiseLoanRequest]
      var memoryDebt = Option.empty[(BigInt, Boolean)]
      def high(x: Bool): Boolean = x.peek().litToBoolean
      def tick(): Unit = {
        // A requester must retain valid AND its complete payload until fire.
        pendingOwner.foreach { saved => owner.valid.expect(true.B); owner.bits.expect(saved) }
        pendingLoan.foreach { saved => loan.request.valid.expect(true.B); loan.request.bits.expect(saved) }
        val ownerFire = high(owner.valid) && high(owner.ready)
        val loanFire = high(loan.request.valid) && high(loan.request.ready)
        assert(!(ownerFire && loanFire), "owner and loan accepted on the same edge")
        if (ownerAccepted == 0) d.io.result.valid.expect(false.B)
        if (loansAccepted != loansRetired) {
          owner.ready.expect(false.B); d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
        }
        if (ownerAccepted != ownerRetired) loan.request.ready.expect(false.B)
        pendingOwner = if (high(owner.valid) && !high(owner.ready)) Some(owner.bits.peek()) else None
        pendingLoan = if (high(loan.request.valid) && !high(loan.request.ready)) Some(loan.request.bits.peek()) else None
        if (ownerFire) ownerAccepted += 1
        if (loanFire) loansAccepted += 1
        if (high(loan.result.valid) && high(loan.result.ready)) loansRetired += 1
        if (high(d.io.result.valid) && high(d.io.result.ready)) ownerRetired += 1
        if (high(scalar.request.valid) && high(scalar.request.ready)) scalarAccepted += 1
        if (high(scalar.result.valid) && high(scalar.result.ready)) scalarRetired += 1
        if (high(d.io.stageCommit)) {
          assert(memoryDebt.isEmpty && writeAcks == 1, "commit before the matching write ACK")
          d.io.committedPhase.expect(8.U); commits += 1
        }
        if (high(d.io.memory.valid) && high(d.io.memory.ready)) {
          assert(memoryDebt.isEmpty, "more than one outstanding memory request")
          memoryDebt = Some((d.io.memory.bits.tag.peek().litValue, high(d.io.memory.bits.write)))
          memoryAccepted += 1
        }
        if (high(d.io.response.valid) && high(d.io.response.ready)) {
          assert(memoryDebt.nonEmpty, "response without an accepted request")
          val (tag, write) = memoryDebt.get
          d.io.response.bits.tag.expect(tag.U); d.io.response.bits.error.expect(false.B)
          if (write) writeAcks += 1
          memoryDebt = None; responsesAccepted += 1
        }
        assert(ownerAccepted <= 1 && ownerRetired <= 1)
        assert(loansRetired <= loansAccepted && loansAccepted <= 2)
        d.io.resetRequired.expect(false.B); d.io.elementwiseResetRequired.get.expect(false.B)
        loan.resetRequired.expect(false.B)
        d.clock.step(); clocks += 1
      }
      def until(description: String, limit: Int = 200)(condition: => Boolean): Unit = {
        var waited = 0
        while (!condition && waited < limit) { tick(); waited += 1 }
        assert(condition, s"timeout waiting for $description after $waited cycles")
      }
      def checkLoan(tag: BigInt, expected: BigInt): Unit = {
        loan.result.valid.expect(true.B); loan.result.bits.tag.expect(tag.U)
        loan.result.bits.status.expect(Status.Ok.U); loan.result.bits.value.expect(expected.U)
      }
      def retireLoan(tag: BigInt, expected: BigInt): Unit = {
        until("real loan terminal", 8)(high(loan.result.valid))
        for (_ <- 0 until 4) { checkLoan(tag, expected); owner.ready.expect(false.B); tick() }
        checkLoan(tag, expected); loan.result.ready.poke(true.B); tick(); loan.result.ready.poke(false.B)
        loan.result.valid.expect(false.B); loan.busy.expect(false.B)
      }

      owner.ready.expect(true.B); loan.request.ready.expect(true.B)
      // Both REAL requests are asserted on the same idle edge. Keep the owner
      // asserted and unchanged through the loan computation and held terminal.
      owner.valid.poke(true.B); loan.request.valid.poke(true.B)
      owner.ready.expect(false.B); loan.request.ready.expect(true.B)
      tick(); loan.request.valid.poke(false.B)
      ownerAccepted shouldBe 0; loansAccepted shouldBe 1
      retireLoan(firstLoanTag, pack(loanA.zip(loanB).map { case (a, b) => (a + b).toFloat }))
      ownerAccepted shouldBe 0; loansRetired shouldBe 1
      owner.ready.expect(true.B); tick(); owner.valid.poke(false.B)
      ownerAccepted shouldBe 1

      // A second offer must remain unaccepted, valid, and payload-stable for the
      // ENTIRE accepted owner operation, including its held final result. It is
      // eventually accepted and drained; no unaccepted offer is withdrawn.
      loan.request.bits.tag.poke(secondLoanTag.U); loan.request.bits.op.poke(ElementwiseLoanOp.MulIeeeRne.U)
      loan.request.bits.a.poke(pack(loanB).U); loan.request.bits.b.poke(pack(loanA).U)
      loan.request.valid.poke(true.B); loan.request.ready.expect(false.B)
      def beat(write: Boolean, address: BigInt, data: BigInt): Unit = {
        until("owner memory request")(high(d.io.memory.valid))
        val request = d.io.memory.bits.peek()
        val tag = d.io.memory.bits.tag.peek().litValue
        // The core maps Add to phase 8 and uses {epoch16,phase16,sequence32}.
        val elementwiseTag = ((ownerTag >> 16) << 16) | BigInt(8)
        tag shouldBe ((elementwiseTag << 32) | BigInt(memoryAccepted))
        d.io.memory.bits.write.expect(write.B); d.io.memory.bits.address.expect(address.U)
        d.io.memory.bits.mask.expect((if (write) fullMask else BigInt(0)).U)
        if (write) d.io.memory.bits.data.expect(data.U)
        else d.io.memory.bits.data.expect(0.U)
        for (_ <- 0 until 3) {
          d.io.memory.valid.expect(true.B); d.io.memory.bits.expect(request)
          d.io.result.valid.expect(false.B); loan.request.ready.expect(false.B); tick()
        }
        d.io.memory.ready.poke(true.B); tick(); d.io.memory.ready.poke(false.B)
        // Request acceptance is not a write ACK or a published core result.
        for (_ <- 0 until 4) {
          d.io.memory.valid.expect(false.B); d.io.response.ready.expect(true.B)
          d.io.result.valid.expect(false.B); d.io.stageCommit.expect(false.B)
          if (write) d.io.acknowledgedWriteBytes.expect(0.U)
          tick()
        }
        d.io.response.bits.tag.poke(tag.U)
        d.io.response.bits.data.poke((if (write) BigInt(0) else data).U)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B)
        tick(); d.io.response.valid.poke(false.B)
      }
      beat(false, aAddress, pack(xs))
      beat(false, bAddress, pack(ys))
      beat(true, dstAddress, pack(xs.zip(ys).map { case (x, y) => (x + y).toFloat }))
      until("real core Add terminal")(high(d.io.result.valid))
      d.io.result.bits.status.expect(Status.Ok.U); d.io.result.bits.phase.expect(8.U)
      d.io.result.bits.epoch.expect((ownerTag >> 16).U)
      d.io.result.bits.macs.expect(0.U); d.io.result.bits.executedMacs.expect(0.U)
      d.io.readBytes.expect(128.U); d.io.writeBytes.expect(64.U); d.io.acknowledgedWriteBytes.expect(64.U)
      val heldCoreResult = d.io.result.bits.peek()
      for (_ <- 0 until 4) {
        d.io.result.valid.expect(true.B); d.io.result.bits.expect(heldCoreResult)
        d.io.memory.valid.expect(false.B); loan.request.ready.expect(false.B); tick()
      }
      loansAccepted shouldBe 1; ownerRetired shouldBe 0
      d.io.result.bits.expect(heldCoreResult)
      d.io.result.ready.poke(true.B); tick(); d.io.result.ready.poke(false.B)
      ownerRetired shouldBe 1; loan.request.ready.expect(true.B)
      tick(); loan.request.valid.poke(false.B)
      retireLoan(secondLoanTag, pack(loanA.zip(loanB).map { case (a, b) => (a * b).toFloat }))

      // Exercise the actual shared BlockScalarFloat after both bank users have
      // drained. Its request/result ports are used normally; no result is poked.
      scalar.request.valid.poke(true.B); scalar.request.ready.expect(true.B)
      tick(); scalar.request.valid.poke(false.B)
      until("real Scalar Add terminal", 8)(high(scalar.result.valid))
      for (_ <- 0 until 3) {
        scalar.result.valid.expect(true.B); scalar.result.bits.expect(bits(3.75f).U)
        scalar.error.expect(false.B); owner.ready.expect(false.B); tick()
      }
      scalar.result.ready.poke(true.B); tick(); scalar.result.ready.poke(false.B)
      for (_ <- 0 until 4) {
        owner.ready.expect(true.B); loan.request.ready.expect(true.B)
        d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
        d.io.result.valid.expect(false.B); loan.result.valid.expect(false.B); scalar.result.valid.expect(false.B)
        tick()
      }
      ownerAccepted shouldBe 1; ownerRetired shouldBe 1
      loansAccepted shouldBe 2; loansRetired shouldBe 2
      memoryAccepted shouldBe 3; responsesAccepted shouldBe 3; writeAcks shouldBe 1; commits shouldBe 1
      scalarAccepted shouldBe 1; scalarRetired shouldBe 1; memoryDebt shouldBe None
      println(s"GDN_RMS_CORE_LOAN_ADMISSION_RTL_PASS core_jobs=$ownerAccepted core_results=$ownerRetired " +
        s"loan_requests=$loansAccepted loan_results=$loansRetired reads=2 writes=1 write_acks=$writeAcks " +
        s"stage_commits=$commits scalar_results=$scalarRetired clocks=$clocks smallshape_only=true")
    }
  }
}
