// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.HeteroFP32Alu

object UnifiedResourceKind { val Matrix=0; val Vector=1; val Scalar=2; val StateTransfer=3 }
class UnifiedFabricLease extends Bundle {
  val context = new UnifiedBlockDispatchV1
  val resource = UInt(2.W)
}
class UnifiedFabricDone extends Bundle {
  val transactionId=UInt(64.W); val profileId=UInt(3.W); val tag=UInt(32.W)
  val status=UInt(8.W); val drained=Bool(); val resetRequired=Bool()
  val acknowledgedWriteBytes=UInt(64.W); val issuedSliceSteps=UInt(64.W)
}
class UnifiedVectorRequest extends Bundle {
  val multiply=Bool(); val a=Vec(16,UInt(32.W)); val b=Vec(16,UInt(32.W))
}
class UnifiedVectorResult extends Bundle {
  val value=Vec(16,UInt(32.W)); val flags=Vec(16,UInt(5.W)); val error=Bool()
}
class UnifiedScalarResult extends Bundle {
  val value=UInt(32.W); val flags=UInt(5.W); val primitiveFlagsValid=Bool(); val error=Bool()
}

// Every resource request carries the admission transaction identity. A held
// late request from a previous lease cannot become work for the next profile.
class UnifiedMatrixGroupRequest extends Bundle {val transactionId=UInt(64.W);val payload=new MatrixStreamGroup(false,false)}
class UnifiedMatrixStepRequest extends Bundle {val transactionId=UInt(64.W);val payload=new MatrixStreamStep(0)}
class UnifiedTaggedMatrixResult extends Bundle {val transactionId=UInt(64.W);val payload=new MatrixStreamResult(0)}
class UnifiedTaggedVectorRequest extends Bundle {val transactionId=UInt(64.W);val payload=new UnifiedVectorRequest}
class UnifiedTaggedVectorResult extends Bundle {val transactionId=UInt(64.W);val payload=new UnifiedVectorResult}
class UnifiedTaggedScalarRequest extends Bundle {val transactionId=UInt(64.W);val payload=new ScalarRequest}
class UnifiedTaggedScalarResult extends Bundle {val transactionId=UInt(64.W);val payload=new UnifiedScalarResult}
class UnifiedTaggedStateRequest extends Bundle {val transactionId=UInt(64.W);val payload=new GdnChunkStateTransferJob}

/** Exactly sixteen original FP32 ALUs, not one vector per profile. One held
  * result; no profile-sized buffer and no new FMA or host arithmetic callback.
  * This first primitive mode conservatively retains fatal-underflow policy.
  * It is NOT the proposed general gradual-underflow vector policy for GDN.
  */
class UnifiedVectorBank extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new UnifiedVectorRequest))
    val result=Decoupled(new UnifiedVectorResult)
  })
  val full=RegInit(false.B);val out=Reg(new UnifiedVectorResult)
  val alus=Seq.fill(16)(Module(new HeteroFP32Alu))
  for(i<-0 until 16){alus(i).io.op:=io.request.bits.multiply;alus(i).io.x:=io.request.bits.a(i);alus(i).io.y:=io.request.bits.b(i)}
  io.request.ready:= !full;io.result.valid:=full;io.result.bits:=out
  when(io.request.fire){
    out.value:=VecInit(alus.map(_.io.out));out.flags:=VecInit(alus.map(_.io.exceptionFlags))
    out.error:=alus.map(a=>a.io.exceptionFlags(4,1).orR || !TensorMath.finite(a.io.out)).reduce(_||_)
    full:=true.B
  }
  when(io.result.fire){full:=false.B}
}

/** Genuine fixed physical backbone. Single lease covers command, result and
  * terminal drain. No resource is an unconnected/dontTouch placeholder:
  * Matrix cmd/step/result/done, vector and scalar request/result, and the real
  * private state transfer/DDR request-response are wired end to end.
  *
  * This INTERNAL scheduler interface is not the public Host tensor ABI. It
  * accepts one Matrix group or one vector/scalar/state operation per lease.
  * Arbitrary full GDN/MoE/block scheduling is not implemented here.
  */
