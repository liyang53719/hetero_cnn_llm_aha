package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

object RawKvElaborate extends App {
  require(args.length==1)
  val out=Paths.get(args(0));Files.createDirectories(out)
  for(tiles<-Seq(false,true);raw<-Seq(false,true)){
    val name=s"banks_tiles${if(tiles)1 else 0}_raw${if(raw)1 else 0}"
    Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(new TransposedDownDenseBanks(tiles,raw)))
  }
}

class RawKvUnit extends AnyFlatSpec with ChiselScalatestTester {
  def defaults(d:TransposedDownDenseBanks):Unit={
    d.io.zero.valid.poke(false.B);d.io.zero.bits.poke(0.U)
    d.io.activation.valid.poke(false.B);d.io.activation.bits.kWord.poke(0.U);d.io.activation.bits.m.poke(0.U);d.io.activation.bits.value.poke(0.U)
    d.io.read.valid.poke(false.B);d.io.read.bits.k.poke(0.U);d.io.read.bits.context.poke(0.U);d.io.read.bits.half.poke(false.B)
    d.io.weight.valid.poke(false.B);d.io.weight.bits.half.poke(false.B);d.io.weight.bits.depth.poke(0.U);d.io.weight.bits.group16.poke(0.U);d.io.weight.bits.pair.poke(false.B);d.io.weight.bits.value.poke(0.U)
    d.io.tileEnable.foreach(_.poke(true.B))
    d.io.tiles.foreach{t=>
      t.control.valid.poke(false.B);t.control.bits.op.poke(0.U);t.control.bits.slot.poke(0.U);t.control.bits.identity.poke(0.U);t.control.bits.ng.poke(0.U);t.control.bits.rows.poke(0.U);t.control.bits.cols.poke(0.U)
      t.write.valid.poke(false.B);t.write.bits.key.slot.poke(0.U);t.write.bits.key.identity.poke(0.U);t.write.bits.key.ng.poke(0.U);t.write.bits.key.index.poke(0.U);t.write.bits.value.foreach(_.poke(0.U))
      t.read.valid.poke(false.B);t.read.bits.slot.poke(0.U);t.read.bits.identity.poke(0.U);t.read.bits.ng.poke(0.U);t.read.bits.index.poke(0.U)
      t.response.ready.poke(false.B);t.abort.poke(false.B)
    }
    d.io.rawKv.foreach{p=>
      p.acquire.valid.poke(false.B);p.acquire.bits.poke(0.U)
      p.release.valid.poke(false.B);p.release.bits.poke(0.U)
      p.request.valid.poke(false.B);key(p.request.bits.key,0,0,0,0);p.request.bits.data.poke(0.U)
      p.ack.valid.poke(false.B);key(p.ack.bits,0,0,0,0)
      p.parentDrained.poke(true.B);p.abort.poke(false.B);p.softReset.poke(false.B)
    }
  }
  def key(k:RawKvKey,o:BigInt,t:BigInt,l:BigInt,w:BigInt):Unit={
    k.owner.poke(o.U);k.tag.poke(t.U);k.line.poke(l.U);k.write.poke((w!=0).B)
  }
  behavior of "existing A banks raw KV candidate"
  it should "replay the frozen model cycle stream on actual synchronous banks" in {
    test(new TransposedDownDenseBanks(enableFfnTiles=true,enableRawKv=true)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      defaults(d);d.clock.setTimeout(100000)
      val source=scala.io.Source.fromFile(sys.env("RAW_KV_STIMULI"))
      val lines=try source.getLines().toVector finally source.close()
      val header=lines.head.split("\t").zipWithIndex.toMap
      for((line,cycle)<-lines.tail.zipWithIndex){
        val v=line.split("\t").map(BigInt(_,16));def n(s:String)=v(header(s));def b(s:String)=n(s)!=0
        defaults(d);val p=d.io.rawKv.get
        p.acquire.valid.poke((n("acquire")!=0).B);p.acquire.bits.poke(n("acquire").U)
        p.release.valid.poke((n("release")!=0).B);p.release.bits.poke(n("release").U)
        p.request.valid.poke(b("req").B);key(p.request.bits.key,n("owner"),n("tag"),n("line"),n("write"));p.request.bits.data.poke(n("data").U)
        p.ack.valid.poke(b("ack").B);key(p.ack.bits,n("ack_owner"),n("ack_tag"),n("ack_line"),n("ack_write"))
        p.parentDrained.poke(b("parent_drained").B);p.abort.poke(b("abort").B);p.softReset.poke(b("soft_reset").B)
        d.io.activation.valid.poke(b("dense").B);d.io.read.valid.poke((b("dense") && !b("leased")).B);d.io.zero.valid.poke(b("clear").B)
        d.io.tiles.get.read.valid.poke(b("tile").B)
        withClue(s"cycle $cycle: "){
          if(n("acquire")!=0)p.acquire.ready.expect(b("acquired").B)
          if(n("release")!=0)p.release.ready.expect(b("released").B)
          if(b("req"))p.request.ready.expect(b("accepted").B)
          if(b("ack"))p.ack.ready.expect(b("acked").B)
          p.leased.expect(b("leased").B);p.drained.expect(b("drained").B);p.resetRequired.expect(b("reset_required").B)
          p.response.valid.expect(b("response").B)
          if(b("response")){
            p.response.bits.key.owner.expect(n("response_owner").U);p.response.bits.key.tag.expect(n("response_tag").U)
            p.response.bits.key.line.expect(n("response_line").U);p.response.bits.key.write.expect(b("response_write").B)
            p.response.bits.data.expect(n("response_data").U)
          }
          if(b("leased")){d.io.activation.ready.expect(false.B);d.io.read.ready.expect(false.B);d.io.tiles.get.read.ready.expect(false.B)}
        }
        d.clock.step()
      }
    }
  }
  for(raw<-Seq(false,true)){
    it should s"preserve original FFN tile write/read with raw enabled=$raw" in {
      test(new TransposedDownDenseBanks(enableFfnTiles=true,enableRawKv=raw)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        defaults(d);val t=d.io.tiles.get
        t.control.valid.poke(true.B);t.control.bits.op.poke(0.U);t.control.bits.slot.poke(0.U)
        t.control.bits.identity.poke(1.U);t.control.bits.ng.poke(0.U);t.control.bits.rows.poke(16.U);t.control.bits.cols.poke(32.U)
        t.control.ready.expect(true.B);d.clock.step();t.control.valid.poke(false.B)
        for(i<-0 until 32){
          t.write.valid.poke(true.B);t.write.bits.key.slot.poke(0.U);t.write.bits.key.identity.poke(1.U)
          t.write.bits.key.ng.poke(0.U);t.write.bits.key.index.poke(i.U)
          for(b<-0 until 16)t.write.bits.value(b).poke((0x3f800000L+i*16+b).U)
          t.write.ready.expect(true.B);d.clock.step();t.write.valid.poke(false.B);d.clock.step()
        }
        t.control.valid.poke(true.B);t.control.bits.op.poke(1.U);t.control.ready.expect(true.B);d.clock.step();t.control.valid.poke(false.B)
        for(i<-0 until 32){
          t.read.valid.poke(true.B);t.read.bits.slot.poke(0.U);t.read.bits.identity.poke(1.U);t.read.bits.ng.poke(0.U);t.read.bits.index.poke(i.U)
          t.read.ready.expect(true.B);d.clock.step();t.read.valid.poke(false.B);d.clock.step()
          t.response.valid.expect(true.B);t.response.bits.error.expect(false.B)
          for(b<-0 until 16)t.response.bits.value(b).expect((0x3f800000L+i*16+b).U)
          t.response.ready.poke(true.B);d.clock.step();t.response.ready.poke(false.B)
        }
        t.control.valid.poke(true.B);t.control.bits.op.poke(2.U);t.control.ready.expect(true.B);d.clock.step()
        t.leased.expect(false.B);t.resetRequired.expect(false.B)
      }
    }
  }
}
