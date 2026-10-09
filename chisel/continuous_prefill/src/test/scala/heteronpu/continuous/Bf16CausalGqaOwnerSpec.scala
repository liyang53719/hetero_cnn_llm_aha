// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.collection.mutable

/** Actual production Scalar and append owner, with an external Matrix endpoint.
  * The test's Matrix endpoint uses sequential software Math.fma on OBSERVED
  * inputs. This is owner/protocol/shared-Scalar coverage, NOT real Matrix RTL
  * arithmetic, retained-iDMA, checkpoint accuracy, or a whole-block M128 gate.
  */
class Bf16CausalGqaHarness(maxCacheTokens: Int = 256) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new Bf16CausalGqaJob))
    val done = Decoupled(new Bf16CausalGqaResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val matrix = new MatrixStreamPort
    val matrixA = Output(UInt(256.W))
    val matrixB = Output(UInt(4096.W))
    val scalarHold = Input(Bool())
    val scalarFault = Input(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestFire = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultFire = Output(Bool())
    val resetRequired = Output(Bool())
    val appendJob = Flipped(Decoupled(new Bf16KvAppendJob))
    val appendDone = Decoupled(new Bf16KvAppendResult)
    val appendMemory = Decoupled(new MemoryRequest)
    val appendResponse = Flipped(Decoupled(new MemoryResponse))
  })
  val owner = Module(new Bf16CausalGqaOwner(maxCacheTokens = maxCacheTokens))
  val scalar = Module(new BlockScalarFloat)
  val append = Module(new Bf16KvAppendOwner)
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  io.matrix <> owner.io.matrix
  io.matrixA := owner.io.matrix.step.bits.a.asUInt
  io.matrixB := owner.io.matrix.step.bits.b.asUInt
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error || io.scalarFault
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := owner.io.scalar.request.bits
  io.scalarRequestFire := owner.io.scalar.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultFire := owner.io.scalar.result.fire
  io.resetRequired := owner.io.resetRequired
  append.io.job <> io.appendJob; io.appendDone <> append.io.done
  io.appendMemory <> append.io.memory; append.io.response <> io.appendResponse
}

