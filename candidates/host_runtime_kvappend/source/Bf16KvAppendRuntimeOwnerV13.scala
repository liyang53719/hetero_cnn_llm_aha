// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal runtime job, never Host authority. Preserve the original typed
  * KV append geometry: contiguous BF16 [tokens,2,256] K and V, and one
  * [2,capacityTokens,512] BF16 cache. The original Qwen owner n is the full
  * row width 512, NOT a truncated or reinterpreted head count.
  * Full Host/txn64/epoch and strict producer-before-consumer provenance are
  * proved by the original Commands/Guard/Prefix, not this raw memory tag.
  */
class Bf16KvAppendRuntimeJobV13 extends Bundle {
  val tokens = UInt(16.W)
  val rowWidth = UInt(16.W)
  val kvHeads = UInt(16.W)
  val headDim = UInt(16.W)
  val keyInput = UInt(64.W)
  val valueInput = UInt(64.W)
  val cacheBase = UInt(64.W)
  val capacityTokens = UInt(32.W)
  val appendStart = UInt(32.W)
  val currentLength = UInt(32.W)
  val expectedLength = UInt(32.W)
  val currentGeneration = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val cold = Bool()
  val tag = UInt(32.W)
}
object Bf16KvAppendRuntimeJobV13 {
  def fromOwner(j:QwenOwnerJob):Bf16KvAppendRuntimeJobV13={
    val r=Wire(new Bf16KvAppendRuntimeJobV13)
    r.tokens:=j.m;r.rowWidth:=j.n;r.kvHeads:=2.U;r.headDim:=j.k
    r.keyInput:=j.a;r.valueInput:=j.b;r.cacheBase:=j.dst
    r.capacityTokens:=j.cacheCapacity;r.appendStart:=j.queryStart
    r.currentLength:=j.cacheLength;r.expectedLength:=j.expectedCacheLength
    r.currentGeneration:=j.currentGeneration;r.expectedGeneration:=j.expectedGeneration
    r.cold:=j.cold;r.tag:=j.tag
    r
  }
}
class Bf16KvAppendRuntimeResultV13 extends Bundle {
  val accepted = new Bf16KvAppendRuntimeJobV13
  val tag = UInt(32.W)
  val cacheBase = UInt(64.W)
  val capacityTokens = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val keyAckBytes = UInt(64.W)
  val valueAckBytes = UInt(64.W)
  val memoryAccepted = UInt(32.W)
  val memoryReturned = UInt(32.W)
  val cycles = UInt(64.W)
  val drained = Bool()
  // Staging proposal ONLY. The full-block final ACK/dual-root fence alone
  // may publish global cache/state metadata; consuming this result may not.
  val proposalValid = Bool()
  val proposedLength = UInt(32.W)
  val proposedGeneration = UInt(32.W)
}
class Bf16KvAppendRuntimePortV13 extends Bundle {
  val job = Flipped(Decoupled(new Bf16KvAppendRuntimeJobV13))
  val done = Decoupled(new Bf16KvAppendRuntimeResultV13)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val parentFault = Input(Bool())
  val resourcesDrained = Output(Bool())
  val resetRequired = Output(Bool())
}
object Bf16KvAppendRuntimeAbiV13 {
  val MaxTokens=128
  val CapacityTokens=128
  val KvHeads=2
  val HeadDim=256
}
/** Runtime installation of original Bf16KvAppendOwner's bit-preserving
  * readInput -> writeTail loop, K then V. A single 512-bit beat is retained.
  * No arithmetic, Matrix, DMA, hub or physical service is instantiated.
  * The same fixed capacity128/K2/D256 definition serves both Attention
  * profiles. Initially only cold position0/length0/generation0 is admitted.
  *
  * A held request cannot be withdrawn on fault. Only its exact matching
  * return retires accepted debt; wrong/unsolicited tags are quarantined and
  * cannot fake finish or drain. Matching old debt may still retire after an
  * unknown response, but the unknown quarantine requires joint transport
  * reset and never claims finite drain. Matching successful write ACKs are
  * evidence even on fault; neither they nor a proposal publish cache state.
  */
