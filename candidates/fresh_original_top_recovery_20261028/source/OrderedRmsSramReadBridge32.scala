// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** The actual single outstanding 512-bit read bridge used by the P0 owner.
  * A published physical request and buffered response survive owner abort.
  * No memory model, arithmetic, cancellation or fabricated acknowledgement.
  */
class OrderedRmsSramReadBridge32 extends Module {
  val io=IO(new Bundle {
    val active=Input(Bool());val externalUnexpected=Input(Bool())
    val request=Flipped(Decoupled(UInt(7.W)))
    val response=Decoupled(Vec(16,UInt(32.W)))
    val physicalRequest=Decoupled(UInt(7.W))
    val physicalResponse=Flipped(Decoupled(UInt(512.W)))
    val drained=Output(Bool());val resetRequired=Output(Bool())
  })
  val idle::issue::waitData::returnData::Nil=Enum(4)
  val state=RegInit(idle);val address=Reg(UInt(7.W));val data=Reg(Vec(16,UInt(32.W)))
  val quarantine=RegInit(false.B)
  val unknown=io.active && (io.externalUnexpected || (io.physicalResponse.valid && state=/=waitData))
  when(unknown){quarantine:=true.B}
  io.resetRequired:=quarantine || unknown
  io.drained:=state===idle && !io.resetRequired
  io.request.ready:=state===idle && !io.resetRequired
  io.physicalRequest.valid:=state===issue;io.physicalRequest.bits:=address
  io.physicalResponse.ready:=state===waitData && !io.resetRequired
  io.response.valid:=state===returnData;io.response.bits:=data
  when(io.request.fire){address:=io.request.bits;state:=issue}
  when(io.physicalRequest.fire){state:=waitData}
  when(io.physicalResponse.fire){data:=io.physicalResponse.bits.asTypeOf(data);state:=returnData}
  when(io.response.fire){state:=idle}
}
