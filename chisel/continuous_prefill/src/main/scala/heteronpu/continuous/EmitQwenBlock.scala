// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
object EmitQwenBlock extends App {
  require(args.nonEmpty && args.tail.forall(Set("--tiny","--retained").contains),"OUT [--tiny] [--retained]")
  val s=(if(args.contains("--tiny"))QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32,maxTokens=1024) else QwenBlockShape()).copy(retainedMatrix=args.contains("--retained"))
  val out=Paths.get(args(0));require(!Files.exists(out),"refuse to overwrite earlier emission");Files.createDirectories(out)
  Files.writeString(out.resolve("Qwen2ContinuousBlock.sv"),ChiselStage.emitSystemVerilog((if(s.retainedMatrix)new RetainedBlockCollection(s,false) else new Qwen2ContinuousBlock(s)),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("Qwen2AxiBlockTop.sv"),ChiselStage.emitSystemVerilog((if(s.retainedMatrix)new RetainedBlockCollection(s,true) else new Qwen2AxiBlockTop(s)),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  val l=new QwenBlockLayout(s);val h=new StringBuilder("// Generated from Chisel BlockLayout. Do not edit.\n#pragma once\n#include <cstdint>\n")
  for((n,v)<-Seq("H"->s.hidden,"F"->s.ffn,"HEADS"->s.heads,"KVHEADS"->s.kvHeads,"HD"->s.headDim,"MAX_TOKENS"->s.maxTokens))h.append(s"static constexpr int $n=$v;\n")
  h.append(s"static constexpr int PHYSICAL_MAC_LANES=${if(s.retainedMatrix)512 else 16};\n")
  h.append(s"static constexpr uint64_t ARENA_BYTES=${l.total}ULL, WRITABLE_START=${l.writableStart}ULL;\n")
  for(r<-l.regions)h.append(s"static constexpr uint64_t OFF_${r.name.toUpperCase}=${r.offset}ULL;\n")
  Files.writeString(out.resolve("block_layout.h"),h.toString)
  val e=l.regions.map(r=>s"{\"name\":\"${r.name}\",\"offset\":${r.offset},\"words\":${r.words},\"external\":${r.external}}")
  Files.writeString(out.resolve("layout.json"),s"{\"schema\":1,\"hidden\":${s.hidden},\"ffn\":${s.ffn},\"heads\":${s.heads},\"kv_heads\":${s.kvHeads},\"head_dim\":${s.headDim},\"max_tokens\":${s.maxTokens},\"arena_bytes\":${l.total},\"mac_lanes\":${if(s.retainedMatrix)512 else 16},\"useful_mac_lanes\":16,\"dense_token_tile\":${if(s.retainedMatrix)1 else 16},\"row_cache_bytes\":${s.maxRow*4*(if(s.retainedMatrix)1 else 16)},\"retained_matrix\":${s.retainedMatrix},\"clock_target_hz\":800000000,\"performance_equivalent_to_revision8b\":false,\"regions\":[${e.mkString(",")}]}\n")
}
