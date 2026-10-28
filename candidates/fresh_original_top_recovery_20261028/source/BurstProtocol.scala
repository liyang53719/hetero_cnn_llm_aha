// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
/** Internal decoded-owner transfer, not a new Host opcode. Each transfer is
  * 1..64 aligned 64-byte beats. A 16-beat service uses 1 KiB windows;
  * a batched 64-beat service uses 4 KiB windows. The unchanged pinned backend
  * still legalizes every external AXI burst to at most 16 beats.
  * Non-LAST beats are provisional and may be forwarded during DMA. Successful
  * LAST is the commit fence: it is released only after the real backend has
  * completed and checked the entire burst. A consumer must stage the whole
  * burst before using it and must drain through LAST on error. Early arrival
  * is not permission to publish a tensor or complete a Host command.
  */
class BurstReadRequest extends Bundle {
  val address=UInt(64.W);val beats=UInt(7.W);val tag=UInt(64.W)
}
class BurstReadResponse extends Bundle {
  val data=UInt(512.W);val tag=UInt(64.W);val last=Bool();val error=Bool()
}
/** Optional internal Dense operand layout, absent from the default interface.
  * When transposedDense is true, only opcode 0x20 and sliceMask 0xff are legal.
  * a[0..15] holds weight N0..15; b[0..127] holds activation M0..127;
  * b[128..143] holds weight N16..31. b[144..255] is reserved and ignored
  * in this mode; senders should write zero, receivers must not consume it.
  * Results keep physical value(row)(slice*32+column): logical M is
  * (slice%4)*32+column and logical N is (slice/4)*16+row.
  * This is a bit-preserving routing contract, with no numerical conversion.
  */
class MatrixStreamGroup(val enableTransposedDense:Boolean=false,val enableAccumulatorSeed:Boolean=false) extends Bundle {
  val groupSequence=if(enableAccumulatorSeed)Some(UInt(32.W))else None
  val transposedDense=if(enableTransposedDense)Some(Bool())else None
  val opcode=UInt(8.W);val sliceMask=UInt(8.W);val tag=UInt(32.W)
}
class MatrixStreamStep(val returnTagBits:Int=0) extends Bundle {
  require(returnTagBits>=0 && returnTagBits<=32,"returnTagBits must be in 0..32")
  // Internal opaque metadata only; absent from the default interface.
  val returnTag=if(returnTagBits>0)Some(UInt(returnTagBits.W))else None
  val a=Vec(16,UInt(16.W));val b=Vec(256,UInt(16.W))
  val context=UInt(3.W);val clear=Bool();val last=Bool()
  val finish=Bool();val emit=Bool()
}
class MatrixStreamResult(val returnTagBits:Int=0) extends Bundle {
  require(returnTagBits>=0 && returnTagBits<=32,"returnTagBits must be in 0..32")
  val returnTag=if(returnTagBits>0)Some(UInt(returnTagBits.W))else None
  val value=Vec(16,Vec(256,UInt(32.W)))
  val context=UInt(3.W);val last=Bool();val error=Bool()
}
class MatrixStreamDone extends Bundle {val tag=UInt(32.W);val error=Bool()}
class MatrixStreamPort(val returnTagBits:Int=0,val enableTransposedDense:Boolean=false,val enableAccumulatorSeed:Boolean=false) extends Bundle {
  require(returnTagBits>=0 && returnTagBits<=32,"returnTagBits must be in 0..32")
  val group=Decoupled(new MatrixStreamGroup(enableTransposedDense,enableAccumulatorSeed))
  val step=Decoupled(new MatrixStreamStep(returnTagBits))
  val result=Flipped(Decoupled(new MatrixStreamResult(returnTagBits)))
  val done=Flipped(Decoupled(new MatrixStreamDone))
  val abort=Output(Bool())
  val seed=if(enableAccumulatorSeed)Some(new MatrixAccumulatorSeedPort)else None
}

/** Internal whole-beat write batch. Accepted data is not a completion: the
  * single response follows the real pinned-iDMA destination B response.
  * The address/count is bounded to one 1-KiB window; all beats are 64 bytes.
  */
class BurstWriteRequest extends Bundle {
  val address=UInt(64.W);val beats=UInt(5.W);val tag=UInt(64.W)
}
class BurstWriteBeat extends Bundle {
  val data=UInt(512.W);val last=Bool()
}
