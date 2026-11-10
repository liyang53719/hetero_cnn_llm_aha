// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Fixed private owner identity for ALL five profiles. Never a host grant.
  * A scheduler creates this from its accepted block snapshot and actual leaf
  * job.fire. GDN phase/head/chunk must not be copied from unaccepted pins.
  * V2's sixteen-bit operation ordinals remain a separately qualified MoE-only
  * interface. No narrowing conversion from this version is implicit.
  */
class UnifiedSharedOwnerIdentityV3 extends Bundle {
  val transactionId = UInt(64.W)
  val ownerSequence = UInt(32.W)
  val stage = UInt(8.W)
  val phase = UInt(5.W)
  val head = UInt(5.W)
  val chunk = UInt(1.W)
  val token = UInt(32.W)
  val tileOrdinal = UInt(16.W)
}
class UnifiedSharedLeaseV3 extends Bundle {
  val identity = new UnifiedSharedOwnerIdentityV3
  val resource = UInt(2.W)
  val expectedOperations = UInt(32.W)
}
class UnifiedSharedOperationTagV3 extends Bundle {
  val owner = new UnifiedSharedOwnerIdentityV3
  val resource = UInt(2.W)
  val serial = UInt(32.W)
}
class UnifiedSharedOperationCountsV3 extends Bundle {
  // Accepted includes any held-but-not-issued request. The extra bit makes
  // overflow observable rather than wrapping to an apparently empty ledger.
  val accepted = UInt(33.W)
  val issued = UInt(33.W)
  val returned = UInt(33.W)
}
class UnifiedSharedReleaseIntentV3 extends Bundle {
  val lease = new UnifiedSharedLeaseV3
  val counts = new UnifiedSharedOperationCountsV3
  val diagnosticStatus = UInt(8.W)
}
class UnifiedSharedReleaseAckV3 extends Bundle {
  val lease = new UnifiedSharedLeaseV3
  val counts = new UnifiedSharedOperationCountsV3
  val status = UInt(8.W)
  val drained = Bool()
  val resetRequired = Bool()
}

object UnifiedSharedOperationBoundsV3 {
  val MatrixQualification = 1
  val MoeMerge = 2
  val GdnLoad = 17
  val GdnDerived = 18
  val GdnTranspose = 19
  val GdnExecute = 32
  val MaxPhaseOperations = 131072
  val PhaseVectorOperations: Seq[(Int, Int)] = Seq(
    5 -> 65792, 6 -> 65792, 7 -> 32768, 8 -> 32768,
    9 -> 131072, 10 -> 512, 11 -> 131072, 12 -> 65536,
    13 -> 512, 14 -> 131072, 15 -> 1024, 16 -> 1024, 17 -> 0)
  require(PhaseVectorOperations.map(_._2).max == MaxPhaseOperations)
  require(PhaseVectorOperations.map(_._2.toLong).sum == 658944L)
  require(658944L * 32 * 2 == 42172416L)

  /** This is a bound/shape decoder, NOT proof of producer authority.
    * Valid for the pinned original phase5..17 schedule only. A future algorithm
    * change needs a new table and review rather than silently raising a cap.
    */
  def gdnPhaseVectorCount(phase: UInt): (Bool, UInt) = {
    val known = phase >= 5.U && phase <= 17.U
    val count = MuxLookup(phase, 0.U(32.W))(PhaseVectorOperations.map {
      case (p, n) => p.U -> n.U(32.W)
    })
    (known, count)
  }
  def ordered(c: UnifiedSharedOperationCountsV3): Bool =
    c.returned <= c.issued && c.issued <= c.accepted

  /** Refuse a new request at saturation; never truncate the accepted count to
    * make a32-bit serial. OwnerSequence has the same reject-before-wrap rule.
    * Already-held offers still retain their exact identity through poison.
    */
  def mayAccept(c: UnifiedSharedOperationCountsV3, expected: UInt): Bool = {
    require(expected.getWidth == 32)
    ordered(c) && c.accepted < expected.pad(33) && c.accepted < "hffffffff".U(33.W)
  }
  def nextOwnerAvailable(sequence: UInt): Bool = {
    require(sequence.getWidth == 32)
    sequence =/= "hffffffff".U(32.W)
  }
  def countsRetired(c: UnifiedSharedOperationCountsV3): Bool =
    ordered(c) && c.accepted === c.issued && c.issued === c.returned
  def exactSuccessfulCount(c: UnifiedSharedOperationCountsV3, expected: UInt): Bool =
    countsRetired(c) && c.returned === expected.pad(33)
  // None of these arithmetic predicates implies real resource/DDR drain.
  // A registered release commit additionally requires no held request/reply,
  // no pending raw response, matching real producer fence and no current fault.
  // Error may retire fewer operations only with those SAME real-drain proofs.
  // Reset/transaction reuse requires external isolation; this bundle is not an
  // epoch generator and does not make the untagged physical primitive replay-safe.
}
