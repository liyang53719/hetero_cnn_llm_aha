// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}
import scala.sys.process._

/** Arithmetic comes from the production shared Scalar/SFU. The test supplies
  * memory only; the explicit error input tests propagation without changing bits. */
class AttentionSigmoidArithmeticHarness(hiddenWidth: Int = 1024, ffnWidth: Int = 3584,
                                        attentionWidth: Int = 2048) extends Module {
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
  val owner = Module(new GdnElementwiseOwner(hiddenWidth, ffnWidth, attentionWidth = attentionWidth, enableAttentionSigmoidMul = true))
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

trait AttentionSigmoidTestSupport { self: ChiselScalatestTester with Matchers =>
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
  lazy val oracle = {
    val supplied = sys.env.get("ATTENTION_SIGMOID_FIXED_VECTORS")
    require(supplied.isDefined == sys.env.contains("ATTENTION_SIGMOID_FIXED_SHA256"), "supply both vector path and hash")
    val raw = supplied.map(p => Files.readAllBytes(Paths.get(p))).getOrElse {
      // General CI discovers every Spec without model fixtures. Regenerate the
      // same synthetic integer-reference vectors in memory, never from goldens.
      val root = Iterator.iterate(Paths.get("").toAbsolutePath)(_.getParent).takeWhile(_ != null)
        .find(p => Files.isRegularFile(p.resolve("chisel/continuous_prefill/scripts/attention_sigmoid_reference.py")))
        .getOrElse(throw new IllegalArgumentException("repository sigmoid reference required"))
      val code = "import json,sys;sys.path.insert(0,sys.argv[1]);import attention_sigmoid_reference as ref;print(json.dumps(ref.manifest(),indent=2))"
      Seq(sys.env.getOrElse("ATTENTION_SIGMOID_PYTHON","python3"), "-c", code,
        root.resolve("chisel/continuous_prefill/scripts").toString).!!.getBytes(java.nio.charset.StandardCharsets.UTF_8)
    }
    val sha = java.security.MessageDigest.getInstance("SHA-256").digest(raw).map(x => f"${x & 255}%02x").mkString
    require(sha == sys.env.getOrElse("ATTENTION_SIGMOID_FIXED_SHA256", "40254ca4fffe28d430e755109ee0c4b640b9b3606801fe9ee3b5526b74274779"), "fixed-vector pin required")
    val data = ujson.read(new String(raw, java.nio.charset.StandardCharsets.UTF_8))
    require(data("official_source_sha256").str == "aac2a1bcca88829afc6dbdf83f97155ebf64d800ee9d703af3802a9aebcfcd18")
    data("values").arr.toSeq
  }
  def reference(opcode: Int, a: Seq[Int], b: Seq[Int]): (Seq[Int], Seq[Step]) = {
    val steps = scala.collection.mutable.ArrayBuffer.empty[Step]
    def step(code: Int, x: Float, y: Float, z: Float): Float = { steps += Step(code, x, y, z); z }
    def mul(x: Float, y: Float): Float = step(ScalarOp.MulIeeeRne, x, y, (x * y).toFloat)
    def add(x: Float, y: Float): Float = step(ScalarOp.Add, x, y, (x + y).toFloat)
    val output = a.zip(b).map { case (aa, bb) =>
      val x = fp(aa); val y = fp(bb)
      if (opcode == GdnElementwiseOp.Add) bf(add(x, y))
      else if (opcode == GdnElementwiseOp.SigmoidMul) {
        val row = oracle.find(v => v("gate").num.toInt == aa && v("context").num.toInt == bb).get
        def raw(v: ujson.Value): Float = java.lang.Float.intBitsToFloat(v.num.toLong.toInt)
        row("steps").arr.foreach(v => steps += Step(v("op").num.toInt, raw(v("a")), raw(v("b")), raw(v("result"))))
        row("output").num.toInt
      } else {
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
  def init(d: AttentionSigmoidArithmeticHarness): Unit = {
    d.clock.setTimeout(1000000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.faultScalarOp.poke(15.U)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: AttentionSigmoidArithmeticHarness, op: Int, width: Int, tokens: Int): Unit = {
    d.io.job.bits.op.poke(op.U); d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.rowWidth.poke(width.U)
    d.io.job.bits.a.poke(aBase.U); d.io.job.bits.b.poke(bBase.U); d.io.job.bits.output.poke(outputBase.U)
    d.io.job.bits.tag.poke(jobTag.U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: AttentionSigmoidArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: AttentionSigmoidArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue)
  def run(d: AttentionSigmoidArithmeticHarness, op: Int, width: Int, a: Seq[Int], b: Seq[Int],
          label: String, fault: String = "none", trace: Boolean = false,
          failure: Int = Status.Ok, validPrefix: Int = 0): Seq[Int] = {
    require(a.size == b.size && a.size % width == 0)
    val (gold, operations) = if (failure == Status.Ok) reference(op, a, b) else if (validPrefix > 0) reference(op, a.take(validPrefix), b.take(validPrefix)) else (Seq.empty[Int], Seq.empty[Step])
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
          assert(r.mask == (BigInt(1) << (active * 2)) - 1)
          assert(r.mask != 0 && (r.mask & ((r.mask + 1) & ((BigInt(1) << 64) - 1))) == 0, "production iDMA low-contiguous mask"); assert(!committed.contains(r.address))
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
    println(s"ATTENTION_SIGMOID_RTL label=$label op=$op width=$width tokens=${a.size / width} status=$code ack_bytes=$ackBytes cycles=${held(3)} scalar_checks=$tracedResults")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
    d.io.scalarHold.poke(false.B)
    gold
  }
  def readBf(path: java.nio.file.Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
}

class AttentionSigmoidOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with AttentionSigmoidTestSupport {
  "GdnElementwiseOwner SigmoidMul" should "use the shared scalar, retain old recipes and fence every result" in {
    test(new AttentionSigmoidArithmeticHarness(33, 37, 35)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val gate = oracle.map(_("gate").num.toInt)
      val context = oracle.map(_("context").num.toInt)
      val oldA = Seq.tabulate(74)(i => bf(((i % 19) - 9).toFloat / 3))
        .updated(0, 0).updated(1, 0x8000).updated(2, 1).updated(3, 0x8001).updated(6, bf(-79.5f))
      val oldB = Seq.tabulate(74)(i => bf(((i % 13) - 6).toFloat / 4))
        .updated(0, 0x8000).updated(1, 0).updated(2, 0x3f80).updated(3, 0x3f80)
      init(d)
      run(d, GdnElementwiseOp.Add, 33, oldA.take(33), oldB.take(33), "legacy-add", trace = true)
      run(d, GdnElementwiseOp.SiluMul, 37, oldA.take(37), oldB.take(37), "legacy-silu", trace = true)
      run(d, GdnElementwiseOp.SigmoidMul, 35, gate.take(35), context.take(35), "sigmoid-tail", trace = true)
      run(d, GdnElementwiseOp.SigmoidMul, 35, gate, context, "sigmoid-two-tokens", trace = true)
      // Immediate reuse in both directions detects operation/intermediate leakage.
      run(d, GdnElementwiseOp.SiluMul, 37, oldA.take(37), oldB.take(37), "legacy-silu-after-sigmoid", trace = true)
      run(d, GdnElementwiseOp.Add, 33, oldA.take(33), oldB.take(33), "legacy-add-after-sigmoid", trace = true)
      for (fault <- Seq("read", "tag", "final-ack", "final-tag")) {
        init(d); run(d, GdnElementwiseOp.SigmoidMul, 35, gate, context, fault, fault)
        d.clock.step(7); d.io.job.ready.expect(false.B); d.io.memory.valid.expect(false.B)
      }
      for ((badA, badB, code, label, prefix) <- Seq(
        (gate.updated(0, 0x7fc0), context, Status.Numerical, "nan-gate", 0),
        (gate, context.updated(0, 0x7f80), Status.Numerical, "infinite-context", 0),
        (gate.updated(0, bf(-80f)), context, Status.Unsupported, "negative-80", 0),
        (gate.updated(0, bf(-100f)), context, Status.Unsupported, "negative-100", 0),
        (gate.updated(33, bf(-80f)), context, Status.Unsupported, "late-unsupported-staging-uncommitted", 32),
        (gate, context.updated(33, 0xff80), Status.Numerical, "late-infinite-staging-uncommitted", 32))) {
        init(d); run(d, GdnElementwiseOp.SigmoidMul, 35, badA, badB, label, failure = code, validPrefix = prefix)
      }
      for (faultOp <- Seq(ScalarOp.ExpNegative, ScalarOp.Add, ScalarOp.Div, ScalarOp.MulIeeeRne)) {
        init(d); d.io.faultScalarOp.poke(faultOp.U)
        run(d, GdnElementwiseOp.SigmoidMul, 35, gate.take(35), context.take(35), s"scalar-$faultOp-error", failure = Status.Numerical)
      }
      for ((op, width, faultOp) <- Seq((0, 33, ScalarOp.Add), (1, 37, ScalarOp.Div))) {
        init(d); d.io.faultScalarOp.poke(faultOp.U)
        run(d, op, width, oldA.take(width), oldB.take(width), "legacy-scalar-error", failure = Status.Numerical)
      }
      init(d); run(d, 1, 37, oldA.take(37).updated(0, bf(-80f)), oldB.take(37),
        "legacy-negative-80", failure = Status.Unsupported)
      init(d); run(d, 0, 33, oldA.take(33).updated(0, 0x7f7f), oldB.take(33).updated(0, 0x7b00),
        "legacy-bf16-overflow", failure = Status.Numerical)
      for (bad <- 0 until 13) {
        init(d); setJob(d, GdnElementwiseOp.SigmoidMul, 35, 1)
        bad match {
          case 0 => d.io.job.bits.output.poke(aBase.U)
          case 1 => d.io.job.bits.output.poke((bBase + 64).U)
          case 2 => d.io.job.bits.a.poke((aBase + 2).U)
          case 3 => d.io.job.bits.tokens.poke(0.U)
          case 4 => d.io.job.bits.rowWidth.poke(33.U)
          case 5 => d.io.job.bits.rowWidth.poke(37.U)
          case 6 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
          case 7 => d.io.job.bits.tokens.poke(129.U)
          case 8 => d.io.job.bits.op.poke(3.U)
          case 9 => d.io.job.bits.b.poke((BigInt(1) << 56).U)
          case 10 => d.io.job.bits.output.poke((outputBase + 2).U)
          case 11 => d.io.job.bits.a.poke(((BigInt(1) << 56) - 64).U)
          case 12 => d.io.job.bits.b.poke((bBase + 2).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
        d.io.done.bits.writeBytes.expect(0.U); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
        d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
        d.clock.step(3); d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B)
      }
      // Coordinate owner and service reset with an actual scalar request in flight.
      init(d); setJob(d, GdnElementwiseOp.SigmoidMul, 35, 1)
      d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      for (values <- Seq(gate, context)) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d); d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(values.take(32)).U); d.io.response.bits.tag.poke(r.tag.U)
        d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      while (!d.io.scalarRequestValid.peek().litToBoolean) d.clock.step()
      d.clock.step(); d.io.done.valid.expect(false.B)
      init(d); run(d, GdnElementwiseOp.SigmoidMul, 35, gate.take(35), context.take(35), "reset-recovered", trace = true)
    }
  }
}
