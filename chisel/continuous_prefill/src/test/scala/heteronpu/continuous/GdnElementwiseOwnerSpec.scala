// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** Arithmetic comes from the production shared Scalar/SFU. The test supplies
  * memory only; the explicit error input tests propagation without changing bits. */
class GdnElementwiseArithmeticHarness(hiddenWidth: Int = 1024, ffnWidth: Int = 3584) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnElementwiseJob))
    val done = Decoupled(new GdnElementwiseResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val faultScalarOp = Input(UInt(4.W))
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestValid = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultValid = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnElementwiseOwner(hiddenWidth, ffnWidth))
  val scalar = Module(new BlockScalarFloat)
  val activeOp = Reg(UInt(3.W))
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  io.resetRequired := owner.io.resetRequired
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  when(scalar.io.request.fire) { activeOp := scalar.io.request.bits.op }
  owner.io.scalar.error := scalar.io.error || activeOp === io.faultScalarOp
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := scalar.io.request.bits
  io.scalarRequestValid := scalar.io.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultValid := owner.io.scalar.result.fire
}

trait GdnElementwiseTestSupport { self: ChiselScalatestTester with Matchers =>
  val aBase = BigInt("310000000", 16)
  val bBase = BigInt("320000000", 16)
  val outputBase = BigInt("330000000", 16)
  val jobTag = BigInt("deadcafe", 16)
  def bits(x: Float): Long = java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL
  def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  def bf(x: Float): Int = ((bits(x) + 0x7fffL + ((bits(x) >>> 16) & 1)) >>> 16).toInt & 65535
  def pack(xs: Seq[Int]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) { case (v, (x, i)) => v | (BigInt(x) << (16 * i)) }
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
  def reference(opcode: Int, a: Seq[Int], b: Seq[Int]): (Seq[Int], Seq[Step]) = {
    val steps = scala.collection.mutable.ArrayBuffer.empty[Step]
    def step(code: Int, x: Float, y: Float, z: Float): Float = { steps += Step(code, x, y, z); z }
    def mul(x: Float, y: Float): Float = step(ScalarOp.MulIeeeRne, x, y, (x * y).toFloat)
    def add(x: Float, y: Float): Float = step(ScalarOp.Add, x, y, (x + y).toFloat)
    val output = a.zip(b).map { case (aa, bb) =>
      val x = fp(aa); val y = fp(bb)
      if (opcode == GdnElementwiseOp.Add) bf(add(x, y)) else {
        val e = step(ScalarOp.ExpNegative, x, 0f, expRecipe(x))
        val den = add(1f, e)
        val inv = step(ScalarOp.Div, 1f, den, (1f / den).toFloat)
        val sig = mul(inv, if ((aa & 0x8000) != 0) e else 1f)
        val silu = fp(bf(mul(sig, x))) // Official BF16 activation boundary.
        bf(mul(silu, y))
      }
    }
    (output, steps.toSeq)
  }
  def init(d: GdnElementwiseArithmeticHarness): Unit = {
    d.clock.setTimeout(1000000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.faultScalarOp.poke(15.U)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: GdnElementwiseArithmeticHarness, op: Int, width: Int, tokens: Int): Unit = {
    d.io.job.bits.op.poke(op.U); d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.rowWidth.poke(width.U)
    d.io.job.bits.a.poke(aBase.U); d.io.job.bits.b.poke(bBase.U); d.io.job.bits.output.poke(outputBase.U)
    d.io.job.bits.tag.poke(jobTag.U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: GdnElementwiseArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: GdnElementwiseArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue)
  def run(d: GdnElementwiseArithmeticHarness, op: Int, width: Int, a: Seq[Int], b: Seq[Int],
          label: String, fault: String = "none", trace: Boolean = false,
          failure: Int = Status.Ok): Seq[Int] = {
    require(a.size == b.size && a.size % width == 0)
    val (gold, operations) = if (failure == Status.Ok) reference(op, a, b) else (Seq.empty[Int], Seq.empty[Step])
    def beats(base: BigInt, xs: Seq[Int], padding: Int): Map[BigInt, BigInt] = xs.grouped(32).zipWithIndex.map {
      case (v, i) => (base + i * 64) -> pack(v.padTo(32, padding))
    }.toMap
    // NaNs in read padding prove inactive lanes are not evaluated.
    val reads = beats(aBase, a, 0x7fc0) ++ beats(bBase, b, 0x7f80)
    val writes = beats(outputBase, gold, 0)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    var elapsed = 0; var issued = 0; var ackBytes = 0; var tracedRequests = 0; var tracedResults = 0; var injected = false
    def step(n: Int): Unit = {
      if (trace) for (_ <- 0 until n) {
        d.io.scalarHold.poke((elapsed % 23 < 5).B)
        if (d.io.scalarRequestValid.peek().litToBoolean) {
          val expected = operations(tracedRequests)
          d.io.scalarRequest.op.expect(expected.op.U)
          d.io.scalarRequest.a.expect(BigInt(bits(expected.a)).U); d.io.scalarRequest.b.expect(BigInt(bits(expected.b)).U)
          tracedRequests += 1
        }
        if (d.io.scalarResultValid.peek().litToBoolean) {
          d.io.scalarResult.expect(BigInt(bits(operations(tracedResults).result)).U); tracedResults += 1
        }
        d.clock.step(); elapsed += 1
      } else { d.clock.step(n); elapsed += n }
    }
    setJob(d, op, width, a.size / width); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(1); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < a.size * 250 + 10000) {
      if (!d.io.memory.valid.peek().litToBoolean) step(if (trace) 1 else 64)
      else {
        val r = request(d)
        assert(r.tag == ((jobTag << 32) | issued), "request sequence")
        val delay = 1 + issued % 5
        step(delay); assert(request(d) == r, "request changed under backpressure")
        d.io.memory.ready.poke(true.B); step(1); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == outputBase + ((a.size - 1) / 32) * 64
        val inject = !injected && (fault match {
          case "read" | "tag" => r.address == bBase
          case "final-ack" | "final-tag" => last
          case _ => false
        })
        if (inject) injected = true
        if (r.write) {
          assert(writes.contains(r.address)); assert(r.data == writes(r.address), s"recipe mismatch $label/${r.address}")
          val active = math.min(32, a.size - ((r.address - outputBase) / 2).toInt)
          assert(r.mask == (BigInt(1) << (active * 2)) - 1); assert(!committed.contains(r.address))
        } else { assert(reads.contains(r.address)); assert(r.mask == 0); assert(r.data == 0) }
        step(if (last) 37 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        d.io.response.bits.tag.poke((r.tag ^ (if (inject && fault.contains("tag")) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && !fault.contains("tag")).B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(1); d.io.response.valid.poke(false.B)
        if (r.write && !inject) { committed(r.address) = r.data; ackBytes += r.mask.bitCount }
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner timeout $label")
    val code = if (failure != Status.Ok) failure else if (fault.contains("tag")) Status.Protocol else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.tag.expect(jobTag.U); d.io.done.bits.status.expect(code.U); d.io.done.bits.writeBytes.expect(ackBytes.U)
    d.io.done.bits.outputCommitted.expect((code == Status.Ok).B); d.io.memory.valid.expect(false.B)
    if (code == Status.Ok) {
      assert(committed.toMap == writes && ackBytes == a.size * 2)
      if (trace) assert(tracedRequests == operations.size && tracedResults == operations.size)
    } else if (failure == Status.Ok) assert(injected)
    val held = completion(d); step(13); assert(completion(d) == held, "completion changed under stall")
    println(s"GDN_ELEMENTWISE_RTL label=$label op=$op width=$width tokens=${a.size / width} status=$code ack_bytes=$ackBytes cycles=${held(3)} scalar_checks=$tracedResults")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
    d.io.scalarHold.poke(false.B)
    gold
  }
  def readBf(path: java.nio.file.Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
}

class GdnElementwiseOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnElementwiseTestSupport {
  "GdnElementwiseOwner" should "preserve BF16 SiLU boundary, masked tails, faults, ACK fences and coordinated reset" in {
    test(new GdnElementwiseArithmeticHarness(35, 37)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val a = Seq.tabulate(74)(i => bf(((i % 19) - 9).toFloat / 3)).updated(0, 0).updated(1, 0x8000).updated(2, 1).updated(3, 0x8001)
        .updated(4, 1).updated(5, 0x8001).updated(6, bf(-79.5f))
      val b = Seq.tabulate(74)(i => bf(((i % 13) - 6).toFloat / 4)).updated(0, 0x8000).updated(1, 0).updated(2, 0x3f80).updated(3, 0x3f80)
        .updated(4, 1).updated(5, 0x8001)
      init(d); run(d, GdnElementwiseOp.Add, 35, a.take(35), b.take(35), "add-tail", trace = true)
      run(d, GdnElementwiseOp.SiluMul, 37, a.take(37), b.take(37), "silu-tail", trace = true)
      run(d, GdnElementwiseOp.SiluMul, 37, a, b, "silu-two-tokens", trace = true)
      run(d, GdnElementwiseOp.SiluMul, 37, a.take(37).updated(4, bf(80f)), b.take(37), "positive-exp-saturation")
      for (fault <- Seq("read", "tag", "final-ack", "final-tag")) {
        init(d); run(d, GdnElementwiseOp.Add, 35, a.take(35), b.take(35), fault, fault)
        d.clock.step(7); d.io.job.ready.expect(false.B)
      }
      for ((badA, badB, code, label) <- Seq(
        (a.take(37).updated(0, 0x7fc0), b.take(37), Status.Numerical, "nan-a"),
        (a.take(37), b.take(37).updated(0, 0x7f80), Status.Numerical, "infinite-b"),
        (a.take(37).updated(0, bf(-80f)), b.take(37), Status.Unsupported, "unsupported-negative-80"),
        (a.take(37).updated(0, bf(-100f)), b.take(37), Status.Unsupported, "unsupported-negative-100"),
        (a.take(37).updated(0, 0x7f7f), b.take(37).updated(0, 0x7f7f), Status.Numerical, "mul-overflow"))) {
        init(d); run(d, GdnElementwiseOp.SiluMul, 37, badA, badB, label, failure = code)
      }
      for ((op, width, faultOp, label) <- Seq((0, 35, ScalarOp.Add, "add-error"), (1, 37, ScalarOp.Div, "div-error"))) {
        init(d); d.io.faultScalarOp.poke(faultOp.U)
        run(d, op, width, a.take(width), b.take(width), label, failure = Status.Numerical)
      }
      // FP32 sum is finite, but its BF16 rounding would overflow.
      init(d); run(d, 0, 35, a.take(35).updated(0, 0x7f7f), b.take(35).updated(0, 0x7b00),
        "bf16-rounded-overflow", failure = Status.Numerical)
      for (bad <- 0 until 10) {
        init(d); setJob(d, 0, 35, 1)
        bad match {
          case 0 => d.io.job.bits.output.poke(aBase.U)
          case 1 => d.io.job.bits.output.poke((bBase + 64).U) // Rounded tail allocation aliases.
          case 2 => d.io.job.bits.a.poke((aBase + 2).U)
          case 3 => d.io.job.bits.tokens.poke(0.U)
          case 4 => d.io.job.bits.rowWidth.poke(37.U)
          case 5 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
          case 6 => d.io.job.bits.tokens.poke(129.U)
          case 7 => d.io.job.bits.op.poke(2.U)
          case 8 => d.io.job.bits.b.poke((BigInt(1) << 56).U)
          case 9 => d.io.job.bits.output.poke((outputBase + 2).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
        d.io.done.bits.outputCommitted.expect(false.B); d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
      }
      // An actual scalar request is outstanding when owner and shared service reset.
      init(d); setJob(d, 1, 37, 1); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      for (_ <- 0 until 2) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d); d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(0x3f00)).U); d.io.response.bits.tag.poke(r.tag.U)
        d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      while (!d.io.scalarRequestValid.peek().litToBoolean) d.clock.step()
      d.clock.step(); d.io.done.valid.expect(false.B)
      init(d); run(d, 1, 37, a.take(37), b.take(37), "reset-recovered")
    }
  }
}

class GdnElementwiseProductionSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnElementwiseTestSupport {
  "GdnElementwiseOwner production geometry" should "execute H1024 and FFN3584 using the shared scalar" in {
    test(new GdnElementwiseArithmeticHarness()).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for ((op, width) <- Seq((0, 1024), (1, 3584))) {
        val a = Seq.tabulate(width)(i => bf(((i % 43) - 21).toFloat / 8))
        val b = Seq.tabulate(width)(i => bf(((i % 31) - 15).toFloat / 7))
        run(d, op, width, a, b, s"production-$width")
      }
      sys.env.get("GDN_ELEMENTWISE_FIXTURE").foreach { directory =>
        val root = Paths.get(directory)
        def digest(raw: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(raw).map(x => f"${x & 255}%02x").mkString
        val raw = Files.readAllBytes(root.resolve("manifest.json"))
        require(digest(raw) == sys.env.getOrElse("GDN_ELEMENTWISE_MANIFEST_SHA256", ""), "fixture pin required")
        val manifest = ujson.read(new String(raw, java.nio.charset.StandardCharsets.UTF_8))
        require(manifest("model_id").str == "Qwen/Qwen3.5-0.8B" && manifest("revision").str == "2fc06364715b967f1860aea9cf38778875588b17")
        require(manifest("official_source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
        for ((file, meta) <- manifest("files").obj) {
          val data = Files.readAllBytes(root.resolve(file))
          require(data.length == meta("bytes").num && digest(data) == meta("sha256").str, s"fixture drift $file")
        }
        for (label <- Seq("cold1", "carried1"); (stage, op, width) <- Seq(("residual1", 0, 1024), ("silu_mul", 1, 3584), ("residual2", 0, 1024))) {
          def values(kind: String) = readBf(root.resolve(s"${label}_${stage}_${kind}.bf16le"))
          val got = run(d, op, width, values("a"), values("b"), s"actual-$label-$stage")
          assert(got == values("recipe"), "independent Python recipe mismatch")
          val native = values("official")
          def ordered(x: Int): Int = if ((x & 0x8000) != 0) 0x8000 - (x & 0x7fff) else 0x8000 + x
          val ulp = got.zip(native).map { case (a, b) => math.abs(ordered(a) - ordered(b)) }
          println(s"GDN_ELEMENTWISE_NATIVE_DIAGNOSTIC case=$label stage=$stage values=${got.size} bit_mismatches=${got.zip(native).count { case (a, b) => a != b }} max_bf16_ulp=${ulp.max} official_acceptance=UNASSIGNED")
        }
      }
    }
  }
}
