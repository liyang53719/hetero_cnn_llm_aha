// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

import firrtl2.ir.{ClockType, IntParam, IntWidth, Param, Type, UIntType}
import treadle2.{ScalaBlackBox, ScalaBlackBoxFactory}
import treadle2.executable.{NegativeEdge, PositiveEdge, Transition}

/** Simulator registration only; does not modify the Chisel hardware definition.
  * The final common circuit must use one fixed seed ABI for every profile.
  * Exact same-run Circuit AST validation precedes binding. Unknown extmodule,
  * duplicate instance, parameter, port direction/type or width is an error.
  * Call requireCompleteBinding after simulator construction AND at finish.
  */
final class RetainedMatrixModelFactory(val seedEnabled: Boolean, circuit: firrtl2.ir.Circuit) extends ScalaBlackBoxFactory {
  private val expectedInstances = RetainedBackendCircuitGate.verify(circuit, seedEnabled)
  private var endpointCount = 0
  private var gateCount = 0
  private val instanceNames = scala.collection.mutable.Set.empty[String]
  def requireCompleteBinding(): Unit = {
    require(endpointCount == 8 && gateCount == 8, "exact eight endpoints/eight ICG model bindings required")
    require(boxes.size == 16 && instanceNames.toSet == expectedInstances.keySet, "unique exact ABI-gated full4096 instance binding")
  }
  override def createInstance(instanceName: String, blackBoxName: String): Option[ScalaBlackBox] = {
    require(expectedInstances.get(instanceName).contains(blackBoxName), "actual ABI-gated instance identity")
    require(!instanceNames(instanceName), "duplicate backend instance " + instanceName)
    val impl: ScalaBlackBox = blackBoxName match {
      case "qwen2_matrix_command_endpoint" =>
        require(endpointCount < 8, "more than eight endpoint instances")
        endpointCount += 1
        new EndpointBlackBox(instanceName, seedEnabled, () => requireCompleteBinding())
      case "tc_clk_gating" =>
        require(gateCount < 8, "more than eight ICG instances")
        gateCount += 1
        new ClockGateBlackBox(instanceName, () => requireCompleteBinding())
      case _ => throw new IllegalArgumentException("unbound extmodule " + blackBoxName + " at " + instanceName)
    }
    instanceNames += instanceName
    Some(add(impl))
  }
}

private[model] object BackendPortChecks {
  def width(tpe: Type, expected: Int): Unit = tpe match {
    case UIntType(IntWidth(n)) => require(n == expected, "blackbox output width")
    case ClockType => require(expected == 1, "clock width")
    case _ => throw new IllegalArgumentException("unknown blackbox output type " + tpe)
  }
}

