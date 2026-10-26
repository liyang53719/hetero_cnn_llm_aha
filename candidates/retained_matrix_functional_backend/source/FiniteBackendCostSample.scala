// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

/** Separate opt-in JVM micro-cost sample. No model fixture/reference reads.
  * This is only arithmetic throughput, not Treadle/block end-to-end throughput.
  * Execution requires its own root-approved bounded command after typecheck.
  */
object FiniteBackendCostSample {
  def main(args: Array[String]): Unit = {
    require(args.length == 1 && args(0) == "--bounded-65536-fma", "one fixed cost sample")
    var sum = 0L; var flags = 0; var n = 0
    val start = System.nanoTime()
    while (n < 65536) {
      val a = ((0x3f00L + (n & 255)) << 16)
      val b = ((0x3f20L + ((n >>> 3) & 127)) << 16)
      val c = 0x3f000000L | ((n.toLong * 17) & 0x7fffffL)
      val r = FiniteFp32Backend.fma(a, b, c)
      sum = (sum + r.value) & 0xffffffffL; flags |= r.flags; n += 1
    }
    println(s"FINITE_BACKEND_COST count=$n nanoseconds=${System.nanoTime()-start} checksum=$sum flags=$flags")
  }
}
