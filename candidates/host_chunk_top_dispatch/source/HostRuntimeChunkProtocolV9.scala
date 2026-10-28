// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private parent boundary of the actual Kernel Collection. No Host input can
  * directly write this port: Top derives binding from real Guard/RawPrep events. */
class QwenRuntimeChunkClientV9 extends Bundle {
  val committed=Input(new GdnChunkCommittedState)
  val prepBinding=Input(new GdnRuntimeChunkPrepBindingV8)
  val prepDone=Flipped(Decoupled(new GdnRuntimeRawPrepReceiptV8))
  val memory=Vec(5,new GdnRuntimeChunkMemoryClient)
  val scalar=Vec(2,new UnifiedScalarClientV2)
  val vector=Vec(2,new GdnRuntimeChunkVectorClient)
  val fabricFault=Input(Bool());val fabricDrained=Input(Bool())
  val jobFire=Output(Bool());val acceptedJob=Output(new GdnRuntimeChunkCoordinatorJob)
  val doneFire=Output(Valid(new GdnRuntimeChunkCoordinatorResult))
  val routeAccepted=Output(Bool());val route=Output(new GdnRuntimeChunkRouteContext)
  val resetRequired=Output(Bool())
}
object HostRuntimeChunkJobV9 {
  def selected(j:QwenOwnerJob):Bool=j.kind===QwenOwnerKind.GdnRecurrent.U && !j.gdnRecurrentMode &&
    (j.m===16.U || j.m===128.U) // legacy M1 remains recurrent even for old zero-filled mode callers
  // Pure decoded geometry/policy mapping, not authority. Top independently
  // checks retained accepted profile1/3 and producer receipt before leasing.
  def fromOwner(j:QwenOwnerJob,b:GdnRuntimeChunkPrepBindingV8):GdnRuntimeChunkCoordinatorJob={
    val x=WireDefault(0.U.asTypeOf(new GdnRuntimeChunkCoordinatorJob))
    x.context.tag:=j.tag;x.context.tokens:=j.m;x.context.cold:=j.cold
    x.context.expectedGeneration:=j.expectedGeneration
    x.context.input:=j.a;x.context.stateIn:=j.b;x.context.stateOut:=j.gdnStateOut
    x.context.output:=j.dst;x.context.scratch:=j.c
    // Fixed runtime profiles: 16-head historical schedule; 32-head guarded
    // cumsum/finite-gradual schedule. No descriptor-supplied mode override.
    x.context.vectorPolicy:=Mux(j.n===32.U,1.U,0.U)
    x.numeric.cumsum:=Mux(j.n===32.U,1.U,0.U);x.numeric.decay:=Mux(j.n===32.U,1.U,0.U)
    x.layout.keyHeads:=16.U;x.layout.valueHeads:=j.n;x.layout.layoutId:=0.U
    x.layout.layoutVersion:=1.U;x.layout.rowBytes:=j.n*1600.U
    x.prepReductionPolicy:=Mux(j.n===32.U,1.U,0.U);x.prepGatePolicy:=Mux(j.n===32.U,2.U,0.U)
    x.prepBinding:=b;x
  }
}
