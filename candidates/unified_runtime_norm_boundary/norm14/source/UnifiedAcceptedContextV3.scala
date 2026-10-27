// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
/** No zero sentinel: transaction0 is the original admission's first identity.
  * Authority is actual admission.active AND the entire retained dispatch.
  * Equality alone on an arbitrary input packet cannot grant an owner. */
object UnifiedAcceptedContextV3 {
  def matches(active:Bool,accepted:UnifiedBlockDispatchV1,offered:UnifiedBlockDispatchV1):Bool =
    active && accepted.asUInt===offered.asUInt
}
