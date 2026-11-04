// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Explicit receiver cancellation extends (does not silently retract) ready/valid.
  * ACK and fire are mutually exclusive. No payload buffer or accepted debt. */
object CancellableHeldDecoupledOfferV1 {
  def apply(intent:Bool,ready:Bool,suppressNew:Bool,cancelled:Bool):HeldDecoupledOfferSignals={
    val held=RegInit(false.B)
    val visible=intent && (!suppressNew || held)
    when(visible){held:= !ready}
    when(cancelled){held:=false.B}
    assert(!held || intent,"held intent must persist through fire or cancel ACK")
    assert(!cancelled || (intent && !(visible && ready)))
    HeldDecoupledOfferSignals(visible,held,visible && ready)
  }
}
