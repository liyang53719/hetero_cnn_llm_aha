// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** JVM model tests, NOT hardware tests. A separate original-HardFloat cross
  * check and Treadle callback/reset/gated-clock check are mandatory before use.
  */
class RetainedEndpointFunctionalModelSpec extends AnyFlatSpec with Matchers {
  private def raw(n: Int): Long = java.lang.Float.floatToRawIntBits(n.toFloat).toLong & 0xffffffffL
  private def pack(xs: Seq[Long], width: Int): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) {
    case (x, (word, i)) => x | (BigInt(word) << (width * i))
  }
  private def reset(m: RetainedEndpointFunctionalModel): Unit = {
    m.setInput("rst_ni", 0); m.setInput("rst_ni", 1)
  }
  private def command(m: RetainedEndpointFunctionalModel, tag: Int): Unit = {
    m.output("cmd_ready_o") shouldBe BigInt(1)
    m.setInput("cmd_i", (BigInt(tag) << 40) | 0x220); m.setInput("cmd_valid_i", 1)
    m.risingEdge(); m.setInput("cmd_valid_i", 0)
  }
  it should "match 74 independent rational FMA fixtures and reject unsupported arithmetic inputs" in {
    EndpointFmaFixture.all.foreach { v =>
      FiniteFp32Backend.fma(v.a.toLong << 16, v.b.toLong << 16, v.c) shouldBe
        FiniteFp32Backend.Rounded(v.value, v.flags)
    }
    for (bad <- Seq(0x7f800000L, 0xff800000L, 0x7fc00001L, 0x7f800001L)) {
      an[IllegalArgumentException] should be thrownBy FiniteFp32Backend.fma(bad, 0x3f800000L, 0)
      an[IllegalArgumentException] should be thrownBy FiniteFp32Backend.fma(0x3f800000L, bad, 0)
      an[IllegalArgumentException] should be thrownBy FiniteFp32Backend.fma(0x3f800000L, 0x3f800000L, bad)
    }
  }
  it should "retain all eight by five by 512 accumulators with pipeline latency and stalled FIFO order" in {
    val all = Vector.fill(8)(new RetainedEndpointFunctionalModel(seedEnabled = true))
    all.zipWithIndex.foreach { case (m, ep) =>
      reset(m); command(m, 100 + ep)
      m.setInput("step_a_i", pack((1 to 16).map(i => raw(i + ep) >>> 16), 16))
      m.setInput("step_b_i", pack((1 to 32).map(i => raw(i) >>> 16), 16))
    }
    // Five distinct contexts fill the pipeline. All accepted operands are
    // nonzero and row/column/endpoint dependent; no ignored padding lanes.
    for (context <- 0 until 5; m <- all) {
      m.setInput("step_context_i", context); m.setInput("step_clear_i", 1)
      m.setInput("step_valid_i", 1); m.setInput("step_last_i", 0)
      m.output("step_ready_o") shouldBe BigInt(1)
      if (context < 4) m.output("out_valid_o") shouldBe BigInt(0)
      m.risingEdge()
    }
    all.foreach { m => m.setInput("step_valid_i", 0); m.output("out_valid_o") shouldBe BigInt(1) }
    val held = all.map(_.output("out_acc_o"))
    for (_ <- 0 until 7; (m, ep) <- all.zipWithIndex) {
      m.risingEdge(); m.output("out_acc_o") shouldBe held(ep)
    }
    // Same-context completion/refill: FIFO returns old value, then updates
    // that context through all five pipeline edges without reordering peers.
    for (context <- 0 until 5; (m, ep) <- all.zipWithIndex) {
      m.output("out_context_o") shouldBe BigInt(context)
      m.output("out_acc_o") shouldBe pack(for (r <- 1 to 16; c <- 1 to 32) yield raw((r + ep) * c), 32)
      m.setInput("out_ready_i", 1); m.setInput("step_context_i", context)
      m.setInput("step_clear_i", 0); m.setInput("step_valid_i", 1)
      m.output("step_ready_o") shouldBe BigInt(1); m.risingEdge()
    }
    all.foreach(_.setInput("step_valid_i", 0))
    for (context <- 0 until 5; (m, ep) <- all.zipWithIndex) {
      m.output("out_valid_o") shouldBe BigInt(1); m.output("out_context_o") shouldBe BigInt(context)
      m.output("out_acc_o") shouldBe pack(for (r <- 1 to 16; c <- 1 to 32) yield raw(2 * (r + ep) * c), 32)
      m.diagnostics._6 shouldBe 0; m.risingEdge()
    }
    all.foreach { m =>
      m.diagnostics shouldBe ((10L, 10L, 0, 31, 31, 0))
      m.output("out_valid_o") shouldBe BigInt(0)
    }
    // Reset one independent instance, not the other seven.
    reset(all.head); all.head.diagnostics._5 shouldBe 0
    all.tail.foreach(_.diagnostics._5 shouldBe 31)
  }
  it should "restore 32 live seed beats only at commit and hold a success ACK across late poison" in {
    val m = new RetainedEndpointFunctionalModel(seedEnabled = true); reset(m)
    m.setInput("seed_context_i", 3); m.setInput("seed_group_tag_i", 9)
    m.setInput("seed_group_sequence_i", 7); m.setInput("seed_source_generation_i", 11)
    m.setInput("seed_begin_valid_i", 1); m.output("seed_begin_ready_o") shouldBe BigInt(1)
    m.risingEdge(); m.setInput("seed_begin_valid_i", 0)
    for (cluster <- 0 until 32) {
      m.setInput("seed_cluster_i", cluster)
      m.setInput("seed_data_i", pack((0 until 16).map(j => raw(cluster * 16 + j + 1)), 32))
      m.setInput("seed_beat_valid_i", 1); m.output("seed_beat_ready_o") shouldBe BigInt(1)
      m.risingEdge(); m.diagnostics._5 shouldBe 0
    }
    m.setInput("seed_beat_valid_i", 0); m.setInput("seed_commit_valid_i", 1)
    m.output("seed_ack_valid_o") shouldBe BigInt(0); m.risingEdge()
    m.setInput("seed_commit_valid_i", 0); m.output("seed_ack_valid_o") shouldBe BigInt(1)
    m.diagnostics._5 shouldBe 8
    m.setInput("seed_ack_ready_i", 1); m.risingEdge(); m.setInput("seed_ack_ready_i", 0)
    command(m, 900)
    m.setInput("step_context_i", 3); m.setInput("step_valid_i", 1)
    m.setInput("step_a_i", pack(Seq.fill(16)(0x3f80L), 16))
    m.setInput("step_b_i", pack(Seq.fill(32)(0x3f80L), 16))
    m.setInput("step_clear_i", 0); m.setInput("step_last_i", 1); m.setInput("command_last_tile_i", 1)
    m.risingEdge(); m.setInput("step_valid_i", 0)
    for (_ <- 0 until 4) m.risingEdge()
    m.output("out_acc_o") shouldBe pack((2 to 513).map(raw), 32)
    m.setInput("out_ready_i", 1); m.risingEdge()
    m.output("completion_valid_o") shouldBe BigInt(1)
    m.output("completion_data_o") shouldBe ((BigInt(900) << 40) | (BigInt(2) << 29))
    m.setInput("completion_ready_i", 1); m.risingEdge()
    // A second seed then held commit ACK. Late abort preserves the held ACK
    // bits while poisoning/invalidation prevents reuse; it is not a rollback.
    m.setInput("seed_begin_valid_i", 1); m.risingEdge(); m.setInput("seed_begin_valid_i", 0)
    for (cluster <- 0 until 32) { m.setInput("seed_cluster_i", cluster); m.setInput("seed_beat_valid_i", 1); m.risingEdge() }
    m.setInput("seed_beat_valid_i", 0); m.setInput("seed_commit_valid_i", 1); m.risingEdge(); m.setInput("seed_commit_valid_i", 0)
    m.output("seed_ack_error_o") shouldBe BigInt(0)
    m.setInput("seed_abort_i", 1); m.risingEdge()
    m.output("seed_ack_valid_o") shouldBe BigInt(1); m.output("seed_ack_error_o") shouldBe BigInt(0)
    m.output("seed_reset_required_o") shouldBe BigInt(1); m.diagnostics._5 shouldBe 0
    m.output("cmd_ready_o") shouldBe BigInt(0)
  }
  it should "reject invalid seed order and command opcodes without inventing a completed arithmetic result" in {
    for (which <- 0 until 3) {
      val m = new RetainedEndpointFunctionalModel(seedEnabled = true); reset(m)
      m.setInput("seed_context_i", 2); m.setInput("seed_begin_valid_i", 1)
      m.risingEdge(); m.setInput("seed_begin_valid_i", 0)
      which match {
        case 0 => m.setInput("seed_cluster_i", 1); m.setInput("seed_beat_valid_i", 1)
        case 1 => m.setInput("seed_data_i", BigInt("7f800000", 16)); m.setInput("seed_beat_valid_i", 1)
        case 2 => m.setInput("seed_commit_valid_i", 1)
      }
      m.risingEdge(); m.output("seed_reset_required_o") shouldBe BigInt(1)
      m.output("out_valid_o") shouldBe BigInt(0); m.diagnostics._5 shouldBe 0
    }
    val m = new RetainedEndpointFunctionalModel(seedEnabled = false); reset(m)
    m.setInput("cmd_i", (BigInt(42) << 40) | 0xff); m.setInput("cmd_valid_i", 1); m.risingEdge()
    m.output("completion_valid_o") shouldBe BigInt(1)
    m.output("completion_data_o") shouldBe ((BigInt(42) << 40) | (BigInt(4) << 32) | (BigInt(2) << 29))
    m.output("step_ready_o") shouldBe BigInt(0); m.diagnostics._1 shouldBe 0L
  }
}
