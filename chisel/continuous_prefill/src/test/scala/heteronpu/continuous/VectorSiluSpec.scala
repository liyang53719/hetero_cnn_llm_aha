// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class VectorSiluSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def f(x:Double):Float=x.toFloat
  def expRecipe(x:Float):Float={
    if(math.abs(x)>=80)0f else {
      val t=f(math.abs(x)*f(1/math.log(2.0)));val k=t.toInt;val frac=f(t-k.toFloat)
      val coeff=(0 to 7).map(i=>f(math.pow(-math.log(2.0),i)/(if(i==0)1.0 else (1 to i).map(_.toDouble).product)))
      var h=coeff(7);for(i<-6 to 0 by -1)h=f(f(h*frac)+coeff(i))
      f(h*java.lang.Float.intBitsToFloat((127-k)<<23))
    }
  }
  def golden(a:Float,b:Float):Float={val e=expRecipe(a);val inv=f(1f/f(1f+e));val gate=f(inv*(if(java.lang.Float.floatToRawIntBits(a)<0)e else 1f));f(f(gate*a)*b)}
  "SiluVectorUnit" should "match the frozen scalar recipe across parallel lanes and retain stalled outputs" in {
    test(new SiluVectorUnit(16)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
      val rng=new scala.util.Random(90816)
      var checked=0
      for(batch<-0 until 12){
        val aa=(0 until 16).map(i=>if(batch==0)Seq(0f,-0f,0.1f,-0.1f,1f,-1f,10f,-10f,79f,-79f,80f,-80f,0.5f,-0.5f,30f,-30f)(i)else f(rng.nextDouble()*30-15))
        val bb=Seq.fill(16)(f(rng.nextDouble()*2-1))
        for(i<-0 until 16){d.io.request.bits.gate(i).poke(F32.bits(aa(i)).U);d.io.request.bits.up(i).poke(F32.bits(bb(i)).U)}
        d.io.request.valid.poke(true.B);d.io.request.ready.expect(true.B);d.clock.step();d.io.request.valid.poke(false.B)
        var n=0;while(!d.io.result.valid.peek().litToBoolean && n<250){d.clock.step();n+=1};assert(n<250)
        d.io.result.bits.error.expect(false.B)
        for(i<-0 until 16){d.io.result.bits.value(i).expect(F32.bits(golden(aa(i),bb(i))).U);checked+=1}
        d.clock.step(7);d.io.result.valid.expect(true.B)
        for(i<-0 until 16)d.io.result.bits.value(i).expect(F32.bits(golden(aa(i),bb(i))).U)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
      println(s"SILU_VECTOR_EXACT_PASS checked_fp32=$checked lanes=16")
    }
  }
  it should "reject nonfinite input and accept a later valid vector" in {
    test(new SiluVectorUnit(2)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
      for(bad<-Seq(true,false)){
        for(i<-0 until 2){d.io.request.bits.gate(i).poke((if(bad&&i==0)BigInt("7fc00001",16)else F32.bits(1f)).U);d.io.request.bits.up(i).poke(F32.bits(1f).U)}
        d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
        var n=0;while(!d.io.result.valid.peek().litToBoolean&&n<250){d.clock.step();n+=1};assert(n<250)
        d.io.result.bits.error.expect(bad.B);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
    }
  }
}
