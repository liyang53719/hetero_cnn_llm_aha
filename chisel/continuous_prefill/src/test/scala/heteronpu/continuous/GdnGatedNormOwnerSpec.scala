// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** Only memory transport is supplied by the test. Every arithmetic answer is
  * produced by the real shared production Scalar/SFU, including underflow. */
class GdnGatedNormArithmeticHarness(heads: Int) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnGatedNormJob))
    val done = Decoupled(new GdnGatedNormResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestValid = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultValid = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnGatedNormOwner(heads))
  val scalar = Module(new BlockScalarFloat)
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  io.resetRequired := owner.io.resetRequired
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := scalar.io.request.bits
  io.scalarRequestValid := scalar.io.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultValid := owner.io.scalar.result.fire
}

trait GdnGatedNormTestSupport { self: ChiselScalatestTester with Matchers =>
  val coreBase = BigInt("210000000", 16)
  val gateBase = BigInt("220000000", 16)
  val weightBase = BigInt("230000000", 16)
  val outputBase = BigInt("240000000", 16)
  val fullMask = (BigInt(1) << 64) - 1
  def bits(x: Float): Long = java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL
  def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  def bf(x: Float): Int = ((bits(x) + 0x7fffL + ((bits(x) >>> 16) & 1)) >>> 16).toInt & 65535
  def pack(xs: Seq[BigInt], width: Int): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (v, (x, i)) => v | (x << (width * i))
  }
  def expRecipe(x: Float): Float = {
    if (math.abs(x) >= 80f) 0f else {
      val t = (math.abs(x) * (1 / math.log(2)).toFloat).toFloat
      val k = t.toInt; val f = (t - k.toFloat).toFloat
      val c = (0 to 7).map(i => (math.pow(-math.log(2), i) /
        (if (i == 0) 1.0 else (1 to i).map(_.toDouble).product)).toFloat)
      var h = c(7)
      for (i <- 6 to 0 by -1) h = ((h * f).toFloat + c(i)).toFloat
      (h * java.lang.Float.intBitsToFloat((127 - k) << 23)).toFloat
    }
  }
  case class Step(op: Int, a: Float, b: Float, result: Float)
  def reference(core: Seq[Int], gate: Seq[Int], weight: Seq[Float]): (Seq[Int], Seq[Step]) = {
    require(core.size == gate.size && core.size % 128 == 0 && weight.size == 128)
    val steps = scala.collection.mutable.ArrayBuffer.empty[Step]
    val out = scala.collection.mutable.ArrayBuffer.empty[Int]
    def op(code: Int, a: Float, b: Float, result: Float): Float = {
      steps += Step(code, a, b, result); result
    }
    def mul(a: Float, b: Float): Float = op(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
    def add(a: Float, b: Float): Float = op(ScalarOp.Add, a, b, (a + b).toFloat)
    def div(a: Float, b: Float): Float = op(ScalarOp.Div, a, b, (a / b).toFloat)
    for (row <- core.indices by 128) {
      var sum = 0f
      for (i <- 0 until 128) sum = add(sum, mul(fp(core(row + i)), fp(core(row + i))))
      val variance = add(mul(sum, 1f / 128), 1e-6f)
      val root = op(ScalarOp.Sqrt, variance, 0f, math.sqrt(variance.toDouble).toFloat)
      val inverse = div(1f, root)
      for (i <- 0 until 128) {
        val norm = fp(bf(mul(fp(core(row + i)), inverse)))
        val weighted = mul(weight(i), norm)
        val z = fp(gate(row + i))
        val exponential = op(ScalarOp.ExpNegative, z, 0f, expRecipe(z))
        val inv = div(1f, add(1f, exponential))
        val sigmoid = mul(inv, if (bits(z) >= 0x80000000L) exponential else 1f)
        val silu = mul(sigmoid, z)
        out += bf(mul(weighted, silu))
      }
    }
    (out.toSeq, steps.toSeq)
  }
  def init(d: GdnGatedNormArithmeticHarness): Unit = {
    d.clock.setTimeout(50000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: GdnGatedNormArithmeticHarness, heads: Int, tokens: Int): Unit = {
    d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.heads.poke(heads.U)
    d.io.job.bits.core.poke(coreBase.U); d.io.job.bits.gate.poke(gateBase.U)
    d.io.job.bits.weight.poke(weightBase.U); d.io.job.bits.output.poke(outputBase.U)
    d.io.job.bits.tag.poke("h89abcdef".U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: GdnGatedNormArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: GdnGatedNormArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue)

  def run(d: GdnGatedNormArithmeticHarness, heads: Int, core: Seq[Int], gate: Seq[Int], weight: Seq[Float],
          label: String, fault: String = "none", trace: Boolean = false, numerical: Boolean = false): Seq[Int] = {
    d.io.scalarHold.poke(false.B)
    val tokens = core.size / (heads * 128)
    val (gold, operations) = if (numerical) (Seq.empty[Int], Seq.empty[Step]) else reference(core, gate, weight)
    def beats(base: BigInt, values: Seq[BigInt], width: Int): Map[BigInt, BigInt] =
      values.grouped(512 / width).zipWithIndex.map { case (v, i) => (base + i * 64) -> pack(v, width) }.toMap
    val reads = beats(coreBase, core.map(BigInt(_)), 16) ++ beats(gateBase, gate.map(BigInt(_)), 16) ++
      beats(weightBase, weight.map(x => BigInt(bits(x))), 32)
    val writes = beats(outputBase, gold.map(BigInt(_)), 16)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    var elapsed = 0; var issued = 0; var acked = 0; var tracedRequests = 0; var tracedResults = 0; var injected = false
    def step(n: Int): Unit = {
      if (trace) for (_ <- 0 until n) {
        d.io.scalarHold.poke((elapsed % 23 < 5).B)
        if (d.io.scalarRequestValid.peek().litToBoolean) {
          val expected = operations(tracedRequests)
          d.io.scalarRequest.op.expect(expected.op.U)
          d.io.scalarRequest.a.expect(BigInt(bits(expected.a)).U)
          d.io.scalarRequest.b.expect(BigInt(bits(expected.b)).U)
          tracedRequests += 1
        }
        if (d.io.scalarResultValid.peek().litToBoolean) {
          d.io.scalarResult.expect(BigInt(bits(operations(tracedResults).result)).U)
          tracedResults += 1
        }
        d.clock.step(); elapsed += 1
      } else { d.clock.step(n); elapsed += n }
    }
    setJob(d, heads, tokens); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(1); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < core.size * 250 + 30000) {
      if (!d.io.memory.valid.peek().litToBoolean) step(if (trace) 1 else 64)
      else {
        val r = request(d)
        assert(r.tag == ((BigInt("89abcdef", 16) << 32) | issued), "request sequence")
        val delay = 1 + issued % 5
        step(delay); assert(request(d) == r, "request changed under backpressure")
        d.io.memory.ready.poke(true.B); step(1); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == outputBase + core.size * 2 - 64
        val inject = !injected && (fault match {
          case "read" | "tag" => !r.write
          case "final-ack" => last
          case _ => false
        })
        if (inject) injected = true
        if (r.write) {
          assert(writes.contains(r.address)); assert(r.data == writes(r.address), s"recipe mismatch $label/${r.address}")
          assert(r.mask == fullMask); assert(!committed.contains(r.address))
        } else { assert(reads.contains(r.address)); assert(r.mask == 0) }
        step(if (last) 37 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        d.io.response.bits.tag.poke((r.tag ^ (if (inject && fault == "tag") BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && fault != "tag").B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(1); d.io.response.valid.poke(false.B)
        if (r.write && !inject) { committed(r.address) = r.data; acked += 1 }
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner timeout $label")
    val code = if (numerical) Status.Numerical else if (fault == "tag") Status.Protocol else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.status.expect(code.U); d.io.done.bits.writeBytes.expect((acked * 64).U)
    d.io.done.bits.outputCommitted.expect((code == Status.Ok).B); d.io.memory.valid.expect(false.B)
    if (code == Status.Ok) {
      assert(committed.toMap == writes)
      if (trace) assert(tracedRequests == operations.size && tracedResults == operations.size)
    } else if (!numerical) assert(injected)
    val held = completion(d); step(13); assert(completion(d) == held, "completion changed under stall")
    println(s"GDN_GATED_NORM_RTL label=$label heads=$heads tokens=$tokens status=$code ack_bytes=${acked * 64} cycles=${held(3)} scalar_checks=$tracedResults")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
    gold
  }
  def readBf(path: java.nio.file.Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
}

class GdnGatedNormOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnGatedNormTestSupport {
  "GdnGatedNormOwner" should "preserve FP32 gamma, BF16 boundaries, IEEE underflow, ACK fencing and reset" in {
    test(new GdnGatedNormArithmeticHarness(1)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val random = new scala.util.Random(350128)
      val core = Seq.fill(128)(bf((random.nextDouble() * 2 - 1).toFloat)).updated(0, 0).updated(1, 0x8000).updated(2, 1).updated(3, 0x8001)
      val gate = Seq.fill(128)(bf((random.nextDouble() * 4 - 2).toFloat)).updated(0, 0x8000).updated(1, 0).updated(2, 1).updated(3, 0x8001)
      val weight = Seq.tabulate(128)(i => (0.25 + i * 0.002137).toFloat)
      init(d); run(d, 1, core, gate, weight, "trace-boundaries-underflow", trace = true)
      run(d, 1, core ++ core.reverse, gate ++ gate.reverse, weight, "two-token-head")
      for (fault <- Seq("read", "tag", "final-ack")) {
        init(d); run(d, 1, core, gate, weight, fault, fault)
        d.clock.step(7); d.io.job.ready.expect(false.B)
      }
      for ((badCore, badGate, badWeight, label) <- Seq(
        (core.updated(0, 0x7fc0), gate, weight, "nan-core"),
        (core, gate.updated(0, bf(-80f)), weight, "negative-exp-domain"),
        (core, gate.updated(0, 0x7f80), weight, "infinite-gate"),
        (core, gate, weight.updated(0, Float.NaN), "nan-gamma"))) {
        init(d); run(d, 1, badCore, badGate, badWeight, label, numerical = true)
      }
      for (bad <- 0 until 7) {
        init(d); setJob(d, 1, 1)
        bad match {
          case 0 => d.io.job.bits.output.poke(coreBase.U)
          case 1 => d.io.job.bits.output.poke(weightBase.U)
          case 2 => d.io.job.bits.gate.poke((gateBase + 2).U)
          case 3 => d.io.job.bits.tokens.poke(0.U)
          case 4 => d.io.job.bits.heads.poke(16.U)
          case 5 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
          case 6 => d.io.job.bits.tokens.poke(129.U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
        d.io.done.bits.outputCommitted.expect(false.B); d.io.memory.valid.expect(false.B)
        d.io.scalarRequestValid.expect(false.B)
      }
      // Reset with an actual scalar operation in flight, then execute a fresh
      // job. Reset covers both owner and shared service in this harness.
      init(d); setJob(d, 1, 1); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      for (_ <- 0 until 16) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d); assert(!r.write)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(BigInt(0x3f00)), 16).U)
        d.io.response.bits.tag.poke(r.tag.U); d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.clock.step(2); d.io.done.valid.expect(false.B)
      init(d); run(d, 1, core, gate, weight, "reset-recovered")
      // Exercise actual heads on the already compiled one-head DUT. This
      // establishes arithmetic coverage, not the sixteen-head address loop.
      sys.env.get("GDN_GATED_NORM_FIXTURE").foreach { directory =>
        val root = Paths.get(directory)
        def digest(raw: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(raw).map(x => f"${x & 255}%02x").mkString
        val raw = Files.readAllBytes(root.resolve("manifest.json"))
        require(digest(raw) == sys.env.getOrElse("GDN_GATED_NORM_MANIFEST_SHA256", ""), "fixture pin required")
        val manifest = ujson.read(new String(raw, java.nio.charset.StandardCharsets.UTF_8))
        require(manifest("official_source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
        for ((file, metadata) <- manifest("files").obj) {
          val data = Files.readAllBytes(root.resolve(file))
          require(data.length == metadata("bytes").num && digest(data) == metadata("sha256").str, s"fixture drift $file")
        }
        val wb = java.nio.ByteBuffer.wrap(Files.readAllBytes(root.resolve("weight.f32le"))).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        val gamma = Seq.fill(128)(wb.getFloat())
        for (label <- Seq("cold1", "carried1"); head <- 0 until 16) {
          def slice(kind: String): Seq[Int] = readBf(root.resolve(s"${label}_${kind}.bf16le")).slice(head * 128, (head + 1) * 128)
          val got = run(d, 1, slice("core"), slice("gate"), gamma, s"actual-$label-head$head", trace = head == 0)
          assert(got == slice("recipe"), "independent Python recipe mismatch")
          val native = slice("official")
          println(s"GDN_GATED_NORM_NATIVE_DIAGNOSTIC label=$label head=$head bit_mismatches=${got.zip(native).count { case (a, b) => a != b }} official_acceptance=UNASSIGNED")
        }
      }
    }
  }
}

/** Requires verified local-only captures from gdn_gated_norm_reference.py.
  * Checks hardware recipe bit-for-bit. Native metrics remain diagnostics until
  * a stage-specific acceptance bound is separately frozen and approved. */
class GdnGatedNormRealSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnGatedNormTestSupport {
  "GdnGatedNormOwner actual layer0" should "execute authentic heads using shared scalar arithmetic" in {
    val root = Paths.get(sys.env.getOrElse("GDN_GATED_NORM_FIXTURE", throw new IllegalArgumentException("GDN_GATED_NORM_FIXTURE required")))
    val heads = sys.env.getOrElse("GDN_GATED_NORM_HEADS", "1").toInt
    require(heads == 1 || heads == 16)
    def digest(a: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(a).map(x => f"${x & 255}%02x").mkString
    val manifestBytes = Files.readAllBytes(root.resolve("manifest.json"))
    require(digest(manifestBytes) == sys.env.getOrElse("GDN_GATED_NORM_MANIFEST_SHA256", throw new IllegalArgumentException("fixture manifest pin required")))
    val manifest = ujson.read(new String(manifestBytes, java.nio.charset.StandardCharsets.UTF_8))
    require(manifest("model_id").str == "Qwen/Qwen3.5-0.8B" && manifest("revision").str == "2fc06364715b967f1860aea9cf38778875588b17")
    require(manifest("official_source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
    require(manifest("heads").num == 16 && manifest("width").num == 128)
    for ((file, metadata) <- manifest("files").obj) {
      val raw = Files.readAllBytes(root.resolve(file))
      require(raw.length == metadata("bytes").num && digest(raw) == metadata("sha256").str, s"fixture drift: $file")
    }
    val weightRaw = Files.readAllBytes(root.resolve("weight.f32le"))
    val wb = java.nio.ByteBuffer.wrap(weightRaw).order(java.nio.ByteOrder.LITTLE_ENDIAN)
    val weight = Seq.fill(128)(wb.getFloat())
    test(new GdnGatedNormArithmeticHarness(heads)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for (label <- Seq("cold1", "carried1")) {
        val core = readBf(root.resolve(label + "_core.bf16le")).take(heads * 128)
        val gate = readBf(root.resolve(label + "_gate.bf16le")).take(heads * 128)
        val got = run(d, heads, core, gate, weight, label, trace = heads == 1)
        val expected = readBf(root.resolve(label + "_recipe.bf16le")).take(heads * 128)
        assert(got == expected, "independent Python recipe mismatch")
        val native = readBf(root.resolve(label + "_official.bf16le")).take(heads * 128)
        def ordered(x: Int): Int = if ((x & 0x8000) != 0) 0x8000 - (x & 0x7fff) else 0x8000 + x
        val ulp = got.zip(native).map { case (a, b) => math.abs(ordered(a) - ordered(b)) }
        val maxAbs = got.zip(native).map { case (a, b) => math.abs(fp(a).toDouble - fp(b).toDouble) }.max
        println(s"GDN_GATED_NORM_NATIVE_DIAGNOSTIC label=$label heads=$heads values=${got.size} bit_mismatches=${got.zip(native).count { case (a, b) => a != b }} max_bf16_ulp=${ulp.max} max_abs=$maxAbs official_acceptance=UNASSIGNED")
      }
    }
  }
}
