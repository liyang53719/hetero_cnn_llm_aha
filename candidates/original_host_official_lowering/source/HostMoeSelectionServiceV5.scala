// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.{HeteroStreamingTopK,HeteroTopKEntry}

/** One fixed original512-entry selector, newly installed in the common Host.
  * The original TopK algorithm and stable-index tie policy are UNCHANGED. This
  * is not a claim that its tied expert set equals Torch's reference choice.
  * The fixed512x65 SyncReadMem is an explicit single-port table, not512 entry
  * registers. It has no reset initializer; the original TopK clears the actual
  * k entries before reading them. This SRAM must retain a memory/macro mapping
  * at physical implementation; source declaration is not SRAM/PPA validation.
  *
  * authority comes only from the Top's actual routed-loop begin.fire ledger.
  * No new Host grant exists. Current fault rejects NEW start, never clears an
  * in-flight selector/table or retracts an already offered output.
  */
class HostMoeSelectionServiceV5 extends Module {
  val io=IO(new Bundle {
    val client=Flipped(new UnifiedMoeRouterSelectionClientV2)
    val authorityValid=Input(Bool());val authority=Input(new UnifiedSharedOwnerIdentityV3)
    val currentFault=Input(Bool())
    val resourcesDrained=Output(Bool());val resetRequired=Output(Bool())
  })
  val selector=Module(new HeteroStreamingTopK(512,32,20))
  val table=SyncReadMem(512,UInt(65.W))
  val readPending=RegInit(false.B);val replyFull=RegInit(false.B)
  val reply=Reg(UInt(65.W))
  val r=selector.io.tableRequest
  r.ready:= !readPending && !replyFull
  val readFire=r.fire && !r.bits.write
  val readData=table.read(r.bits.address,readFire)
  when(r.fire && r.bits.write){table.write(r.bits.address,r.bits.data.asUInt)}
  readPending:=readFire
  when(readPending){reply:=readData;replyFull:=true.B}
  selector.io.tableResponse.valid:=replyFull
  selector.io.tableResponse.bits:=reply.asTypeOf(new HeteroTopKEntry(32))
  when(selector.io.tableResponse.fire){replyFull:=false.B}

  val active=RegInit(false.B);val identity=Reg(new UnifiedSharedOwnerIdentityV3)
  val poison=RegInit(false.B);val accepted=RegInit(0.U(9.W));val returned=RegInit(0.U(4.W))
  val sameOwner=io.authorityValid && identity.asUInt===io.authority.asUInt
  val changed=active && !sameOwner
  val badStart=io.client.start && (!io.authorityValid || active ||
    io.client.itemCount=/=256.U || io.client.k=/=8.U)
  val strayInput=io.client.in.valid && !active
  val strayOutput=selector.io.out.valid && !active
  val badCount=(io.client.in.fire && accepted>=256.U) ||
    (io.client.out.fire && (returned>=8.U || io.client.out.bits.rank=/=returned ||
      io.client.out.bits.last=/=(returned===7.U)))
  val unexpectedDone=selector.io.done && (!active || !io.client.out.fire ||
    accepted=/=256.U || returned=/=7.U)
  val localFault=poison || changed || badStart || strayInput || strayOutput || badCount ||
    unexpectedDone || selector.io.invalidConfig
  when(localFault || io.currentFault){poison:=true.B}
  selector.io.clear:=false.B // joint Module reset only; fault is NOT a flush/drain
  io.client.startReady:=selector.io.startReady && !active && io.authorityValid &&
    !poison && !io.currentFault && io.client.itemCount===256.U && io.client.k===8.U &&
    !readPending && !replyFull
  selector.io.start:=io.client.start && io.client.startReady
  selector.io.itemCount:=io.client.itemCount;selector.io.k:=io.client.k
  when(selector.io.start){active:=true.B;identity:=io.authority;accepted:=0.U;returned:=0.U}
  // Selection is exclusive after start. No fault-dependent valid gates on an
  // existing stream/output: matched offered obligations retain their payload.
  selector.io.in.valid:=io.client.in.valid && active
  selector.io.in.bits:=io.client.in.bits
  io.client.in.ready:=selector.io.in.ready && active
  io.client.out.valid:=selector.io.out.valid
  io.client.out.bits:=selector.io.out.bits;selector.io.out.ready:=io.client.out.ready
  when(io.client.in.fire){accepted:=accepted+1.U}
  when(io.client.out.fire){returned:=returned+1.U}
  when(selector.io.done){active:=false.B}
  io.client.busy:=selector.io.busy || active
  io.client.done:=selector.io.done
  // The original numeric owner uses invalidConfig in its start predicate.
  // Register feedback; otherwise start -> invalidConfig -> start is a graph loop.
  io.client.invalidConfig:=RegNext(selector.io.invalidConfig || badStart,false.B)
  io.resetRequired:=localFault || io.currentFault
  io.resourcesDrained:= !active && !selector.io.busy && !selector.io.out.valid &&
    !selector.io.tableRequest.valid && !readPending && !replyFull && !io.client.start &&
    !io.client.in.valid && !io.resetRequired
}
