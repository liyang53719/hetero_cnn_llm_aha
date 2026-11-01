// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Pure Scala references to EXISTING hardware ports. These case classes are not
  * Bundles or Modules and instantiate no wires, storage, arithmetic or grants.
  * Production connect wrappers pass their real IO. Bounded protocol fixtures
  * drive the same boundary while elaborating the SAME helper implementation. */
object Rms32PortRefsV1 {
  case class ArithmeticIO(
    acquire:Vec[ValidIO[UnifiedMoeArithmeticLeaseV5]],
    retire:Vec[ValidIO[UnifiedMoeArithmeticRetireV5]],
    status:Vec[UnifiedMoeArithmeticClientStatusV5],
    formatRequest:Vec[DecoupledIO[UnifiedRawFp32FormatRequestV3]],
    formatResult:Vec[DecoupledIO[UnifiedRawFp32FormatResultV3]],
    rmsVectorRequest:DecoupledIO[UnifiedVectorElement32PayloadV4],
    rmsVectorResult:DecoupledIO[UnifiedVectorElement32ResultPayloadV4],resetRequired:Bool)
  case class Arithmetic(io:ArithmeticIO)
  def arithmetic(a:UnifiedMoeSharedArithmeticAdapterV5):Arithmetic=Arithmetic(ArithmeticIO(
    a.io.acquire,a.io.retire,a.io.status,a.io.formatRequest,a.io.formatResult,
    a.io.rmsVectorRequest,a.io.rmsVectorResult,a.io.resetRequired))
  case class GuardIO(job:DecoupledIO[QwenOwnerJob],physicalJob:DecoupledIO[QwenOwnerJob],
    physicalDone:DecoupledIO[QwenOwnerResult],localFault:Bool,acceptedTransaction:UInt,phaseReserved:Bool)
  case class Guard(io:GuardIO)
  def guard(g:HostRuntimeOwnerGuardV5):Guard=Guard(GuardIO(g.io.job,g.io.physicalJob,g.io.physicalDone,
    g.io.localFault,g.io.acceptedTransaction,g.io.phaseReserved))
  case class OwnerIO(
    rmsVectorRequest:Option[DecoupledIO[UnifiedVectorElement32PayloadV4]],
    rmsVectorResult:Option[DecoupledIO[UnifiedVectorElement32ResultPayloadV4]],
    rmsVectorDrained:Option[Bool],rmsVectorResetRequired:Option[Bool],rmsVectorPublished:Option[Bool],
    runtimeRms:Option[QwenRuntimeRmsClientV6],
    runtimeRmsDoneFire:Option[ValidIO[GdnRuntimeRmsNormResultV16]],
    runtimeElementwiseDoneFire:Option[ValidIO[GdnRuntimeElementwiseResultV15]],
    runtimeGqaDoneFire:Option[ValidIO[Bf16CausalGqaRuntimeResultV14]],
    runtimeKvAppendDoneFire:Option[ValidIO[Bf16KvAppendRuntimeResultV13]],
    runtimeRopeDoneFire:Option[ValidIO[PartialRopeRuntimeResultV12]],
    runtimeQkNormDoneFire:Option[ValidIO[QkNormRuntimeResultV11]],
    runtimeGatedDoneFire:Option[ValidIO[GdnRuntimeGatedNormResultV10]],
    runtimePrepPrepare:Option[DecoupledIO[GdnRuntimeRawPrepReadyV7]],
    runtimePrepDoneFire:Option[ValidIO[GdnRuntimeRawPrepResultV7]])
  case class Owner(io:OwnerIO)
  def owner(k:QwenOwnerKernel):Owner=Owner(OwnerIO(k.io.rmsVectorRequest,k.io.rmsVectorResult,
    k.io.rmsVectorDrained,k.io.rmsVectorResetRequired,k.io.rmsVectorPublished,k.io.runtimeRms,
    k.io.runtimeRmsDoneFire,k.io.runtimeElementwiseDoneFire,k.io.runtimeGqaDoneFire,k.io.runtimeKvAppendDoneFire,
    k.io.runtimeRopeDoneFire,k.io.runtimeQkNormDoneFire,k.io.runtimeGatedDoneFire,
    k.io.runtimePrepPrepare,k.io.runtimePrepDoneFire))
}
