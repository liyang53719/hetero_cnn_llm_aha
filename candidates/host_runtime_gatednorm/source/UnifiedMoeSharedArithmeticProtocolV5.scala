// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Fixed private client numbering. No profile-specialized constructors. */
object UnifiedMoeArithmeticClientV5 {
  val RouterScalar=0;val ActivationScalar=1;val SigmoidScalar=2
  val RouterFormat=3;val ActivationFormat=4;val SigmoidFormat=5
  val MergeVector=6;val ResidualVector=7
  val OrdinaryNormScalar=8;val OrdinaryNormFormat=9
  // Aliases of the SAME ordinary slots; no extra client or physical capacity.
  val OrdinaryConvScalar=8;val OrdinaryConvFormat=9
  val OrdinaryConvStage=70
  val OrdinaryConvMaximumOperations=Seq(13631488,2097152)
  val OrdinaryRawPrepScalar=8;val OrdinaryRawPrepFormat=9
  val OrdinaryRawPrepStage=71
  // Covers32-head Ascending128 as well as TorchCpuDefault128. This is NOT
  // exact success: parent supplies the actual post-ALog prepare.fire counts.
  val OrdinaryRawPrepMaximumOperations=Seq(3731456,4096)
  val OrdinaryChunkScalar=8;val OrdinaryChunkVector=10
  val OrdinaryChunkStage=72
  val OrdinaryChunkMaximumOperations=Seq(194624,42506240)
  val OrdinaryGatedNormScalar=8;val OrdinaryGatedNormFormat=9
  val OrdinaryGatedNormStage=73
  val OrdinaryGatedNormMaximumOperations=Seq(5259264,1048576)
  val Count=11
  val ScalarClients=Seq(0,1,2,8);val FormatClients=Seq(3,4,5,9)
  val VectorClients=Seq(6,7);val BankClients=FormatClients++VectorClients++Seq(OrdinaryChunkVector)
  val Stages=Seq(64,65,66,64,65,66,67,68,69,69,72)
  val Resources=Seq(2,2,2,1,1,1,1,1,2,1,1)
  // Bounds, not authority or inferred success. Top supplies exact M/R counts.
  val MaximumOperations=Seq(133120,393216,512,1024,131072,128,294912,16384,1332736,262144,42506240)
}
/** Authority domains are not capabilities inferred from raw request bits.
  * Original Top supplies these ONLY from its actual allocator/Guard events. */
object UnifiedArithmeticAuthorityKindV5 {
  val MoEAllocation=0;val OrdinaryNorm=1;val OrdinaryConv=2;val OrdinaryRawPrep=3;val OrdinaryChunk=4;val OrdinaryGatedNorm=5
}
/** Delivered only by the original Top's actual accepted child start event,
  * under its actual allocator/Guard lease. Ordinary slots8..10 use the actual
  * ordinary Guard physicalJob.fire (Norm/Conv), or RawPrep's actual
  * prepare.fire AFTER that real Guard authority and successful A_log reads.
  * RawPrep kind3/stage71 uses data-dependent exact counts captured at prepare,
  * not a geometry upper bound or a new grant inferred from raw requests.
  * Kinds1/2/3 use Scalar8/Format9; Chunk kind4/stage72 uses Scalar8/Vector10,
  * NEVER Format9. Chunk provenance is the actual Guard job and acknowledged
  * RawPrep dependency, not an arbitrary schema-compatible input. All operations
  * have separate bounds. No ordinary operation fabricates a MoE allocation.
  * Ordinary allocationValid=false/allocationSequence=0 means NOT ALLOCATED;
  * ownerSequence0 is a valid first actual Guard owner. Old slots0..7 still
  * REQUIRE a real nonzero MoE allocation with allocationValid=true. Not a host grant or raw-port hint.
  * allocation/epoch remain full-width private side-ledger state. The physical
  * V3 tag remains197 bits; txn/owner/stage/serial correlate it to this snapshot.
  */
class UnifiedMoeArithmeticLeaseV5 extends Bundle {
  val lease=new UnifiedSharedLeaseV3
  val authorityKind=UInt(3.W)
  val allocationValid=Bool()
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

/** Private ordinary vector operation. The original V2 payload/policy2 ABI is
  * untouched. formatOnly and gradual are mutually exclusive explicit modes;
  * raw policy3 remains diagnostic, NEVER gradual3 or format4. Gradual requires
  * canonical payload policy0 and uses physical V4 policy3 with raw FP32 values
  * and all five actual ALU flags. Format requires canonical policy0,
  * multiply=false/all b=0; low16 a are raw FP32. The one V4 bank actually
  * rounds them; high16 lanes are actual +0. Neither mode adds a bank. */
class UnifiedOrdinaryVectorRequestV5 extends Bundle {
  val formatOnly=Bool()
  val gradual=Bool()
  val payload=new UnifiedVectorRequestV2
}
class UnifiedOrdinaryVectorResultV5 extends Bundle {
  val formatOnly=Bool()
  val gradual=Bool()
  val arithFlagsValid=Bool()
  // Format returns actual expanded BF16 values, zero reserved flags marked
  // invalid above. Consumer extracts bits31:16; it must not round again.
  val payload=new UnifiedVectorResultV2
}
