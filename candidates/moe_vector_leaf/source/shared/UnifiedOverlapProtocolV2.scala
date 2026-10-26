// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** One versioned internal namespace shared by all runtime profiles. Not Host ABI. */
object UnifiedVectorPolicyV2 { val LegacyRaw=0;val Bf16MulRne=1;val Bf16AddRne=2 }
class UnifiedVectorRequestV2 extends Bundle {
  val policy=UInt(2.W);val multiply=Bool();val a=Vec(16,UInt(32.W));val b=Vec(16,UInt(32.W))
}
class UnifiedVectorResultV2 extends Bundle {
  val policy=UInt(2.W);val value=Vec(16,UInt(32.W));val flags=Vec(16,UInt(5.W));val error=Bool()
}
class UnifiedOverlapLeaseV2 extends Bundle {
  val transactionId=UInt(64.W);val ownerSequence=UInt(32.W);val stage=UInt(8.W)
  val token=UInt(32.W);val tileOrdinal=UInt(16.W);val expectedOperations=UInt(16.W)
}
class UnifiedOverlapTagV2 extends Bundle {
  val transactionId=UInt(64.W);val resource=UInt(2.W)
  val ownerSequence=UInt(32.W);val stage=UInt(8.W)
  val token=UInt(32.W);val tileOrdinal=UInt(16.W);val serial=UInt(16.W)
}
class UnifiedOverlapVectorRequestV2 extends Bundle {val identity=new UnifiedOverlapTagV2;val payload=new UnifiedVectorRequestV2}
class UnifiedOverlapVectorResultV2 extends Bundle {val identity=new UnifiedOverlapTagV2;val payload=new UnifiedVectorResultV2}
class UnifiedOverlapDoneV2 extends Bundle {
  val lease=new UnifiedOverlapLeaseV2;val issued=UInt(17.W);val returned=UInt(17.W)
  val operationCountsValid=Bool();val issuedSliceSteps=UInt(64.W)
  val status=UInt(8.W);val drained=Bool();val resetRequired=Bool()
}
class UnifiedOverlapReleaseIntentV2 extends Bundle {
  val lease=new UnifiedOverlapLeaseV2;val issued=UInt(17.W);val returned=UInt(17.W);val diagnosticStatus=UInt(8.W)
}
class UnifiedOverlapProducerFenceV2 extends Bundle {
  val lease=new UnifiedOverlapLeaseV2;val status=UInt(8.W);val drained=Bool()
}
