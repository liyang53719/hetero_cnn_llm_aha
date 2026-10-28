// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
/** Private accepted-profile numeric schedule, not an untrusted host override.
  * One hardware definition supports both schedules. Values2/3 fail closed.
  * Candidate implementation is not official-model/HardFloat qualification. */
class GdnRuntimeChunkNumericPolicy extends Bundle {
  val cumsum = UInt(2.W)
  val decay = UInt(2.W)
}
object GdnRuntimeChunkNumericPolicy {
  val LegacyAscending = 0
  val GuardedTwoSum = 1
  val LegacyDecay = 0
  val GradualDecay = 1
  def admitted(p:GdnRuntimeChunkNumericPolicy):Bool=p.cumsum<=1.U && p.decay<=1.U
}
