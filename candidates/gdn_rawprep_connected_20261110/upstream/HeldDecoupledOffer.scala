// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

final case class HeldDecoupledOfferSignals(valid:Bool,held:Bool,fire:Bool)
/** One control bit per interface, no payload storage or arithmetic. A caller
  * must preserve intent AND payload while held, until the actual fire. Fault
  * suppresses only a not-yet-presented offer; it cannot cancel a commitment.
  * Caller state must not abandon its issue state while held && !fire. This
  * pattern supplies no cancellation handshake and no bounded recovery.
  */
object HeldDecoupledOffer {
  def apply(intent:Bool,ready:Bool,suppressNew:Bool):HeldDecoupledOfferSignals={
    val held=RegInit(false.B)
    val visible=intent && (!suppressNew || held)
    when(visible){held:= !ready}
    assert(!held || intent,"held Decoupled intent must persist until fire")
    HeldDecoupledOfferSignals(visible,held,visible && ready)
  }
}
