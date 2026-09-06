// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class QwenBlockLayoutSpec extends AnyFlatSpec with Matchers {
  "QwenBlockLayout" should "reserve nonoverlapping DDR ranges for real Qwen2 shapes without a quadratic score tensor" in {
    val s=QwenBlockShape();val l=new QwenBlockLayout(s)
    l.regions.map(_.name).distinct.size shouldBe l.regions.size
    l.regions.sliding(2).foreach(x=>assert(x.head.offset+x.head.words*4<=x(1).offset))
    l.regions.foreach(r=>{assert(r.offset%64==0);assert(r.words>0);assert(r.offset+r.words*4<=l.total)})
    l.regions.find(_.name=="wg").get.words shouldBe 1536L*8960
    l.regions.find(_.name=="k").get.words shouldBe 1024L*256
    l.regions.exists(r=>r.name=="scores"||r.name=="probabilities") shouldBe false
    assert(l.regions.filterNot(_.external).forall(_.offset>=l.writableStart))
  }
  it should "refuse inconsistent or unsupported vector geometry" in {
    assertThrows[IllegalArgumentException](QwenBlockShape(hidden=1537))
    assertThrows[IllegalArgumentException](QwenBlockShape(ffn=8961))
    assertThrows[IllegalArgumentException](QwenBlockShape(maxTokens=1025))
  }
}
