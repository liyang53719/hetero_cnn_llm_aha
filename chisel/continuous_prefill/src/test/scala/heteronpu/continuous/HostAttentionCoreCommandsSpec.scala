// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Path, Paths}
import scala.sys.process._

/** CONTROL_ONLY: every owner receipt below is deliberately mocked. This checks
  * descriptor admission, real producer provenance, owner binding, completion
  * ordering and checkpoint publication. It does not run arithmetic or payload
  * DMA and does not establish numerical, physical-resource or QoR correctness.
  */
class AttentionCoreFrontendControlHarness(enabled: Boolean = true) extends HostBlockCommands(
  QwenBlockShape.qwen35Qkv(), eventSlots = 64, maxCommands = 21,
  bf16Weights = true, bf16Qkv = true, bf16QkNormRope = true, bf16AttentionCore = enabled) {
  val coreEnabled = enabled
  val committedValid = IO(Output(Bool())); committedValid := attentionCacheValid
  val committedLength = IO(Output(UInt(32.W))); committedLength := attentionLength
  val committedGeneration = IO(Output(UInt(32.W))); committedGeneration := attentionGeneration
  val committedCache = IO(Output(new DecodedTensor)); committedCache := attentionCache
  val committedContext = IO(Output(new DecodedTensor)); committedContext := attentionContext
  val committedParameters = IO(Output(Vec(6, new DecodedTensor))); committedParameters := attentionParameters
  val stagedAppend = IO(Output(Bool())); stagedAppend := pendingAttentionValid
  val stagedGqa = IO(Output(Bool())); stagedGqa := pendingGqaValid
}

class HostAttentionCoreCommandsSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val cb = BigInt(0x1000); val db = BigInt(0x2000); val nil = BigInt(0xffffff); val epoch = 7
  val hidden = BigInt(0x1000000)
  val weights = Vector(0x2000000, 0x3000000, 0x4000000).map(BigInt(_))
  val projected = Vector(0x8000000, 0x8200000, 0x8400000).map(BigInt(_))
  val gamma = Vector(0x5000000, 0x5001000).map(BigInt(_))
  val normalized = Vector(0xa000000, 0xa200000).map(BigInt(_))
  val gate = BigInt(0xb000000); val trig = BigInt(0x5200000)
  val rotated = Vector(0xc000000, 0xc200000).map(BigInt(_))
  val cache = BigInt(0xd000000); val context0 = BigInt(0xe000000); val context1 = BigInt(0xf000000)
  val score = BigInt(0x10000000); val probability = BigInt(0x11000000)
  val policyRoots = Vector(117, 130, 142, 152, 164)
  val contextRoots = Vector(118, 131, 143, 153, 165)

  case class Expected(pc: Int, kind: Int, a: BigInt, b: BigInt, c: BigInt, dst: BigInt,
    m: Int, n: Int, k: Int, bytes: BigInt, role: Int = 0, position: Int = 0, trigTokens: Int = 0,
    capacity: Int = 0, length: Int = 0, oldLength: Int = 0, queryStart: Int = 0,
    generation: BigInt = 0, cold: Boolean = false)
  case class Program(commands: Vector[BigInt], records: Vector[BigInt], expected: Vector[Expected],
    rows: Int, base: Int, count: Int, capacity: Int, oldLength: Int, generation: BigInt,
    cold: Boolean, cacheAddress: BigInt, contextAddress: BigInt)
  case class Snapshot(valid: Boolean, length: BigInt, generation: BigInt,
    cache: DecodedTensor, context: DecodedTensor, parameters: Vector[DecodedTensor])
  case class Result(status: Int, jobs: Int, completed: Int, bytes: BigInt, failedPc: Int,
    fenceHeld: Boolean = false)

  def field(word: BigInt, low: Int, width: Int, value: BigInt): BigInt = {
    require(value >= 0 && value < (BigInt(1) << width))
    (word & ~(((BigInt(1) << width) - 1) << low)) | (value << low)
  }
  def edit(p: Program, index: Int, low: Int, width: Int, value: BigInt): Program =
    p.copy(records = p.records.updated(index, field(p.records(index), low, width, value)))
  def editCommand(p: Program, index: Int, low: Int, width: Int, value: BigInt): Program =
    p.copy(commands = p.commands.updated(index, field(p.commands(index), low, width, value)))
  def select(p: Program, indices: Seq[Int]): Program = {
    val pcMap = indices.zipWithIndex.toMap
    p.copy(commands = indices.zipWithIndex.map { case (old, pc) =>
      field(field(p.commands(old), 24, 16, pc), 40, 16, pc + 1)
    }.toVector, expected = p.expected.filter(e => pcMap.contains(e.pc)).map(e => e.copy(pc = pcMap(e.pc))))
  }
  def reorder(p: Program, indices: Seq[Int]): Program = p.copy(commands = indices.zipWithIndex.map {
    case (old, pc) => field(field(p.commands(old), 24, 16, pc), 40, 16, pc + 1)
  }.toVector)

  lazy val repo: Path = sys.env.get("ATTENTION_CORE_REPO").orElse(sys.env.get("QK_NORM_REPO"))
    .map(Paths.get(_)).getOrElse(Iterator.iterate(Paths.get("").toAbsolutePath)(_.getParent)
      .takeWhile(_ != null).find(p => Files.isRegularFile(p.resolve(
        "chisel/continuous_prefill/scripts/host_bf16_qk_rope_descriptor.py")))
      .getOrElse(throw new IllegalArgumentException("ATTENTION_CORE_REPO required")))
  // Production tests default to production serializers. An isolated source
  // experiment must explicitly identify its override in the test command.
  lazy val scripts: Path = sys.env.get("ATTENTION_CORE_SCRIPT_DIR").map(Paths.get(_))
    .getOrElse(repo.resolve("chisel/continuous_prefill/scripts"))
  val serializer = """
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'src'))
import heteronpu
overlay=Path(sys.argv[2]).resolve().parents[2]/'src/heteronpu'
if overlay != Path(sys.argv[1]).resolve()/'src/heteronpu':
    heteronpu.__path__.insert(0,str(overlay))
sys.path.insert(0,str(Path(sys.argv[1])/'chisel/continuous_prefill/scripts'))
sys.path.insert(0,sys.argv[2])
from host_bf16_attention_core_descriptor import HostAttentionCoreBinding,build_host_attention_core_commands
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding,HostPartialRopeBinding
rows,base,count,capacity,old,generation,cold,cache,context=map(int,sys.argv[3:])
p=[HostQkvBinding(r,rows,base,count,0x1000000,0x2000000+r*0x1000000,0x8000000+r*0x200000) for r in range(3)]
n=[HostQkNormBinding(r,rows,base,count,p[r].output_ddr,0x5000000+r*0x1000,0xa000000+r*0x200000,0xb000000 if r==0 else 0) for r in range(2)]
r=[HostPartialRopeBinding(i,rows,base,count,n[i].output_ddr,0x5200000,0xc000000+i*0x200000,256,old) for i in range(2)]
a=HostAttentionCoreBinding(rows,base,count,capacity,old,old,generation,bool(cold),r[0].output_ddr,r[1].output_ddr,p[2].output_ddr,cache,0x10000000,0x11000000,context)
c,d=build_host_attention_core_commands(p,n,r,a)
assert len(c)==12 and len(d)==172
print(json.dumps({'commands':[str(x.pack()) for x in c],'records':[str(d[i].pack()) for i in range(len(d))]}))
"""
  def program(rows: Int = 128, base: Int = 127, count: Int = 1, capacity: Int = 256,
    oldLength: Int = 0, generation: BigInt = 0, cold: Boolean = true,
    cacheAddress: BigInt = cache, contextAddress: BigInt = context0): Program = {
    val args = Seq(rows.toString, base.toString, count.toString, capacity.toString, oldLength.toString,
      generation.toString, (if (cold) 1 else 0).toString, cacheAddress.toString, contextAddress.toString)
    val raw = (Seq("python3", "-c", serializer, repo.toString, scripts.toString) ++ args).!!
    val json = ujson.read(raw)
    val commands = json("commands").arr.map(v => BigInt(v.str)).toVector
    val records = json("records").arr.map(v => BigInt(v.str)).toVector
    val dense = (0 until 3).map { role =>
      val width = if (role == 0) 4096 else 512
      Expected(role, QwenOwnerKind.Dense, hidden + BigInt(base) * 2048, weights(role), 0,
        projected(role) + BigInt(base) * width * 2, count, width, 1024, BigInt(count) * width * 2)
    }
    val norm = (0 until 2).map { role =>
      val width = if (role == 0) 2048 else 512
      val inputWidth = if (role == 0) 4096 else 512
      Expected(3 + role, QwenOwnerKind.QkNorm256, projected(role) + BigInt(base) * inputWidth * 2,
        gamma(role), if (role == 0) gate + BigInt(base) * 4096 else BigInt(0),
        normalized(role) + BigInt(base) * width * 2, count, if (role == 0) 8 else 2, 256,
        BigInt(count) * width * 2 * (if (role == 0) 2 else 1), role, 0, 1)
    }
    val rope = (0 until 2).map { role =>
      val width = if (role == 0) 2048 else 512
      Expected(5 + role, QwenOwnerKind.PartialRope64, normalized(role) + BigInt(base) * width * 2,
        trig, 0, rotated(role) + BigInt(base) * width * 2, count, if (role == 0) 8 else 2,
        256, BigInt(count) * width * 2, role, oldLength, 256)
    }
    val append = Expected(7, QwenOwnerKind.KvAppend, rotated(1) + BigInt(base) * 1024,
      projected(2) + BigInt(base) * 1024, 0, cacheAddress, count, 512, 256, BigInt(count) * 2048,
      capacity = capacity, length = oldLength, oldLength = oldLength, queryStart = oldLength,
      generation = generation, cold = cold)
    val gqa = Expected(10, QwenOwnerKind.Attention, rotated(0) + BigInt(base) * 4096,
      cacheAddress, 0, contextAddress + BigInt(base) * 4096, count, 2048, 256, BigInt(count) * 4096,
      capacity = capacity, length = oldLength + count, oldLength = oldLength, queryStart = oldLength,
      generation = generation, cold = cold)
    val p = Program(commands, records, (dense ++ norm ++ rope ++ Seq(append, gqa)).toVector,
      rows, base, count, capacity, oldLength, generation, cold, cacheAddress, contextAddress)
    commands.map(c => (c & 255).toInt) shouldBe Vector(0x20, 0x20, 0x20, 0x32, 0x32, 0x34, 0x34, 0x41, 0x23, 0x33, 0x24, 0x30)
    commands.drop(7).map(c => ((c >> 8) & 7).toInt) shouldBe Vector(4, 2, 3, 2, 3)
    commands.map(c => ((c >> 56) & nil).toInt) shouldBe Vector(0, 21, 42, 63, 78, 90, 102, 114, 125, 138, 147, 160)
    p.expected.map(_.bytes).sum shouldBe BigInt(count) * 30720
    p
  }

  def snapshot(d: AttentionCoreFrontendControlHarness): Snapshot = Snapshot(
    d.committedValid.peek().litToBoolean, d.committedLength.peek().litValue,
    d.committedGeneration.peek().litValue, d.committedCache.peek(), d.committedContext.peek(),
    (0 until 6).map(i => d.committedParameters(i).peek()).toVector)
  def unchanged(d: AttentionCoreFrontendControlHarness, saved: Snapshot): Unit = {
    d.committedValid.expect(saved.valid.B); d.committedLength.expect(saved.length.U)
    d.committedGeneration.expect(saved.generation.U)
    // Cache/context registers deliberately have no reset value. Once captured,
    // even their complete allocation metadata must remain stable until commit.
    d.committedCache.expect(saved.cache); d.committedContext.expect(saved.context)
    for (i <- 0 until 6) d.committedParameters(i).expect(saved.parameters(i))
  }
  def setup(d: AttentionCoreFrontendControlHarness, p: Program, doReset: Boolean): Unit = {
    d.clock.setTimeout(3000000)
    d.io.launch.valid.poke(false.B); d.io.result.ready.poke(false.B); d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B); d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U); d.io.done.bits.status.poke(0.U); d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U); d.io.done.bits.usefulMacs.poke(0.U); d.io.done.bits.executedMacs.poke(0.U)
    if (doReset) {
      d.reset.poke(true.B); d.clock.step(2); d.reset.poke(false.B)
      d.committedValid.expect(false.B); d.committedLength.expect(0.U); d.committedGeneration.expect(0.U)
      d.stagedAppend.expect(false.B); d.stagedGqa.expect(false.B)
    }
    val l = d.io.launch.bits
    l.commandBase.poke(cb.U); l.commandLimit.poke((cb + 0x1000).U); l.commands.poke(p.commands.size.U)
    l.descriptorBase.poke(db.U); l.descriptorLimit.poke((db + 0x2000).U); l.descriptors.poke(p.records.size.U)
    l.epoch.poke(epoch.U)
    for ((r, i) <- Seq((cb, BigInt(0x4000), true, false),
      (hidden, BigInt(0x6000000), true, false), (projected(0), BigInt(0x12000000), true, true),
      (BigInt(0), BigInt(0), false, false)).zipWithIndex) {
      l.regions(i).base.poke(r._1.U); l.regions(i).limit.poke(r._2.U)
      l.regions(i).read.poke(r._3.B); l.regions(i).write.poke(r._4.B)
    }
  }

  // Fault 1: failing status; 2: wrong tag; 3/4: short/long successful ACK;
  // 5: failing status after one cache span (or a partial final context write).
  def run(d: AttentionCoreFrontendControlHarness, p: Program, doReset: Boolean = true,
    faultJob: Int = -1, fault: Int = 0, acceptFence: Boolean = true,
    mutatePins: Boolean = true): Result = {
    setup(d, p, doReset)
    var committed = snapshot(d)
    d.io.launch.ready.expect(true.B); d.io.launch.valid.poke(true.B); d.clock.step(); d.io.launch.valid.poke(false.B)
    if (mutatePins) {
      d.io.launch.bits.commandBase.poke(0.U); d.io.launch.bits.descriptorBase.poke(0.U)
      d.io.launch.bits.epoch.poke(99.U); d.io.launch.bits.commands.poke(1.U); d.io.launch.bits.descriptors.poke(1.U)
      d.io.launch.bits.regions(1).read.poke(false.B); d.io.launch.bits.regions(2).write.poke(false.B)
    }
    var jobs = 0; var completed = 0; var ticks = 0; var written = BigInt(0)
    var failedCompletionPc = -1
    while (!d.io.result.valid.peek().litToBoolean && ticks < 16000) {
      unchanged(d, committed)
      if (d.io.memory.valid.peek().litToBoolean) {
        val address = d.io.memory.bits.address.peek().litValue; val tag = d.io.memory.bits.tag.peek().litValue
        assert(address >= cb && address < db + 0x2000, "CONTROL_ONLY frontend requested payload DDR")
        d.io.memory.bits.write.expect(false.B); d.io.memory.bits.mask.expect(0.U)
        d.clock.step(2); unchanged(d, committed)
        d.io.memory.bits.address.expect(address.U); d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        val isCommand = address < db; val table = if (isCommand) p.commands else p.records
        val offset = ((address - (if (isCommand) cb else db)) / 16).toInt
        val data = (0 until 4).map(i => table.lift(offset + i).getOrElse(BigInt(0)) << (128 * i)).reduce(_ | _)
        d.io.response.bits.data.poke(data.U); d.io.response.bits.tag.poke(tag.U)
        d.io.response.valid.poke(true.B); d.io.response.ready.expect(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      } else if (d.io.job.valid.peek().litToBoolean) {
        assert(jobs < p.expected.size, "QK, Softmax and Fence must not create extra owner jobs")
        val e = p.expected(jobs); val tag = (BigInt(epoch) << 16) | e.pc
        val j = d.io.job.bits
        d.io.pc.expect(e.pc.U)
        for ((actual, value) <- Seq(j.kind -> BigInt(e.kind), j.a -> e.a, j.b -> e.b, j.c -> e.c,
          j.dst -> e.dst, j.m -> BigInt(e.m), j.n -> BigInt(e.n), j.k -> BigInt(e.k),
          j.writeBytes -> e.bytes, j.tag -> tag, j.qkRole -> BigInt(e.role),
          j.qkPositionBase -> BigInt(e.position), j.qkTrigTokens -> BigInt(e.trigTokens),
          j.cacheCapacity -> BigInt(e.capacity), j.cacheLength -> BigInt(e.length),
          j.expectedCacheLength -> BigInt(e.oldLength), j.queryStart -> BigInt(e.queryStart),
          j.expectedGeneration -> e.generation, j.currentGeneration -> e.generation)) actual.expect(value.U)
        j.cold.expect(e.cold.B)
        j.activationBf16.expect(true.B); j.weightBf16.expect(true.B); j.outputBf16.expect(true.B)
        for (unused <- Seq(j.historyOut, j.gdnALog, j.gdnDtBias, j.gdnStateOut, j.gdnElementwiseOp)) unused.expect(0.U)
        j.gdnRecurrentMode.expect(false.B)
        if (e.kind == QwenOwnerKind.Attention) {
          completed shouldBe 8 // None of QK/Softmax/PV completes before this receipt.
          d.stagedAppend.expect(true.B); d.stagedGqa.expect(false.B)
          j.a.peek().litValue should not be score; j.a.peek().litValue should not be probability
          j.b.peek().litValue shouldBe p.cacheAddress
        }
        val bound = j.peek()
        for (_ <- 0 until 4) {
          unchanged(d, committed); j.expect(bound); d.io.completion.valid.expect(false.B)
          d.io.memory.valid.expect(false.B); d.clock.step()
        }
        d.io.job.ready.poke(true.B); d.clock.step(); d.io.job.ready.poke(false.B)
        // Inactive result pins, including an apparently successful byte count,
        // do not complete a command or publish any checkpoint.
        d.io.done.bits.tag.poke(tag.U); d.io.done.bits.status.poke(Status.Ok.U); d.io.done.bits.writeBytes.poke(e.bytes.U)
        for (_ <- 0 until 6) {
          unchanged(d, committed); d.io.completion.valid.expect(false.B)
          d.io.job.valid.expect(false.B); d.io.memory.valid.expect(false.B); d.io.writeBytes.expect(written.U); d.clock.step()
        }
        val f = if (jobs == faultJob) fault else 0
        val reported = if (f == 3) e.bytes - 64 else if (f == 4) e.bytes + 64 else if (f == 5) {
          if (e.kind == QwenOwnerKind.KvAppend) e.bytes / 2 else e.bytes - 64
        } else e.bytes
        d.io.done.bits.tag.poke((tag ^ (if (f == 2) BigInt(1) else BigInt(0))).U)
        d.io.done.bits.status.poke((if (f == 1 || f == 5) Status.Memory else Status.Ok).U)
        d.io.done.bits.writeBytes.poke(reported.U); d.io.done.valid.poke(true.B)
        d.io.done.ready.expect(true.B); d.clock.step(); d.io.done.valid.poke(false.B)
        if (f == 0) written += e.bytes
        jobs += 1
      } else if (d.io.completion.valid.peek().litToBoolean) {
        val word = d.io.completion.bits.peek().litValue
        val pc = (word & ((BigInt(1) << 29) - 1)).toInt
        val ok = ((word >> 32) & 255) == Status.Ok
        pc should be < p.commands.size
        val command = p.commands(pc)
        ((word >> 29) & 7) shouldBe ((command >> 8) & 7)
        (word >> 40) shouldBe ((command >> 40) & 65535)
        if (ok) pc shouldBe completed else failedCompletionPc = pc
        d.io.writeBytes.expect(written.U)
        val fence = ok && pc == 11 && p.commands.size == 12
        if (fence) {
          jobs shouldBe 9; completed shouldBe 11
          d.stagedAppend.expect(true.B); d.stagedGqa.expect(true.B)
        }
        for (_ <- 0 until (if (fence) 24 else 4)) {
          unchanged(d, committed); d.io.completion.bits.expect(word.U)
          d.io.job.valid.expect(false.B); d.io.memory.valid.expect(false.B); d.io.result.valid.expect(false.B); d.clock.step()
        }
        if (fence && !acceptFence) return Result(Status.Ok, jobs, completed, written, -1, fenceHeld = true)
        d.io.completion.ready.poke(true.B); d.clock.step(); d.io.completion.ready.poke(false.B)
        if (ok) completed += 1
        if (fence) {
          d.committedValid.expect(true.B); d.committedLength.expect((p.oldLength + p.count).U)
          d.committedGeneration.expect((p.generation + 1).U)
          d.committedCache.address.expect(p.cacheAddress.U); d.committedCache.rank.expect(3.U)
          d.committedCache.dtype.expect(5.U); d.committedCache.dims(0).expect(2.U)
          d.committedCache.dims(1).expect(p.capacity.U); d.committedCache.dims(2).expect(512.U)
          d.committedCache.payloadBytes.expect((BigInt(p.capacity) * 2048).U)
          d.committedCache.paddedEnd.expect((p.cacheAddress + BigInt(p.capacity) * 2048).U)
          d.committedContext.address.expect(p.contextAddress.U); d.committedContext.rank.expect(2.U)
          d.committedContext.dtype.expect(5.U); d.committedContext.dims(0).expect(p.rows.U)
          d.committedContext.dims(1).expect(2048.U)
          d.committedContext.payloadBytes.expect((BigInt(p.rows) * 4096).U)
          d.committedContext.paddedEnd.expect((p.contextAddress + BigInt(p.rows) * 4096).U)
          for ((address, index) <- (weights ++ gamma ++ Vector(trig)).zipWithIndex)
            d.committedParameters(index).address.expect(address.U)
          d.stagedAppend.expect(false.B); d.stagedGqa.expect(false.B)
          committed = snapshot(d)
        }
        unchanged(d, committed)
      } else d.clock.step()
      ticks += 1
    }
    d.io.result.valid.expect(true.B); d.io.result.bits.epoch.expect(epoch.U)
    d.io.result.bits.completed.expect(completed.U); d.io.issuedJobs.expect(jobs.U); d.io.writeBytes.expect(written.U)
    val status = d.io.result.bits.status.peek().litValue.toInt
    val failedPc = d.io.result.bits.failedPc.peek().litValue.toInt
    if (failedCompletionPc >= 0) failedPc shouldBe failedCompletionPc
    // An invalid launch count fails admission before any command executes.
    // Existing Host admission returns Bounds without poisoning the frontend.
    val launchRejected = d.coreEnabled && p.commands.size != 12
    if (launchRejected) {
      status shouldBe Status.Bounds; jobs shouldBe 0; completed shouldBe 0
    }
    d.io.resetRequired.expect((status != Status.Ok && !launchRejected).B)
    for (_ <- 0 until 4) {
      unchanged(d, committed); d.io.result.bits.status.expect(status.U)
      d.io.result.bits.completed.expect(completed.U); d.io.result.bits.failedPc.expect(failedPc.U)
      d.io.memory.valid.expect(false.B); d.io.job.valid.expect(false.B); d.clock.step()
    }
    d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
    d.io.launch.ready.expect((status == Status.Ok || launchRejected).B)
    Result(status, jobs, completed, written, failedPc)
  }

  def success(r: Result, count: Int = 1): Unit = {
    r.status shouldBe Status.Ok; r.jobs shouldBe 9; r.completed shouldBe 12
    r.bytes shouldBe BigInt(count) * 30720; r.fenceHeld shouldBe false
  }
  def reject(d: AttentionCoreFrontendControlHarness, p: Program, owners: Int, completions: Int,
    pc: Int, label: String, doReset: Boolean = true, exact: Option[Int] = None): Unit = withClue(label + ": ") {
    val r = run(d, p, doReset = doReset)
    r.status should not be Status.Ok; r.jobs shouldBe owners; r.completed shouldBe completions
    r.failedPc shouldBe pc; r.bytes shouldBe p.expected.take(owners).map(_.bytes).sum
    exact.foreach(s => r.status shouldBe s)
  }

  "Host BF16 Attention core CONTROL_ONLY" should "carry only accepted checkpoints through real producer receipts and a terminal fence" in {
    val cold = program()
    val carry = program(oldLength = 1, generation = 1, cold = false, contextAddress = context1)
    test(new AttentionCoreFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      success(run(d, cold))
      success(run(d, carry, doReset = false))
      // The former context allocation becomes reusable only after replacement
      // by an accepted fence. The cache allocation remains exactly the same.
      success(run(d, program(oldLength = 2, generation = 2, cold = false), doReset = false))
      val signals = Vector(3, 5, 8, 13, 21, 22, 25, 31, 33, 34, 37, 41)
      val nonconsecutive = cold.copy(commands = cold.commands.zipWithIndex.map { case (c, pc) =>
        field(field(c, 24, 16, if (pc == 0) 0 else signals(pc - 1)), 40, 16, signals(pc))
      })
      success(run(d, nonconsecutive))
      // The same admission and byte accounting applies to the full M128 window.
      success(run(d, program(base = 0, count = 128)), 128)
      success(run(d, program(base = 0, count = 128, oldLength = 128, generation = 1,
        cold = false, contextAddress = context1), doReset = false), 128)

      success(run(d, cold))
      val stalled = run(d, carry, doReset = false, acceptFence = false)
      stalled.fenceHeld shouldBe true; stalled.jobs shouldBe 9; stalled.completed shouldBe 11
      d.committedLength.expect(1.U); d.committedGeneration.expect(1.U)
      d.committedCache.address.expect(cache.U); d.committedContext.address.expect(context0.U)
      // A shared reset invalidates this checkpoint. Replaying its metadata is
      // not a restoration protocol, even after every previous owner ACKed.
      reject(d, carry, 5, 5, 5, "reset-cannot-import-carried-checkpoint", exact = Some(Status.Dependency))

      for (owner <- Seq(7, 8); fault <- 1 to 5) {
        success(run(d, cold))
        val r = run(d, carry, doReset = false, faultJob = owner, fault = fault)
        r.status shouldBe (if (fault == 1 || fault == 5) Status.Memory else Status.Protocol)
        r.jobs shouldBe owner + 1; r.completed shouldBe 8.min(owner)
        r.failedPc shouldBe (if (owner == 7) 7 else 10)
        r.bytes shouldBe carry.expected.take(owner).map(_.bytes).sum
        d.committedValid.expect(true.B); d.committedLength.expect(1.U); d.committedGeneration.expect(1.U)
        d.committedCache.address.expect(cache.U); d.committedContext.address.expect(context0.U)
        d.stagedAppend.expect(false.B); d.stagedGqa.expect(false.B)
      }
      // Cold partial append failure cannot manufacture a durable context.
      val partial = run(d, cold, faultJob = 7, fault = 5)
      partial.status shouldBe Status.Memory; partial.jobs shouldBe 8; partial.completed shouldBe 7
      d.committedValid.expect(false.B); d.committedLength.expect(0.U); d.committedGeneration.expect(0.U)
      println("HOST_ATTENTION_CORE_CONTROL cold_carried_fence_stall_owner_fault_partial_append_reset=PASS numeric=false")
    }
  }

  it should "reject altered snapshots and all malformed arithmetic phases before the affected owner" in {
    val cold = program()
    val carry = program(oldLength = 1, generation = 1, cold = false, contextAddress = context1)
    test(new AttentionCoreFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      // Strict semantic producer order cannot be replaced by an earlier event,
      // a descriptor's position, or a writable tensor with the expected shape.
      reject(d, reorder(cold, Vector(1, 0) ++ (2 until 12)), 0, 0, 0, "K-before-Q-Dense")
      reject(d, reorder(cold, (0 until 3) ++ Vector(4, 3) ++ (5 until 12)), 3, 3, 3, "K-before-Q-Norm")
      reject(d, reorder(cold, (0 until 5) ++ Vector(6, 5) ++ (7 until 12)), 5, 5, 5, "K-before-Q-RoPE")
      reject(d, editCommand(cold, 7, 24, 16, 1), 7, 7, 7, "append-skips-producer-event", exact = Some(Status.Dependency))
      for ((root, address, pc) <- Seq((114, BigInt(0x5800000), 7), (119, projected(1), 7),
        (125, normalized(0), 8), (132, cache + 64, 8), (138, probability, 9),
        (147, score, 10), (154, cache + 64, 10))) {
        val owners = if (pc == 7) 7 else 8
        reject(d, edit(cold, root, 56, 48, address), owners, owners, pc, s"unproduced-source-$root")
      }
      for (root <- Seq(95, 107))
        reject(d, edit(cold, root, 80, 32, 1), if (root == 95) 5 else 6,
          if (root == 95) 5 else 6, if (root == 95) 5 else 6, s"RoPE-position-$root", exact = Some(Status.Dependency))

      // Every append snapshot dimension is checked against the real committed
      // cache and current producer window before the append owner can run.
      val snapshots = Seq(
        (122, 56, 48, cache + 0x100000, "root"), (118, 64, 9, BigInt(128), "capacity"),
        (118, 73, 9, BigInt(0), "length"), (118, 82, 9, BigInt(0), "query-start"),
        (118, 91, 32, BigInt(2), "generation"), (118, 123, 1, BigInt(1), "cold"),
        (122, 108, 4, BigInt(7), "dtype"), (122, 116, 4, BigInt(2), "rank"),
        (123, 92, 18, BigInt(256), "shape"), (124, 56, 24, BigInt(512), "stride"),
        (117, 68, 32, BigInt(126), "window-base"), (117, 100, 8, BigInt(2), "window-count"))
      for ((i, low, width, value, label) <- snapshots) {
        success(run(d, cold))
        reject(d, edit(carry, i, low, width, value), 7, 7, 7, s"carried-snapshot-$label", doReset = false)
      }
      // Prior cache and the FULL prior context are protected before the first
      // new Dense. Its active row is outside the context's inactive prefix.
      for (target <- Seq(cache, context0)) {
        success(run(d, cold))
        reject(d, edit(carry, 18, 56, 48, target), 0, 0, 0,
          s"producer-overwrites-committed-allocation-$target", doReset = false, exact = Some(Status.Permission))
      }
      for ((root, address, pc) <- Seq((15, weights(0) + 64, 0), (69, gamma(0) + 64, 3), (96, trig + 64, 5))) {
        success(run(d, cold))
        reject(d, edit(carry, root, 56, 48, address), pc, pc, pc,
          s"carried-parameter-identity-$root", doReset = false)
      }
      // Equal address, byte size and paddedEnd do not make different typed
      // trig geometry equivalent to the committed [256,64] allocation.
      success(run(d, cold))
      val reshapedTrig = edit(edit(edit(carry, 97, 56, 18, 128), 97, 74, 18, 128), 98, 56, 24, 128)
      reject(d, reshapedTrig, 5, 5, 5, "carried-trig-same-span-wrong-shape", doReset = false)
      // Hidden may move between calls, but cannot become a committed parameter.
      success(run(d, cold))
      val hiddenAsParameter = Seq(0, 21, 42).foldLeft(carry)((p, i) => edit(p, i, 56, 48, trig))
      reject(d, hiddenAsParameter, 0, 0, 0, "hidden-overlaps-committed-trig", doReset = false)
      success(run(d, cold))
      reject(d, program(oldLength = 1, generation = 1, cold = false, contextAddress = context0),
        8, 8, 10, "PV-overwrites-current-context", doReset = false, exact = Some(Status.Permission))

      val phaseEdits = Seq(
        (117, 56, 8, BigInt(1), 7), (117, 64, 4, BigInt(4), 7), (117, 108, 8, BigInt(0xa1), 7),
        (118, 124, 1, BigInt(0), 7), (118, 125, 3, BigInt(1), 7), (118, 91, 32, BigInt("ffffffff", 16), 7),
        (128, 115, 1, BigInt(0), 8), (129, 56, 24, BigInt(0), 8), (130, 108, 8, BigInt(0), 8),
        (131, 91, 32, BigInt(1), 8), (135, 108, 4, BigInt(7), 8), (136, 56, 18, BigInt(2), 8),
        (141, 72, 8, BigInt(2), 9), (142, 64, 4, BigInt(1), 9), (143, 64, 9, BigInt(128), 9),
        (144, 108, 4, BigInt(7), 9), (145, 74, 18, BigInt(2), 9),
        (150, 115, 1, BigInt(1), 10), (151, 56, 24, BigInt(0), 10), (152, 108, 8, BigInt(0xb1), 10),
        (153, 82, 9, BigInt(1), 10), (157, 56, 48, context0 + 2, 10), (158, 74, 18, BigInt(512), 10),
        (163, 72, 8, BigInt(1), 11), (164, 108, 8, BigInt(0xa1), 11), (165, 91, 32, BigInt(1), 11),
        (160, 56, 48, cache + 64, 11), (166, 56, 48, normalized(0), 11), (169, 56, 48, context1, 11))
      for ((i, low, width, value, pc) <- phaseEdits) {
        val owners = if (pc == 7) 7 else if (pc == 11) 9 else 8
        val completions = if (pc == 11) 11 else owners
        reject(d, edit(cold, i, low, width, value), owners, completions, pc, s"phase-$pc-record-$i-bit-$low")
      }
      // Reserved bits and malformed/cyclic tails are rejected in every phase.
      for ((root, phase) <- policyRoots.zipWithIndex) {
        val pc = phase + 7; val owners = if (pc == 7) 7 else if (pc == 11) 9 else 8
        val completions = if (pc == 11) 11 else owners
        reject(d, edit(cold, root, 127, 1, 1), owners, completions, pc, s"reserved-policy-$pc")
        reject(d, edit(cold, root, 32, 24, root), owners, completions, pc, s"cyclic-policy-$pc")
        reject(d, edit(cold, contextRoots(phase), 32, 24, root), owners, completions, pc, s"context-nonterminal-$pc")
      }
      for ((pc, engine) <- Seq((7, 2), (8, 3), (9, 2), (10, 3), (11, 2))) {
        val owners = if (pc == 7) 7 else if (pc == 11) 9 else 8
        reject(d, editCommand(cold, pc, 8, 3, engine), owners, if (pc == 11) 11 else owners,
          pc, s"wrong-engine-$pc", exact = Some(Status.Unsupported))
      }
      val missingFence = run(d, cold.copy(commands = cold.commands.dropRight(1)))
      missingFence.status should not be Status.Ok; missingFence.jobs shouldBe 0; missingFence.completed shouldBe 0
      d.committedValid.expect(false.B)
      success(run(d, cold))
      println("HOST_ATTENTION_CORE_CONTROL snapshots_phase_prevalidation_full_allocation_protection=PASS numeric=false")
    }
  }

  it should "remain default off while preserving the seven existing QKV Norm RoPE owners" in {
    val p = program()
    test(new AttentionCoreFrontendControlHarness(enabled = false)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      for (pc <- 7 until 12)
        reject(d, select(p, Seq(pc)), 0, 0, 0, s"default-off-opcode-$pc", exact = Some(Status.Unsupported))
      reject(d, p, 7, 7, 7, "default-off-after-seven-real-producers", exact = Some(Status.Unsupported))
      val legacy = run(d, select(p, 0 until 7))
      legacy.status shouldBe Status.Ok; legacy.jobs shouldBe 7; legacy.completed shouldBe 7; legacy.bytes shouldBe 24576
      d.committedValid.expect(false.B); d.committedLength.expect(0.U); d.committedGeneration.expect(0.U)
      println("HOST_ATTENTION_CORE_CONTROL default_off_existing_seven_owners=PASS numeric=false")
    }
  }
}
