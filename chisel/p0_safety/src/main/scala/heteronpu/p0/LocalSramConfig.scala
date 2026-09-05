// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0

import chisel3._

/** Implemented SRAM size is not inferred from the address encoding width. */
case class LocalSramConfig(addressBits: Int = 15, rowsPerBank: Int = 6144) {
  require(addressBits >= 3 && addressBits <= 32)
  require(rowsPerBank > 0 && BigInt(rowsPerBank) <= (BigInt(1) << (addressBits - 2)))
  val banks: Int = 16
  val bytes: BigInt = BigInt(banks) * rowsPerBank * 16
  val beatCount: BigInt = bytes / 64
  def contains(base: UInt, span: UInt): Bool =
    (base.pad(66) + span.pad(66)) <= bytes.U(66.W)
}