class Bf16KvAppendRuntimeOwnerV13 extends Module {
  val io = IO(new Bf16KvAppendRuntimePortV13)
  val idle :: readInput :: waitInput :: writeTail :: waitTail :: finish :: report :: locked :: Nil = Enum(8)
  val state = RegInit(idle)
  val job = Reg(new Bf16KvAppendRuntimeJobV13)
  val valuePlane = RegInit(false.B)
  val beat = RegInit(0.U(11.W)) // 128 * 16 = 2048 beats per plane.
  val data = Reg(UInt(512.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val keyAckBytes = RegInit(0.U(64.W))
  val valueAckBytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val memoryAccepted = RegInit(0.U(32.W))
  val poison = RegInit(false.B)
  val drainUnknown = RegInit(false.B)
  val terminal = Reg(new Bf16KvAppendRuntimeResultV13)

  val memoryOffer=state===readInput || state===writeTail
  val memoryDebt=state===waitInput || state===waitTail
  val expectedTag=Cat(job.tag,sequence)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  val currentFault=io.parentFault || unknownMemory
  when(unknownMemory){drainUnknown:=true.B}
  when(currentFault){
    poison:=true.B
    when(state=/=report && state=/=locked && status===Status.Ok.U){status:=Status.Protocol.U}
  }
  val quiet= !io.response.valid
  val noService= !memoryOffer && !memoryDebt
  io.resourcesDrained:=noService && memoryAccepted===sequence && quiet && !drainUnknown && !unknownMemory
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  io.resetRequired:=status=/=Status.Ok.U || poison || drainUnknown || currentFault

  val expectedPlaneBytes=job.tokens.pad(64)<<10
  val expectedBytes=job.tokens.pad(64)<<11
  val expectedMemory=(job.tokens.pad(64)<<6)(31,0) // two planes, 16 reads + 16 writes/token.
  // Widen before all address/extent arithmetic, as in the original owner.
  val beatOffset=beat.pad(66)<<6
  val planeOffset=Mux(valuePlane,job.capacityTokens.pad(66)<<10,0.U)
  val appendOffset=job.appendStart.pad(66)<<10
  val inputAddress=Mux(valuePlane,job.valueInput,job.keyInput).pad(66)+beatOffset
  val tailAddress=job.cacheBase.pad(66)+planeOffset+appendOffset+beatOffset
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || drainUnknown)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write:=state===writeTail
  io.memory.bits.address:=Mux(state===writeTail,tailAddress,inputAddress)
  io.memory.bits.data:=Mux(state===writeTail,data,0.U)
  io.memory.bits.mask:=Mux(state===writeTail,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=expectedTag
  // Quarantine does not cancel legitimate debt. Unknown responses do not fire.
  io.response.ready:=memoryDebt && !unknownMemory

  when(state=/=idle && state=/=report && state=/=locked){cycles:=cycles+1.U}
  def fail(code:UInt):Unit={
    when(status===Status.Ok.U){status:=code}
    poison:=true.B;state:=finish
  }
  // Only an unexposed intent can be abandoned. Otherwise keep state, data,
  // sequence and payload until the already-visible request actually fires.
  when((poison || currentFault || drainUnknown) && memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
  when(io.job.fire){
    job:=io.job.bits
    valuePlane:=false.B;beat:=0.U;sequence:=0.U
    status:=Status.Ok.U;bytes:=0.U;keyAckBytes:=0.U;valueAckBytes:=0.U;cycles:=0.U
    memoryAccepted:=0.U
    val j=io.job.bits
    val inputBytes=j.tokens.pad(66)<<10
    val cacheBytes=j.capacityTokens.pad(66)<<11
    val appendEnd=j.appendStart.pad(66)+j.tokens.pad(66)
    def badSpan(base:UInt,size:UInt):Bool=
      base(5,0)=/=0.U || base.pad(66)+size>(BigInt(1)<<56).U
    def overlap(a:UInt,na:UInt,b:UInt,nb:UInt):Bool=
      a.pad(66)<b.pad(66)+nb && b.pad(66)<a.pad(66)+na
    val badAddress=badSpan(j.keyInput,inputBytes) || badSpan(j.valueInput,inputBytes) ||
      badSpan(j.cacheBase,cacheBytes)
    val alias=overlap(j.keyInput,inputBytes,j.valueInput,inputBytes) ||
      overlap(j.cacheBase,cacheBytes,j.keyInput,inputBytes) ||
      overlap(j.cacheBase,cacheBytes,j.valueInput,inputBytes)
    val badGeometry=j.tokens===0.U || j.tokens>Bf16KvAppendRuntimeAbiV13.MaxTokens.U ||
      j.rowWidth=/=512.U || j.kvHeads=/=Bf16KvAppendRuntimeAbiV13.KvHeads.U ||
      j.headDim=/=Bf16KvAppendRuntimeAbiV13.HeadDim.U ||
      j.capacityTokens=/=Bf16KvAppendRuntimeAbiV13.CapacityTokens.U ||
      j.currentLength>j.capacityTokens || appendEnd>j.capacityTokens.pad(66)
    val wrongSnapshot=j.appendStart=/=j.currentLength || j.expectedLength=/=j.currentLength ||
      j.expectedGeneration=/=j.currentGeneration || j.currentGeneration==="hffffffff".U ||
      !j.cold || j.appendStart=/=0.U || j.currentLength=/=0.U || j.currentGeneration=/=0.U
    when(badGeometry || badAddress || alias){fail(Status.Bounds.U)}
      .elsewhen(wrongSnapshot){fail(Status.Dependency.U)}
      .elsewhen(j.tag==="hffffffff".U){fail(Status.Protocol.U)}
      .otherwise{state:=readInput}
  }
  when(io.memory.fire){
    memoryAccepted:=memoryAccepted+1.U
    state:=Mux(state===readInput,waitInput,waitTail)
  }
  when(io.response.fire){
    val r=io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    // Count only actual successful writes, including a held write accepted
    // before/after a late independent fault. Never infer ACKs from issuance.
    when(state===waitTail && !r.error){
      bytes:=bytes+64.U
      when(valuePlane){valueAckBytes:=valueAckBytes+64.U}
        .otherwise{keyAckBytes:=keyAckBytes+64.U}
    }
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault || drainUnknown){state:=finish}
      .otherwise{
        when(state===waitInput){data:=r.data;state:=writeTail}
          .otherwise{
            when(beat+&1.U===(job.tokens<<4)){
              when(valuePlane){state:=finish}
                .otherwise{valuePlane:=true.B;beat:=0.U;state:=readInput}
            }.otherwise{beat:=beat+1.U;state:=readInput}
          }
      }
  }
  when(state===finish && io.resourcesDrained){
    val exact=memoryAccepted===expectedMemory && sequence===expectedMemory &&
      keyAckBytes===expectedPlaneBytes && valueAckBytes===expectedPlaneBytes && bytes===expectedBytes
    val complete=status===Status.Ok.U && !poison && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag
    terminal.cacheBase:=job.cacheBase;terminal.capacityTokens:=job.capacityTokens
    terminal.status:=Mux(status===Status.Ok.U && (!exact || poison || currentFault),Status.Protocol.U,status)
    terminal.writeBytes:=bytes;terminal.keyAckBytes:=keyAckBytes;terminal.valueAckBytes:=valueAckBytes
    terminal.memoryAccepted:=memoryAccepted;terminal.memoryReturned:=sequence
    terminal.cycles:=cycles;terminal.drained:=io.resourcesDrained
    terminal.proposalValid:=complete
    terminal.proposedLength:=job.currentLength+Mux(complete,job.tokens,0.U)
    terminal.proposedGeneration:=job.currentGeneration+Mux(complete,1.U,0.U)
    when(status===Status.Ok.U && !exact){poison:=true.B}
    state:=report
  }
  // Hold every terminal bit unchanged under backpressure or a late fault.
  // Parent Guard/Prefix also vetoes publication on its current fault signals.
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
}
