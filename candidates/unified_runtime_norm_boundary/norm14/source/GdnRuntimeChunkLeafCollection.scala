// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Stable common-fabric client ordinals. They identify control owners, not
  * additional DDR channels, scalar units, or vector banks. */
object GdnRuntimeChunkClient {
  val State=0; val Load=1; val Derived=2; val Transpose=3; val Execute=4
  val MemoryClients=5; val ScalarClients=2; val VectorClients=2
  val LoadScalar=0; val DerivedScalar=1
  val DerivedVector=0; val ExecuteVector=1
}
class GdnRuntimeChunkMemoryClient extends Bundle {
  val request=Decoupled(new MemoryRequest)
  val response=Flipped(Decoupled(new MemoryResponse))
}
class GdnRuntimeChunkVectorClient extends Bundle {
  val request=Decoupled(new UnifiedVectorRequestV2)
  val result=Flipped(Decoupled(new UnifiedVectorResultV2))
}
/** One shared retained observation of an ACTUAL leaf job.fire. This is not
  * owner-success/admission proof or the parent's txn64 identity. Parent binds
  * it to its retained global context and must sample every routeAccepted pulse.
  * Transpose is one job spanning3/4, represented by phase3 (no vector work).
  */
class GdnRuntimeChunkRouteContext extends Bundle {
  val kind=UInt(3.W) // same static client ordinal as MemoryClients
  val phase=UInt(5.W)
  val head=UInt(5.W)
  val chunk=UInt(1.W)
  val context=new GdnChunkJob
}
class GdnRuntimeChunkLeafCollectionPort extends Bundle {
  val job=Flipped(Decoupled(new GdnRuntimeChunkCoordinatorJob))
  val committed=Input(new GdnChunkCommittedState)
  val prepDone=Flipped(Decoupled(new GdnRuntimeInputPrepResult))
  val memory=Vec(GdnRuntimeChunkClient.MemoryClients,new GdnRuntimeChunkMemoryClient)
  val scalar=Vec(GdnRuntimeChunkClient.ScalarClients,new UnifiedScalarClientV2)
  val vector=Vec(GdnRuntimeChunkClient.VectorClients,new GdnRuntimeChunkVectorClient)
  val fabricFault=Input(Bool())
  val fabricFaultStatus=Input(UInt(8.W))
  val fabricDrained=Input(Bool())
  val done=Decoupled(new GdnRuntimeChunkCoordinatorResult)
  val leafResetRequired=Output(Vec(GdnRuntimeChunkClient.MemoryClients,Bool()))
  // BEGIN READONLY ROUTE PORTS
  val leafJobFire=Output(Vec(GdnRuntimeChunkClient.MemoryClients,Bool()))
  val routeAccepted=Output(Bool()) // one cycle AFTER the actual job.fire
  val route=Output(new GdnRuntimeChunkRouteContext)
  val routeMetadataFault=Output(Bool()) // sticky until coordinated global reset
  // END READONLY ROUTE PORTS
  val resetRequired=Output(Bool())
}

/** Actual phase1..17/64x2 control/data wiring. Exactly one copy of each leaf
  * plus the coordinator; NO Matrix/Vector/Scalar arithmetic instance or new
  * payload bank. All16/32 heads and M16/M128 are runtime fields on one DUT.
  *
  * This is an internal collection, not an executable full-block top. The parent
  * must supply job only from its retained accepted profile; prepDone MUST be
  * the matching actual raw-prep producer, not a constructed host receipt.
  * The one shared resource router owns these fixed client ordinals, leases,
  * global transaction epochs and no-stale/exactly-once responses. No local mux
  * is allowed to infer return ownership from current request.valid. Memory
  * tags are leaf tag32/sequence32 and must be rebound by that router.
  *
  * fabricDrained is actual transport/service quiescence for this collection,
  * NOT inverse of whole-block admission.busy. Fault does not gate/retract any
  * leaf request: real pending operations must drain or be globally isolated.
  * Parent must check resetRequired together with its final publication fence,
  * even after a success result became held. done is staged chunk completion,
  * not Conv-history/residual/root-generation publication. No local recovery,
  * automatic reset or safe cancellation is invented here.
  */
