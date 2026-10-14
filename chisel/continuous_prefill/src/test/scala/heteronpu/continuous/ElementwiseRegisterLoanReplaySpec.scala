// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import heteronpu.p0.LocalSramConfig
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.{ByteBuffer, ByteOrder}
import java.nio.file.{Files, Paths, Path}
import java.security.MessageDigest
import java.util.regex.Pattern

/** Only adds combinational final BF16 RNE observation to the production loan. */
class ElementwiseLoanReplayTop extends ElementwiseRegisterLoan(
    ChainConfig(tileElements=32),LocalSramConfig(addressBits=3,rowsPerBank=2)) {
  val bf16 = IO(Output(UInt(256.W)))
  bf16 := Cat((0 until 16).reverse.map(i=>TensorMath.bf16Rne(loan.result.bits.value(32*i+31,32*i))))
}

/** Explicit opt-in real-operand test; absent inputs fail, never silently skip.
  * Run separately from the no-checkpoint synthetic boundary suite.
  */
class ElementwiseRegisterLoanReplaySpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  def words(b:Array[Byte]):Array[BigInt]={val r=ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN);Array.fill(b.length/4)(BigInt(r.getInt().toLong&0xffffffffL))}
  def shorts(b:Array[Byte]):Array[BigInt]={val r=ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN);Array.fill(b.length/2)(BigInt(r.getShort().toInt&65535))}
  def pack(xs:Seq[BigInt],width:Int):BigInt=xs.zipWithIndex.foldLeft(BigInt(0)){case(a,(x,i))=>a|(x<<(width*i))}
  "ElementwiseRegisterLoan" should "replay frozen actual M16 and M128 postnorm observations bit exactly" in {
    val root=Paths.get(sys.env("HETERO_RMS_LOAN_FIXTURE_ROOT"))
    val reports=scala.collection.mutable.ArrayBuffer.empty[String]
    test(new ElementwiseLoanReplayTop).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      d.clock.setTimeout(200000)
      d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
      d.io.job.bits.op.poke(0.U);d.io.job.bits.tag.poke(0.U);d.io.job.bits.elementCount.poke(0.U)
      d.io.job.bits.a.poke(0.U);d.io.job.bits.b.poke(0.U);d.io.job.bits.dst.poke(0.U)
      d.io.job.bits.aBf16.poke(false.B);d.io.job.bits.bBf16.poke(false.B);d.io.job.bits.dstBf16.poke(false.B)
      d.io.response.bits.tag.poke(0.U);d.io.response.bits.data.poke(0.U);d.io.response.bits.error.poke(false.B)
      d.loan.abort.poke(false.B);d.loan.resetLoan.poke(false.B);d.loan.request.valid.poke(false.B);d.loan.result.ready.poke(false.B)
      for(m<-Seq(16,128)){
        val directory=root.resolve(s"rms_loan_fixture_m$m")
        val manifest=Files.readAllBytes(directory.resolve("manifest.json"));val identity=sha(manifest)
        identity shouldBe sys.env(s"HETERO_RMS_LOAN_M${m}_MANIFEST_SHA")
        val text=new String(manifest,java.nio.charset.StandardCharsets.UTF_8)
        def read(name:String):Array[Byte]={
          val regex=("(?s)\\\""+Pattern.quote(name)+"\\\"\\s*:\\s*\\{\\s*\\\"bytes\\\"\\s*:\\s*([0-9]+),\\s*\\\"sha256\\\"\\s*:\\s*\\\"([a-f0-9]{64})\\\"").r
          val found=regex.findFirstMatchIn(text).getOrElse(throw new IllegalArgumentException("manifest record "+name))
          val raw=Files.readAllBytes(directory.resolve(name));raw.length shouldBe found.group(1).toInt;sha(raw) shouldBe found.group(2);raw
        }
        val x=words(read("x.fp32le"));val w=words(read("weights.fp32le"));val inv=words(read("inverse.fp32le"))
        val expected=words(read("expected.fp32le"));val expectedBf=shorts(read("expected.bf16le"))
        x.length shouldBe m*2048;w.length shouldBe 2048;inv.length shouldBe m
        expected.length shouldBe x.length;expectedBf.length shouldBe x.length
        var transactions=0;var clocks=0
        for(token<-0 until m; col<-0 until 2048 by 16){
          val offset=token*2048+col;val tag=transactions+1
          d.loan.request.bits.tag.poke(tag.U);d.loan.request.bits.op.poke(ElementwiseLoanOp.RmsEpilogue.U)
          d.loan.request.bits.a.poke(pack(x.slice(offset,offset+16).toSeq,32).U)
          d.loan.request.bits.b.poke(pack(w.slice(col,col+16).toSeq,32).U);d.loan.request.bits.inverse.poke(inv(token).U)
          d.loan.request.valid.poke(true.B);d.loan.request.ready.expect(true.B);d.clock.step();clocks+=1
          d.loan.request.valid.poke(false.B);d.loan.result.valid.expect(false.B)
          d.io.job.ready.expect(false.B);d.io.memory.valid.expect(false.B)
          d.clock.step(3);clocks+=3
          d.loan.result.valid.expect(true.B);d.loan.result.bits.tag.expect(tag.U);d.loan.result.bits.status.expect(Status.Ok.U)
          d.loan.result.bits.value.expect(pack(expected.slice(offset,offset+16).toSeq,32).U)
          d.bf16.expect(pack(expectedBf.slice(offset,offset+16).toSeq,16).U)
          d.loan.result.ready.poke(true.B);d.clock.step();clocks+=1;d.loan.result.ready.poke(false.B)
          d.loan.resetRequired.expect(false.B);transactions+=1
        }
        transactions shouldBe m*128;clocks shouldBe transactions*5
        val report=s"""{"tokens":$m,"transactions":$transactions,"fp32_values":${m*2048},"bf16_values":${m*2048},"vector_primitive_issues":${transactions*3},"clock_edges":$clocks,"request_interval":5,"manifest_sha256":"$identity","rtl_executed":true,"full_block":false,"local_ideal_supply_only":true}"""
        reports+=report;println("RMS_EPILOGUE_ACTUAL_RTL_REPLAY_PASS "+report)
      }
    }
    Files.writeString(root.resolve("rms_loan_rtl_replay_results.json"),reports.mkString("[\n",",\n","\n]\n"))
  }
}
