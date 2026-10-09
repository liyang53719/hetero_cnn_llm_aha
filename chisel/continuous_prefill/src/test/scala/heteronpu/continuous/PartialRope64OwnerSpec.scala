// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.io.ByteArrayInputStream
import java.nio.{ByteBuffer, ByteOrder}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files, Path, Paths}
import scala.sys.process._

/** This harness uses the actual shared Scalar. Oracle values never drive it. */
class PartialRope64ArithmeticHarness extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new PartialRope64Job))
    val done = Decoupled(new PartialRope64Result)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val injectScalarError = Input(Bool())
    val injectScalarFlags = Input(UInt(5.W))
    val dropScalarFlags = Input(Bool())
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestAvailable = Output(Bool())
    val scalarRequestValid = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultAvailable = Output(Bool())
    val scalarResultValid = Output(Bool())
    val scalarError = Output(Bool())
    val scalarFlags = Output(UInt(5.W))
    val scalarFlagsValid = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new PartialRope64Owner)
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
  owner.io.scalarFlags := scalar.io.primitiveFlags | io.injectScalarFlags
  owner.io.scalarFlagsValid := scalar.io.primitiveFlagsValid && !io.dropScalarFlags
  io.scalarRequest := scalar.io.request.bits
  io.scalarRequestAvailable := owner.io.scalar.request.valid
  io.scalarRequestValid := scalar.io.request.fire
  io.scalarResult := owner.io.scalar.result.bits
  io.scalarResultAvailable := scalar.io.result.valid
  io.scalarResultValid := owner.io.scalar.result.fire
  io.scalarError := scalar.io.error
  io.scalarFlags := scalar.io.primitiveFlags
  io.scalarFlagsValid := scalar.io.primitiveFlagsValid
}

class PartialRope64ConversionHarness extends Module {
  val io = IO(new Bundle {
    val input = Input(UInt(32.W))
    val output = Output(UInt(16.W))
    val flags = Output(UInt(5.W))
  })
  val (value, flags) = PartialRope64Math.bf16RneFlags(io.input)
  io.output := value; io.flags := flags
}

