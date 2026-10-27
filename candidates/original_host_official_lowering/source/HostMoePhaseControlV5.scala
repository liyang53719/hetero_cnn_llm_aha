// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** PRIVATE final phase retirement, never a Host grant or a routed-loop result.
  * The unique original parent must produce this from its retained accepted
  * lease, actual shared+eight-routed merge/write-ACK, and real resource ledger.
  * Success is offered only after BOTH Guard.range and allocator.lifetime have
  * actually released. resourcesRetired is a checked receipt field, not itself
  * the source of permission to release either owner. Failed terminals may have
  * resourcesRetired=false and require isolation; unknown identities never retire.
  * Current faults remain live sidebands after this held receipt was created.
  */
class HostMoePhaseRetirementV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val outputAddress=UInt(64.W);val acknowledgedWriteBytes=UInt(64.W)
  val usefulMacs=UInt(64.W);val executedMacs=UInt(64.W)
  val status=UInt(8.W);val resourcesRetired=Bool()
}

/** Wiring only, no Module / registers / arithmetic / second scheduler.
  * Called INSIDE the original parent. Private lifetime fences, grant consumer,
  * phase jobs and final retirement still require their actual parent producers.
  * The metadata event is not used to generate ready; it is checked on fire by
  * the original Commands, allocator and one Guard. Bad allocator proposals may
  * be consumed without a reservation and therefore cannot be called acceptance.
  */
object HostMoePhaseControlV5 {
  def connectMetadata(cmd:HostBlockCommandsV4,guard:HostRuntimeOwnerGuardV5,
      allocator:HostRuntimeMoePhaseAllocatorV5):Unit={
    allocator.io.authority:=cmd.io.runtimeAuthority
    allocator.io.liveRegionConflict:=cmd.io.moeRegionConflict
    allocator.io.propose<>cmd.io.moePhase
    cmd.io.moePhaseFailure<>allocator.io.failure
    guard.io.reserve<>allocator.io.ownerReserve
    allocator.io.ownerReservation<>guard.io.reservation
  }
}
