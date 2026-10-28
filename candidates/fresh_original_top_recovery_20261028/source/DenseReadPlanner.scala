// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Fixed physical SRAM allocation; runtime K changes only the row stride.
  * Includes A and both B ping-pong buffers, not the separately-owned FP32
  * accumulator/result registers. No assumption that encoded address space
  * is physically implemented storage.
  */
case class DenseScratchGeometry(maxK:Int, maxTokenTiles:Int, budgetBytes:Int=768*1024) {
  require(maxK>0 && maxK%16==0 && maxTokenTiles>=1 && maxTokenTiles<=5)
  val weightBytes=16*160*32
  val aWordsPerBank=math.min(maxTokenTiles*(maxK/16),(budgetBytes-weightBytes)/(16*32))
  val aBytes=16*aWordsPerBank*32
  val totalBytes=aBytes+weightBytes
  require(aWordsPerBank>=maxK/16 && totalBytes<=budgetBytes)
  def tokenTiles(k:UInt):UInt = MuxCase(1.U(3.W),
    (maxTokenTiles to 2 by -1).map(t=>(k<=(aWordsPerBank*16/t).U)->t.U(3.W)))
}

/** Bound a real iDMA read by contiguous tensor geometry, not by the arbitrary
  * 256-column arithmetic slice boundary. A read can cross adjacent N contexts.
  * It can also cross K rows only when this group covers the WHOLE N dimension.
  * Every offer remains inside the same 1-KiB window and the current K16 buffer.
  * The returned cursor advances once per accepted payload beat. The consumer
  * still publishes a filled buffer only after the successful final DMA beat.
  */
class DenseReadPlanner(coalesce:Boolean=true) extends Module {
  val io=IO(new Bundle {
    val nativeBf16=Input(Bool());val n=Input(UInt(16.W));val nBase=Input(UInt(16.W))
    val contexts=Input(UInt(3.W));val depthCount=Input(UInt(5.W))
    val depth=Input(UInt(5.W));val context=Input(UInt(3.W));val beat=Input(UInt(5.W))
    val address=Input(UInt(64.W))
    val beats=Output(UInt(5.W));val nextDepth=Output(UInt(5.W))
    val nextContext=Output(UInt(3.W));val nextBeat=Output(UInt(5.W))
    val bufferEnd=Output(Bool())
  })
  val remainingCols=io.n.pad(20)-io.nBase
  val width=Mux(remainingCols<(io.contexts.pad(20)<<8),remainingCols,io.contexts.pad(20)<<8)
  val contextCols=io.n.pad(20)-(io.nBase.pad(20)+(io.context.pad(20)<<8))
  val thisWidth=Mux(contextCols<256.U,contextCols,256.U)
  val perContext=Mux(io.nativeBf16,thisWidth>>5,thisWidth>>4)
  val perRow=Mux(io.nativeBf16,width>>5,width>>4)
  val offset=Mux(io.nativeBf16,io.context.pad(20)<<3,io.context.pad(20)<<4)+io.beat
  val wholeRow=io.nBase===0.U && width===io.n
  val contiguous=Mux(wholeRow,(io.depthCount.pad(20)-io.depth)*perRow-offset,perRow-offset)
  val available=if(coalesce)contiguous else perContext-io.beat
  val boundary=16.U(6.W)-io.address(9,6)
  io.beats:=Mux(available<boundary,available,boundary)
  val endContext=io.beat+&1.U===perContext
  val endRow=endContext && io.context+&1.U===io.contexts
  io.bufferEnd:=endRow && io.depth+&1.U===io.depthCount
  io.nextBeat:=Mux(endContext,0.U,io.beat+1.U)
  io.nextContext:=Mux(endContext,Mux(endRow,0.U,io.context+1.U),io.context)
  io.nextDepth:=Mux(endRow,io.depth+1.U,io.depth)
}
