// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Private provenance, not a Host grant. These fields are captured from the
  * existing Guard/prefix lease, never inferred from geometry or echoed ACKs.
  * Producer P is distinct from the later Chunk physical owner C; P may be 0.
  */
class GdnRuntimeRawPrepProducerV8 extends Bundle {
  val transactionId=UInt(64.W)
  val hostEpoch=UInt(16.W)
  val ownerSequence=UInt(32.W)
}

/** The complete, unmodified V7 terminal observed at the actual producer fire.
  * Only the existing prefix lease capture is an installed source. A matching
  * packet alone does not confer authority, DDR ownership or stale isolation.
  */
class GdnRuntimeRawPrepReceiptV8 extends Bundle {
  val producer=new GdnRuntimeRawPrepProducerV8
  val result=new GdnRuntimeRawPrepResultV7
}

/** Consumer expectation, to be supplied by a trusted parent from its retained
  * accepted transaction and producer job. This is not itself a success bit.
  * source includes all five actual addresses, tokens, layout and policies.
  * The current Top has no Chunk dispatch/binding path yet.
  */
class GdnRuntimeChunkPrepBindingV8 extends Bundle {
  val transactionId=UInt(64.W)
  val hostEpoch=UInt(16.W)
  val producerOwner=UInt(32.W)
  val source=new GdnRuntimeRawPrepJobV7
}
