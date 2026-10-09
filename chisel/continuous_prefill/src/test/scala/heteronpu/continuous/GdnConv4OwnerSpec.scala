// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** The test provides memory bytes, never arithmetic answers. This is the same
  * BlockScalarFloat used in production, outside the arithmetic-free owner. */
class GdnConv4ArithmeticHarness(channels: Int, maxTokens: Int = 128) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnConv4Job))
    val currentGeneration = Input(UInt(32.W))
    val done = Decoupled(new GdnConv4Result)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val traceValid = Output(Bool())
    val trace = Output(new ScalarRequest)
    val resultTraceValid = Output(Bool())
    val resultTrace = Output(UInt(32.W))
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnConv4Owner(channels, maxTokens))
  val scalar = Module(new BlockScalarFloat)
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  owner.io.currentGeneration := io.currentGeneration
  io.resetRequired := owner.io.resetRequired
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.traceValid := scalar.io.request.fire
  io.trace := scalar.io.request.bits
  io.resultTraceValid := owner.io.scalar.result.fire
  io.resultTrace := owner.io.scalar.result.bits
}

trait GdnConv4TestSupport { self: ChiselScalatestTester with Matchers =>
  val inputBase = BigInt("110000000", 16)
  val weightBase = BigInt("120000000", 16)
  val oldBase = BigInt("130000000", 16)
  val newBase = BigInt("140000000", 16)
  val outputBase = BigInt("150000000", 16)
  val fullMask = (BigInt(1) << 64) - 1
  def bits(f: Float): Int = java.lang.Float.floatToRawIntBits(f)
  def fp(b: Int): Float = java.lang.Float.intBitsToFloat(b << 16)
  def bf(f: Float): Int = {
    val u = bits(f).toLong & 0xffffffffL
    if ((u & 0x7f800000L) == 0x7f800000L) ((u >>> 16).toInt | (if ((u & 0x7fffffL) != 0) 64 else 0)) & 65535
    else ((u + 0x7fffL + ((u >>> 16) & 1)) >>> 16).toInt & 65535
  }
  def pack(xs: Seq[Int]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (v, (x, i)) => v | (BigInt(x & 65535) << (16 * i))
  }
  def expRecipe(x: Float): Float = {
    if (math.abs(x) >= 80f) 0f else {
      val t = (math.abs(x) * (1 / math.log(2)).toFloat).toFloat
      val k = t.toInt; val frac = (t - k.toFloat).toFloat
      val coeff = (0 to 7).map(i => (math.pow(-math.log(2), i) /
        (if (i == 0) 1.0 else (1 to i).map(_.toDouble).product)).toFloat)
      var h = coeff(7)
      for (i <- 6 to 0 by -1) h = ((h * frac).toFloat + coeff(i)).toFloat
      (h * java.lang.Float.intBitsToFloat((127 - k) << 23)).toFloat
    }
  }
  def silu(x: Float): Float = {
    val e = expRecipe(x)
    val inv = (1f / (1f + e).toFloat).toFloat
    ((inv * (if (bits(x) < 0) e else 1f)).toFloat * x).toFloat
  }
  case class Expected(output: Seq[Int], history: Seq[Int], conv: Seq[Int])
  case class ArithmeticStep(op: Int, a: Float, b: Float, result: Float)
  def arithmeticSteps(input: Seq[Int], weight: Seq[Int], past: Seq[Int], channels: Int, cold: Boolean): Seq[ArithmeticStep] = {
    val h = (if (cold) Seq.fill(channels * 4)(0) else past).toArray
    val steps = scala.collection.mutable.ArrayBuffer.empty[ArithmeticStep]
    def operation(op: Int, a: Float, b: Float, result: Float): Float = {
      steps += ArithmeticStep(op, a, b, result); result
    }
    for (g <- 0 until channels by 32; t <- 0 until input.size / channels; c <- g until g + 32) {
      val window = (1 to 3).map(k => h(c * 4 + k)) :+ input(t * channels + c)
      var acc = 0f
      for (k <- 0 until 4) {
        val a = fp(window(k)); val b = fp(weight(c * 4 + k))
        val p = operation(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
        acc = operation(ScalarOp.Add, acc, p, (acc + p).toFloat)
      }
      val x = fp(bf(acc))
      val e = operation(ScalarOp.ExpNegative, x, 0f, expRecipe(x))
      val den = operation(ScalarOp.Add, 1f, e, (1f + e).toFloat)
      val inv = operation(ScalarOp.Div, 1f, den, (1f / den).toFloat)
      val sign = if (bits(x) < 0) e else 1f
      val sigmoid = operation(ScalarOp.Mul, inv, sign, (inv * sign).toFloat)
      operation(ScalarOp.Mul, sigmoid, x, (sigmoid * x).toFloat)
      for (k <- 0 until 4) h(c * 4 + k) = window(k)
    }
    steps.toSeq
  }
  def expected(input: Seq[Int], weight: Seq[Int], past: Seq[Int], channels: Int, cold: Boolean): Expected = {
    val history = (if (cold) Seq.fill(channels * 4)(0) else past).toArray
    val out = Array.fill(input.size)(0); val conv = Array.fill(input.size)(0)
    for (t <- 0 until input.size / channels; c <- 0 until channels) {
      val window = (1 to 3).map(k => history(c * 4 + k)) :+ input(t * channels + c)
      var acc = 0f
      for (k <- 0 until 4) acc = (acc + (fp(window(k)) * fp(weight(c * 4 + k))).toFloat).toFloat
      val b = bf(acc); conv(t * channels + c) = b
      out(t * channels + c) = bf(silu(fp(b)))
      for (k <- 0 until 4) history(c * 4 + k) = window(k)
    }
    Expected(out.toSeq, history.toSeq, conv.toSeq)
  }
  def init(d: GdnConv4ArithmeticHarness): Unit = {
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U)
    d.io.response.bits.error.poke(false.B); d.io.currentGeneration.poke(0.U)
    d.io.scalarHold.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
    d.clock.setTimeout(0)
  }
  def setJob(d: GdnConv4ArithmeticHarness, channels: Int, tokens: Int, cold: Boolean, generation: Int): Unit = {
    val j = d.io.job.bits
    j.tokens.poke(tokens.U); j.channels.poke(channels.U); j.input.poke(inputBase.U)
    j.weight.poke(weightBase.U); j.historyIn.poke(oldBase.U); j.historyOut.poke(newBase.U)
    j.output.poke(outputBase.U); j.cold.poke(cold.B); j.expectedGeneration.poke(generation.U)
    j.tag.poke(0x12345678L.U); d.io.currentGeneration.poke(generation.U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: GdnConv4ArithmeticHarness): Request = {
    val r = d.io.memory.bits
    Request(r.write.peek().litToBoolean, r.address.peek().litValue, r.data.peek().litValue,
      r.mask.peek().litValue, r.tag.peek().litValue)
  }
  def completion(d: GdnConv4ArithmeticHarness): Seq[BigInt] = {
    val r = d.io.done.bits
    Seq(r.tag.peek().litValue, r.status.peek().litValue, r.writeBytes.peek().litValue,
      r.cycles.peek().litValue, r.historyCommitted.peek().litValue, r.generation.peek().litValue)
  }
  def beats(base: BigInt, values: Seq[Int]): Map[BigInt, BigInt] =
    values.grouped(32).zipWithIndex.map { case (xs, i) => (base + i * 64) -> pack(xs) }.toMap

  def run(d: GdnConv4ArithmeticHarness, channels: Int, input: Seq[Int], weight: Seq[Int], past: Seq[Int],
          cold: Boolean, generation: Int, label: String, fault: String = "none", trace: Boolean = false): Expected = {
    val tokens = input.size / channels
    val gold = expected(input, weight, past, channels, cold)
    val reads = beats(inputBase, input) ++ beats(weightBase, weight) ++ beats(oldBase, past)
    val writes = beats(outputBase, gold.output) ++ beats(newBase, gold.history)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    val convOrder = (0 until channels by 32).flatMap(g => (0 until tokens).flatMap(t => (0 until 32).map(c => gold.conv(t * channels + g + c))))
    val scalarExpected = if (trace) arithmeticSteps(input, weight, past, channels, cold) else Seq.empty
    var traced = 0; var requestsTraced = 0; var resultsTraced = 0
    var elapsed = 0; var issued = 0; var acked = 0; var faulted = false
    def step(n: Int): Unit = {
      if (trace) for (_ <- 0 until n) {
        // Exercise both shared-service request and result backpressure while
        // retaining real arithmetic, including at the BF16 boundary.
        d.io.scalarHold.poke((elapsed % 19 < 4).B)
        def unsigned(f: Float): BigInt = BigInt(bits(f).toLong & 0xffffffffL)
        if (d.io.traceValid.peek().litToBoolean) {
          val expected = scalarExpected(requestsTraced)
          d.io.trace.op.expect(expected.op.U)
          d.io.trace.a.expect(unsigned(expected.a).U); d.io.trace.b.expect(unsigned(expected.b).U)
          requestsTraced += 1
        }
        if (d.io.resultTraceValid.peek().litToBoolean) {
          d.io.resultTrace.expect(unsigned(scalarExpected(resultsTraced).result).U)
          resultsTraced += 1
        }
        if (d.io.traceValid.peek().litToBoolean && d.io.trace.op.peek().litValue == ScalarOp.ExpNegative) {
          d.io.trace.a.expect((BigInt(convOrder(traced)) << 16).U)
          traced += 1
        }
        d.clock.step(); elapsed += 1
      } else { d.clock.step(n); elapsed += n }
    }
    setJob(d, channels, tokens, cold, generation)
    d.io.job.ready.expect(true.B); d.io.job.valid.poke(true.B); step(1); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < channels * tokens * 250 + 50000) {
      if (!d.io.memory.valid.peek().litToBoolean) {
        // Memory ready is low, so a request cannot vanish during a batched step.
        step(if (trace) 1 else 64)
      } else {
        val r = request(d)
        assert(r.tag == ((BigInt(0x12345678L) << 32) | issued), "transaction tag sequence")
        assert((r.address & 63) == 0)
        val delay = 1 + issued % 5
        d.io.scalarHold.poke((issued % 3 == 0).B)
        step(delay); assert(request(d) == r, "request changed while stalled")
        d.io.scalarHold.poke(false.B)
        d.io.memory.ready.poke(true.B); step(1); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == newBase + channels * 8 - 64
        val inject = !faulted && (fault match {
          case "read" | "tag" => !r.write
          case "final-ack" => last
          case _ => false
        })
        if (inject) faulted = true
        if (r.write) {
          assert(writes.contains(r.address), "write outside output/staged-state spans")
          assert(r.mask == fullMask)
          assert(!committed.contains(r.address), "duplicate write")
          assert(r.data == writes(r.address), s"BF16 arithmetic/history mismatch $label at ${r.address.toString(16)}")
        } else {
          assert(reads.contains(r.address), "read outside declared spans")
          assert(r.mask == 0)
          if (cold) assert(r.address < oldBase || r.address >= oldBase + channels * 8, "cold read stale history")
        }
        // In particular, the last store must wait for its ACK before publishing.
        step(if (last) 37 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.historyCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        d.io.response.bits.tag.poke((r.tag ^ (if (inject && fault == "tag") BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && fault != "tag").B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B)
        step(1); d.io.response.valid.poke(false.B)
        if (r.write && !inject) { committed(r.address) = r.data; acked += 1 }
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner deadlock: $label")
    val code = if (fault == "tag") Status.Protocol else if (fault != "none") Status.Memory else Status.Ok
    if (d.io.done.bits.status.peek().litValue != code) {
      println(s"GDN_CONV4_UNEXPECTED_STATUS label=$label status=${d.io.done.bits.status.peek().litValue} bytes=${d.io.done.bits.writeBytes.peek().litValue} input_group_address=0x${d.io.memory.bits.address.peek().litValue.toString(16)} scalar_op=${d.io.trace.op.peek().litValue} scalar_a=0x${d.io.trace.a.peek().litValue.toString(16)} scalar_b=0x${d.io.trace.b.peek().litValue.toString(16)} scalar_result=0x${d.io.resultTrace.peek().litValue.toString(16)}")
    }
    d.io.done.bits.status.expect(code.U); d.io.done.bits.writeBytes.expect((acked * 64).U)
    d.io.done.bits.historyCommitted.expect((fault == "none").B)
    d.io.done.bits.generation.expect((generation + (if (fault == "none") 1 else 0)).U)
    d.io.memory.valid.expect(false.B)
    if (fault == "none") {
      assert(committed.toMap == writes)
      if (trace) assert(traced == input.size, "missing convolution BF16-boundary checks")
      if (trace) assert(requestsTraced == scalarExpected.size && resultsTraced == scalarExpected.size, "missing scalar rounding checks")
    } else assert(faulted)
    val held = completion(d); step(13); assert(completion(d) == held, "completion changed while stalled")
    println(s"GDN_CONV4_RTL_CASE label=$label channels=$channels tokens=$tokens cold=$cold status=$code acknowledged_bytes=${acked * 64} cycles=${held(3)} boundary_checks=$traced scalar_result_checks=$resultsTraced")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((fault == "none").B)
    gold
  }
  def readBf16(path: java.nio.file.Path): Seq[Int] = {
    val b = Files.readAllBytes(path)
    require(b.length % 2 == 0)
    b.grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
  }
}

class GdnConv4OwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnConv4TestSupport {
  "GdnConv4Owner" should "preserve BF16 boundaries, raw carried history, ACK fencing and fail-closed reset" in {
    test(new GdnConv4ArithmeticHarness(32)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      val random = new scala.util.Random(35084)
      def values(n: Int) = Seq.fill(n)(bf((random.nextDouble() * 3 - 1.5).toFloat))
      val weight = values(128).updated(5 * 4 + 3, 0x0220); val ignoredPast = values(128)
      // Include the actual channel397 underflow operands found by the full
      // geometry test. The accepted FP32 product must be signed zero, not a
      // test-injected answer or a blanket suppression of shared-service errors.
      val first = run(d, 32, values(32).updated(5, 0x83d7), weight, ignoredPast, true, 0, "cold1", trace = true)
      val second = run(d, 32, values(32), weight, first.history, false, 1, "carried1", trace = true)
      run(d, 32, values(32 * 16), weight, second.history, false, 2, "carried16", trace = true)
      for (fault <- Seq("read", "tag", "final-ack")) {
        init(d)
        run(d, 32, values(32), weight, ignoredPast, true, 0, fault, fault)
        d.io.resetRequired.expect(true.B); d.clock.step(5); d.io.job.ready.expect(false.B)
      }
      // Every malformed job must fail before any memory/scalar request.
      for (bad <- 0 until 8) {
        init(d); setJob(d, 32, 1, cold = false, generation = 7)
        val j = d.io.job.bits
        bad match {
          case 0 => j.historyOut.poke(oldBase.U)
          case 1 => j.output.poke(inputBase.U)
          case 2 => j.input.poke((inputBase + 2).U)
          case 3 => j.tokens.poke(0.U)
          case 4 => j.channels.poke(64.U)
          case 5 => j.expectedGeneration.poke(6.U)
          case 6 => j.cold.poke(true.B)
          case 7 => j.historyOut.poke(((BigInt(1) << 56) - 64).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.memory.valid.expect(false.B); d.io.traceValid.expect(false.B)
        d.io.done.bits.status.expect((if (bad == 5 || bad == 6) Status.Dependency else Status.Bounds).U)
        d.io.done.bits.historyCommitted.expect(false.B); d.io.done.bits.writeBytes.expect(0.U)
      }
      // Nonfinite operands and the shared exp's unsupported negative-saturation
      // domain fail without injecting an arithmetic result/error from the test.
      for (badInput <- Seq(0x7fc0, bf(-80f))) {
      init(d); setJob(d, 32, 1, cold = true, generation = 0)
      d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      var sequence = 0
      while (!d.io.done.valid.peek().litToBoolean && sequence < 8) {
        while (!d.io.memory.valid.peek().litToBoolean && !d.io.done.valid.peek().litToBoolean) d.clock.step()
        if (d.io.memory.valid.peek().litToBoolean) {
          val r = request(d); assert(!r.write)
          d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
          d.io.response.bits.data.poke((if (r.address == inputBase) pack(Seq.fill(32)(badInput)) else pack(Seq.fill(32)(bf(1f)))).U)
          d.io.response.bits.tag.poke(r.tag.U); d.io.response.bits.error.poke(false.B)
          d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
          sequence += 1
        }
      }
      d.io.done.bits.status.expect(Status.Numerical.U)
      d.io.done.bits.historyCommitted.expect(false.B); d.io.done.bits.writeBytes.expect(0.U)
      }
      // Reset the owner and shared arithmetic together with a scalar operation
      // in flight. No old completion or state publication may survive reset.
      init(d); setJob(d, 32, 1, cold = true, generation = 0)
      d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      for (_ <- 0 until 5) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d); assert(!r.write)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(bf(0.5f))).U)
        d.io.response.bits.tag.poke(r.tag.U); d.io.response.bits.error.poke(false.B)
        d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.clock.step(7); d.io.done.valid.expect(false.B); d.io.memory.valid.expect(false.B)
      init(d); run(d, 32, values(32), weight, ignoredPast, true, 0, "recovered", trace = true)
    }
  }
}

/** Local-only actual model payloads. The repository never embeds checkpoint
  * bytes, NPZ payloads, or regenerated downloadable weight-bearing fixtures. */
class GdnConv4RealSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnConv4TestSupport {
  "GdnConv4Owner full geometry" should "execute actual BF16 producers through the real shared scalar arithmetic" in {
    val root = Paths.get(sys.env.getOrElse("GDN_CONV_FIXTURE", throw new IllegalArgumentException("GDN_CONV_FIXTURE is required")))
    def digest(bytes: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).map(b => f"${b & 255}%02x").mkString
    val manifestBytes = Files.readAllBytes(root.resolve("manifest.json"))
    sys.env.get("GDN_CONV_MANIFEST_SHA256").foreach(expected => require(digest(manifestBytes) == expected, "fixture manifest hash drift"))
    val manifest = ujson.read(new String(manifestBytes, java.nio.charset.StandardCharsets.UTF_8))
    require(manifest("model_id").str == "Qwen/Qwen3.5-0.8B" && manifest("revision").str == "2fc06364715b967f1860aea9cf38778875588b17")
    require(manifest("channels").num == 6144 && manifest("taps").num == 4)
    require(manifest("source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
    require(manifest("source_cache_npz_sha256").str == "effe83b39a07b2de618abb322dc2d3ae160f0d0391605d4e4fc78e3ff3d65f51")
    require(digest(Files.readAllBytes(root.resolve("weights.bin"))) == "130344a7183ae52ad58fc5da96539f28071b64d452bb3acf0890a7947da44188")
    val weight = readBf16(root.resolve("weights.bin")); require(weight.size == 6144 * 4)
    val cases = sys.env.getOrElse("GDN_CONV_CASES", "cold1,carried1").split(",").toSeq
    test(new GdnConv4ArithmeticHarness(6144)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for (name <- cases) {
        val dir = root.resolve(name)
        for (file <- Seq("input", "history_in", "conv_bf16", "output_bf16", "history_out")) {
          val bytes = Files.readAllBytes(dir.resolve(file + ".bin"))
          val recorded = manifest("cases")(name)("files")(file)
          require(bytes.length == recorded("bytes").num && digest(bytes) == recorded("sha256").str, s"fixture hash drift: $name/$file")
        }
        require(manifest("cases")(name)("conv_min").num > -80, "fixture is outside the supported negative-exp domain")
        val input = readBf16(dir.resolve("input.bin")); val past = readBf16(dir.resolve("history_in.bin"))
        require(input.size % 6144 == 0 && past.size == 6144 * 4)
        val cold = name.startsWith("cold")
        val gold = run(d, 6144, input, weight, past, cold, if (cold) 0 else 1, name)
        assert(gold.history == readBf16(dir.resolve("history_out.bin")), "official raw history mismatch")
        val officialConv = readBf16(dir.resolve("conv_bf16.bin"))
        val officialOutput = readBf16(dir.resolve("output_bf16.bin"))
        require(officialConv.size == input.size && officialOutput.size == input.size)
        def ulp(a: Int, b: Int): Int = {
          // The numerical ULP metric maps +/-0 together; report raw-bit
          // mismatches separately so this never implies native bit identity.
          def ordered(x: Int): Int = if ((x & 0x8000) != 0) 0x8000 - (x & 0x7fff) else 0x8000 + x
          math.abs(ordered(a) - ordered(b))
        }
        val convUlps = gold.conv.zip(officialConv).map { case (a, b) => ulp(a, b) }
        val outUlps = gold.output.zip(officialOutput).map { case (a, b) => ulp(a, b) }
        val convBitMismatch = gold.conv.zip(officialConv).count { case (a, b) => a != b }
        val outputBitMismatch = gold.output.zip(officialOutput).count { case (a, b) => a != b }
        println(s"GDN_CONV4_OFFICIAL_CASE label=$name values=${input.size} signed_zero_numeric_equal=true conv_bit_mismatch=$convBitMismatch conv_numeric_mismatch=${convUlps.count(_ != 0)} conv_max_bf16_ulp=${convUlps.max} output_bit_mismatch=$outputBitMismatch output_numeric_mismatch=${outUlps.count(_ != 0)} output_max_bf16_ulp=${outUlps.max}")
        assert(convUlps.max <= 1, "convolution diverged more than one BF16 ULP from official producer")
        assert(outUlps.max <= 1, "SiLU diverged more than one BF16 ULP from official producer")
      }
    }
  }
}
