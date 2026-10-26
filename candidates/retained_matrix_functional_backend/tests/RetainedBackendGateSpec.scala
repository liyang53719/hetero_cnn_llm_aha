// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
import firrtl2.ir._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class RetainedBackendGateSpec extends AnyFlatSpec with Matchers {
  private def circuit(seed: Boolean): Circuit = {
    def external(name: String, endpoint: Boolean): ExtModule = ExtModule(NoInfo, name,
      RetainedBackendCircuitGate.expected(seed, endpoint).toSeq.sortBy(_._1).map { case (n, (d, t)) => Port(NoInfo, n, d, t) },
      if (endpoint) "qwen2_matrix_command_endpoint" else "tc_clk_gating",
      if (endpoint && seed) Seq(IntParam("ENABLE_ACCUMULATOR_SEED", BigInt(1))) else Seq.empty)
    Circuit(NoInfo, Seq(Module(NoInfo, "Top", Seq.empty, Block((0 until 8).flatMap(i =>
      Seq(DefInstance(NoInfo, "ep" + i, "Endpoint"), DefInstance(NoInfo, "gate" + i, "Gate"))))),
      external("Endpoint", true), external("Gate", false)), "Top")
  }
  it should "require every actual port direction width clock type parameter and full instance map" in {
    for (seed <- Seq(false, true)) {
      val c = circuit(seed)
      RetainedBackendCircuitGate.verify(c, seed).size shouldBe 16
      for (idx <- Seq(1, 2)) {
        val e = c.modules(idx).asInstanceOf[ExtModule]
        def reject(ports: Seq[Port]): Unit = {
          an[IllegalArgumentException] should be thrownBy RetainedBackendCircuitGate.verify(
            c.copy(modules = c.modules.updated(idx, e.copy(ports = ports))), seed)
        }
        for (p <- e.ports) {
          reject(e.ports.filterNot(_.name == p.name))
          reject(e.ports.map(x => if (x.name == p.name) x.copy(direction = if (x.direction == Input) Output else Input) else x))
          reject(e.ports.map(x => if (x.name == p.name) x.copy(tpe = UIntType(IntWidth(99))) else x))
          reject(e.ports :+ p)
        }
        an[IllegalArgumentException] should be thrownBy RetainedBackendCircuitGate.verify(
          c.copy(modules = c.modules.updated(idx, e.copy(params = Seq(IntParam("UNKNOWN", 1))))), seed)
      }
      val top = c.modules.head.asInstanceOf[Module]
      val body = top.body.asInstanceOf[Block]
      an[IllegalArgumentException] should be thrownBy RetainedBackendCircuitGate.verify(
        c.copy(modules = c.modules.updated(0, top.copy(body = Block(body.stmts.tail)))), seed)
    }
  }
  it should "preserve an ICG pulse and capture both live enables only in the low phase" in {
    val gate = new ClockGateBlackBox("gate", () => ())
    val tpe = ClockType
    def clk(n: Int): BigInt = gate.getOutput(Seq(BigInt(n)), tpe, "clk_o")
    clk(0) shouldBe BigInt(0)
    gate.inputChanged("en_i", 0); gate.inputChanged("test_en_i", 0)
    clk(1) shouldBe BigInt(0)
    gate.inputChanged("en_i", 1) // cannot create a high-phase edge
    clk(1) shouldBe BigInt(0)
    clk(0) shouldBe BigInt(0); clk(1) shouldBe BigInt(1)
    gate.inputChanged("en_i", 0) // cannot truncate current pulse
    clk(1) shouldBe BigInt(1)
    clk(0) shouldBe BigInt(0); clk(1) shouldBe BigInt(0)
    clk(0); gate.inputChanged("test_en_i", 1); clk(1) shouldBe BigInt(1)
    gate.inputChanged("test_en_i", 0); clk(1) shouldBe BigInt(1)
    clk(0); clk(1) shouldBe BigInt(0)
  }
  it should "sample live pre-edge inputs once regardless of callback versus Q-evaluation order" in {
    for (callbackFirst <- Seq(false, true)) {
      val ep = new EndpointBlackBox("ep", false, () => ())
      val ins = RetainedEndpointFunctionalModel.InputWidths.filterNot(_._1.startsWith("seed_"))
      for ((n, _) <- ins if n != "clk_i") ep.inputChanged(n, 0)
      ep.inputChanged("rst_ni", 1)
      def q(clock: Int): BigInt = ep.getOutput(Seq(BigInt(clock), BigInt(1)), UIntType(IntWidth(1)), "out_valid_o")
      q(0)
      ep.inputChanged("cmd_i", 0x220); ep.inputChanged("cmd_valid_i", 1)
      def rise(): Unit = {
        if (callbackFirst) ep.clockChange(treadle2.executable.PositiveEdge, "ep.clk_i")
        q(1)
        if (!callbackFirst) ep.clockChange(treadle2.executable.PositiveEdge, "ep.clk_i")
        q(1) // repeated settle is not a second physical edge
      }
      rise(); q(0)
      ep.inputChanged("cmd_valid_i", 0); ep.inputChanged("step_valid_i", 1)
      ep.inputChanged("step_clear_i", 1); ep.inputChanged("step_context_i", 0)
      ep.inputChanged("step_a_i", BigInt("3f80", 16)); ep.inputChanged("step_b_i", BigInt("3f80", 16))
      rise()
      ep.state.diagnostics._1 shouldBe 1L
      q(1); ep.state.diagnostics._1 shouldBe 1L
    }
  }

}