private[model] final class EndpointBlackBox(val name: String, seedEnabled: Boolean, complete: () => Unit)
    extends ScalaBlackBox {
  val state = new RetainedEndpointFunctionalModel(seedEnabled)
  private val baseInputs = RetainedEndpointFunctionalModel.InputWidths.filterNot(_._1.startsWith("seed_"))
  private val inputWidths = if (seedEnabled) RetainedEndpointFunctionalModel.InputWidths else baseInputs
  private val baseOutputs = Map("cmd_ready_o" -> 1, "step_ready_o" -> 1, "out_valid_o" -> 1,
    "out_context_o" -> 3, "out_last_o" -> 1, "out_acc_o" -> 16384,
    "completion_valid_o" -> 1, "completion_data_o" -> 56, "protocol_error_o" -> 1)
  private val seedOutputs = Map("seed_begin_ready_o" -> 1, "seed_beat_ready_o" -> 1,
    "seed_commit_ready_o" -> 1, "seed_ack_valid_o" -> 1, "seed_ack_context_o" -> 3,
    "seed_ack_group_tag_o" -> 32, "seed_ack_group_sequence_o" -> 32,
    "seed_ack_source_generation_o" -> 32, "seed_ack_error_o" -> 1,
    "seed_reset_required_o" -> 1, "arithmetic_busy_o" -> 5, "arithmetic_out_valid_o" -> 1)
  private val outputWidths = baseOutputs ++ (if (seedEnabled) seedOutputs else Map.empty[String, Int])
  private val stateDeps = Seq("clk_i", "rst_ni")
  private val observedInputs = scala.collection.mutable.Set.empty[String]
  private var sampledClock = BigInt(0)
  private var positiveCallbacks = 0L
  // Registers in Treadle separate Q from next-D. All non-reset inputs are
  // assigned after the state-only out_valid Q. Actual combinational ready
  // dependencies remain below. This prevents newly evaluated parent next-data
  // from being mistaken for the pre-edge inputs captured by this endpoint.
  override def getDependencies: Seq[(String, Set[String])] =
    inputWidths.keys.toSeq.sorted.filterNot(n => n == "clk_i" || n == "rst_ni")
      .map(n => n -> Set("out_valid_o"))
  private def observeClock(value: BigInt): Unit = {
    require(value == 0 || value == 1, "two-state actual endpoint clock")
    if (sampledClock == 0 && value == 1) {
      require(observedInputs.toSet == inputWidths.keySet - "clk_i", "all actual declared inputs assigned before first edge")
      state.setInput("clk_i", 1)
      state.risingEdge()
    }
    sampledClock = value
    state.setInput("clk_i", value)
  }
  private val seedBlockDeps = if (seedEnabled)
    Seq("seed_begin_valid_i", "seed_beat_valid_i", "seed_commit_valid_i", "seed_abort_i") else Seq.empty
  override def setParams(params: Seq[Param]): Unit = {
    val expected = if (seedEnabled) Seq(IntParam("ENABLE_ACCUMULATOR_SEED", BigInt(1))) else Seq.empty
    require(params == expected, "exact common seed parameter and no unknown parameters")
  }
  override def inputChanged(port: String, value: BigInt): Unit = {
    require(inputWidths.contains(port), "unknown/disabled endpoint input " + port)
    state.setInput(port, value)
    observedInputs += port
  }
  override def clockChange(transition: Transition, clockName: String): Unit = {
    require(clockName == name + ".clk_i" || clockName == "clk_i", "endpoint clock identity")
    // Callback ordering among siblings sharing a clock is not a total order.
    // Do not mutate state here. getOutput sees the real clock dependency and
    // commits once before publishing any Q, independent of callback ordering.
    if (transition == PositiveEdge) positiveCallbacks += 1
  }
  override def outputDependencies(port: String): Seq[String] = {
    require(outputWidths.contains(port), "unknown/disabled endpoint output " + port)
    port match {
      case "cmd_ready_o" => stateDeps ++ seedBlockDeps
      case "step_ready_o" => stateDeps ++ Seq("step_context_i", "out_ready_i") ++ seedBlockDeps
      case "seed_begin_ready_o" | "seed_beat_ready_o" | "seed_commit_ready_o" =>
        stateDeps ++ Seq("step_context_i", "step_valid_i", "out_ready_i") ++ seedBlockDeps
      case _ => stateDeps
    }
  }
  override def getOutput(inputValues: Seq[BigInt], tpe: Type, outputName: String): BigInt = {
    val width = outputWidths.getOrElse(outputName, throw new IllegalArgumentException("unknown output " + outputName))
    BackendPortChecks.width(tpe, width)
    require(inputValues.size == outputDependencies(outputName).size, "actual dependency values")
    observeClock(inputValues.head)
    val value = state.output(outputName)
    require(value >= 0 && value.bitLength <= width, "endpoint modeled output width")
    value
  }
  override def finish(): Unit = complete()
}

/** Exact low-transparent two-state ICG behavior, not combinational clk & en.
  * A low clock must be observed before first high output (RTL clk_en has no
  * reset and is X before that point; this backend does not pretend to model X).
  */
private[model] final class ClockGateBlackBox(val name: String, complete: () => Unit) extends ScalaBlackBox {
  private var enable = BigInt(0); private var testEnable = BigInt(0)
  private var latched = BigInt(0); private var clockLevel = BigInt(0)
  private var lowObserved = false
  private val seen = scala.collection.mutable.Set.empty[String]
  override def setParams(params: Seq[Param]): Unit = require(params.isEmpty, "original ICG default parameter only")
  // The low-transparent latch is the real storage cut, not an ignored input.
  // Outputs are evaluated before enable next-input assignment (official
  // ScalaBlackBox state ordering). A low-clock enable update writes the latch;
  // a high-clock update must NOT change the current pulse.
  override def getDependencies: Seq[(String, Set[String])] =
    Seq("en_i" -> Set("clk_o"), "test_en_i" -> Set("clk_o"))
  override def inputChanged(port: String, value: BigInt): Unit = {
    require(value == 0 || value == 1, "two-state ICG input")
    port match {
      case "en_i" => enable = value
      case "test_en_i" => testEnable = value
      case _ => throw new IllegalArgumentException("unknown ICG nonclock input " + port)
    }
    seen += port
    if (lowObserved && clockLevel == 0) latched = enable | testEnable
  }
  override def outputDependencies(port: String): Seq[String] = {
    require(port == "clk_o", "unknown ICG output")
    Seq("clk_i")
  }
  override def getOutput(inputValues: Seq[BigInt], tpe: Type, outputName: String): BigInt = {
    require(outputName == "clk_o" && inputValues.size == 1, "ICG output contract")
    BackendPortChecks.width(tpe, 1)
    val clk = inputValues.head
    require(clk == 0 || clk == 1, "two-state ICG clock")
    clockLevel = clk
    if (clk == 0) { lowObserved = true; latched = enable | testEnable }
    else require(lowObserved && seen.toSet == Set("en_i", "test_en_i"), "low clock and both actual inputs required before high")
    clk & latched
  }
  override def finish(): Unit = complete()
}