class GdnRuntimeChunkLeafCollection extends Module {
  val io=IO(new GdnRuntimeChunkLeafCollectionPort)
  val coordinator=Module(new GdnRuntimeChunkCoordinator)
  val state=Module(new GdnChunkStateTransferOwner)
  val load=Module(new GdnRuntimeChunkLoadPrepV2Owner)
  val derived=Module(new GdnRuntimeChunkDerivedAndPairV2Owner)
  val transpose=Module(new GdnRuntimeChunkTransposeV2Owner)
  val execute=Module(new GdnRuntimeChunkExecuteOwner)
  coordinator.io.job<>io.job
  coordinator.io.committed:=io.committed
  coordinator.io.prepDone<>io.prepDone
  io.done<>coordinator.io.done
  state.io.job<>coordinator.io.stateJob;coordinator.io.stateDone<>state.io.done
  load.io.job<>coordinator.io.loadJob;coordinator.io.loadDone<>load.io.done
  derived.io.job<>coordinator.io.derivedJob;coordinator.io.derivedDone<>derived.io.done
  transpose.io.job<>coordinator.io.transposeJob;coordinator.io.transposeDone<>transpose.io.done
  execute.io.job<>coordinator.io.executeJob;coordinator.io.executeDone<>execute.io.done
  // Leaves see the actual admission-time committed snapshot. Coordinator sees
  // the live root and poisons on any mutation; it cannot silently rebase work.
  state.io.committed:=coordinator.io.committedSnapshot
  load.io.committed:=coordinator.io.committedSnapshot
  derived.io.committed:=coordinator.io.committedSnapshot
  transpose.io.committed:=coordinator.io.committedSnapshot
  execute.io.committed:=coordinator.io.committedSnapshot
  val requests=Seq(state.io.memory,load.io.memory,derived.io.memory,transpose.io.memory,execute.io.memory)
  val responses=Seq(state.io.response,load.io.response,derived.io.response,transpose.io.response,execute.io.response)
  for(i<-0 until GdnRuntimeChunkClient.MemoryClients){
    io.memory(i).request<>requests(i)
    responses(i)<>io.memory(i).response
  }
  io.scalar(GdnRuntimeChunkClient.LoadScalar)<>load.io.scalar
  io.scalar(GdnRuntimeChunkClient.DerivedScalar)<>derived.io.scalar
  io.vector(GdnRuntimeChunkClient.DerivedVector).request<>derived.io.vectorRequest
  derived.io.vectorResult<>io.vector(GdnRuntimeChunkClient.DerivedVector).result
  io.vector(GdnRuntimeChunkClient.ExecuteVector).request<>execute.io.vectorRequest
  execute.io.vectorResult<>io.vector(GdnRuntimeChunkClient.ExecuteVector).result
  io.leafResetRequired:=VecInit(Seq(state.io.resetRequired,load.io.resetRequired,derived.io.resetRequired,
    transpose.io.resetRequired,execute.io.resetRequired))
  val leafPoison=io.leafResetRequired.asUInt.orR
  coordinator.io.fabricFault:=io.fabricFault || leafPoison
  // Preserve parent fault code; a leaf's sticky sideband without a parent code
  // is a protocol quarantine request, not a fabricated leaf completion.
  coordinator.io.fabricFaultStatus:=Mux(io.fabricFault,io.fabricFaultStatus,Status.Protocol.U)
  coordinator.io.fabricDrained:=io.fabricDrained
  io.resetRequired:=coordinator.io.resetRequired || leafPoison || io.fabricFault
  // BEGIN READONLY ROUTE CAPTURE
  // One shared402-bit GdnChunkJob+14bits identity,not five copies or a table.
  // Two more bits retain one-cycle accepted pulse and sticky metadata fault.
  // This observer never gates valid/ready, changes payloads, or retires debt.
  val fires=VecInit(Seq(state.io.job.fire,load.io.job.fire,derived.io.job.fire,
    transpose.io.job.fire,execute.io.job.fire))
  io.leafJobFire:=fires
  val observed=Reg(new GdnRuntimeChunkRouteContext)
  val acceptedPulse=RegNext(fires.asUInt.orR,false.B)
  val metadataFault=RegInit(false.B)
  io.route:=observed;io.routeAccepted:=acceptedPulse
  io.routeMetadataFault:=metadataFault
  def captureRoute(kind:Int,phase:UInt,head:UInt,chunk:UInt,context:GdnChunkJob):Unit={
    observed.kind:=kind.U;observed.phase:=phase;observed.head:=head(4,0)
    observed.chunk:=chunk;observed.context:=context
  }
  def basicMetadataBad(context:GdnChunkJob,heads:UInt,head:UInt,chunk:UInt):Bool={
    val chunks=Mux(context.tokens===128.U,2.U,1.U)
    (context.tokens=/=16.U && context.tokens=/=128.U) ||
      (heads=/=16.U && heads=/=32.U) || head>=heads || chunk>=chunks
  }
  val sj=state.io.job.bits
  val stateChunk=Mux(sj.operation===1.U && sj.context.tokens===128.U,1.U(1.W),0.U(1.W))
  val stateBad=sj.operation>1.U || sj.head(15,5).orR ||
    basicMetadataBad(sj.context,sj.activeHeads,sj.head,stateChunk)
  val lj=load.io.job.bits
  val loadBad=lj.keyHeads=/=16.U || basicMetadataBad(lj.context,lj.valueHeads,lj.head,lj.chunk)
  val dj=derived.io.job.bits
  val derivedBad= !GdnRuntimeChunkLayout.admitted(dj.layout) || basicMetadataBad(dj.context,dj.layout.valueHeads,dj.head,dj.chunk)
  val tj=transpose.io.job.bits
  val transposeBad= !GdnRuntimeChunkLayout.admitted(tj.layout) || basicMetadataBad(tj.context,tj.layout.valueHeads,tj.head,tj.chunk)
  val ej=execute.io.job.bits
  val executeBad=ej.phase<5.U || ej.phase>17.U || !GdnRuntimeChunkLayout.admitted(ej.layout) ||
    basicMetadataBad(ej.context,ej.layout.valueHeads,ej.head,ej.chunk)
  when(fires.asUInt.orR){
    when(PopCount(fires)=/=1.U || (fires(0) && stateBad) || (fires(1) && loadBad) ||
      (fires(2) && derivedBad) || (fires(3) && transposeBad) || (fires(4) && executeBad)){
      metadataFault:=true.B
    }
    // Priority chooses one real source if a bug makes multiple fires. The
    // simultaneous sticky fault makes that observation ineligible for a lease.
    when(fires(0)){captureRoute(GdnRuntimeChunkClient.State,Mux(sj.operation===1.U,18.U,0.U),sj.head,stateChunk,sj.context)}
      .elsewhen(fires(1)){captureRoute(GdnRuntimeChunkClient.Load,1.U,lj.head,lj.chunk,lj.context)}
      .elsewhen(fires(2)){captureRoute(GdnRuntimeChunkClient.Derived,2.U,dj.head,dj.chunk,dj.context)}
      .elsewhen(fires(3)){captureRoute(GdnRuntimeChunkClient.Transpose,3.U,tj.head,tj.chunk,tj.context)}
      .elsewhen(fires(4)){captureRoute(GdnRuntimeChunkClient.Execute,ej.phase,ej.head,ej.chunk,ej.context)}
  }
  // END READONLY ROUTE CAPTURE
}
