// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Path,Paths}
import java.security.MessageDigest

/** Actual production Command128/descriptor decoder. Only metadata enters its
  * memory port; owner return values are controlled protocol stimuli. This gate
  * establishes dispatch contracts and event lifetime, not arithmetic or timing.
  */
class Qwen2Public21DispatchControlSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  // ujson stores JSON numbers as Double. Quote integer tokens before decoding
  // so 64-bit addresses and counts never pass through a floating-point value.
  def exactJson(raw:String):ujson.Value={
    val out=new StringBuilder;var i=0;var quoted=false;var escaped=false
    while(i<raw.length){val c=raw(i)
      if(quoted){out.append(c);if(escaped)escaped=false else if(c=='\\')escaped=true else if(c=='"')quoted=false;i+=1}
      else if(c=='"'){quoted=true;out.append(c);i+=1}
      else if(c.isDigit || c=='-'){val start=i;i+=1;while(i<raw.length && raw(i).isDigit)i+=1
        require(i==raw.length || !".eE+".contains(raw(i)),"integer-only fixture numbers")
        out.append('"').append(raw.substring(start,i)).append('"')}
      else {out.append(c);i+=1}}
    ujson.read(out.toString)
  }
  def num(x:ujson.Value):BigInt=BigInt(x.str)
  case class Fixture(path:Path,pin:String){
    val raw=Files.readAllBytes(path.resolve("manifest.json"));require(sha(raw)==pin,"explicit fixture manifest pin")
    val m=exactJson(new String(raw,java.nio.charset.StandardCharsets.UTF_8))
    def n(k:String):BigInt=num(m(k))
    def table(k:String):ujson.Value=m("tables")(k)
    def bytes(k:String):Array[Byte]={val t=table(k);val p=path.resolve(t("file").str).normalize
      require(p.startsWith(path),"fixture path escape");val b=Files.readAllBytes(p)
      require(sha(b)==t("sha256").str && BigInt(b.length)==((num(t("count"))*16+63)/64)*64,"metadata file identity");b}
    val commandBytes=bytes("command");val descriptorBytes=bytes("descriptor")
    val jobs=m("accepted_jobs").arr.toVector
    val completions=m("expected_completions").arr.toVector
    require(jobs.size==19 && completions.size==21,"current production public21 profile")
    require(n("rows")==16 || n("rows")==128,"supported full prefill rows")
    require(m("regions").arr.size==4,"four physical regions")
  }
  val root=Paths.get(sys.env.getOrElse("HETERO_PUBLIC21_FIXTURE_ROOT",throw new IllegalArgumentException("HETERO_PUBLIC21_FIXTURE_ROOT required"))).toAbsolutePath.normalize
  val gate=exactJson(Files.readString(root.resolve("gate.json")))
  val fixtures=gate("fixtures").arr.map(v=>Fixture(root.resolve(v("directory").str).normalize,v("manifest_sha256").str)).toVector
  require(fixtures.map(_.n("rows"))==Vector(BigInt(16),BigInt(128),BigInt(16)),"M16/M128/relocated M16")
  def initialize(d:HostBlockCommands,f:Fixture):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    val l=d.io.launch.bits;val c=f.table("command");val t=f.table("descriptor")
    l.commandBase.poke(num(c("base")).U);l.commandLimit.poke(num(c("limit")).U);l.commands.poke(num(c("count")).U)
    l.descriptorBase.poke(num(t("base")).U);l.descriptorLimit.poke(num(t("limit")).U);l.descriptors.poke(num(t("count")).U);l.epoch.poke(f.n("epoch").U)
    for((r,i)<-f.m("regions").arr.zipWithIndex){l.regions(i).base.poke(num(r("base")).U);l.regions(i).limit.poke(num(r("limit")).U);l.regions(i).read.poke(r("read").bool.B);l.regions(i).write.poke(r("write").bool.B)}
  }
  def reset(d:HostBlockCommands,f:Fixture):Unit={d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);initialize(d,f)}
  def run(d:HostBlockCommands,f:Fixture,fault:String="",mutateFirst:Option[BigInt]=None):(Int,Int,Int)={
    val commands=f.commandBytes.clone
    mutateFirst.foreach(w=>(0 until 16).foreach(i=>commands(i)=((w>>(8*i))&255).toByte))
    d.io.launch.ready.expect(true.B);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    var jobs=0;var completions=0;var reads=0;var iterations=0;var cycles=1;var errorCompletions=0
    def step(n:Int=1):Unit={d.clock.step(n);cycles+=n}
    while(!d.io.result.valid.peek().litToBoolean && iterations<6000){
      if(d.io.memory.valid.peek().litToBoolean){
        val address=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.bits.write.expect(false.B)
        val choices=Seq((f.table("command"),commands),(f.table("descriptor"),f.descriptorBytes))
          .filter{case(t,_)=>address>=num(t("base")) && address<num(t("limit"))}
        choices.size shouldBe 1 // no payload, score, probability or other virtual reads
        val (t,b)=choices.head;val off=(address-num(t("base"))).toInt;off%64 shouldBe 0
        val data=BigInt(1,Array.tabulate[Byte](64)(i=>if(off+i<b.length)b(off+i)else 0.toByte).reverse)
        for(_<-0 until 3){d.io.memory.bits.address.expect(address.U);d.io.memory.bits.tag.expect(tag.U);step()}
        d.io.memory.ready.poke(true.B);step();d.io.memory.ready.poke(false.B);step(2)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke(tag.U);d.io.response.bits.error.poke((fault=="metadata").B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);step();d.io.response.valid.poke(false.B);reads+=1
      }else if(d.io.job.valid.peek().litToBoolean){
        jobs should be < f.jobs.size
        val expected=f.jobs(jobs);val pc=num(expected("pc")).toInt;d.io.pc.expect(pc.U)
        val fields=Seq("m","n","k","a","b","c","dst","tag","writeBytes")
        fields.foreach(k=>d.io.job.bits.elements(k).asInstanceOf[UInt].expect(num(expected(k)).U))
        d.io.job.bits.kind.expect(num(expected("kind_id")).U)
        Seq("weightBf16","activationBf16","outputBf16").foreach(k=>d.io.job.bits.elements(k).asInstanceOf[Bool].expect(expected(k).bool.B))
        val known=(fields++Seq("kind","weightBf16","activationBf16","outputBf16")).toSet
        d.io.job.bits.elements.filterNot(x=>known(x._1)).values.foreach{case b:Bool=>b.expect(false.B);case u:UInt=>u.expect(0.U);case _=>fail("unreviewed internal job field")}
        val saved=d.io.job.bits.peek().litValue
        for(_<-0 until 5){d.io.completion.valid.expect(false.B);d.io.job.bits.peek().litValue shouldBe saved;step()}
        d.io.job.ready.poke(true.B);step();d.io.job.ready.poke(false.B);jobs+=1
        for(_<-0 until 9){d.io.completion.valid.expect(false.B);d.io.result.valid.expect(false.B);step()}
        val isFault=pc==1;val tag=num(expected("tag"));val bytes=num(expected("writeBytes"))
        d.io.done.bits.tag.poke((if(isFault && fault=="tag")tag^1 else tag).U)
        d.io.done.bits.status.poke((if(isFault && fault=="owner")3 else 0).U)
        d.io.done.bits.writeBytes.poke((if(isFault && fault=="short")bytes-64 else bytes).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);step();d.io.done.valid.poke(false.B)
      }else if(d.io.completion.valid.peek().litToBoolean){
        val c=d.io.completion.bits.peek().litValue;val status=((c>>32)&255).toInt
        if(status==0){val e=f.completions(completions);(c&((BigInt(1)<<29)-1)) shouldBe num(e("pc"));((c>>29)&7) shouldBe num(e("engine"));((c>>40)&65535) shouldBe num(e("signal"));completions+=1}else errorCompletions+=1
        for(_<-0 until 4){d.io.job.valid.expect(false.B);d.io.completion.bits.expect(c.U);step()}
        d.io.completion.ready.poke(true.B);step();d.io.completion.ready.poke(false.B)
      }else step()
      iterations+=1
    }
    d.io.result.valid.expect(true.B);val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.result.bits.completed.expect(completions.U);d.io.result.bits.epoch.expect(f.n("epoch").U)
    val held=d.io.result.bits.peek().litValue
    for(_<-0 until 7){d.io.result.bits.peek().litValue shouldBe held;d.io.job.valid.expect(false.B);step()}
    if(status==0){jobs shouldBe 19;completions shouldBe 21;errorCompletions shouldBe 0
      reads shouldBe (num(f.table("command")("count"))+num(f.table("descriptor")("count"))).toInt
      d.io.resetRequired.expect(false.B)
      println(s"PUBLIC21_CURRENT_PARSER_CONTROL_PASS rows=${f.n("rows")} epoch=${f.n("epoch")} command_base=${num(f.table("command")("base"))} jobs=$jobs completions=$completions metadata_reads=$reads controlled_cycles=$cycles arithmetic=false owner_completion_mock=true")
    }else{errorCompletions shouldBe 1;d.io.resetRequired.expect(true.B)}
    (status,jobs,completions)
  }
  "Current Qwen2 public21 decoder" should "match all physical dispatch contracts, relocation and fail-closed lifetime fences" in {
    test(new HostBlockCommands(QwenBlockShape(),bf16Weights=true)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d,fixtures.head);d.clock.step(20);d.io.memory.valid.expect(false.B);d.io.job.valid.expect(false.B)
      for(f<-fixtures){initialize(d,f);run(d,f) shouldBe (0,19,21);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)}
      val f=fixtures.head
      for(fault<-Seq("short","tag","owner")){reset(d,f);val r=run(d,f,fault);r._1 should not be 0;r._2 shouldBe 2;r._3 shouldBe 1
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B);d.io.launch.valid.poke(true.B);d.clock.step(8);d.io.launch.ready.expect(false.B)}
      reset(d,f);run(d,f,"metadata") shouldBe (3,0,0)
      val first=BigInt(1,f.commandBytes.take(16).reverse)
      reset(d,f);val malformed=run(d,f,mutateFirst=Some((first&~BigInt(255))|255));malformed._1 should not be 0;malformed._2 shouldBe 0
      reset(d,f);run(d,f) shouldBe (0,19,21);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      initialize(d,f);val oldConsumer=BigInt(1,f.commandBytes.slice(16,32).reverse)&~(BigInt(65535)<<24)
      val stale=run(d,f,mutateFirst=Some(oldConsumer));stale._1 shouldBe Status.Dependency;stale._2 shouldBe 0;stale._3 shouldBe 0
      println("PUBLIC21_CURRENT_PARSER_REJECTION_PASS cases=short,tag,owner,metadata,unknown_opcode,stale_producer arithmetic=false")
    }
  }
}
