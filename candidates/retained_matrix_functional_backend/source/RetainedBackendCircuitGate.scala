// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

import firrtl2.ir._

/** Pre-simulation, same-elaboration AST gate, not a source-text port count.
  * Neither fixture defaults nor callback values certify an absent/wrong port.
  * This object returns the complete reachable instance -> defname map; the
  * factory must consume exactly that map. It does not certify RTL arithmetic.
  */
object RetainedBackendCircuitGate {
  private val baseOut = Map("cmd_ready_o" -> 1, "step_ready_o" -> 1, "out_valid_o" -> 1,
    "out_context_o" -> 3, "out_last_o" -> 1, "out_acc_o" -> 16384,
    "completion_valid_o" -> 1, "completion_data_o" -> 56, "protocol_error_o" -> 1)
  private val seedOut = Map("seed_begin_ready_o" -> 1, "seed_beat_ready_o" -> 1,
    "seed_commit_ready_o" -> 1, "seed_ack_valid_o" -> 1, "seed_ack_context_o" -> 3,
    "seed_ack_group_tag_o" -> 32, "seed_ack_group_sequence_o" -> 32,
    "seed_ack_source_generation_o" -> 32, "seed_ack_error_o" -> 1,
    "seed_reset_required_o" -> 1, "arithmetic_busy_o" -> 5, "arithmetic_out_valid_o" -> 1)
  def expected(seed: Boolean, endpoint: Boolean): Map[String, (Direction, Type)] = {
    if (!endpoint) Map("clk_i" -> (Input, ClockType), "en_i" -> (Input, UIntType(IntWidth(1))),
      "test_en_i" -> (Input, UIntType(IntWidth(1))), "clk_o" -> (Output, ClockType))
    else {
      val in = RetainedEndpointFunctionalModel.InputWidths.filter { case (n, _) => seed || !n.startsWith("seed_") }
        .map { case (n, w) => n -> ((Input: Direction), if (n == "clk_i") ClockType else UIntType(IntWidth(w))) }
      val out = (baseOut ++ (if (seed) seedOut else Map.empty[String, Int]))
        .map { case (n, w) => n -> ((Output: Direction), UIntType(IntWidth(w)): Type) }
      in ++ out
    }
  }
  def verify(circuit: Circuit, seed: Boolean): Map[String, String] = {
    require(circuit.modules.map(_.name).distinct.size == circuit.modules.size, "unique module declarations")
    val modules = circuit.modules.map(m => m.name -> m).toMap
    require(modules.get(circuit.main).exists(_.isInstanceOf[Module]), "actual regular top")
    val bindings = scala.collection.mutable.Map.empty[String, String]
    def visit(moduleName: String, prefix: String, ancestors: Set[String]): Unit = {
      require(!ancestors(moduleName), "recursive module hierarchy")
      val module = modules.getOrElse(moduleName, throw new IllegalArgumentException("unresolved actual module " + moduleName))
      module match {
        case e: ExtModule =>
          require(e.defname == "qwen2_matrix_command_endpoint" || e.defname == "tc_clk_gating", "unknown actual extmodule " + e.defname)
          val endpoint = e.defname == "qwen2_matrix_command_endpoint"
          val exp = expected(seed, endpoint)
          require(e.ports.map(_.name).distinct.size == e.ports.size, "duplicate port declaration")
          val actual = e.ports.map(p => p.name -> ((p.direction: Direction), p.tpe)).toMap
          require(actual == exp, "exact complete ExtModule name/direction/type/width mismatch " + e.name)
          val params = if (endpoint && seed) Seq(IntParam("ENABLE_ACCUMULATOR_SEED", BigInt(1))) else Seq.empty
          require(e.params == params, "exact actual ExtModule parameters")
          require(prefix.nonEmpty && !bindings.contains(prefix), "unique instance path")
          bindings(prefix) = e.defname
        case m: Module =>
          def walk(s: Statement): Unit = {
            s match {
              case i: DefInstance => visit(i.module, if (prefix.isEmpty) i.name else prefix + "." + i.name, ancestors + moduleName)
              case _ => ()
            }
            s.foreachStmt(walk)
          }
          walk(m.body)
      }
    }
    visit(circuit.main, "", Set.empty)
    require(bindings.values.count(_ == "qwen2_matrix_command_endpoint") == 8, "full eight512 endpoints")
    require(bindings.values.count(_ == "tc_clk_gating") == 8 && bindings.size == 16, "exact eight ICG plus eight endpoints")
    bindings.toMap
  }
}
