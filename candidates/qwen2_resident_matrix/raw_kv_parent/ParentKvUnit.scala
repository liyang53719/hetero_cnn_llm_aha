// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.{VerilatorBackendAnnotation, VerilatorCFlags}
import org.scalatest.flatspec.AnyFlatSpec
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}
import scala.collection.mutable

/** The original composed parent is the DUT. No replacement parent, DMA RTL,
  * Matrix arithmetic implementation, or additional payload memory is built.
  * The software services below are deliberately bounded protocol test agents.
  */
object ParentKvHarness {
  def owner(raw: Boolean): TransposedDenseDownOwner = new TransposedDenseDownOwner(
    burstWrites = true, enableFfnTiles = true, enableFfnWindow = true,
    enableFfnDrain = true, enableKWindow = true, enableDenseDrain = true,
    enableRawKv = raw)
}

object ParentKvElaborate extends App {
  require(args.length == 1, "ParentKvElaborate requires an output directory")
  val out = Paths.get(args(0))
  Files.createDirectories(out)
  for (raw <- Seq(false, true)) {
    Files.writeString(out.resolve(s"parent_raw${if (raw) 1 else 0}.fir"),
      ChiselStage.emitCHIRRTL(ParentKvHarness.owner(raw)))
  }
}

class ParentKvUnit extends AnyFlatSpec with ChiselScalatestTester {
  // Fixed markers contain no addresses, tags, data or internal state.
  private def progress(event: String, scenario: String, cycle: Int = 0): Unit = {
    println(s"PARENT_PROGRESS $event $scenario $cycle")
    Console.out.flush()
  }
  private val aBase = BigInt(0x100000)
  private val bBase = BigInt(0x200000)
  private val dstBase = BigInt(0x300000)
  private val prefixBase = BigInt(0x400000)
  private val ownerId = BigInt(0x1234)
  private def yes(x: Bool): Boolean = x.peek().litToBoolean
  private def number(x: UInt): BigInt = x.peek().litValue

