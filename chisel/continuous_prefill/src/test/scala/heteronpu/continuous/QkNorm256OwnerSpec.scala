// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.{ByteBuffer, ByteOrder}
import java.nio.file.{Files, Path, Paths}
import scala.sys.process._

/** The only arithmetic service is the real production BlockScalarFloat. */
class QkNorm256ArithmeticHarness(qHeads: Int = 2, kvHeads: Int = 1) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new QkNorm256Job))
    val done = Decoupled(new QkNorm256Result)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val injectScalarError = Input(Bool())
    val dropFlags = Input(Bool())
    val injectFlags = Input(UInt(5.W))
    val scalarRequest = Output(new ScalarRequest)
    val scalarRequestAvailable = Output(Bool())
    val scalarRequestFire = Output(Bool())
    val scalarResult = Output(UInt(32.W))
    val scalarResultFlags = Output(UInt(5.W))
    val scalarResultFlagsValid = Output(Bool())
    val scalarResultAvailable = Output(Bool())
    val scalarResultFire = Output(Bool())
    val scalarResultError = Output(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new QkNorm256Owner(qHeads, kvHeads))
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
  owner.io.scalarFlags := scalar.io.primitiveFlags | io.injectFlags
  owner.io.scalarFlagsValid := scalar.io.primitiveFlagsValid && !io.dropFlags
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.scalarRequest := scalar.io.request.bits
  io.scalarRequestAvailable := owner.io.scalar.request.valid
  io.scalarRequestFire := scalar.io.request.fire
  io.scalarResult := scalar.io.result.bits
  io.scalarResultFlags := scalar.io.primitiveFlags
  io.scalarResultFlagsValid := scalar.io.primitiveFlagsValid
  io.scalarResultAvailable := scalar.io.result.valid
  io.scalarResultFire := owner.io.scalar.result.fire
  io.scalarResultError := scalar.io.error
}

trait QkNorm256TestSupport { self: ChiselScalatestTester with Matchers =>
  val inputBase = BigInt("510000000", 16)
  val weightBase = BigInt("520000000", 16)
  val outputBase = BigInt("530000000", 16)
  val gateBase = BigInt("540000000", 16)
  val fullMask = (BigInt(1) << 64) - 1
  val tag = BigInt("c1abcdef", 16)
  def pack(xs: Seq[Int]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (v, (x, i)) => v | (BigInt(x & 65535) << (16 * i))
  }
  def readBf(path: Path): Seq[Int] = Files.readAllBytes(path).grouped(2).map(x => (x(0) & 255) | ((x(1) & 255) << 8)).toSeq
  def writeBf(path: Path, values: Seq[Int]): Unit = Files.write(path, values.flatMap(v => Seq(v.toByte, (v >>> 8).toByte)).toArray)
  def words(path: Path): Seq[BigInt] = {
    val b = ByteBuffer.wrap(Files.readAllBytes(path)).order(ByteOrder.LITTLE_ENDIAN)
    Seq.fill(b.remaining() / 4)(BigInt(b.getInt().toLong & 0xffffffffL))
  }
  case class Step(op: BigInt, a: BigInt, b: BigInt, result: BigInt, flags: BigInt)
  case class Gold(norm: Seq[Int], gate: Seq[Int], operations: Seq[Step], flags: BigInt, meanEps: BigInt, inverse: BigInt)

