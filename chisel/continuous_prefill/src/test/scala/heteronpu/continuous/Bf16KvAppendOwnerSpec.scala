// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.collection.mutable

/** These are memory-owner tests. Synthetic 128-token copy coverage is NOT a
  * real-model M=128 numeric gate, a retained-iDMA test or a whole-block gate.
  * One persistent, full-address memory image retains actual accepted stores;
  * carried prefixes are never reloaded from a golden fixture.
  */
class Bf16KvAppendOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private val fullMask = (BigInt(1) << 64) - 1
  // Deliberately identical low 32 address bits, distinct physical addresses.
  private val keyBase = BigInt("510000000", 16)
  private val valueBase = BigInt("610000000", 16)
  private val cacheBase = BigInt("710000000", 16)
  private case class Receipt(length: BigInt, generation: BigInt)
  private val cold = Receipt(0, 0)
  private case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)

  private def init(d: Bf16KvAppendOwner): Unit = {
    d.clock.setTimeout(250000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U)
    d.io.response.bits.error.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
    d.io.job.ready.expect(true.B); d.io.done.valid.expect(false.B)
    d.io.resetRequired.expect(false.B); d.io.memory.valid.expect(false.B)
  }

  private def setJob(d: Bf16KvAppendOwner, previous: Receipt, tokens: Int, capacity: BigInt,
                     tag: BigInt, base: BigInt = cacheBase): Unit = {
    d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.kvHeads.poke(2.U)
    d.io.job.bits.headDim.poke(256.U)
    d.io.job.bits.keyInput.poke(keyBase.U); d.io.job.bits.valueInput.poke(valueBase.U)
    d.io.job.bits.cacheBase.poke(base.U); d.io.job.bits.capacityTokens.poke(capacity.U)
    d.io.job.bits.appendStart.poke(previous.length.U)
    d.io.job.bits.currentLength.poke(previous.length.U)
    d.io.job.bits.expectedLength.poke(previous.length.U)
    d.io.job.bits.currentGeneration.poke(previous.generation.U)
    d.io.job.bits.expectedGeneration.poke(previous.generation.U)
    d.io.job.bits.cold.poke((previous == cold).B); d.io.job.bits.tag.poke(tag.U)
  }

  private def request(d: Bf16KvAppendOwner): Request = Request(
    d.io.memory.bits.write.peek().litToBoolean, d.io.memory.bits.address.peek().litValue,
    d.io.memory.bits.data.peek().litValue, d.io.memory.bits.mask.peek().litValue,
    d.io.memory.bits.tag.peek().litValue)

  private def completion(d: Bf16KvAppendOwner): Seq[BigInt] = Seq(
    d.io.done.bits.tag.peek().litValue, d.io.done.bits.cacheBase.peek().litValue,
    d.io.done.bits.capacityTokens.peek().litValue, d.io.done.bits.status.peek().litValue,
    d.io.done.bits.writeBytes.peek().litValue, d.io.done.bits.cycles.peek().litValue,
    d.io.done.bits.proposalValid.peek().litValue, d.io.done.bits.proposedLength.peek().litValue,
    d.io.done.bits.proposedGeneration.peek().litValue)

  private def pattern(beat: Int, salt: Int): BigInt = (0 until 32).foldLeft(BigInt(0)) { (word, lane) =>
    // A 128-token plane covers every BF16 bit pattern, including NaN, infinity,
    // signed zero and subnormals. Append performs no arithmetic or conversion.
    val bits = ((beat * 32 + lane) * 40503 + salt) & 65535
    word | (BigInt(bits) << (lane * 16))
  }

  private class Memory(capacity: Int, base: BigInt = cacheBase) {
    val image = mutable.Map.empty[BigInt, BigInt]
    private var nextTag = BigInt("31410000", 16)
    private val planeBytes = BigInt(capacity) * 1024
    // Install sentinels once. Subsequent calls and DUT resets retain this map.
    for (index <- -1 to capacity * 32) image(base + index * 64) = pattern(index, 0x9a6d)

    private def checkUnchanged(before: Map[BigInt, BigInt], allowed: Set[BigInt], previous: Receipt): Unit = {
      for ((address, value) <- before if !allowed(address)) {
        assert(image(address) == value, s"write outside the two active tails at 0x${address.toString(16)}")
      }
      for (plane <- 0 until 2; index <- 0 until (previous.length * 16).toInt) {
        val address = base + plane * planeBytes + index * 64
        assert(image(address) == before(address), "published prefix changed")
      }
    }

    /** A nonempty result is an actual accepted successful done receipt. A
      * failure/reset returns None; caller must retain its prior receipt.
      * Erroring stores update physical memory anyway, deliberately modeling
      * the conservative case where a failed ACK cannot undo a DMA write.
      */
    def run(d: Bf16KvAppendOwner, previous: Receipt, tokens: Int, label: String,
            fault: String = "none", salt: Int = 1): Option[Receipt] = {
      val count = tokens * 16
      for (index <- 0 until count) {
        image(keyBase + index * 64) = pattern(index, salt)
        image(valueBase + index * 64) = pattern(index, salt + 0x4d17)
      }
      val before = image.toMap
      val destinations = (for (plane <- 0 until 2; index <- 0 until count) yield {
        val input = (if (plane == 0) keyBase else valueBase) + index * 64
        (base + plane * planeBytes + previous.length * 1024 + index * 64) -> before(input)
      }).toMap
      val allowed = destinations.keySet
      val tag = nextTag; nextTag += 1
      setJob(d, previous, tokens, capacity, tag, base)
      d.io.job.ready.expect(true.B); d.io.job.valid.poke(true.B)
      d.clock.step(); d.io.job.valid.poke(false.B)
      var issued = 0; var ackBytes = 0; var injected = false
      val reads = mutable.ArrayBuffer.empty[BigInt]
      val writes = mutable.ArrayBuffer.empty[BigInt]
      var lastRead: Option[BigInt] = None
      while (!d.io.done.valid.peek().litToBoolean && issued < count * 4 + 1) {
        d.io.memory.valid.expect(true.B)
        d.io.done.bits.proposalValid.expect(false.B)
        d.io.done.bits.proposedLength.expect(previous.length.U)
        d.io.done.bits.proposedGeneration.expect(previous.generation.U)
        val r = request(d)
        assert(r.tag == ((tag << 32) | issued), "memory sequence/tag mismatch")
        assert((r.address & 63) == 0, "unaligned memory packet")
        val plane = issued / (count * 2)
        val index = (issued / 2) % count
        assert(r.write == (issued % 2 == 1), "one buffered read must precede each store")
        val source = (if (plane == 0) keyBase else valueBase) + index * 64
        val dest = base + plane * planeBytes + previous.length * 1024 + index * 64
        if (r.write) {
          assert(r.address == dest && allowed(r.address), "not an active tail address")
          assert(r.mask == fullMask, "retained adapters require full64 stores")
          assert(r.data == lastRead.get && r.data == destinations(r.address), "store differs from actual read response")
          assert(!writes.contains(r.address), "duplicate store")
        } else {
          assert(r.address == source && r.mask == 0, "unexpected source read")
        }
        val delay = 1 + issued % 3
        d.clock.step(delay)
        assert(request(d) == r, "memory request changed while stalled")
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        // Physical effects are modeled at request acceptance, before the ACK.
        if (r.write) { image(r.address) = r.data; writes += r.address }
        else reads += r.address
        val finalK = r.write && plane == 0 && index == count - 1
        val finalV = r.write && plane == 1 && index == count - 1
        val firstRead = !r.write && issued == 0
        val resetHere = (fault == "reset-read" && firstRead) ||
          (fault == "reset-final-k" && finalK) || (fault == "reset-final-v" && finalV)
        val failHere = !injected && (fault match {
          case "read" | "read-tag" => firstRead
          case "write" => r.write
          case "value-read" => !r.write && plane == 1
          case "final-k" | "final-k-tag" => finalK
          case "final-v" | "final-v-tag" => finalV
          case _ => false
        })
        d.clock.step(if (finalK || finalV) 17 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.proposalValid.expect(false.B)
        d.io.job.ready.expect(false.B); d.io.memory.valid.expect(false.B)
        if (finalK || finalV) checkUnchanged(before, allowed, previous)
        if (resetHere) {
          init(d) // Joint transport reset drops the held response, retains DDR.
          checkUnchanged(before, allowed, previous)
          println(s"BF16_KV_APPEND_MEMORY_OWNER label=$label reset=true prior_length=${previous.length} prior_generation=${previous.generation} proposal=false physical_stores=${writes.size} model_m128=false")
          return None
        }
        val wrongTag = failHere && fault.endsWith("tag")
        val reply = if (r.write) BigInt(0) else image(r.address)
        d.io.response.bits.data.poke(reply.U)
        d.io.response.bits.tag.poke((r.tag ^ (if (wrongTag) BigInt(1) << 32 else BigInt(0))).U)
        d.io.response.bits.error.poke((failHere && !wrongTag).B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B)
        d.clock.step(); d.io.response.valid.poke(false.B)
        if (r.write && !failHere) ackBytes += 64
        if (!r.write && !failHere) lastRead = Some(reply)
        injected ||= failHere
        issued += 1
      }
      d.io.done.valid.expect(true.B)
      val code = if (!injected) Status.Ok else if (fault.endsWith("tag")) Status.Protocol else Status.Memory
      d.io.done.bits.tag.expect(tag.U); d.io.done.bits.cacheBase.expect(base.U)
      d.io.done.bits.capacityTokens.expect(capacity.U); d.io.done.bits.status.expect(code.U)
      d.io.done.bits.writeBytes.expect(ackBytes.U)
      d.io.done.bits.proposalValid.expect((code == Status.Ok).B)
      val proposed = if (code == Status.Ok) Receipt(previous.length + tokens, previous.generation + 1) else previous
      d.io.done.bits.proposedLength.expect(proposed.length.U)
      d.io.done.bits.proposedGeneration.expect(proposed.generation.U)
      d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
      d.io.job.ready.expect(false.B)
      checkUnchanged(before, allowed, previous)
      if (code == Status.Ok) {
        assert(issued == count * 4 && ackBytes == tokens * 2048)
        assert(writes.toSet == allowed && writes.size == allowed.size)
        assert(reads.size == count * 2 && reads.distinct.size == reads.size)
        assert(destinations.forall { case (address, value) => image(address) == value })
      } else assert(injected)
      val held = completion(d)
      d.io.job.valid.poke(true.B) // Backpressured done must block a new job.
      d.clock.step(13)
      d.io.job.ready.expect(false.B); d.io.memory.valid.expect(false.B)
      assert(completion(d) == held, "done result changed under backpressure")
      d.io.job.valid.poke(false.B)
      if (fault == "reset-done") {
        init(d)
        checkUnchanged(before, allowed, previous)
        println(s"BF16_KV_APPEND_MEMORY_OWNER label=$label reset_before_done_fire=true prior_length=${previous.length} prior_generation=${previous.generation} receipt=false model_m128=false")
        return None
      }
      // The actual successful result, sampled before fire, is the only source
      // of carried metadata. No expected/golden receipt seeds subsequent jobs.
      val actual = Receipt(d.io.done.bits.proposedLength.peek().litValue,
        d.io.done.bits.proposedGeneration.peek().litValue)
      d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
      d.io.done.valid.expect(false.B); d.io.done.bits.proposalValid.expect(false.B)
      d.io.resetRequired.expect((code != Status.Ok).B)
      d.io.job.ready.expect((code == Status.Ok).B)
      if (code != Status.Ok) {
        d.io.job.valid.poke(true.B); d.clock.step(7)
        d.io.job.ready.expect(false.B); d.io.memory.valid.expect(false.B)
        d.io.done.valid.expect(false.B); d.io.job.valid.poke(false.B)
      }
      println(s"BF16_KV_APPEND_MEMORY_OWNER label=$label tokens=$tokens status=$code ack_bytes=$ackBytes proposal=${code == Status.Ok} proposed_length=${actual.length} proposed_generation=${actual.generation} model_m128=false")
      if (code == Status.Ok) Some(actual) else None
    }
  }

  "Bf16KvAppendOwner" should "preserve actual cold and carried prefixes and propose only after both final ACKs" in {
    test(new Bf16KvAppendOwner).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      val memory = new Memory(16)
      val one = memory.run(d, cold, 1, "cold-one", salt = 11).get
      val two = memory.run(d, one, 1, "carried-one", salt = 22).get
      val seven = memory.run(d, two, 5, "carried-five", salt = 33).get
      val full = memory.run(d, seven, 9, "carried-nine-capacity-boundary", salt = 44).get
      assert(full == Receipt(16, 4))
      // Reset retains actual cache bytes and uses the last accepted receipt.
      init(d)
      setJob(d, full, 1, 16, 0x1717)
      d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
      d.io.done.bits.proposalValid.expect(false.B); d.io.memory.valid.expect(false.B)
      d.io.done.bits.proposedLength.expect(full.length.U)
      d.io.done.bits.proposedGeneration.expect(full.generation.U)
    }
  }

  it should "leave failed tails unpublished, lock, and retry from actual receipts without reloading prefixes" in {
    test(new Bf16KvAppendOwner).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      val memory = new Memory(64)
      var published = memory.run(d, cold, 1, "fault-seed", salt = 51).get
      for ((fault, index) <- Seq("read", "read-tag", "write", "value-read", "final-k", "final-k-tag",
        "final-v", "final-v-tag", "reset-read", "reset-final-k", "reset-final-v", "reset-done").zipWithIndex) {
        val prior = published
        val result = memory.run(d, published, 2, fault, fault, salt = 100 + index)
        assert(result.isEmpty && published == prior, "failure/reset published metadata")
        init(d) // Retain Memory.image and the prior actual successful receipt.
        published = memory.run(d, prior, 2, s"retry-$fault", salt = 500 + index).get
        assert(published.length == prior.length + 2 && published.generation == prior.generation + 1)
      }
      assert(published == Receipt(25, 13))
    }
  }

  it should "copy synthetic 128-token memory windows at full64 width without claiming a model M128 gate" in {
    test(new Bf16KvAppendOwner).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      // Allocation ends exactly at the retained 56-bit aperture boundary.
      val base = (BigInt(1) << 56) - BigInt(260) * 2048
      val memory = new Memory(260, base)
      val first = memory.run(d, cold, 128, "synthetic-memory-only-cold-128", salt = 79).get
      val second = memory.run(d, first, 128, "synthetic-memory-only-carried-128", salt = 113).get
      assert(second == Receipt(256, 2))
    }
  }

  it should "reject malformed geometry, stale snapshots, full-aperture aliases and overflow before any memory access" in {
    test(new Bf16KvAppendOwner).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val cases: Seq[(String, Int, Bf16KvAppendOwner => Unit)] = Seq(
        ("zero-tokens", Status.Bounds, _.io.job.bits.tokens.poke(0.U)),
        ("too-many-tokens", Status.Bounds, _.io.job.bits.tokens.poke(129.U)),
        ("heads", Status.Bounds, _.io.job.bits.kvHeads.poke(1.U)),
        ("dimension", Status.Bounds, _.io.job.bits.headDim.poke(128.U)),
        ("zero-capacity", Status.Bounds, _.io.job.bits.capacityTokens.poke(0.U)),
        ("capacity-overrun", Status.Bounds, _.io.job.bits.tokens.poke(17.U)),
        ("published-outside-capacity", Status.Bounds, _.io.job.bits.currentLength.poke(17.U)),
        ("key-alignment", Status.Bounds, _.io.job.bits.keyInput.poke((keyBase + 2).U)),
        ("value-alignment", Status.Bounds, _.io.job.bits.valueInput.poke((valueBase + 2).U)),
        ("cache-alignment", Status.Bounds, _.io.job.bits.cacheBase.poke((cacheBase + 2).U)),
        ("source-same", Status.Bounds, _.io.job.bits.valueInput.poke(keyBase.U)),
        ("source-partial-overlap", Status.Bounds, _.io.job.bits.valueInput.poke((keyBase + 64).U)),
        ("cache-key", Status.Bounds, _.io.job.bits.keyInput.poke(cacheBase.U)),
        ("cache-value", Status.Bounds, _.io.job.bits.valueInput.poke((cacheBase + 16 * 1024).U)),
        ("unused-key-aperture", Status.Bounds, _.io.job.bits.keyInput.poke((cacheBase + 15 * 1024).U)),
        ("unused-value-aperture", Status.Bounds, _.io.job.bits.valueInput.poke((cacheBase + 31 * 1024).U)),
        ("key-overflow56", Status.Bounds, _.io.job.bits.keyInput.poke(((BigInt(1) << 56) - 64).U)),
        ("value-overflow56", Status.Bounds, _.io.job.bits.valueInput.poke(((BigInt(1) << 56) - 64).U)),
        ("cache-full-aperture-overflow56", Status.Bounds, _.io.job.bits.cacheBase.poke(((BigInt(1) << 56) - 2048).U)),
        ("key-overflow64", Status.Bounds, _.io.job.bits.keyInput.poke(((BigInt(1) << 64) - 64).U)),
        ("value-overflow64", Status.Bounds, _.io.job.bits.valueInput.poke(((BigInt(1) << 64) - 64).U)),
        ("cache-overflow64", Status.Bounds, _.io.job.bits.cacheBase.poke(((BigInt(1) << 64) - 64).U)),
        ("append-overflow32", Status.Bounds, _.io.job.bits.appendStart.poke("hffffffff".U)),
        ("wrong-append", Status.Dependency, _.io.job.bits.appendStart.poke(1.U)),
        ("wrong-expected-length", Status.Dependency, _.io.job.bits.expectedLength.poke(1.U)),
        ("wrong-expected-generation", Status.Dependency, _.io.job.bits.expectedGeneration.poke(1.U)),
        ("carried-zero-metadata", Status.Dependency, _.io.job.bits.cold.poke(false.B)),
        ("cold-nonzero-generation", Status.Dependency, d => {
          d.io.job.bits.currentGeneration.poke(1.U); d.io.job.bits.expectedGeneration.poke(1.U)
        }),
        ("cold-nonzero-length", Status.Dependency, d => {
          d.io.job.bits.currentLength.poke(1.U); d.io.job.bits.expectedLength.poke(1.U)
          d.io.job.bits.appendStart.poke(1.U)
        }),
        ("generation-wrap", Status.Dependency, d => {
          d.io.job.bits.currentGeneration.poke("hffffffff".U)
          d.io.job.bits.expectedGeneration.poke("hffffffff".U)
        }),
        ("carried-zero-generation", Status.Dependency, d => {
          d.io.job.bits.cold.poke(false.B); d.io.job.bits.currentLength.poke(1.U)
          d.io.job.bits.expectedLength.poke(1.U); d.io.job.bits.appendStart.poke(1.U)
        }),
        ("carried-zero-length", Status.Dependency, d => {
          d.io.job.bits.cold.poke(false.B); d.io.job.bits.currentGeneration.poke(1.U)
          d.io.job.bits.expectedGeneration.poke(1.U)
        }))
      for ((label, status, mutate) <- cases) {
        init(d); setJob(d, cold, 1, 16, 0x7171); mutate(d)
        val priorLength = d.io.job.bits.currentLength.peek().litValue
        val priorGeneration = d.io.job.bits.currentGeneration.peek().litValue
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(status.U)
        d.io.done.bits.proposalValid.expect(false.B); d.io.done.bits.writeBytes.expect(0.U)
        d.io.done.bits.proposedLength.expect(priorLength.U)
        d.io.done.bits.proposedGeneration.expect(priorGeneration.U)
        d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
        val held = completion(d); d.clock.step(5); assert(completion(d) == held)
        d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
        d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B)
        println(s"BF16_KV_APPEND_REJECT label=$label status=$status memory_requests=0")
      }
    }
  }
}
