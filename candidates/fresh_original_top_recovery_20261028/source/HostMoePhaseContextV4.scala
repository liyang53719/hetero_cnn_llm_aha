// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** PRIVATE phase identity, NOT UnifiedBlockDispatchV1 or a full-block launch.
  * The original Host owns the complete844-bit accepted envelope; original
  * typed readers and actual postnorm ACK own all three tensor views below.
  * No invented flat weights/state/KV/cache fields exist in this phase ABI.
  * Equality of these bits is necessary but never creates execution authority.
  * Parent must capture this together with the8 weights and full postnorm
  * job/result at the SAME actual clean metadata event, then acquire an actual
  * allocator lease and physical-resource ownership before offering any work.
  */
class HostMoePhaseContextV4 extends Bundle {
  val version=UInt(8.W)
  val phase=UInt(8.W)
  val transactionId=UInt(64.W)
  val host=new HostCommandLaunchV4
  val profile=new UnifiedRuntimeProfile
  val tokens=UInt(16.W)
  val postnormOwnerSequence=UInt(32.W)
  val input=new DecodedTensor // actual postnorm output, not original block input
  val residual=new DecodedTensor // actual postmixer residual consumed by postnorm
  val output=new DecodedTensor // actual new rootD, final MoE residual destination
}
object HostMoePhaseContextV4 {
  val Version=1
  val MoePhase=1 // routed + shared + residual phase; no full-block completion
  def fromActualMetadata(a:HostRuntimeAuthoritySnapshotV4):(HostMoePhaseContextV4,Bool)={
    val c=Wire(new HostMoePhaseContextV4)
    c.version:=Version.U;c.phase:=MoePhase.U;c.transactionId:=a.transaction
    c.host:=a.launch;c.profile:=a.profile;c.tokens:=a.postnormJob.m
    c.postnormOwnerSequence:=a.postnormJob.tag
    c.input:=a.postnormOutputTensor;c.residual:=a.postnormResidual;c.output:=a.moeOutput
    val (p,known)=UnifiedRuntimeProfile.decode(a.launch.profileId)
    val j=a.postnormJob;val r=a.postnormResult
    def matrix(t:DecodedTensor):Bool=t.dtype===5.U && t.rank===2.U &&
      t.dims(0)===j.m && t.dims(1)===2048.U && t.dims(2)===1.U && t.dims(3)===1.U &&
      t.elementCount===(j.m.pad(64)<<11) && t.payloadBytes===(j.m.pad(64)<<12) &&
      t.address(5,0)===0.U && t.address<t.paddedEnd &&
      t.paddedEnd.pad(80)===t.address.pad(80)+t.payloadBytes.pad(80) &&
      t.paddedEnd<=(BigInt(1)<<56).U
    val profile=known && (a.launch.profileId===3.U || a.launch.profileId===4.U) &&
      p.asUInt===a.profile.asUInt && p.hidden===2048.U && p.mlp===1.U
    val source=j.kind===QwenOwnerKind.GdnRmsNorm.U && j.m>=1.U && j.m<=128.U &&
      j.n===2048.U && j.k===2048.U && j.activationBf16 && j.weightBf16 && j.outputBf16 &&
      j.a===a.postnormResidual.address && j.dst===a.postnormOutputTensor.address &&
      j.writeBytes===(j.m.pad(64)<<12) && r.tag===j.tag &&
      r.status===Status.Ok.U && r.writeBytes===j.writeBytes
    // This Bool denotes only a clean actual metadata event, NOT lease/grant.
    // No registered state or bypass permits a software lookalike to acquire it.
    val event=a.accepted && a.moeWeightsAccepted && a.postnormCommitValid &&
      !a.currentFault && HostCommandLaunchV4.known(a.launch) && profile && source &&
      matrix(a.postnormOutputTensor) && matrix(a.postnormResidual) && matrix(a.moeOutput)
    (c,event)
  }
}