class UnifiedPhysicalFabric extends Module {
  val io=IO(new Bundle {
    val lease=Flipped(Decoupled(new UnifiedFabricLease));val done=Decoupled(new UnifiedFabricDone)
    val matrixGroup=Flipped(Decoupled(new UnifiedMatrixGroupRequest))
    val matrixStep=Flipped(Decoupled(new UnifiedMatrixStepRequest))
    val matrixResult=Decoupled(new UnifiedTaggedMatrixResult)
    val vectorRequest=Flipped(Decoupled(new UnifiedTaggedVectorRequest));val vectorResult=Decoupled(new UnifiedTaggedVectorResult)
    val scalarRequest=Flipped(Decoupled(new UnifiedTaggedScalarRequest));val scalarResult=Decoupled(new UnifiedTaggedScalarResult)
    val stateJob=Flipped(Decoupled(new UnifiedTaggedStateRequest))
    val committed=Input(new GdnChunkCommittedState)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
  })
  // These four constructors are fixed across all five runtime profiles.
  val matrix=Module(new MatrixPipelineService()) // original eight512 endpoints
  val vector=Module(new UnifiedVectorBank) // one16-lane bank
  val scalar=Module(new BlockScalarFloat(enableSoftplus=true)) // one shared scalar
  val stateOwner=Module(new GdnChunkStateTransferOwner) // fixed32 capacity, one64B payload
  val idle::active::finishing::locked::Nil=Enum(4)
  val state=RegInit(idle);val lease=Reg(new UnifiedFabricLease)
  val committed=Reg(new GdnChunkCommittedState);val issued=RegInit(false.B)
  val receipt=Reg(new UnifiedFabricDone);val poison=RegInit(false.B);val baseSteps=Reg(UInt(64.W))
  val (decoded,known)=UnifiedRuntimeProfile.decode(io.lease.bits.context.launch.profileId)
  val leaseMatches=known && decoded.asUInt===io.lease.bits.context.profile.asUInt
  val stateProfileOk=io.lease.bits.resource=/=UnifiedResourceKind.StateTransfer.U || decoded.mixer===1.U
  io.lease.ready:=state===idle && !poison && !matrix.io.resetRequired && !stateOwner.io.resetRequired
  io.done.valid:=state===finishing;io.done.bits:=receipt
  io.resetRequired:=poison||matrix.io.resetRequired||stateOwner.io.resetRequired
  when(io.lease.fire){
    lease:=io.lease.bits;committed:=io.committed;issued:=false.B;baseSteps:=matrix.io.acceptedSteps
    receipt:=0.U.asTypeOf(new UnifiedFabricDone)
    receipt.transactionId:=io.lease.bits.context.transactionId
    receipt.profileId:=io.lease.bits.context.profile.profileId
    receipt.tag:=io.lease.bits.context.launch.tag
    receipt.drained:=false.B
    when(leaseMatches && stateProfileOk){state:=active}
      .otherwise{receipt.status:="h81".U;receipt.drained:=true.B;state:=finishing}
  }
  val matrixSelected=state===active && lease.resource===UnifiedResourceKind.Matrix.U
  val vectorSelected=state===active && lease.resource===UnifiedResourceKind.Vector.U
  val scalarSelected=state===active && lease.resource===UnifiedResourceKind.Scalar.U
  val stateSelected=state===active && lease.resource===UnifiedResourceKind.StateTransfer.U

  val matrixGroupIdentity=io.matrixGroup.bits.transactionId===lease.context.transactionId
  val matrixStepIdentity=io.matrixStep.bits.transactionId===lease.context.transactionId
  val vectorIdentity=io.vectorRequest.bits.transactionId===lease.context.transactionId
  val scalarIdentity=io.scalarRequest.bits.transactionId===lease.context.transactionId
  val stateIdentity=io.stateJob.bits.transactionId===lease.context.transactionId

  matrix.io.port.group.valid:=matrixSelected && !issued && matrixGroupIdentity && io.matrixGroup.valid
  matrix.io.port.group.bits:=io.matrixGroup.bits.payload
  // The accepted lease, not a caller's changing tag, owns the completion.
  matrix.io.port.group.bits.tag:=lease.context.launch.tag
  io.matrixGroup.ready:=matrixGroupIdentity && matrixSelected && !issued && matrix.io.port.group.ready
  when(matrix.io.port.group.fire){issued:=true.B}
  matrix.io.port.step.valid:=matrixSelected && issued && matrixStepIdentity && io.matrixStep.valid
  matrix.io.port.step.bits:=io.matrixStep.bits.payload
  io.matrixStep.ready:=matrixStepIdentity && matrixSelected && issued && matrix.io.port.step.ready
  io.matrixResult.valid:=matrixSelected && matrix.io.port.result.valid
  io.matrixResult.bits.transactionId:=lease.context.transactionId
  io.matrixResult.bits.payload:=matrix.io.port.result.bits
  matrix.io.port.result.ready:=matrixSelected && io.matrixResult.ready
  matrix.io.port.abort:=false.B // no unsafe host clear/abort port in this increment
  matrix.io.port.done.ready:=matrixSelected && issued
  when(matrix.io.port.done.fire){
    val bad=matrix.io.port.done.bits.error || matrix.io.port.done.bits.tag=/=lease.context.launch.tag
    receipt.status:=Mux(bad,2.U,0.U);receipt.resetRequired:=bad||matrix.io.resetRequired
    // A poisoned child may only drain accepted metadata, not all endpoint command
    // completions. Never convert that into a reusable/global-drained success.
    receipt.drained:= !bad && !matrix.io.resetRequired
    receipt.issuedSliceSteps:=matrix.io.acceptedSteps-baseSteps
    when(bad||matrix.io.resetRequired){poison:=true.B};state:=finishing
  }

