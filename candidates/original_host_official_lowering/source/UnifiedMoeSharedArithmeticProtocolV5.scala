// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Fixed private client numbering. No profile-specialized constructors. */
object UnifiedMoeArithmeticClientV5 {
  val RouterScalar=0;val ActivationScalar=1;val SigmoidScalar=2
  val RouterFormat=3;val ActivationFormat=4;val SigmoidFormat=5
  val MergeVector=6;val ResidualVector=7
  val Count=8
  val Stages=Seq(64,65,66,64,65,66,67,68)
  val Resources=Seq(2,2,2,1,1,1,1,1)
  // Bounds, not authority or inferred success. Top supplies exact M/R counts.
  val MaximumOperations=Seq(133120,393216,512,1024,131072,128,294912,16384)
}
/** Delivered only by the original Top's actual accepted child start event,
  * under its actual allocator/Guard lease. Not a host grant or raw-port hint.
  * allocation/epoch remain full-width private side-ledger state. The physical
  * V3 tag remains197 bits; txn/owner/stage/serial correlate it to this snapshot.
  */
class UnifiedMoeArithmeticLeaseV5 extends Bundle {
  val lease=new UnifiedSharedLeaseV3
  val allocationSequence=UInt(64.W)
  val hostEpoch=UInt(16.W)
}
/** Actual matching child done.fire event, never a generated resource receipt.
  * It is captured as an intent; it cannot erase held/physical/returned debt.
  */
class UnifiedMoeArithmeticRetireV5 extends Bundle {
  val lease=new UnifiedMoeArithmeticLeaseV5
  val status=UInt(8.W)
}
class UnifiedMoeArithmeticClientStatusV5 extends Bundle {
  val lease=new UnifiedMoeArithmeticLeaseV5
  val active=Bool();val retiring=Bool()
  val counts=new UnifiedSharedOperationCountsV3
  // Reservation alone is not physical debt; numerical poison is separate.
  val resourcesDrained=Bool()
}
