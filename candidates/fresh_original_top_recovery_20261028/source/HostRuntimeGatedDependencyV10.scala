// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._

/** Read-only snapshot of a real, fully checked Chunk terminal. It is not a
  * Host input, grant, or new qualification wrapper. Top alone captures it on
  * actual Collection.done.fire after Guard identity, ACK/count and drain checks.
  * Eligible only after the SAME Scalar8/Vector10 leases actually retire. */
class GdnRuntimeChunkStagedReceiptV10 extends Bundle {
  val producer=new GdnRuntimeRawPrepProducerV8
  val result=new GdnRuntimeChunkCoordinatorResult
}
