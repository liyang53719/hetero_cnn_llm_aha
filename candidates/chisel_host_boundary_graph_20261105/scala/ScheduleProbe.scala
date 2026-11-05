package chiseltest.simulator

import java.io.{BufferedReader,File,FileInputStream,InputStream,InputStreamReader}
import java.net.JarURLConnection
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import firrtl2.options.Dependency
import firrtl2.passes.memlib.VerilogMemDelays
import firrtl2.stage.Forms
import firrtl2.transforms.BlackBoxSourceHelper
import treadle2.stage.phases.{HandleFormalStatements,PrepareAst}
import treadle2.utils.AugmentPrintf

/** Schedule discovery only: no CircuitState, circuit, transform execution or DUT. */
object ScheduleProbe {
  private var phase="ARGS"
  private var failure="UNEXPECTED"
  private def need(p:Boolean,code:String):Unit=if(!p){failure=code;throw new IllegalArgumentException()}
  private def hex(bytes:Array[Byte]):String={
    val digits="0123456789abcdef";val out=new Array[Char](bytes.length*2);var i=0
    while(i<bytes.length){val b=bytes(i)&255;out(i*2)=digits.charAt(b>>>4);out(i*2+1)=digits.charAt(b&15);i+=1}
    new String(out)
  }
  private def sha(s:String):String=hex(MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8)))
  private def validSha(s:String):Boolean=s!=null && s.length==64 && s.forall(c=>(c>='0' && c<='9') || (c>='a' && c<='f'))
  private def streamSha(in:InputStream,limit:Long):String={
    val digest=MessageDigest.getInstance("SHA-256");val buffer=new Array[Byte](8192);var total=0L
    try{var n=in.read(buffer)
      while(n>=0){need(n.toLong<=limit-total,"BYTES");if(n>0){digest.update(buffer,0,n);total+=n};n=in.read(buffer)}
      hex(digest.digest())
    }finally{in.close()}
  }
  private def fileSha(file:File,limit:Long):String={
    need(file.isFile && file.length()<=limit,"FILE")
    streamSha(new FileInputStream(file),limit)
  }
  private def canonical(path:String):File=new File(path).getCanonicalFile
  private def classPath(c:Class[_]):String={
    val name=c.getName;need(name.length>0 && name.length<=512,"CLASS")
    name.replace('.','/')+".class"
  }
  private def codeSource(c:Class[_]):File={
    val pd=c.getProtectionDomain;need(pd!=null && pd.getCodeSource!=null,"LOCATION")
    val location=pd.getCodeSource.getLocation;need(location!=null && location.getProtocol=="file","LOCATION")
    new File(location.toURI).getCanonicalFile
  }
  private def loadedJarSha(c:Class[_],expectedJar:File):String={
    need(codeSource(c)==expectedJar,"LOCATION")
    val path=classPath(c);val url=c.getResource("/"+path)
    need(url!=null && url.getProtocol=="jar","RESOURCE")
    val connection=url.openConnection();need(connection.isInstanceOf[JarURLConnection],"RESOURCE")
    val jar=connection.asInstanceOf[JarURLConnection];jar.setUseCaches(false)
    need(jar.getJarFileURL.getProtocol=="file" && new File(jar.getJarFileURL.toURI).getCanonicalFile==expectedJar &&
      jar.getEntryName==path,"RESOURCE")
    streamSha(jar.getInputStream,4L*1024*1024)
  }
  private def loadedProbeSha(c:Class[_],root:File):String={
    need(codeSource(c)==root,"LOCATION")
    val path=classPath(c);val expected=new File(root,path).getCanonicalFile
    need(expected.toPath.startsWith(root.toPath),"LOCATION")
    val url=c.getResource("/"+path);need(url!=null && url.getProtocol=="file","RESOURCE")
    need(new File(url.toURI).getCanonicalFile==expected,"RESOURCE")
    fileSha(expected,4L*1024*1024)
  }
  private def ordinal(s:String):Int={
    need(s.nonEmpty && s.length<=5 && (s.length==1 || s.charAt(0)!='0') && s.forall(c=>c>='0' && c<='9'),"CATALOG")
    val n=s.toInt;need(n<16384,"CATALOG");n
  }
  private def binaryName(s:String):Boolean=s.nonEmpty && s.length<=512 &&
    s.forall(c=>(c>='a' && c<='z') || (c>='A' && c<='Z') || (c>='0' && c<='9') || c=='_' || c=='$' || c=='.')
  private def item(i:Int,k:Int,h:String,jar:String):String=
    "PREPARE_SCHEDULE_ITEM_V1 i="+i+" k="+k+" sha="+h+" jar="+jar
  private def selfChecks():Int={
    need(sha("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SELFTEST")
    need(validSha("a"*64) && !validSha("A"*64) && !validSha("a"*63),"SELFTEST")
    need(item(255,16383,"a"*64,"TREADLE").getBytes(StandardCharsets.UTF_8).length*256+2048<32768,"SELFTEST")
    val d=MessageDigest.getInstance("SHA-256");d.update("a\n".getBytes(StandardCharsets.UTF_8));d.update("b\n".getBytes(StandardCharsets.UTF_8))
    need(hex(d.digest())==sha("a\nb\n"),"SELFTEST")
    4
  }
  def main(args:Array[String]):Unit={
    try{
      need(args.length==9,"ARGS")
      val catalogFile=canonical(args(0));val catalogSha=args(1)
      val firrtlJar=canonical(args(2));val firrtlSha=args(3)
      val treadleJar=canonical(args(4));val treadleSha=args(5)
      val probeRoot=canonical(args(6));val forwarderSha=args(7);val moduleSha=args(8)
      need(validSha(catalogSha) && validSha(firrtlSha) && validSha(treadleSha) && validSha(forwarderSha) && validSha(moduleSha),"HASH")
      need(probeRoot.isDirectory && firrtlJar!=treadleJar,"LOCATION")
      phase="IDENTITY"
      need(fileSha(firrtlJar,256L*1024*1024)==firrtlSha && fileSha(treadleJar,256L*1024*1024)==treadleSha,"HASH")
      need(fileSha(catalogFile,4L*1024*1024)==catalogSha,"HASH")
      val moduleClass=getClass
      val forwarder=Class.forName("chiseltest.simulator.ScheduleProbe",false,moduleClass.getClassLoader)
      need(loadedProbeSha(forwarder,probeRoot)==forwarderSha && loadedProbeSha(moduleClass,probeRoot)==moduleSha,"HASH")
      phase="CATALOG"
      val names=new Array[String](16384);val nameHashes=new Array[String](16384)
      val hashes=new Array[String](16384);val jars=new Array[String](16384);var count=0
      val reader=new BufferedReader(new InputStreamReader(new FileInputStream(catalogFile),StandardCharsets.UTF_8))
      try{var line=reader.readLine()
        while(line!=null){
          need(count<16384 && line.length<=1024,"CATALOG")
          val fields=line.split("\t",-1);need(fields.length==4 && ordinal(fields(0))==count && binaryName(fields(1)) &&
            validSha(fields(2)) && (fields(3)=="FIRRTL" || fields(3)=="TREADLE"),"CATALOG")
          val nameHash=sha(fields(1));need(count==0 || nameHashes(count-1).compareTo(nameHash)<0,"CATALOG")
          names(count)=fields(1);nameHashes(count)=nameHash;hashes(count)=fields(2);jars(count)=fields(3);count+=1
          line=reader.readLine()
        }
      }finally{reader.close()}
      need(count>0,"CATALOG")
      def verify(c:Class[_]):Int={
        val n=c.getName;need(binaryName(n),"CLASS");val h=sha(n);var lo=0;var hi=count-1;var found = -1
        while(lo<=hi && found<0){val mid=lo+(hi-lo)/2;val cmp=nameHashes(mid).compareTo(h)
          if(cmp==0)found=mid else if(cmp<0)lo=mid+1 else hi=mid-1}
        need(found>=0 && names(found)==n,"CATALOG")
        val expected=if(jars(found)=="FIRRTL")firrtlJar else treadleJar
        need(loadedJarSha(c,expected)==hashes(found),"HASH");found
      }
      phase="IDENTITY"
      val prepare=verify(classOf[PrepareAst]);val compiler=verify(classOf[firrtl2.stage.transforms.Compiler]);val augment=verify(classOf[AugmentPrintf])
      val tests=selfChecks()
      phase="SCHEDULE"
      // Exact pinned PrepareAst source recipe. Do not add observer transforms,
      // wrappers, annotations, knownObjects, or replace this flattened-order API.
      val targets = Seq(
        Dependency(firrtl2.transforms.EnsureNamedStatements),
        Dependency[BlackBoxSourceHelper],
        Dependency[AugmentPrintf],
        Dependency[HandleFormalStatements]
      ) ++ Forms.LowFormOptimized ++
        Seq(Dependency(VerilogMemDelays))
      val manager = new firrtl2.stage.transforms.Compiler(targets, currentState = Nil)
      val transforms = manager.flattenedTransformOrder
      val indices=new Array[Int](256);var total=0;var augmentIndex = -1;var augmentCount=0
      val iterator=transforms.iterator
      while(iterator.hasNext){
        need(total<256,"COUNT");val transform=iterator.next();val c=transform.getClass;indices(total)=verify(c)
        if(c==classOf[AugmentPrintf]){augmentIndex=total;augmentCount+=1};total+=1
      }
      need(total>0 && augmentCount==1,"AUGMENT")
      // Buffer only finite metadata. No output until all identity/order checks pass.
      val rows=new Array[String](total);val digest=MessageDigest.getInstance("SHA-256");var i=0;var bytes=0
      while(i<total){val k=indices(i);val line=item(i,k,hashes(k),jars(k));rows(i)=line
        val encoded=(line+"\n").getBytes(StandardCharsets.UTF_8);digest.update(encoded);bytes+=encoded.length;i+=1}
      val idRows=Array(
        "PREPARE_SCHEDULE_ID_V1 role=PREPARE sha="+hashes(prepare)+" jar="+jars(prepare),
        "PREPARE_SCHEDULE_ID_V1 role=COMPILER sha="+hashes(compiler)+" jar="+jars(compiler),
        "PREPARE_SCHEDULE_ID_V1 role=AUGMENT sha="+hashes(augment)+" jar="+jars(augment),
        "PREPARE_SCHEDULE_ID_V1 role=PROBE sha="+moduleSha+" jar=PROBE")
      val summary="PREPARE_SCHEDULE_V1 pass=true count="+total+" augmentIndex="+augmentIndex+
        " augmentCount="+augmentCount+" orderSha="+hex(digest.digest())+" selfChecks="+tests
      i=0;while(i<idRows.length){bytes+=(idRows(i)+"\n").getBytes(StandardCharsets.UTF_8).length;i+=1}
      bytes+=(summary+"\n").getBytes(StandardCharsets.UTF_8).length;need(bytes<=32768,"OUTPUT")
      phase="EMIT";idRows.foreach(println);rows.foreach(println);println(summary)
    }catch{case _:Throwable=>
      println("PREPARE_SCHEDULE_FAILURE_V1 phase="+phase+" code="+failure)
      System.exit(1)
    }
  }
}
