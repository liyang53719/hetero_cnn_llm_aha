package gemmini
import chisel3._
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths}
class HeteroFP32Primitives extends Module{
 val io=IO(new Bundle{val aluOp=Input(Bool());val aluX=Input(UInt(32.W));val aluY=Input(UInt(32.W));
  val aluOut=Output(UInt(32.W));val aluFlags=Output(UInt(5.W));val floorX=Input(UInt(32.W));
  val floorOut=Output(UInt(16.W));val floorFlags=Output(UInt(8.W))})
 val alu=Module(new HeteroFP32Alu);alu.io.op:=io.aluOp;alu.io.x:=io.aluX;alu.io.y:=io.aluY
 io.aluOut:=alu.io.out;io.aluFlags:=alu.io.exceptionFlags
 val floor=Module(new HeteroFP32Scale16Floor);floor.io.x:=io.floorX
 io.floorOut:=floor.io.out;io.floorFlags:=floor.io.exceptionFlags
}
object EmitHeteroFP32Primitives extends App{require(args.length==1);val p=Paths.get(args(0));val s=ChiselStage.emitSystemVerilog(new HeteroFP32Primitives);Files.createDirectories(p.getParent);Files.writeString(p,s,StandardCharsets.UTF_8)}
