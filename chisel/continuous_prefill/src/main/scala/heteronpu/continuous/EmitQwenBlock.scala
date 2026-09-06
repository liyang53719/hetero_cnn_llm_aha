// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
object EmitQwenBlock extends App {
  require(args.length>=1 && args.drop(1).forall(x=>Set("--tiny","--axi","--retained")(x)),"OUT [--tiny] [--axi] [--retained]")
  val s=(if(args.contains("--tiny"))QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32,maxTokens=1024) else QwenBlockShape()).copy(retainedMatrix=args.contains("--retained"))
  val out=Paths.get(args(0));require(!Files.exists(out),"refuse to overwrite an earlier emission");Files.createDirectories(out)
  val axi=args.contains("--axi")
  val name=if(axi)"Qwen2BlockAxiTop" else "Qwen2ContinuousBlock"
  Files.writeString(out.resolve(name+".sv"),ChiselStage.emitSystemVerilog(if(s.retainedMatrix)new RetainedBlockCollection(s,axi) else if(axi)new Qwen2BlockAxiTop(s) else new Qwen2ContinuousBlock(s),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  val layout=new QwenBlockLayout(s)
  val hdr=new StringBuilder("// Generated from Chisel BlockLayout. Do not edit.\n#pragma once\n#include <cstdint>\n")
  for((name,value)<-Seq("H"->s.hidden,"F"->s.ffn,"HEADS"->s.heads,"KVHEADS"->s.kvHeads,"HD"->s.headDim,"MAX_TOKENS"->s.maxTokens))hdr.append(s"static constexpr int $name=$value;\n")
  hdr.append(s"static constexpr int PHYSICAL_MAC_LANES=${if(s.retainedMatrix)512 else 16};\n")
  hdr.append(s"static constexpr uint64_t ARENA_BYTES=${layout.total}ULL, WRITABLE_START=${layout.writableStart}ULL;\n")
  for(r<-layout.regions)hdr.append(s"static constexpr uint64_t OFF_${r.name.toUpperCase}=${r.offset}ULL;\n")
  Files.writeString(out.resolve("block_layout.h"),hdr.toString)
  val entries=layout.regions.map(r=>s"{\"name\":\"${r.name}\",\"offset\":${r.offset},\"words\":${r.words},\"external\":${r.external}}")
  Files.writeString(out.resolve("layout.json"),s"{\"schema\":1,\"hidden\":${s.hidden},\"ffn\":${s.ffn},\"heads\":${s.heads},\"kv_heads\":${s.kvHeads},\"head_dim\":${s.headDim},\"max_tokens\":${s.maxTokens},\"arena_bytes\":${layout.total},\"useful_lanes_per_issue\":16,\"physical_mac_lanes\":${if(s.retainedMatrix)512 else 16},\"retained_matrix\":${s.retainedMatrix},\"clock_target_hz\":800000000,\"performance_equivalent_to_revision8b\":false,\"regions\":[${entries.mkString(",") }]}\n")
}