  vector.io.request.valid:=vectorSelected && !issued && vectorIdentity && io.vectorRequest.valid
  vector.io.request.bits:=io.vectorRequest.bits.payload
  io.vectorRequest.ready:=vectorIdentity && vectorSelected && !issued && vector.io.request.ready
  when(vector.io.request.fire){issued:=true.B}
  io.vectorResult.valid:=vectorSelected && issued && vector.io.result.valid
  io.vectorResult.bits.transactionId:=lease.context.transactionId
  io.vectorResult.bits.payload:=vector.io.result.bits;vector.io.result.ready:=vectorSelected && issued && io.vectorResult.ready
  when(vector.io.result.fire){receipt.drained:=true.B;receipt.status:=Mux(vector.io.result.bits.error,2.U,0.U);state:=finishing}

  scalar.io.request.valid:=scalarSelected && !issued && scalarIdentity && io.scalarRequest.valid
  scalar.io.request.bits:=io.scalarRequest.bits.payload
  io.scalarRequest.ready:=scalarIdentity && scalarSelected && !issued && scalar.io.request.ready
  when(scalar.io.request.fire){issued:=true.B}
  io.scalarResult.valid:=scalarSelected && issued && scalar.io.result.valid
  io.scalarResult.bits.transactionId:=lease.context.transactionId
  io.scalarResult.bits.payload.value:=scalar.io.result.bits;io.scalarResult.bits.payload.flags:=scalar.io.primitiveFlags
  io.scalarResult.bits.payload.primitiveFlagsValid:=scalar.io.primitiveFlagsValid;io.scalarResult.bits.payload.error:=scalar.io.error
  scalar.io.result.ready:=scalarSelected && issued && io.scalarResult.ready
  when(scalar.io.result.fire){receipt.drained:=true.B;receipt.status:=Mux(scalar.io.error,2.U,0.U);state:=finishing}

  stateOwner.io.job.valid:=stateSelected && !issued && stateIdentity && io.stateJob.valid
  stateOwner.io.job.bits:=io.stateJob.bits.payload
  stateOwner.io.job.bits.activeHeads:=lease.context.profile.gdnValueHeads
  stateOwner.io.job.bits.context.tag:=lease.context.launch.tag
  stateOwner.io.job.bits.context.tokens:=lease.context.launch.tokens
  stateOwner.io.job.bits.context.expectedGeneration:=lease.context.launch.expectedGeneration
  stateOwner.io.job.bits.context.cold:=lease.context.launch.cold
  stateOwner.io.job.bits.context.input:=lease.context.launch.input
  stateOwner.io.job.bits.context.output:=lease.context.launch.output
  stateOwner.io.job.bits.context.scratch:=lease.context.launch.scratch
  stateOwner.io.job.bits.context.stateIn:=lease.context.launch.stateIn
  stateOwner.io.job.bits.context.stateOut:=lease.context.launch.stateOut
  stateOwner.io.committed:=committed
  io.stateJob.ready:=stateIdentity && stateSelected && !issued && stateOwner.io.job.ready
  when(stateOwner.io.job.fire){issued:=true.B}
  io.memory.valid:=stateSelected && stateOwner.io.memory.valid;io.memory.bits:=stateOwner.io.memory.bits
  stateOwner.io.memory.ready:=stateSelected && io.memory.ready
  stateOwner.io.response.valid:=stateSelected && io.response.valid;stateOwner.io.response.bits:=io.response.bits
  io.response.ready:=stateSelected && stateOwner.io.response.ready
  stateOwner.io.done.ready:=stateSelected && issued
  when(stateOwner.io.done.fire){
    val d=stateOwner.io.done.bits
    val bad=d.tag=/=lease.context.launch.tag || d.expectedGeneration=/=lease.context.launch.expectedGeneration || !d.localDrained
    receipt.status:=Mux(bad,2.U,d.status)
    receipt.acknowledgedWriteBytes:=Mux(bad,0.U,d.writeBytes);receipt.drained:= !bad && d.localDrained
    receipt.resetRequired:=bad||d.status=/=0.U||stateOwner.io.resetRequired
    when(bad||d.status=/=0.U||stateOwner.io.resetRequired){poison:=true.B};state:=finishing
  }
  when(io.done.fire){state:=Mux(poison||io.resetRequired,locked,idle)}
}
