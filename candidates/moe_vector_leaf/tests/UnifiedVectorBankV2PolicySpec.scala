package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Directed actual bank numeric-policy checks, not all IEEE/BF16-domain proof. */
class UnifiedVectorBankV2PolicySpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "common V2 bank explicit raw and materialized policies"
  private def init(d:UnifiedVectorBankV2):Unit={
    d.clock.setTimeout(2000);d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
    d.io.request.bits.policy.poke(0.U);d.io.request.bits.multiply.poke(false.B)
    for(i<-0 until 16){d.io.request.bits.a(i).poke(0.U);d.io.request.bits.b(i).poke(0.U)}
  }
  private def request(d:UnifiedVectorBankV2,policy:Int,mul:Boolean,a:BigInt,b:BigInt):Unit={
    d.io.request.bits.policy.poke(policy.U);d.io.request.bits.multiply.poke(mul.B)
    for(i<-0 until 16){d.io.request.bits.a(i).poke(a.U);d.io.request.bits.b(i).poke(b.U)}
    d.io.request.valid.poke(true.B);d.io.request.ready.expect(true.B);d.clock.step();d.io.request.valid.poke(false.B)
    d.io.result.valid.expect(true.B);d.io.result.bits.policy.expect(policy.U)
  }
  private def check(d:UnifiedVectorBankV2,error:Boolean,value:Option[BigInt]=None,flags:Option[Int]=None):Unit={
    d.io.result.bits.error.expect(error.B)
    for(i<-0 until 16){value.foreach(x=>d.io.result.bits.value(i).expect(x.U));flags.foreach(x=>d.io.result.bits.flags(i).expect(x.U))}
    val held=d.io.result.bits.value.map(_.peek().litValue).toVector
    val heldFlags=d.io.result.bits.flags.map(_.peek().litValue).toVector
    val heldPolicy=d.io.result.bits.policy.peek().litValue
    // Held result, all fields checked; the bank remains source-II2/nonelastic.
    d.clock.step(3);d.io.result.valid.expect(true.B);d.io.result.bits.error.expect(error.B)
    d.io.result.bits.policy.expect(heldPolicy.U)
    for(i<-0 until 16){d.io.result.bits.value(i).expect(held(i).U);d.io.result.bits.flags(i).expect(heldFlags(i).U)}
    d.io.request.ready.expect(false.B);d.io.result.ready.poke(true.B)
    d.io.request.ready.expect(false.B);d.clock.step();d.io.result.ready.poke(false.B);d.io.request.ready.expect(true.B)
  }
  it should "retain legacy raw values and distinguish legal BF16 Mul underflow from legacy fatal underflow" in {
    test(new UnifiedVectorBankV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      // Exact rawFP32 1.000000119 + 1.000000119 = 2.000000238, not BF16-expanded.
      request(d,0,false,BigInt("3f800001",16),BigInt("3f800001",16));check(d,false,Some(BigInt("40000001",16)),Some(0))
      // BF16 minsubnormal2^-133 *2^-17 =2^-150, half the FP32 minsubnormal.
      // FP32 RNE produces +0 with UF+NX=3; only explicit policy1 accepts it.
      request(d,1,true,BigInt("00010000",16),BigInt("37000000",16));check(d,false,Some(BigInt(0)),Some(3))
      request(d,0,true,BigInt("00010000",16),BigInt("37000000",16));check(d,true,Some(BigInt(0)),Some(3))
      // Signed underflow keeps the sign of zero through both materializations.
      request(d,1,true,BigInt("80010000",16),BigInt("37000000",16));check(d,false,Some(BigInt("80000000",16)),Some(3))
    }
  }
  it should "round BF16 ties to even and reject policy, format, nonfinite and overflow cases explicitly" in {
    test(new UnifiedVectorBankV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      // Products land at consecutive odd/even BF16 midpoints; rawFP32 exact.
      request(d,1,true,BigInt("3fc00000",16),BigInt("3f810000",16));check(d,false,Some(BigInt("3fc20000",16)),Some(0))
      request(d,1,true,BigInt("3fc00000",16),BigInt("3f830000",16));check(d,false,Some(BigInt("3fc40000",16)),Some(0))
      request(d,2,false,BigInt("3f800000",16),BigInt("3b800000",16));check(d,false,Some(BigInt("3f800000",16)),Some(0))
      request(d,2,false,BigInt("3f810000",16),BigInt("3b800000",16));check(d,false,Some(BigInt("3f820000",16)),Some(0))
      for((p,m,a,b)<-Vector(
        (3,false,"3f800000","3f800000"), // unknown policy
        (1,false,"3f800000","3f800000"), // Mul policy with Add opcode
        (2,true,"3f800000","3f800000"),  // Add policy with Mul opcode
        (1,true,"3f800001","3f800000"),  // noncanonical low bits
        (1,true,"7fc00000","3f800000"),  // quiet NaN input
        (2,false,"7f800000","3f800000")  // Inf input
      )){request(d,p,m,BigInt(a,16),BigInt(b,16));check(d,true)}
      // RawFP32 addition is finite/exact but its BF16 tie rounds to infinity.
      request(d,2,false,BigInt("7f7f0000",16),BigInt("7b000000",16));check(d,true,Some(BigInt("7f800000",16)),Some(0))
      request(d,1,true,BigInt("7f7f0000",16),BigInt("40000000",16));check(d,true,Some(BigInt("7f800000",16)),Some(5))
    }
  }
}
