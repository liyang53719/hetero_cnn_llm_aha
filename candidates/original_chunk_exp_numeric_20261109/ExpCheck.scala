import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import heteronpu.continuous._
object ExpCheck extends App {
 RawTester.test(new BlockScalarFloatPolicyV2,Seq(TreadleBackendAnnotation)){d=>
  d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
  d.io.request.bits.policy.poke(0.U);d.io.request.bits.payload.op.poke(4.U)
  d.io.request.bits.payload.a.poke(0.U);d.io.request.bits.payload.b.poke(0.U)
  d.clock.setTimeout(20000);d.clock.step()
  var checked=0;var totalCycles=0;var maxCycles=0
  for((p,a,y)<-Fixture.cases){
   d.io.request.ready.expect(true.B);d.io.request.valid.poke(true.B)
   d.io.request.bits.policy.poke(p.U);d.io.request.bits.payload.op.poke(4.U)
   d.io.request.bits.payload.a.poke(a.U);d.io.request.bits.payload.b.poke(0.U)
   d.clock.step();d.io.request.valid.poke(false.B)
   d.io.request.bits.policy.poke((1-p).U);d.io.request.bits.payload.a.poke("h7fc00000".U)
   var cycles=0
   while(!d.io.result.valid.peek().litToBoolean && cycles<250){d.io.request.ready.expect(false.B);d.clock.step();cycles+=1}
   assert(cycles<250,s"timeout policy=$p input=$a")
   for(_<-0 until 3){
    d.io.result.valid.expect(true.B);d.io.result.bits.policy.expect(p.U)
    assert(d.io.result.bits.value.peek().litValue==BigInt(y),s"mismatch policy=$p input=${a.toHexString} expected=${y.toHexString} actual=${d.io.result.bits.value.peek().litValue.toString(16)}")
    d.io.result.bits.error.expect(false.B);d.io.result.bits.flags.expect(0.U)
    d.io.result.bits.primitiveFlagsValid.expect(false.B);d.io.request.ready.expect(false.B);d.clock.step()
   }
   d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
   d.io.result.valid.expect(false.B);d.io.request.ready.expect(true.B)
   checked+=1;totalCycles+=cycles;maxCycles=math.max(maxCycles,cycles)
  }
  println(s"EXP_PASS checked=$checked mismatches=0 waitCycles=$totalCycles maxWaitCycles=$maxCycles heldCycles=3 policies=0,1")
 }
}
