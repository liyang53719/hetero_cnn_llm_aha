package heteronpu.continuous.model

import firrtl2.{CircuitState,InstanceKind,SourceFlow,SinkFlow}
import firrtl2.ir._
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Paths
import java.security.MessageDigest
import treadle2.executable.SymbolTable

/** Tiny source-only qualification of the exact production metadata factory.
  * Run the same compiled fixture and metadata classes against independently
  * qualified official and cached SymbolTable classes. No execution engine,
  * data store, functional model, native provider, or file input is created.
  * The production boxes throw on every execution method, so any such call
  * prevents this fixture from reporting success.
  */
object StructuralMetadataFixture {
  private def sha(bytes:Array[Byte]):String=
    MessageDigest.getInstance("SHA-256").digest(bytes).map(x=>f"${x&255}%02x").mkString
  private def hash(text:String):String=sha(text.getBytes(UTF_8))
  private def loaded(c:Class[_],location:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==
      Paths.get(location).toRealPath(),"metadata fixture class location")
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class")
    require(in!=null,"metadata fixture class bytes")
    try{val bytes=in.readAllBytes();require(bytes.length<=1024*1024);sha(bytes)}finally{in.close()}
  }
  private def namedClass(name:String):Class[_]=Class.forName(name,false,getClass.getClassLoader)
  private val one=UIntType(IntWidth(1))
  private val instances=Vector.tabulate(8)(i=>("endpoint"+i,"Endpoint",StructuralLeafContract.endpoint))++
    Vector.tabulate(8)(i=>("gate"+i,"Gate",StructuralLeafContract.gate))++
    Vector(("idma","Idma",IdmaSplitLayout.modelName))

  private def circuit():Circuit={
    require(instances.size==17 && instances.map(_._1).distinct.size==17)
    val leaves=Vector(("Endpoint",StructuralLeafContract.endpoint),("Gate",StructuralLeafContract.gate),
      ("Idma",IdmaSplitLayout.modelName)).map{case(name,kind)=>
      val ports=if(kind==IdmaSplitLayout.modelName)IdmaSplitLayout.ports else
        StructuralLeafContract.ports(kind,seed=true).toVector.sortBy(_._1).map{case(n,(direction,tpe))=>
          Port(NoInfo,n,direction,tpe)}
      require(ports.size<=128)
      ExtModule(NoInfo,name,ports,kind,StructuralLeafContract.params(kind,seed=true))
    }
    val byName=leaves.map(m=>m.name->m).toMap
    val body=Vector.newBuilder[Statement]
    instances.foreach{case(instance,module,_)=>
      body+=DefInstance(NoInfo,instance,module,UnknownType)
      byName(module).ports.filter(_.direction==Input).foreach{p=>
        val target=SubField(Reference(instance,UnknownType,InstanceKind,SourceFlow),p.name,p.tpe,SinkFlow)
        val value:Expression=if(p.name=="clk_i")Reference("clock",ClockType)
          else if(p.name=="rst_ni")Reference("reset",one)
          else p.tpe match{
            case UIntType(IntWidth(w)) if w>0 && w<=16384=>UIntLiteral(0,IntWidth(w))
            case _=>throw new IllegalArgumentException("metadata fixture input type")
          }
        body+=Connect(NoInfo,target,value)
      }
    }
    body+=Connect(NoInfo,Reference("sentinel",one),
      SubField(Reference("endpoint0",UnknownType,InstanceKind,SourceFlow),"out_valid_o",one,SourceFlow))
    val statements=body.result();require(statements.size<2048)
    val top=Module(NoInfo,"MetadataTop",Vector(Port(NoInfo,"clock",Input,ClockType),
      Port(NoInfo,"reset",Input,one),Port(NoInfo,"sentinel",Output,one)),Block(statements))
    val raw=Circuit(NoInfo,top+:leaves,top.name)
    val kinds=firrtl2.passes.ResolveKinds.runTransform(CircuitState(raw,Seq.empty))
    val types=firrtl2.passes.InferTypes.runTransform(kinds)
    val result=firrtl2.passes.ResolveFlows.runTransform(types).circuit
    require(firrtl2.passes.CheckTypes.run(result) eq result)
    require(firrtl2.passes.CheckFlows.run(result) eq result)
    result
  }

  private def graphDigest(table:SymbolTable):String={
    require(table.size>0 && table.size<=4096)
    val rows=Vector.newBuilder[String]
    table.symbols.toVector.sortBy(_.name).foreach{s=>
      rows+=Seq("symbol",s.name,s.dataSize.toString,s.dataType.toString,s.dataKind.toString,
        s.bitWidth.toString,s.slots.toString,s.firrtlType.serialize,s.info.serialize,
        s.index.toString,s.cardinalNumber.toString).map(x=>x.length+":"+x).mkString("|")
      val children=table.childrenOf.getEdges(s).toVector.map(_.name).sorted
      val parents=table.parentsOf.getEdges(s).toVector.map(_.name).sorted
      require(children.size<=4096 && parents.size<=4096)
      rows+=("children:"+s.name+":"+children.mkString("|"))
      rows+=("parents:"+s.name+":"+parents.mkString("|"))
    }
    def names(label:String,values:Iterable[String]):Unit=
      rows+=(label+":"+values.toVector.sorted.mkString("|"))
    names("inputs",table.inputPortsNames);names("outputs",table.outputPortsNames)
    names("orphans",table.orphans.map(_.name));names("instances",table.instanceNames)
    names("modules",table.instanceNameToModuleName.iterator.map{case(a,b)=>a+"="+b}.toVector)
    val text=rows.result().mkString("\n");require(text.length<=2*1024*1024);hash(text)
  }

  def main(args:Array[String]):Unit={
    val out=System.out;val err=System.err
    val muted=new PrintStream(OutputStream.nullOutputStream())
    var result="STRUCTURAL_METADATA_FIXTURE_V1 status=FAIL numericalPass=false fullHostAccepted=false"
    var ok=false
    try{
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        require(args.length==13 && Set("official","cached")(args(0)))
        require(Vector(1,2,3,5,6,7,8,10,11,12).forall(i=>args(i).matches("[0-9a-f]{64}")))
        require(loaded(classOf[SymbolTable],args(4))==args(2))
        require(loaded(SymbolTable.getClass,args(4))==args(3))
        require(loaded(classOf[StructuralMetadataFactory],args(9))==args(6))
        require(loaded(StructuralLeafContract.getClass,args(9))==args(7))
        val boxClass=namedClass("heteronpu.continuous.model.StructuralMetadataBox")
        require(loaded(boxClass,args(9))==args(8))
        require(loaded(namedClass("heteronpu.continuous.model.StructuralMetadataFixture"),args(9))==args(11))
        require(loaded(getClass,args(9))==args(12))
        val c=circuit();val before=c.serialize;require(before.length<=65536)
        val factory=new StructuralMetadataFactory(c,seed=true)
        val expected=instances.map{case(name,_,kind)=>name->kind}.toMap
        require(factory.bindings==expected && expected.size==17)
        val table=SymbolTable(c,Seq(factory),allowCycles=false)
        factory.requireComplete()
        require(table.instanceNames.toSet==expected.keySet && table.size>0 && table.size<=4096)
        expected.keys.foreach{name=>
          val implementation=table.getBlackboxImplementation(table(name));require(implementation.isDefined)
          require(implementation.get.getClass==boxClass && implementation.get.name==name)
        }
        require(table.registerNames.isEmpty && table.registerToClock.isEmpty && table.stopToStopInfo.isEmpty &&
          table.printToPrintInfo.isEmpty && table.verifyInfo.isEmpty && table.moduleMemoryToMemorySymbol.isEmpty)
        require(table.inputPortsNames.toSet==Set("clock","reset") && table.outputPortsNames.toSet==Set("sentinel"))
        require(c.serialize==before,"metadata fixture AST unchanged")
        val digest=graphDigest(table)
        val success="STRUCTURAL_METADATA_FIXTURE_V1 status=PASS label="+args(0)+
          " symbolSourceSha="+args(1)+" symbolClassSha="+args(2)+" symbolCompanionSha="+args(3)+
          " factorySourceSha="+args(5)+" factoryClassSha="+args(6)+" contractCompanionSha="+args(7)+
          " boxClassSha="+args(8)+" fixtureSourceSha="+args(10)+" fixtureClassSha="+args(11)+
          " fixtureCompanionSha="+args(12)+" bindings=17 instances=17 symbols="+table.size+
          " graphDigest="+digest+" executionMethodsCalled=0 numericalPass=false fullHostAccepted=false"
        require(success.length<=2048);result=success;ok=true
      }}
    }catch{case _:Throwable=>()}
    finally{System.setOut(out);System.setErr(err);muted.close()}
    out.println(result);out.flush()
    if(!ok || out.checkError())System.exit(2)
  }
}
