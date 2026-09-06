// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class BlockScalarFloatSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  "BlockScalarFloat" should "match IEEE operations and bounded exp approximation while holding a stalled result" in {
    test(new BlockScalarFloat).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.request.bits.op.poke(0.U);d.io.request.bits.a.poke(0.U);d.io.request.bits.b.poke(0.U)
      def run(op:Int,a:Float,b:Float,expected:Float,tol:Double,error:Boolean=false):Unit={
        d.io.request.bits.op.poke(op.U);d.io.request.bits.a.poke(F32.bits(a.toDouble).U);d.io.request.bits.b.poke(F32.bits(b.toDouble).U);d.io.request.valid.poke(true.B)
        var n=0;while(!d.io.request.ready.peek().litToBoolean&&n<200){d.clock.step();n+=1};assert(n<200);d.clock.step();d.io.request.valid.poke(false.B)
        n=0;while(!d.io.result.valid.peek().litToBoolean&&n<200){d.clock.step();n+=1};assert(n<200)
        d.io.error.expect(error.B);val raw=d.io.result.bits.peek().litValue;val actual=java.lang.Float.intBitsToFloat(raw.toInt)
        if(!error)assert(math.abs(actual.toDouble-expected.toDouble)<=tol*math.max(1e-35,math.abs(expected.toDouble)),s"op=$op a=$a b=$b actual=$actual expected=$expected")
        d.clock.step(3);d.io.result.valid.expect(true.B);d.io.result.bits.expect(raw.U);d.io.error.expect(error.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
      run(0,1.25f,-0.25f,1f,0);run(1,1.25f,0.5f,0.625f,0);run(2,1f,3f,1f/3f,0);run(3,2f,0f,math.sqrt(2).toFloat,0)
      val r=new scala.util.Random(807)
      for(x<-Seq(0f,0.1f,0.6931472f,1f,-2f,10f,30f,79f)++Seq.fill(60)((r.nextDouble()*50).toFloat))run(4,x,0f,math.exp(-math.abs(x.toDouble)).toFloat,5e-6)
      run(4,80f,0f,0f,0);run(2,1f,0f,0f,0,true);run(3,-1f,0f,0f,0,true);run(5,0f,0f,0f,0,true);run(0,Float.NaN,0f,0f,0,true)
      println("BLOCK_SCALAR_VECTORS_PASS count=77 random_seed=807")
    }
  }
}
