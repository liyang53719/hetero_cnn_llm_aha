// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** Real production shared arithmetic. The test supplies only memory transport. */
class GdnInputPrepHarness(heads: Int) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnInputPrepJob))
    val done = Decoupled(new GdnInputPrepResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val scalarError = Input(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestValid = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultValid = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnInputPrepOwner(heads))
  val scalar = Module(new BlockScalarFloat(enableSoftplus = true))
  owner.io.job <> io.job; io.done <> owner.io.done
  io.memory <> owner.io.memory; owner.io.response <> io.response
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error || io.scalarError
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := owner.io.scalar.request.bits
  io.scalarRequestValid := owner.io.scalar.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultValid := owner.io.scalar.result.fire
  io.resetRequired := owner.io.resetRequired
}

trait GdnInputPrepSupport { self: ChiselScalatestTester with Matchers =>
  val base: Seq[BigInt] = (0 until 11).map(i => BigInt("310000000", 16) + i * 0x100000)
  def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  def fp(x: Int): Float = java.lang.Float.intBitsToFloat(x << 16)
  def bf(x: Float): Int = ((bits(x).toLong + 0x7fff + ((bits(x).toLong >>> 16) & 1)) >>> 16).toInt & 65535
  def pack(xs: Seq[BigInt], width: Int): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) { case (v, (x, i)) => v | (x << (width * i)) }
  def exp(x: Float): Float = {
    if (math.abs(x) >= 80f) 0f else {
      val scaled = (math.abs(x) * (1 / math.log(2)).toFloat).toFloat
      val k = scaled.toInt; val fraction = (scaled - k.toFloat).toFloat
      val c = (0 to 7).map(i => (math.pow(-math.log(2), i) / (if (i == 0) 1.0 else (1 to i).map(_.toDouble).product)).toFloat)
      var h = c(7)
      for (i <- 6 to 0 by -1) h = ((h * fraction).toFloat + c(i)).toFloat
      (h * java.lang.Float.intBitsToFloat((127 - k) << 23)).toFloat
    }
  }
  def softplus(x: Float): Float = {
    if (x > 20f) x else {
      val e = exp(x); val y = (e / (2f + e).toFloat).toFloat; val z = (y * y).toFloat
      var h = (1.0 / 15).toFloat
      for (denom <- Seq(13, 11, 9, 7, 5, 3, 1)) h = ((h * z).toFloat + (1.0 / denom).toFloat).toFloat
      (math.max(x, 0f) + ((2f * y).toFloat * h).toFloat).toFloat
    }
  }
  case class Inputs(q: Seq[Int], k: Seq[Int], v: Seq[Int], a: Seq[Int], b: Seq[Int], aLog: Seq[Float], bias: Seq[Int]) { def heads: Int = a.size }
  case class Step(op: Int, a: Float, b: Float, out: Float)
  def reference(in: Inputs, recurrent: Boolean): (Map[BigInt, BigInt], Seq[Step]) = {
    val writes = scala.collection.mutable.Map.empty[BigInt, BigInt]
    val operations = scala.collection.mutable.ArrayBuffer.empty[Step]
    def op(code: Int, a: Float, b: Float, out: Float): Float = { operations += Step(code, a, b, out); out }
    def mul(a: Float, b: Float): Float = op(ScalarOp.MulIeeeRne, a, b, (a * b).toFloat)
    def add(a: Float, b: Float): Float = op(ScalarOp.Add, a, b, (a + b).toFloat)
    def div(a: Float, b: Float): Float = op(ScalarOp.Div, a, b, (a / b).toFloat)
    def store(address: BigInt, xs: Seq[Float]): Unit = xs.grouped(16).zipWithIndex.foreach { case (v, i) => writes(address + i * 64) = pack(v.map(bits), 32) }
    for (head <- 0 until in.heads) {
      for ((raw, role) <- Seq(in.q, in.k).zipWithIndex) {
        val x = raw.slice(head * 128, (head + 1) * 128).map(fp)
        var acc = 0f
        for (v <- x) acc = add(acc, mul(v, v))
        val eps = add(acc, 1e-6f)
        val root = op(ScalarOp.Sqrt, eps, 0f, math.sqrt(eps.toDouble).toFloat)
        val inv = div(1f, root)
        val out = x.map { v =>
          val normalized = mul(v, inv)
          if (role == 1) normalized else if (recurrent) div(normalized, math.sqrt(128).toFloat) else mul(normalized, (1 / math.sqrt(128)).toFloat)
        }
        store(base(7 + role) + head * 512, out)
      }
      store(base(9) + head * 512, in.v.slice(head * 128, (head + 1) * 128).map(fp))
      val y = add(fp(in.a(head)), fp(in.bias(head)))
      val soft = op(ScalarOp.Softplus, y, 0f, softplus(y))
      val e = op(ScalarOp.ExpNegative, in.aLog(head), 0f, exp(in.aLog(head)))
      val aExp = if ((bits(in.aLog(head)) & BigInt("80000000", 16)) != 0) e else div(1f, e)
      val g = mul(-aExp, soft)
      val b = fp(in.b(head))
      val eb = op(ScalarOp.ExpNegative, b, 0f, exp(b))
      val inv = div(1f, add(1f, eb))
      val beta = fp(bf(mul(inv, if ((bits(b) & BigInt("80000000", 16)) != 0) eb else 1f)))
      store(base(10) + head * 64, Seq(g, beta) ++ Seq.fill(14)(0f))
    }
    (writes.toMap, operations.toSeq)
  }
  def init(d: GdnInputPrepHarness): Unit = {
    // A complete 128-lane norm legitimately has more than 1000 cycles between
    // external memory handshakes. The run loop retains its explicit watchdog.
    d.clock.setTimeout(100000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B); d.io.memory.ready.poke(false.B)
    d.io.response.valid.poke(false.B); d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.scalarError.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: GdnInputPrepHarness, heads: Int, recurrent: Boolean): Unit = {
    val j = d.io.job.bits
    j.tokens.poke(1.U); j.heads.poke(heads.U); j.recurrentMode.poke(recurrent.B); j.tag.poke("h35012807".U)
    Seq(j.queryIn, j.keyIn, j.valueIn, j.ab, j.aLog, j.dtBias, j.query, j.key, j.value, j.gates).zip(Seq(0,1,2,3,5,6,7,8,9,10).map(i => base(i))).foreach { case (p, v) => p.poke(v.U) }
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: GdnInputPrepHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean, d.io.memory.bits.address.peek().litValue,
    d.io.memory.bits.data.peek().litValue, d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def run(d: GdnInputPrepHarness, in: Inputs, recurrent: Boolean, label: String, fault: String = "none", trace: Boolean = false): Unit = {
    val (expected, operations) = reference(in, recurrent)
    def beats(addr: BigInt, xs: Seq[BigInt], width: Int): Map[BigInt, BigInt] = xs.grouped(512 / width).zipWithIndex.map { case (x, i) => (addr + i * 64) -> pack(x, width) }.toMap
    val reads = beats(base(0), in.q.map(BigInt(_)), 16) ++ beats(base(1), in.k.map(BigInt(_)), 16) ++ beats(base(2), in.v.map(BigInt(_)), 16) ++
      Map(base(3) -> pack((in.a.padTo(16, 0) ++ in.b.padTo(16, 0)).map(BigInt(_)), 16), base(5) -> pack(in.aLog.map(bits), 32), base(6) -> pack(in.bias.map(BigInt(_)), 16))
    val written = scala.collection.mutable.Map.empty[BigInt, BigInt]
    var cycle = 0; var sequence = 0; var scalarIn = 0; var scalarOut = 0; var injected = false
    def step(n: Int = 1): Unit = for (_ <- 0 until n) {
      d.io.scalarHold.poke((trace && cycle % 23 < 5).B)
      if (trace && d.io.scalarRequestValid.peek().litToBoolean) {
        val e = operations(scalarIn)
        d.io.scalarRequest.op.expect(e.op.U); d.io.scalarRequest.a.expect(bits(e.a).U); d.io.scalarRequest.b.expect(bits(e.b).U); scalarIn += 1
      }
      if (trace && d.io.scalarResultValid.peek().litToBoolean) { d.io.scalarResult.expect(bits(operations(scalarOut).out).U); scalarOut += 1 }
      d.clock.step(); cycle += 1
    }
    setJob(d, in.heads, recurrent); d.io.job.valid.poke(true.B); d.io.job.ready.expect(true.B); step(); d.io.job.valid.poke(false.B)
    d.io.scalarError.poke((fault == "scalar").B)
    while (!d.io.done.valid.peek().litToBoolean && cycle < in.heads * 45000) {
      if (!d.io.memory.valid.peek().litToBoolean) step()
      else {
        val r = request(d); assert(r.tag == ((BigInt("35012807", 16) << 32) | sequence))
        step(2 + sequence % 3); assert(request(d) == r, "unstable memory request")
        d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == base(10) + (in.heads - 1) * 64
        val inject = !injected && ((fault == "read" || fault == "tag") && !r.write || fault == "final-ack" && last)
        if (inject) injected = true
        if (r.write) { assert(expected(r.address) == r.data, s"$label output mismatch ${r.address}"); assert(r.mask == (BigInt(1) << 64) - 1); assert(!written.contains(r.address)) }
        else { assert(reads.contains(r.address)); assert(r.mask == 0) }
        step(if (last) 31 else 2)
        d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        d.io.response.bits.tag.poke((r.tag ^ (if (inject && fault == "tag") BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && fault != "tag").B); d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(); d.io.response.valid.poke(false.B)
        if (r.write && !inject) written(r.address) = r.data
        sequence += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"$label timeout")
    val status = fault match { case "none" => Status.Ok; case "tag" => Status.Protocol; case "scalar" | "numerical" => Status.Numerical; case _ => Status.Memory }
    d.io.done.bits.status.expect(status.U); d.io.done.bits.outputCommitted.expect((status == Status.Ok).B)
    d.io.done.bits.writeBytes.expect((written.size * 64).U)
    def completion = Seq(d.io.done.bits.tag.peek().litValue, d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue, d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue)
    val held = completion; step(11); assert(completion == held)
    if (status == Status.Ok) { assert(written.toMap == expected); if (trace) { assert(scalarIn == operations.size); assert(scalarOut == operations.size) } }
    println(s"GDN_INPUT_PREP_RTL label=$label heads=${in.heads} recurrent=$recurrent status=$status bytes=${written.size * 64} scalar_checks=$scalarOut cycles=$cycle")
    d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((status == Status.Ok).B); d.io.resetRequired.expect((status != Status.Ok).B)
  }
}

class GdnInputPrepOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnInputPrepSupport {
  "GdnInputPrepOwner" should "execute shared arithmetic with explicit dtype policy and fail closed at transaction boundaries" in {
    test(new GdnInputPrepHarness(1)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val rng = new scala.util.Random(350128)
      def vector = Seq.fill(128)(bf((rng.nextDouble() * 2 - 1).toFloat)).updated(0, 0x8000).updated(1, 0)
      val in = Inputs(vector, vector, vector, Seq(bf(-1.25f)), Seq(bf(-.625f)), Seq(.423789f), Seq(bf(-.523f)))
      init(d); run(d, in, false, "cold-chunk-bitexact", trace = true)
      run(d, in, true, "carried-decode-bitexact", trace = true)
      for (fault <- Seq("read", "tag", "final-ack", "scalar")) { init(d); run(d, in, false, fault, fault) }
      for ((badInput, label) <- Seq(
        (in.copy(q = in.q.updated(0, 0x7fc0)), "nan-query"),
        (in.copy(v = in.v.updated(0, 0x7f80)), "infinite-value"),
        (in.copy(b = Seq(bf(-80f))), "beta-exp-domain"),
        (in.copy(aLog = Seq(80f)), "Alog-exp-domain"),
        (in.copy(a = Seq(bf(100f))), "recurrent-g-domain"),
        (in.copy(a = Seq(bf(-100f))), "softplus-unsupported-legal-range"))) {
        init(d); run(d, badInput, false, label, "numerical")
      }
      init(d); run(d, in.copy(q = Seq.fill(128)(0).updated(0, 0x8000)), false, "zero-head-epsilon", trace = true)
      for (bad <- 0 until 6) {
        init(d); setJob(d, 1, false)
        bad match {
          case 0 => d.io.job.bits.query.poke(base(0).U)
          case 1 => d.io.job.bits.key.poke(base(7).U)
          case 2 => d.io.job.bits.aLog.poke((base(5) + 4).U)
          case 3 => d.io.job.bits.tokens.poke(128.U)
          case 4 => d.io.job.bits.heads.poke(2.U)
          case _ => d.io.job.bits.gates.poke(((BigInt(1) << 56) - 32).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U); d.io.memory.valid.expect(false.B)
        d.io.done.bits.outputCommitted.expect(false.B)
      }
      // Reset during an outstanding memory response must clear ownership. The
      // test resets the whole service/transport, never delivers a stale reply.
      init(d); setJob(d, 1, false); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
      d.io.response.ready.expect(true.B); init(d); d.io.response.ready.expect(false.B); d.io.job.ready.expect(true.B)
      run(d, in.copy(aLog = Seq(-.123789f)), false, "reset-reuse-negative-Alog")
    }
  }
}

class GdnInputPrepActualSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnInputPrepSupport {
  "GdnInputPrepOwner actual head" should "consume bounded verified checkpoint-conditioned stage inputs through real scalar arithmetic" in {
    val path = sys.env.get("GDN_INPUT_PREP_FIXTURE")
    assume(path.nonEmpty, "GDN_INPUT_PREP_FIXTURE is required; never substitute a synthetic full-block result")
    val root = Paths.get(path.get)
    val manifest = Files.readString(root.resolve("manifest.json"))
    def verifiedFile(name: String): Array[Byte] = {
      val raw = Files.readAllBytes(root.resolve(name))
      val digest = java.security.MessageDigest.getInstance("SHA-256").digest(raw).map(x => f"${x & 255}%02x").mkString
      val pattern = ("\"" + java.util.regex.Pattern.quote(name) + "\"\\s*:\\s*\\{\\s*\"bytes\"\\s*:\\s*(\\d+)\\s*,\\s*\"sha256\"\\s*:\\s*\"([0-9a-f]{64})\"").r
      val receipt = pattern.findFirstMatchIn(manifest).getOrElse(throw new IllegalArgumentException("missing fixture receipt " + name))
      require(receipt.group(1).toInt == raw.length && receipt.group(2) == digest, "fixture corruption " + name)
      raw
    }
    def bfFile(name: String) = verifiedFile(name).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
    def fpFile(name: String) = verifiedFile(name).grouped(4).map(x => java.lang.Float.intBitsToFloat((x(0) & 255) | ((x(1) & 255) << 8) | ((x(2) & 255) << 16) | ((x(3) & 255) << 24))).toSeq
    val fixtureHeads = fpFile("a_log.f32le").size
    require(fixtureHeads == 1 || fixtureHeads == 2)
    test(new GdnInputPrepHarness(fixtureHeads)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for (token <- 0 until 2) {
        val in = Inputs(bfFile(s"query$token.bf16le"), bfFile(s"key$token.bf16le"), bfFile(s"value$token.bf16le"),
          bfFile(s"a$token.bf16le"), bfFile(s"b$token.bf16le"), fpFile("a_log.f32le"), bfFile("dt_bias.bf16le"))
        val fixtureExpected = Seq("query", "key", "value", "gates").zipWithIndex.flatMap { case (role, index) =>
          fpFile(s"expected_${role}$token.f32le").grouped(16).zipWithIndex.map { case (values, beat) => (base(7 + index) + beat * 64) -> pack(values.map(bits), 32) }
        }.toMap
        assert(reference(in, token == 1)._1 == fixtureExpected, "independent Python/Scala frozen recipe mismatch")
        run(d, in, token == 1, s"checkpoint-token$token", trace = true)
      }
    }
  }
}
