// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Compile-time selection shared by every runtime profile. One execute leaf,
  * one existing arithmetic bank; unused private client is tied off. */
class GdnRuntimeChunkSelectedExecuteV1(enableChunk32:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new GdnRuntimeChunkExecuteJob))
    val committed=Input(new GdnChunkCommittedState)
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val vectorRequest=Decoupled(new UnifiedOrdinaryVectorRequestV5)
    val vectorResult=Flipped(Decoupled(new UnifiedOrdinaryVectorResultV5))
    val vector32=new GdnRuntimeChunkVector32Client
    val abort32=new GdnRuntimeChunkAbort32Client
    val done=Decoupled(new GdnRuntimeChunkExecuteResult)
    val resetRequired=Output(Bool())
  })
  if(enableChunk32){
    val execute=Module(new GdnRuntimeChunkExecuteOwner32V1)
    execute.io.abort32<>io.abort32
    execute.io.job<>io.job;execute.io.committed:=io.committed
    io.memory<>execute.io.memory;execute.io.response<>io.response
    io.done<>execute.io.done;io.resetRequired:=execute.io.resetRequired
    io.vector32.request<>execute.io.vectorRequest;execute.io.vectorResult<>io.vector32.result
    io.vectorRequest.valid:=false.B;io.vectorRequest.bits:=0.U.asTypeOf(io.vectorRequest.bits)
    io.vectorResult.ready:=false.B
  }else{
    val execute=Module(new GdnRuntimeChunkExecuteOwnerV8)
    io.abort32.memoryCancel:=false.B;io.abort32.vectorCancel:=false.B
    execute.io.job<>io.job;execute.io.committed:=io.committed
    io.memory<>execute.io.memory;execute.io.response<>io.response
    io.done<>execute.io.done;io.resetRequired:=execute.io.resetRequired
    io.vectorRequest<>execute.io.vectorRequest;execute.io.vectorResult<>io.vectorResult
    io.vector32.request.valid:=false.B;io.vector32.request.bits:=0.U.asTypeOf(io.vector32.request.bits)
    io.vector32.result.ready:=false.B
  }
}
