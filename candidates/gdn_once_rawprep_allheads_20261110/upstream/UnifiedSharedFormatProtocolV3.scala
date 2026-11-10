// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
/** Private shared-resource format operation; fullowner/serial binding belongs
  * to the one common resource arbiter. Neither packet is host authority. */
class UnifiedRawFp32FormatRequestV3 extends Bundle {val value=UInt(32.W)}
class UnifiedRawFp32FormatResultV3 extends Bundle {val value=UInt(16.W);val error=Bool()}
