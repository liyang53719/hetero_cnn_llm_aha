package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Protocol boundary fixture, NOT a Core/whole-block substitute. Both production
  * helper bodies and the actual Adapter/32-bank are instantiated. Guard/owner
  * offers are controlled test inputs. Scalar responses come from the real
  * BlockScalarFloatPolicyV2; its small fixture transport counts actual fires,
  * and does not qualify the omitted Core scheduler/SRAM/numerical recipe. */
class Rms32FaultFeedbackFixture extends Module {
  val io=IO(new Bundle {
    val authority=Input(new HostRuntimeAuthoritySnapshotV4)
    val logical=Input(Valid(new QwenOwnerJob));val physical=Input(Valid(new QwenOwnerJob))
    val terminal=Input(Valid(new QwenOwnerResult));val terminalReady=Input(Bool())
    val runtimeTerminal=Input(Valid(new GdnRuntimeRmsNormResultV16))
    val p0Request=Flipped(Decoupled(new UnifiedVectorElement32PayloadV4))
    val p0Result=Decoupled(new UnifiedVectorElement32ResultPayloadV4)
    val runtimeRequest=Flipped(Decoupled(new UnifiedVectorElement32PayloadV4))
    val runtimeResult=Decoupled(new UnifiedVectorElement32ResultPayloadV4)
    val scalarRequest=Flipped(Decoupled(new UnifiedScalarRequestV2))
    val scalarResult=Decoupled(new UnifiedScalarResultV2)
    val coreDrained=Input(Bool());val coreReset=Input(Bool());val runtimeDrained=Input(Bool())
    val independentFault=Input(Bool());val injectConflict=Input(Bool());val injectWrongScalarTag=Input(Bool())
    val status=Output(Vec(12,new UnifiedMoeArithmeticClientStatusV5))
    val p0Fault=Output(Bool());val prefixFault=Output(Bool());val adapterFault=Output(Bool())
    val actualPublished=Output(Bool());val allDrained=Output(Bool())
  })
  val a=Module(new UnifiedMoeSharedArithmeticAdapterV5)
  // Same-cycle adapter -> authority fault feedback exists in actual Top.
  // No test-controlled low tie-off or register is inserted in this path.
  val internalAuthority=WireDefault(io.authority)
  internalAuthority.currentFault:=io.authority.currentFault || a.io.resetRequired
  a.io.externalPoison:=false.B // independent publication fault tested separately
  for(i<-0 until 12){a.io.acquire(i).valid:=false.B;a.io.acquire(i).bits:=0.U.asTypeOf(a.io.acquire(i).bits);a.io.retire(i).valid:=false.B;a.io.retire(i).bits:=0.U.asTypeOf(a.io.retire(i).bits)}
  for(i<-0 until 4){a.io.scalar(i).request.valid:=false.B;a.io.scalar(i).request.bits:=0.U.asTypeOf(a.io.scalar(i).request.bits);a.io.scalar(i).result.ready:=false.B;a.io.formatRequest(i).valid:=false.B;a.io.formatRequest(i).bits:=0.U.asTypeOf(a.io.formatRequest(i).bits);a.io.formatResult(i).ready:=false.B}
  for(i<-0 until 2){a.io.vectorRequest(i).valid:=false.B;a.io.vectorRequest(i).bits:=0.U.asTypeOf(a.io.vectorRequest(i).bits);a.io.vectorResult(i).ready:=false.B}
  a.io.ordinaryVectorRequest.valid:=false.B;a.io.ordinaryVectorRequest.bits:=0.U.asTypeOf(a.io.ordinaryVectorRequest.bits);a.io.ordinaryVectorResult.ready:=false.B
  val scalar=Module(new BlockScalarFloatPolicyV2)
  val offer=Reg(new QwenSharedScalarRequestV3);val held=RegInit(false.B);val pending=RegInit(false.B)
  val ca=RegInit(0.U(33.W));val ci=RegInit(0.U(33.W));val cr=RegInit(0.U(33.W))
  val port=a.io.coreScalar
  port.request.ready:= !held && !pending && !scalar.io.result.valid
  when(port.request.fire){offer:=port.request.bits;held:=true.B;ca:=ca+1.U}
  scalar.io.request.valid:=held;scalar.io.request.bits:=offer.payload
  when(scalar.io.request.fire){held:=false.B;pending:=true.B;ci:=ci+1.U}
  port.result.valid:=pending && scalar.io.result.valid;port.result.bits.identity:=offer.identity;port.result.bits.payload:=scalar.io.result.bits
  port.result.bits.identity.serial:=Mux(io.injectWrongScalarTag,offer.identity.serial+1.U,offer.identity.serial)
  scalar.io.result.ready:=pending && port.result.ready
  when(port.result.fire){pending:=false.B;cr:=cr+1.U}
  port.status.counts.accepted:=ca;port.status.counts.issued:=ci;port.status.counts.returned:=cr
  port.status.heldRequest:=held;port.status.pending:=pending;port.status.heldResult:=pending && scalar.io.result.valid
  port.status.resourcesDrained:= !held && !pending && !scalar.io.result.valid && ca===ci && ci===cr
  port.status.resetRequired:=false.B
  val job=Wire(Decoupled(new QwenOwnerJob));job.valid:=io.logical.valid;job.bits:=io.logical.bits;job.ready:=true.B
  val physical=Wire(Decoupled(new QwenOwnerJob));physical.valid:=io.physical.valid;physical.bits:=io.physical.bits;physical.ready:=true.B
  val done=Wire(Decoupled(new QwenOwnerResult));done.valid:=io.terminal.valid;done.bits:=io.terminal.bits;done.ready:=io.terminalReady
  val g=Rms32PortRefsV1.Guard(Rms32PortRefsV1.GuardIO(job,physical,done,false.B,io.authority.transaction,false.B))
  val runtime=Wire(new QwenRuntimeRmsClientV6)
  runtime.scalar.request<>io.scalarRequest;io.scalarResult<>runtime.scalar.result
  runtime.vectorRequest<>io.runtimeRequest;io.runtimeResult<>runtime.vectorResult
  runtime.formatRequest.valid:=false.B;runtime.formatRequest.bits:=0.U.asTypeOf(runtime.formatRequest.bits)
  runtime.formatResult.ready:=true.B;runtime.parentFault:=io.independentFault;runtime.resourcesDrained:=io.runtimeDrained
  def absent[T<:Data](gen:T):ValidIO[T]={val v=Wire(Valid(gen));v.valid:=false.B;v.bits:=0.U.asTypeOf(gen);v}
  val prep=Wire(Decoupled(new GdnRuntimeRawPrepReadyV7));prep.valid:=false.B;prep.bits:=0.U.asTypeOf(prep.bits)
  val published=Wire(Bool())
  val k=Rms32PortRefsV1.Owner(Rms32PortRefsV1.OwnerIO(Some(io.p0Request),Some(io.p0Result),Some(io.coreDrained),Some(io.coreReset),Some(published),Some(runtime),Some(io.runtimeTerminal),
    Some(absent(new GdnRuntimeElementwiseResultV15)),Some(absent(new Bf16CausalGqaRuntimeResultV14)),Some(absent(new Bf16KvAppendRuntimeResultV13)),Some(absent(new PartialRopeRuntimeResultV12)),Some(absent(new QkNormRuntimeResultV11)),Some(absent(new GdnRuntimeGatedNormResultV10)),Some(prep),Some(absent(new GdnRuntimeRawPrepResultV7))))
  val prefixScalar=Wire(new UnifiedScalarClientV2);a.io.scalar(3)<>prefixScalar
  val prefix=HostRuntimePrefixLeaseWiringV8.connectPorts(Rms32PortRefsV1.arithmetic(a),g,internalAuthority,k,io.independentFault,prefixScalar,absent(new GdnRuntimeChunkStagedReceiptV10))
  a.io.acquire(8):=prefix.scalarAcquire;a.io.retire(8):=prefix.scalarRetire
  // Explicit malformed boundary injection, not a passing authority substitute.
  // Other prefix signals remain the actual production helper outputs.
  val forwarded=Wire(new HostRuntimePrefixLeaseWiringV8.View)
  for((name,value)<-forwarded.elements if name!="vectorRequest" && name!="vectorResult"){value:=prefix.elements(name)}
  forwarded.vectorRequest.valid:=prefix.vectorRequest.valid;forwarded.vectorRequest.bits:=prefix.vectorRequest.bits
  forwarded.vectorResult.ready:=prefix.vectorResult.ready
  forwarded.vectorAcquire.valid:=prefix.vectorAcquire.valid || io.injectConflict
  forwarded.vectorAcquire.bits:=prefix.vectorAcquire.bits
  prefix.vectorRequest.ready:=forwarded.vectorRequest.ready
  prefix.vectorResult.valid:=forwarded.vectorResult.valid;prefix.vectorResult.bits:=forwarded.vectorResult.bits
  val p0=HostOrderedRms32WiringV1.connectPorts(Rms32PortRefsV1.arithmetic(a),g,internalAuthority,k,forwarded,io.independentFault,true)
  io.status:=a.io.status;io.p0Fault:=p0.localFault;io.prefixFault:=prefix.localFault;io.adapterFault:=a.io.resetRequired
  io.actualPublished:=published;io.allDrained:=p0.resourcesDrained && prefix.resourcesDrained && a.io.resourcesDrained
}
