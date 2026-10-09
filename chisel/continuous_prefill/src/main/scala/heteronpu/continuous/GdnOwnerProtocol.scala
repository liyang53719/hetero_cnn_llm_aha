// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal decoded GDN convolution job, not a Host command encoding.
  * All storage is BF16. QKV/output are [tokens, channels]; weight and history
  * are native [channels, 4], oldest tap first. historyOut is a separate staging
  * allocation. The caller owns serialization and publication of generations.
  */
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

/** Client of the existing shared BlockScalarFloat, with one operation in flight.
  * The service must keep error stable with result under backpressure. Reset of
  * an in-flight owner must also reset/drain the shared service and transport.
  */
class GdnScalarClient extends Bundle {
  val request = Decoupled(new ScalarRequest)
  val result = Flipped(Decoupled(UInt(32.W)))
  val error = Input(Bool())
}

class GdnConv4OwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnConv4Job))
  val currentGeneration = Input(UInt(32.W))
  val done = Decoupled(new GdnConv4Result)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}
