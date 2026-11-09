// Exact source excerpt, interface only. No owner or arithmetic substitution.
package heteronpu.continuous
import chisel3._
class GdnRuntimeChunkPreparedReceipt extends Bundle {
  val tag = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val tokens = UInt(16.W)
  val input = UInt(64.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val preparedComplete = Bool()
  val drained = Bool()
  val recurrentMode = Bool()
  // Layout 0 is the existing prepared FP32 [Q[valueHead], K[valueHead],
  // V[valueHead], gates[valueHead,16]] row, NOT compact raw Conv/QKV.
  val layoutId = UInt(2.W)
  val layoutVersion = UInt(8.W)
  val rowBytes = UInt(32.W)
  val keyHeads = UInt(6.W)
  val valueHeads = UInt(6.W)
}

