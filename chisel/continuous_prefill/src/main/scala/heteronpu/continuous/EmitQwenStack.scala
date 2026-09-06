// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
import java.nio.charset.StandardCharsets
object EmitQwenStack extends App {
  require(args.nonEmpty,"output [--tiny] [--layers=N]")
  val tiny=args.contains("--tiny")
  val layers=args.find(_.startsWith("--layers=")).map(_.drop(9).toInt).getOrElse(4)
  require(layers>=1 && layers<=28)
  val s=if(tiny)QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32,maxTokens=33) else QwenBlockShape()
  val g=new StackGeometry(s);val p=g.layout
  val out=Paths.get(args(0));require(!Files.exists(out),"refuse output overwrite");Files.createDirectories(out)
  val sv=ChiselStage.emitSystemVerilog(new Qwen2LayerStack(s,layers),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization"))
  Files.writeString(out.resolve("Qwen2LayerStack.sv"),sv,StandardCharsets.UTF_8)
  val h=new StringBuilder("// Generated from Chisel BlockLayout. Do not edit.\n#pragma once\n#include <cstdint>\n")
  for((n,v)<-Seq("H"->s.hidden,"F"->s.ffn,"HEADS"->s.heads,"KVHEADS"->s.kvHeads,"HD"->s.headDim,"MAX_TOKENS"->s.maxTokens,"STACK_LAYERS"->layers))h.append(s"static constexpr int $n=$v;\n")
  h.append(s"static constexpr uint64_t ARENA_BYTES=${p.total}ULL, WRITABLE_START=${p.writableStart}ULL;\n")
  for(r<-p.regions)h.append(s"static constexpr uint64_t OFF_${r.name.toUpperCase}=${r.offset}ULL;\n")
  for((n,v)<-Seq("WEIGHT"->g.weightBytes,"ROPE"->g.ropeBytes,"HIDDEN"->g.hiddenBytes,"SCRATCH"->g.scratchBytes))h.append(s"static constexpr uint64_t STACK_${n}_BYTES=${v}ULL;\n")
  Files.writeString(out.resolve("block_layout.h"),h.toString,StandardCharsets.UTF_8)
}
