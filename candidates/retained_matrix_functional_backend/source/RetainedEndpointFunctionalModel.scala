// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

/** Simulation-only, two-state, finite-domain implementation of ONE retained
  * endpoint. Instantiate exactly eight independent objects for the 4096 model.
  * No reference file, expected value, host float or scripted response is read.
  * Arithmetic is evaluated at modeled PRE using live accepted operands and the
  * old accumulator bank, then committed at the original fifth pipeline edge.
  * Internal HardFloat recoded intermediates are abstracted, not cycle-observed.
  */
final class RetainedEndpointFunctionalModel(val seedEnabled: Boolean) {
  import RetainedEndpointFunctionalModel._
  private val inputs = scala.collection.mutable.Map.empty[String, BigInt]
  InputWidths.foreach { case (n, _) => inputs(n) = BigInt(0) }
  private def b(n: String): Boolean = inputs(n) != 0
  private def u(n: String): Int = inputs(n).toInt
  private def word(n: String): Long = inputs(n).toLong
  private def bi(x: Boolean): BigInt = if (x) BigInt(1) else BigInt(0)

  // The provider does not reset accumulator contents, only validity. Zero
  // allocation is an unobservable two-state initialization while invalid.
  private val bank = Array.fill[Long](5, 512)(0L)
  private val bankValid = Array.fill(5)(false)
  private val busy = Array.fill(5)(false)
  private val schedulerValid = Array.fill(5)(false)
  private val contexts = Array.fill(8)(0)
  private val lasts = Array.fill(8)(false)
  private val result = Array.fill[BigInt](5)(BigInt(0))
  private val resultFlags = Array.fill(5)(0)
  private var tagWrite = 0; private var tagRead = 0; private var tagCount = 0
  private var resultWrite = 0; private var resultRead = 0; private var tokens = 0
  private var active = false; private var pending = false
  private var event = 0; private var status = 0; private var protocol = false
  private var accepted = 0L; private var completed = 0L
  private case class Issue(context: Int, clear: Boolean, a: BigInt, b: BigInt)
  private case class Computed(context: Int, words: Array[Long], packed: BigInt, flags: Int)
  private var inputStage: Option[Issue] = None
  private var preStage: Option[Computed] = None
  private var mulStage: Option[Computed] = None
  private var postStage: Option[Computed] = None
  private var seedContext = 0; private var seedTag = 0L; private var seedSequence = 0L
  private var seedGeneration = 0L; private var seedBeats = 0
  private var seedReserved = false; private var seedAck = false
  private var seedAckError = false; private var seedPoison = false
  private var resetObserved = false

  def setInput(name: String, value: BigInt): Unit = {
    val width = InputWidths.getOrElse(name, throw new IllegalArgumentException("unknown input " + name))
    require(value >= 0 && value.bitLength <= width, "two-state input width " + name)
    inputs(name) = value
    if (name == "rst_ni" && value == 0) asyncReset()
  }
  def asyncReset(): Unit = {
    resetObserved = true
    java.util.Arrays.fill(bankValid, false); java.util.Arrays.fill(busy, false)
    java.util.Arrays.fill(schedulerValid, false)
    // Tag FIFO contents are unreset in RTL, but inaccessible with count zero.
    tagWrite = 0; tagRead = 0; tagCount = 0; resultWrite = 0; resultRead = 0; tokens = 0
    var i = 0; while (i < 5) { result(i) = 0; resultFlags(i) = 0; i += 1 }
    active = false; pending = false; event = 0; status = 0; protocol = false
    accepted = 0; completed = 0
    inputStage = None; preStage = None; mulStage = None; postStage = None
    seedContext = 0; seedTag = 0; seedSequence = 0; seedGeneration = 0; seedBeats = 0
    seedReserved = false; seedAck = false; seedAckError = false; seedPoison = false
  }
  private def mask(xs: Array[Boolean]): Int = xs.indices.foldLeft(0)((m, i) => m | (if (xs(i)) 1 << i else 0))
  private case class Comb(context: Int, last: Boolean, arrayOut: Boolean, matrixOut: Boolean,
    pop: Boolean, issue: Boolean, matrixReady: Boolean, cmdReady: Boolean,
    seedBlock: Boolean, seedHold: Boolean, beginReady: Boolean, beatReady: Boolean,
    commitReady: Boolean, beginFire: Boolean, beatFire: Boolean, commitFire: Boolean,
    legalBegin: Boolean, legalCommit: Boolean, reserve: Boolean, seedWrite: Boolean,
    commit: Boolean, invalidate: Boolean, bankContext: Int, fault: Boolean)

