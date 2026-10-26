// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Actual controller RTL tests, NOT the physical4096 Matrix or vector arithmetic.
  * Physical replies/counter and private producer-fence packets are controlled
  * test inputs. They verify ownership/credit logic, not producer provenance.
  * The real order->bridge->fence connection needs its separate integration test.
  */
class UnifiedMatrixVectorLeasePortsV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  private def zero(x:Data):Unit=x match {
    case b:Bool=>b.poke(false.B)
    case u:UInt=>u.poke(0.U)
    case v:Vec[_]=>v.getElements.foreach(zero)
    case r:Record=>r.elements.values.foreach(zero)
    case _=>throw new IllegalArgumentException("unsupported test input "+x.getClass)
  }
  private def snap(x:Data):Seq[BigInt]=x match {
    case b:Bool=>Seq(b.peek().litValue)
    case u:UInt=>Seq(u.peek().litValue)
    case v:Vec[_]=>v.getElements.toSeq.flatMap(snap)
    case r:Record=>r.elements.values.toSeq.flatMap(snap)
    case _=>throw new IllegalArgumentException("unsupported snapshot")
  }
  private def init(d:UnifiedMatrixVectorLeasePortsV2):Unit={
    Seq(d.io.begin.bits,d.io.end.bits,d.io.matrixLease.bits,d.io.vectorLease.bits,
      d.io.matrixGroup.bits,d.io.matrixStep.bits,d.io.vectorRequest.bits,
      d.io.vectorRelease.bits,d.io.producerFence.bits,d.io.ownerFault.bits,
      d.io.physicalMatrix.result.bits,d.io.physicalMatrix.done.bits,
      d.io.physicalVectorResult.bits).foreach(zero)
    Seq(d.io.begin.valid,d.io.end.valid,d.io.matrixLease.valid,d.io.vectorLease.valid,
      d.io.matrixGroup.valid,d.io.matrixStep.valid,d.io.vectorRequest.valid,
      d.io.vectorRelease.valid,d.io.producerFence.valid,d.io.ownerFault.valid,
      d.io.physicalMatrix.result.valid,d.io.physicalMatrix.done.valid,
      d.io.physicalVectorResult.valid,d.io.physicalMatrixResetRequired,
      d.io.physicalMatrix.group.ready,d.io.physicalMatrix.step.ready,
      d.io.physicalVectorRequest.ready,d.io.matrixDone.ready,d.io.vectorDone.ready).foreach(_.poke(false.B))
    d.io.matrixResult.ready.poke(true.B);d.io.vectorResult.ready.poke(true.B)
    d.io.physicalMatrixAcceptedSteps.poke(0.U)
  }
  // Test-only isolation: ALL mocked physical offers/returns are removed before
  // reset. This is not evidence that resetting this controller isolates DDR.
  private def isolateReset(d:UnifiedMatrixVectorLeasePortsV2):Unit={
    init(d);d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
    d.io.active.expect(false.B);d.io.resetRequired.expect(false.B)
  }
  private def begin(d:UnifiedMatrixVectorLeasePortsV2,txn:Int=100,pid:Int=3):Unit={
    zero(d.io.begin.bits);d.io.begin.bits.transactionId.poke(txn.U)
    val l=d.io.begin.bits.launch;l.version.poke(1.U);l.profileId.poke(pid.U);l.tokens.poke(128.U);l.cold.poke(true.B)
    if(pid==4)l.cacheCapacity.poke(256.U)
    val p=d.io.begin.bits.profile
    p.profileId.poke(pid.U);p.hidden.poke(2048.U);p.mlp.poke(1.U)
    p.expertCount.poke(256.U);p.expertsPerToken.poke(8.U);p.expertFfn.poke(512.U);p.sharedFfn.poke(512.U);p.maxPosition.poke(262144.U)
    if(pid==3){p.mixer.poke(1.U);p.gdnKeyHeads.poke(16.U);p.gdnValueHeads.poke(32.U);p.gdnKeyDim.poke(128.U);p.gdnValueDim.poke(128.U);p.convKernel.poke(4.U)}
    else {require(pid==4);p.attentionHeads.poke(16.U);p.kvHeads.poke(2.U);p.headDim.poke(256.U);p.rotaryDim.poke(64.U)}
    d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(true.B);d.clock.step();d.io.begin.valid.poke(false.B)
    d.io.active.expect(true.B);d.io.resetRequired.expect(false.B)
  }
  private def lease(l:UnifiedOverlapLeaseV2,txn:Int,vector:Boolean,seq:Int=0):Unit={
    zero(l);l.transactionId.poke(txn.U);l.ownerSequence.poke(seq.U)
    l.stage.poke((if(vector)2 else 1).U);l.expectedOperations.poke((if(vector)36 else 0).U)
  }
  private def acquire(d:UnifiedMatrixVectorLeasePortsV2,txn:Int=100,matrix:Boolean=false):Unit={
    lease(d.io.vectorLease.bits,txn,true);d.io.vectorLease.valid.poke(true.B)
    if(matrix){lease(d.io.matrixLease.bits,txn,false);d.io.matrixLease.valid.poke(true.B);d.io.matrixLease.ready.expect(true.B)}
    d.io.vectorLease.ready.expect(true.B);d.clock.step();d.io.vectorLease.valid.poke(false.B);d.io.matrixLease.valid.poke(false.B)
    d.io.allResourcesDrained.expect(false.B)
  }
  private def request(d:UnifiedMatrixVectorLeasePortsV2,serial:Int,txn:Int=100):Unit={
    val t=d.io.vectorRequest.bits.identity;zero(t);t.transactionId.poke(txn.U);t.resource.poke(1.U);t.stage.poke(2.U);t.serial.poke(serial.U)
    val p=d.io.vectorRequest.bits.payload;p.policy.poke(1.U);p.multiply.poke(true.B)
    for(i<-0 until 16){p.a(i).poke((BigInt("3f800000",16)+serial*32+i).U);p.b(i).poke(BigInt("3f800000",16).U)}
  }
  private def issue(d:UnifiedMatrixVectorLeasePortsV2,serial:Int,txn:Int=100,stalls:Int=0):Unit={
    request(d,serial,txn);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRequest.ready.expect(true.B)
    d.io.physicalVectorRequest.ready.poke(false.B);d.clock.step();d.io.vectorRequest.valid.poke(false.B)
    d.io.physicalVectorRequest.valid.expect(true.B);val held=snap(d.io.physicalVectorRequest.bits)
    for(_<-0 until stalls){d.clock.step();assert(snap(d.io.physicalVectorRequest.bits)==held);d.io.physicalVectorRequest.valid.expect(true.B)}
    d.io.physicalVectorRequest.ready.poke(true.B);d.clock.step();d.io.physicalVectorRequest.ready.poke(false.B)
    d.io.physicalVectorRequest.valid.expect(false.B)
  }
  private def response(d:UnifiedMatrixVectorLeasePortsV2,serial:Int,txn:Int=100,error:Boolean=false,stalls:Int=0):Unit={
    d.io.physicalVectorResult.bits.policy.poke(1.U);d.io.physicalVectorResult.bits.error.poke(error.B)
    for(i<-0 until 16){d.io.physicalVectorResult.bits.value(i).poke((serial*32+i).U);d.io.physicalVectorResult.bits.flags(i).poke(0.U)}
    d.io.physicalVectorResult.valid.poke(true.B);d.io.vectorResult.ready.poke(false.B)
    d.io.vectorResult.valid.expect(true.B);d.io.vectorResult.bits.identity.transactionId.expect(txn.U);d.io.vectorResult.bits.identity.serial.expect(serial.U)
    val held=snap(d.io.vectorResult.bits)
    for(_<-0 until stalls){d.io.physicalVectorResult.ready.expect(false.B);d.clock.step();assert(snap(d.io.vectorResult.bits)==held)}
    d.io.vectorResult.ready.poke(true.B);d.io.physicalVectorResult.ready.expect(true.B);d.clock.step();d.io.physicalVectorResult.valid.poke(false.B)
  }
  private def fence(d:UnifiedMatrixVectorLeasePortsV2,txn:Int=100,status:Int=0):Unit={
    lease(d.io.producerFence.bits.lease,txn,true);d.io.producerFence.bits.status.poke(status.U);d.io.producerFence.bits.drained.poke(true.B)
    d.io.producerFence.valid.poke(true.B);d.io.producerFence.ready.expect(true.B);d.clock.step();d.io.producerFence.valid.poke(false.B)
  }
  private def releaseBits(d:UnifiedMatrixVectorLeasePortsV2,count:Int,txn:Int=100,status:Int=0):Unit={
    lease(d.io.vectorRelease.bits.lease,txn,true);d.io.vectorRelease.bits.issued.poke(count.U);d.io.vectorRelease.bits.returned.poke(count.U);d.io.vectorRelease.bits.diagnosticStatus.poke(status.U)
  }
  private def finishVector(d:UnifiedMatrixVectorLeasePortsV2,count:Int,txn:Int=100,bad:Boolean=false):Unit={
    releaseBits(d,count,txn,if(bad)2 else 0);d.io.vectorRelease.valid.poke(true.B);d.io.vectorRelease.ready.expect(true.B)
    d.clock.step();d.io.vectorRelease.valid.poke(false.B);d.io.vectorDone.valid.expect(true.B)
    d.io.vectorDone.bits.issued.expect(count.U);d.io.vectorDone.bits.returned.expect(count.U);d.io.vectorDone.bits.operationCountsValid.expect(true.B)
    d.io.vectorDone.bits.drained.expect(true.B);d.io.vectorDone.bits.resetRequired.expect(bad.B);d.io.vectorDone.bits.status.expect((if(bad)2 else 0).U)
    val held=snap(d.io.vectorDone.bits);d.clock.step(3);assert(snap(d.io.vectorDone.bits)==held)
    d.io.vectorDone.ready.poke(true.B);d.clock.step();d.io.vectorDone.ready.poke(false.B)
  }
  private def group(d:UnifiedMatrixVectorLeasePortsV2):Unit={
    d.io.matrixGroup.bits.opcode.poke(32.U);d.io.matrixGroup.bits.sliceMask.poke(255.U);d.io.matrixGroup.bits.tag.poke(99.U)
    d.io.matrixGroup.valid.poke(true.B);d.io.matrixGroup.ready.expect(true.B);d.clock.step();d.io.matrixGroup.valid.poke(false.B)
    d.io.physicalMatrix.group.valid.expect(true.B);d.io.physicalMatrix.group.bits.tag.expect(0.U)
    d.io.physicalMatrix.group.ready.poke(true.B);d.clock.step();d.io.physicalMatrix.group.ready.poke(false.B)
  }
  private def matrixDone(d:UnifiedMatrixVectorLeasePortsV2,bad:Boolean=false):Unit={
    d.io.physicalMatrix.done.bits.tag.poke(0.U);d.io.physicalMatrix.done.bits.error.poke(bad.B)
    d.io.physicalMatrix.done.valid.poke(true.B);d.io.physicalMatrix.done.ready.expect(true.B);d.clock.step();d.io.physicalMatrix.done.valid.poke(false.B)
  }
  behavior of "UnifiedMatrixVectorLeasePortsV2 actual control RTL"
  it should "own both resources concurrently and close36 credits on two runtime profiles without reset" in {
    test(new UnifiedMatrixVectorLeasePortsV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((pid,txn)<-Seq((3,100),(4,101))){
        begin(d,txn,pid);acquire(d,txn,matrix=true);group(d)
        d.io.matrixStep.bits.a(0).poke(17.U);d.io.matrixStep.valid.poke(true.B);d.io.matrixStep.ready.expect(true.B);d.clock.step();d.io.matrixStep.valid.poke(false.B)
        d.io.physicalMatrix.step.valid.expect(true.B);val held=snap(d.io.physicalMatrix.step.bits);d.clock.step(2);assert(snap(d.io.physicalMatrix.step.bits)==held)
        // Real simultaneous controller output offers, no throughput inference.
        request(d,0,txn);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRequest.ready.expect(true.B);d.clock.step();d.io.vectorRequest.valid.poke(false.B)
        d.io.physicalMatrix.step.ready.poke(true.B);d.io.physicalVectorRequest.ready.poke(true.B)
        d.io.physicalMatrix.step.valid.expect(true.B);d.io.physicalVectorRequest.valid.expect(true.B);d.clock.step()
        d.io.physicalMatrix.step.ready.poke(false.B);d.io.physicalVectorRequest.ready.poke(false.B);d.io.physicalMatrixAcceptedSteps.poke(8.U)
        response(d,0,txn,stalls=2)
        for(i<-1 until 36){issue(d,i,txn,stalls=if(i==35)2 else 0);response(d,i,txn)}
        matrixDone(d);d.io.matrixDone.valid.expect(true.B);d.io.matrixDone.bits.drained.expect(true.B);d.io.matrixDone.bits.issuedSliceSteps.expect(8.U)
        val mh=snap(d.io.matrixDone.bits);d.clock.step(2);assert(snap(d.io.matrixDone.bits)==mh)
        d.io.matrixDone.ready.poke(true.B);d.clock.step();d.io.matrixDone.ready.poke(false.B)
        fence(d,txn);finishVector(d,36,txn);d.io.allResourcesDrained.expect(true.B)
        // End wins over a new owner; no lease crosses the block context fence.
        d.io.end.bits.poke(txn.U);d.io.end.valid.poke(true.B);lease(d.io.vectorLease.bits,txn,true,1);d.io.vectorLease.valid.poke(true.B)
        d.io.vectorLease.ready.expect(false.B);d.io.end.ready.expect(true.B);d.clock.step();d.io.end.valid.poke(false.B);d.io.vectorLease.valid.poke(false.B)
        d.io.active.expect(false.B);d.io.physicalMatrixAcceptedSteps.poke(0.U)
      }
    }
  }
  it should "reject all three terminal same-cycle new-offer and unknown-return counterexamples" in {
    test(new UnifiedMatrixVectorLeasePortsV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d);acquire(d,matrix=true);group(d)
      d.io.matrixStep.valid.poke(true.B);d.io.physicalMatrix.done.valid.poke(true.B);d.io.physicalMatrix.done.bits.tag.poke(0.U)
      d.io.matrixStep.ready.expect(false.B);d.io.physicalMatrix.done.ready.expect(true.B);d.clock.step()
      d.io.matrixStep.valid.poke(false.B);d.io.physicalMatrix.done.valid.poke(false.B)
      d.io.matrixDone.bits.drained.expect(true.B);d.io.physicalMatrix.step.valid.expect(false.B);d.clock.step(2);d.io.physicalMatrix.step.valid.expect(false.B)
      isolateReset(d);begin(d);acquire(d);fence(d,status=2);releaseBits(d,0,status=2)
      request(d,0);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRelease.valid.poke(true.B)
      d.io.vectorRequest.ready.expect(false.B);d.io.vectorRelease.ready.expect(true.B);d.clock.step()
      d.io.vectorRequest.valid.poke(false.B);d.io.vectorRelease.valid.poke(false.B)
      d.io.vectorDone.bits.drained.expect(true.B);d.io.vectorDone.bits.status.expect(2.U);d.io.physicalVectorRequest.valid.expect(false.B)
      isolateReset(d);begin(d);acquire(d);fence(d,status=2);releaseBits(d,0,status=2)
      d.io.vectorRelease.valid.poke(true.B);d.io.physicalVectorResult.valid.poke(true.B)
      d.io.vectorRelease.ready.expect(false.B);d.io.physicalVectorResult.ready.expect(false.B);d.clock.step()
      d.io.physicalVectorResult.valid.poke(false.B);d.io.vectorRelease.ready.expect(false.B);d.io.vectorDone.valid.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }
  it should "keep accepted ordinals stable and drain held offers through ordinary poison" in {
    test(new UnifiedMatrixVectorLeasePortsV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d);acquire(d)
      request(d,0);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRequest.ready.expect(true.B);d.clock.step()
      request(d,1);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRequest.ready.expect(false.B)
      val held=snap(d.io.physicalVectorRequest.bits)
      d.clock.step(3);d.io.resetRequired.expect(false.B);assert(snap(d.io.physicalVectorRequest.bits)==held)
      d.io.physicalVectorRequest.ready.poke(true.B);d.clock.step();d.io.physicalVectorRequest.ready.poke(false.B)
      d.io.vectorRequest.ready.expect(false.B);d.io.resetRequired.expect(false.B)
      response(d,0);d.io.vectorRequest.ready.expect(true.B);d.clock.step();d.io.vectorRequest.valid.poke(false.B)
      // Private ordinary poison is NOT raw-response quarantine. Already-owned
      // accepted work and subsequent legitimate draining requests may proceed.
      lease(d.io.ownerFault.bits.lease,100,true);d.io.ownerFault.bits.resource.poke(1.U);d.io.ownerFault.bits.reason.poke(9.U);d.io.ownerFault.valid.poke(true.B)
      d.clock.step();d.io.ownerFault.valid.poke(false.B);d.io.resetRequired.expect(true.B);d.io.physicalVectorRequest.valid.expect(true.B)
      d.io.physicalVectorRequest.ready.poke(true.B);d.clock.step();d.io.physicalVectorRequest.ready.poke(false.B);response(d,1)
      issue(d,2);response(d,2);fence(d,status=2);finishVector(d,3,bad=true)
      d.io.end.bits.poke(100.U);d.io.end.valid.poke(true.B);d.io.end.ready.expect(false.B);d.io.begin.ready.expect(false.B)
    }
  }
  it should "enforce36 accepted offers and quarantine unknown Matrix returns without invented drain" in {
    test(new UnifiedMatrixVectorLeasePortsV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d);acquire(d)
      for(i<-0 until 35){issue(d,i);response(d,i)}
      request(d,35);d.io.vectorRequest.valid.poke(true.B);d.io.vectorRequest.ready.expect(true.B);d.clock.step()
      request(d,36);d.io.vectorRequest.ready.expect(false.B);d.clock.step();d.io.resetRequired.expect(true.B)
      d.io.vectorRequest.valid.poke(false.B);d.io.physicalVectorRequest.valid.expect(true.B)
      d.io.physicalVectorRequest.ready.poke(true.B);d.clock.step();d.io.physicalVectorRequest.ready.poke(false.B);response(d,35)
      fence(d,status=2);finishVector(d,36,bad=true)
      isolateReset(d);begin(d);acquire(d)
      // Wrong identity and undrained packets cannot supply producer credit.
      lease(d.io.producerFence.bits.lease,101,true);d.io.producerFence.bits.drained.poke(true.B);d.io.producerFence.valid.poke(true.B)
      d.io.producerFence.ready.expect(false.B);d.clock.step();d.io.resetRequired.expect(true.B)
      lease(d.io.producerFence.bits.lease,100,true);d.io.producerFence.bits.drained.poke(false.B)
      d.io.producerFence.ready.expect(false.B);d.clock.step();d.io.producerFence.valid.poke(false.B)
      releaseBits(d,0,status=2);d.io.vectorRelease.valid.poke(true.B);d.io.vectorRelease.ready.expect(false.B);d.clock.step();d.io.vectorRelease.valid.poke(false.B)
      fence(d,status=2);finishVector(d,0,bad=true)
      isolateReset(d);begin(d)
      d.io.physicalMatrix.result.valid.poke(true.B);d.io.physicalMatrix.result.ready.expect(false.B)
      d.clock.step();d.io.physicalMatrix.result.valid.poke(false.B);d.io.resetRequired.expect(true.B)
      d.io.matrixDone.valid.expect(false.B);d.io.vectorDone.valid.expect(false.B);d.io.allResourcesDrained.expect(false.B)
      lease(d.io.matrixLease.bits,100,false);d.io.matrixLease.valid.poke(true.B);d.io.matrixLease.ready.expect(false.B)
    }
  }
}