trait PartialRope64TestSupport { self: ChiselScalatestTester with Matchers =>
  val inputBase = BigInt("410000000", 16)
  val trigBase = BigInt("420000000", 16)
  val outputBase = BigInt("430000000", 16)
  val fullMask = (BigInt(1) << 64) - 1
  val jobTag = BigInt("76543210", 16)
  lazy val repo: Path = {
    val start = Paths.get(sys.env.getOrElse("PARTIAL_ROPE_REPO", ".")).toAbsolutePath.normalize
    Iterator.iterate(start)(_.getParent).takeWhile(_ != null)
      .find(p => Files.exists(p.resolve("src/heteronpu/rope_bf16_candidate.py")))
      .getOrElse(throw new IllegalArgumentException("cannot find independent RoPE oracle; set PARTIAL_ROPE_REPO"))
  }
  def process(command: Seq[String], input: String = ""): String = {
    val output = new StringBuilder; val errors = new StringBuilder
    val code = (Process(command, repo.toFile) #< new ByteArrayInputStream(input.getBytes(UTF_8))).!(
      ProcessLogger(line => output.append(line).append('\n'), line => errors.append(line).append('\n')))
    require(code == 0, s"reference process failed: ${command.head}: $errors")
    output.toString
  }
  lazy val cOracle: String = {
    val binary = Files.createTempDirectory("partial-rope-independent-").resolve("reference")
    process(Seq(sys.env.getOrElse("CC", "cc"), "-std=c11", "-O2", "-frounding-math", "-ffp-contract=off", "-fno-fast-math",
      repo.resolve("scripts/rope_bf16_candidate_reference.c").toString, "-lm", "-o", binary.toString))
    process(Seq(binary.toString, "--self-test"))
    binary.toString
  }
  def words(output: String, columns: Int): Seq[Seq[BigInt]] = output.linesIterator.filter(_.nonEmpty).map { line =>
    val row = line.split(" ").toSeq.map(x => BigInt(x, 16))
    require(row.size == columns, "independent oracle trace width")
    row
  }.toSeq
  def oracle(inputs: Seq[Seq[BigInt]], converter: Boolean = false): Seq[Seq[BigInt]] = {
    val text = inputs.map(_.map(x => f"${x.toLong}%08x").mkString(" ")).mkString("", "\n", "\n")
    val call = if (converter) "bf16_convert(v[0])" else "pair_trace(*v)"
    val python = "import sys; sys.path.insert(0,'src'); from heteronpu.rope_bf16_candidate import pair_trace,bf16_convert\n" +
      "for line in sys.stdin:\n v=[int(x,16) for x in line.split()]; print(' '.join('%08x'%x for x in " + call + "))\n"
    val expected = words(process(Seq("python3", "-c", python), text), if (converter) 2 else 25)
    val native = words(process(Seq(cOracle) ++ (if (converter) Seq("--converter") else Seq.empty), text), if (converter) 2 else 25)
    require(expected.size == inputs.size && native.size == inputs.size)
    for ((actual, want) <- native.zip(expected)) {
      if (converter) assert(actual == want, "independent C converter differs from integer oracle")
      else {
        val adjusted = actual.toArray
        for (index <- 0 until 24 if actual(index) != want(index)) {
          // Existing oracle's only documented host-fenv waiver: FP32 minimum
          // normal result and solely the UF bit; conversion flags never waived.
          val valueIndex = if (index < 8) index - 4 else index - 2
          assert(Set(4, 5, 6, 7, 18, 19).contains(index), "C value/conversion mismatch")
          assert((actual(index) ^ want(index)) == 2 && (actual(index) & 1) == 1 && (want(index) & 1) == 1)
          assert(actual(valueIndex) == want(valueIndex) && (want(valueIndex) & BigInt("7fffffff", 16)) == BigInt("00800000", 16))
          adjusted(index) = want(index)
        }
        val flagIndices = Seq(4, 5, 6, 7, 12, 13, 14, 15, 18, 19, 22, 23)
        assert(actual(24) == flagIndices.map(actual).reduce(_ | _), "C aggregate flag mismatch")
        adjusted(24) = flagIndices.map(adjusted(_)).reduce(_ | _)
        assert(adjusted.toSeq == want, "independent C pair trace differs from integer oracle")
      }
    }
    expected
  }
  case class Fixture(tokens: Int, heads: Int, position: Long, trigTokens: Long,
                     hidden: Seq[Int], rows: Map[Long, Seq[Int]])
  case class Step(op: Int, a: BigInt, b: BigInt, result: BigInt, primitiveFlags: Int,
                  converted: BigInt, conversionFlags: Int)
  case class Reference(output: Seq[Int], steps: Seq[Step], flags: Int)
  def reference(f: Fixture): Reference = {
    require(f.hidden.size == f.tokens * f.heads * 256)
    val pairInputs = for (t <- 0 until f.tokens; h <- 0 until f.heads; p <- 0 until 32) yield {
      val base = (t * f.heads + h) * 256; val trig = f.rows(f.position + t)
      Seq(f.hidden(base + p), f.hidden(base + p + 32), trig(p), trig(p + 32)).map(x => BigInt(x) << 16)
    }
    val traces = oracle(pairInputs)
    val output = f.hidden.toArray; val steps = scala.collection.mutable.ArrayBuffer.empty[Step]
    var aggregate = 0
    for ((trace, index) <- traces.zipWithIndex) {
      val in = pairInputs(index); val base = (index / 32) * 256; val pair = index % 32
      val aa = Seq(in(0), in(1), in(0), in(1), trace(8), trace(10))
      val bb = Seq(in(2), in(3), in(3), in(2), trace(9) ^ BigInt("80000000", 16), trace(11))
      for (n <- 0 until 6) {
        val value = if (n < 4) trace(n) else trace(n + 12)
        val primitive = if (n < 4) trace(n + 4) else trace(n + 14)
        val converted = if (n < 4) trace(n + 8) else trace(n + 16)
        val flags = if (n < 4) trace(n + 12) else trace(n + 18)
        steps += Step(if (n < 4) ScalarOp.Mul else ScalarOp.Add, aa(n), bb(n), value, primitive.toInt, converted, flags.toInt)
      }
      output(base + pair) = (trace(20) >> 16).toInt
      output(base + pair + 32) = (trace(21) >> 16).toInt
      aggregate |= trace(24).toInt
    }
    Reference(output.toSeq, steps.toSeq, aggregate)
  }
  def synthetic(tokens: Int = 2, heads: Int = 2, position: Long = 3): Fixture = {
    val hidden = Seq.tabulate(tokens * heads * 256) { index =>
      val lane = index % 256
      if (lane < 64) (if ((index & 1) == 0) 0 else 0x8000) | (0x3d80 + (index * 17 % 700))
      else (index * 193 + 0x711d) & 65535
    }.toArray
    hidden(0) = 0xbf92; hidden(32) = 0xc110
    for (base <- hidden.indices by 256) {
      hidden(base + 64) = 0x7f80; hidden(base + 65) = 0xff80
      hidden(base + 66) = 0x7fc1; hidden(base + 67) = 0x7f81
      hidden(base + 68) = 0x8000; hidden(base + 69) = 1
    }
    val rows = (0 until tokens).map { t =>
      val values = Seq.tabulate(64) { i =>
        if (i < 32) 0x3f00 + ((i * 3 + t * 7) % 100)
        else (if ((i & 1) == 0) 0 else 0x8000) | (0x3c00 + ((i * 11 + t * 19) % 300))
      }.toArray
      if (t == 0) { values(0) = 0x3f80; values(32) = 0x3ce1 }
      (position + t) -> values.toSeq
    }.toMap
    Fixture(tokens, heads, position, position + tokens + 1, hidden.toSeq, rows)
  }
  def pack(xs: Seq[Int]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) { case (word, (x, i)) => word | (BigInt(x) << (i * 16)) }
  def beats(base: BigInt, values: Seq[Int]): Map[BigInt, BigInt] = values.grouped(32).zipWithIndex.map {
    case (xs, i) => (base + i * 64) -> pack(xs)
  }.toMap
  def init(d: PartialRope64ArithmeticHarness): Unit = {
    d.clock.setTimeout(250000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.injectScalarError.poke(false.B)
    d.io.injectScalarFlags.poke(0.U); d.io.dropScalarFlags.poke(false.B)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: PartialRope64ArithmeticHarness, f: Fixture): Unit = {
    d.io.job.bits.tokens.poke(f.tokens.U); d.io.job.bits.heads.poke(f.heads.U)
    d.io.job.bits.headDim.poke(256.U); d.io.job.bits.rotaryDim.poke(64.U); d.io.job.bits.policy.poke("hb1".U)
    d.io.job.bits.input.poke(inputBase.U); d.io.job.bits.trig.poke(trigBase.U); d.io.job.bits.output.poke(outputBase.U)
    d.io.job.bits.positionBase.poke(f.position.U); d.io.job.bits.trigTokens.poke(f.trigTokens.U); d.io.job.bits.tag.poke(jobTag.U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: PartialRope64ArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: PartialRope64ArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue, d.io.done.bits.cycles.peek().litValue,
    d.io.done.bits.outputCommitted.peek().litValue, d.io.done.bits.exceptionFlags.peek().litValue)

  def run(d: PartialRope64ArithmeticHarness, f: Fixture, label: String, fault: String = "none",
          trace: Boolean = true, numerical: Boolean = false): Reference = {
    val expected = if (numerical) Reference(Seq.empty, Seq.empty, 0) else reference(f)
    val reads = beats(inputBase, f.hidden) ++ f.rows.toSeq.flatMap { case (position, row) => beats(trigBase + position * 128, row) }.toMap
    val writes = beats(outputBase, expected.output)
    val readCount = scala.collection.mutable.Map.empty[BigInt, Int].withDefaultValue(0)
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    d.io.injectScalarError.poke((fault == "scalar").B)
    d.io.injectScalarFlags.poke((if (fault == "flags") 2 else 0).U)
    d.io.dropScalarFlags.poke((fault == "flags-valid").B)
    var elapsed = 0; var issued = 0; var requests = 0; var results = 0; var injected = false
    var observedFlags = 0
    var heldRequest: Option[Seq[BigInt]] = None
    var heldResult: Option[Seq[BigInt]] = None
    def step(n: Int = 1): Unit = for (_ <- 0 until n) {
      val hold = elapsed % 19 < 4
      d.io.scalarHold.poke(hold.B)
      val requestWords = Seq(d.io.scalarRequest.op.peek().litValue, d.io.scalarRequest.a.peek().litValue, d.io.scalarRequest.b.peek().litValue)
      val resultWords = Seq(d.io.scalarResult.peek().litValue, d.io.scalarFlags.peek().litValue,
        d.io.scalarFlagsValid.peek().litValue, d.io.scalarError.peek().litValue)
      heldRequest.foreach { previous =>
        d.io.scalarRequestAvailable.expect(true.B); assert(previous == requestWords, "scalar request changed under backpressure")
      }
      heldResult.foreach { previous =>
        d.io.scalarResultAvailable.expect(true.B); assert(previous == resultWords, "scalar result/flags/error changed under backpressure")
      }
      heldRequest = if (d.io.scalarRequestAvailable.peek().litToBoolean && !d.io.scalarRequestValid.peek().litToBoolean) Some(requestWords) else None
      heldResult = if (d.io.scalarResultAvailable.peek().litToBoolean && !d.io.scalarResultValid.peek().litToBoolean) Some(resultWords) else None
      if (trace && !numerical) {
        if (d.io.scalarRequestValid.peek().litToBoolean) {
          assert(requests < expected.steps.size, "unexpected scalar request")
          val wanted = expected.steps(requests)
          d.io.scalarRequest.op.expect(wanted.op.U); d.io.scalarRequest.a.expect(wanted.a.U); d.io.scalarRequest.b.expect(wanted.b.U)
          requests += 1
        }
        if (d.io.scalarResultValid.peek().litToBoolean) {
          val wanted = expected.steps(results)
          d.io.scalarResult.expect(wanted.result.U); d.io.scalarFlags.expect(wanted.primitiveFlags.U)
          d.io.scalarFlagsValid.expect(true.B)
          if (fault != "flags-valid") observedFlags |= wanted.primitiveFlags | wanted.conversionFlags | (if (fault == "flags") 2 else 0)
          results += 1
        }
      }
      d.clock.step(); elapsed += 1
    }
    setJob(d, f); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < f.tokens * f.heads * 20000 + 10000) {
      if (!d.io.memory.valid.peek().litToBoolean) step()
      else {
        val r = request(d)
        assert(r.tag == ((jobTag << 32) | issued), "memory transaction sequence")
        val delay = 1 + issued % 4
        step(delay); assert(request(d) == r, "request changed under memory backpressure")
        d.io.memory.ready.poke(true.B); step(); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == outputBase + f.hidden.size * 2 - 64
        val inject = !injected && (fault match {
          case "read" | "tag" => !r.write
          case "write" => r.write
          case "final-ack" | "final-tag" => last
          case _ => false
        })
        if (inject) injected = true
        if (r.write) {
          assert(writes.contains(r.address), "unexpected output address")
          assert(r.data == writes(r.address), s"output/conversion/tail mismatch $label ${r.address}")
          assert(r.mask == fullMask && !committed.contains(r.address))
        } else {
          assert(reads.contains(r.address), s"unexpected input/coefficient address $label ${r.address}")
          assert(r.mask == 0); readCount(r.address) += 1
        }
        step(if (last) 29 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        val wrongTag = inject && (fault == "tag" || fault == "final-tag")
        d.io.response.bits.tag.poke((r.tag ^ (if (wrongTag) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && !wrongTag).B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(); d.io.response.valid.poke(false.B)
        if (r.write && !inject) committed(r.address) = r.data
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner timeout $label")
    val code = if (numerical || fault == "scalar" || fault == "flags" || (expected.flags & 30) != 0) Status.Numerical
      else if (Set("tag", "final-tag", "flags-valid").contains(fault)) Status.Protocol
      else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.status.expect(code.U); d.io.done.bits.tag.expect(jobTag.U)
    d.io.done.bits.writeBytes.expect((committed.size * 64).U); d.io.done.bits.outputCommitted.expect((code == Status.Ok).B)
    d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
    if (trace && !numerical) d.io.done.bits.exceptionFlags.expect(observedFlags.U)
    if (code == Status.Ok) {
      assert(committed.toMap == writes)
      assert(readCount.toMap == reads.keys.map(_ -> 1).toMap, "trig must be read once per token and shared by heads")
      d.io.done.bits.exceptionFlags.expect(expected.flags.U)
      if (trace) assert(requests == expected.steps.size && results == expected.steps.size)
      for (base <- f.hidden.indices by 256) assert(expected.output.slice(base + 64, base + 256) == f.hidden.slice(base + 64, base + 256))
    }
    val held = completion(d); step(11); assert(completion(d) == held, "completion changed while stalled")
    println(s"PARTIAL_ROPE64_RTL label=$label tokens=${f.tokens} heads=${f.heads} position=${f.position} status=$code ack_bytes=${committed.size * 64} scalar_checks=$results flags=${held(5)}")
    d.io.done.ready.poke(true.B); step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
    if (code != Status.Ok) { step(7); d.io.job.ready.expect(false.B) }
    if (code == Status.Ok) {
      val actual = committed.toSeq.sortBy(_._1).flatMap { case (_, word) =>
        (0 until 32).map(i => ((word >> (i * 16)) & 65535).toInt)
      }
      expected.copy(output = actual)
    } else expected
  }
  def readBf(path: Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(b => (b(0) & 255) | ((b(1) & 255) << 8)).toSeq
  def readWords(path: Path): Seq[BigInt] = {
    val bytes = ByteBuffer.wrap(Files.readAllBytes(path)).order(ByteOrder.LITTLE_ENDIAN)
    require(bytes.remaining() % 4 == 0)
    Seq.fill(bytes.remaining() / 4)(BigInt(bytes.getInt().toLong & 0xffffffffL))
  }
  def digest(bytes: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(bytes).map(x => f"${x & 255}%02x").mkString
}

class PartialRope64OwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with PartialRope64TestSupport {
  "PartialRope64Owner" should "match independent integer and C nodes, split pairs, token coefficients and untouched tails" in {
    test(new PartialRope64ArithmeticHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); val f = synthetic()
      val expected = run(d, f, "nonzero-position-two-token-two-head")
      assert(expected.flags == 1, "synthetic NX witness must retain nonfatal inexact")
      run(d, synthetic(tokens = 1, heads = 1, position = 0), "position-zero-one-head")
      for (fault <- Seq("read", "tag", "write", "final-ack", "final-tag", "scalar", "flags", "flags-valid")) {
        init(d); run(d, synthetic(tokens = 1, heads = 1), fault, fault)
      }
      val normal = synthetic(tokens = 1, heads = 1)
      for ((bad, label) <- Seq(
        normal.copy(hidden = normal.hidden.updated(0, 0x7fc0)) -> "nan-even",
        normal.copy(hidden = normal.hidden.updated(32, 0x7f80)) -> "infinite-odd",
        normal.copy(rows = normal.rows.updated(normal.position, normal.rows(normal.position).updated(0, 0x7f81))) -> "snan-cos",
        normal.copy(rows = normal.rows.updated(normal.position, normal.rows(normal.position).updated(32, 0xff80))) -> "infinite-sin")) {
        init(d); run(d, bad, label, numerical = true)
      }
      for ((a, c, label) <- Seq((0x7f7f, 0x4000, "fp32-overflow"), (0x0001, 0x3f01, "bf16-underflow"),
        (0x0001, 0x0001, "fp32-underflow"))) {
        val bad = normal.copy(hidden = normal.hidden.updated(0, a),
          rows = normal.rows.updated(normal.position, normal.rows(normal.position).updated(0, c)))
        init(d); run(d, bad, label)
      }
      // Joint owner/transport/Scalar reset while a memory read is in flight.
      init(d); setJob(d, normal); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B); d.io.response.ready.expect(true.B)
      init(d); run(d, normal, "memory-reset-recovery")
      // Enter the actual shared Scalar, then reset both modules before result.
      init(d); setJob(d, normal); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      val reads = beats(inputBase, normal.hidden) ++ beats(trigBase + normal.position * 128, normal.rows(normal.position))
      for (_ <- 0 until 10) {
        d.io.memory.valid.expect(true.B); val r = request(d); assert(!r.write)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(reads(r.address).U); d.io.response.bits.tag.poke(r.tag.U)
        d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.io.scalarRequestValid.expect(true.B); d.clock.step(); d.io.done.valid.expect(false.B)
      init(d); run(d, normal, "scalar-reset-recovery")
      // One staging write has committed physically, with the next output
      // packet stalled. Joint reset must discard it and start a fresh job.
      init(d); setJob(d, normal); d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
      var firstWriteAcked = false; var resetCycles = 0
      while (!firstWriteAcked && resetCycles < 3000) {
        if (!d.io.memory.valid.peek().litToBoolean) { d.clock.step(); resetCycles += 1 }
        else {
          val r = request(d)
          d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
          d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
          d.io.response.bits.tag.poke(r.tag.U); d.io.response.valid.poke(true.B)
          d.clock.step(); d.io.response.valid.poke(false.B); resetCycles += 2
          firstWriteAcked = r.write
        }
      }
      assert(firstWriteAcked, "did not reach partially acknowledged output")
      d.io.done.bits.writeBytes.expect(64.U); d.io.done.bits.outputCommitted.expect(false.B)
      d.io.memory.valid.expect(true.B); d.io.memory.bits.write.expect(true.B)
      d.clock.step(7); d.io.done.valid.expect(false.B)
      val fresh = normal.copy(hidden = normal.hidden.updated(0, 0x3f80),
        rows = normal.rows.updated(normal.position, normal.rows(normal.position).updated(0, 0x3f00)))
      init(d); d.io.memory.valid.expect(false.B); run(d, fresh, "partial-write-reset-new-job")
    }
  }

  it should "reject aliases, malformed geometry, position overflow and all overflowing spans before issuing work" in {
    test(new PartialRope64ArithmeticHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val f = synthetic()
      for (bad <- 0 until 22) {
        init(d); setJob(d, f)
        bad match {
          case 0 => d.io.job.bits.output.poke(inputBase.U)
          case 1 => d.io.job.bits.output.poke((inputBase + 64).U)
          case 2 => d.io.job.bits.output.poke(trigBase.U)
          case 3 => d.io.job.bits.output.poke((trigBase + 64).U)
          case 4 => d.io.job.bits.input.poke((inputBase + 2).U)
          case 5 => d.io.job.bits.trig.poke((trigBase + 2).U)
          case 6 => d.io.job.bits.output.poke((outputBase + 2).U)
          case 7 => d.io.job.bits.tokens.poke(0.U)
          case 8 => d.io.job.bits.tokens.poke(129.U)
          case 9 => d.io.job.bits.heads.poke(0.U)
          case 10 => d.io.job.bits.heads.poke(9.U)
          case 11 => d.io.job.bits.headDim.poke(128.U)
          case 12 => d.io.job.bits.rotaryDim.poke(128.U)
          case 13 => d.io.job.bits.policy.poke(0.U)
          case 14 => d.io.job.bits.input.poke(((BigInt(1) << 56) - 64).U)
          case 15 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
          case 16 => d.io.job.bits.trig.poke(((BigInt(1) << 56) - 64).U)
          case 17 => d.io.job.bits.input.poke(((BigInt(1) << 64) - 64).U)
          case 18 => d.io.job.bits.trigTokens.poke((f.position + f.tokens - 1).U)
          case 19 => d.io.job.bits.positionBase.poke("hffffffff".U); d.io.job.bits.trigTokens.poke("hffffffff".U)
          case 20 => d.io.job.bits.positionBase.poke(0.U); d.io.job.bits.trigTokens.poke(0.U)
          case 21 => d.io.job.bits.trig.poke(((BigInt(1) << 64) - 128).U)
        }
        d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
        d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
        d.io.done.bits.writeBytes.expect(0.U); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.memory.valid.expect(false.B); d.io.scalarRequestValid.expect(false.B)
        d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
        d.io.resetRequired.expect(true.B); d.io.job.ready.expect(false.B)
      }
    }
  }

  "PartialRope64 BF16 conversion" should "preserve the frozen destination-encoding tininess and all special encodings" in {
    val inputs = Seq("00000000", "80000000", "00000001", "80000001", "00008000", "00008001",
      "007f7fff", "007f8000", "007fffff", "00800000", "00800001", "3f808000", "3f818000",
      "7f7f7fff", "7f7f8000", "ff7f8000", "7f800000", "ff800000", "7fc12345", "ffc12345", "7f800001", "ff800001")
      .map(x => Seq(BigInt(x, 16)))
    val expected = oracle(inputs, converter = true)
    test(new PartialRope64ConversionHarness) { d =>
      for ((input, output) <- inputs.zip(expected)) {
        d.io.input.poke(input.head.U); d.io.output.expect((output.head >> 16).U); d.io.flags.expect(output(1).U)
      }
    }
  }
}

/** Owner-only gate: inputs are frozen Norm outputs derived from captured real
  * Host Q/K projections. This harness does not execute Host, Matrix or iDMA.
  * Native values remain diagnostics; no full-block acceptance is implied.
  */
class PartialRope64RealSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with PartialRope64TestSupport {
  "PartialRope64Owner real Q8/K2" should "match frozen all-products-BF16 nodes at absolute positions 0 and 255" in {
    val root = Paths.get(sys.env.getOrElse("QK_NORM_ROPE_FIXTURE", throw new IllegalArgumentException("QK_NORM_ROPE_FIXTURE required")))
    val raw = Files.readAllBytes(root.resolve("manifest.json"))
    require(digest(raw) == sys.env.getOrElse("QK_NORM_ROPE_MANIFEST_SHA256", ""), "fixture manifest pin required")
    val manifest = ujson.read(new String(raw, UTF_8))
    require(manifest("model_revision").str == "2fc06364715b967f1860aea9cf38778875588b17")
    require(manifest("framework_revision").str == "14e738b5d0cc69aa27a95dde272aea41fde44f2f")
    require(manifest("layer_id").num == 3 && manifest("status").str == "PASS_PREPARED_OWNER_ONLY_FIXTURE_PYTHON_C")
    require(!manifest("host_output_injection").bool && !manifest("hardware_acceptance_claimed").bool)
    for ((name, metadata) <- manifest("files").obj) {
      val bytes = Files.readAllBytes(root.resolve(name))
      require(bytes.length == metadata("bytes").num && digest(bytes) == metadata("sha256").str, s"fixture drift $name")
    }
    for ((name, hash) <- manifest("oracle_source_sha256").obj) {
      require(digest(Files.readAllBytes(repo.resolve(name))) == hash.str, s"independent oracle drift $name")
    }
    test(new PartialRope64ArithmeticHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for (label <- Seq("cold0", "carried127")) {
        val directory = root.resolve(label)
        val caseRaw = Files.readAllBytes(directory.resolve("manifest.json"))
        require(digest(caseRaw) == manifest("cases")(label)("sha256").str, s"case manifest drift $label")
        val metadata = ujson.read(new String(caseRaw, UTF_8))
        val position = metadata("positionBase").num.toLong
        require(position == (if (label == "cold0") 0L else 255L))
        require(metadata("head_dim").num == 256 && metadata("rotary_dim").num == 64 && metadata("rope_policy").num == 177)
        require(metadata("token_count").num == 1 && metadata("q_heads").num == 8 && metadata("k_heads").num == 2)
        require(metadata("trig_file_rows").num == 1 && metadata("trig_file_row_index").num.toLong == position)
        require(metadata("scalar_opcodes")("Add").num == ScalarOp.Add && metadata("scalar_opcodes")("Mul").num == ScalarOp.Mul)
        val trig = readBf(directory.resolve("trig.bf16le")); require(trig.size == 64)
        for ((role, heads) <- Seq("q" -> 8, "k" -> 2)) {
          val input = readBf(directory.resolve(s"norm_$role.bf16le"))
          val f = Fixture(1, heads, position, metadata("trigTokens").num.toLong, input, Map(position -> trig))
          val got = run(d, f, s"real-$label-$role")
          assert(got.output == readBf(directory.resolve(s"rope_$role.bf16le")), "frozen independently checked terminal mismatch")
          val scalarTrace = got.steps.flatMap(s => Seq(BigInt(s.op), s.a, s.b, s.result, BigInt(s.primitiveFlags)))
          val conversionTrace = got.steps.flatMap(s => Seq(s.result, s.converted, BigInt(s.conversionFlags)))
          assert(scalarTrace == readWords(directory.resolve(s"rope_${role}_scalar_trace.u32le")), "frozen scalar node/flag mismatch")
          assert(conversionTrace == readWords(directory.resolve(s"rope_${role}_conversion_trace.u32le")), "frozen BF16 boundary/flag mismatch")
          val nativeInput = readBf(directory.resolve(s"native_norm_$role.bf16le"))
          val native = readBf(directory.resolve(s"native_rope_${role}_prefix.bf16le"))
          val actualPrefix = got.output.grouped(256).flatMap(_.take(64)).toSeq
          require(native.size == actualPrefix.size)
          val differences = actualPrefix.zip(native).count { case (a, b) => a != b }
          val tailDifferences = got.output.grouped(256).zip(input.grouped(256)).map { case (a, b) =>
            a.drop(64).zip(b.drop(64)).count { case (x, y) => x != y }
          }.sum
          println(s"PARTIAL_ROPE64_NATIVE_DIAGNOSTIC label=$label-$role same_input=${input == nativeInput} prefix_values=${native.size} bit_mismatches=$differences tail_bit_mismatches=$tailDifferences official_acceptance=UNASSIGNED full_host_chain=false")
          sys.env.get("PARTIAL_ROPE_ACTUAL_DIR").foreach { outputPath =>
            val out = Paths.get(outputPath).resolve(label); Files.createDirectories(out)
            val bytes = got.output.flatMap(v => Seq(v.toByte, (v >>> 8).toByte)).toArray
            Files.write(out.resolve(s"actual_rope_$role.bf16le"), bytes)
          }
        }
      }
    }
  }
}
