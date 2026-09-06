// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import scala.util.Random
class DenseTileCursorSpec extends AnyFlatSpec with ChiselScalatestTester {
  def init(d:DenseTileCursor,m:Int,n:Int,k:Int):Unit={
    d.io.request.valid.poke(false.B);d.io.tile.ready.poke(false.B);d.io.ack.valid.poke(false.B);d.io.done.ready.poke(false.B)
    d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)
    val x=d.io.request.bits; x.a.poke(BigInt("100000000",16).U);x.b.poke(BigInt("200000000",16).U);x.dst.poke(BigInt("300000000",16).U)
    x.m.poke(m.U);x.n.poke(n.U);x.k.poke(k.U)
    x.aStride.poke(((k*2+63)/64*64).U);x.bStride.poke(((n*2+63)/64*64).U);x.dstStride.poke(((n*4+63)/64*64).U)
    x.aLimit.poke(BigInt("180000000",16).U);x.bLimit.poke(BigInt("280000000",16).U);x.dstLimit.poke(BigInt("380000000",16).U)
    d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
  }
  for((m,n,k)<-Seq((1,1,1),(17,33,129),(32,256,1536),(16,512,2048),(16,640,2560),(16,1536,8960))){
    it should s"enumerate $m x $n x $k with ordered K blocks and acknowledged stores" in {
      test(new DenseTileCursor()){d=>init(d,m,n,k);val rng=new Random(m+n+k);var mac=BigInt(0);var tiles=0
        for(mi<-0 until m by 16;ni<-0 until n by 32;ki<-0 until k by 128){
          val t=d.io.tile.bits;d.io.tile.valid.expect(true.B)
          t.mBase.expect(mi.U);t.nBase.expect(ni.U);t.kBase.expect(ki.U)
          t.a.expect((BigInt("100000000",16)+mi*((k*2+63)/64*64)+ki*2).U)
          t.b.expect((BigInt("200000000",16)+ki*((n*2+63)/64*64)+ni*2).U)
          t.dst.expect((BigInt("300000000",16)+mi*((n*4+63)/64*64)+ni*4).U)
          val rm=math.min(16,m-mi);val rn=math.min(32,n-ni);val rk=math.min(128,k-ki);mac+=BigInt(rm)*rn*rk
          t.rows.expect(rm.U);t.columns.expect(rn.U);t.depth.expect(rk.U);t.clear.expect((ki==0).B);t.lastK.expect((ki+rk==k).B)
          d.clock.step(rng.nextInt(3));t.kBase.expect(ki.U)
          d.io.tile.ready.poke(true.B);d.clock.step();d.io.tile.ready.poke(false.B)
          d.clock.step(rng.nextInt(3));d.io.tile.valid.expect(false.B)
          d.io.ack.bits.tag.poke(tiles.U);d.io.ack.bits.status.poke(0.U);d.io.ack.bits.writeCommitted.poke((ki+rk==k).B)
          d.io.ack.valid.poke(true.B);d.clock.step();d.io.ack.valid.poke(false.B);tiles+=1
        }
        d.io.done.valid.expect(true.B);d.io.done.bits.expect(0.U);d.io.usefulMacs.expect(mac.U);d.io.tiles.expect(tiles.U)
        assert(mac==BigInt(m)*n*k)
      }
    }
  }
  it should "refuse a final K ack without writeback commitment" in {test(new DenseTileCursor()){d=>init(d,1,1,1);d.io.tile.ready.poke(true.B);d.clock.step()
    d.io.ack.bits.tag.poke(0.U);d.io.ack.bits.status.poke(0.U);d.io.ack.bits.writeCommitted.poke(false.B);d.io.ack.valid.poke(true.B);d.clock.step()
    d.io.done.bits.expect(7.U);d.io.resetRequired.expect(true.B);d.io.usefulMacs.expect(0.U)
  }}
  it should "reject a wrapped DDR footprint" in {test(new DenseTileCursor()){d=>init(d,0,1,1);d.io.done.bits.expect(5.U);d.io.tile.valid.expect(false.B)}}
}
