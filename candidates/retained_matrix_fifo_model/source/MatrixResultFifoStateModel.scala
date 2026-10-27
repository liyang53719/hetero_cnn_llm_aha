// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

/** Simulation-only state semantics for the EXACT original returnTag32 FIFO.
  * No arithmetic, reference-file access, scripted return, shortened capacity,
  * or fabricated latency. Both complete16x256x32 payload slots are retained.
  * A separate strict AST transform would be required to use this contract in
  * the original Chisel simulation; this class is NOT currently installed.
  */
final class MatrixResultFifoStateModel {
  import MatrixResultFifoStateModel._
  private val rows = Array.fill[BigInt](2,16)(BigInt(0))
  private val metadata = Array.fill[BigInt](2)(BigInt(0))
  private var head = 0; private var tail = 0; private var count = 0
  def occupancy: Int = count
  def pointers: (Int,Int) = (head,tail)
  def deqValid: Boolean = count != 0
  def enqReady(deqReady: Boolean): Boolean = count < 2 || (deqReady && deqValid)
  // Original deq.bits reads storage(head) even when invalid; do not replace it
  // by zero or clear storage on reset. Zero constructor state only matches the
  // pinned two-state simulator initialization, not power-up RTL X semantics.
  def deqBits: Payload = Payload(rows(head).toVector,metadata(head))
  def edge(reset: Boolean,enqValid: Boolean,enq: Payload,deqReady: Boolean): Transfers = {
    validate(enq)
    val old = deqBits
    val push = enqValid && enqReady(deqReady)
    val pop = deqReady && deqValid
    // storage has NO reset in the original. A real enq.fire can still write
    // during synchronous reset; head/tail/count reset has independent priority.
    if(push){ var row=0; while(row<16){rows(tail)(row)=enq.rows(row);row+=1};metadata(tail)=enq.metadata }
    if(reset){head=0;tail=0;count=0}
    else {
      if(push) tail ^= 1
      if(pop) head ^= 1
      if(push != pop) count += (if(push) 1 else -1)
    }
    require(count>=0 && count<=2,"original two-slot occupancy")
    Transfers(push,pop,old)
  }
}
object MatrixResultFifoStateModel {
  val Rows=16;val Columns=256;val WordBits=32;val Slots=2
  val RowBits=Columns*WordBits;val MetadataBits=32+3+1+1
  require(Slots*Rows*RowBits==262144) // exactly32768 bytes of data, plus74 metadata bits
  final case class Payload(rows:Vector[BigInt],metadata:BigInt)
  final case class Transfers(enqueue:Boolean,dequeue:Boolean,oldHead:Payload)
  def validate(p:Payload):Unit={
    require(p.rows.size==Rows && p.rows.forall(x=>x>=0 && x.bitLength<=RowBits),"sixteen full8192bit rows")
    require(p.metadata>=0 && p.metadata.bitLength<=MetadataBits,"returnTag32/context3/last/error37bits")
  }
  def packRow(words:Vector[Long]):BigInt={
    require(words.size==Columns && words.forall(x=>x>=0 && x<=0xffffffffL),"256 raw32bit words")
    words.zipWithIndex.foldLeft(BigInt(0)){case(acc,(word,col))=>acc | (BigInt(word)<<(col*32))}
  }
  def unpackRow(row:BigInt):Vector[Long]={
    require(row>=0 && row.bitLength<=RowBits,"8192bit row")
    Vector.tabulate(Columns)(col=>((row>>(col*32))&0xffffffffL).toLong)
  }
}