  // Recursive literal pokes, not zero.asTypeOf: this runs outside a Module.
  private def zero(x: Data): Unit = x match {
    case b: Bool => b.poke(false.B)
    case u: UInt => u.poke(0.U)
    case s: SInt => s.poke(0.S)
    case v: Vec[_] => v.foreach(e => zero(e))
    case r: Record => r.elements.values.foreach(zero)
    case other => throw new IllegalArgumentException(s"unsupported input leaf $other")
  }
  private def defaults(d: TransposedDenseDownOwner): Unit = {
    d.io.job.valid.poke(false.B); zero(d.io.job.bits)
    d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B)
    d.io.response.valid.poke(false.B); zero(d.io.response.bits)
    d.io.burst.ready.poke(false.B)
    d.io.burstResponse.valid.poke(false.B); zero(d.io.burstResponse.bits)
    d.io.writeRequest.get.ready.poke(false.B)
    d.io.writeData.get.ready.poke(false.B)
    d.io.writeResponse.get.valid.poke(false.B); zero(d.io.writeResponse.get.bits)
    zero(d.io.prefixWorkspace.get)
    d.io.physicalSteps.poke(0.U)
    d.io.matrix.group.ready.poke(false.B); d.io.matrix.step.ready.poke(false.B)
    d.io.matrix.result.valid.poke(false.B); zero(d.io.matrix.result.bits)
    d.io.matrix.done.valid.poke(false.B); zero(d.io.matrix.done.bits)
    val seed = d.io.matrix.seed.get
    seed.begin.ready.poke(false.B); seed.beat.ready.poke(false.B)
    seed.ack.valid.poke(false.B); zero(seed.ack.bits)
    val tile = d.io.tiles.get
    tile.control.valid.poke(false.B); zero(tile.control.bits)
    tile.write.valid.poke(false.B); zero(tile.write.bits)
    tile.read.valid.poke(false.B); zero(tile.read.bits)
    tile.response.ready.poke(false.B); tile.abort.poke(false.B)
    val window = d.io.window.get
    window.request.valid.poke(false.B); zero(window.request.bits)
    window.result.ready.poke(false.B); window.invalidateLease.poke(false.B)
    val drain = d.io.drain.get
    drain.request.valid.poke(false.B); zero(drain.request.bits)
    drain.result.ready.poke(false.B); drain.abort.poke(false.B)
    d.io.rawKv.foreach { raw =>
      raw.acquire.valid.poke(false.B); raw.acquire.bits.poke(0.U)
      raw.release.valid.poke(false.B); raw.release.bits.poke(0.U)
      raw.request.valid.poke(false.B); zero(raw.request.bits)
      raw.ack.valid.poke(false.B); zero(raw.ack.bits)
      raw.abort.poke(false.B); raw.softReset.poke(false.B)
    }
  }
  private def workspace(d: TransposedDenseDownOwner): Unit = {
    val w = d.io.prefixWorkspace.get
    w.valid.poke(true.B); w.base.poke(prefixBase.U); w.extent.poke(16384.U)
    w.generation.poke(7.U); w.splitK.poke(128.U)
  }
  private def job(j: QwenOwnerJob, k: Int, tag: Int): Unit = {
    zero(j)
    j.kind.poke(QwenOwnerKind.Dense.U); j.m.poke(16.U)
    j.n.poke(32.U); j.k.poke(k.U)
    j.a.poke(aBase.U); j.b.poke(bBase.U); j.dst.poke(dstBase.U)
    j.writeBytes.poke(2048.U); j.tag.poke(tag.U)
  }
  // Exact BF16-representable finite FP32 ingress patterns. This is routing
  // stimulus, not a matrix multiplication or numerical correctness oracle.
  private def activation(row: Int, k: Int): BigInt =
    BigInt(0x3f800000L) + (BigInt((row * 5 + k) & 31) << 16)
  private def weight(k: Int, col: Int): BigInt =
    BigInt(0x40000000L) + (BigInt((k * 3 + col) & 31) << 16)
  private def token(sequence: BigInt, row: Int, col: Int): BigInt =
    BigInt(0x3f000000L) | ((sequence & 127) << 13) | (BigInt(row) << 8) | BigInt(col)
  private def packet(words: Seq[BigInt]): BigInt =
    words.zipWithIndex.foldLeft(BigInt(0)) { case (v, (w, i)) => v | (w << (32 * i)) }

  /** One accepted descriptor at a time, delayed matching responses, explicit
    * seed identity and beat counts, and a synthetic Matrix result ONLY after
    * the owner's accepted terminal step. Every outstanding item is tracked.
    */
  private class Services(d: TransposedDenseDownOwner, k: Int, window: Boolean) {
    private case class Read(address: BigInt, tag: BigInt, data: BigInt, due: Int)
    private case class Write(address: BigInt, tag: BigInt, beats: Int,
      var received: Int = 0, var due: Int = Int.MaxValue)
    private case class Seed(tag: BigInt, sequence: BigInt, generation: BigInt,
      context: BigInt, var received: Int = 0, var due: Int = Int.MaxValue)
    private var read: Option[Read] = None
    private var write: Option[Write] = None
    private var seed: Option[Seed] = None
    private var matrixActive = false
    private var matrixTag = BigInt(0)
    private var matrixSequence = BigInt(0)
    private var lastAcceptedResultSequence: Option[BigInt] = None
    private var groupSteps = 0
    private var resultPending = false
    private var resultLoaded = false
    private var resultDue = Int.MaxValue
    private var doneDue = Int.MaxValue
    private var physical = number(d.io.physicalSteps).toInt
    private val scenario = if (window) "retained_a_window"
      else if (d.io.rawKv.isDefined) "enabled_dense_drain" else "default_off_dense"
    var cycle = 0
    var readsAccepted = 0; var readsReturned = 0
    var groups = 0; var results = 0; var matrixDones = 0; var steps = 0
    var writeCommands = 0; var writeAcks = 0
    var prefixWriteBytes = 0; var outputWriteBytes = 0
    var prefixAckBytes = 0; var outputAckBytes = 0
    var prefixReads = 0; var seedBegins = 0; var seedBeats = 0; var seedAcks = 0
    var dmaHeldCycles = 0; var seedAckHeldCycles = 0
    var outputAckHeldCycles = 0; var matrixDoneHeldCycles = 0
    val stored = mutable.Map.empty[BigInt, BigInt]
    private val acknowledged = mutable.Set.empty[BigInt]
    private def prefix(address: BigInt): Boolean = address >= prefixBase && address < prefixBase + 16384
    private def readData(address: BigInt): BigInt = {
      if (prefix(address)) {
        assert(stored.contains(address), s"prefix read before actual accepted write: $address")
        assert(acknowledged.contains(address), s"prefix read before matching write ACK: $address")
        prefixReads += 1
        stored(address)
      } else if (address >= aBase && address < aBase + 16 * k * 4) {
        val first = ((address - aBase) / 4).toInt
        packet((0 until 16).map(i => activation((first + i) / k, (first + i) % k)))
      } else {
        assert(address >= bBase && address < bBase + k * 32 * 4, s"unexpected DMA read $address")
        val first = ((address - bBase) / 4).toInt
        packet((0 until 16).map(i => weight((first + i) / 32, (first + i) % 32)))
      }
    }
    private def checkOperands(): Unit = {
      val s = d.io.matrix.step.bits
      val logicalK = (if (window) 0 else (groups - 1) * 128) + groupSteps
      val depth = if (window) k else math.min(128, k - (groups - 1) * 128)
      s.context.expect(0.U)
      s.clear.expect((logicalK == 0).B)
      s.last.expect((groupSteps + 1 == depth).B)
      s.emit.expect((groupSteps + 1 == depth).B)
      s.finish.expect((groupSteps + 1 == depth).B)
      // Both B halves and all sixteen active rows exercise the original
      // synchronous operand banks. Inactive/reserved positions stay zero.
      for (i <- 0 until 16) {
        s.a(i).expect((weight(logicalK, i) >> 16).U)
        s.b(i).expect((activation(i, logicalK) >> 16).U)
        s.b(128 + i).expect((weight(logicalK, 16 + i) >> 16).U)
      }
      for (i <- Seq(16, 127, 144, 255)) s.b(i).expect(0.U)
    }
    def tick(denyAcquire: Boolean = false): Unit = {
      if (cycle % 1024 == 0) progress("cycle", scenario, cycle)
      assert(cycle < 30000, "bounded parent protocol simulation timed out")
      val m = d.io.matrix
      val s = m.seed.get
      d.io.burst.ready.poke(true.B)
      d.io.writeRequest.get.ready.poke(true.B)
      d.io.writeData.get.ready.poke(true.B)
      m.group.ready.poke(true.B)
      m.step.ready.poke((cycle % 7 != 3).B)
      s.begin.ready.poke(true.B); s.beat.ready.poke((cycle % 5 != 2).B)
      d.io.burstResponse.valid.poke(read.exists(_.due <= cycle).B)
      read.foreach { r =>
        d.io.burstResponse.bits.data.poke(r.data.U); d.io.burstResponse.bits.tag.poke(r.tag.U)
        d.io.burstResponse.bits.last.poke(true.B); d.io.burstResponse.bits.error.poke(false.B)
        if (r.due > cycle) dmaHeldCycles += 1
      }
      d.io.writeResponse.get.valid.poke(write.exists(w => w.received == w.beats && w.due <= cycle).B)
      write.foreach { w =>
        d.io.writeResponse.get.bits.tag.poke(w.tag.U)
        d.io.writeResponse.get.bits.data.poke(0.U); d.io.writeResponse.get.bits.error.poke(false.B)
        if (!prefix(w.address) && w.received == w.beats && w.due > cycle) outputAckHeldCycles += 1
      }
      s.ack.valid.poke(seed.exists(x => x.received == 256 && x.due <= cycle).B)
      seed.foreach { x =>
        s.ack.bits.groupTag.poke(x.tag.U); s.ack.bits.groupSequence.poke(x.sequence.U)
        s.ack.bits.sourceGeneration.poke(x.generation.U); s.ack.bits.context.poke(x.context.U)
        s.ack.bits.error.poke(false.B)
        if (x.received == 256 && x.due > cycle) seedAckHeldCycles += 1
      }
      if (resultPending && !resultLoaded) {
        for (row <- 0 until 16; col <- 0 until 256)
          m.result.bits.value(row)(col).poke(token(matrixSequence, row, col).U)
        m.result.bits.context.poke(0.U); m.result.bits.last.poke(true.B)
        m.result.bits.error.poke(false.B); resultLoaded = true
      }
      m.result.valid.poke((resultPending && resultDue <= cycle).B)
      m.done.valid.poke((matrixActive && doneDue <= cycle).B)
      m.done.bits.tag.poke(matrixTag.U); m.done.bits.error.poke(false.B)
      if (matrixActive && doneDue != Int.MaxValue && doneDue > cycle) matrixDoneHeldCycles += 1
      d.io.physicalSteps.poke(physical.U)
      if (denyAcquire) {
        val raw = d.io.rawKv.get
        raw.acquire.valid.expect(true.B); raw.acquire.ready.expect(false.B)
        raw.leased.expect(false.B)
      }
      d.io.resetRequired.expect(false.B)
      m.abort.expect(false.B)
      // Sample every handshake before taking the edge. Responses cannot be
      // invented or retired merely because valid was asserted.
      val readFire = yes(d.io.burst.valid) && yes(d.io.burst.ready)
      val responseFire = yes(d.io.burstResponse.valid) && yes(d.io.burstResponse.ready)
      val writeFire = yes(d.io.writeRequest.get.valid) && yes(d.io.writeRequest.get.ready)
      val dataFire = yes(d.io.writeData.get.valid) && yes(d.io.writeData.get.ready)
      val ackFire = yes(d.io.writeResponse.get.valid) && yes(d.io.writeResponse.get.ready)
      val groupFire = yes(m.group.valid) && yes(m.group.ready)
      val stepFire = yes(m.step.valid) && yes(m.step.ready)
      val resultFire = yes(m.result.valid) && yes(m.result.ready)
      val doneFire = yes(m.done.valid) && yes(m.done.ready)
      val seedBeginFire = yes(s.begin.valid) && yes(s.begin.ready)
      val seedBeatFire = yes(s.beat.valid) && yes(s.beat.ready)
      val seedAckFire = yes(s.ack.valid) && yes(s.ack.ready)
      if (responseFire) { assert(read.nonEmpty); readsReturned += 1; read = None }
      if (readFire) {
        assert(read.isEmpty, "second DMA descriptor before first retirement")
        d.io.burst.bits.beats.expect(1.U)
        val address = number(d.io.burst.bits.address)
        assert((address & 63) == 0)
        read = Some(Read(address, number(d.io.burst.bits.tag), readData(address), cycle + 3))
        readsAccepted += 1
      }
      if (ackFire) {
        val w = write.get; assert(w.received == w.beats)
        for (beat <- 0 until w.beats) {
          val address = w.address + 64 * beat
          assert(stored.contains(address) && !acknowledged.contains(address))
          acknowledged += address
        }
        if (prefix(w.address)) prefixAckBytes += 64 * w.beats else outputAckBytes += 64 * w.beats
        writeAcks += 1; write = None
      }
      if (writeFire) {
        assert(write.isEmpty, "second write descriptor before ACK")
        val p = d.io.writeRequest.get.bits
        val address = number(p.address); val beats = number(p.beats).toInt
        assert((address & 63) == 0 && beats >= 1 && beats <= 16)
        assert((address / 1024) == ((address + 64 * beats - 1) / 1024))
        assert(prefix(address) || (address >= dstBase && address + 64 * beats <= dstBase + 2048))
        if (prefix(address)) assert(beats == 1)
        write = Some(Write(address, number(p.tag), beats)); writeCommands += 1
      }
      if (dataFire) {
        val w = write.get; assert(w.received < w.beats)
        d.io.writeData.get.bits.last.expect((w.received + 1 == w.beats).B)
        val address = w.address + 64 * w.received
        assert(!stored.contains(address), s"unexpected duplicate write $address")
        if (!prefix(address)) {
          // Route the already accepted opaque result packet to logical
          // Y[m,n]. No dot product, rounding, or numeric reference is used.
          val sequence = lastAcceptedResultSequence.get
          val first = ((address - dstBase) / 4).toInt
          val expected = packet((0 until 16).map { lane =>
            val mRow = (first + lane) / 32
            val nCol = (first + lane) % 32
            token(sequence, nCol % 16, (nCol / 16) * 128 + mRow)
          })
          d.io.writeData.get.bits.data.expect(expected.U)
        }
        stored(address) = number(d.io.writeData.get.bits.data)
        if (prefix(address)) prefixWriteBytes += 64 else outputWriteBytes += 64
        w.received += 1
        if (w.received == w.beats) w.due = cycle + 5
      }
      if (groupFire) {
        assert(!matrixActive && !resultPending && seed.isEmpty)
        m.group.bits.opcode.expect(0x20.U); m.group.bits.sliceMask.expect(255.U)
        m.group.bits.transposedDense.get.expect(true.B)
        matrixTag = number(m.group.bits.tag); matrixSequence = number(m.group.bits.groupSequence.get)
        assert(matrixSequence != 0)
        matrixActive = true; groupSteps = 0; doneDue = Int.MaxValue; groups += 1
      }
      if (stepFire) {
        assert(matrixActive && seed.isEmpty)
        checkOperands(); groupSteps += 1; steps += 1; physical += 1
        if (yes(m.step.bits.last)) {
          assert(!resultPending); resultPending = true; resultLoaded = false; resultDue = cycle + 3
        }
      }
      if (resultFire) {
        assert(resultPending); results += 1; resultPending = false; resultLoaded = false
        lastAcceptedResultSequence = Some(matrixSequence)
        doneDue = cycle + 5
      }
      if (doneFire) {
        assert(matrixActive && !resultPending && results == groups && seed.isEmpty)
        matrixActive = false; doneDue = Int.MaxValue; matrixDones += 1
      }
      if (seedBeginFire) {
        assert(matrixActive && seed.isEmpty && groupSteps == 0)
        s.begin.bits.groupTag.expect(matrixTag.U); s.begin.bits.groupSequence.expect(matrixSequence.U)
        s.begin.bits.sourceGeneration.expect(7.U); s.begin.bits.context.expect(0.U)
        s.begin.bits.sliceMask.expect(255.U)
        seed = Some(Seed(matrixTag, matrixSequence, 7, 0)); seedBegins += 1
      }
      if (seedBeatFire) {
        val x = seed.get
        s.beat.bits.groupTag.expect(x.tag.U); s.beat.bits.groupSequence.expect(x.sequence.U)
        s.beat.bits.sourceGeneration.expect(x.generation.U); s.beat.bits.context.expect(x.context.U)
        s.beat.bits.index.expect(x.received.U); s.beat.bits.last.expect((x.received == 255).B)
        s.beat.bits.error.expect(false.B)
        val index = x.received
        val memoryIndex = (((index >> 1) & 15) << 4) + ((index >> 5) << 1) + (index & 1)
        s.beat.bits.data.expect(stored(prefixBase + 64 * memoryIndex).U)
        x.received += 1; seedBeats += 1
        if (x.received == 256) x.due = cycle + 7
      }
      if (seedAckFire) {
        assert(seed.exists(_.received == 256)); seed = None; seedAcks += 1
      }
      d.clock.step(); cycle += 1
      // Do not leave a consumed valid high between service cycles. A parent
      // reaching idle must not mistake a simulator's stale offer for a reply.
      if (responseFire) d.io.burstResponse.valid.poke(false.B)
      if (ackFire) d.io.writeResponse.get.valid.poke(false.B)
      if (resultFire) m.result.valid.poke(false.B)
      if (doneFire) m.done.valid.poke(false.B)
      if (seedAckFire) s.ack.valid.poke(false.B)
    }
    def until(condition: => Boolean, denyAcquire: Boolean = false): Unit = {
      var waited = 0
      while (!condition) { assert(waited < 25000, "parent completion timeout"); tick(denyAcquire); waited += 1 }
    }
    def retired(): Unit = {
      assert(read.isEmpty && write.isEmpty && seed.isEmpty && !matrixActive && !resultPending)
      assert(readsAccepted == readsReturned && writeCommands == writeAcks)
      assert(groups == results && groups == matrixDones && seedBegins == seedAcks)
      assert(prefixWriteBytes == prefixAckBytes && outputWriteBytes == outputAckBytes)
      assert(acknowledged.size == stored.size)
      d.io.burst.valid.expect(false.B); d.io.writeRequest.get.valid.expect(false.B)
      d.io.writeData.get.valid.expect(false.B); d.io.matrix.group.valid.expect(false.B)
      d.io.matrix.step.valid.expect(false.B); d.io.matrix.seed.get.begin.valid.expect(false.B)
      d.io.matrix.seed.get.beat.valid.expect(false.B)
      d.io.burstResponse.valid.expect(false.B); d.io.writeResponse.get.valid.expect(false.B)
      d.io.matrix.result.valid.expect(false.B); d.io.matrix.done.valid.expect(false.B)
      d.io.matrix.seed.get.ack.valid.expect(false.B)
    }
  }

  private def offerRaw(d: TransposedDenseDownOwner): Unit = {
    val r = d.io.rawKv.get
    r.acquire.bits.poke(ownerId.U); r.acquire.valid.poke(true.B)
  }
  private def acquireRaw(d: TransposedDenseDownOwner): Unit = {
    val r = d.io.rawKv.get
    offerRaw(d); r.acquire.ready.expect(true.B); d.clock.step()
    r.acquire.valid.poke(false.B); r.leased.expect(true.B); r.drained.expect(true.B)
  }
  private def releaseRaw(d: TransposedDenseDownOwner): Unit = {
    val r = d.io.rawKv.get
    r.release.bits.poke(ownerId.U); r.release.valid.poke(true.B)
    r.release.ready.expect(true.B); d.clock.step(); r.release.valid.poke(false.B)
    r.leased.expect(false.B); r.drained.expect(true.B)
  }
  private def quiescent(d: TransposedDenseDownOwner, service: Services): Unit = {
    service.retired()
    d.io.done.valid.expect(false.B); d.io.window.get.result.valid.expect(false.B)
    d.io.drain.get.result.valid.expect(false.B); d.io.window.get.busy.expect(false.B)
    d.io.drain.get.busy.expect(false.B); d.io.window.get.leaseValid.expect(false.B)
    d.io.tiles.get.response.valid.expect(false.B); d.io.tiles.get.drained.expect(true.B)
    d.io.tiles.get.leased.expect(false.B); d.io.rawKv.foreach { r =>
      r.response.valid.expect(false.B); r.drained.expect(true.B); r.leased.expect(false.B)
      r.resetRequired.expect(false.B)
    }
    d.io.resetRequired.expect(false.B); d.io.job.ready.expect(true.B)
  }
  private def ordinary(d: TransposedDenseDownOwner, k: Int, tag: Int, raw: Boolean): Services = {
    workspace(d); job(d.io.job.bits, k, tag)
    d.io.job.valid.poke(true.B); d.io.job.ready.expect(true.B)
    d.clock.step(); d.io.job.valid.poke(false.B)
    val service = new Services(d, k, window = false)
    if (raw) offerRaw(d)
    service.until(yes(d.io.done.valid), denyAcquire = raw)
    d.io.done.bits.tag.expect(tag.U); d.io.done.bits.status.expect(0.U)
    d.io.done.bits.writeBytes.expect(2048.U); d.io.done.bits.usefulMacs.expect((16 * 32 * k).U)
    assert(service.outputWriteBytes == 2048 && service.outputAckBytes == 2048)
    assert(service.steps == k && service.groups == (k + 127) / 128)
    assert(service.dmaHeldCycles > 0 && service.outputAckHeldCycles > 0 && service.matrixDoneHeldCycles > 0)
    if (k > 128) {
      assert(service.prefixWriteBytes == 16384 && service.prefixAckBytes == 16384)
      assert(service.prefixReads == 256 && service.seedBegins == 1 && service.seedBeats == 256 && service.seedAcks == 1)
      assert(service.seedAckHeldCycles >= 6)
    } else assert(service.prefixWriteBytes == 0 && service.seedBegins == 0)
    service.retired()
    // The held owner completion and its accepting edge still forbid a loan.
    for (_ <- 0 until 3) {
      d.io.done.valid.expect(true.B)
      if (raw) d.io.rawKv.get.acquire.ready.expect(false.B)
      d.clock.step()
    }
    d.io.done.ready.poke(true.B)
    if (raw) d.io.rawKv.get.acquire.ready.expect(false.B)
    d.clock.step(); d.io.done.ready.poke(false.B)
    if (raw) {
      d.io.rawKv.get.acquire.ready.expect(true.B); d.clock.step()
      d.io.rawKv.get.acquire.valid.poke(false.B)
      d.io.rawKv.get.leased.expect(true.B)
      releaseRaw(d)
    }
    quiescent(d, service)
    service
  }

  private def successfulWindow(d: TransposedDenseDownOwner): Unit = {
    workspace(d)
    val w = d.io.window.get; val t = d.io.tiles.get; val r = d.io.rawKv.get
    job(w.request.bits.job, 32, 202)
    w.request.bits.identity.poke(9.U); w.request.bits.ng.poke(0.U)
    w.request.bits.cols.poke(32.U); w.request.bits.slot.poke(0.U)
    w.request.bits.reuseA.poke(false.B); zero(w.request.bits.kWindow.get)
    w.request.valid.poke(true.B); w.request.ready.expect(true.B)
    d.clock.step(); w.request.valid.poke(false.B)
    offerRaw(d)
    val service = new Services(d, 32, window = true)
    service.until(yes(w.result.valid), denyAcquire = true)
    w.result.bits.status.expect(0.U); w.result.bits.committed.expect(true.B)
    w.result.bits.tag.expect(202.U); w.result.bits.identity.expect(9.U)
    w.result.bits.producedBeats.expect(32.U); w.result.bits.ddrWriteBytes.expect(0.U)
    assert(service.writeCommands == 0 && service.steps == 32 && service.groups == 1)
    service.retired(); w.leaseValid.expect(true.B)
    for (_ <- 0 until 3) { r.acquire.ready.expect(false.B); w.result.valid.expect(true.B); d.clock.step() }
    w.result.ready.poke(true.B); r.acquire.ready.expect(false.B)
    d.clock.step(); w.result.ready.poke(false.B)
    // Result retirement alone leaves both a live tile and retained A lease.
    r.acquire.ready.expect(false.B); t.leased.expect(true.B); w.leaseValid.expect(true.B)
    r.acquire.valid.poke(false.B)
    t.state(0).produced.expect(32.U); t.state(0).consumed.expect(0.U)
    t.state(0).sealedTile.expect(true.B)
    for (index <- 0 until 32) {
      t.read.bits.slot.poke(0.U); t.read.bits.identity.poke(9.U)
      t.read.bits.ng.poke(0.U); t.read.bits.index.poke(index.U)
      t.read.valid.poke(true.B); t.read.ready.expect(true.B)
      d.clock.step(); t.read.valid.poke(false.B)
      var wait = 0
      while (!yes(t.response.valid)) { assert(wait < 5); d.clock.step(); wait += 1 }
      t.response.bits.error.expect(false.B)
      t.response.bits.key.slot.expect(0.U); t.response.bits.key.identity.expect(9.U)
      t.response.bits.key.ng.expect(0.U); t.response.bits.key.index.expect(index.U)
      // The previously accepted Matrix packet is only checked for bit routing.
      // Group sequence is three: two ordinary groups preceded this window.
      for (lane <- 0 until 16)
        t.response.bits.value(lane).expect(token(3, index & 15, (index >> 4) * 128 + lane).U)
      if (index == 0) {
        for (_ <- 0 until 3) { t.response.valid.expect(true.B); d.clock.step() }
        t.state(0).consumed.expect(0.U)
      }
      t.response.ready.poke(true.B); d.clock.step(); t.response.ready.poke(false.B)
    }
    t.state(0).consumed.expect(32.U); t.drained.expect(true.B)
    t.control.bits.op.poke(2.U); t.control.bits.slot.poke(0.U)
    t.control.bits.identity.poke(9.U); t.control.bits.ng.poke(0.U)
    t.control.bits.rows.poke(16.U); t.control.bits.cols.poke(32.U)
    t.control.bits.matrixProducerOrder.get.poke(true.B)
    t.control.valid.poke(true.B); t.control.ready.expect(true.B)
    d.clock.step(); t.control.valid.poke(false.B)
    t.leased.expect(false.B); t.drained.expect(true.B)
    // Isolate the retained-A blocker after every tile byte has been consumed.
    offerRaw(d); w.leaseValid.expect(true.B)
    r.acquire.ready.expect(false.B); d.clock.step(); r.acquire.ready.expect(false.B)
    w.invalidateLease.poke(true.B); r.acquire.ready.expect(false.B)
    d.clock.step(); w.invalidateLease.poke(false.B)
    w.leaseValid.expect(false.B); r.acquire.ready.expect(true.B)
    d.clock.step(); r.acquire.valid.poke(false.B); r.leased.expect(true.B)
    releaseRaw(d); quiescent(d, service)
  }

  private def key(k: RawKvKey, tag: Int, line: Int, write: Boolean): Unit = {
    k.owner.poke(ownerId.U); k.tag.poke(tag.U); k.line.poke(line.U); k.write.poke(write.B)
  }
  private def rawRequest(d: TransposedDenseDownOwner, tag: Int, line: Int, write: Boolean, data: BigInt): Unit = {
    val r = d.io.rawKv.get
    key(r.request.bits.key, tag, line, write); r.request.bits.data.poke(data.U)
    r.request.valid.poke(true.B); r.request.ready.expect(true.B)
    d.clock.step(); r.request.valid.poke(false.B); r.drained.expect(false.B)
    r.response.valid.expect(false.B)
    d.clock.step(); r.response.valid.expect(true.B)
    r.response.bits.key.owner.expect(ownerId.U); r.response.bits.key.tag.expect(tag.U)
    r.response.bits.key.line.expect(line.U); r.response.bits.key.write.expect(write.B)
  }
  private def rawAck(d: TransposedDenseDownOwner, tag: Int, line: Int, write: Boolean): Unit = {
    val r = d.io.rawKv.get
    key(r.ack.bits, tag, line, write); r.ack.valid.poke(true.B)
    r.ack.ready.expect(true.B); r.release.ready.expect(false.B)
    d.clock.step(); r.ack.valid.poke(false.B)
    r.response.valid.expect(false.B); r.drained.expect(true.B)
  }
  private def rawFaultRetirement(d: TransposedDenseDownOwner): Unit = {
    val r = d.io.rawKv.get
    val data = (BigInt(1) << 511) | BigInt("0123456789abcdef0123456789abcdef", 16)
    // Competing idle offers must give the raw loan priority. Keep the same
    // valid Dense offer present until this clean raw lease is released.
    job(d.io.job.bits, 32, 303); d.io.job.valid.poke(true.B)
    offerRaw(d); r.acquire.ready.expect(true.B); d.io.job.ready.expect(false.B)
    d.clock.step(); r.acquire.valid.poke(false.B); r.leased.expect(true.B)
    d.io.job.ready.expect(false.B); d.io.window.get.request.ready.expect(false.B)
    d.io.drain.get.request.ready.expect(false.B); d.io.tiles.get.read.ready.expect(false.B)
    rawRequest(d, 1, 19, write = true, data = data)
    r.response.bits.data.expect(0.U)
    rawAck(d, 1, 19, write = true)
    rawRequest(d, 2, 19, write = false, data = 0)
    r.release.bits.poke(ownerId.U); r.release.valid.poke(true.B)
    for (_ <- 0 until 4) {
      r.release.ready.expect(false.B); r.response.valid.expect(true.B)
      r.response.bits.data.expect(data.U); r.drained.expect(false.B)
      d.clock.step()
    }
    // A foreign ACK neither clears the response nor licenses early release.
    key(r.ack.bits, 99, 19, write = false); r.ack.valid.poke(true.B)
    r.ack.ready.expect(false.B); r.release.ready.expect(false.B)
    d.clock.step(); r.ack.valid.poke(false.B)
    r.response.bits.data.expect(data.U)
    rawAck(d, 2, 19, write = false)
    r.release.ready.expect(true.B); d.io.job.valid.expect(true.B); d.io.job.ready.expect(false.B)
    d.clock.step(); r.release.valid.poke(false.B)
    r.leased.expect(false.B); r.resetRequired.expect(false.B)
    d.io.job.ready.expect(true.B)
    // The offer was blocked through the release edge. Withdraw it before
    // another edge so this priority probe cannot launch unserviced work.
    d.io.job.valid.poke(false.B); d.io.burst.valid.expect(false.B)
    // Final phase: a held accepted fill survives a backend fault and a
    // foreign parent reply. Neither input is falsely counted as accepted DMA.
    acquireRaw(d); rawRequest(d, 3, 23, write = true, data = data ^ 0x55)
    val heldKey = (number(r.response.bits.key.owner), number(r.response.bits.key.tag),
      number(r.response.bits.key.line), yes(r.response.bits.key.write))
    d.io.burstResponse.valid.poke(true.B); d.io.burstResponse.bits.tag.poke(0xdead.U)
    d.io.burstResponse.bits.data.poke(0.U); d.io.burstResponse.bits.last.poke(true.B)
    d.io.burstResponse.bits.error.poke(true.B)
    d.io.burstResponse.ready.expect(false.B); r.resetRequired.expect(true.B)
    d.clock.step(); d.io.burstResponse.valid.poke(false.B)
    r.resetRequired.expect(true.B); r.response.valid.expect(true.B)
    d.io.drain.get.abort.poke(true.B); d.clock.step(); d.io.drain.get.abort.poke(false.B)
    r.release.bits.poke(ownerId.U); r.release.valid.poke(true.B)
    for (_ <- 0 until 3) {
      r.response.valid.expect(true.B); r.response.bits.data.expect(0.U)
      r.response.bits.key.owner.expect(heldKey._1.U); r.response.bits.key.tag.expect(heldKey._2.U)
      r.response.bits.key.line.expect(heldKey._3.U); r.response.bits.key.write.expect(heldKey._4.B)
      r.resetRequired.expect(true.B); r.release.ready.expect(false.B)
      d.io.resetRequired.expect(true.B); d.clock.step()
    }
    rawAck(d, 3, 23, write = true)
    r.release.ready.expect(true.B); d.clock.step(); r.release.valid.poke(false.B)
    r.leased.expect(false.B); r.drained.expect(true.B); r.response.valid.expect(false.B)
    // A raw-only reset cannot repair the real parent's poisoned backend.
    r.softReset.poke(true.B); d.clock.step(); r.softReset.poke(false.B)
    offerRaw(d); r.acquire.ready.expect(false.B); r.resetRequired.expect(true.B)
    d.io.resetRequired.expect(true.B); d.io.job.ready.expect(false.B)
    d.io.window.get.request.ready.expect(false.B); d.io.drain.get.request.ready.expect(false.B)
    d.clock.step(); r.acquire.valid.poke(false.B)
    // Deliberately end poisoned and fully debt-retired. No cold reset repairs
    // this scenario, and no reset occurs between any raw-enabled scenarios.
  }

  behavior of "the actual composed TransposedDenseDownOwner raw KV loan"
  it should "complete ordinary Dense with the raw feature absent" in {
    progress("case_begin", "default_off_dense")
    test(ParentKvHarness.owner(raw = false)).withAnnotations(Seq(VerilatorBackendAnnotation, VerilatorCFlags(Seq("-O0")))) { d =>
      progress("sim_ready", "default_off_dense")
      defaults(d); d.clock.setTimeout(100000)
      assert(d.io.rawKv.isEmpty)
      ordinary(d, k = 32, tag = 101, raw = false)
      progress("scenario_done", "default_off_dense")
      println("PARENT_SCENARIO_PASS default_off_dense")
    }
  }
  it should "retire real parent work before loans and preserve poisoned raw debt" in {
    progress("case_begin", "enabled_dense_drain")
    test(ParentKvHarness.owner(raw = true)).withAnnotations(Seq(VerilatorBackendAnnotation, VerilatorCFlags(Seq("-O0")))) { d =>
      progress("sim_ready", "enabled_dense_drain")
      defaults(d); d.clock.setTimeout(100000)
      ordinary(d, k = 256, tag = 201, raw = true)
      progress("scenario_done", "enabled_dense_drain")
      println("PARENT_SCENARIO_PASS enabled_dense_drain")
      progress("scenario_begin", "retained_a_window")
      successfulWindow(d)
      progress("scenario_done", "retained_a_window")
      println("PARENT_SCENARIO_PASS retained_a_window")
      progress("scenario_begin", "raw_fault_retirement")
      rawFaultRetirement(d)
      progress("scenario_done", "raw_fault_retirement")
      println("PARENT_SCENARIO_PASS raw_fault_retirement")
    }
  }
}
