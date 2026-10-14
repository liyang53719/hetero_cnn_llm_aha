// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.p0.LocalSramConfig
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

class ElementwiseRegisterLoanSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def bits(x: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x).toLong & 0xffffffffL)
  def fp(x: BigInt): Float = java.lang.Float.intBitsToFloat(x.toInt)
  def pack(xs: Seq[BigInt]): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) { case (a,(x,i)) => a | (x << (32*i)) }
  val one = bits(1f); val zero = BigInt(0)
  def job(d: ElementwiseMemoryEngine, opcode: Int, count: Int): Unit = {
    d.io.job.bits.op.poke(opcode.U); d.io.job.bits.tag.poke(99.U)
    d.io.job.bits.a.poke(0x1000.U); d.io.job.bits.b.poke(0x2000.U); d.io.job.bits.dst.poke(0x3000.U)
    d.io.job.bits.elementCount.poke(count.U)
    d.io.job.bits.aBf16.poke(false.B); d.io.job.bits.bBf16.poke(false.B); d.io.job.bits.dstBf16.poke(false.B)
  }
  "ElementwiseRegisterLoan" should "use the existing sixteen ALUs with RNE, exclusive leases, stable retirement and measured edges" in {
    test(new ElementwiseRegisterLoan(ChainConfig(tileElements=32),LocalSramConfig(addressBits=3,rowsPerBank=2)))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      d.clock.setTimeout(10000)
      d.io.job.valid.poke(false.B); job(d,ElemOp.Copy,0); d.io.done.ready.poke(false.B)
      d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
      d.io.response.bits.tag.poke(0.U);d.io.response.bits.data.poke(0.U);d.io.response.bits.error.poke(false.B)
      d.loan.request.valid.poke(false.B);d.loan.result.ready.poke(false.B)
      d.loan.abort.poke(false.B);d.loan.resetLoan.poke(false.B)
      d.loan.request.bits.tag.poke(0.U);d.loan.request.bits.op.poke(0.U)
      d.loan.request.bits.a.poke(0.U);d.loan.request.bits.b.poke(0.U);d.loan.request.bits.inverse.poke(one.U)
      var edge=0;var tag=1;var checked=0
      def step(n:Int=1):Unit={require(n>=0);if(n>0)d.clock.step(n);edge+=n}
      def offer(op:Int,aa:Seq[BigInt],bb:Seq[BigInt],inverse:BigInt=one):Int={
        d.loan.request.bits.tag.poke(tag.U);d.loan.request.bits.op.poke(op.U)
        d.loan.request.bits.a.poke(pack(aa).U);d.loan.request.bits.b.poke(pack(bb).U);d.loan.request.bits.inverse.poke(inverse.U)
        d.loan.request.valid.poke(true.B);d.loan.request.ready.expect(true.B)
        val accepted=edge;step();d.loan.request.valid.poke(false.B)
        d.loan.request.bits.tag.poke(0xbadcafe.U);d.loan.request.bits.a.poke(0.U);d.loan.request.bits.b.poke(0.U);d.loan.request.bits.inverse.poke(0.U)
        accepted
      }
      def awaitResult():Unit={var n=0;while(!d.loan.result.valid.peek().litToBoolean&&n<8){step();n+=1};assert(n<8)}
      def retire(status:Int,expected:Seq[BigInt],hold:Int=0):Int={
        awaitResult();val first=edge
        d.loan.result.bits.tag.expect(tag.U);d.loan.result.bits.status.expect(status.U)
        d.loan.result.bits.value.expect((if(status==0)pack(expected)else BigInt(0)).U)
        for(_<-0 until hold){
          d.io.job.valid.poke(true.B);d.io.job.ready.expect(false.B);d.loan.request.ready.expect(false.B)
          d.io.memory.valid.expect(false.B);step()
          d.loan.result.valid.expect(true.B);d.loan.result.bits.tag.expect(tag.U)
          d.loan.result.bits.status.expect(status.U);d.loan.result.bits.value.expect((if(status==0)pack(expected)else BigInt(0)).U)
        }
        d.io.job.valid.poke(false.B);d.loan.result.ready.poke(true.B);step();d.loan.result.ready.poke(false.B)
        if(status!=0){
          d.loan.resetRequired.expect(true.B);d.loan.request.ready.expect(false.B)
          d.loan.resetLoan.poke(true.B);step();d.loan.resetLoan.poke(false.B)
          d.loan.resetRequired.expect(false.B)
        }
        d.loan.request.ready.expect(true.B);tag+=1;checked+=16;first
      }
      val aa=Seq(bits(0f),BigInt("80000000",16),bits(1f),bits(-1f),bits(0.25f),bits(-3.5f),BigInt("00800000",16),BigInt("3f800001",16))++Seq.tabulate(8)(i=>bits(i.toFloat/8f))
      val bb=Seq.tabulate(16)(i=>bits((i-8).toFloat/16f))
      for(op<-Seq(ElementwiseLoanOp.Add,ElementwiseLoanOp.MulIeeeRne)){
        val start=offer(op,aa,bb)
        val expected=aa.zip(bb).map{case(a,b)=>bits(if(op==ElementwiseLoanOp.Add)(fp(a)+fp(b)).toFloat else (fp(a)*fp(b)).toFloat)}
        val first=retire(0,expected,3);assert(first-start==2,s"primitive accept-to-earliest-retirement ${first-start}")
      }
      var primitiveStart = -1
      for(_<-0 until 2){
        val start=offer(ElementwiseLoanOp.Add,aa,bb)
        if(primitiveStart>=0)assert(start-primitiveStart==3,s"primitive initiation interval ${start-primitiveStart}")
        retire(0,aa.zip(bb).map{case(a,b)=>bits((fp(a)+fp(b)).toFloat)});primitiveStart=start
      }
      var lastStart = -1
      for(batch<-0 until 3){
        val inverse=bits(0.75f);val start=offer(ElementwiseLoanOp.RmsEpilogue,aa,bb,inverse)
        if(lastStart>=0)assert(start-lastStart==5,s"RMS initiation interval ${start-lastStart}")
        val expected=aa.zip(bb).map{case(a,w)=>bits(((fp(a)*fp(inverse)).toFloat*(1f+fp(w)).toFloat).toFloat)}
        val first=retire(0,expected);assert(first-start==4,s"RMS accept-to-earliest-retirement ${first-start}");lastStart=start
      }
      // An actual inexact subnormal multiply: strict legacy rejects, op6 preserves it.
      val tiny=Seq.fill(16)(BigInt("00800000",16));val third=Seq.fill(16)(BigInt("3eaaaaab",16))
      offer(ElementwiseLoanOp.Mul,tiny,third);retire(Status.Numerical,Nil)
      offer(ElementwiseLoanOp.MulIeeeRne,tiny,third)
      retire(0,tiny.zip(third).map{case(a,b)=>bits((fp(a)*fp(b)).toFloat)})
      for((x,y)<-Seq((BigInt("7f7fffff",16),bits(2f)),(BigInt("7f800000",16),zero),(BigInt("7fc12345",16),one))){
        offer(ElementwiseLoanOp.MulIeeeRne,Seq.fill(16)(x),Seq.fill(16)(y));retire(Status.Numerical,Nil)
      }
      // Finite underflow is retained in BOTH RMS multiply phases.
      for((xs,ws,inv)<-Seq((Seq.fill(16)(BigInt("00800000",16)),Seq.fill(16)(zero),BigInt("3eaaaaab",16)),
          (Seq.fill(16)(BigInt("00800000",16)),Seq.fill(16)(bits(-0.75f)),BigInt("3f800001",16)))){
        offer(ElementwiseLoanOp.RmsEpilogue,xs,ws,inv)
        val expected=xs.zip(ws).map{case(a,w)=>bits(((fp(a)*fp(inv)).toFloat*(1f+fp(w)).toFloat).toFloat)}
        retire(0,expected)
      }
      // Bad first/middle/final RMS stage; one bad lane poisons the complete vector.
      val max=BigInt("7f7fffff",16)
      for((xs,ws,inv)<-Seq((Seq.fill(16)(max),Seq.fill(16)(zero),bits(2f)),
          (aa,bb.updated(9,BigInt("7f800000",16)),one),
          (Seq.fill(16)(bits(2f)),Seq.fill(16)(max),one))){
        offer(ElementwiseLoanOp.RmsEpilogue,xs,ws,inv);retire(Status.Numerical,Nil)
      }
      offer(0,aa,bb);retire(Status.Unsupported,Nil)
      // Cancellation during each live compute stage retains a terminal, then needs reset.
      for(delay<-0 until 3){
        offer(ElementwiseLoanOp.RmsEpilogue,aa,bb);step(delay)
        d.loan.abort.poke(true.B);d.loan.result.valid.expect(false.B);step();d.loan.abort.poke(false.B)
        retire(ElementwiseLoanOp.Aborted,Nil)
      }
      offer(ElementwiseLoanOp.Add,aa,bb);awaitResult()
      d.loan.result.ready.poke(true.B);d.loan.resetLoan.poke(true.B)
      d.loan.result.valid.expect(false.B);step();d.loan.resetLoan.poke(false.B);d.loan.result.ready.poke(false.B)
      retire(ElementwiseLoanOp.Aborted,Nil,2)
      // Normal DDR Add/Mul must still work after register loans used every bank register.
      for(op<-Seq(ElemOp.Add,ElemOp.Mul)){
        val xs=Seq.tabulate(16)(i=>bits(1f+i.toFloat/4f));val ys=Seq.tabulate(16)(i=>bits(2f+i.toFloat/16f))
        val expected=pack(xs.zip(ys).map{case(x,y)=>bits(if(op==ElemOp.Add)(fp(x)+fp(y)).toFloat else (fp(x)*fp(y)).toFloat)})
        job(d,op,16);d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);step();d.io.job.valid.poke(false.B)
        var reads=0;var writes=0;var guard=0
        while(!d.io.done.valid.peek().litToBoolean && guard<200){
          if(d.io.memory.valid.peek().litToBoolean){
            val write=d.io.memory.bits.write.peek().litToBoolean;val address=d.io.memory.bits.address.peek().litValue
            val mt=d.io.memory.bits.tag.peek().litValue
            val response=if(write){d.io.memory.bits.data.expect(expected.U);d.io.memory.bits.mask.expect(((BigInt(1)<<64)-1).U);address shouldBe BigInt(0x3000);writes+=1;BigInt(0)}
              else{reads+=1;if(address==0x1000)pack(xs)else{address shouldBe BigInt(0x2000);pack(ys)}}
            d.io.memory.ready.poke(true.B);step();d.io.memory.ready.poke(false.B)
            d.io.response.bits.tag.poke(mt.U);d.io.response.bits.data.poke(response.U);d.io.response.bits.error.poke(false.B)
            d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);step();d.io.response.valid.poke(false.B)
          }else step()
          guard+=1
        }
        assert(guard<200);reads shouldBe 2;writes shouldBe 1
        d.io.done.bits.status.expect(Status.Ok.U);d.io.done.bits.writeBytes.expect(64.U)
        d.io.done.ready.poke(true.B);step();d.io.done.ready.poke(false.B);d.loan.request.ready.expect(true.B)
      }
      // Same-edge arbitration: malformed DDR job wins, loan reset cannot unlock its poison.
      job(d,ElemOp.Copy,0);d.io.job.valid.poke(true.B);d.loan.request.valid.poke(true.B)
      d.io.job.ready.expect(true.B);d.loan.request.ready.expect(false.B);step()
      d.io.job.valid.poke(false.B);d.loan.request.valid.poke(false.B)
      d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(Status.Unsupported.U)
      d.loan.resetLoan.poke(true.B);step();d.loan.resetLoan.poke(false.B);d.io.done.valid.expect(true.B)
      d.io.done.ready.poke(true.B);step();d.io.done.ready.poke(false.B)
      d.loan.resetLoan.poke(true.B);step();d.loan.resetLoan.poke(false.B);d.loan.request.ready.expect(false.B)
      // Coordinated global reset is legal here: no external request has been accepted.
      d.reset.poke(true.B);step(2);d.reset.poke(false.B);step();d.loan.request.ready.expect(true.B)
      // An offered and then accepted DDR read excludes the loan through response drain.
      job(d,ElemOp.Copy,16);d.io.job.valid.poke(true.B);step();d.io.job.valid.poke(false.B)
      d.io.memory.valid.expect(true.B);val memoryTag=d.io.memory.bits.tag.peek().litValue
      for(_<-0 until 3){d.loan.request.valid.poke(true.B);d.loan.request.ready.expect(false.B);step()}
      d.loan.request.valid.poke(false.B);d.io.memory.ready.poke(true.B);step();d.io.memory.ready.poke(false.B)
      d.loan.resetLoan.poke(true.B);step();d.loan.resetLoan.poke(false.B);d.io.response.ready.expect(true.B)
      d.loan.request.ready.expect(false.B)
      d.io.response.bits.tag.poke(memoryTag.U);d.io.response.bits.error.poke(true.B);d.io.response.valid.poke(true.B);step();d.io.response.valid.poke(false.B)
      d.io.done.bits.status.expect(Status.Memory.U);d.io.done.ready.poke(true.B);step();d.io.done.ready.poke(false.B)
      d.loan.resetLoan.poke(true.B);step();d.loan.resetLoan.poke(false.B);d.loan.request.ready.expect(false.B)
      println(s"ELEMENTWISE_REGISTER_LOAN_RTL_PASS checked_lanes=$checked primitive_earliest_retirement_edges=2 rms_earliest_retirement_edges=4 rms_II=5 clocks=$edge local_scope_only=true")
    }
  }
  it should "retain the production ALU and wide-storage inventory during elaboration" in {
    val out=Paths.get("../../work/elementwise_register_loan_rtl");Files.createDirectories(out)
    val base=circt.stage.ChiselStage.emitCHIRRTL(new ElementwiseMemoryEngine())
    val loan=circt.stage.ChiselStage.emitCHIRRTL(new ElementwiseRegisterLoan())
    Files.writeString(out.resolve("baseline.fir"),base);Files.writeString(out.resolve("loan.fir"),loan)
    def instances(s:String)=s.linesIterator.count(x=>x.contains("inst ")&&x.contains(" of HeteroFP32Alu"))
    instances(base) shouldBe 16;instances(loan) shouldBe 16
    def wide(s:String)=s.linesIterator.filter(x=>(x.trim.startsWith("reg ")||x.trim.startsWith("regreset "))&&x.contains("UInt<512>")).map(_.trim.takeWhile(_!='@')).toSeq.sorted
    wide(loan) shouldBe wide(base)
    def memories(s:String)=s.linesIterator.filter(_.trim.startsWith("smem ")).map(_.trim.takeWhile(_!='@')).toSeq.sorted
    memories(loan) shouldBe memories(base); memories(loan).size shouldBe 16
    def registers(s:String)=s.linesIterator.filter(x=>x.trim.startsWith("reg ")||x.trim.startsWith("regreset ")).map(_.trim.takeWhile(_!='@')).toSeq
    registers(base).diff(registers(loan)) shouldBe empty
    val added=registers(loan).diff(registers(base))
    added.size shouldBe 2
    added.forall(x=>x.startsWith("regreset loanState : UInt<3>")||x.startsWith("regreset loanPoison : UInt<1>")) shouldBe true
    val rtl=circt.stage.ChiselStage.emitSystemVerilog(new ElementwiseRegisterLoan())
    Files.writeString(out.resolve("ElementwiseRegisterLoan.sv"),rtl)
    println(s"ELEMENTWISE_REGISTER_LOAN_RESOURCE_PASS alus=16 baseline_wide_regs=${wide(base).size} loan_wide_regs=${wide(loan).size} generated_rtl=true")
  }
}
