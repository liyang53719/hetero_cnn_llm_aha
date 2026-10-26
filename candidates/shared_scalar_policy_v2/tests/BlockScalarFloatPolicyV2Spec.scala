// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Future actual HardFloat primitive tests. Expected words are fixed rational
  * NODE-recipe witnesses, not a correctly-rounded exp/Torch oracle. No full
  * GDN owner, checkpoint weights, or full4096 block is instantiated here. */
class BlockScalarFloatPolicyV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "one shared Scalar runtime numerical policy"
  def init(d:BlockScalarFloatPolicyV2):Unit={
    d.io.request.valid.poke(false.B);d.io.request.bits.policy.poke(0.U)
    d.io.request.bits.payload.op.poke(0.U);d.io.request.bits.payload.a.poke(0.U);d.io.request.bits.payload.b.poke(0.U)
    d.io.result.ready.poke(false.B);d.clock.step()
  }
  def run(d:BlockScalarFloatPolicyV2,p:Int,op:Int,a:BigInt,b:BigInt,y:BigInt,
      error:Boolean=false,flags:Int=0,primitive:Boolean=false):Unit={
    d.io.request.ready.expect(true.B)
    d.io.request.bits.policy.poke(p.U);d.io.request.bits.payload.op.poke(op.U)
    d.io.request.bits.payload.a.poke(a.U);d.io.request.bits.payload.b.poke(b.U)
    d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
    // Runtime source changes after fire must not change any held result field.
    d.io.request.bits.policy.poke(((p+1)&3).U);d.io.request.bits.payload.op.poke(5.U)
    d.io.request.bits.payload.a.poke("h7fc00000".U);d.io.request.bits.payload.b.poke("hffffffff".U)
    var cycles=0
    while(!d.io.result.valid.peek().litToBoolean && cycles<250){d.io.request.ready.expect(false.B);d.clock.step();cycles+=1}
    assert(cycles<250,s"bounded policy=$p op=$op input=${a.toString(16)}")
    for(_<-0 until 4){
      d.io.result.valid.expect(true.B);d.io.result.bits.policy.expect(p.U)
      d.io.result.bits.value.expect(y.U);d.io.result.bits.error.expect(error.B)
      d.io.result.bits.flags.expect(flags.U);d.io.result.bits.primitiveFlagsValid.expect(primitive.B)
      d.io.request.ready.expect(false.B);d.clock.step()
    }
    d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
    d.io.result.valid.expect(false.B);d.io.request.ready.expect(true.B)
  }
  it should "switch legacy decay and dual Softplus on one DUT without reset and retain every result field" in {
    test(new BlockScalarFloatPolicyV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      val cases=Seq(
      (1, 4, BigInt("00000000",16), BigInt("3f800000",16)),
      (1, 4, BigInt("80000000",16), BigInt("3f800000",16)),
      (1, 4, BigInt("80000001",16), BigInt("3f800000",16)),
      (1, 4, BigInt("c2a00000",16), BigInt("05bfecba",16)),
      (1, 4, BigInt("c2aeac4f",16), BigInt("00800026",16)),
      (1, 4, BigInt("c2aeac50",16), BigInt("007fffe6",16)),
      (1, 4, BigInt("c2aeac51",16), BigInt("007fffa6",16)),
      (1, 4, BigInt("c2b72752",16), BigInt("0001d7fd",16)),
      (1, 4, BigInt("c2b72754",16), BigInt("0001d7fb",16)),
      (1, 4, BigInt("c2ce8ed0",16), BigInt("00000001",16)),
      (1, 4, BigInt("c2cff1b3",16), BigInt("00000001",16)),
      (1, 4, BigInt("c2cff1b4",16), BigInt("00000001",16)),
      (1, 4, BigInt("c2cff1b5",16), BigInt("00000000",16)),
      (1, 4, BigInt("ff7fffff",16), BigInt("00000000",16)),
      (1, 4, BigInt("c2a00001",16), BigInt("05bfec5b",16)),
      (0, 7, BigInt("c29e0000",16), BigInt("06826d17",16)),
      (2, 7, BigInt("c29e0000",16), BigInt("06826d27",16)),
      (0, 7, BigInt("c1200000",16), BigInt("383e6ab2",16)),
      (2, 7, BigInt("c1200000",16), BigInt("383e6ab3",16)),
      (0, 7, BigInt("c0880000",16), BigInt("3c680dd6",16)),
      (2, 7, BigInt("c0880000",16), BigInt("3c680dd6",16)),
      (0, 7, BigInt("bdcccccd",16), BigInt("3f24f72d",16)),
      (2, 7, BigInt("bdcccccd",16), BigInt("3f24f72d",16)),
      (0, 7, BigInt("80000000",16), BigInt("3f317218",16)),
      (2, 7, BigInt("80000000",16), BigInt("3f317218",16)),
      (0, 7, BigInt("00000000",16), BigInt("3f317218",16)),
      (2, 7, BigInt("00000000",16), BigInt("3f317218",16)),
      (0, 7, BigInt("3dcccccd",16), BigInt("3f3e90c7",16)),
      (2, 7, BigInt("3dcccccd",16), BigInt("3f3e90c7",16)),
      (0, 7, BigInt("3f800000",16), BigInt("3fa818f6",16)),
      (2, 7, BigInt("3f800000",16), BigInt("3fa818f6",16)),
      (0, 7, BigInt("41a00000",16), BigInt("41a00000",16)),
      (2, 7, BigInt("41a00000",16), BigInt("41a00000",16)),
      (0, 7, BigInt("41a40000",16), BigInt("41a40000",16)),
      (2, 7, BigInt("41a40000",16), BigInt("41a40000",16)),
      (0, 4, BigInt("00000000",16), BigInt("3f800000",16)),
      (0, 4, BigInt("bf800000",16), BigInt("3ebc5ab2",16)),
      (0, 4, BigInt("c29f0000",16), BigInt("061e3730",16)),
      (0, 4, BigInt("c2a00000",16), BigInt("00000000",16)),
      (0, 4, BigInt("c2b72752",16), BigInt("00000000",16)),
      (0, 4, BigInt("40000000",16), BigInt("3e0a954e",16)))
      for((p,op,a,y)<-cases)run(d,p,op,a,BigInt(0),y)
      // c2a00001 ->05bfec5b is retained despite the known Torch05bfec5a witness.
      // No tolerance/widening/clipping or implicit reference replacement.
    }
  }
  it should "reject unknown policy opcode domains and preserve the pinned Softplus domain" in {
    test(new BlockScalarFloatPolicyV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      val bad=Seq((3,4,BigInt(0)),(1,0,BigInt(0)),(1,3,BigInt(0)),(1,7,BigInt(0)),
        (2,4,BigInt(0)),(2,6,BigInt(0)),(0,5,BigInt(0)),(1,4,BigInt("3f800000",16)),
        (1,4,BigInt("7f800000",16)),(1,4,BigInt("ff800000",16)),(1,4,BigInt("7fc00000",16)),
        (2,7,BigInt("c2a00000",16)),(2,7,BigInt("c2a20000",16)),(0,7,BigInt("c2a00000",16)))
      for((p,op,a)<-bad)run(d,p,op,a,BigInt(0),BigInt(0),error=true)
      run(d,1,4,BigInt(0),BigInt("7f800000",16),BigInt(0),error=true)
    }
  }
  it should "retain primitive Add Mul op6 Div and Sqrt legacy flags and results" in {
    test(new BlockScalarFloatPolicyV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      run(d,0,0,BigInt("3f800000",16),BigInt("40000000",16),BigInt("40400000",16),primitive=true)
      run(d,0,1,BigInt(1),BigInt("3f000000",16),BigInt(0),error=true,flags=3,primitive=true)
      run(d,0,6,BigInt(1),BigInt("3f000000",16),BigInt(0),flags=3,primitive=true)
      run(d,0,2,BigInt("40800000",16),BigInt("40000000",16),BigInt("40000000",16))
      run(d,0,3,BigInt("40800000",16),BigInt(0),BigInt("40000000",16))
    }
  }
}