class Bf16CausalGqaOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  // All allocations have the same low 32 address bits. Truncating an address
  // would alias them, so the physical image always uses the entire address.
  private val qBase = BigInt("410000000", 16)
  private val kBase = BigInt("510000000", 16)
  private val vBase = BigInt("610000000", 16)
  private val cacheBase = BigInt("710000000", 16)
  private val outBase = BigInt("810000000", 16)
  private val fullMask = (BigInt(1) << 64) - 1
  private val jobTag = BigInt("35162807", 16)
  private case class Receipt(length: Int, generation: Int)
  private case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  private case class Inputs(q: Vector[Int], k: Vector[Int], v: Vector[Int], tokens: Int,
                            queryStart: Int, capacity: Int) {
    val length: Int = k.size / 512
    def query(t: Int, h: Int, d: Int): Int = q((t * 8 + h) * 256 + d)
    def key(t: Int, h: Int, d: Int): Int = k((t * 2 + h) * 256 + d)
    def value(t: Int, h: Int, d: Int): Int = v((t * 2 + h) * 256 + d)
  }
  private case class Reference(output: Map[BigInt, BigInt], probability: Array[Array[Array[Int]]])
  private def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  private def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  private def bf(x: Float): Int = {
    val b = bits(x).toLong
    (((b + 0x7fffL + ((b >>> 16) & 1)) >>> 16) & 65535).toInt
  }
  private def pack(xs: Seq[Int]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (word, (value, index)) => word | (BigInt(value & 65535) << (16 * index))
  }
  private def beats(base: BigInt, xs: Seq[Int]): Map[BigInt, BigInt] =
    xs.grouped(32).zipWithIndex.map { case (lanes, i) => (base + i * 64) -> pack(lanes) }.toMap
  private def expRecipe(x: Float): Float = {
    require(math.abs(x) < 80f, "unsupported exp domain must never enter the reference polynomial")
    val scaled = (math.abs(x) * (1.0 / math.log(2.0)).toFloat).toFloat
    val exponent = scaled.toInt
    val fraction = (scaled - exponent.toFloat).toFloat
    val coefficients = (0 to 7).map(i => (math.pow(-math.log(2.0), i) /
      (if (i == 0) 1.0 else (1 to i).map(_.toDouble).product)).toFloat)
    var result = coefficients(7)
    for (i <- 6 to 0 by -1) result = ((result * fraction).toFloat + coefficients(i)).toFloat
    (result * java.lang.Float.intBitsToFloat((127 - exponent) << 23)).toFloat
  }
  private def vector(tokens: Int, heads: Int, salt: Int): Vector[Int] =
    Vector.tabulate(tokens * heads * 256) { i =>
      val token = i / (heads * 256); val head = (i / 256) % heads; val dimension = i % 256
      bf((((dimension * 13 + token * 19 + head * 7 + salt) % 31 - 15) / 64f + head / 32f).toFloat)
    }
  private def reference(in: Inputs): Reference = {
    val p = Array.ofDim[Int](in.tokens, 8, in.length)
    val output = Array.ofDim[Int](in.tokens * 8 * 256)
    for (t <- 0 until in.tokens; h <- 0 until 8) {
      val scores = Array.tabulate(in.length) { key =>
        var dot = 0f
        for (d <- 0 until 256) dot = java.lang.Math.fma(fp(in.query(t, h, d)), fp(in.key(key, h / 4, d)), dot)
        fp(bf((fp(bf(dot)) * .0625f).toFloat))
      }
      val allowed = in.queryStart + t + 1
      val maximum = scores.take(allowed).max
      val exponents = Array.fill(in.length)(0f)
      var denominator = 0f
      for (key <- 0 until allowed) {
        exponents(key) = expRecipe((scores(key) - maximum).toFloat)
        denominator = (denominator + exponents(key)).toFloat
      }
      for (key <- 0 until allowed) p(t)(h)(key) = bf((exponents(key) / denominator).toFloat)
      for (d <- 0 until 256) {
        var sum = 0f
        // Masked zero-probability keys still occupy their increasing-key FMA.
        for (key <- 0 until in.length) sum = java.lang.Math.fma(fp(p(t)(h)(key)), fp(in.value(key, h / 4, d)), sum)
        output((t * 8 + h) * 256 + d) = bf(sum)
      }
    }
    Reference(beats(outBase, output.toSeq), p)
  }
  private def request(port: MemoryRequest): Request = Request(port.write.peek().litToBoolean,
    port.address.peek().litValue, port.data.peek().litValue, port.mask.peek().litValue, port.tag.peek().litValue)
  private def completion(d: Bf16CausalGqaHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue,
    d.io.done.bits.attentionStatus.peek().litValue)
  private def init(d: Bf16CausalGqaHarness): Unit = {
    d.clock.setTimeout(500000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.matrix.group.ready.poke(false.B); d.io.matrix.step.ready.poke(false.B)
    d.io.matrix.result.valid.poke(false.B); d.io.matrix.result.bits.context.poke(0.U)
    d.io.matrix.result.bits.last.poke(true.B); d.io.matrix.result.bits.error.poke(false.B)
    for (r <- 0 until 16; c <- 0 until 256) d.io.matrix.result.bits.value(r)(c).poke(0.U)
    d.io.matrix.done.valid.poke(false.B); d.io.matrix.done.bits.tag.poke(0.U); d.io.matrix.done.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.scalarFault.poke(false.B)
    d.io.appendJob.valid.poke(false.B); d.io.appendDone.ready.poke(false.B)
    d.io.appendMemory.ready.poke(false.B); d.io.appendResponse.valid.poke(false.B)
    d.io.appendResponse.bits.data.poke(0.U); d.io.appendResponse.bits.tag.poke(0.U); d.io.appendResponse.bits.error.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
    d.io.job.ready.expect(true.B); d.io.resetRequired.expect(false.B)
  }
  private def setJob(d: Bf16CausalGqaHarness, tokens: Int, start: Int, length: Int, capacity: Int): Unit = {
    val j = d.io.job.bits
    j.tokens.poke(tokens.U); j.queryHeads.poke(8.U); j.kvHeads.poke(2.U); j.headDim.poke(256.U)
    j.queryInput.poke(qBase.U); j.cacheBase.poke(cacheBase.U); j.output.poke(outBase.U)
    j.queryStart.poke(start.U); j.cacheLength.poke(length.U); j.capacityTokens.poke(capacity.U); j.tag.poke(jobTag.U)
  }

  /** Persistent physical DDR image. A write takes effect at request acceptance,
    * including an erroring final ACK. Only accepted append receipts carry length.
    * No score/probability or previously published cache is loaded from a golden.
    */
  private class Memory(val capacity: Int) {
    val image = mutable.Map.empty[BigInt, BigInt]
    // Unused capacity is poisoned, so reading padding is neither numerically
    // harmless nor silently accepted by the active-span address checks.
    for (i <- -1 to capacity * 32) image(cacheBase + i * 64) = pack(Seq.fill(32)(0x7fc1))
    def append(d: Bf16CausalGqaHarness, previous: Receipt, keys: Vector[Int], values: Vector[Int]): Receipt = {
      val tokens = keys.size / 512
      require(tokens > 0 && values.size == keys.size)
      image ++= beats(kBase, keys); image ++= beats(vBase, values)
      val before = image.toMap
      val j = d.io.appendJob.bits
      j.tokens.poke(tokens.U); j.kvHeads.poke(2.U); j.headDim.poke(256.U)
      j.keyInput.poke(kBase.U); j.valueInput.poke(vBase.U); j.cacheBase.poke(cacheBase.U)
      j.capacityTokens.poke(capacity.U); j.appendStart.poke(previous.length.U)
      j.currentLength.poke(previous.length.U); j.expectedLength.poke(previous.length.U)
      j.currentGeneration.poke(previous.generation.U); j.expectedGeneration.poke(previous.generation.U)
      j.cold.poke((previous.length == 0).B); j.tag.poke((0x1000 + previous.generation).U)
      d.io.appendJob.ready.expect(true.B); d.io.appendJob.valid.poke(true.B); d.clock.step(); d.io.appendJob.valid.poke(false.B)
      val written = mutable.Set.empty[BigInt]
      var sequence = 0
      while (!d.io.appendDone.valid.peek().litToBoolean && sequence < tokens * 64 + 1) {
        d.io.appendMemory.valid.expect(true.B)
        val r = request(d.io.appendMemory.bits)
        assert(r.tag == ((BigInt(0x1000 + previous.generation) << 32) | sequence))
        d.clock.step(1 + sequence % 3); assert(request(d.io.appendMemory.bits) == r)
        d.io.appendMemory.ready.poke(true.B); d.clock.step(); d.io.appendMemory.ready.poke(false.B)
        val plane = sequence / (tokens * 32); val index = (sequence / 2) % (tokens * 16)
        assert(r.write == (sequence % 2 == 1))
        if (r.write) {
          val expectedAddress = cacheBase + plane * capacity * 1024 + previous.length * 1024 + index * 64
          val input = (if (plane == 0) kBase else vBase) + index * 64
          assert(r.address == expectedAddress && r.mask == fullMask && r.data == image(input))
          assert(!written(r.address)); written += r.address; image(r.address) = r.data
        } else assert(r.address == (if (plane == 0) kBase else vBase) + index * 64 && r.mask == 0)
        d.clock.step(if (sequence == tokens * 64 - 1) 11 else 2)
        d.io.appendDone.valid.expect(false.B); d.io.appendDone.bits.proposalValid.expect(false.B)
        d.io.appendResponse.bits.data.poke((if (r.write) BigInt(0) else image(r.address)).U)
        d.io.appendResponse.bits.tag.poke(r.tag.U); d.io.appendResponse.bits.error.poke(false.B)
        d.io.appendResponse.valid.poke(true.B); d.io.appendResponse.ready.expect(true.B)
        d.clock.step(); d.io.appendResponse.valid.poke(false.B); sequence += 1
      }
      d.io.appendDone.valid.expect(true.B); d.io.appendDone.bits.status.expect(Status.Ok.U)
      d.io.appendDone.bits.proposalValid.expect(true.B); d.io.appendDone.bits.writeBytes.expect((tokens * 2048).U)
      val receipt = Receipt(d.io.appendDone.bits.proposedLength.peek().litValue.toInt,
        d.io.appendDone.bits.proposedGeneration.peek().litValue.toInt)
      assert(receipt == Receipt(previous.length + tokens, previous.generation + 1))
      for ((address, value) <- before if !written(address)) assert(image(address) == value, "append changed the retained prefix or another allocation")
      d.io.appendDone.ready.poke(true.B); d.clock.step(); d.io.appendDone.ready.poke(false.B)
      receipt
    }

    def run(d: Bf16CausalGqaHarness, in: Inputs, label: String, fault: String = "none",
            expectedStatus: Int = Status.Ok, expectedAttention: Int = 0): Unit = {
      require(in.capacity == capacity && in.queryStart + in.tokens == in.length)
      image ++= beats(qBase, in.q)
      val referenceResult = if (Set("nonfinite-q", "nonfinite-k", "nonfinite-v", "domain").contains(fault)) None else Some(reference(in))
      val original = image.toMap
      val readSet = beats(qBase, in.q).keySet ++
        (0 until in.length * 16).map(i => cacheBase + i * 64) ++
        (0 until in.length * 16).map(i => cacheBase + capacity * 1024 + i * 64)
      val physicalWrites = mutable.Set.empty[BigInt]
      var acknowledged = 0; var sequence = 0; var cycle = 0; var injected = false
      var abortObserved = false; var finalAckHeld = false
      var groupCount = 0; var doneCount = 0; var scalarCount = 0
      var qTile = 0; var head = 0; var kTile = 0; var expectPv = false
      var heldRequest: Option[Request] = None
      var heldGroup: Option[(BigInt, BigInt, BigInt)] = None
      var heldStep: Option[Seq[BigInt]] = None
      case class Pending(r: Request, due: Int, fail: Boolean, wrongTag: Boolean)
      var pending: Option[Pending] = None
      class MatrixWork(val opcode: Int, val tag: BigInt) {
        val rows = math.min(16, in.tokens - qTile)
        val columns = if (opcode == 0x23) 32 else 256
        val acc = Array.fill(rows, columns)(0f)
        var index = 0; var stage = "steps"; var due = 0; var aborted = false
        var resultError = false; var doneError = false; var wrongTag = false
      }
      var matrix: Option[MatrixWork] = None
      val scalarExpected = mutable.Queue.empty[BigInt]
      def scalarAnswer(op: Int, a: Float, b: Float): Float = op match {
        case ScalarOp.Add => (a + b).toFloat
        case ScalarOp.MulIeeeRne => (a * b).toFloat
        case ScalarOp.Div => (a / b).toFloat
        case ScalarOp.ExpNegative => expRecipe(a)
        case other => fail(s"unexpected scalar opcode $other; legacy multiplication is forbidden")
      }
      def stepSnapshot: Seq[BigInt] = Seq(d.io.matrixA.peek().litValue, d.io.matrixB.peek().litValue,
        d.io.matrix.step.bits.context.peek().litValue, d.io.matrix.step.bits.clear.peek().litValue,
        d.io.matrix.step.bits.last.peek().litValue, d.io.matrix.step.bits.finish.peek().litValue,
        d.io.matrix.step.bits.emit.peek().litValue)
      def tick(): Unit = {
        d.io.scalarHold.poke((cycle % 19 < 3).B)
        d.io.scalarFault.poke((fault == "scalar").B)
        d.io.memory.ready.poke((pending.isEmpty && cycle % 4 != 0).B)
        d.io.response.valid.poke(pending.exists(_.due <= cycle).B)
        pending.foreach { p =>
          d.io.response.bits.data.poke((if (p.r.write) BigInt(0) else image(p.r.address)).U)
          d.io.response.bits.tag.poke((p.r.tag ^ (if (p.wrongTag) BigInt(1) << 32 else BigInt(0))).U)
          d.io.response.bits.error.poke(p.fail.B)
        }
        if (d.io.matrix.abort.peek().litToBoolean) {
          abortObserved = true
          matrix.foreach { m => if (!m.aborted) { m.aborted = true; m.stage = "done"; m.due = cycle + 5; m.doneError = true } }
        }
        d.io.matrix.group.ready.poke((matrix.isEmpty && cycle % 5 != 0).B)
        d.io.matrix.step.ready.poke((matrix.exists(_.stage == "steps") && cycle % 7 != 0).B)
        d.io.matrix.result.valid.poke(matrix.exists(m => m.stage == "result" && m.due <= cycle).B)
        d.io.matrix.done.valid.poke(matrix.exists(m => m.stage == "done" && m.due <= cycle).B)
        matrix.foreach { m =>
          d.io.matrix.result.bits.error.poke(m.resultError.B)
          d.io.matrix.done.bits.tag.poke((m.tag ^ (if (m.wrongTag) BigInt(1) else BigInt(0))).U)
          d.io.matrix.done.bits.error.poke(m.doneError.B)
        }
        if (d.io.memory.valid.peek().litToBoolean) {
          val r = request(d.io.memory.bits)
          heldRequest.foreach(old => assert(old == r, "memory request changed under backpressure"))
          if (!d.io.memory.ready.peek().litToBoolean) heldRequest = Some(r)
          else {
            heldRequest = None
            assert(r.tag == ((jobTag << 32) | sequence), "memory tag/sequence lost the accepted job")
            assert((r.address & 63) == 0)
            val last = r.write && r.address == outBase + in.tokens * 4096 - 64
            val wrongTag = !injected && fault == "memory-tag" && !r.write
            val memoryFault = !injected && ((fault == "memory-read" && !r.write) || (fault == "final-ack" && last))
            injected ||= wrongTag || memoryFault
            if (r.write) {
              assert(matrix.isEmpty, "output store preceded Matrix terminal done")
              assert(r.mask == fullMask, "every output packet must use full64, never zero or a partial mask")
              assert(r.address >= outBase && r.address < outBase + in.tokens * 4096)
              assert(!physicalWrites(r.address), "duplicate output store")
              referenceResult.foreach(ref => assert(ref.output(r.address) == r.data, s"$label output differs at 0x${r.address.toString(16)}"))
              image(r.address) = r.data; physicalWrites += r.address
              if (last) finalAckHeld = true
            } else { assert(r.mask == 0 && readSet(r.address), s"read escaped active input/cache spans: $r") }
            val earlyDone = !injected && fault == "matrix-early-done" && !r.write && matrix.exists(_.opcode == 0x24)
            if (earlyDone) {
              // Matrix terminates abnormally while an accepted V DMA is still
              // in flight. The owner must drain that response before done.
              val m = matrix.get; m.stage = "done"; m.due = cycle + 1; m.doneError = true
              injected = true
            }
            pending = Some(Pending(r, cycle + (if (last || earlyDone) 23 else 2 + sequence % 3), memoryFault, wrongTag))
          }
        } else assert(heldRequest.isEmpty)
        if (d.io.response.valid.peek().litToBoolean && d.io.response.ready.peek().litToBoolean) {
          val p = pending.get
          if (p.r.write && !p.fail && !p.wrongTag) acknowledged += 64
          pending = None; sequence += 1
        }
        if (d.io.matrix.group.valid.peek().litToBoolean) {
          val g = d.io.matrix.group.bits
          val snapshot = (g.opcode.peek().litValue, g.sliceMask.peek().litValue, g.tag.peek().litValue)
          heldGroup.foreach(old => assert(old == snapshot, "Matrix group changed while stalled"))
          if (!d.io.matrix.group.ready.peek().litToBoolean) heldGroup = Some(snapshot)
          else {
            heldGroup = None; assert(matrix.isEmpty)
            assert(snapshot._1 == (if (expectPv) 0x24 else 0x23))
            assert(snapshot._2 == (if (expectPv) 255 else 1), "QK/PV physical slice masks differ")
            assert(snapshot._3 == ((jobTag + groupCount) & 0xffffffffL))
            matrix = Some(new MatrixWork(snapshot._1.toInt, snapshot._3)); groupCount += 1
          }
        }
        if (d.io.matrix.step.valid.peek().litToBoolean) {
          val snapshot = stepSnapshot
          heldStep.foreach(old => assert(old == snapshot, "Matrix step changed while stalled"))
          if (!d.io.matrix.step.ready.peek().litToBoolean) heldStep = Some(snapshot)
          else {
            heldStep = None
            val m = matrix.get; val pv = m.opcode == 0x24
            val terminal = m.index == (if (pv) in.length - 1 else 255)
            assert(snapshot(2) == 0 && snapshot(3) == (if (m.index == 0) 1 else 0))
            assert(snapshot.drop(4).forall(_ == (if (terminal) BigInt(1) else BigInt(0))), "last/finish/emit must coincide only at the final reduction step")
            val a = (0 until 16).map(r => ((snapshot(0) >> (16 * r)) & 65535).toInt)
            val b = (0 until m.columns).map(c => ((snapshot(1) >> (16 * c)) & 65535).toInt)
            for (r <- 0 until 16) {
              val expected = if (r >= m.rows) Some(0) else if (!pv) Some(in.query(qTile + r, head, m.index))
                else referenceResult.map(_.probability(qTile + r)(head)(m.index))
              expected.foreach(value => assert(a(r) == value, s"wrong ${if (pv) "probability" else "query"} lane row=$r head=$head step=${m.index}"))
            }
            for (c <- 0 until m.columns) {
              val expected = if (pv) in.value(m.index, head / 4, c)
                else if (kTile + c < in.length) in.key(kTile + c, head / 4, m.index) else 0
              assert(b(c) == expected, s"wrong ${if (pv) "value" else "key"} lane column=$c head=$head step=${m.index}")
            }
            for (r <- 0 until m.rows; c <- 0 until m.columns) m.acc(r)(c) = java.lang.Math.fma(fp(a(r)), fp(b(c)), m.acc(r)(c))
            m.index += 1
            if (terminal) {
              for (r <- 0 until m.rows; c <- 0 until m.columns) d.io.matrix.result.bits.value(r)(c).poke(bits(m.acc(r)(c)).U)
              m.resultError = !injected && fault == "matrix-result"
              if (!injected && fault == "matrix-nonfinite") { d.io.matrix.result.bits.value(0)(0).poke("h7fc00000".U); injected = true }
              injected ||= m.resultError
              m.stage = "result"; m.due = cycle + 3
            }
          }
        }
        if (d.io.matrix.result.valid.peek().litToBoolean && d.io.matrix.result.ready.peek().litToBoolean) {
          val m = matrix.get; m.stage = "done"; m.due = cycle + 11
          m.doneError = !injected && fault == "matrix-done"
          m.wrongTag = !injected && fault == "matrix-tag"
          injected ||= m.doneError || m.wrongTag
        }
        if (d.io.matrix.done.valid.peek().litToBoolean && d.io.matrix.done.ready.peek().litToBoolean) {
          val m = matrix.get
          if (m.opcode == 0x23) {
            if (kTile + 32 < in.length) kTile += 32 else expectPv = true
          } else {
            expectPv = false; kTile = 0; head += 1
            if (head == 8) { head = 0; qTile += 16 }
          }
          matrix = None; doneCount += 1
        }
        if (d.io.scalarRequestFire.peek().litToBoolean) {
          assert(matrix.isEmpty, "scalar consumed provisional Matrix results before terminal done")
          val s = d.io.scalarRequest
          val op = s.op.peek().litValue.toInt
          val a = java.lang.Float.intBitsToFloat(s.a.peek().litValue.toInt)
          val b = java.lang.Float.intBitsToFloat(s.b.peek().litValue.toInt)
          scalarExpected.enqueue(bits(scalarAnswer(op, a, b))); scalarCount += 1
        }
        if (d.io.scalarResultFire.peek().litToBoolean) {
          assert(scalarExpected.nonEmpty, "unrequested Scalar result")
          d.io.scalarResult.expect(scalarExpected.dequeue().U)
        }
        if (pending.exists(_.r.write) || (pending.nonEmpty && injected && fault == "matrix-early-done")) {
          d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        }
        d.clock.step(); cycle += 1
      }
      setJob(d, in.tokens, in.queryStart, in.length, capacity)
      d.io.job.ready.expect(true.B); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      // All subsequent traffic and done must use the accepted descriptor.
      d.io.job.bits.tokens.poke(0.U); d.io.job.bits.queryInput.poke(0.U)
      d.io.job.bits.cacheBase.poke(0.U); d.io.job.bits.output.poke(0.U)
      d.io.job.bits.capacityTokens.poke(0.U); d.io.job.bits.queryStart.poke("hffffffff".U)
      d.io.job.bits.cacheLength.poke(0.U); d.io.job.bits.tag.poke("hdeadbeef".U)
      while (!d.io.done.valid.peek().litToBoolean && cycle < 400000) tick()
      assert(d.io.done.valid.peek().litToBoolean, s"$label timed out at cycle $cycle")
      assert(pending.isEmpty && matrix.isEmpty && scalarExpected.isEmpty, "done exposed pending service work")
      d.io.done.bits.tag.expect(jobTag.U); d.io.done.bits.status.expect(expectedStatus.U)
      d.io.done.bits.attentionStatus.expect(expectedAttention.U)
      d.io.done.bits.writeBytes.expect(acknowledged.U)
      d.io.done.bits.outputCommitted.expect((expectedStatus == Status.Ok).B)
      for ((address, data) <- original if !physicalWrites(address)) assert(image(address) == data, "GQA changed a source, cache prefix, or guard")
      if (expectedStatus == Status.Ok) {
        assert(finalAckHeld && acknowledged == in.tokens * 4096)
        assert(physicalWrites.toSet == referenceResult.get.output.keySet)
        assert(referenceResult.get.output.forall { case (address, data) => image(address) == data })
        assert(groupCount == ((in.length + 31) / 32 + 1) * 8 * ((in.tokens + 15) / 16) && doneCount == groupCount)
      }
      if (fault == "final-ack") {
        assert(injected && finalAckHeld && physicalWrites.size * 64 == in.tokens * 4096)
        assert(acknowledged == in.tokens * 4096 - 64, "failed ACK counted as committed bytes")
        assert(image(outBase + in.tokens * 4096 - 64) == referenceResult.get.output(outBase + in.tokens * 4096 - 64),
          "erroring store must still have a modeled physical side effect")
      }
      if (Set("matrix-result", "matrix-nonfinite").contains(fault)) assert(abortObserved && injected && doneCount == 1)
      if (fault == "matrix-early-done") assert(injected && doneCount == 2 && physicalWrites.isEmpty)
      val held = completion(d)
      d.io.job.valid.poke(true.B)
      for (_ <- 0 until 13) { tick(); d.io.job.ready.expect(false.B); assert(completion(d) == held, "done changed under backpressure") }
      d.io.job.valid.poke(false.B); d.io.done.ready.poke(true.B); tick(); d.io.done.ready.poke(false.B)
      d.io.job.ready.expect((expectedStatus == Status.Ok).B); d.io.resetRequired.expect((expectedStatus != Status.Ok).B)
      if (expectedStatus != Status.Ok) {
        d.io.job.valid.poke(true.B); for (_ <- 0 until 7) tick()
        d.io.job.ready.expect(false.B); d.io.memory.valid.expect(false.B); d.io.done.valid.expect(false.B)
        d.io.job.valid.poke(false.B)
      }
      d.io.memory.ready.poke(false.B); d.io.scalarHold.poke(false.B); d.io.scalarFault.poke(false.B)
      println(s"BF16_GQA_OWNER_PROTOCOL_SCALAR label=$label tokens=${in.tokens} cache=${in.length} status=$expectedStatus attention=$expectedAttention ack_bytes=$acknowledged physical_stores=${physicalWrites.size} matrix_groups=$groupCount scalar_checks=$scalarCount cycles=$cycle real_matrix_rtl=false model_m128=false")
    }
  }

  "Bf16CausalGqaOwner" should "preserve actual cold and carried append bytes through causal GQA with head mapping" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      val memory = new Memory(8)
      val k0 = vector(2, 2, 3); val v0 = vector(2, 2, 17)
      val first = memory.append(d, Receipt(0, 0), k0, v0)
      memory.run(d, Inputs(vector(2, 8, 9), k0, v0, 2, 0, 8), "cold-two")
      val before = memory.image.toMap
      val k1 = vector(1, 2, 25); val v1 = vector(1, 2, 29)
      val carried = memory.append(d, first, k1, v1)
      assert(carried == Receipt(3, 2))
      for (plane <- 0 until 2; index <- 0 until first.length * 16) {
        val address = cacheBase + plane * 8 * 1024 + index * 64
        assert(memory.image(address) == before(address), "carried append changed actual published prefix")
      }
      memory.run(d, Inputs(vector(1, 8, 31), k0 ++ k1, v0 ++ v1, 1, first.length, 8), "carried-one")
    }
  }

  it should "compute a three-row tail and retain failed final physical stores without publication" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); val memory = new Memory(8)
      val keys = vector(3, 2, 7); val values = vector(3, 2, 21)
      memory.append(d, Receipt(0, 0), keys, values)
      val in = Inputs(vector(3, 8, 13), keys, values, 3, 0, 8)
      memory.run(d, in, "tail-three")
      memory.run(d, in.copy(tokens = 1, queryStart = 2, q = vector(1, 8, 27)), "failed-final-write", "final-ack", Status.Memory)
      init(d) // Joint owner/Scalar/Matrix/transport reset retains the DDR image.
      memory.run(d, in.copy(tokens = 1, queryStart = 2, q = vector(1, 8, 27)), "retry-after-final-write")
    }
  }

  it should "drain Matrix faults, reject nonfinite inputs and unsupported exp, and lock until joint reset" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); val memory = new Memory(4)
      val keys = vector(2, 2, 4); val values = vector(2, 2, 15)
      memory.append(d, Receipt(0, 0), keys, values)
      val in = Inputs(vector(1, 8, 11), keys, values, 1, 1, 4)
      for ((fault, status, attention) <- Seq(
        ("memory-read", Status.Memory, 0), ("memory-tag", Status.Protocol, 0),
        ("matrix-result", Status.Protocol, 0), ("matrix-done", Status.Protocol, 0),
        ("matrix-tag", Status.Protocol, 0), ("matrix-early-done", Status.Protocol, 0), ("matrix-nonfinite", Status.Numerical, 1),
        ("scalar", Status.Numerical, 2))) {
        init(d); memory.run(d, in, fault, fault, status, attention)
      }
      init(d)
      memory.run(d, in.copy(q = in.q.updated(0, 0x7f80)), "nonfinite-query", "nonfinite-q", Status.Numerical, 1)
      for ((role, pattern) <- Seq(("k", 0x7fc1), ("v", 0xff80))) {
        init(d); val badMemory = new Memory(4)
        val badKeys = if (role == "k") keys.updated(0, pattern) else keys
        val badValues = if (role == "v") values.updated(0, pattern) else values
        badMemory.append(d, Receipt(0, 0), badKeys, badValues)
        badMemory.run(d, in.copy(k = badKeys, v = badValues), s"nonfinite-$role", s"nonfinite-$role", Status.Numerical, 1)
      }
      // A legal one-row query over two keys, with an unmasked difference < -80.
      // The cache is produced by append, not by seeding an intermediate tensor.
      init(d); val wide = new Memory(4)
      val wideKeys = Vector.fill(1024)(0).updated(0, bf(-128f)).updated(512, bf(128f))
      wide.append(d, Receipt(0, 0), wideKeys, values)
      val wideQuery = Vector.fill(2048)(0).updated(0, bf(16f))
      wide.run(d, Inputs(wideQuery, wideKeys, values, 1, 1, 4), "unsupported-unmasked-exp", "domain", Status.Unsupported, 3)
    }
  }

  it should "cross the sixteen-query and thirty-two-key boundaries using an actual carried append prefix" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); val memory = new Memory(40)
      val prefixKeys = vector(16, 2, 6); val prefixValues = vector(16, 2, 23)
      val prefix = memory.append(d, Receipt(0, 0), prefixKeys, prefixValues)
      val tailKeys = vector(17, 2, 18); val tailValues = vector(17, 2, 30)
      val appended = memory.append(d, prefix, tailKeys, tailValues)
      assert(appended == Receipt(33, 2))
      memory.run(d, Inputs(vector(17, 8, 12), prefixKeys ++ tailKeys, prefixValues ++ tailValues,
        17, prefix.length, 40), "query17-cache33-boundaries")
    }
  }

  it should "reject geometry, fully masked descriptors, whole-allocation aliases, and address overflow before access" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val cases: Seq[(String, Int, Bf16CausalGqaJob => Unit)] = Seq(
        ("zero-tokens", Status.Bounds, _.tokens.poke(0.U)),
        ("too-many-tokens", Status.Bounds, _.tokens.poke(129.U)),
        ("query-heads", Status.Bounds, _.queryHeads.poke(4.U)),
        ("kv-heads", Status.Bounds, _.kvHeads.poke(1.U)),
        ("dimension", Status.Bounds, _.headDim.poke(128.U)),
        ("fully-masked-empty-cache", Status.Bounds, _.cacheLength.poke(0.U)),
        ("zero-capacity", Status.Bounds, _.capacityTokens.poke(0.U)),
        ("capacity-limit", Status.Bounds, _.capacityTokens.poke(257.U)),
        ("length-over-capacity", Status.Bounds, _.cacheLength.poke(17.U)),
        ("query-start-mismatch", Status.Dependency, _.queryStart.poke(1.U)),
        ("query-start-overflow32", Status.Dependency, _.queryStart.poke("hffffffff".U)),
        ("query-alignment", Status.Bounds, _.queryInput.poke((qBase + 2).U)),
        ("cache-alignment", Status.Bounds, _.cacheBase.poke((cacheBase + 2).U)),
        ("output-alignment", Status.Bounds, _.output.poke((outBase + 2).U)),
        ("query-output-alias", Status.Bounds, _.output.poke(qBase.U)),
        ("query-output-partial-alias", Status.Bounds, _.output.poke((qBase + 64).U)),
        ("query-unused-key-capacity", Status.Bounds, _.queryInput.poke((cacheBase + 15 * 1024).U)),
        ("output-unused-value-capacity", Status.Bounds, _.output.poke((cacheBase + 31 * 1024).U)),
        ("query-overflow56", Status.Bounds, _.queryInput.poke(((BigInt(1) << 56) - 64).U)),
        ("output-overflow56", Status.Bounds, _.output.poke(((BigInt(1) << 56) - 64).U)),
        ("cache-allocation-overflow56", Status.Bounds, _.cacheBase.poke(((BigInt(1) << 56) - 2048).U)),
        ("query-overflow64", Status.Bounds, _.queryInput.poke(((BigInt(1) << 64) - 64).U)),
        ("output-overflow64", Status.Bounds, _.output.poke(((BigInt(1) << 64) - 64).U)),
        ("cache-overflow64", Status.Bounds, _.cacheBase.poke(((BigInt(1) << 64) - 64).U)))
      for ((label, status, mutate) <- cases) {
        init(d); setJob(d, 1, 0, 1, 16); mutate(d.io.job.bits)
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        var cycles = 0
        while (!d.io.done.valid.peek().litToBoolean && cycles < 10) {
          d.io.memory.valid.expect(false.B); d.io.matrix.group.valid.expect(false.B)
          d.io.scalarRequestFire.expect(false.B); d.clock.step(); cycles += 1
        }
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(status.U)
        d.io.done.bits.writeBytes.expect(0.U); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.memory.valid.expect(false.B); d.io.response.ready.expect(false.B)
        val held = completion(d); d.clock.step(7); assert(completion(d) == held)
        d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
        d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B)
        println(s"BF16_GQA_REJECT label=$label status=$status memory_requests=0")
      }
    }
  }

  it should "address a synthetic M128 source near the aperture boundary and reset a pending cache read" in {
    test(new Bf16CausalGqaHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); setJob(d, 128, 128, 256, 256)
      val source = (BigInt(1) << 56) - 128 * 4096
      d.io.job.bits.queryInput.poke(source.U)
      d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      // Only the first physical 16-row query tile is read. This deliberately
      // stops before doing any M128 arithmetic or claiming a model-level gate.
      for (index <- 0 until 16 * 8) {
        d.io.memory.valid.expect(true.B)
        val r = request(d.io.memory.bits)
        assert(!r.write && r.address == source + (index / 8) * 4096 + (index % 8) * 64)
        assert(r.tag == ((jobTag << 32) | index))
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(bf(.125f))).U)
        d.io.response.bits.tag.poke(r.tag.U); d.io.response.bits.error.poke(false.B)
        d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.io.memory.valid.expect(true.B); d.io.memory.bits.address.expect(cacheBase.U)
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
      d.clock.step(17); d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
      init(d) // Joint transport reset drops the deliberately withheld cache ACK.
      d.clock.step(11); d.io.job.ready.expect(true.B); d.io.memory.valid.expect(false.B)
      d.io.done.valid.expect(false.B); d.io.resetRequired.expect(false.B)
      println("BF16_GQA_ADDRESS_ONLY tokens=128 query_reads=128 pending_cache_reset=true real_matrix_rtl=false model_m128=false")
    }
  }
}
