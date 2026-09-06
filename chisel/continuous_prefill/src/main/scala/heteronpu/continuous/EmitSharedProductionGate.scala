// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}

/** One elaboration, one original Matrix endpoint and one original iDMA. */
class SharedProductionCollection(s:QwenBlockShape) extends Module {
  val top=Module(new Qwen2SharedProductionTop(s));val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitSharedProductionGate extends App {
  require(args.length==2 && Set("commands","tiny","tail","real").contains(args(1)),"OUT commands|tiny|tail|real")
  val out=Paths.get(args(0));require(!Files.exists(out),"preserve existing generated outputs");Files.createDirectories(out)
  val opts=Array("--preserve-values=all","-disable-all-randomization")
  if(args(1)=="commands") {
    Files.writeString(out.resolve("HostResidualIdmaTop.sv"),ChiselStage.emitSystemVerilog(new HostResidualIdmaTop,firtoolOpts=opts))
  }else {
    val s=(if(args(1)=="tiny")QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32)
      else if(args(1)=="tail")QwenBlockShape(hidden=64,ffn=80,heads=2,kvHeads=1,headDim=32) else QwenBlockShape()).copy(retainedMatrix=true)
    Files.writeString(out.resolve("Qwen2SharedProductionTop.sv"),ChiselStage.emitSystemVerilog(new SharedProductionCollection(s),firtoolOpts=opts))
    val l=new QwenBlockLayout(s)
    val h=new StringBuilder("// Generated from Chisel geometry. Do not edit.\n#pragma once\n#include <cstdint>\n")
    for((n,v)<-Seq("H"->s.hidden,"F"->s.ffn,"HEADS"->s.heads,"KVHEADS"->s.kvHeads,"HD"->s.headDim,"MAX_TOKENS"->s.maxTokens))h.append(s"static constexpr int $n=$v;\n")
    h.append(s"static constexpr int PHYSICAL_MAC_LANES=512;\nstatic constexpr uint64_t ARENA_BYTES=${l.total}ULL, WRITABLE_START=${l.writableStart}ULL;\n")
    for(r<-l.regions)h.append(s"static constexpr uint64_t OFF_${r.name.toUpperCase}=${r.offset}ULL;\n")
    Files.writeString(out.resolve("block_layout.h"),h.toString)
  }
  Files.writeString(out.resolve("SCOPE.json"),s"""{"profile":"${args(1)}","host_opcode_enabled":[48],"single_idma":true,"original_full_graph":false,"official_weights":false,"clock_target_hz":800000000,"dc_pass":false}\n""")
}
