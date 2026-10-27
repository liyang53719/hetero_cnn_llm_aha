// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import firrtl2.{CircuitState, Parser, SystemVerilogEmitter}
import firrtl2.ir._
import firrtl2.PrimOps
import firrtl2.options.TargetDirAnnotation
import heteronpu.continuous.model.HostDenseAccMemoryLowering
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest

/** A single finite storage calibration, never a replacement production Host.
  * Both state branches are mechanically taken from the actual original Core
  * AST and its exact denseAcc transform. Only the three write predicates are
  * abstracted to independent test inputs; Host control is not verified here.
  */
object HostDenseAccCalibrationEmitter {
  private val InputPath="inputs/Qwen2ContinuousBlock.raw.fir"
  private val InputBytes=4429273
  private val InputSha="bc4dbb1ba1b31c887bb72a48e938dc05592b7c476859b08cf5dea11a42c561d8"
  private val Out="compiled-denseacc-calibration"
  private val Top="HostDenseAccCalibration"
  private val Mem="sim_denseacc_rows"
  private val Beat="sim_denseacc_selected_beat"
  private def u(w:Int)=UIntType(IntWidth(w))
  private val Row=VectorType(u(32),256)
  private val Tile=VectorType(Row,16)
  private def ref(n:String):Expression=Reference(n)
  private def path(parts:String*):Expression=parts.tail.foldLeft(ref(parts.head))((e,n)=>SubField(e,n))
  private def conn(a:Expression,b:Expression)=Connect(NoInfo,a,b)
  private def bits(e:Expression,h:Int,l:Int):Expression=DoPrim(PrimOps.Bits,Seq(e),Seq(BigInt(h),BigInt(l)),u(h-l+1))
  private def sha(b:Array[Byte])=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def all(s:Statement):Seq[Statement]={val b=Vector.newBuilder[Statement];b+=s;s.foreachStmt(x=>b++=all(x));b.result()}
  private def root(e:Expression):String=e match {
    case r:Reference=>r.name
    case x:SubField=>root(x.expr)
    case x:SubIndex=>root(x.expr)
    case x:SubAccess=>root(x.expr)
    case _=>""
  }
  private def cat(xs:Vector[Expression]):Expression={
    require(xs.nonEmpty)
    if(xs.size==1)xs.head else {val n=xs.size/2;DoPrim(PrimOps.Cat,Seq(cat(xs.drop(n)),cat(xs.take(n))),Seq.empty,UnknownType)}
  }
  private def ports:Seq[Port]=Seq(Port(NoInfo,"clock",Input,ClockType),Port(NoInfo,"reset",Input,u(1)),
    Port(NoInfo,"capture",Input,u(1)),Port(NoInfo,"clearFirst",Input,u(1)),Port(NoInfo,"clearSecond",Input,u(1)),
    Port(NoInfo,"denseRow",Input,u(5)),Port(NoInfo,"denseBeat",Input,u(4)),
    Port(NoInfo,"matrixResult",Input,BundleType(Seq(Field("bits",Default,BundleType(Seq(Field("value",Default,Tile))))))),
    Port(NoInfo,"selectedDense",Output,VectorType(u(32),16)))
  private def clearScaffold(original:Module,w:String):Seq[Statement]={
    val ss=all(original.body)
    val rows=ss.collect{case x:Connect if root(x.loc)==w=>x}
    require(rows.size==16)
    val names=rows.map(_.expr.serialize).toSet+w
    require(names.size==17 && rows.map(_.loc.serialize).toSet==(0 until 16).map(r=>s"$w[$r]").toSet)
    val wires=ss.collect{case x:DefWire if names(x.name)=>x}
    require(wires.size==17 && wires.find(_.name==w).get.tpe==Tile && wires.filterNot(_.name==w).forall(_.tpe==Row))
    val assigns=ss.collect{case x:Connect if names(root(x.loc))=>x}
    require(assigns.size==4112)
    for(row<-names-w){
      val cells=assigns.filter(x=>root(x.loc)==row)
      require(cells.size==256 && cells.map(_.loc.serialize).toSet==(0 until 256).map(c=>s"$row[$c]").toSet)
      require(cells.forall(_.expr==UIntLiteral(0,IntWidth(32))),"actual clear scaffold only original zero words")
    }
    // Preserve relative original statement order, not a handwritten clear DUT.
    ss.filter{case x:DefWire=>names(x.name);case x:Connect=>names(root(x.loc));case _=>false}
  }
  private def branch(original:Module,changed:Module,adapted:Boolean):Module={
    val ss=all(original.body);val cs=all(changed.body)
    val indices=ss.collect{case n:DefNode if n.name.matches("_selectedDense_[0-9]+_T(?:_[123])?")=>n}
    require(indices.size==64)
    val bulk=ss.collect{case c:Connect if c.loc.serialize=="denseAcc"=>c}
    require(bulk.map(_.expr.serialize)==Seq("matrixResult.bits.value","_WIRE_26","_WIRE_44"))
    val origStorage=ss.collect{case r:DefRegister if r.name=="denseAcc"=>r};require(origStorage.size==1)
    val setup=cs.collect{case b:Block if b.stmts.headOption.exists{case m:DefMemory=>m.name==Mem;case _=>false}=>b}
    require(setup.size==1 && setup.head.stmts.size==83)
    val updateBlocks=cs.collect{case b:Block if b.stmts.size==32 && b.stmts.headOption.exists{
      case c:Connect=>c.loc.serialize==s"$Mem.w0.en";case _=>false}=>b}
    require(updateBlocks.size==3)
    for(b<-updateBlocks;i<-0 until 16){
      require(b.stmts(2*i).asInstanceOf[Connect].loc.serialize==s"$Mem.w$i.en" &&
        b.stmts(2*i+1).asInstanceOf[Connect].loc.serialize==s"$Mem.w$i.data")
    }
    val chosen=if(adapted)cs else ss
    val reads=chosen.collect{case c:Connect if c.loc.serialize.matches("selectedDense\\[[0-9]+\\]")=>c}
    require(reads.size==16 && reads.map(_.loc.serialize).toSet==(0 until 16).map(i=>s"selectedDense[$i]").toSet)
    val readPrelude=if(adapted)cs.collect{
      case c:Connect if c.loc.serialize==s"$Mem.r.addr"=>c
      case n:DefNode if n.name==Beat=>n
    }else Seq.empty
    require(!adapted || readPrelude.size==2)
    val updates:Seq[Statement]=if(adapted)updateBlocks else bulk
    val body=Block((if(adapted)setup else origStorage)++indices++Seq(
      Conditionally(NoInfo,ref("capture"),updates(0),EmptyStmt),
      Conditionally(NoInfo,ref("clearFirst"),Block(clearScaffold(original,"_WIRE_26"):+updates(1)),EmptyStmt),
      Conditionally(NoInfo,ref("clearSecond"),Block(clearScaffold(original,"_WIRE_44"):+updates(2)),EmptyStmt)
    )++readPrelude++reads)
    // No unselected original arithmetic/controller may enter the calibration.
    val allowed=ports.map(_.name).toSet++all(body).collect{
      case d:DefRegister=>d.name;case d:DefMemory=>d.name;case d:DefWire=>d.name;case d:DefNode=>d.name}
    def check(e:Expression):Unit={e match{case r:Reference=>require(allowed(r.name),"unexpected retained dependency "+r.name);case _=>()};e.foreachExpr(check)}
    all(body).foreach(_.foreachExpr(check))
    Module(NoInfo,if(adapted)"DenseAccAdaptedCalibration"else"DenseAccOriginalCalibration",ports,body)
  }
  private def retain(n:String,s:String):Unit={Files.write(Paths.get(Out,n),s.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW);()}
  def main(args:Array[String]):Unit={
    require(args.isEmpty && !Files.exists(Paths.get(Out)),"fixed bounded calibration input and fresh output only")
    val p=Paths.get(InputPath);require(Files.size(p)==InputBytes)
    val raw=Files.readAllBytes(p);require(raw.length==InputBytes && sha(raw)==InputSha,"actual bounded original Core high module")
    val parsed=Parser.parse("FIRRTL version 1.2.0\ncircuit Qwen2ContinuousBlock :\n"+new String(raw,StandardCharsets.UTF_8))
    require(parsed.modules.size==1)
    val original=parsed.modules.head.asInstanceOf[Module]
    require(sha(original.serialize.getBytes(StandardCharsets.UTF_8))==HostDenseAccMemoryLowering.ExpectedModuleSha256)
    val changed=HostDenseAccMemoryLowering(parsed).modules.head.asInstanceOf[Module]
    val a=branch(original,changed,false);val b=branch(original,changed,true)
    val shared=ports.filterNot(p=>Set("matrixResult","selectedDense")(p.name))
    val topPorts=shared++Seq(Port(NoInfo,"payload",Input,u(131072)),Port(NoInfo,"original",Output,u(512)),Port(NoInfo,"adapted",Output,u(512)))
    val body=Vector.newBuilder[Statement]
    for((inst,m)<-Seq("before"->a,"after"->b)){
      body+=DefInstance(NoInfo,inst,m.name,UnknownType)
      shared.foreach(p=>body+=conn(path(inst,p.name),ref(p.name)))
      for(r<-0 until 16;c<-0 until 256){
        val loc=SubIndex(SubIndex(path(inst,"matrixResult","bits","value"),r,Row),c,u(32))
        val at=32*(r*256+c);body+=conn(loc,bits(ref("payload"),at+31,at))
      }
      body+=conn(ref(if(inst=="before")"original"else"adapted"),cat(Vector.tabulate(16)(i=>SubIndex(path(inst,"selectedDense"),i,u(32)))))
    }
    val circuit=Circuit(NoInfo,Seq(a,b,Module(NoInfo,Top,topPorts,Block(body.result()))),Top)
    Files.createDirectory(Paths.get(Out))
    retain("calibration-high.fir",circuit.serialize)
    retain("EXTRACTION.txt","ACTUAL_ORIGINAL_CORE_AST_AND_EXACT_TRANSFORM; ONE_FULL4096_STORAGE_PAIR; THREE_PREDICATES_ABSTRACTED_ONLY; NOT_HOST_CONTROL_OR_BLOCK_NUMERIC\n")
    val low=Compiler.toLowFirrtl(CircuitState(circuit,Seq(TargetDirAnnotation(Out))))
    retain("calibration-low.fir",low.circuit.serialize)
    var finalSeen=false
    val emitter=new SystemVerilogEmitter {
      override protected def runTransforms(in:CircuitState):CircuitState={val out=super.runTransforms(in)
        require(!finalSeen);finalSeen=true;retain("calibration-final.fir",out.circuit.serialize);out}
    }
    val w=new java.io.StringWriter;emitter.emit(low,w);require(finalSeen)
    retain(Top+".sv",w.toString)
  }
}
