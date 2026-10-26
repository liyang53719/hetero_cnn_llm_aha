// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

/** Simulation ONLY. Mechanical Scala port of the pinned strict-lane integer
  * model, not a new hardware implementation and not the independent reference.
  * Finite input domain; unsupported NaN/Inf inputs throw, never return a fixture.
  * RNE / after-rounding tininess follows the existing model's unrestricted-
  * exponent precision rounding, including tiny values rounded to minnormal.
  */
object FiniteFp32Backend {
  final case class Rounded(value: Long, flags: Int)
  private val Mask = 0xffffffffL
  private val Sign = 0x80000000L
  private val Inf = 0x7f800000L
  def finite(u: Long): Boolean = (u & Inf) != Inf
  private def decode(u: Long): (BigInt, Int, Int) = {
    require(u >= 0L && u <= Mask && finite(u), "finite binary32 raw word required")
    val sign = (u >>> 31).toInt
    val e = ((u >>> 23) & 255L).toInt
    val f = u & 0x7fffffL
    val n = BigInt(if (e != 0) (1L << 23) | f else f)
    val power = if (e != 0) e - 150 else -149
    (if (sign != 0) -n else n, power, sign)
  }
  private def nearest(n: BigInt, discard: Int): (BigInt, Boolean) = {
    require(n >= 0)
    if (discard <= 0) (n << -discard, false)
    else {
      val (q, r) = n /% (BigInt(1) << discard)
      val half = BigInt(1) << (discard - 1)
      (q + (if (r > half || (r == half && q.testBit(0))) 1 else 0), r != 0)
    }
  }
  private def round(n0: BigInt, power: Int, zeroSign: Int): Rounded = {
    if (n0 == 0) return Rounded(zeroSign.toLong << 31, 0)
    val sign = if (n0 < 0) Sign else 0L
    val n = n0.abs
    val discard = n.bitLength - 24
    val (initialSig, unboundedInexact) = nearest(n, discard)
    var sig = initialSig
    var unit = power + discard
    if (sig >= (BigInt(1) << 24)) { sig = sig >> 1; unit += 1 }
    val exponent = unit + 23
    if (exponent > 127) Rounded(sign | Inf, 5)
    else if (exponent >= -126)
      Rounded(sign | ((exponent + 127).toLong << 23) | (sig.toLong & 0x7fffffL),
        if (unboundedInexact) 1 else 0)
    else {
      val (sub, inexact) = nearest(n, -149 - power)
      require(sub <= (BigInt(1) << 23), "pinned tiny-round bound")
      Rounded(sign | sub.toLong, if (inexact) 3 else 0)
    }
  }
  def fma(a: Long, b: Long, c: Long): Rounded = {
    val (an, ae, sa) = decode(a); val (bn, be, sb) = decode(b); val (cn, ce, sc) = decode(c)
    val pn = an * bn; val pe = ae + be; val ps = sa ^ sb
    val e = math.min(pe, ce)
    val exact = (pn << (pe - e)) + (cn << (ce - e))
    val zs = if (pn == 0 && cn == 0 && ps == sc) ps else 0
    round(exact, e, zs)
  }
  def mul(a: Long, b: Long): Rounded = {
    val (an, ae, sa) = decode(a); val (bn, be, sb) = decode(b)
    round(an * bn, ae + be, sa ^ sb)
  }
  def add(a: Long, b: Long): Rounded = {
    val (an, ae, sa) = decode(a); val (bn, be, sb) = decode(b)
    val e = math.min(ae, be)
    round((an << (ae - e)) + (bn << (be - e)), e, sa & sb)
  }
}
