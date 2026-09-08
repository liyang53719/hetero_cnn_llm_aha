// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
/** Internal decoded-owner transfer, not a new Host opcode. Each transfer is
  * 1..16 aligned 64-byte beats inside a single physical 1KiB boundary.
  * Non-LAST beats are provisional and may be forwarded during DMA. Successful
  * LAST is the commit fence: it is released only after the real backend has
  * completed and checked the entire burst. A consumer must stage the whole
  * burst before using it and must drain through LAST on error. Early arrival
  * is not permission to publish a tensor or complete a Host command.
  */
class BurstReadRequest extends Bundle {
  val address=UInt(64.W);val beats=UInt(5.W);val tag=UInt(64.W)
}
class BurstReadResponse extends Bundle {
  val data=UInt(512.W);val tag=UInt(64.W);val last=Bool();val error=Bool()
}
class MatrixStreamGroup extends Bundle {
  val opcode=UInt(8.W);val sliceMask=UInt(8.W);val tag=UInt(32.W)
}
class MatrixStreamStep extends Bundle {
  val a=Vec(16,UInt(16.W));val b=Vec(256,UInt(16.W))
  val context=UInt(3.W);val clear=Bool();val last=Bool()
  val finish=Bool();val emit=Bool()
}
class MatrixStreamResult extends Bundle {
  val value=Vec(16,Vec(256,UInt(32.W)))
  val context=UInt(3.W);val last=Bool();val error=Bool()
}
class MatrixStreamDone extends Bundle {val tag=UInt(32.W);val error=Bool()}
class MatrixStreamPort extends Bundle {
  val group=Decoupled(new MatrixStreamGroup)
  val step=Decoupled(new MatrixStreamStep)
  val result=Flipped(Decoupled(new MatrixStreamResult))
  val done=Flipped(Decoupled(new MatrixStreamDone))
  val abort=Output(Bool())
}