  // The checked-in integer and independently compiled C recipes must agree on
  // every trace word before any result can become the RTL test's expectation.
  // No JVM floating point, frozen output spoof, or oracle-driven Scalar exists.
  val oracleScript = """
import os, struct, subprocess, sys
from pathlib import Path
repo, out, isq = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
sys.path.insert(0, str(repo / 'src'))
from heteronpu.qk_norm256_candidate import head_trace, trace_words, RSQRT_COEFFICIENTS
def u16(p):
 b=p.read_bytes(); return struct.unpack('<%dH'%(len(b)//2), b)
def put(p, xs): p.write_bytes(struct.pack('<%dI'%len(xs), *xs))
x, w = u16(out/'input.bf16le'), u16(out/'weight.bf16le')
assert len(w)==256 and len(x)%(512 if isq else 256)==0
ops=[]; all_trace=[]; records=[]; norm=[]; gate=[]; flags=0
for base in range(0,len(x),512 if isq else 256):
 a=[v<<16 for v in x[base:base+256]]; b=[v<<16 for v in w]
 t=head_trace(a,b); all_trace.extend(trace_words(t)); records.extend(a+b)
 def step(op, lhs, rhs, value, flag): ops.extend((op,lhs,rhs,value,flag))
 total=0
 for chunk in range(16):
  start=chunk*16
  for i in range(start,start+16): step(1,a[i],a[i],t['squares'][i],t['square_flags'][i])
  level=list(t['squares'][start:start+16]); ti=chunk*15
  while len(level)>1:
   nxt=[]
   for i in range(0,len(level),2):
    r=t['tree'][ti]; step(0,level[i],level[i+1],r,t['tree_flags'][ti]); nxt.append(r); ti+=1
   level=nxt
  step(0,total,level[0],t['running'][chunk],t['running_flags'][chunk]); total=t['running'][chunk]
 step(1,total,0x3b800000,t['mean'],t['mean_flags'])
 step(0,t['mean'],0x358637bd,t['mean_eps'],t['mean_eps_flags'])
 rv=t['rsqrt_values']; rf=t['rsqrt_flags']; coeff=RSQRT_COEFFICIENTS[t['rsqrt_index']]
 args=[(1,coeff>>32,t['rsqrt_norm']),(0,rv[0],coeff&0xffffffff),(1,rv[1],rv[1]),
       (1,t['rsqrt_norm'],rv[2]),(1,0x3f000000,rv[3]),(0,0x3fc00000,rv[4]^0x80000000),
       (1,rv[1],rv[5]),(1,rv[6],t['rsqrt_scale'])]
 for i,(op,lhs,rhs) in enumerate(args): step(op,lhs,rhs,rv[i],rf[i])
 for i in range(256):
  step(0,0x3f800000,b[i],t['gamma'][i],t['gamma_flags'][i])
  step(1,a[i],t['inverse'],t['scaled'][i],t['scaled_flags'][i])
  step(1,t['scaled'][i],t['gamma'][i],t['output_fp32'][i],t['output_fp32_flags'][i])
 norm.extend(v>>16 for v in t['output_bf16']); flags|=t['aggregate_flags']
 if isq: gate.extend(x[base+256:base+512])
put(out/'c_input.u32le',records); put(out/'python_trace.u32le',all_trace)
subprocess.run(['cc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
 str(repo/'scripts/qk_norm256_reference.c'),'-lm','-o',str(out/'reference')],check=True)
subprocess.run([str(out/'reference'),str(out/'c_input.u32le'),str(out/'c_trace.u32le')],check=True)
assert (out/'c_trace.u32le').read_bytes()==(out/'python_trace.u32le').read_bytes(), 'C/integer trace drift'
put(out/'operations.u32le',ops); put(out/'summary.u32le',[flags,t['mean_eps'],t['inverse']])
(out/'norm.bf16le').write_bytes(struct.pack('<%dH'%len(norm),*norm))
(out/'gate.bf16le').write_bytes(struct.pack('<%dH'%len(gate),*gate))
"""
  lazy val repo: Path = {
    val explicit = sys.env.get("QK_NORM_REPO").map(Paths.get(_))
    explicit.getOrElse(Iterator.iterate(Paths.get("").toAbsolutePath)(_.getParent)
      .takeWhile(_ != null).find(p => Files.isRegularFile(p.resolve("scripts/qk_norm256_reference.c")))
      .getOrElse(throw new IllegalArgumentException("QK_NORM_REPO required")))
  }
  def reference(input: Seq[Int], weight: Seq[Int], isQ: Boolean): Gold = {
    val dir = Files.createTempDirectory("qk_norm_owner_gold_")
    writeBf(dir.resolve("input.bf16le"), input); writeBf(dir.resolve("weight.bf16le"), weight)
    require(Seq("python3", "-c", oracleScript, repo.toString, dir.toString, if (isQ) "1" else "0").! == 0,
      "independent Q/K integer/C oracle failed")
    val operations = words(dir.resolve("operations.u32le")).grouped(5).map(v => Step(v(0), v(1), v(2), v(3), v(4))).toSeq
    val summary = words(dir.resolve("summary.u32le"))
    Gold(readBf(dir.resolve("norm.bf16le")), readBf(dir.resolve("gate.bf16le")), operations, summary(0), summary(1), summary(2))
  }
  def init(d: QkNorm256ArithmeticHarness): Unit = {
    d.clock.setTimeout(1000000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalarHold.poke(false.B); d.io.injectScalarError.poke(false.B)
    d.io.dropFlags.poke(false.B); d.io.injectFlags.poke(0.U)
    d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
  }
  def setJob(d: QkNorm256ArithmeticHarness, isQ: Boolean, tokens: Int): Unit = {
    d.io.job.bits.tokens.poke(tokens.U); d.io.job.bits.role.poke((if (isQ) 0 else 1).U)
    d.io.job.bits.headDim.poke(256.U); d.io.job.bits.policy.poke("hc1".U); d.io.job.bits.epsilon.poke("h358637bd".U)
    d.io.job.bits.input.poke(inputBase.U); d.io.job.bits.weight.poke(weightBase.U)
    d.io.job.bits.output.poke(outputBase.U); d.io.job.bits.gateOutput.poke((if (isQ) gateBase else BigInt(0)).U)
    d.io.job.bits.tag.poke(tag.U)
  }
  case class Request(write: Boolean, address: BigInt, data: BigInt, mask: BigInt, tag: BigInt)
  def request(d: QkNorm256ArithmeticHarness): Request = Request(d.io.memory.bits.write.peek().litToBoolean,
    d.io.memory.bits.address.peek().litValue, d.io.memory.bits.data.peek().litValue,
    d.io.memory.bits.mask.peek().litValue, d.io.memory.bits.tag.peek().litValue)
  def completion(d: QkNorm256ArithmeticHarness): Seq[BigInt] = Seq(d.io.done.bits.tag.peek().litValue,
    d.io.done.bits.status.peek().litValue, d.io.done.bits.writeBytes.peek().litValue,
    d.io.done.bits.cycles.peek().litValue, d.io.done.bits.outputCommitted.peek().litValue,
    d.io.done.bits.normStatus.peek().litValue, d.io.done.bits.exceptionFlags.peek().litValue,
    d.io.done.bits.lastMeanEps.peek().litValue, d.io.done.bits.lastInverse.peek().litValue)

  def run(d: QkNorm256ArithmeticHarness, hidden: Seq[Int], weight: Seq[Int], isQ: Boolean, tokens: Int,
          gold: Option[Gold], label: String, fault: String = "none", expectedNormStatus: Int = 0,
          trace: Boolean = true): Unit = {
    d.io.injectScalarError.poke((fault == "scalar").B)
    d.io.dropFlags.poke((fault == "flags-missing").B)
    d.io.injectFlags.poke((if (fault == "flags-underflow") 2 else 0).U)
    def beats(base: BigInt, xs: Seq[Int]): Map[BigInt, BigInt] = xs.grouped(32).zipWithIndex.map {
      case (values, index) => (base + index * 64) -> pack(values)
    }.toMap
    val reads = beats(inputBase, hidden) ++ beats(weightBase, weight)
    val writes = gold.map(g => beats(outputBase, g.norm) ++ beats(gateBase, g.gate)).getOrElse(Map.empty[BigInt, BigInt])
    val committed = scala.collection.mutable.Map.empty[BigInt, BigInt]
    var elapsed = 0; var issued = 0; var requests = 0; var results = 0; var injected = false
    var heldRequest = Option.empty[Seq[BigInt]]
    var heldResult = Option.empty[Seq[BigInt]]
    def step(n: Int): Unit = for (_ <- 0 until n) {
      val hold = elapsed % 29 < 7
      d.io.scalarHold.poke(hold.B)
      if (d.io.scalarRequestAvailable.peek().litToBoolean) {
        val requestNow = Seq(d.io.scalarRequest.op.peek().litValue,
          d.io.scalarRequest.a.peek().litValue, d.io.scalarRequest.b.peek().litValue)
        heldRequest.foreach(old => assert(old == requestNow, "Scalar request changed under backpressure"))
        heldRequest = if (hold) Some(requestNow) else None
      } else heldRequest = None
      val resultNow = Seq(d.io.scalarResult.peek().litValue, d.io.scalarResultFlags.peek().litValue,
        d.io.scalarResultFlagsValid.peek().litValue, d.io.scalarResultError.peek().litValue)
      if (d.io.scalarResultAvailable.peek().litToBoolean) {
        heldResult.foreach(old => assert(old == resultNow, "Scalar result/flags changed under backpressure"))
        heldResult = if (hold) Some(resultNow) else None
      } else heldResult = None
      if (d.io.scalarRequestFire.peek().litToBoolean) {
        if (trace && gold.isDefined) {
          val e = gold.get.operations(requests)
          d.io.scalarRequest.op.expect(e.op.U); d.io.scalarRequest.a.expect(e.a.U); d.io.scalarRequest.b.expect(e.b.U)
        }
        requests += 1
      }
      if (d.io.scalarResultFire.peek().litToBoolean) {
        if (trace && gold.isDefined) {
          val e = gold.get.operations(results)
          d.io.scalarResult.expect(e.result.U); d.io.scalarResultFlags.expect(e.flags.U)
          d.io.scalarResultFlagsValid.expect(true.B); d.io.scalarResultError.expect(false.B)
        }
        results += 1
      }
      d.clock.step(); elapsed += 1
    }
    setJob(d, isQ, tokens); d.io.job.ready.expect(true.B)
    d.io.job.valid.poke(true.B); step(1); d.io.job.valid.poke(false.B)
    while (!d.io.done.valid.peek().litToBoolean && elapsed < 600000) {
      if (!d.io.memory.valid.peek().litToBoolean) step(1)
      else {
        val r = request(d)
        assert(r.tag == ((tag << 32) | issued), "memory transaction sequence")
        val delay = 1 + issued % 3
        step(delay); assert(request(d) == r, "memory request changed under backpressure")
        d.io.memory.ready.poke(true.B); step(1); d.io.memory.ready.poke(false.B)
        val last = r.write && r.address == (if (isQ) gateBase else outputBase) + hidden.size / (if (isQ) 2 else 1) * 2 - 64
        val inject = !injected && (fault match {
          case "read" | "tag" => !r.write
          case "write" => r.write
          case "final-ack" | "final-tag" => last
          case _ => false
        })
        if (inject) injected = true
        if (r.write) {
          assert(writes.contains(r.address), s"unexpected write $label/${r.address}")
          assert(r.data == writes(r.address), s"candidate bits mismatch $label/${r.address}")
          assert(r.mask == fullMask); assert(!committed.contains(r.address))
        } else { assert(reads.contains(r.address)); assert(r.mask == 0) }
        step(if (last) 37 else delay)
        d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
        d.io.response.bits.data.poke((if (r.write) BigInt(0) else reads(r.address)).U)
        val wrongTag = inject && (fault == "tag" || fault == "final-tag")
        d.io.response.bits.tag.poke((r.tag ^ (if (wrongTag) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((inject && !wrongTag).B)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); step(1); d.io.response.valid.poke(false.B)
        if (r.write && !inject) committed(r.address) = r.data
        issued += 1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean, s"owner timeout $label")
    val numerical = expectedNormStatus != 0 || fault == "scalar" || fault == "flags-underflow"
    val code = if (fault == "tag" || fault == "final-tag" || fault == "flags-missing") Status.Protocol
      else if (numerical) Status.Numerical else if (fault != "none") Status.Memory else Status.Ok
    d.io.done.bits.status.expect(code.U); d.io.done.bits.tag.expect(tag.U)
    d.io.done.bits.normStatus.expect((if (fault == "scalar" || fault == "flags-underflow") 4 else expectedNormStatus).U)
    d.io.done.bits.writeBytes.expect((committed.size * 64).U)
    d.io.done.bits.outputCommitted.expect((code == Status.Ok).B); d.io.memory.valid.expect(false.B)
    if (code == Status.Ok) {
      assert(committed.toMap == writes)
      assert(issued == 8 + hidden.size / 32 + writes.size, "weights must be read exactly once per job")
      assert(requests == gold.get.operations.size && results == gold.get.operations.size)
      d.io.done.bits.exceptionFlags.expect(gold.get.flags.U)
      d.io.done.bits.lastMeanEps.expect(gold.get.meanEps.U); d.io.done.bits.lastInverse.expect(gold.get.inverse.U)
    }
    if (expectedNormStatus != 0) { assert(requests == 0); d.io.done.bits.exceptionFlags.expect(0.U) }
    if (fault == "flags-underflow") assert((d.io.done.bits.exceptionFlags.peek().litValue & 2) != 0)
    val held = completion(d); step(13); assert(completion(d) == held, "completion changed under backpressure")
    println(s"QK_NORM_OWNER label=$label status=$code norm_status=${held(5)} bytes=${committed.size * 64} scalar_results=$results flags=${held(6)}")
    d.io.done.ready.poke(true.B); step(1); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((code == Status.Ok).B); d.io.resetRequired.expect((code != Status.Ok).B)
  }

  def invalidDescriptors(d: QkNorm256ArithmeticHarness): Unit = for (bad <- 0 until 19) {
    init(d); setJob(d, isQ = bad != 18, tokens = 1)
    bad match {
      case 0 => d.io.job.bits.tokens.poke(0.U)
      case 1 => d.io.job.bits.tokens.poke(129.U)
      case 2 => d.io.job.bits.role.poke(2.U)
      case 3 => d.io.job.bits.headDim.poke(128.U)
      case 4 => d.io.job.bits.policy.poke(0.U)
      case 5 => d.io.job.bits.epsilon.poke("h358637be".U)
      case 6 => d.io.job.bits.input.poke((inputBase + 2).U)
      case 7 => d.io.job.bits.weight.poke((weightBase + 2).U)
      case 8 => d.io.job.bits.output.poke((outputBase + 2).U)
      case 9 => d.io.job.bits.gateOutput.poke((gateBase + 2).U)
      case 10 => d.io.job.bits.output.poke((inputBase + 64).U)
      case 11 => d.io.job.bits.output.poke(weightBase.U)
      case 12 => d.io.job.bits.gateOutput.poke((inputBase + 64).U)
      case 13 => d.io.job.bits.gateOutput.poke(weightBase.U)
      case 14 => d.io.job.bits.gateOutput.poke((outputBase + 64).U)
      case 15 => d.io.job.bits.input.poke(((BigInt(1) << 56) - 64).U)
      case 16 => d.io.job.bits.output.poke(((BigInt(1) << 56) - 64).U)
      case 17 => d.io.job.bits.gateOutput.poke(((BigInt(1) << 56) - 64).U)
      case 18 => d.io.job.bits.gateOutput.poke(gateBase.U)
    }
    d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
    d.io.done.valid.expect(true.B); d.io.done.bits.status.expect(Status.Bounds.U)
    d.io.done.bits.normStatus.expect(1.U); d.io.done.bits.outputCommitted.expect(false.B)
    d.io.done.bits.exceptionFlags.expect(0.U); d.io.memory.valid.expect(false.B); d.io.scalarRequestFire.expect(false.B)
    d.io.done.ready.poke(true.B); d.clock.step(); d.io.done.ready.poke(false.B)
    d.io.job.ready.expect(false.B); d.io.resetRequired.expect(true.B)
  }
  def resetInFlight(d: QkNorm256ArithmeticHarness, arithmetic: Boolean): Unit = {
    init(d); setJob(d, isQ = false, tokens = 1)
    d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
    if (!arithmetic) {
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
      d.io.response.ready.expect(true.B)
    } else {
      for (_ <- 0 until 16) {
        while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
        val r = request(d)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        d.io.response.bits.data.poke(pack(Seq.fill(32)(0x3f00)).U)
        d.io.response.bits.tag.poke(r.tag.U); d.io.response.valid.poke(true.B)
        d.clock.step(); d.io.response.valid.poke(false.B)
      }
      d.io.scalarRequestFire.expect(true.B); d.clock.step()
      d.io.scalarHold.poke(true.B); d.clock.step(4)
      d.io.scalarResultAvailable.expect(true.B); d.io.done.valid.expect(false.B)
    }
    init(d); d.io.job.ready.expect(true.B); d.io.done.valid.expect(false.B)
    d.io.memory.valid.expect(false.B); d.io.scalarResultAvailable.expect(false.B); d.io.resetRequired.expect(false.B)
  }
  def resetAfterStagingWrite(d: QkNorm256ArithmeticHarness): Unit = {
    init(d); setJob(d, isQ = false, tokens = 1)
    d.io.job.valid.poke(true.B); d.clock.step(); d.io.job.valid.poke(false.B)
    for (_ <- 0 until 16) {
      while (!d.io.memory.valid.peek().litToBoolean) d.clock.step()
      val r = request(d); assert(!r.write)
      d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
      d.io.response.bits.data.poke(pack(Seq.fill(32)(0x3f00)).U)
      d.io.response.bits.tag.poke(r.tag.U); d.io.response.valid.poke(true.B)
      d.clock.step(); d.io.response.valid.poke(false.B)
    }
    while (!d.io.memory.valid.peek().litToBoolean) d.clock.step(32)
    val first = request(d)
    assert(first.write && first.address == outputBase && first.mask == fullMask)
    d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
    d.io.response.bits.tag.poke(first.tag.U); d.io.response.valid.poke(true.B)
    d.clock.step(); d.io.response.valid.poke(false.B)
    d.io.done.valid.expect(false.B); d.io.done.bits.outputCommitted.expect(false.B)
    d.io.done.bits.writeBytes.expect(64.U)
    assert(request(d).address == outputBase + 64)
    init(d); d.clock.step(7)
    d.io.job.ready.expect(true.B); d.io.done.valid.expect(false.B)
    d.io.memory.valid.expect(false.B); d.io.scalarResultAvailable.expect(false.B)
  }
}

class QkNorm256OwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with QkNorm256TestSupport {
  "QkNorm256Owner" should "match frozen integer and C nodes with one real Scalar and transactional DMA" in {
    val hidden = Seq.tabulate(256)(i => (if ((i & 1) != 0) 0x8000 else 0) | ((118 + i % 19) << 7) | (i * 17 & 127))
      .updated(0, 0).updated(1, 0x8000).updated(2, 95 << 7).updated(3, 158 << 7)
    val weight = Seq.tabulate(256)(i => (if (i % 3 == 0) 0x8000 else 0) | ((116 + i % 16) << 7) | (i * 13 & 127))
      .updated(0, 0).updated(1, 0x8000).updated(2, 0xbf80).updated(3, 0xc000)
    val gate = Seq.tabulate(256)(i => (i * 313 + 17) & 65535)
      .updated(0, 0x7f80).updated(1, 0xff80).updated(2, 0x7fc1).updated(3, 1).updated(4, 0x8000)
    val q = hidden ++ gate ++ hidden.reverse ++ gate.reverse
    val kg = reference(hidden, weight, isQ = false)
    // Keep both tokens' Q/gate layout explicit; heads differ in both norm and gate.
    val qt = q ++ q
    val qtg = reference(qt, weight, isQ = true)
    val zeros = Seq.tabulate(256)(i => if ((i & 1) == 0) 0 else 0x8000)
    val zg = reference(zeros, weight, isQ = false)
    test(new QkNorm256ArithmeticHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d); run(d, hidden, weight, false, 1, Some(kg), "K-boundary-domain")
      run(d, qt, weight, true, 2, Some(qtg), "Q-two-tokens-two-heads-opaque-gate")
      run(d, zeros, weight, false, 1, Some(zg), "signed-zeros-epsilon-rsqrt")
      for (fault <- Seq("read", "tag", "write", "final-ack", "final-tag", "scalar", "flags-missing", "flags-underflow")) {
        init(d); run(d, hidden, weight, false, 1, Some(kg), fault, fault)
      }
      init(d); run(d, qt, weight, true, 2, Some(qtg), "Q-final-gate-ack-fault", fault = "final-ack")
      for ((x, w, code, label) <- Seq(
        (hidden.updated(0, 0x7fc1), weight, 2, "nan-input"),
        (hidden.updated(0, 0xff80), weight, 2, "infinite-input"),
        (hidden.updated(0, 1), weight, 3, "subnormal-input"),
        (hidden.updated(0, 94 << 7), weight, 3, "below-domain"),
        (hidden.updated(0, 159 << 7), weight, 3, "above-domain"),
        (hidden, weight.updated(0, 0x7fc1), 2, "nan-weight"),
        (hidden, weight.updated(0, 1), 3, "subnormal-weight"),
        (hidden.updated(255, 0x7f80), weight.updated(0, 1), 2, "nonfinite-priority-over-weight-range"))) {
        init(d); run(d, x, w, false, 1, None, label, expectedNormStatus = code)
      }
      invalidDescriptors(d)
      resetInFlight(d, arithmetic = false)
      run(d, hidden, weight, false, 1, Some(kg), "memory-reset-recovered")
      resetInFlight(d, arithmetic = true)
      run(d, hidden, weight, false, 1, Some(kg), "shared-scalar-reset-recovered")
      resetAfterStagingWrite(d)
      run(d, hidden, weight, false, 1, Some(kg), "partial-staging-reset-recovered")
    }
  }
}

/** Actual production Host Q/K bytes, native model weights and full 8/2 heads.
  * Enable explicitly after materializing and pinning the fixture manifest.
  */
class QkNorm256OwnerRealSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with QkNorm256TestSupport {
  "QkNorm256Owner real Qwen3.5 layer3" should "normalize actual Host Q/K projections with frozen arithmetic" in {
    val root = Paths.get(sys.env.getOrElse("QK_NORM_OWNER_FIXTURE", throw new IllegalArgumentException("QK_NORM_OWNER_FIXTURE required")))
    def digest(raw: Array[Byte]): String = java.security.MessageDigest.getInstance("SHA-256").digest(raw).map(b => f"${b & 255}%02x").mkString
    val raw = Files.readAllBytes(root.resolve("manifest.json"))
    require(digest(raw) == sys.env.getOrElse("QK_NORM_OWNER_MANIFEST_SHA256", ""), "fixture manifest pin required")
    val manifest = ujson.read(new String(raw, java.nio.charset.StandardCharsets.UTF_8))
    require(manifest("model_revision").str == "2fc06364715b967f1860aea9cf38778875588b17" && manifest("layer_id").num == 3)
    require(manifest("framework_revision").str == "14e738b5d0cc69aa27a95dde272aea41fde44f2f")
    for ((name, metadata) <- manifest("files").obj) {
      val data = Files.readAllBytes(root.resolve(name))
      require(data.length == metadata("bytes").num && digest(data) == metadata("sha256").str, s"fixture drift $name")
    }
    test(new QkNorm256ArithmeticHarness(8, 2)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d)
      for (label <- Seq("cold0", "carried127"); isQ <- Seq(true, false)) {
        val dir = root.resolve(label)
        val input = readBf(dir.resolve(if (isQ) "packed_q.bf16le" else "k.bf16le"))
        val weightPath = dir.resolve(if (isQ) "q_gamma.bf16le" else "k_gamma.bf16le")
        val weight = readBf(weightPath)
        require(digest(Files.readAllBytes(weightPath)) == (if (isQ)
          "6fbc460e96b527aa6b54ab345195d141716dd4e34094baec92c65344f8bac298"
          else "424ead8a89f71d4e83858da7f28335665c4d61a8797b121cfaa26a56d1f5ea6a"), "original checkpoint gamma pin required")
        require(input.size == (if (isQ) 4096 else 512) && weight.size == 256)
        val gold = reference(input, weight, isQ)
        require(gold.norm == readBf(dir.resolve(if (isQ) "norm_q.bf16le" else "norm_k.bf16le")))
        if (isQ) require(gold.gate == readBf(dir.resolve("gate.bf16le")))
        run(d, input, weight, isQ, 1, Some(gold), s"actual-host-$label-${if (isQ) "Q8" else "K2"}")
      }
    }
  }
}
