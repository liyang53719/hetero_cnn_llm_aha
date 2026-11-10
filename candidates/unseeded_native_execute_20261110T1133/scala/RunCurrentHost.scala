package chiseltest.simulator
import firrtl2._
import firrtl2.ir._
import firrtl2.stage.FirrtlCircuitAnnotation
import firrtl2.options.TargetDirAnnotation
import heteronpu.continuous._
import heteronpu.continuous.model._
import treadle2._
import treadle2.executable.ClockInfo
import java.nio.file.{Files,Paths}
import java.security.MessageDigest
object RunCurrentHost extends App {
 def sha(s:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(s).map(b=>f"${b&255}%02x").mkString
 val ir=Files.readAllBytes(Paths.get(args(0)));require(sha(ir)=="cb373a03c3d3160cb4faa41545a0f666692ad2ea236133b94c4b189f6f15ac92","independent current CHIRRTL pin")
 val text=new String(ir,"UTF-8");val begin=text.indexOf("  extmodule idma_backend_rw_axi_flat_wrap :");require(begin>=0)
 val end=text.indexOf("\n\n",begin);require(end>begin)
 val ec=Parser.parse("circuit PinProbe :\n"+text.substring(begin,end)+"\n").modules.collect{case e:ExtModule=>e};require(ec.size==1)
 val ep=sha(ec.head.serialize.getBytes("UTF-8"));println("PINNED_IDMA_EXT "+ep)
 val shape=QwenBlockShape(retainedMatrix=true,matrixColumns=256)
 val (high,_)=Compiler.elaborate(()=>new HostBlockTopV4(shape,weightReadBeats=16,pipelined=true),Seq(TargetDirAnnotation(args(4))),Seq.empty)
 println("ORIGINAL_HIGH_ELABORATED modules="+high.circuit.modules.size)
 val split=IdmaFieldSplitTransform(high.circuit,ep)
 val inventory=UnseededNativeRetainedModelFactoryV2.validateInventory(split);require(inventory.size==17);println("ORIGINAL17_BINDINGS_VERIFIED")
 val low=Compiler.toLowFirrtl(high.copy(circuit=split));println("ORIGINAL_LOW_READY modules="+low.circuit.modules.size)
 val nativeHashes=Vector("cccd47947cedee61ccdd4d69082f3a080945f978fd95a77f88a36b841b6b3b4e","0d204232b904de19415be2a20adc43d61e10c666fadc596e2a4b6cb78d0b6a27","3044ee41c4647bbf337008ab6e104f51dece66376c717627f0e03700e144aa78")
 def pin(i:Int):NativeLibraryPin={val p=Paths.get(args(i));NativeLibraryPin(p.toAbsolutePath.toString,nativeHashes(i-1))}
 val factory=new UnseededNativeRetainedModelFactoryV2(low.circuit,pin(1),pin(2),pin(3))
 val ann=Seq(FirrtlCircuitAnnotation(low.circuit),BlackBoxFactoriesAnnotation(Seq(factory)),ClockInfoAnnotation(Seq(ClockInfo("clock"))))++low.annotations
 var tester:TreadleTester=null
 try {val withInfo=treadle2.stage.phases.SetImplicitOutputInfo.transform(treadle2.stage.phases.GetFirrtlAst.transform(ann));val prepared=new treadle2.stage.phases.PrepareAst().transform(withInfo);println("OFFICIAL_TREADLE_AST_PREPARED");tester=new TreadleTester(prepared);factory.requireCompleteBinding();println("ORIGINAL_HOST_CONSTRUCTED_17_NATIVE_NO_NUMERICAL_PASS");tester.poke("reset",1);tester.poke("io_launch_valid",0);tester.poke("io_completion_ready",0);tester.poke("io_result_ready",0);tester.step(2);println("ORIGINAL_HOST_RESET_TWO_CYCLES_ONLY_NO_PREFILL")} finally {if(tester!=null)tester.finish;factory.abortUnqualifiedConstruction()}
}
