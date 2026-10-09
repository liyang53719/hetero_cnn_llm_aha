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
  it should "accept rounded underflow only for the explicit IEEE multiply policy" in {
    test(new BlockScalarFloat).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
      d.io.request.bits.op.poke(0.U);d.io.request.bits.a.poke(0.U);d.io.request.bits.b.poke(0.U)
      def run(op:Int,a:String,b:String,expected:String,error:Boolean):Unit={
        d.io.request.bits.op.poke(op.U);d.io.request.bits.a.poke(BigInt(a,16).U);d.io.request.bits.b.poke(BigInt(b,16).U)
        d.io.request.valid.poke(true.B)
        var n=0;while(!d.io.request.ready.peek().litToBoolean&&n<200){d.clock.step();n+=1};assert(n<200)
        d.clock.step();d.io.request.valid.poke(false.B)
        // The exception policy belongs to the accepted request, not live pins.
        d.io.request.bits.op.poke(7.U);d.io.request.bits.a.poke("h7fc00000".U)
        n=0;while(!d.io.result.valid.peek().litToBoolean&&n<200){d.clock.step();n+=1};assert(n<200)
        for(_<-0 until 6){d.io.result.bits.expect(BigInt(expected,16).U);d.io.error.expect(error.B);d.io.result.valid.expect(true.B);d.clock.step()}
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
      // Exact official layer0/channel397 operands. RNE is negative zero;
      // HardFloat's independently probed flags are underflow + inexact (0x03).
      run(ScalarOp.Mul,"83d70000","02200000","80000000",true)
      run(ScalarOp.MulIeeeRne,"83d70000","02200000","80000000",false)
      run(ScalarOp.MulIeeeRne,"03d70000","02200000","00000000",false)
      // Subnormal ties demonstrate gradual underflow and round-to-even rather
      // than flush-to-zero. The exact subnormal product keeps legacy behavior.
      run(ScalarOp.Mul,"00800000","3f000000","00400000",false)
      run(ScalarOp.Mul,"00800000","3f000001","00400000",true)
      run(ScalarOp.MulIeeeRne,"00800000","3f000001","00400000",false)
      run(ScalarOp.MulIeeeRne,"00800000","3f000003","00400002",false)
      // Both operands are exact BF16 widenings, as in the GDN owner.
      run(ScalarOp.Mul,"00810000","34810000","00000002",true)
      run(ScalarOp.MulIeeeRne,"00810000","34810000","00000002",false)
      run(ScalarOp.MulIeeeRne,"3fc00000","40000000","40400000",false)
      run(ScalarOp.MulIeeeRne,"3f800001","3f800001","3f800002",false)
      run(ScalarOp.Mul,"7f7fffff","40000000","7f800000",true)
      run(ScalarOp.MulIeeeRne,"7f7fffff","40000000","7f800000",true)
      run(ScalarOp.MulIeeeRne,"7fc00000","3f800000","00000000",true)
      run(ScalarOp.MulIeeeRne,"7f800000","00000000","00000000",true)
      run(ScalarOp.Div,"3f800000","00000000","7f800000",true)
      run(5,"00000000","00000000","00000000",true)
      run(7,"00000000","00000000","00000000",true)
      println("BLOCK_SCALAR_IEEE_UNDERFLOW_PASS bit_vectors=18 legacy_policy_preserved=true")
    }
  }
}
