package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.{VerilatorBackendAnnotation,VerilatorCFlags}

/** Boundary protocol test, not RMS arithmetic or full-block proof. Synthetic
  * Guard/owner metadata is intentional; the tested helper bodies and bank are
  * actual production code. No fabricated numerical primitive response. */
object Rms32FaultFeedbackProtocolTest extends App {
  RawTester.test(new Rms32FaultFeedbackFixture,Seq(VerilatorBackendAnnotation,VerilatorCFlags(Seq("-O0")))){c=>
    def zero(x:Data):Unit=x match {
      case b:Bool=>b.poke(false.B)
      case u:UInt=>u.poke(0.U)
      case s:SInt=>s.poke(0.S)
      case v:Vec[_]=>v.foreach(z=>zero(z.asInstanceOf[Data]))
      case r:Record=>r.elements.values.foreach(zero)
      case _=>throw new IllegalArgumentException("unhandled fixture input")
    }
    def tickUntil(ok: =>Boolean,limit:Int=4000):Unit={var n=0;while(!ok && n<limit){c.clock.step();n+=1};assert(ok,"bounded protocol timeout")}
    def clean():Unit={
      for(x<-Seq(c.io.authority,c.io.logical,c.io.physical,c.io.terminal,c.io.runtimeTerminal,c.io.p0Request.bits,c.io.runtimeRequest.bits,c.io.scalarRequest.bits))zero(x)
      c.io.p0Request.valid.poke(false.B);c.io.runtimeRequest.valid.poke(false.B);c.io.scalarRequest.valid.poke(false.B)
      c.io.p0Result.ready.poke(true.B);c.io.runtimeResult.ready.poke(true.B);c.io.scalarResult.ready.poke(true.B)
      c.io.terminalReady.poke(true.B);c.io.coreDrained.poke(true.B);c.io.coreReset.poke(false.B);c.io.runtimeDrained.poke(true.B)
      c.io.independentFault.poke(false.B);c.io.injectConflict.poke(false.B);c.io.injectWrongScalarTag.poke(false.B)
      c.reset.poke(true.B);c.clock.step(3);c.reset.poke(false.B);c.clock.step(2)
    }
    def job(j:QwenOwnerJob,runtime:Boolean,tag:Int):Unit={
      zero(j);j.kind.poke((if(runtime)QwenOwnerKind.GdnRmsNorm else QwenOwnerKind.Norm).U)
      j.m.poke(1.U);j.n.poke((if(runtime)1024 else 1536).U);j.k.poke((if(runtime)1024 else 1536).U)
      j.tag.poke(tag.U);j.a.poke(0x1000.U);j.b.poke(0x3000.U);j.dst.poke(0x5000.U)
      j.writeBytes.poke((if(runtime)2048 else 6144).U)
      j.activationBf16.poke(runtime.B);j.weightBf16.poke(runtime.B);j.outputBf16.poke(runtime.B)
      j.cold.poke(runtime.B)
    }
    def logical(runtime:Boolean):Unit={
      c.io.authority.accepted.poke(true.B);c.io.authority.ownerValidated.poke(true.B)
      c.io.authority.launch.profileId.poke((if(runtime)1 else 0).U);c.io.authority.launch.epoch.poke(1.U);c.io.authority.transaction.poke(1.U)
      job(c.io.authority.ownerJob,runtime,5);job(c.io.logical.bits,runtime,5)
      c.io.logical.valid.poke(true.B);c.clock.step();c.io.logical.valid.poke(false.B)
    }
    def physical(runtime:Boolean):Unit={job(c.io.physical.bits,runtime,19);c.io.physical.valid.poke(true.B);c.clock.step();c.io.physical.valid.poke(false.B)}
    def start(runtime:Boolean):Unit={logical(runtime);physical(runtime);tickUntil(c.io.status(11).active.peek().litToBoolean);c.clock.step()}
    def vector(runtime:Boolean,target:Int):Unit={
      val q=if(runtime)c.io.runtimeRequest else c.io.p0Request
      zero(q.bits);q.valid.poke(true.B);tickUntil(q.ready.peek().litToBoolean);c.clock.step();q.valid.poke(false.B)
      tickUntil(c.io.status(11).counts.returned.peek().litValue==target)
    }
    def scalar(target:Int):Unit={
      zero(c.io.scalarRequest.bits);c.io.scalarRequest.bits.payload.op.poke(ScalarOp.Add.U)
      c.io.scalarRequest.valid.poke(true.B);tickUntil(c.io.scalarRequest.ready.peek().litToBoolean);c.clock.step();c.io.scalarRequest.valid.poke(false.B)
      tickUntil(c.io.status(8).counts.returned.peek().litValue==target)
    }
    def terminal(runtime:Boolean,error:Boolean=false,tag:Int=19):Unit={
      zero(c.io.terminal.bits);c.io.terminal.bits.tag.poke(tag.U);c.io.terminal.bits.status.poke((if(error)Status.Protocol else Status.Ok).U)
      c.io.terminal.bits.writeBytes.poke((if(runtime)2048 else 6144).U);c.io.terminal.valid.poke(true.B)
      if(runtime){
        val r=c.io.runtimeTerminal.bits;zero(r);r.tag.poke(tag.U);r.status.poke((if(error)Status.Protocol else Status.Ok).U)
        r.accepted.tokens.poke(1.U);r.accepted.hiddenWidth.poke(1024.U);r.accepted.input.poke(0x1000.U);r.accepted.weight.poke(0x3000.U);r.accepted.output.poke(0x5000.U);r.accepted.tag.poke(19.U);r.accepted.reductionRecipe.poke(1.U)
        r.writeBytes.poke(2048.U);r.outputAckBytes.poke(2048.U);r.outputCommitted.poke(true.B);r.resourcesDrained.poke(true.B)
        r.scalarAccepted.poke(4.U);r.scalarReturned.poke(4.U);r.vectorAccepted.poke(206.U);r.vectorReturned.poke(206.U)
        r.memoryAccepted.poke(128.U);r.memoryReturned.poke(128.U);c.io.runtimeTerminal.valid.poke(true.B)
      }
    }
    println("LEASE_CASE P0_EXACT_111")
    clean();start(false)
    assert(!c.io.status(8).active.peek().litToBoolean,"P0 must not borrow own Scalar8")
    for(i<-1 to 111)vector(false,i)
    c.io.terminalReady.poke(false.B);terminal(false);c.clock.step(4)
    assert(c.io.status(11).active.peek().litToBoolean && !c.io.status(11).retiring.peek().litToBoolean,"no retire before physicalDone.fire")
    c.io.terminalReady.poke(true.B);c.clock.step();c.io.terminal.valid.poke(false.B)
    tickUntil(!c.io.status(11).active.peek().litToBoolean);assert(!c.io.p0Fault.peek().litToBoolean && !c.io.adapterFault.peek().litToBoolean)

    println("LEASE_CASE RUNTIME_EXACT_206_PLUS4")
    clean();start(true)
    assert(c.io.status(8).lease.lease.expectedOperations.peek().litValue==4)
    assert(c.io.status(11).lease.lease.expectedOperations.peek().litValue==206)
    assert(!c.io.status(9).active.peek().litToBoolean,"RMS32 must not acquire Format9")
    for(i<-1 to 4)scalar(i);for(i<-1 to 206)vector(true,i)
    terminal(true);c.clock.step();c.io.terminal.valid.poke(false.B);c.io.runtimeTerminal.valid.poke(false.B)
    tickUntil(!c.io.status(11).active.peek().litToBoolean && !c.io.status(8).active.peek().litToBoolean)
    assert(!c.io.prefixFault.peek().litToBoolean && !c.io.adapterFault.peek().litToBoolean)

    println("LEASE_CASE UNPUBLISHED_FAULT")
    clean();start(false);c.io.independentFault.poke(true.B);c.io.p0Request.valid.poke(true.B);c.clock.step(2)
    assert(!c.io.actualPublished.peek().litToBoolean && c.io.status(11).counts.accepted.peek().litValue==0,"unpublished fresh intent blocked")
    c.io.p0Request.valid.poke(false.B) // boundary owner cancels only unpublished intent

    def publicationTrace(label:String):Unit={
      println(s"P0_PUBLICATION_TRACE $label valid=${c.io.actualPublished.peek().litToBoolean} ready=${c.io.p0Request.ready.peek().litToBoolean} accepted=${c.io.status(11).counts.accepted.peek().litValue} issued=${c.io.status(11).counts.issued.peek().litValue} returned=${c.io.status(11).counts.returned.peek().litValue} fault=${c.io.independentFault.peek().litToBoolean}")
    }
    println("LEASE_CASE THIRD_REAL_STALL_LATE_FAULT")
    clean();start(false);c.io.p0Result.ready.poke(false.B);c.io.p0Request.valid.poke(true.B)
    tickUntil(c.io.p0Request.ready.peek().litToBoolean);c.clock.step();c.io.p0Request.valid.poke(false.B)
    tickUntil(c.io.p0Result.valid.peek().litToBoolean)
    // A backpressured bank result does not fill the adapter ingress. The
    // second offer is accepted into vOffer; only a THIRD offer can be held at
    // this external boundary. A post-edge valid/!ready alone does not prove
    // held=true: the offer must remain visible across a stalled clock edge.
    assert(c.io.status(11).counts.accepted.peek().litValue==1)
    c.io.p0Request.valid.poke(true.B)
    assert(c.io.p0Request.ready.peek().litToBoolean,"second offer fills real empty ingress")
    publicationTrace("second-before-fire");c.clock.step();publicationTrace("second-after-fire")
    assert(c.io.status(11).counts.accepted.peek().litValue==2,"second packet accepted, not held externally")
    c.io.p0Request.bits.a(0).poke("h3f800000".U) // distinct THIRD request; second payload is captured already
    assert(c.io.actualPublished.peek().litToBoolean && !c.io.p0Request.ready.peek().litToBoolean)
    publicationTrace("third-before-stall-edge")
    c.clock.step();publicationTrace("third-after-stall-edge") // valid && !ready establishes actual HeldDecoupledOffer debt
    assert(c.io.status(11).counts.accepted.peek().litValue==2 && c.io.actualPublished.peek().litToBoolean)
    c.io.independentFault.poke(true.B)
    for(i<-0 until 3){
      publicationTrace(s"third-late-fault-$i-before-edge")
      assert(c.io.actualPublished.peek().litToBoolean && !c.io.p0Request.ready.peek().litToBoolean,"held publication survives late independent fault")
      assert(c.io.status(11).counts.accepted.peek().litValue==2 && c.io.status(11).counts.returned.peek().litValue==0,"fault cannot drop or refund accepted debt")
      assert(c.io.p0Request.bits.a(0).peek().litValue==BigInt("3f800000",16) && c.io.p0Request.bits.b(0).peek().litValue==0,"held owner payload remains exact")
      c.clock.step()
    }
    publicationTrace("third-after-fault-edges")
    assert(c.io.actualPublished.peek().litToBoolean,"held remains after all fault edges")
    c.io.independentFault.poke(false.B);c.io.p0Result.ready.poke(true.B)
    tickUntil(c.io.p0Request.ready.peek().litToBoolean);c.clock.step();c.io.p0Request.valid.poke(false.B)
    tickUntil(c.io.status(11).counts.returned.peek().litValue==2 && c.io.p0Result.valid.peek().litToBoolean)
    assert(!c.io.p0Result.bits.error.peek().litToBoolean && c.io.p0Result.bits.value(0).peek().litValue==BigInt("3f800000",16),"third accepted payload survives held fault and real bank")
    for(i<-1 until 32)assert(c.io.p0Result.bits.value(i).peek().litValue==0,"other third payload lanes unchanged")
    c.clock.step();assert(c.io.status(11).counts.returned.peek().litValue==3)
    assert(c.io.status(11).counts.accepted.peek().litValue==3 && c.io.status(11).counts.issued.peek().litValue==3,"exact three accepted/issued/returned")

    println("LEASE_CASE WRONG_TERMINAL_TAG")
    clean();start(false);terminal(false,error=true,tag=20);c.clock.step();c.io.terminal.valid.poke(false.B);c.clock.step(2)
    assert(c.io.p0Fault.peek().litToBoolean && c.io.status(11).active.peek().litToBoolean,"wrong terminal tag cannot refund lease")

    println("LEASE_CASE CONFLICTING_ACQUIRE")
    clean();logical(false);physical(false);c.io.injectConflict.poke(true.B);c.clock.step();c.io.injectConflict.poke(false.B);c.clock.step(2)
    assert(c.io.p0Fault.peek().litToBoolean && !c.io.status(11).active.peek().litToBoolean,"conflicting acquire must not grant")

    println("LEASE_CASE ERROR_WITH_OWNER_DEBT")
    clean();start(true);terminal(true,error=true);c.io.runtimeDrained.poke(false.B);c.io.runtimeTerminal.bits.resourcesDrained.poke(false.B)
    c.clock.step();c.io.terminal.valid.poke(false.B);c.io.runtimeTerminal.valid.poke(false.B);c.clock.step(2)
    assert(c.io.prefixFault.peek().litToBoolean && c.io.status(8).active.peek().litToBoolean && c.io.status(11).active.peek().litToBoolean,"error cannot bypass actual owner drain")
    println("LEASE_CASE CURRENT_CORE_RESET")
    clean();start(false);c.io.coreReset.poke(true.B);c.io.p0Request.valid.poke(true.B);c.clock.step(2)
    assert(!c.io.actualPublished.peek().litToBoolean && c.io.status(11).counts.accepted.peek().litValue==0,"current core poison blocks first publication")

    println("LEASE_CASE WRONG_SCALAR_RESPONSE_TAG")
    clean();start(true);c.io.injectWrongScalarTag.poke(true.B);zero(c.io.scalarRequest.bits)
    c.io.scalarRequest.bits.payload.op.poke(ScalarOp.Add.U);c.io.scalarRequest.valid.poke(true.B)
    tickUntil(c.io.scalarRequest.ready.peek().litToBoolean);c.clock.step();c.io.scalarRequest.valid.poke(false.B)
    tickUntil(c.io.adapterFault.peek().litToBoolean)
    assert(c.io.status(8).counts.returned.peek().litValue==0 && !c.io.status(8).resourcesDrained.peek().litToBoolean,"wrong actual primitive response tag quarantines, no refund")
    terminal(true,error=true);c.clock.step();c.io.terminal.valid.poke(false.B);c.io.runtimeTerminal.valid.poke(false.B);c.clock.step(2)
    assert(c.io.status(8).active.peek().litToBoolean && c.io.status(11).active.peek().litToBoolean,"error cannot refund unknown-response debt")
    println("RMS32_LEASE_PROTOCOL_BOUNDARY_ONLY_NOT_NUMERICAL_PASS")
  }
}
