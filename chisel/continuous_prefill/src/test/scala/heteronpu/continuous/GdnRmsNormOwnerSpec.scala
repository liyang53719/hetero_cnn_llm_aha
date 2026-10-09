// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** Arithmetic is produced by the production shared Scalar, not a test oracle. */
class GdnRmsNormArithmeticHarness(width: Int) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnRmsNormJob))
    val done = Decoupled(new GdnRmsNormResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val injectScalarError = Input(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestValid = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultValid = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnRmsNormOwner(width))
  val scalar = Module(new BlockScalarFloat)
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  io.resetRequired := owner.io.resetRequired
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error || io.injectScalarError
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := scalar.io.request.bits
  io.scalarRequestValid := scalar.io.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultValid := owner.io.scalar.result.fire
}

trait GdnRmsNormTestSupport { self: ChiselScalatestTester with Matchers =>
  val inputBase = BigInt("310000000", 16)
  val weightBase = BigInt("320000000", 16)
  val outputBase = BigInt("330000000", 16)
  val fullMask = (BigInt(1) << 64) - 1
  def bits(x: Float): Long = java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL
  def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  def bf(x: Float): Int = ((bits(x) + 0x7fffL + ((bits(x) >>> 16) & 1)) >>> 16).toInt & 65535
  def pack(xs: Seq[BigInt], width: Int = 16): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (v, (x, i)) => v | (x << (width * i))
  }
  case class Step(op: Int, a: Float, b: Float, result: Float)
  def reference(hidden: Seq[Int], weight: Seq[Int]): (Seq[Int], Seq[Step]) = {
    val width = weight.size
    require(hidden.size % width == 0)
    val steps = scala.collection.mutable.ArrayBuffer.empty[Step]
    val output = scala.collection.mutable.ArrayBuffer.empty[Int]
    def op(code: Int, a: Float, b: Float, result: Float): Float = {
      steps += Step(code, a, b, result); result
    }
    def mul(a: Float, b: Float): Float = op(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
    def add(a: Float, b: Float): Float = op(ScalarOp.Add, a, b, (a + b).toFloat)
    for (row <- hidden.indices by width) {
      var sum = 0f
      for (lane <- 0 until width) sum = add(sum, mul(fp(hidden(row + lane)), fp(hidden(row + lane))))
      val variance = add(mul(sum, 1f / width), 1e-6f)
      val root = op(ScalarOp.Sqrt, variance, 0f, math.sqrt(variance.toDouble).toFloat)
      val inverse = op(ScalarOp.Div, 1f, root, (1f / root).toFloat)
      for (lane <- 0 until width) {
        val normalized = mul(fp(hidden(row + lane)), inverse)
        val offset = add(1f, fp(weight(lane)))
        output += bf(mul(normalized, offset))
      }
    }
    (output.toSeq, steps.toSeq)
  }
  def init(d: GdnRmsNormArithmeticHarness): Unit = {
    d.clock.setTimeout(250000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.injectScalarError.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: GdnRmsNormArithmeticHarness, width: Int, tokens: Int): Unit = {
    d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.hiddenWidth.poke(width.U)
    d.io.job.bits.input.poke(inputBase.U); d.io.job.bits.weight.poke(weightBase.U)
    d.io.job.bits.output.poke(outputBase.U); d.io.job.bits.tag.poke("h89abcdef".U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: GdnRmsNormArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: GdnRmsNormArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue)

  def run(d: GdnRmsNormArithmeticHarness, hidden: Seq[Int], weight: Seq[Int], label: String,
          fault: String = "none", trace: Boolean = false, numerical: Boolean = false): Seq[Int] = {
    d.io.scalarHold.poke(false.B)
    d.io.injectScalarError.poke((fault == "scalar").B)
    val width = weight.size; val tokens = hidden.size / width
    val (gold, operations) = if (numerical || fault == "scalar") (Seq.empty[Int], Seq.empty[Step]) else reference(hidden, weight)
    def beats(base: BigInt, xs: Seq[Int]): Map[BigInt, BigInt] = xs.grouped(32).zipWithIndex.map {
      case (values, index) => (base + index * 64) -> pack(values.map(BigInt(_)))
    }.toMap
    val reads = beats(inputBase, hidden) ++ beats(weightBase, weight)
    val writes = beats(outputBase, gold)
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
    setJob(d, width, tokens); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(1); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < hidden.size * 150 + 30000) {
      if (!d.io.memory.valid.peek().litToBoolean) step(if (trace) 1 else 64)
      else {
        val r = request(d)
        assert(r.tag == ((BigInt("89abcdef", 16) << 32) | issued), "request sequence")
        val delay = 1 + issued % 5
        step(delay); assert(request(d) == r, "memory request changed under backpressure")
        d.io.memory.ready.poke(true.B); step(1); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == outputBase + hidden.size * 2 - 64
        val inject = !injected && (fault match {
          case "read" | "tag" => !r.write
          case "write" => r.write
          case "final-ack" | "final-tag" => last
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
        val wrongTag = inject && (fault == "tag" || fault == "final-tag")
        d.io.response.bits.tag.poke((r.tag ^ (if (wrongTag) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && !wrongTag).B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(1); d.io.response.valid.poke(false.B)
        if (r.write && !inject) { committed(r.address) = r.data; acked += 1 }
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner timeout $label")
    val code = if (numerical || fault == "scalar") Status.Numerical else if (fault == "tag" || fault == "final-tag") Status.Protocol else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.status.expect(code.U); d.io.done.bits.tag.expect("h89abcdef".U)
    d.io.done.bits.writeBytes.expect((acked * 64).U); d.io.done.bits.outputCommitted.expect((code == Status.Ok).B)
    d.io.memory.valid.expect(false.B)
    if (code == Status.Ok) {
      assert(committed.toMap == writes)
      assert(issued == weight.size / 32 + 2 * hidden.size / 32, "weights must be read exactly once per job")
      if (trace) assert(tracedRequests == operations.size && tracedResults == operations.size)
    } else if (!numerical && fault != "scalar") assert(injected)
    val held = completion(d); step(13); assert(completion(d) == held, "completion changed under backpressure")
    println(s"GDN_RMSNORM_RTL label=$label width=$width tokens=$tokens status=$code ack_bytes=${acked * 64} cycles=${held(3)} scalar_checks=$tracedResults")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
    gold
  }
  def exerciseContracts(d: GdnRmsNormArithmeticHarness, width: Int): Unit = {
      val hidden = Seq.tabulate(width)(i => bf((-1.37 + i * .097).toFloat)).updated(0, 0).updated(1, 0x8000).updated(2, 1).updated(3, 0x8001)
      val weight = Seq.tabulate(width)(i => bf((-.63 + i * .051).toFloat)).updated(4, bf(-1f)).updated(5, bf(-2f))
      init(d); run(d, hidden, weight, "FP32-nodes-final-only-BF16", trace = width == 32)
      run(d, hidden ++ hidden.reverse, weight, "two-token-shared-weight", trace = width == 32)
      for (fault <- Seq("read", "tag", "write", "final-ack", "final-tag", "scalar")) {
        init(d); run(d, hidden ++ hidden.reverse, weight, fault, fault)
        d.clock.step(7); d.io.job.ready.expect(false.B)
      }
      for ((badHidden, badWeight, label) <- Seq(
        (hidden.updated(0, 0x7fc0), weight, "nan-hidden"),
        (hidden.updated(0, 0x7f80), weight, "infinite-hidden"),
        (hidden.updated(0, 0x7f7f), weight, "square-overflow"),
        (hidden, weight.updated(0, 0x7fc0), "nan-weight"),
        (hidden, weight.updated(0, 0x7f80), "infinite-weight"))) {
        init(d); run(d, badHidden, badWeight, label, numerical = true)
      }
      for (bad <- 0 until 10) {
        init(d); setJob(d, width, 2)
        bad match {
          case 0 => d.io.job.bits.output.poke(inputBase.U)
          case 1 => d.io.job.bits.output.poke(weightBase.U)
          case 2 => d.io.job.bits.input.poke((inputBase + 2).U)
          case 3 => d.io.job.bits.weight.poke((weightBase + 2).U)
          case 4 => d.io.job.bits.tokens.poke(0.U)
          case 5 => d.io.job.bits.hiddenWidth.poke((width + 32).U)
          case 6 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
          case 7 => d.io.job.bits.tokens.poke(129.U)
          case 8 => d.io.job.bits.input.poke(((BigInt(1) << 56) - 64).U)
          case 9 => d.io.job.bits.output.poke((inputBase + 64).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
        d.io.done.bits.outputCommitted.expect(false.B); d.io.memory.valid.expect(false.B)
        d.io.scalarRequestValid.expect(false.B)
      }
      // Reset while a memory read is awaiting response.
      init(d); setJob(d, width, 1); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
      d.io.response.ready.expect(true.B)
      init(d); run(d, hidden, weight, "memory-reset-recovered")
      // Reset the owner and shared Scalar together while arithmetic is in flight.
      init(d); setJob(d, width, 1); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      for (_ <- 0 until (2 * width / 32)) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d); assert(!r.write)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(BigInt(0x3f00))).U)
        d.io.response.bits.tag.poke(r.tag.U); d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.io.scalarRequestValid.expect(true.B); d.clock.step(); d.io.done.valid.expect(false.B)
      init(d); run(d, hidden, weight, "scalar-reset-recovered", trace = width == 32)
  }
  def readBf(path: java.nio.file.Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
}

class GdnRmsNormOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnRmsNormTestSupport {
  "GdnRmsNormOwner" should "preserve original BF16 zero-centered weights, FP32 nodes, stalls, ACK fences and reset" in {
    test(new GdnRmsNormArithmeticHarness(32)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      exerciseContracts(d, 32)
    }
  }
}

/** Same real input bytes feed native and frozen recipes; no native tolerance
  * is introduced. Width1024 actual input and post RMSNorm M1 cold/carried gate. */
class GdnRmsNormRealSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnRmsNormTestSupport {
  "GdnRmsNormOwner real layer0" should "execute input and post normalization at authentic width1024" in {
    val root = Paths.get(sys.env.getOrElse("GDN_RMSNORM_FIXTURE", throw new IllegalArgumentException("GDN_RMSNORM_FIXTURE required")))
    def digest(a: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(a).map(x => f"${x & 255}%02x").mkString
    val raw = Files.readAllBytes(root.resolve("manifest.json"))
    require(digest(raw) == sys.env.getOrElse("GDN_RMSNORM_MANIFEST_SHA256", ""), "fixture manifest pin required")
    val manifest = ujson.read(new String(raw, java.nio.charset.StandardCharsets.UTF_8))
    require(manifest("model_id").str == "Qwen/Qwen3.5-0.8B" && manifest("revision").str == "2fc06364715b967f1860aea9cf38778875588b17")
    require(manifest("official_source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
    require(manifest("width").num == 1024 && manifest("token_ids").arr.map(_.num.toInt).toSeq == Seq(19, 92))
    for ((file, metadata) <- manifest("files").obj) {
      val bytes = Files.readAllBytes(root.resolve(file))
      require(bytes.length == metadata("bytes").num && digest(bytes) == metadata("sha256").str, s"fixture drift $file")
    }
    val pins = Map("input" -> "032420ad60956b0e62b5f4afbfc3a51a7148c79946f746ea4eb6b0ceb6c67e37",
      "post" -> "9c5f1eafa39cd5af93a2f9fadafd3362bc886938ab1a1db3954baea7887fe303")
    test(new GdnRmsNormArithmeticHarness(1024)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      exerciseContracts(d, 1024)
      init(d)
      for (name <- Seq("input", "post"); label <- Seq("cold1", "carried1")) {
        val weightPath = root.resolve(s"${name}_weight.bf16le")
        require(digest(Files.readAllBytes(weightPath)) == pins(name), "original BF16 weight pin required")
        val hidden = readBf(root.resolve(s"${name}_${label}_hidden.bf16le"))
        val weight = readBf(weightPath)
        require(hidden.size == 1024 && weight.size == 1024)
        val got = run(d, hidden, weight, s"$name-$label", trace = sys.env.get("GDN_RMSNORM_TRACE").contains("1"))
        val expected = readBf(root.resolve(s"${name}_${label}_recipe.bf16le"))
        val native = readBf(root.resolve(s"${name}_${label}_official.bf16le"))
        assert(got == expected, "independent Python recipe mismatch")
        def ordered(x: Int): Int = if ((x & 0x8000) != 0) 0x8000 - (x & 0x7fff) else 0x8000 + x
        val ulp = got.zip(native).map { case (a, b) => math.abs(ordered(a) - ordered(b)) }
        val bitMismatches = got.zip(native).count { case (a, b) => a != b }
        val numericMismatches = ulp.count(_ != 0)
        val maxAbs = got.zip(native).map { case (a, b) => math.abs(fp(a).toDouble - fp(b).toDouble) }.max
        println(s"GDN_RMSNORM_NATIVE_DIAGNOSTIC label=$name-$label values=${got.size} bit_mismatches=$bitMismatches numeric_mismatches=$numericMismatches signed_zero_only=${bitMismatches - numericMismatches} max_bf16_ulp=${ulp.max} max_abs=$maxAbs official_acceptance=UNASSIGNED")
      }
    }
  }
}
