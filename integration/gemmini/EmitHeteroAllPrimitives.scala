package gemmini
import chisel3._
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths}
class HeteroAllPrimitives extends Module{
 val io=IO(new Bundle{
  val bfA=Input(UInt(16.W));val bfB=Input(UInt(16.W));val bfC=Input(UInt(32.W));
  val bfOut=Output(UInt(32.W));val bfFlags=Output(UInt(5.W));
  val aluOp=Input(Bool());val aluX=Input(UInt(32.W));val aluY=Input(UInt(32.W));
  val aluOut=Output(UInt(32.W));val aluFlags=Output(UInt(5.W));
  val floorX=Input(UInt(32.W));val floorOut=Output(UInt(16.W));val floorFlags=Output(UInt(8.W))})
 val bf=Module(new HeteroBF16FmaLane);dontTouch(bf.clock);dontTouch(bf.reset)
 bf.io.a:=io.bfA;bf.io.b:=io.bfB;bf.io.c:=io.bfC;io.bfOut:=bf.io.out;io.bfFlags:=bf.io.exceptionFlags
 val fp=Module(new HeteroFP32Primitives);fp.io.aluOp:=io.aluOp;fp.io.aluX:=io.aluX;fp.io.aluY:=io.aluY
 io.aluOut:=fp.io.aluOut;io.aluFlags:=fp.io.aluFlags;fp.io.floorX:=io.floorX
 io.floorOut:=fp.io.floorOut;io.floorFlags:=fp.io.floorFlags
}
object EmitHeteroAllPrimitives extends App{require(args.length==1);val p=Paths.get(args(0));val s=ChiselStage.emitSystemVerilog(new HeteroAllPrimitives);Files.createDirectories(p.getParent);Files.writeString(p,s,StandardCharsets.UTF_8)}
