// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

/** Bounded host-only progress, not a model callback or simulated hardware.
  * Process CPU includes this JVM's threads; wall is monotonic elapsed time.
  * Counts supplied by the fixture mean COMPLETED host calls/handshakes, not a
  * guessed hardware cycle or arithmetic-result count. Missing .end is pending
  * or interrupted/failed work; it is never treated as phase success.
  */
object RetainedServicePhaseObserver {
  private val origin = System.nanoTime()
  private val process = ProcessHandle.current()
  private var sequence = 0
  def mark(phase: String, completedStepCycles: Long = -1L,
    completedExpectCalls: Long = -1L, driverGroupHandshakes: Long = -1L,
    driverWideStepHandshakes: Long = -1L): Unit = synchronized {
    require(sequence < 96 && phase.matches("[a-zA-Z0-9_.-]{1,64}"), "bounded fixed phase observation")
    val cpu = process.info().totalCpuDuration()
    require(cpu.isPresent, "JDK process CPU duration unavailable: do not substitute zero")
    sequence += 1
    val wall = System.nanoTime() - origin
    val processCpu = cpu.get().toNanos
    println(s"""BACKEND_PHASE {"sequence":$sequence,"phase":"$phase","process_cpu_ns":$processCpu,"elapsed_wall_ns":$wall,"completed_step_cycles":$completedStepCycles,"completed_expect_calls":$completedExpectCalls,"driver_group_handshakes":$driverGroupHandshakes,"driver_wide_step_handshakes":$driverWideStepHandshakes}""")
    System.out.flush()
  }
  def measured[A](phase: String)(body: => A): A = {
    mark(phase + ".begin")
    val result = body
    mark(phase + ".end")
    result
  }
}
