package heteronpu.p0
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.util.Random

class Group8SchedulerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:Group8Scheduler):Unit={
    d.io.start.poke(false.B);d.io.command.poke(0xabc.U);d.io.traceOnly.poke(false.B);d.io.batches.poke(1.U)
    d.io.contextValid.poke(false.B);d.io.contextLegal.poke(true.B);d.io.contextStatus.poke(0.U)
    d.io.addresses.poke((BigInt(0x10000000)|(BigInt(0x20000000)<<56)|(BigInt(0x30000000)<<112)).U)
    d.io.columns.poke(256.U);d.io.weightStride.poke(512.U);d.io.tiles.poke(8.U);d.io.contextFp32.poke(false.B)
    d.io.normDone.poke(false.B);d.io.normStatus.poke(0.U);d.io.normBytes.poke(49152.U)
    d.io.payloadDone.poke(false.B);d.io.payloadStatus.poke(0.U);d.io.payloadSteps.poke(1536.U)
    d.io.matrixCmdReady.poke(false.B);d.io.matrixCompletion.poke(false.B);d.io.matrixStatus.poke(0.U);d.io.matrixError.poke(false.B)
    d.io.dmaReady.poke(false.B);d.io.dmaResponse.poke(false.B);d.io.dmaError.poke(false.B)
  }
  def run(d:Group8Scheduler,tiles:Int,batches:Int,fp32:Boolean=false,fault:String="",seed:Int=17):Unit={
    init(d);d.clock.setTimeout(100000);d.io.tiles.poke(tiles.U);d.io.columns.poke((tiles*32).U);d.io.weightStride.poke((tiles*64).U)
    d.io.batches.poke(batches.U);d.io.contextFp32.poke(fp32.B)
    d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B);d.io.command.poke(0x999.U)
    val rng=new Random(seed);var desc = -1;var nd = -1;var pd = -1;var dd = -1;var cmdWait=4
    var dmaErr=false;var normErr=false;var payloadErr=false;var finalPay=false
    var weights=0;var stores=0;var norms=0;var pays=0;var commands=0;var cycles=0;var lastStoreAck=false
    var heldDma:Option[(BigInt,BigInt,BigInt,BigInt)]=None
    while(!d.io.done.peek().litToBoolean && cycles<100000){
      val cr=cmdWait==0; if(cmdWait>0)cmdWait-=1
      d.io.matrixCmdReady.poke(cr.B);val dr=rng.nextInt(3)!=0;d.io.dmaReady.poke(dr.B)
      d.io.contextValid.poke((desc==0).B);d.io.contextLegal.poke((fault!="descriptor").B);d.io.contextStatus.poke((if(fault=="descriptor")2 else 0).U)
      d.io.normDone.poke((nd==0).B);d.io.normStatus.poke((if(normErr)3 else 0).U)
      d.io.payloadDone.poke((pd==0).B);d.io.payloadStatus.poke((if(payloadErr)5 else 0).U)
      d.io.dmaResponse.poke((dd==0).B);d.io.dmaError.poke(dmaErr.B)
      d.io.matrixCompletion.poke((pd==0 && finalPay && !payloadErr).B)
      d.io.matrixStatus.poke((if(fault=="matrix_completion" && pd==0 && finalPay)7 else 0).U)
      d.io.heldCommand.expect(0xabc.U)
      if(d.io.descriptorStart.peek().litToBoolean)desc=2
      if(d.io.matrixCmdValid.peek().litToBoolean){desc should be < 0; if(cr)commands+=1}
      if(d.io.normStart.peek().litToBoolean){norms+=1;nd=3;normErr=fault=="norm"}
      if(d.io.payloadStart.peek().litToBoolean){pays+=1;pd=5;payloadErr=fault=="payload";finalPay=d.io.lastTile.peek().litToBoolean}
      if(d.io.dmaValid.peek().litToBoolean){
        val tuple=(d.io.dmaSource.peek().litValue,d.io.dmaDestination.peek().litValue,d.io.dmaRowBytes.peek().litValue,d.io.dmaRows.peek().litValue)
        heldDma.foreach(_ shouldBe tuple)
        if(dr){
          if(d.io.dmaKind.peek().litValue==1){weights+=1;tuple._2 shouldBe BigInt(0xa0000);tuple._4 shouldBe BigInt(1536);dmaErr=fault=="weight_first"||(fault=="weight_second"&&weights==2)}
          else {stores+=1;tuple._1 shouldBe BigInt(0x160000);tuple._3 shouldBe BigInt(if(fp32)128 else 64);tuple._4 shouldBe BigInt(16);dmaErr=fault=="store_first"||(fault=="store_last"&&stores==tiles*batches)}
          dd=3;heldDma=None
        }else heldDma=Some(tuple)
      }
      if(dd==0 && d.io.dmaResponseReady.peek().litToBoolean && stores==tiles*batches)lastStoreAck=true
      d.clock.step();cycles+=1
      if(desc>=0)desc-=1;if(nd>=0)nd-=1;if(pd>=0)pd-=1;if(dd>=0)dd-=1
    }
    cycles should be < 100000
    if(fault.isEmpty){
      lastStoreAck shouldBe true;commands shouldBe 1;stores shouldBe tiles*batches;pays shouldBe tiles*batches;weights shouldBe (tiles+7)/8
      d.io.status.expect(0.U);d.io.resetRequired.expect(false.B);d.io.matrixSteps.expect((tiles*batches*1536).U)
      d.io.values.expect((tiles*batches*512).U);d.io.weightLoads.expect(tiles.U);d.io.normLoads.expect((((tiles+7)/8)*batches).U)
      d.io.readBytes.expect((BigInt(tiles)*98304+BigInt((tiles+7)/8)*batches*49152).U)
      d.io.writeBytes.expect((BigInt(tiles)*batches*(if(fp32)2048 else 1024)).U)
      d.clock.step();d.io.done.expect(false.B)
    }else if(fault=="descriptor"){
      d.io.status.expect(2.U);d.io.resetRequired.expect(false.B);commands shouldBe 0;weights shouldBe 0;stores shouldBe 0;d.clock.step()
    }else{
      val code=if(fault=="payload")5 else if(fault=="matrix_completion")7 else 3
      d.io.status.expect(code.U);d.io.resetRequired.expect(true.B)
      d.clock.step();d.io.start.poke(true.B)
      for(_<-0 until 10){d.io.done.expect(false.B);d.io.dmaValid.expect(false.B);d.io.matrixCmdValid.expect(false.B);d.io.descriptorStart.expect(false.B);d.io.status.expect(code.U);d.clock.step()}
      d.io.start.poke(false.B)
    }
  }
  for((tiles,batches,fp)<-Seq((8,1,false),(48,2,false),(8,2,true),(48,2,true)))it should s"schedule tiles=$tiles batches=$batches fp32=$fp and finish only after checked writeback" in {
    test(new Group8Scheduler).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>run(d,tiles,batches,fp);run(d,8,1,false,seed=99)}
  }
  for(fault<-Seq("weight_first","weight_second","store_first","store_last","norm","payload","matrix_completion"))it should s"latch $fault once, reject new work and recover only on reset" in {
    test(new Group8Scheduler).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      run(d,16,1,fault=fault);d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);run(d,8,1)
    }
  }
  it should "reject a descriptor before submitting a Matrix command and accept a later legal request" in {
    test(new Group8Scheduler).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>run(d,8,1,fault="descriptor");run(d,8,1)}
  }
  for(b<-Seq(0,65))it should s"reject batch count $b without starting a child" in {
    test(new Group8Scheduler).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>init(d);d.io.batches.poke(b.U);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B);d.io.done.expect(true.B);d.io.status.expect(5.U);d.io.descriptorStart.expect(false.B);d.io.matrixCmdValid.expect(false.B)}
  }
  it should "keep trace-only schedule enumeration separate from payload execution" in {
    test(new Group8Scheduler).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.batches.poke(64.U);d.io.tiles.poke(48.U);d.io.columns.poke(1536.U);d.io.traceOnly.poke(true.B);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B)
      d.io.traceOnly.poke(false.B);d.io.contextValid.poke(true.B);d.clock.step();d.io.contextValid.poke(false.B)
      var n=0;while(!d.io.done.peek().litToBoolean && n<4000){d.io.matrixCmdValid.expect(false.B);d.io.dmaValid.expect(false.B);d.clock.step();n+=1}
      n should be < 4000;d.io.matrixSteps.expect((3072*1536).U);d.io.values.expect((1024*1536).U);d.io.status.expect(0.U)
    }
  }
}
