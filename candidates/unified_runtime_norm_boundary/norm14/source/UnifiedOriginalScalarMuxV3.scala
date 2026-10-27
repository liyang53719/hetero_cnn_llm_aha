// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Eight fixed private clients share the one EXISTING ScalarV2 primitive.
  * No ALU/SFU instance. Owner and policy are captured at actual request.fire;
  * held request/response never use a live requester to infer ownership.
  * All responses must be registered (minimum one edge). Unknown responses
  * quarantine without refunding a credit or injecting a zero result.
  */
class UnifiedOriginalScalarMuxV3 extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Vec(8,Decoupled(new UnifiedScalarRequestV2)))
    val result=Vec(8,Decoupled(new UnifiedScalarResultV2))
    val scalar=new UnifiedScalarClientV2
    val parentPoison=Input(Bool())
    val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
    val accepted=Output(UInt(33.W));val issued=Output(UInt(33.W));val retired=Output(UInt(33.W))
  })
  val arb=Module(new RRArbiter(new UnifiedScalarRequestV2,8))
  val state=RegInit(0.U(2.W)) // idle,held offer,await response,held response
  val owner=Reg(UInt(3.W));val request=Reg(new UnifiedScalarRequestV2)
  val result=Reg(new UnifiedScalarResultV2)
  val accepted=RegInit(0.U(33.W));val issued=RegInit(0.U(33.W));val retired=RegInit(0.U(33.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknown=io.scalar.result.valid && (state=/=2.U || io.scalar.result.bits.policy=/=request.policy)
  val exhausted=accepted==="hffffffff".U && io.request.map(_.valid).reduce(_||_)
  val countBad=retired>issued || issued>accepted || accepted(32) || issued(32) || retired(32)
  for(i<-0 until 8){arb.io.in(i)<>io.request(i)
    io.result(i).valid:=state===3.U && owner===i.U;io.result(i).bits:=result}
  arb.io.out.ready:=state===0.U && !quarantine && !unknown && !countBad && accepted<"hffffffff".U
  io.scalar.request.valid:=state===1.U;io.scalar.request.bits:=request
  io.scalar.result.ready:=state===2.U && !quarantine && !unknown
  when(arb.io.out.fire){request:=arb.io.out.bits;owner:=arb.io.chosen;accepted:=accepted+1.U;state:=1.U}
  when(io.scalar.request.fire){issued:=issued+1.U;state:=2.U}
  when(io.scalar.result.fire){result:=io.scalar.result.bits;state:=3.U
    when(io.scalar.result.bits.error){poison:=true.B}}
  when(state===3.U && io.result(owner).ready){retired:=retired+1.U;state:=0.U}
  when(unknown){quarantine:=true.B;poison:=true.B}
  when(countBad || exhausted){poison:=true.B}
  // Ordinary poison does NOT retract held offers or strand a still-owned leaf
  // needing more legal operations to drain. Parent denies new owner/job starts.
  io.resetRequired:=poison || quarantine || unknown || countBad || exhausted || io.parentPoison ||
    (state===2.U && io.scalar.result.valid && io.scalar.result.bits.error)
  io.resourcesDrained:=state===0.U && !io.request.map(_.valid).reduce(_||_) &&
    !io.scalar.result.valid && accepted===issued && issued===retired && !quarantine && !unknown && !countBad
  io.accepted:=accepted;io.issued:=issued;io.retired:=retired
}
