// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.{ByteBuffer, ByteOrder}
import java.nio.file.{Files, Paths}
import java.security.MessageDigest
import java.util.regex.Pattern

/** External actual stimuli are mandatory. Only BF16 input/weight enter DUT DDR;
  * all expected files, including inverse, are host assertions only. */
class GdnRmsNormFixedBankReplaySpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  import GdnRmsNormFixedBankReference._
  def sha(raw:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(raw).map(x=>f"${x&255}%02x").mkString
  def words(raw:Array[Byte]):Seq[BigInt]={
    require(raw.length%4==0);val b=ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
    Vector.fill(raw.length/4)(BigInt(b.getInt().toLong&0xffffffffL))
  }
  def halves(raw:Array[Byte]):Seq[Int]={
    require(raw.length%2==0);val b=ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN)
    Vector.fill(raw.length/2)(b.getShort().toInt&65535)
  }
  "GdnRmsNormFixedBankOwner" should "compute frozen actual M1 M16 and M128 with the production core services" in {
    val root=Paths.get(sys.env("HETERO_H2048_FIXTURE_ROOT"))
    val selected=sys.env("HETERO_H2048_REPLAY_TOKENS").split(",").map(_.toInt).toSeq
    require(selected.nonEmpty && selected.distinct==selected && selected.forall(Set(1,16,128)))
    val useVectorEpilogue = sys.env.getOrElse("HETERO_H2048_USE_VECTOR_EPILOGUE", "true") match {
      case "true" => true
      case "false" => false
      case other => throw new IllegalArgumentException("invalid epilogue selector: " + other)
    }
    test(new GdnRmsNormFixedBankArithmeticHarness(productionCore=true,
      useVectorEpilogue=useVectorEpilogue))
      .withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d)
      for(m<-selected){
        val directory=root.resolve(if(m==1)"h2048_borrower_replay_m1_from_m16" else s"h2048_borrower_replay_m$m")
        val manifest=Files.readAllBytes(directory.resolve("manifest.json"))
        sha(manifest) shouldBe sys.env(s"HETERO_H2048_M${m}_MANIFEST_SHA")
        val text=new String(manifest,java.nio.charset.StandardCharsets.UTF_8)
        def read(name:String):Array[Byte]={
          val entry=("(?s)\\\""+Pattern.quote(name)+"\\\"\\s*:\\s*\\{([^}]+)\\}").r
            .findFirstMatchIn(text).getOrElse(throw new IllegalArgumentException("missing fixture record "+name)).group(1)
          val length="\\\"bytes\\\"\\s*:\\s*([0-9]+)".r.findFirstMatchIn(entry).get.group(1).toInt
          val digest="\\\"sha256\\\"\\s*:\\s*\\\"([a-f0-9]{64})\\\"".r.findFirstMatchIn(entry).get.group(1)
          val raw=Files.readAllBytes(directory.resolve(name));raw.length shouldBe length;sha(raw) shouldBe digest;raw
        }
        val input=halves(read("stimulus/input.bf16le"));val weight=halves(read("stimulus/weights.bf16le"))
        input.size shouldBe m*Width;weight.size shouldBe Width
        val actualBf=halves(read("expected/output.bf16le"))
        val actualWeighted=words(read("expected/weighted.fp32le"))
        val scalarNodes=Seq("sum","mean","mean_eps","root","inverse").map(n=>n->words(read(s"expected/$n.fp32le"))).toMap
        for((row,token)<-input.grouped(Width).zipWithIndex){
          val recipe=GdnRmsNormFixedBankReference(row,weight)
          for((name,index)<-Seq("sum"->4263,"mean"->4264,"mean_eps"->4265,"root"->4266,"inverse"->4267)){
            assert(recipe.scalar(index).result==scalarNodes(name)(token),s"frozen actual $name token=$token")
          }
          val expectedWords=actualWeighted.slice(token*Width,(token+1)*Width)
          for((loan,index)<-recipe.loan.zipWithIndex){
            assert(loan.result==pack(expectedWords.slice(index*16,index*16+16),32),s"frozen actual weighted token=$token group=$index")
          }
          assert(recipe.output==actualBf.slice(token*Width,(token+1)*Width),s"frozen actual BF16 token=$token")
        }
        // Only input and weight are supplied to the memory responder in run().
        // The actual core Scalar produces inverse; expected inverse is never poked.
        val epilogue = if (useVectorEpilogue) "vector" else "scalar"
        val report=run(d,input,weight,s"frozen-actual-production-core-M$m-H2048-$epilogue-epilogue")
        report.output shouldBe actualBf
        println(s"H2048_FIXED_BANK_ACTUAL_RTL_PASS tokens=$m cycles=${report.cycles} scalar_requests=${report.scalarRequests} loans=${report.loans} reads=${report.reads} write_acks=${report.writeAcks} manifest_sha256=${sha(manifest)} core_bound=true full_block=false epilogue=$epilogue borrower_bank_bytes=6144 launch_to_done_fire_cycles=${report.launchToDoneFireCycles} sampled_cycles=${report.sampledCycles} elem_alu_execution_busy=${report.arithmeticCycles.getOrElse("elem_alu_execution_busy", 0L)} elem_alu_effective_lane=${report.arithmeticCycles.getOrElse("elem_alu_effective_lane", 0L)}")
      }
    }
  }
}
