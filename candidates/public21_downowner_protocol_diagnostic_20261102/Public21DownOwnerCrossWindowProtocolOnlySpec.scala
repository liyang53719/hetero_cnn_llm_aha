// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}
import java.security.MessageDigest
import scala.collection.mutable

/** UNRUN B: actual DownOwner/banks + actual Router/Coordinator/SumBridge.
  * MatrixStream, DDR bytes and vector Add results are MOCK ZERO protocol traffic.
  * No actual arithmetic, Matrix endpoint or whole-block qualification claimed.
  */
class Public21DownOwnerCrossWindowProtocolOnlySpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case v:Vec[_]=>v.foreach(zero);case r:Record=>r.elements.values.foreach(zero);case _=>fail("unknown input")}
  val path=Paths.get(sys.env.getOrElse("P0_CLOSED_PROGRAM_MANIFEST",throw new IllegalArgumentException("closed P0 metadata required")))
  val raw=Files.readAllBytes(path)
  val digest=MessageDigest.getInstance("SHA-256").digest(raw).map(x=>f"${x&255}%02x").mkString
  require(digest==sys.env.getOrElse("P0_CLOSED_PROGRAM_MANIFEST_SHA256",""),"independent manifest pin")
  val manifest=ujson.read(new String(raw,java.nio.charset.StandardCharsets.UTF_8))
  def integer(v:ujson.Value):BigInt={val n=v.num;require(n>=0 && n<9007199254740992.0 && n==math.floor(n));BigInt(n.toLong)}
  require(integer(manifest("tokens"))==128 && integer(manifest("shape")("H"))==1536 && integer(manifest("commands"))==21)
  def address(k:String):BigInt={val t=manifest("tensors")(k);require(t("dims").arr.map(integer).toSeq==Seq(if(k=="wq")BigInt(1536)else BigInt(128),BigInt(1536)));integer(t("address"))}
  val inputAddress=address("n0");val weightAddress=address("wq");val outputAddress=address("q")
  def run(d:Public21DownOwnerProtocolHarness):Unit={
    val p=d.io;println("B_SIM_READY control_only=true actual_banks=true mock_matrix=true")
    p.job.valid.poke(false.B);zero(p.job.bits);p.done.ready.poke(false.B)
    p.memory.ready.poke(false.B);p.response.valid.poke(false.B);zero(p.response.bits)
    p.burst.ready.poke(false.B);p.burstResponse.valid.poke(false.B);zero(p.burstResponse.bits)
    p.writeRequest.ready.poke(false.B);p.writeData.ready.poke(false.B);p.writeResponse.valid.poke(false.B);zero(p.writeResponse.bits)
    p.matrix.group.ready.poke(false.B);p.matrix.step.ready.poke(false.B);p.matrix.result.valid.poke(false.B);zero(p.matrix.result.bits);p.matrix.done.valid.poke(false.B);zero(p.matrix.done.bits)
    p.matrix.seed.get.begin.ready.poke(false.B);p.matrix.seed.get.beat.ready.poke(false.B);p.matrix.seed.get.ack.valid.poke(false.B);zero(p.matrix.seed.get.ack.bits)
    p.vector.request.ready.poke(false.B);p.vector.result.valid.poke(false.B);zero(p.vector.result.bits)
    p.vector.busy.poke(false.B);p.vector.drained.poke(true.B);p.vector.resetRequired.poke(false.B)
    p.backendReset.poke(false.B);p.abort.poke(false.B)
    // Explicit synthetic disjoint prefix metadata. This K<=splitK recipe must
    // never request seed/prefix traffic; it is NOT an actual workspace replay.
    zero(p.prefixWorkspace);p.prefixWorkspace.valid.poke(true.B);p.prefixWorkspace.base.poke("h200000000".U)
    p.prefixWorkspace.extent.poke(786432.U);p.prefixWorkspace.generation.poke(1.U);p.prefixWorkspace.splitK.poke(1536.U)
    val j=p.job.bits;j.kind.poke(QwenOwnerKind.Dense.U);j.tag.poke(1.U)
    j.m.poke(128.U);j.n.poke(1536.U);j.k.poke(1536.U);j.a.poke(inputAddress.U);j.b.poke(weightAddress.U);j.dst.poke(outputAddress.U)
    j.weightBf16.poke(true.B);j.public21Reduction.poke(true.B);j.writeBytes.poke(786432.U)
    // tag1/identity2 are fixture identities, not an observed Guard-tag replay.
    p.job.ready.expect(true.B);p.job.valid.poke(true.B);d.clock.step();p.job.valid.poke(false.B)
    var ticks=0;var windows=0;var returnedWindows=0;var drains=0;var vectors=0
    var reads=0;var readPending:Option[BigInt]=None
    case class Write(tag:BigInt,beats:Int,var received:Int=0)
    var writePending:Option[Write]=None
    var groupActive=false;var groupTag=BigInt(0);var groupSequence=BigInt(0);var lastGroupSequence=BigInt(0)
    var steps=0;var length=0;var terminalReturns=0;var finishSeen=false;var mockCompletionClosed=false;var groups=0
    val results=mutable.Queue[Int]() // bounded two terminal contexts, values fixed finite zeros
    var vectorPending=false
    def checkpoint(label:String):Unit={
      val q=d.diagnostic
      println(s"$label tick=$ticks windows=$returnedWindows group=$groupSequence steps=$steps reset=${p.resetRequired.peek().litToBoolean} status=${q.status.peek().litValue} firstStatus=${q.firstStatus.peek().litValue} state=${q.state.peek().litValue} bankReset=${q.bankReset.peek().litToBoolean} firstBankReset=${q.firstBankReset.peek().litToBoolean} terminalIssued=${q.terminalIssued.peek().litValue} captured=${q.captured.peek().litValue} written=${q.written.peek().litValue} ng=${q.nBase.peek().litValue} ownerGroupSequence=${q.groupSequence.peek().litValue}")
    }
    while(returnedWindows<3 && ticks<500000){
      // Current fields matter: first-fault registers may update next edge.
      if(p.resetRequired.peek().litToBoolean)checkpoint("B_FAULT_BEFORE_ASSERT")
      else if(ticks%20000==0)checkpoint("B_BOUNDED_PROGRESS")
      p.resetRequired.expect(false.B);p.done.valid.expect(false.B);p.reductionOwns.expect(true.B)
      p.memory.valid.expect(false.B) // no prefix or scalar memory in this selected recipe
      p.matrix.seed.get.begin.valid.expect(false.B);p.matrix.seed.get.beat.valid.expect(false.B)
      p.burst.ready.poke(readPending.isEmpty.B)
      p.burstResponse.valid.poke(readPending.nonEmpty.B);p.burstResponse.bits.tag.poke(readPending.getOrElse(BigInt(0)).U);p.burstResponse.bits.last.poke(true.B)
      p.writeRequest.ready.poke(writePending.isEmpty.B)
      p.writeData.ready.poke(writePending.exists(w=>w.received<w.beats).B)
      p.writeResponse.valid.poke(writePending.exists(w=>w.received==w.beats).B);p.writeResponse.bits.tag.poke(writePending.map(_.tag).getOrElse(BigInt(0)).U)
      p.matrix.group.ready.poke((!groupActive).B)
      p.matrix.step.ready.poke((groupActive && !finishSeen && results.size<2).B)
      p.matrix.result.valid.poke(results.nonEmpty.B);p.matrix.result.bits.context.poke(results.headOption.getOrElse(0).U);p.matrix.result.bits.last.poke(true.B)
      // MatrixPipeline.scala:63,260-264: completion + empty result FIFO,
      // NOT owner written/tile retirement. Mock completion closes when its
      // final accepted step produces the last terminal response. Offer done
      // immediately after all five real result fires, including tile overlap.
      val canDone=groupActive && finishSeen && mockCompletionClosed && results.isEmpty && terminalReturns==5
      p.matrix.done.valid.poke(canDone.B);p.matrix.done.bits.tag.poke(groupTag.U)
      p.vector.request.ready.poke((!vectorPending).B);p.vector.result.valid.poke(vectorPending.B)
      p.vector.busy.poke(vectorPending.B);p.vector.drained.poke((!vectorPending).B)
      def fire(x:chisel3.util.DecoupledIO[_]):Boolean=x.valid.peek().litToBoolean && x.ready.peek().litToBoolean
      val readFire=fire(p.burst);val readReturn=fire(p.burstResponse)
      val wrFire=fire(p.writeRequest);val wdFire=fire(p.writeData);val waFire=fire(p.writeResponse)
      val groupFire=fire(p.matrix.group);val stepFire=fire(p.matrix.step);val resultFire=fire(p.matrix.result);val doneFire=fire(p.matrix.done)
      val vectorFire=fire(p.vector.request);val vectorReturn=fire(p.vector.result)
      val readTag=if(readFire)p.burst.bits.tag.peek().litValue else BigInt(0)
      val writeTag=if(wrFire)p.writeRequest.bits.tag.peek().litValue else BigInt(0)
      val writeBeats=if(wrFire)p.writeRequest.bits.beats.peek().litValue.toInt else 0
      if(readFire){p.burst.bits.beats.expect(1.U);val addr=p.burst.bits.address.peek().litValue
        require((addr>=inputAddress && addr<inputAddress+786432)||(addr>=weightAddress && addr<weightAddress+4718592),"mock DDR read outside exact A/W spans")}
      if(wdFire){val w=writePending.get;p.writeData.bits.last.expect((w.received+1==w.beats).B)}
      if(p.windowAccepted.valid.peek().litToBoolean){
        val q=p.windowAccepted.bits;q.ng.expect((if(windows<2)0 else 160).U);q.slot.expect((if(windows==1)1 else 0).U)
        q.cols.expect(160.U);q.job.m.expect(128.U);q.job.n.expect(1536.U);q.job.k.expect(1536.U)
        q.kWindow.get.begin.expect((if(windows==1)1024 else 0).U);q.kWindow.get.end.expect((if(windows==1)1536 else 1024).U);q.kWindow.get.pairReverse.expect(true.B)
        q.reuseA.expect((windows!=0).B);windows+=1
        println(s"B_WINDOW_ACCEPTED ordinal=$windows tick=$ticks ng=${q.ng.peek().litValue} slot=${q.slot.peek().litValue}")
      }
      if(groupFire){
        require(!groupActive && results.isEmpty);p.matrix.group.bits.tag.expect(1.U);p.matrix.group.bits.sliceMask.expect(255.U);p.matrix.group.bits.transposedDense.get.expect(true.B)
        groupTag=p.matrix.group.bits.tag.peek().litValue;groupSequence=p.matrix.group.bits.groupSequence.get.peek().litValue
        require(groupSequence>lastGroupSequence,"actual owner groupSequence must advance");lastGroupSequence=groupSequence
        length=if(groups==1)512 else 1024;steps=0;terminalReturns=0;finishSeen=false;mockCompletionClosed=false;groups+=1
      }
      var newResult:Option[Int]=None
      if(stepFire){
        val x=p.matrix.step.bits;val context=steps%5;val k=steps/5
        x.context.expect(context.U);x.clear.expect((k==0).B);x.last.expect((k+1==length).B);x.emit.expect((k+1==length).B);x.finish.expect((k+1==length && context==4).B)
        require(k<length,"no extra Matrix step after K range")
        if(x.last.peek().litToBoolean)newResult=Some(context)
        if(x.finish.peek().litToBoolean)finishSeen=true
      }
      if(resultFire){require(results.head==terminalReturns,"ordered mock terminal contexts");d.diagnostic.terminalIssued.peek().litValue.testBit(results.head) shouldBe true}
      if(doneFire){steps shouldBe length*5;terminalReturns shouldBe 5;d.diagnostic.captured.expect(5.U)}
      if(vectorFire){p.vector.request.bits.binaryAdd.get.expect(true.B);vectors+=1}
      if(p.windowReturned.valid.peek().litToBoolean){
        val r=p.windowReturned.bits;r.status.expect(0.U);r.committed.expect(true.B);r.producedBeats.expect(1280.U);r.ddrWriteBytes.expect(0.U)
        r.ng.expect((if(returnedWindows<2)0 else 160).U);r.slot.expect((if(returnedWindows==1)1 else 0).U)
        returnedWindows+=1
        println(s"B_WINDOW_TERMINAL ordinal=$returnedWindows tick=$ticks group=$groupSequence issued=$steps captured=${d.diagnostic.captured.peek().litValue} written=${d.diagnostic.written.peek().litValue} status=0 mock_matrix=true")
      }
      if(p.drainReturned.valid.peek().litToBoolean){val r=p.drainReturned.bits;r.status.expect(0.U);r.ng.expect(0.U);r.ddrWriteBytes.expect(81920.U);r.consumedBeats.expect(1280.U);drains+=1}
      d.clock.step();ticks+=1
      if(readReturn)readPending=None
      if(readFire){readPending=Some(readTag);reads+=1}
      if(waFire)writePending=None
      if(wrFire)writePending=Some(Write(writeTag,writeBeats))
      if(wdFire)writePending.get.received+=1
      if(groupFire)groupActive=true
      if(resultFire){results.dequeue();terminalReturns+=1}
      newResult.foreach { context =>
        results.enqueue(context)
        if(context==4 && finishSeen)mockCompletionClosed=true
      }
      if(stepFire)steps+=1
      if(doneFire)groupActive=false
      if(vectorReturn)vectorPending=false
      if(vectorFire)vectorPending=true
    }
    returnedWindows shouldBe 3;windows shouldBe 3;groups shouldBe 3;drains shouldBe 1;vectors shouldBe 1280
    p.resetRequired.expect(false.B);d.diagnostic.firstStatus.expect(0.U);d.diagnostic.firstBankReset.expect(false.B)
    println(s"B_PROTOCOL_BOUNDARY_ONLY windows=$returnedWindows drains=$drains reads=$reads ticks=$ticks numerical=false full_block=false matrix_endpoint_mock=true")
  }
  "Real selected DownOwner and banks with mock Matrix service" should "reach ng160 first-partial terminal without inventing done" in {
    println("B_BEFORE_ELAB real_banks=true matrix4096=false")
    test(new Public21DownOwnerProtocolHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>run(d)}
  }
}
