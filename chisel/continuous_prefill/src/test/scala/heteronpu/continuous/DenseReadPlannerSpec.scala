// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class DenseScratchGeometryProbe extends Module {
  val io=IO(new Bundle {val k=Input(UInt(16.W));val tiles=Output(UInt(3.W))})
  val geometry=DenseScratchGeometry(8960,5)
  io.tiles:=geometry.tokenTiles(io.k)
}

/** Actual combinational Chisel planner, independent enumerated-address oracle.
  * This is geometry/control coverage, not a Matrix numerical proof.
  */
class DenseReadPlannerSpec extends AnyFlatSpec with ChiselScalatestTester {
  for(coalesce<-Seq(false,true)) {
    it should s"preserve all ordered tensor beats without crossing holes coalesce=$coalesce" in {
      test(new DenseReadPlanner(coalesce)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        var beatsChecked=0;var bursts=0
        for(native<-Seq(false,true); n<-Seq(32,64,96,128,256,288,512,544,1536,8960); offset<-Seq(0,64,960)) {
          val epb=if(native)32 else 16;val bytes=if(native)2 else 4
          for(base<-0 until n by 1280) {
            val full=(n-base)/256
            val contexts=if(full==0)1 else math.min(5,full)
            val width=math.min(contexts*256,n-base)
            val steps=16
            // Explicit tensor addresses, independent of RTL cursor arithmetic.
            val expected=(for(k<-0 until steps;c<-0 until width by epb)yield(0x100000000L+offset+(k.toLong*n+base+c)*bytes,k,c/256,(c%256)/epb)).toVector
            d.io.nativeBf16.poke(native.B);d.io.n.poke(n.U);d.io.nBase.poke(base.U)
            d.io.contexts.poke(contexts.U);d.io.depthCount.poke(steps.U)
            var i=0
            while(i<expected.length) {
              val (addr,k,c,b)=expected(i)
              d.io.address.poke(addr.U);d.io.depth.poke(k.U);d.io.context.poke(c.U);d.io.beat.poke(b.U)
              val max=math.min(16-((addr>>6)&15).toInt,expected.length-i)
              var want=1
              while(want<max && expected(i+want)._1==addr+64L*want &&
                    (coalesce||(expected(i+want)._2==k&&expected(i+want)._3==c)))want+=1
              d.io.beats.expect(want.U)
              for(j<-0 until want) {
                val (a,dep,ctx,beat)=expected(i+j)
                d.io.address.poke(a.U);d.io.depth.poke(dep.U);d.io.context.poke(ctx.U);d.io.beat.poke(beat.U)
                val last=i+j+1==expected.length
                d.io.bufferEnd.expect(last.B)
                if(!last) {
                  val next=expected(i+j+1)
                  d.io.nextDepth.expect(next._2.U);d.io.nextContext.expect(next._3.U);d.io.nextBeat.expect(next._4.U)
                }
                beatsChecked+=1
              }
              i+=want;bursts+=1
            }
          }
        }
        println(s"DENSE_READ_PLAN_PASS coalesce=$coalesce checked_beats=$beatsChecked bursts=$bursts")
      }
    }
  }
  it should "fit actual maxK=8960 scratch in 768KiB and select legal per-K M reuse" in {
    val g=DenseScratchGeometry(8960,5)
    assert(g.totalBytes==768*1024 && g.aWordsPerBank==1376)
    test(new DenseScratchGeometryProbe).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(k<-16 to 8960 by 16) {
        d.io.k.poke(k.U)
        val want=math.min(5,g.aWordsPerBank*16/k)
        d.io.tiles.expect(want.U)
        assert(want*k*16*2+g.weightBytes<=g.budgetBytes)
      }
    }
  }
}
