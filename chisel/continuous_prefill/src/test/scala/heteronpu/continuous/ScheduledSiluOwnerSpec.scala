// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Actual HardFloat owner tests. The memory service stores bytes and returns
  * responses only; expected arithmetic is never injected into the DUT. */
class ScheduledSiluOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private val aBase = BigInt("110000000", 16)
  private val bBase = BigInt("120000000", 16)
  private val cBase = BigInt("130000000", 16)
  private val fullMask = (BigInt(1) << 64) - 1
  private def bits(f: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(f).toLong & 0xffffffffL)
  private def pack(xs: Seq[BigInt]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (v, (x, i)) => v | (x << (32 * i))
  }
  // Same frozen, separately rounded degree-7 scalar recipe as VectorSiluSpec.
  private def golden(a: Float, b: Float): Float = {
    val abs = math.abs(a)
    val e = if (abs >= 80f) 0f else {
      val t = (abs * (1.0 / math.log(2.0)).toFloat).toFloat
      val k = t.toInt; val frac = (t - k.toFloat).toFloat
      val coeff = (0 to 7).map(i => (math.pow(-math.log(2.0), i) /
        (if (i == 0) 1.0 else (1 to i).map(_.toDouble).product)).toFloat)
      var h = coeff(7)
      for (i <- 6 to 0 by -1) h = ((h * frac).toFloat + coeff(i)).toFloat
      (h * java.lang.Float.intBitsToFloat((127 - k) << 23)).toFloat
    }
    val inv = (1f / (1f + e).toFloat).toFloat
    val gate = (inv * (if (java.lang.Float.floatToRawIntBits(a) < 0) e else 1f)).toFloat
    ((gate * a).toFloat * b).toFloat
  }
  private case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  private case class Pending(r: Request, due: Int, data: BigInt, error: Boolean, badTag: Boolean)

  private def initialize(d: ScheduledSiluOwner): Unit = {
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U)
    d.io.response.bits.error.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  private def job(d: ScheduledSiluOwner, count: Int, tag: BigInt): Unit = {
    val j = d.io.job.bits
    j.kind.poke(QwenOwnerKind.Activation.U); j.m.poke(1.U); j.n.poke(count.U); j.k.poke(0.U)
    j.a.poke(aBase.U); j.b.poke(bBase.U); j.c.poke(0.U); j.dst.poke(cBase.U)
    j.weightBf16.poke(false.B); j.writeBytes.poke((count.toLong * 4).U); j.tag.poke(tag.U)
  }
  private def snapshot(d: ScheduledSiluOwner): Request = {
    val r = d.io.memory.bits
    Request(r.write.peek().litToBoolean, r.address.peek().litValue, r.data.peek().litValue,
      r.mask.peek().litValue, r.tag.peek().litValue)
  }
  private def completion(d: ScheduledSiluOwner): Seq[BigInt] = {
    val r = d.io.done.bits
    Seq(r.tag.peek().litValue, r.status.peek().litValue, r.writeBytes.peek().litValue,
      r.cycles.peek().litValue, r.usefulMacs.peek().litValue, r.executedMacs.peek().litValue)
  }

  private def run(d: ScheduledSiluOwner, mode: String, count: Int, seed: Int,
                  fault: String = "none"): Unit = {
    val rng = new scala.util.Random(seed)
    val gates = Array.fill(count)((rng.nextDouble() * 30 - 15).toFloat)
    val ups = Array.fill(count)((rng.nextDouble() * 4 - 2).toFloat)
    val edge = Seq(0f, -0.0f, 1f, -1f, 10f, -10f, 79f, -79f, 80f, -80f, 0.5f, -0.5f)
    edge.zipWithIndex.foreach { case (v, i) => if (i < count) gates(i) = v }
    val numerical = fault.startsWith("numerical")
    if (numerical) gates(16) = java.lang.Float.intBitsToFloat(0x7fc00001)
    val expected = gates.zip(ups).map { case (a, b) => bits(golden(a, b)) }
    val tag = BigInt(0x50000000L + seed)
    job(d, count, tag)
    d.io.job.ready.expect(true.B); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
    d.io.done.ready.poke(false.B)
    var pending: Option[Pending] = None
    var stalled: Option[Request] = None
    var cycle = 0; var issued = 0; var returned = 0; var reads = 0; var stores = 0; var acked = 0
    var checked = 0; var injected = false; var poisonDuringWrite = false; var lateAck = false
    var stalledStore = false; var storeOfferCycles = 0
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    while (!d.io.done.valid.peek().litToBoolean && cycle < 200000) {
      val poison = d.io.resetRequired.peek().litToBoolean
      val offer = if (d.io.memory.valid.peek().litToBoolean) Some(snapshot(d)) else None
      stalled.foreach { r => assert(offer.contains(r), "stalled request withdrawn/changed") }
      val forceStoreStall = fault == "numerical-stalled-store" && offer.exists(_.write) && storeOfferCycles < 250
      if (forceStoreStall) { storeOfferCycles += 1; if (poison) stalledStore = true }
      val ready = pending.isEmpty && !forceStoreStall && (numerical || rng.nextInt(4) != 0)
      d.io.memory.ready.poke(ready.B)
      val response = pending.filter(_.due <= cycle)
      d.io.response.valid.poke(response.isDefined.B)
      response.foreach { p =>
        d.io.response.bits.data.poke(p.data.U)
        d.io.response.bits.tag.poke((p.r.tag ^ (if (p.badTag) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke(p.error.B)
      }
      val requestFire = offer.isDefined && ready
      val responseFire = response.isDefined && d.io.response.ready.peek().litToBoolean
      if (poison && pending.exists(_.r.write)) poisonDuringWrite = true
      stalled = if (offer.isDefined && !ready) offer else None
      var accepted: Option[Pending] = None
      if (requestFire) {
        assert(pending.isEmpty, "multiple outstanding transactions")
        val r = offer.get
        assert(r.tag == ((tag << 32) | issued), "nonmonotonic transaction tag")
        assert((r.address & 63) == 0, "unaligned memory request")
        var data = BigInt(0)
        if (r.write) {
          assert(r.address == cBase + stores * 64, "duplicate/out-of-order store")
          assert(r.mask == fullMask, "bad write byte mask")
          val index = stores * 16
          assert(index + 16 <= count, "out-of-bounds store")
          assert(!gates.slice(index, index + 16).exists(_.isNaN), "faulty vector was stored")
          assert(r.data == pack(expected.slice(index, index + 16).toSeq), "numerical output mismatch")
          checked += 16; stores += 1
        } else {
          val isGate = r.address >= aBase && r.address < aBase + count * 4
          val isUp = r.address >= bBase && r.address < bBase + count * 4
          assert(isGate || isUp, "read outside operand extents")
          val index = (r.address - (if (isGate) aBase else bBase)).toInt / 4
          assert(index + 16 <= count && r.mask == 0, "invalid read beat")
          data = pack((if (isGate) gates else ups).slice(index, index + 16).map(bits).toSeq)
          reads += 1
        }
        val hit = !injected && (fault match {
          case "read-gate" | "tag" => !r.write && r.address == aBase
          case "read-up" => !r.write && r.address == bBase
          case "last-store" => r.write && r.address == cBase + (count - 16) * 4
          case _ => false
        })
        if (hit) injected = true
        val delay = if (fault == "numerical-late-store" && r.write) 250 else if (numerical) 1 else 1 + rng.nextInt(27)
        accepted = Some(Pending(r, cycle + delay, data, hit && fault != "tag", hit && fault == "tag"))
        issued += 1
      }
      if (responseFire) {
        val p = response.get
        if (p.r.write && !p.error && !p.badTag) {
          committed(p.r.address) = p.r.data; acked += 1
          if (poison) lateAck = true
        }
        returned += 1
      }
      d.clock.step(); cycle += 1
      if (responseFire) pending = None
      if (accepted.isDefined) pending = accepted
    }
    assert(cycle < 200000, "owner deadlock")
    assert(pending.isEmpty && issued == returned && stalled.isEmpty, "completion before transport drain")
    d.io.memory.valid.expect(false.B); d.io.response.valid.poke(false.B); d.io.memory.ready.poke(false.B)
    val expectedStatus = if (numerical) Status.Numerical else if (fault == "tag") Status.Protocol else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.status.expect(expectedStatus.U); d.io.done.bits.tag.expect(tag.U)
    // This is a physical successful-ACK count, including an ACK after poison.
    println(s"SILU_OWNER_ACK_OBSERVED mode=$mode fault=$fault acknowledged_bytes=${acked * 64} reported_bytes=${d.io.done.bits.writeBytes.peek().litValue} late_ack=$lateAck")
    d.io.done.bits.writeBytes.expect((acked * 64).U)
    d.io.done.bits.usefulMacs.expect(0.U); d.io.done.bits.executedMacs.expect(0.U)
    if (fault == "none") {
      assert(reads == count / 8 && stores == count / 16 && committed.size == count / 16)
      assert(checked == count)
    } else if (!numerical) assert(injected, "fault not exercised")
    if (fault == "numerical-late-store") assert(poisonDuringWrite && lateAck && acked > 0, "late ACK race not exercised")
    if (fault == "numerical-stalled-store") assert(stalledStore && lateAck && acked > 0, "stalled offer race not exercised")
    val held = completion(d)
    d.clock.step(11); d.io.done.valid.expect(true.B); assert(completion(d) == held, "stalled completion changed")
    println(s"SILU_OWNER_CASE mode=$mode elements=$count seed=$seed fault=$fault cycles=${held(3)} checked_fp32=$checked read_beats=$reads write_ack_bytes=${acked * 64}")
    d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((fault == "none").B)
    if (fault != "none") { d.clock.step(5); d.io.job.ready.expect(false.B); initialize(d) }
  }

  for (overlap <- Seq(false, true)) {
    val mode = if (overlap) "overlap" else "baseline"
    s"ScheduledSiluOwner($mode)" should "preserve numeric bits, memory ordering, and acknowledged completion" in {
      test(new ScheduledSiluOwner(overlap)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
        d.clock.setTimeout(0); initialize(d)
        for (seed <- 1 to 12) run(d, mode, Seq(16, 32, 64, 256)(seed % 4), seed)
        run(d, mode, 1024, 101)
        if (overlap) {
          // Both are real numerical-error races, not externally injected status.
          run(d, mode, 64, 201, "numerical-late-store")
          run(d, mode, 64, 202, "numerical-stalled-store")
          for ((fault, i) <- Seq("read-gate", "read-up", "last-store", "tag").zipWithIndex) {
            run(d, mode, 64, 210 + i, fault)
            run(d, mode, 32, 220 + i) // same DUT after coordinated reset
          }
          for (bad <- 0 until 7) {
            job(d, 32, BigInt(0x60000000L + bad))
            bad match {
              case 0 => d.io.job.bits.n.poke(0.U); d.io.job.bits.writeBytes.poke(0.U)
              case 1 => d.io.job.bits.n.poke(17.U); d.io.job.bits.writeBytes.poke(68.U)
              case 2 => d.io.job.bits.a.poke((aBase + 4).U)
              case 3 => d.io.job.bits.a.poke(((BigInt(1) << 56) - 64).U)
              case 4 => d.io.job.bits.dst.poke(aBase.U)
              case 5 => d.io.job.bits.writeBytes.poke(64.U)
              case 6 => d.io.job.bits.kind.poke(QwenOwnerKind.Dense.U)
            }
            d.io.job.valid.poke(true.B); d.io.job.ready.expect(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
            d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
            d.io.done.bits.writeBytes.expect(0.U); d.io.memory.valid.expect(false.B)
            d.io.done.ready.poke(true.B); d.clock.step(); d.io.job.ready.expect(false.B); initialize(d)
          }
          println("SILU_OWNER_REJECT_PASS cases=7 memory_requests=0")
        }
        println(s"SILU_OWNER_SUITE_PASS mode=$mode numeric_cases=${if (overlap) 17 else 13} fault_cases=${if (overlap) 6 else 0}")
      }
    }
  }
}
