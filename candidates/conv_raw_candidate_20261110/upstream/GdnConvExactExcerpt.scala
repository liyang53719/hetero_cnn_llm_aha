package heteronpu.continuous
import chisel3._
class GdnConv4Job extends Bundle {
  val tokens = UInt(16.W)
  val channels = UInt(16.W)
  val input = UInt(64.W)
  val weight = UInt(64.W)
  val historyIn = UInt(64.W)
  val historyOut = UInt(64.W)
  val output = UInt(64.W)
  val cold = Bool()
  val expectedGeneration = UInt(32.W)
  val tag = UInt(32.W)
}

class GdnConv4Result extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  // Only this flag permits publication of historyOut and generation. A failure
  // may have acknowledged writes into staging, but never commits that state.
  val historyCommitted = Bool()
  val generation = UInt(32.W)
}