  private def comb: Comb = {
    val ctx = if (tagCount != 0) contexts(tagRead) else 0
    val last = tagCount != 0 && lasts(tagRead)
    val arrayOut = tokens != 0
    val matrixOut = arrayOut && tagCount != 0
    val pop = matrixOut && active && b("out_ready_i")
    val block = seedEnabled && (seedReserved || seedAck || seedPoison || b("seed_abort_i") ||
      b("seed_begin_valid_i") || b("seed_beat_valid_i") || b("seed_commit_valid_i"))
    val c = u("step_context_i")
    val available = c < 5 && (!busy(c) || (pop && ctx == c))
    val ready = available && tagCount < 8 && tokens < 8 && !block
    val issue = active && b("step_valid_i") && ready
    val quiescent = mask(busy) == 0 && !matrixOut && !arrayOut && !issue &&
      inputStage.isEmpty && preStage.isEmpty && mulStage.isEmpty && postStage.isEmpty
    val beginReady = seedEnabled && !seedReserved && !seedAck && !seedPoison && !b("seed_abort_i") && quiescent
    val beatReady = seedEnabled && seedReserved && !seedAck && !seedPoison && !b("seed_abort_i") && quiescent
    val commitReady = beatReady
    val beginFire = b("seed_begin_valid_i") && beginReady
    val beatFire = b("seed_beat_valid_i") && beatReady
    val commitFire = b("seed_commit_valid_i") && commitReady
    val identity = u("seed_context_i") == seedContext && word("seed_group_tag_i") == seedTag &&
      word("seed_group_sequence_i") == seedSequence && word("seed_source_generation_i") == seedGeneration
    val legalBegin = u("seed_context_i") < 5 && !b("seed_beat_valid_i") && !b("seed_commit_valid_i")
    val finiteData = (0 until 16).forall(i => ((inputs("seed_data_i") >> (i * 32 + 23)) & 255) != 255)
    val legalBeat = identity && seedBeats < 32 && u("seed_cluster_i") == seedBeats && finiteData &&
      !b("seed_commit_valid_i") && !b("seed_begin_valid_i")
    val legalCommit = identity && seedBeats == 32 && !b("seed_beat_valid_i") && !b("seed_begin_valid_i")
    val fault = seedEnabled && (b("seed_abort_i") || (seedReserved && !quiescent) ||
      (b("seed_begin_valid_i") && !quiescent) || (beginFire && !legalBegin) ||
      (beatFire && !legalBeat) || (commitFire && !legalCommit) ||
      (b("seed_begin_valid_i") && (seedReserved || seedAck)) ||
      ((b("seed_beat_valid_i") || b("seed_commit_valid_i")) && (!seedReserved || seedAck)))
    val reserve = beginFire && legalBegin && !fault
    Comb(ctx, last, arrayOut, matrixOut, pop, issue, ready,
      !active && !pending && !block, block, seedEnabled && (seedReserved || seedAck),
      beginReady, beatReady, commitReady, beginFire, beatFire, commitFire, legalBegin,
      legalCommit, reserve, beatFire && legalBeat && !fault, commitFire && legalCommit && !fault,
      seedEnabled && (fault || seedPoison), if (reserve) u("seed_context_i") else seedContext, fault)
  }
  def output(name: String): BigInt = {
    val c = comb
    name match {
      case "cmd_ready_o" => bi(c.cmdReady)
      case "step_ready_o" => bi(active && c.matrixReady)
      case "out_valid_o" => bi(active && c.matrixOut)
      case "out_context_o" => BigInt(c.context)
      case "out_last_o" => bi(c.last)
      case "out_acc_o" => result(resultRead)
      case "completion_valid_o" => bi(pending)
      case "completion_data_o" => (BigInt(event) << 40) | (BigInt(status) << 32) | (BigInt(2) << 29)
      case "protocol_error_o" => bi(protocol || seedPoison)
      case "arithmetic_busy_o" => BigInt(mask(busy))
      case "arithmetic_out_valid_o" => bi(c.matrixOut)
      case "seed_begin_ready_o" => bi(c.beginReady)
      case "seed_beat_ready_o" => bi(c.beatReady)
      case "seed_commit_ready_o" => bi(c.commitReady)
      case "seed_ack_valid_o" => bi(seedEnabled && seedAck)
      case "seed_ack_context_o" => BigInt(if (seedEnabled) seedContext else 0)
      case "seed_ack_group_tag_o" => BigInt(if (seedEnabled) seedTag else 0L)
      case "seed_ack_group_sequence_o" => BigInt(if (seedEnabled) seedSequence else 0L)
      case "seed_ack_source_generation_o" => BigInt(if (seedEnabled) seedGeneration else 0L)
      case "seed_ack_error_o" => bi(seedEnabled && seedAckError)
      case "seed_reset_required_o" => bi(seedEnabled && seedPoison)
      case _ => throw new IllegalArgumentException("unknown endpoint output " + name)
    }
  }
  // Read-only diagnostics expose actual model state, not a reference injection.
  def diagnostics: (Long, Long, Int, Int, Int, Int) =
    (accepted, completed, mask(busy), mask(schedulerValid), mask(bankValid), resultFlags(resultRead))
  private def calculate(i: Issue): Computed = {
    val values = new Array[Long](512); var packed = BigInt(0); var flags = 0; var lane = 0
    while (lane < 512) {
      val a = ((i.a >> ((lane / 32) * 16)) & 65535).toLong << 16
      val b = ((i.b >> ((lane % 32) * 16)) & 65535).toLong << 16
      val old = if (i.clear || !bankValid(i.context)) 0L else bank(i.context)(lane)
      val f = FiniteFp32Backend.fma(a, b, old)
      values(lane) = f.value; packed |= BigInt(f.value) << (lane * 32); flags |= f.flags
      lane += 1
    }
    Computed(i.context, values, packed, flags)
  }
  def risingEdge(): Unit = {
    require(resetObserved, "explicit reset must precede functional execution")
    if (!b("rst_ni")) { asyncReset(); return }
    val c = comb
    val wasPending = pending; val wasSeedAck = seedAck; val wasSeedPoison = seedPoison
    val pushed = postStage.nonEmpty
    // PRE samples OLD banks before this edge's ROUND/seed writes.
    val nextPre = if (!c.seedHold) inputStage.map(calculate) else preStage
    if (!c.seedHold) {
      postStage.foreach { p =>
        System.arraycopy(p.words, 0, bank(p.context), 0, 512); bankValid(p.context) = true
        result(resultWrite) = p.packed; resultFlags(resultWrite) = p.flags
        resultWrite = (resultWrite + 1) % 5
      }
      if (c.pop) resultRead = (resultRead + 1) % 5
    }
    if (active && b("step_valid_i") && u("step_context_i") >= 5) protocol = true
    if (c.arrayOut && tagCount == 0) protocol = true
    if (c.pop) {
      schedulerValid(c.context) = true; busy(c.context) = false; tagRead = (tagRead + 1) & 7
      completed = (completed + 1) & 0xffffffffL
    }
    if (c.issue) {
      val ctx = u("step_context_i"); contexts(tagWrite) = ctx; lasts(tagWrite) = b("step_last_i")
      tagWrite = (tagWrite + 1) & 7; busy(ctx) = true; accepted = (accepted + 1) & 0xffffffffL
    }
    tagCount += (if (c.issue) 1 else 0) - (if (c.pop) 1 else 0)
    tokens += (if (pushed) 1 else 0) - (if (c.pop) 1 else 0)
    if (!c.seedHold) { postStage = mulStage; mulStage = preStage; preStage = nextPre }
    else { postStage = None; mulStage = None; preStage = None } // controller valid flops still shift; quiescent reservation guarantees empty
    inputStage = if (c.issue) Some(Issue(u("step_context_i"), b("step_clear_i"), inputs("step_a_i"), inputs("step_b_i"))) else None

    if (seedEnabled) {
      if (c.seedWrite) {
        var j = 0
        while (j < 16) { bank(c.bankContext)(u("seed_cluster_i") * 16 + j) =
          ((inputs("seed_data_i") >> (j * 32)) & BigInt("ffffffff", 16)).toLong; j += 1 }
      }
      if (c.commit && c.bankContext < 5) { bankValid(c.bankContext) = true; schedulerValid(c.bankContext) = true }
      if ((c.reserve || c.invalidate) && c.bankContext < 5) { bankValid(c.bankContext) = false; schedulerValid(c.bankContext) = false }
      if (c.beginFire) {
        seedContext = u("seed_context_i"); seedTag = word("seed_group_tag_i")
        seedSequence = word("seed_group_sequence_i"); seedGeneration = word("seed_source_generation_i")
        seedBeats = 0; seedReserved = c.legalBegin; seedAckError = false
      }
      if (c.seedWrite) seedBeats += 1
      if (c.commitFire) { seedAck = true; seedAckError = !c.legalCommit || c.fault }
      if (wasSeedAck && b("seed_ack_ready_i")) { seedAck = false; if (!wasSeedPoison && !c.fault) seedReserved = false }
      if (c.fault) seedPoison = true
    }
    if (b("cmd_valid_i") && c.cmdReady) {
      event = ((inputs("cmd_i") >> 40) & 65535).toInt
      if (Set(0x20, 0x21, 0x23, 0x24)((inputs("cmd_i") & 255).toInt)) { active = true; status = 0 }
      else { pending = true; status = 4 }
    }
    if (c.pop && c.last && b("command_last_tile_i")) { active = false; pending = true }
    if (wasPending && b("completion_ready_i")) pending = false
    require(tagCount >= 0 && tagCount <= 8 && tokens >= 0 && tokens <= 8, "provider credit invariant")
  }
}

object RetainedEndpointFunctionalModel {
  val InputWidths: Map[String, Int] = Map(
    "clk_i" -> 1, "rst_ni" -> 1, "cmd_valid_i" -> 1, "cmd_i" -> 128,
    "step_valid_i" -> 1, "step_context_i" -> 3, "step_clear_i" -> 1, "step_last_i" -> 1,
    "command_last_tile_i" -> 1, "step_a_i" -> 256, "step_b_i" -> 512,
    "out_ready_i" -> 1, "completion_ready_i" -> 1, "seed_begin_valid_i" -> 1,
    "seed_context_i" -> 3, "seed_group_tag_i" -> 32, "seed_group_sequence_i" -> 32,
    "seed_source_generation_i" -> 32, "seed_beat_valid_i" -> 1, "seed_cluster_i" -> 5,
    "seed_data_i" -> 512, "seed_commit_valid_i" -> 1, "seed_abort_i" -> 1, "seed_ack_ready_i" -> 1)
}
