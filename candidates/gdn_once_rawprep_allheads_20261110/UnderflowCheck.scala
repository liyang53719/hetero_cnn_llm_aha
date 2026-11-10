import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.continuous._
object UnderflowCheck extends App {
 RawTester.test(new UnifiedVectorElement32BankV4,Seq(VerilatorBackendAnnotation)){d=>
  def zero(x:Data):Unit=x match{case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case a:Aggregate=>a.getElements.foreach(zero);case _=>()}
  zero(d.io.request.bits);d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B);d.clock.step()
  for(policy<-Seq(0,3)){
   d.io.request.bits.payload.policy.poke(policy.U);d.io.request.bits.payload.multiply.poke(true.B)
   d.io.request.bits.payload.a(0).poke("h0713e498".U);d.io.request.bits.payload.b(0).poke("hb8009900".U)
   d.io.request.valid.poke(true.B);d.io.request.ready.expect(true.B);d.clock.step();d.io.request.valid.poke(false.B)
   var n=0;while(!d.io.result.valid.peek().litToBoolean && n<10){d.clock.step();n+=1}
   d.io.result.valid.expect(true.B);d.io.result.bits.payload.value(0).expect("h80252558".U)
   d.io.result.bits.payload.arithFlags(0).expect(3.U);d.io.result.bits.payload.error.expect((policy==0).B)
   println(s"UNDERFLOW_DIAGNOSTIC policy=$policy result=80252558 flags=3 error=${d.io.result.bits.payload.error.peek().litToBoolean}")
   d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
  }
 }
}
