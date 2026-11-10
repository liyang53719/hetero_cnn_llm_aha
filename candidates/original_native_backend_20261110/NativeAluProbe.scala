import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
object NativeAluProbe extends App {
 val started=System.nanoTime()
 RawTester.test(new gemmini.HeteroFP32Alu,Seq(VerilatorBackendAnnotation),"native_original_alu_probe"){d=>
  val testStart=System.nanoTime();var count=0
  for(i<-0 until 2048; multiply<-Seq(false,true)){
   val a=((i*17%1021)-510).toFloat/32.0f
   val b=((i*31%997)-498).toFloat/64.0f
   val expected=if(multiply)(a*b) else (a+b)
   def bits(f:Float)=BigInt(java.lang.Float.floatToRawIntBits(f).toLong & 0xffffffffL)
   d.io.op.poke(multiply.B);d.io.x.poke(bits(a).U);d.io.y.poke(bits(b).U)
   d.clock.step();d.io.out.expect(bits(expected).U);d.io.exceptionFlags.expect(0.U);count+=1
  }
  println(s"PASS original_alu operations=$count simulation_seconds=${(System.nanoTime()-testStart)/1e9}")
 }
 println(s"NATIVE_TOTAL_SECONDS ${(System.nanoTime()-started)/1e9}")
}
