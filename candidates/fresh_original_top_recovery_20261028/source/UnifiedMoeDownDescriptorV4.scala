// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private ACKed descriptor format, one64B record at descriptorBase+expert*64.
  * Byte offsets are little-endian within the original MemoryRequest.data beat:
  * 0 txn64,8 allocation64,16 downBase64,24 writeBytes64,32 owner32,
  * 36 firstRoute16,38 rows16,40 expert16,42 status8,43 version8,
  * 44..63 reserved0. High unused bits of widened fields are zero.
  * Only an EXACT successful real FFN down result.fire may create this record;
  * only its real matching writeACK retires the group. It is not host authority.
  * Unselected expert slots need not be initialized: a future reader must reject
  * stale txn/allocation/version/geometry and consult the actual routed map.
  */
object UnifiedMoeDownDescriptorV4 {
  val Version=1;val Bytes=64;val Capacity=256
  def pack(transactionId:UInt,allocationSequence:UInt,firstRoute:UInt,
      down:UnifiedMoeDenseWritebackV2):UInt={
    Cat(0.U(160.W),Version.U(8.W),down.result.status,
      down.expert.pad(16),down.groupRows.pad(16),firstRoute.pad(16),
      down.ownerSequence,down.result.writeBytes,down.output,
      allocationSequence,transactionId)
  }
  def transaction(x:UInt):UInt=x(63,0)
  def allocation(x:UInt):UInt=x(127,64)
  def output(x:UInt):UInt=x(191,128)
  def bytes(x:UInt):UInt=x(255,192)
  def owner(x:UInt):UInt=x(287,256)
  def firstRoute(x:UInt):UInt=x(303,288)
  def rows(x:UInt):UInt=x(319,304)
  def expert(x:UInt):UInt=x(335,320)
  def status(x:UInt):UInt=x(343,336)
  def version(x:UInt):UInt=x(351,344)
  def canonical(x:UInt):Bool=x(511,352)===0.U && version(x)===Version.U &&
    expert(x)<256.U && rows(x)>=1.U && rows(x)<=128.U && firstRoute(x)<1024.U
}
