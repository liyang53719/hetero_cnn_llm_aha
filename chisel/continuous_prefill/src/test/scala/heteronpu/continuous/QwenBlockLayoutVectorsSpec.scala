// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import java.nio.file.{Files, Paths}
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.jdk.CollectionConverters._

/** C03.3 consumer of the safe legacy subset only. Candidate decoupled shapes,
  * query/KV lengths and wide-address admission require C03.2 integration.
  * BigInt(decimal) prevents JSON Double truncation above 2^53.
  */
class QwenBlockLayoutVectorsSpec extends AnyFlatSpec with Matchers {
  "QwenBlockLayout" should "match every independent legacy region and wide product" in {
    val path = Paths.get("../../tests/fixtures/block_contracts/legacy_layout_vectors.tsv")
    val rows = Files.readAllLines(path).asScala.filterNot(_.startsWith("#")).filter(_.nonEmpty)
    rows.size shouldBe 4
    rows.foreach { line =>
      val f = line.split("\t", -1)
      withClue(f(0) + ": ") {
        f.length shouldBe 12
        def integer(i: Int): Int = { val n = BigInt(f(i)); require(n.isValidInt); n.toInt }
        val s = QwenBlockShape(hidden=integer(1), ffn=integer(2), heads=integer(3),
          kvHeads=integer(4), headDim=integer(5), maxTokens=integer(6))
        val layout = new QwenBlockLayout(s)
        BigInt(s.maxRow) shouldBe BigInt(f(7))
        BigInt(s.kv) shouldBe BigInt(f(8))
        BigInt(layout.writableStart) shouldBe BigInt(f(9))
        BigInt(layout.total) shouldBe BigInt(f(10))
        val expected = f(11).split(",").map(_.split(":"))
        layout.regions.size shouldBe expected.length
        layout.regions.zip(expected).foreach { case (actual, e) =>
          actual.name shouldBe e(0)
          BigInt(actual.offset) shouldBe BigInt(e(1))
          BigInt(actual.words) shouldBe BigInt(e(2))
          actual.external shouldBe (e(3) == "1")
        }
      }
    }
  }
}
