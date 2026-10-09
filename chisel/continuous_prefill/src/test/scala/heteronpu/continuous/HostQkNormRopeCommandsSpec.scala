// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Path, Paths}
import scala.sys.process._

/** Production Host frontend CONTROL ONLY. Typed metadata comes from the public
  * Python serializer; owner completion is a deliberate test double. This gate
  * proves binding, dependency, permissions and publication. It does not execute
  * Dense, Norm, RoPE, payload DMA or their write ACKs, and makes no numeric claim.
  */
class HostQkNormRopeCommandsSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val commandBase = BigInt(0x1000)
  val descriptorBase = BigInt(0x2000)
  val hidden = BigInt(0x1000000)
  val weights = Vector(0x2000000, 0x3000000, 0x4000000).map(BigInt(_))
  val projected = Vector(0x8000000, 0x8200000, 0x8400000).map(BigInt(_))
  val gamma = Vector(0x5000000, 0x5001000).map(BigInt(_))
  val normalized = Vector(0xa000000, 0xa200000).map(BigInt(_))
  val gate = BigInt(0xb000000)
  val trig = BigInt(0x5200000)
  val rotated = Vector(0xc000000, 0xc200000).map(BigInt(_))
  val nullIndex = BigInt(0xffffff)
  val epoch = 7
  case class Expected(kind: Int, a: BigInt, b: BigInt, c: BigInt, dst: BigInt,
                      m: Int, n: Int, k: Int, bytes: BigInt, role: Int = 0,
                      position: Int = 0, trigTokens: Int = 0)
  case class Program(commands: Vector[BigInt], records: Vector[BigInt], expected: Vector[Expected])
  case class Result(status: Int, jobs: Int, completions: Int, bytes: BigInt, failedPc: Int)
  def field(word: BigInt, low: Int, width: Int, value: BigInt): BigInt =
    (word & ~(((BigInt(1) << width) - 1) << low)) | (value << low)
  def edit(p: Program, index: Int, low: Int, width: Int, value: BigInt): Program =
    p.copy(records = p.records.updated(index, field(p.records(index), low, width, value)))
  def editCommand(p: Program, index: Int, low: Int, width: Int, value: BigInt): Program =
    p.copy(commands = p.commands.updated(index, field(p.commands(index), low, width, value)))
  def select(p: Program, commands: Seq[Int]): Program = p.copy(
    commands = commands.zipWithIndex.map { case (old, index) =>
      field(field(p.commands(old), 24, 16, index), 40, 16, index + 1)
    }.toVector, expected = commands.map(p.expected).toVector)

  lazy val repo: Path = sys.env.get("QK_NORM_REPO").map(Paths.get(_)).getOrElse(
    Iterator.iterate(Paths.get("").toAbsolutePath)(_.getParent).takeWhile(_ != null)
      .find(p => Files.isRegularFile(p.resolve("chisel/continuous_prefill/scripts/host_bf16_qk_rope_descriptor.py")))
      .getOrElse(throw new IllegalArgumentException("QK_NORM_REPO required")))
  val serializer = """
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'chisel/continuous_prefill/scripts'))
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding,HostPartialRopeBinding,build_host_qkv_rope_commands
rows,base,count,position=map(int,sys.argv[2:])
p=[HostQkvBinding(r,rows,base,count,0x1000000,0x2000000+r*0x1000000,0x8000000+r*0x200000) for r in range(3)]
n=[HostQkNormBinding(r,rows,base,count,p[r].output_ddr,0x5000000+r*0x1000,0xa000000+r*0x200000,0xb000000 if r==0 else 0) for r in range(2)]
q=[HostPartialRopeBinding(r,rows,base,count,n[r].output_ddr,0x5200000,0xc000000+r*0x200000,256,position) for r in range(2)]
c,d=build_host_qkv_rope_commands(p,n,q)
assert len(c)==7 and len(d)==114
print(json.dumps({'commands':[str(x.pack()) for x in c],'records':[str(d[i].pack()) for i in range(114)]}))
"""
  def program(rows: Int = 128, base: Int = 127, count: Int = 1, position: Int = 255): Program = {
    val raw = Seq("python3", "-c", serializer, repo.toString, rows.toString, base.toString, count.toString, position.toString).!!
    val data = ujson.read(raw)
    val commands = data("commands").arr.map(v => BigInt(v.str)).toVector
    val records = data("records").arr.map(v => BigInt(v.str)).toVector
    val dense = (0 until 3).map { role =>
      val n = if (role == 0) 4096 else 512
      Expected(QwenOwnerKind.Dense, hidden + base * 2048, weights(role), 0,
        projected(role) + BigInt(base) * n * 2, count, n, 1024, BigInt(count) * n * 2)
    }
    val norm = (0 until 2).map { role =>
      val width = if (role == 0) 2048 else 512
      val inputWidth = if (role == 0) 4096 else 512
      Expected(QwenOwnerKind.QkNorm256, projected(role) + BigInt(base) * inputWidth * 2,
        gamma(role), if (role == 0) gate + base * 4096 else BigInt(0), normalized(role) + BigInt(base) * width * 2,
        count, if (role == 0) 8 else 2, 256, BigInt(count) * width * 2 * (if (role == 0) 2 else 1),
        role, 0, 1)
    }
    val rope = (0 until 2).map { role =>
      val width = if (role == 0) 2048 else 512
      Expected(QwenOwnerKind.PartialRope64, normalized(role) + BigInt(base) * width * 2, trig, 0,
        rotated(role) + BigInt(base) * width * 2, count, if (role == 0) 8 else 2, 256,
        BigInt(count) * width * 2, role, position, 256)
    }
    val p = Program(commands, records, (dense ++ norm ++ rope).toVector)
    assert(commands.size == 7 && records.size == 114 && p.expected.map(_.bytes).sum == BigInt(count) * 24576)
    assert(commands.map(c => ((c >> 56) & nullIndex).toInt) == Vector(0, 21, 42, 63, 78, 90, 102))
    p
  }
  def initialize(d: HostBlockCommands, p: Program): Unit = {
    d.clock.setTimeout(3000000)
    d.io.launch.valid.poke(false.B); d.io.result.ready.poke(false.B); d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U); d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B); d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U); d.io.done.bits.status.poke(0.U); d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U); d.io.done.bits.usefulMacs.poke(0.U); d.io.done.bits.executedMacs.poke(0.U)
    d.reset.poke(true.B); d.clock.step(2); d.reset.poke(false.B)
    val launch = d.io.launch.bits
    launch.commandBase.poke(commandBase.U); launch.commandLimit.poke((commandBase + 0x1000).U); launch.commands.poke(p.commands.size.U)
    launch.descriptorBase.poke(descriptorBase.U); launch.descriptorLimit.poke((descriptorBase + 0x2000).U); launch.descriptors.poke(p.records.size.U)
    launch.epoch.poke(epoch.U)
    for ((region, index) <- Seq((commandBase, BigInt(0x4000), true, false),
      (hidden, BigInt(0x6000000), true, false), (projected(0), BigInt(0xe000000), true, true),
      (BigInt(0), BigInt(0), false, false)).zipWithIndex) {
      launch.regions(index).base.poke(region._1.U); launch.regions(index).limit.poke(region._2.U)
      launch.regions(index).read.poke(region._3.B); launch.regions(index).write.poke(region._4.B)
    }
  }
  def run(d: HostBlockCommands, p: Program, faultAt: Int = -1, doneFault: Int = 0,
          readFault: Int = 0, mutatePins: Boolean = true): Result = {
    initialize(d, p)
    d.io.launch.valid.poke(true.B); d.io.launch.ready.expect(true.B); d.clock.step(); d.io.launch.valid.poke(false.B)
    if (mutatePins) {
      d.io.launch.bits.commandBase.poke(0.U); d.io.launch.bits.descriptorBase.poke(0.U)
      d.io.launch.bits.epoch.poke(99.U); d.io.launch.bits.commands.poke(1.U); d.io.launch.bits.descriptors.poke(1.U)
      d.io.launch.bits.regions(1).read.poke(false.B); d.io.launch.bits.regions(2).write.poke(false.B)
    }
    var jobs = 0; var completed = 0; var accepted = 0; var iterations = 0; var bytes = BigInt(0)
    while (!d.io.result.valid.peek().litToBoolean && iterations < 7000) {
      if (d.io.memory.valid.peek().litToBoolean) {
        val address = d.io.memory.bits.address.peek().litValue
        val requestTag = d.io.memory.bits.tag.peek().litValue
        assert((address >= commandBase && address < commandBase + 0x1000) ||
          (address >= descriptorBase && address < descriptorBase + 0x2000), "frontend must not access payload DDR")
        d.io.memory.bits.write.expect(false.B); d.io.memory.bits.mask.expect(0.U)
        d.clock.step(2); d.io.memory.bits.address.expect(address.U); d.io.memory.bits.tag.expect(requestTag.U)
        d.io.memory.ready.poke(true.B); d.clock.step(); d.io.memory.ready.poke(false.B)
        val commands = address < descriptorBase
        val table = if (commands) p.commands else p.records
        val offset = ((address - (if (commands) commandBase else descriptorBase)) / 16).toInt
        val data = (0 until 4).map(i => table.lift(offset + i).getOrElse(BigInt(0)) << (128 * i)).reduce(_ | _)
        d.io.response.bits.data.poke(data.U); d.io.response.bits.tag.poke((requestTag ^ (if (readFault == 2) BigInt(1) else BigInt(0))).U)
        d.io.response.bits.error.poke((readFault == 1).B); d.io.response.valid.poke(true.B)
        d.io.response.ready.expect(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
      } else if (d.io.job.valid.peek().litToBoolean) {
        val e = p.expected(jobs); val ownerTag = BigInt(epoch << 16) | jobs
        val j = d.io.job.bits
        for ((actual, expected) <- Seq(j.kind -> BigInt(e.kind), j.a -> e.a, j.b -> e.b, j.c -> e.c, j.dst -> e.dst,
          j.m -> BigInt(e.m), j.n -> BigInt(e.n), j.k -> BigInt(e.k), j.writeBytes -> e.bytes, j.tag -> ownerTag,
          j.qkRole -> BigInt(e.role), j.qkPositionBase -> BigInt(e.position), j.qkTrigTokens -> BigInt(e.trigTokens))) actual.expect(expected.U)
        j.activationBf16.expect(true.B); j.weightBf16.expect(true.B); j.outputBf16.expect(true.B)
        for (unused <- Seq(j.historyOut, j.expectedGeneration, j.currentGeneration, j.gdnALog, j.gdnDtBias, j.gdnStateOut, j.gdnElementwiseOp)) unused.expect(0.U)
        j.cold.expect(false.B); j.gdnRecurrentMode.expect(false.B)
        val saved = Seq(j.kind, j.a, j.b, j.c, j.dst, j.m, j.n, j.k, j.writeBytes, j.tag,
          j.qkRole, j.qkPositionBase, j.qkTrigTokens).map(x => x -> x.peek().litValue)
        for (_ <- 0 until 4) {
          saved.foreach { case (x, v) => x.expect(v.U) }
          d.io.completion.valid.expect(false.B); d.io.memory.valid.expect(false.B); d.clock.step()
        }
        d.io.job.ready.poke(true.B); d.clock.step(); d.io.job.ready.poke(false.B)
        val thisJob = jobs; jobs += 1
        // Bogus inactive result pins cannot publish anything while valid is low.
        d.io.done.bits.tag.poke("hffffffff".U); d.io.done.bits.status.poke(Status.Memory.U)
        d.io.done.bits.writeBytes.poke(0.U)
        for (_ <- 0 until 6) {
          d.io.completion.valid.expect(false.B); d.io.job.valid.expect(false.B); d.io.memory.valid.expect(false.B)
          d.io.writeBytes.expect(bytes.U); d.clock.step()
        }
        val inject = thisJob == faultAt
        d.io.done.bits.tag.poke((ownerTag ^ (if (inject && doneFault == 2) BigInt(1) else BigInt(0))).U)
        d.io.done.bits.status.poke((if (inject && doneFault == 1) Status.Memory else Status.Ok).U)
        val reported = e.bytes + (if (inject && doneFault == 3) -64 else if (inject && doneFault == 4) 64 else 0)
        d.io.done.bits.writeBytes.poke(reported.U); d.io.done.valid.poke(true.B)
        d.io.done.ready.expect(true.B); d.clock.step(); d.io.done.valid.poke(false.B)
      } else if (d.io.completion.valid.peek().litToBoolean) {
        val completion = d.io.completion.bits.peek().litValue
        val command = p.commands(accepted)
        (completion & ((BigInt(1) << 29) - 1)) shouldBe BigInt(accepted)
        ((completion >> 29) & 7) shouldBe (if (readFault != 0) BigInt(0) else (command >> 8) & 7)
        (completion >> 40) shouldBe (if (readFault != 0) BigInt(0) else (command >> 40) & 65535)
        val success = ((completion >> 32) & 255) == 0
        val expectedBytes = bytes + (if (success) p.expected(accepted).bytes else BigInt(0))
        d.io.writeBytes.expect(expectedBytes.U)
        for (_ <- 0 until 4) {
          d.io.completion.bits.expect(completion.U); d.io.job.valid.expect(false.B); d.io.memory.valid.expect(false.B)
          d.io.result.valid.expect(false.B); d.clock.step()
        }
        if (success) { bytes = expectedBytes; completed += 1 }
        d.io.completion.ready.poke(true.B); d.clock.step(); d.io.completion.ready.poke(false.B); accepted += 1
      } else d.clock.step()
      iterations += 1
    }
    d.io.result.valid.expect(true.B); d.io.result.bits.epoch.expect(epoch.U)
    d.io.result.bits.completed.expect(completed.U); d.io.issuedJobs.expect(jobs.U); d.io.writeBytes.expect(bytes.U)
    val status = d.io.result.bits.status.peek().litValue.toInt
    val failedPc = d.io.result.bits.failedPc.peek().litValue.toInt
    d.io.resetRequired.expect((status != 0).B)
    for (_ <- 0 until 4) {
      d.io.result.bits.status.expect(status.U); d.io.result.bits.completed.expect(completed.U)
      d.io.result.bits.failedPc.expect(failedPc.U); d.io.memory.valid.expect(false.B); d.io.job.valid.expect(false.B); d.clock.step()
    }
    d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
    d.io.launch.ready.expect((status == 0).B)
    Result(status, jobs, completed, bytes, failedPc)
  }
  def rejected(d: HostBlockCommands, p: Program, before: Int, label: String, exactStatus: Option[Int] = None): Unit =
    withClue(label + ": ") {
      val r = run(d, p)
      r.status should not be Status.Ok; r.jobs shouldBe before; r.completions shouldBe before
      r.failedPc shouldBe before; r.bytes shouldBe p.expected.take(before).map(_.bytes).sum
      exactStatus.foreach(s => r.status shouldBe s)
    }
  def dut(enabled: Boolean = true): HostBlockCommands = new HostBlockCommands(QwenBlockShape.qwen35Qkv(),
    maxCommands = 21, bf16Weights = true, bf16Qkv = true, bf16QkNormRope = enabled)

  "Host BF16 QK Norm and partial RoPE control" should "bind seven producers and reject stale, aliased and malformed work before publication" in {
    val p = program()
    val windows = Seq((1, 0, 1, 0), (128, 0, 128, 0), (128, 0, 128, 128), (128, 127, 1, 255))
      .map { case (m, base, count, position) => program(m, base, count, position) }
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      for ((candidate, index) <- windows.zipWithIndex) {
        val r = run(d, candidate)
        r.status shouldBe 0; r.jobs shouldBe 7; r.completions shouldBe 7
        r.bytes shouldBe candidate.expected.map(_.bytes).sum
        println(s"HOST_QK_ROPE_FRONTEND window=$index jobs=${r.jobs} completed=${r.completions} bytes=${r.bytes} numeric=false")
      }
      // Failure at every owner stops the chain. In particular, both Norm
      // outputs are withheld together when tag/bytes/status do not match.
      for (at <- 0 until 7; fault <- 1 to 4) {
        val r = run(d, p, faultAt = at, doneFault = fault)
        r.status shouldBe (if (fault == 1) Status.Memory else Status.Protocol)
        r.jobs shouldBe at + 1; r.completions shouldBe at; r.failedPc shouldBe at
        r.bytes shouldBe p.expected.take(at).map(_.bytes).sum
      }
      for (fault <- 1 to 2) {
        val r = run(d, p, readFault = fault)
        r.status shouldBe (if (fault == 1) Status.Memory else Status.Protocol)
        r.jobs shouldBe 0; r.completions shouldBe 0; r.bytes shouldBe 0
      }
      // Readonly bytes, even with the right shape and addressable allocation,
      // cannot manufacture the required Dense or Norm completion provenance.
      val readonlyLookalike = BigInt(0x5800000)
      rejected(d, edit(select(p, Seq(3)), 63, 56, 48, readonlyLookalike), 0, "readonly-preloaded-Q-Norm", Some(Status.Dependency))
      rejected(d, edit(select(p, Seq(5)), 90, 56, 48, readonlyLookalike), 0, "readonly-preloaded-Q-RoPE", Some(Status.Dependency))
      rejected(d, select(p, Seq(0, 4)), 1, "Q-Dense-cannot-produce-K", Some(Status.Dependency))
      rejected(d, select(p, Seq(0, 1, 2, 5)), 3, "Dense-cannot-replace-Norm", Some(Status.Dependency))
      rejected(d, edit(p, 63, 56, 48, readonlyLookalike), 3, "completed-Dense-wrong-Norm-input", Some(Status.Dependency))
      rejected(d, edit(p, 90, 56, 48, readonlyLookalike), 5, "completed-Norm-wrong-RoPE-input", Some(Status.Dependency))
      rejected(d, edit(p, 67, 68, 32, 126), 3, "Norm-window-must-match-producer", Some(Status.Dependency))
      rejected(d, edit(p, 94, 68, 32, 126), 5, "RoPE-window-must-match-producer", Some(Status.Dependency))
      rejected(d, edit(p, 26, 68, 32, 126), 1, "K-projection-window-must-match-Q")
      rejected(d, editCommand(p, 3, 24, 16, 1), 3, "wait-must-be-immediate-predecessor", Some(Status.Dependency))

      // Active writes are disjoint here; it is their FULL allocations that
      // collide with an earlier producer's inactive prefix/suffix.
      assert(normalized(0) != projected(2))
      assert(projected(2) + 127 * 4096 >= projected(2) + 128 * 1024)
      rejected(d, edit(p, 72, 56, 48, projected(2)), 3, "Norm-overlaps-V-full-allocation", Some(Status.Permission))
      rejected(d, edit(p, 75, 56, 48, projected(2)), 3, "gate-overlaps-V-full-allocation", Some(Status.Permission))
      rejected(d, edit(p, 72, 56, 48, projected(0) + 0x10000), 3, "Norm-overlaps-packed-Q-inactive-prefix", Some(Status.Permission))
      rejected(d, edit(p, 99, 56, 48, gate + 0x10000), 5, "RoPE-overlaps-gate-inactive-prefix", Some(Status.Permission))
      rejected(d, edit(p, 75, 56, 48, normalized(0)), 3, "Norm-and-gate-alias", Some(Status.Permission))

      val normEdits = Seq(
        (63, 108, 4, BigInt(7)), (69, 108, 4, BigInt(7)), (72, 108, 4, BigInt(7)), (75, 108, 4, BigInt(7)),
        (63, 116, 4, BigInt(3)), (63, 104, 4, BigInt(1)), (64, 92, 18, BigInt(2)),
        (64, 74, 18, BigInt(2048)), (70, 74, 18, BigInt(128)), (73, 74, 18, BigInt(512)),
        (76, 74, 18, BigInt(512)), (65, 56, 24, BigInt(8192)), (71, 56, 24, BigInt(512)),
        (66, 56, 16, BigInt(0x34)), (66, 72, 8, BigInt(1)), (66, 80, 8, BigInt(2)),
        (66, 88, 4, BigInt(7)), (66, 92, 4, BigInt(7)), (66, 96, 8, BigInt(8)), (66, 104, 1, BigInt(1)),
        (67, 56, 8, BigInt(0)), (67, 56, 8, BigInt(2)), (67, 64, 2, BigInt(1)), (67, 64, 2, BigInt(2)),
        (67, 66, 2, BigInt(1)), (67, 108, 8, BigInt(0xb1)), (67, 127, 1, BigInt(1)),
        (67, 100, 8, BigInt(0)), (67, 100, 8, BigInt(2)), (67, 100, 8, BigInt(129)), (67, 68, 32, BigInt("ffffffff", 16)),
        (68, 80, 32, BigInt(1)), (68, 112, 1, BigInt(1)), (68, 56, 24, nullIndex), (68, 56, 24, BigInt(72)),
        (63, 8, 1, BigInt(1)), (66, 8, 1, BigInt(1)), (63, 32, 24, BigInt(63)),
        (65, 32, 24, nullIndex), (67, 32, 24, BigInt(66)), (68, 32, 24, BigInt(69)),
        (71, 32, 24, BigInt(63)), (74, 32, 24, BigInt(75)), (77, 32, 24, BigInt(63)),
        (63, 56, 48, projected(0) + 2), (69, 56, 48, gamma(0) + 2), (72, 56, 48, normalized(0) + 2),
        (75, 56, 48, gate + 2), (75, 56, 48, BigInt(0xe000000) - 64))
      for ((index, low, width, value) <- normEdits)
        rejected(d, edit(p, index, low, width, value), 3, s"Norm-record-$index-bit-$low-value-$value")
      for ((index, low, width, value) <- Seq(
        (83, 56, 24, BigInt(75)), (82, 66, 2, BigInt(1)), (82, 108, 8, BigInt(0xb1))))
        rejected(d, edit(p, index, low, width, value), 4, s"K-Norm-record-$index-bit-$low")
      for ((index, low, width, value) <- Seq(
        (90, 108, 4, BigInt(7)), (93, 88, 4, BigInt(7)), (94, 56, 8, BigInt(2)),
        (94, 66, 2, BigInt(0)), (94, 108, 8, BigInt(0xc1)), (95, 56, 24, BigInt(75)),
        (95, 80, 32, BigInt(256)), (95, 80, 32, BigInt("ffffffff", 16)), (95, 112, 1, BigInt(1)),
        (97, 56, 18, BigInt(255)), (97, 74, 18, BigInt(128)), (98, 56, 24, BigInt(128)),
        (99, 56, 48, rotated(0) + 2), (101, 32, 24, BigInt(90))))
        rejected(d, edit(p, index, low, width, value), 5, s"RoPE-record-$index-bit-$low")
      for ((low, width, value) <- Seq((0, 8, BigInt(0x30)), (8, 3, BigInt(2)), (11, 1, BigInt(1)),
        (80, 24, BigInt(63)), (40, 16, BigInt(0)), (40, 16, BigInt(3))))
        rejected(d, editCommand(p, 3, low, width, value), 3, s"Norm-command-bit-$low-value-$value")
      // A poison/locked frontend must recover only through the shared reset.
      val recovered = run(d, p)
      recovered.status shouldBe 0; recovered.jobs shouldBe 7; recovered.completions shouldBe 7
      recovered.bytes shouldBe 24576
      println("HOST_QK_ROPE_FRONTEND malformed_dependency_alias_completion_stall_reset=PASS numeric=false")
    }
  }
  it should "keep the new SFU commands disabled by default while retaining the existing QKV frontend" in {
    val p = program()
    test(dut(enabled = false)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      for (index <- Seq(3, 4, 5, 6)) rejected(d, select(p, Seq(index)), 0, s"default-off-$index", Some(Status.Unsupported))
      rejected(d, p, 3, "default-off-after-real-Dense-completions", Some(Status.Unsupported))
      val denseOnly = run(d, select(p, Seq(0, 1, 2)))
      denseOnly.status shouldBe 0; denseOnly.jobs shouldBe 3; denseOnly.completions shouldBe 3
      denseOnly.bytes shouldBe 10240
    }
  }
}
