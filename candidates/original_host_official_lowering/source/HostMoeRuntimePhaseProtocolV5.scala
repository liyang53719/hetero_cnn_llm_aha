// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** PRIVATE fixed-role views read/validated by the actual Host descriptor path.
  * Linear weights are already in original Dense [K,N] order; expert views are
  * [E,K,N]. No implicit transpose, cast, padding, or host-written grant bit.
  * The source image/DDR service must establish this layout, not this bundle.
  */
object HostMoeWeightRoleV4 {
  val Router=0; val ExpertGate=1; val ExpertUp=2; val ExpertDown=3
  val SharedGate=4; val SharedUp=5; val SharedDown=6; val SharedGateLogit=7
  val Count=8
}

/** Actual phase allocation produced only after an owned postnorm job's real
  * successful write-ACK terminal and the original parent live resource fence.
  * HostCommandLaunchV4 is version WIDTH8, VALUE1. This V5 lease uses the
  * private phase-only HostMoePhaseContextV4, never a fabricated full-block V1.
  * Its input/residual/output are actual typed phase views, and host is the
  * complete accepted envelope. Full8 weight views below share the same actual
  * clean metadata capture event as context and postnormJob/postnormResult.
  * Private packet equality alone never establishes that producer provenance.
  * This type is not a new Host port and is not an admission capability by itself.
  */
class HostMoeRuntimePhaseLeaseV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W) // allocator starts at1, no wrap; NOT transactionId
  val firstOwnerSequence=UInt(32.W)
  val hostEpoch=UInt(16.W)
  val postnormJob=new QwenOwnerJob
  val postnormResult=new QwenOwnerResult // actual result.fire; not host data
  val postnormOwnerSequence=UInt(32.W) // original logical job.tag, never relabeled
  val postnormPhysicalSequence=UInt(32.W) // actual one-Guard retirement sideband
  val postnormBase=UInt(64.W)
  val residualBase=UInt(64.W)
  val weights=Vec(HostMoeWeightRoleV4.Count,new DecodedTensor)
  val metadataBase=UInt(64.W) // 16KiB token/expert route map
  val descriptorBase=UInt(64.W) // reserved16KiB for real ACKed descriptor records
  val routerLogits=UInt(64.W) // BF16[128,256],64KiB capacity
  val gatheredInput=UInt(64.W) // BF16[128,2048],512KiB capacity
  val gateOutput=UInt(64.W) // BF16[128,512],128KiB capacity
  val upOutput=UInt(64.W)
  val activationOutput=UInt(64.W)
  val routedDown=UInt(64.W) // all1024 routed rows,4MiB; NEVER reused before merge fence
  val sharedDown=UInt(64.W) // BF16[128,2048],512KiB capacity
  val mergedOutput=UInt(64.W) // separate BF16[128,2048],512KiB capacity
  val allocationBase=UInt(64.W)
  val allocationEnd=UInt(64.W)
}

/** Private staged result, NOT a block completion/release. Routed outputs must
  * remain resident until the real token-nine merge readers retire. Missing N1
  * gate/official tie/activation qualification cannot be represented as success
  * for shared contribution or full MoE merely because this loop has finished.
  */
class HostMoeRoutedPhaseResultV5 extends Bundle {
  val transactionId=UInt(64.W);val allocationSequence=UInt(64.W)
  val groups=UInt(9.W);val routedRows=UInt(11.W)
  val nextOwnerSequence=UInt(32.W)
  val status=UInt(8.W);val locallyDrained=Bool();val resetRequired=Bool()
  val routedDownBase=UInt(64.W)
}

/** One immutable physical32 reservation for the WHOLE phase. Routed consumers
  * use only offsets0..1280, even if fewer than256 experts are present. Tail
  * offsets never use routed.nextOwnerSequence and unused IDs are never recycled.
  * These are owner identities, not arithmetic operation counts. Tail operation
  * routing is group-scope and still needs its actual V3 resource ledger.
  */
object HostMoeOwnerRangeV5 {
  val RoutedCount=1281
  val SharedFfnFirst=1281 // gate/up/activation/down: four consecutive identities
  val SharedFfnCount=4
  val SharedGateDense=1285
  val SharedSigmoid=1286
  val Merge=1287
  val Residual=1288
  val Count=1289
  val EndLimit=BigInt("ffffffff",16) // exclusive; allones is never issued
  val MaximumFirst=EndLimit-Count
  require(SharedFfnFirst==RoutedCount && SharedGateDense==SharedFfnFirst+SharedFfnCount)
  require(SharedSigmoid==SharedGateDense+1 && Merge==SharedSigmoid+1 && Residual==Merge+1 && Count==Residual+1)
}
