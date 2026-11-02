// Test-only: no Chisel Module/Stage, FIRRTL parse or Verilator invocation.
package heteronpu.continuous
import chisel3._
import chiseltest.simulator.{SimulatorContext,StepOk}
import chiseltest.simulator.jna.DirectBContextFactory
import scala.language.dynamics
import java.nio.file.{Files,Paths,Path}
import java.security.MessageDigest

case class DirectPin(id:Int,name:String,width:Int,input:Boolean)
case class DirectValue(litValue:BigInt,width:Int) {
  def litToBoolean:Boolean={require(width==1,"Boolean peek width");litValue==1}
}
class DirectDut(val ctx:SimulatorContext,val pins:Vector[DirectPin]) {
  require(pins.map(_.id)==pins.indices.toVector,"ordered IDs")
  require(pins.map(_.name).distinct.size==pins.size,"unique names")
  require(pins.forall(p=>p.width>0 && p.width<=512),"finite widths")
  val byName=pins.map(p=>p.name->p).toMap
  def path(name:String):DirectPort={
    require(byName.contains(name)||pins.exists(_.name.startsWith(name+"_")),"unknown port prefix: "+name)
    new DirectPort(this,name)
  }
  val io=path("io");val diagnostic=path("diagnostic")
  object clock {
    def step(n:Int=1):Unit={require(n>0);require(ctx.step(n)==StepOk,"interrupted simulator step")}
  }
}
class DirectPort(val dut:DirectDut,val name:String) extends Dynamic {
  def selectDynamic(child:String):DirectPort={require(child.matches("[A-Za-z][A-Za-z0-9_]*"));dut.path(name+"_"+child)}
  // Only an Option-present marker in the original typed fixture; no name suffix.
  def get:DirectPort=this
  private def leaf:DirectPin=dut.byName.getOrElse(name,throw new IllegalArgumentException("nonleaf access: "+name))
  private def literal(v:Data):BigInt=v match {
    case u:UInt=>u.litValue
    case _=>throw new IllegalArgumentException("only original unsigned literals")
  }
  private def checked(n:BigInt,p:DirectPin):Unit=require(n>=0 && n<(BigInt(1)<<p.width),"port value overflow: "+name)
  def poke(v:Data):Unit={val p=leaf;require(p.input,"poke output: "+name);val n=literal(v);checked(n,p);dut.ctx.poke(name,n)}
  def peek():DirectValue={val p=leaf;val n=dut.ctx.peek(name);checked(n,p);DirectValue(n,p.width)}
  def expect(v:Data):Unit={val p=leaf;val wanted=literal(v);checked(wanted,p);val actual=peek().litValue;require(actual==wanted,s"port expectation $name expected=$wanted actual=$actual")}
  def zero():Unit={
    val selected=dut.pins.filter(p=>p.name==name||p.name.startsWith(name+"_"))
    require(selected.nonEmpty && selected.forall(_.input),"zero direction/prefix")
    selected.foreach(p=>dut.ctx.poke(p.name,BigInt(0)))
  }
}
object Public21DownOwnerDirectMain {
  def sha(p:Path):String={
    val digest=MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(p);val b=new Array[Byte](65536)
    try {var n=in.read(b);while(n>=0){if(n>0)digest.update(b,0,n);n=in.read(b)}}finally in.close()
    digest.digest().map(x=>f"${x&255}%02x").mkString
  }
  def main(args:Array[String]):Unit={
    // All three pins are supplied by the enclosing trusted, supervised invocation.
    require(args.length==5,"PORTS.json PORTS_SHA SHARED_LIBRARY LIB_SHA NEW_OUTPUT_DIRECTORY")
    val map=Paths.get(args(0)).toRealPath();val lib=Paths.get(args(2)).toRealPath();val out=Paths.get(args(4)).toRealPath()
    require(args(1).matches("[0-9a-f]{64}") && sha(map)==args(1),"port manifest hash")
    require(args(3).matches("[0-9a-f]{64}") && sha(lib)==args(3),"shared library hash")
    require(Files.isDirectory(out) && lib.startsWith(out),"owned new library/output domain")
    val m=ujson.read(new String(Files.readAllBytes(map),java.nio.charset.StandardCharsets.UTF_8))
    require(m("schema").str=="B_DIRECT_JNA_PORT_INVENTORY_V1" && m("scope").str=="PROTOCOL_FIXTURE_ONLY_NOT_NUMERICAL")
    require(m("top").str=="Public21DownOwnerProtocolHarness" && m("clocks").arr.map(_.str).toSeq==Seq("clock"))
    val pins=m("ports").arr.map { p=>
      require(!p("signed").bool && !p("clock").bool,"unsigned nonclock leaf only")
      require(Set("input","output").contains(p("direction").str))
      for(k<-Seq("id","width"))require(p(k).num==math.floor(p(k).num) && p(k).num>=0 && p(k).num<100000)
      DirectPin(p("id").num.toInt,p("name").str,p("width").num.toInt,p("direction").str=="input")
    }.toVector
    require(pins.map(_.id)==pins.indices.toVector && pins.map(_.name).distinct.size==pins.size)
    require(pins==pins.filter(_.input)++pins.filterNot(_.input),"inputs followed by outputs")
    require(pins.exists(p=>p.name=="reset" && p.input && p.width==1))
    // Official helper makes one uniquely suffixed library copy beside lib. The
    // enclosing stage must account for that disk usage and native RSS. No compiler.
    println("B_DIRECT_BEFORE_NATIVE_LOAD protocol_only=true re_elaboration=false")
    val ctx=DirectBContextFactory.open(os.Path(lib.toString),os.Path(out.toString),m("top").str,pins.filter(_.input).map(p=>(p.name,p.width,false)),pins.filterNot(_.input).map(p=>(p.name,p.width,false)),Seq("clock"))
    try {
      // Exact SimController.run default sequence, official chiseltest 6.0.0.
      ctx.poke("reset",BigInt(1));require(ctx.step(1)==StepOk,"reset interrupted");ctx.poke("reset",BigInt(0))
      val dut=new DirectDut(ctx,pins)
      new Public21DownOwnerDirectDriver().run(dut)
      println("B_DIRECT_DRIVER_RETURNED_PROTOCOL_ONLY numerical=false")
    } finally ctx.finish()
  }
}
