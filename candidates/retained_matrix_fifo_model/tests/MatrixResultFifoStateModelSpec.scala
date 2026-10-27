// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Pure model controls; NOT original Chisel/FIFO equivalence or runtime evidence. */
class MatrixResultFifoStateModelSpec extends AnyFlatSpec with Matchers {
  import MatrixResultFifoStateModel._
  private def tile(seed:Int)=Payload(Vector.tabulate(16)(r=>packRow(Vector.tabulate(256)(c=>
    ((seed.toLong<<24) ^ (r.toLong<<16) ^ c.toLong)&0xffffffffL))),BigInt(seed)&((BigInt(1)<<37)-1))
  it should "retain all8192 words across two full slots and simultaneous full dequeue enqueue" in {
    val s=new MatrixResultFifoStateModel;val a=tile(1);val b=tile(2);val c=tile(3)
    s.edge(false,true,a,false).enqueue shouldBe true
    s.edge(false,true,b,false).enqueue shouldBe true
    s.occupancy shouldBe 2;s.enqReady(false) shouldBe false;s.deqBits shouldBe a
    s.edge(false,true,c,false).enqueue shouldBe false;s.deqBits shouldBe a
    val both=s.edge(false,true,c,true);both.enqueue shouldBe true;both.dequeue shouldBe true;both.oldHead shouldBe a
    s.deqBits shouldBe b;s.occupancy shouldBe 2
    s.edge(false,false,a,true).oldHead shouldBe b;s.deqBits shouldBe c
    s.edge(false,false,a,true).oldHead shouldBe c;s.deqValid shouldBe false
  }
  it should "preserve non flowthrough empty behavior and full row word order" in {
    val s=new MatrixResultFifoStateModel;val a=tile(6)
    s.edge(false,true,a,true).dequeue shouldBe false;s.occupancy shouldBe 1;s.deqBits shouldBe a
    for(r<-0 until 16;c<-0 until 256)unpackRow(s.deqBits.rows(r))(c) shouldBe (((6L<<24)^(r.toLong<<16)^c.toLong)&0xffffffffL)
  }
  it should "reset only pointers and count while retaining real storage writes under reset" in {
    val s=new MatrixResultFifoStateModel;val a=tile(1);val b=tile(2);val c=tile(3)
    s.edge(false,true,a,false);s.edge(false,true,b,false)
    s.edge(true,false,c,false);s.occupancy shouldBe 0;s.pointers shouldBe (0,0);s.deqBits shouldBe a
    s.edge(true,true,c,false).enqueue shouldBe true;s.occupancy shouldBe 0;s.deqBits shouldBe c
    s.edge(false,true,b,false);s.deqValid shouldBe true;s.deqBits shouldBe b
  }
  it should "reject widened or truncated payloads rather than wrap storage" in {
    val s=new MatrixResultFifoStateModel;val a=tile(1)
    intercept[IllegalArgumentException]{s.edge(false,true,a.copy(rows=a.rows.take(15)),false)}
    intercept[IllegalArgumentException]{s.edge(false,true,a.copy(metadata=BigInt(1)<<37),false)}
    intercept[IllegalArgumentException]{s.edge(false,true,a.copy(rows=a.rows.updated(0,BigInt(1)<<8192)),false)}
  }
}
