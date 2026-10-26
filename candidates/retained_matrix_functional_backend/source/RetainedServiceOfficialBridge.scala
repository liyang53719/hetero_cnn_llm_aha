// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import chisel3.RawModule
import firrtl2.{AnnotationSeq, CircuitState}
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.RetainedBackendCircuitGate
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths, StandardOpenOption}
import treadle2.{ClockInfoAnnotation, TreadleCircuitStateAnnotation}
import treadle2.stage.phases.{GetFirrtlAst, PrepareAst, SetImplicitOutputInfo}
import treadle2.executable.ClockInfo

/** Test-backend adapter, not a hardware transform or a second elaboration.
  * Calls the pinned official chiseltest Compiler used by ChiselScalatestTester.
  * Serialized IR is evidence only: the factory and Treadle receive the exact
  * same prepared Circuit object, never a reparsed/repaired text representation.
  * Preparation follows all three official TreadleTesterPhase pre-construction
  * phases; the caller uses its final official CreateTester constructor step.
  */
object RetainedServiceOfficialBridge {
  private def checkAnnotations(state: CircuitState): Unit = {
    require(!state.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),
      "unsupported official Chisel-to-firrtl2 annotation")
    require(!state.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),
      "CircuitState annotations must not carry a second circuit")
  }
  private def retain(name: String, text: String): Unit = {
    val directory = Paths.get("service-feedback")
    Files.createDirectories(directory)
    Files.write(directory.resolve(name), text.getBytes(StandardCharsets.UTF_8),
      StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
  }
  def prepare[M <: RawModule](gen: () => M): (CircuitState, AnnotationSeq) = {
    val (high, _) = Compiler.elaborate(gen, Seq(TargetDirAnnotation("service-feedback")), Seq.empty)
    checkAnnotations(high)
    retain("official-bridge-high.fir", high.circuit.serialize)
    val highBindings = RetainedBackendCircuitGate.verify(high.circuit, seed = false)
    val low = Compiler.toLowFirrtl(high)
    checkAnnotations(low)
    retain("official-bridge-low.fir", low.circuit.serialize)
    val lowBindings = RetainedBackendCircuitGate.verify(low.circuit, seed = false)
    require(lowBindings == highBindings, "same-elaboration exact external instance paths and definitions")
    val obtained = GetFirrtlAst.transform(treadleAnnotations(low))
    val withOutputInfo = SetImplicitOutputInfo.transform(obtained)
    val preparedAnnos = (new PrepareAst).transform(withOutputInfo)
    val preparedStates = preparedAnnos.collect { case TreadleCircuitStateAnnotation(s) => s }
    require(preparedStates.size == 1, "exactly one officially prepared CircuitState")
    val prepared = preparedStates.head
    require(!prepared.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),
      "unsupported prepared annotation")
    retain("official-bridge-prepared.fir", prepared.circuit.serialize)
    val preparedBindings = RetainedBackendCircuitGate.verify(prepared.circuit, seed = false)
    require(preparedBindings == lowBindings, "final prepared exact external bindings unchanged")
    (prepared, preparedAnnos)
  }
  private def treadleAnnotations(state: CircuitState): AnnotationSeq = {
    checkAnnotations(state)
    RetainedBackendCircuitGate.verify(state.circuit, seed = false)
    val toplevel = TopmoduleInfo(state.circuit)
    require(toplevel.clocks == Seq("clock"), "one original service clock")
    // This is the pinned TreadleSimulator.createContext clock/Circuit route.
    // There are no WriteVcdAnnotation or PlusArgsAnnotation inputs to translate.
    ClockInfoAnnotation(toplevel.clocks.map(name => ClockInfo(name))) +:
      (FirrtlCircuitAnnotation(state.circuit) +: state.annotations)
  }
}
