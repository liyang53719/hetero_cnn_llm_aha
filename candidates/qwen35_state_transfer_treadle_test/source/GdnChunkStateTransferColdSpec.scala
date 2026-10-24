// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Prepared source only: one real-owner cold M16/head0 Initialize transaction.
  * The endpoint supplies controlled ACKs; it is not a DDR or arithmetic model.
  * Compilation, elaboration and execution require separate admission.
  */
class GdnChunkStateTransferColdSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "GdnChunkStateTransferOwner cold M16/head0"

  it should "zero exactly 1024 private beats and hold completion until accepted" in {
    test(new GdnChunkStateTransferOwner)
      .withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      val maxClockSteps = 20000
      val beatCount = 1024
      val beatBytes = 64
      val jobTag = BigInt("a1b2c3d4", 16)
      val nextJobTag = BigInt("55667788", 16)
      val scratchBase = BigInt("01000000", 16)
      val fullMask = (BigInt(1) << 64) - 1
      val ackData = (BigInt(1) << 512) - 1 // Deliberately nonzero, ignored for writes.
      var clockSteps = 0
      var activeCycles = 0
      var accepted = 0
      var acknowledged = 0
      var ackBytes = BigInt(0)
      var requestStallCycles = 0
      var responseStallCycles = 0
      var delayedAckCycles = 0

      // The only explicit clock.step site, including reset and held-done checks.
      def tick(active: Boolean = false): Unit = {
        assert(clockSteps < maxClockSteps, "20,000 explicit clock-step limit")
        d.clock.step()
        clockSteps += 1
        if (active) activeCycles += 1
      }
      d.clock.setTimeout(maxClockSteps)

      def clearReceipt(r: GdnChunkStageReceipt): Unit = {
        r.tag.poke(0.U); r.expectedGeneration.poke(0.U)
        r.head.poke(0.U); r.chunk.poke(0.U); r.phase.poke(0.U)
        r.status.poke(0.U); r.scratchAckBytes.poke(0.U)
        r.outputAckBytes.poke(0.U); r.stateAckBytes.poke(0.U)
        r.drained.poke(false.B)
      }
      d.io.job.valid.poke(false.B)
      val j = d.io.job.bits
      val c = j.context
      c.tag.poke(jobTag.U); c.tokens.poke(16.U); c.cold.poke(true.B)
      c.expectedGeneration.poke(0.U); c.vectorPolicy.poke(0.U)
      // Complete, 64-byte-aligned, disjoint spans, including unused cold stateIn.
      c.input.poke(BigInt("00100000", 16).U)
      c.stateIn.poke(BigInt("00400000", 16).U)
      c.stateOut.poke(BigInt("00800000", 16).U)
      c.output.poke(BigInt("00c00000", 16).U)
      c.scratch.poke(scratchBase.U)
      j.head.poke(0.U); j.operation.poke(0.U)
      clearReceipt(j.nextStateReady); clearReceipt(j.outputReady)
      d.io.committed.valid.poke(false.B)
      d.io.committed.generation.poke(0.U); d.io.committed.state.poke(0.U)
      d.io.memory.ready.poke(false.B); d.io.done.ready.poke(false.B)
      d.io.response.valid.poke(false.B)
      d.io.response.bits.tag.poke(0.U); d.io.response.bits.data.poke(ackData.U)
      d.io.response.bits.error.poke(false.B)
      d.reset.poke(true.B); tick(); tick()
      d.reset.poke(false.B); tick()

      d.io.job.ready.expect(true.B)
      d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
      d.io.done.valid.expect(false.B); d.io.resetRequired.expect(false.B)
      d.io.job.valid.poke(true.B)
      tick() // The only accepted job; this edge initializes owner cycles to zero.
      // Keep a distinct second offer stable, but never accept or execute it.
      c.tag.poke(nextJobTag.U)

      def expectBusy(): Unit = {
        d.io.job.ready.expect(false.B)
        d.io.done.valid.expect(false.B); d.io.resetRequired.expect(false.B)
        d.io.done.bits.readBytes.expect(0.U)
        d.io.done.bits.writeBytes.expect(ackBytes.U)
        d.io.done.bits.cycles.expect(activeCycles.U)
      }
      def expectRequest(index: Int): Unit = {
        expectBusy()
        d.io.memory.valid.expect(true.B)
        d.io.memory.bits.write.expect(true.B)
        d.io.memory.bits.address.expect((scratchBase + BigInt(index) * beatBytes).U)
        d.io.memory.bits.tag.expect(((jobTag << 32) | BigInt(index)).U)
        d.io.memory.bits.mask.expect(fullMask.U)
        d.io.memory.bits.data.expect(0.U)
        d.io.response.ready.expect(false.B)
      }
      def expectWaiting(): Unit = {
        expectBusy()
        d.io.memory.valid.expect(false.B)
        d.io.response.ready.expect(true.B)
      }

      for (index <- 0 until beatCount) {
        assert(accepted == index && acknowledged == index)
        d.io.memory.ready.poke(false.B)
        d.io.response.valid.poke(false.B)
        // Every request is observed unchanged on stalled cycles and its fire edge.
        for (_ <- 0 until (1 + index % 3)) {
          expectRequest(index)
          tick(active = true)
          requestStallCycles += 1
        }

        val responseTag = (jobTag << 32) | BigInt(index)
        val immediateAck = index % 4 == 0
        d.io.memory.ready.poke(true.B)
        d.io.response.bits.tag.poke(responseTag.U)
        d.io.response.valid.poke(immediateAck.B)
        expectRequest(index)
        d.io.memory.ready.expect(true.B)
        if (immediateAck) {
          // Zero-latency producer: response.valid on request.fire, ready is low.
          d.io.response.valid.expect(true.B)
          responseStallCycles += 1
        }
        tick(active = true) // memory.fire; no response can fire on this edge.
        accepted += 1
        d.io.memory.ready.poke(false.B)
        assert(accepted - acknowledged == 1, "exactly one outstanding write")

        if (!immediateAck) {
          // No ACK means no byte credit, next request, or early completion.
          for (_ <- 0 until (1 + index % 4)) {
            expectWaiting()
            d.io.response.valid.expect(false.B)
            tick(active = true)
            delayedAckCycles += 1
          }
          d.io.response.valid.poke(true.B)
        }
        // For immediate ACKs no payload/valid poke occurred after the stalled edge.
        expectWaiting()
        d.io.response.valid.expect(true.B)
        d.io.response.bits.tag.expect(responseTag.U)
        d.io.response.bits.data.expect(ackData.U)
        d.io.response.bits.error.expect(false.B)
        tick(active = true) // Matching successful response.fire, one 64-byte ACK.
        acknowledged += 1
        ackBytes += beatBytes // MemoryResponse has no nbytes or direction field.
        d.io.response.valid.poke(false.B)
      }

      assert(accepted == 1024 && acknowledged == 1024 && ackBytes == 65536)
      assert(requestStallCycles == 2047 && responseStallCycles == 256)
      assert(delayedAckCycles == 2304 && activeCycles == 6399)

      def expectDone(): Unit = {
        d.io.done.valid.expect(true.B); d.io.job.ready.expect(false.B)
        d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
        d.io.resetRequired.expect(false.B)
        val r = d.io.done.bits
        r.tag.expect(jobTag.U); r.expectedGeneration.expect(0.U)
        r.head.expect(0.U); r.operation.expect(0.U); r.status.expect(Status.Ok.U)
        r.readBytes.expect(0.U); r.writeBytes.expect(65536.U)
        r.cycles.expect(activeCycles.U)
        r.transferComplete.expect(true.B); r.localDrained.expect(true.B)
      }
      for (_ <- 0 until 8) {
        expectDone() // Every result field, including cycles, remains constant.
        d.io.done.ready.expect(false.B)
        d.io.job.valid.expect(true.B)
        tick()
      }
      expectDone()
      d.io.done.ready.poke(true.B)
      expectDone() // The pending job is still blocked on the done.fire edge.
      tick()
      d.io.done.valid.expect(false.B)
      d.io.job.ready.expect(true.B)
      d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
      d.io.resetRequired.expect(false.B)
      // End before any idle clock edge: the pending second offer never fires.
      assert(clockSteps == 6412 && clockSteps <= maxClockSteps)
      println(s"GDN_CHUNK_COLD_PASS accepted=$accepted acknowledged=$acknowledged " +
        s"ackBytes=$ackBytes activeCycles=$activeCycles clockSteps=$clockSteps")
    }
  }
}
