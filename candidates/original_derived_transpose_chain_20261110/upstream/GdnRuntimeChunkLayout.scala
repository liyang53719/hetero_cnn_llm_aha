// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Private scheduler-retained layout, not host-supplied producer authority.
  * One fixed expanded prepared format; runtime counts change span, not RTL.
  * Reuse the published maximum32 GdnChunkStageReceipt and unchanged context.
  */
class GdnRuntimeChunkLayout extends Bundle {
  val keyHeads = UInt(6.W)
  val valueHeads = UInt(6.W)
  val layoutId = UInt(2.W)
  val layoutVersion = UInt(8.W)
  val rowBytes = UInt(32.W)
}
object GdnRuntimeChunkLayout {
  def admitted(p: GdnRuntimeChunkLayout): Bool =
    p.keyHeads === 16.U && (p.valueHeads === 16.U || p.valueHeads === 32.U) &&
      p.layoutId === 0.U && p.layoutVersion === 1.U && p.rowBytes === p.valueHeads * 1600.U
}

/** Actual phase2 decay/result identity, retained privately until phase15.
  * No persistent publication, new exp policy, profile elab or arithmetic unit.
  * The scheduler must bind this to its own transaction/profile/producer lease;
  * a caller-constructed valid bit is not execution provenance.
  */
class GdnRuntimeChunkPrivateDecay extends Bundle {
  val context = new GdnChunkJob
  val layout = new GdnRuntimeChunkLayout
  val head = UInt(5.W)
  val chunk = UInt(1.W)
  val value = UInt(32.W)
  val valid = Bool()
}
