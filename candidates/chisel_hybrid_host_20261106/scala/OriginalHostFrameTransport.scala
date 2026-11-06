package chiseltest.simulator

import java.io.{BufferedInputStream,BufferedOutputStream,DataInputStream,DataOutputStream}
import java.nio.{ByteBuffer,ByteOrder}
import java.security.MessageDigest
import treadle2.executable.ExecutionEngine

/** Exact production frame loop, separately callable only by package fixtures.
  * Production still enters through OriginalHostPinDriver.run and its unchanged
  * gate + exclusive Session.withEngine ownership. No gate-bypass option exists.
  */
private[simulator] object OriginalHostFrameTransport {
  import OriginalHostPorts._
  import OriginalHostPinDriver.Report
  private val schema=OriginalHostPorts.schemaSha.grouped(2).map(Integer.parseInt(_,16).toByte).toArray
  private def hex(b:Array[Byte])=b.map(x=>f"${x&255}%02x").mkString
  private def le(b:Array[Byte])=ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN)
  private def encode(value:BigInt,bytes:Int):Array[Byte]=Array.tabulate(bytes)(i=>((value>>(8*i))&255).toByte)
  private def decode(b:Array[Byte]):BigInt=BigInt(1,b.reverse)

  def serve(engine:ExecutionEngine,child:Process,maxFrames:Long):Report={
    OriginalHostPorts.verify(engine.ast)
    require(engine.getInputPorts.toSet==inputs.map(_.name).toSet,"only ALL original top input ports may be driven")
    require(engine.getOutputPorts.toSet==outputs.map(_.name).toSet,"ALL original top output ports returned")
    val in=new DataInputStream(new BufferedInputStream(child.getInputStream))
    val out=new DataOutputStream(new BufferedOutputStream(child.getOutputStream))
    val trace=MessageDigest.getInstance("SHA-256")
    var frames=0L;var lastTime=0L;var lastClock=0;var rises=0L;var falls=0L;var finalSeen=false
    var previousNonclock:Option[Map[String,BigInt]]=None
    var eof=false
    while(!eof){
      val first=in.read()
      if(first<0){eof=true;require(finalSeen,"driver EOF without unique complete final")}
      else {
        require(!finalSeen && frames<maxFrames,"bounded unique final frame")
        val header=new Array[Byte](60);header(0)=first.toByte;in.readFully(header,1,59)
        val h=le(header);require(h.getInt()==0x31545048,"pin protocol magic")
        val op=h.getInt();val seq=h.getLong();val time=h.getLong();val bytes=h.getInt()
        val receivedSchema=new Array[Byte](32);h.get(receivedSchema)
        require(seq==frames && time>=lastTime && java.util.Arrays.equals(schema,receivedSchema),"full schema/time/sequence identity")
        require((op==1 && bytes==inputBytes)||(op==2 && bytes==0 && frames>0),"exact bounded operation/payload")
        val payload=new Array[Byte](bytes);in.readFully(payload)
        trace.update(header);trace.update(payload)
        val result=if(op==2){finalSeen=true;Array.emptyByteArray}else {
          var offset=0
          val snapshot=inputs.map {p=>
            val value=decode(payload.slice(offset,offset+p.bytes));offset+=p.bytes
            require(value.bitLength<=p.width,"unsigned full input width")
            p.name->value
          }.toMap
          require(snapshot.size==41 && offset==payload.length,"one complete original snapshot")
          val level=snapshot("clock").toInt
          require(frames>0 || level==0,"first actual observed clock is low")
          val nonclock=snapshot-"clock"
          // The ORIGINAL full Host driver changes nonclock pins only while
          // already low. Transitions and repeated high evaluations hold them.
          // Reject broader, unqualified schedules before touching the engine.
          if(lastClock==1 || level==1)
            require(previousNonclock.contains(nonclock),"original Host schedule: stable nonclock pins across/high clock")
          // Each input is set ONCE. Treadle auto-evaluates a repeated setValue
          // before evaluateCircuit; uniqueness prevents partial-snapshot work.
          // Previous frame finished evaluation, so there are no pending pokes.
          inputs.filterNot(_.name=="clock").foreach(p=>engine.setValue(p.name,snapshot(p.name)))
          engine.setValue("clock",snapshot("clock"))
          engine.evaluateCircuit()
          require(!engine.inputsChanged,"completed evaluation before any output getter")
          val values=outputs.map {p=>
            val value=engine.getValue(p.name)
            require(value>=0 && value.bitLength<=p.width,"unsigned full output width")
            encode(value,p.bytes)
          }.foldLeft(Array.emptyByteArray)(_++_)
          if(lastClock==0 && level==1)rises+=1
          if(lastClock==1 && level==0)falls+=1
          lastClock=level;previousNonclock=Some(nonclock);values
        }
        val response=header.clone();le(response).putInt(24,result.length)
        trace.update(response);trace.update(result)
        out.write(response);out.write(result);out.flush()
        frames+=1;lastTime=time
      }
    }
    require(finalSeen && rises>0 && lastClock==0,"complete evaluated low terminal")
    Report(OriginalHostTreadleBinding.Engine,frames,rises,falls,hex(trace.digest()),-1,finalSeen,"","","")
  }

}
