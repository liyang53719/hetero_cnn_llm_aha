// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Uniform candidate Host ABI: 833 legacy bits plus 8 version bits and 3
  * profile bits. Version is a VALUE of 1, not the number 8. No host-provided
  * transaction, free dimensions or numerical policy. Descriptor geometry and
  * permissions still require the actual original DDR parser/owner checks.
  * This is an ABI migration candidate, not qualification of five runtime paths.
  */
class HostCommandLaunchV4 extends HostCommandLaunch {
  val version=UInt(8.W)
  val profileId=UInt(3.W)
}
object HostCommandLaunchV4 {
  val Version=1
  val Width=844
  def known(l:HostCommandLaunchV4):Bool = l.version===Version.U && l.profileId<=4.U
}

/** Private retained metadata. accepted means a valid accepted command-table
  * envelope, NOT an execution grant. Only actual ownerValidated/ownerAccepted
  * events can acquire work; result holding (including Unsupported) is not a
  * grant. Full transaction zero is valid and has no sentinel meaning.
  */
class HostRuntimeAuthoritySnapshotV4 extends Bundle {
  val accepted=Bool();val launch=new HostCommandLaunchV4
  val transaction=UInt(64.W);val identityExhausted=Bool()
  val profile=new UnifiedRuntimeProfile
  val currentFault=Bool()
  val semanticSourceValid=Vec(16,Bool());val semanticSource=Vec(16,new DecodedTensor)
  val ownerValidated=Bool();val ownerOffered=Bool();val ownerAccepted=Bool()
  val ownerJob=new QwenOwnerJob;val ownerReturned=Bool();val ownerResult=new QwenOwnerResult
  // Actual descriptor/policy validation creates these private semantic facts.
  // An arbitrary GdnRmsNorm kind or matching pointer is not postnorm authority.
  val ownerPostnormValidated=Bool()
  val ownerInputTensor=new DecodedTensor
  // Durable receipt captured ONLY from the successful actual postnorm ACK.
  // It survives metadata scanning; no requirement to re-invent a done pulse.
  val postnormCommitValid=Bool()
  val postnormJob=new QwenOwnerJob;val postnormResult=new QwenOwnerResult
  val postnormResidual=new DecodedTensor;val postnormOutputTensor=new DecodedTensor
  // Source event from the same original readers; not allocation authority.
  val moeWeightsAccepted=Bool();val moeWeights=Vec(8,new DecodedTensor)
  val moeOutput=new DecodedTensor
  val pc=UInt(16.W)
}
