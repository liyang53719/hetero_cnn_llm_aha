package chiseltest.simulator

import java.io.{File,FileInputStream,InputStream}
import java.net.JarURLConnection
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import firrtl2.Transform
import treadle2.stage.phases.PrepareAst
import treadle2.utils.AugmentPrintf

/** Exact schedule identity from qualified probe42013546414; does not execute a transform. */
object ObservedScheduleIdentity {
  private def need(p:Boolean,code:String):Unit=if(!p)throw new IllegalArgumentException("OBSERVED_SCHEDULE_"+code)
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
  private val expected=Array(
    ("d378e8d14425b6322c0bcb7d788c8e5f1bb275ee4348ad5e10479a8b969a8e34","e080c1c764b0d4e20d5e4c93d88d4ad762764cbfca3385da782a565ccda0f930","FIRRTL",2466),
    ("7edcd96e85f9da8aa89a6aaa224ce6ab4cbea56a6d27f8587fe658e21a71f41e","c6d91f6ebce4f0edba4003cd91445da6ab6e8dc408fbd5ecf682bd5eaffd6393","FIRRTL",1479),
    ("ce790c012493f582da089d58de66b283d4c9e94c421a0f30105a8c1d9fc28092","cd9e3f3a0c6cfd4a823775414fd8542b3f247668f253456277d3c717372daffe","FIRRTL",2410),
    ("7a31b0e5d50f47b2a87720a92838674b95a40d5327e278dcacd5c7bc6535ebdd","c1779992fb27f6b95404575d91c8e97f5cbc78371286ea918f4fba61f5930bea","FIRRTL",1416),
    ("de43dbac932c8214bb86ffd772c83de20059d1fcdce5b8a347f971f2e8b04478","c82784171af9af491f8a71ae7209273b8588481c5fa24acba3e55cdd58825397","FIRRTL",2596),
    ("7cb638941766df64bb9461ab557483d9ffa7e8f7c7c53f3cbea85920c06d78ec","4075fdd633ab9615b62a6370eb1fe0eb27c5cbaa4c1794fd863306c0835ab01f","FIRRTL",1444),
    ("5a841dca080eb858c0d484f794f358ea6b0e8c0d610ba060aed7daa00a31c949","696bcfdee5a44bd4badf94144a2c9ad217eea222c180731d8cb3d016b5a474e4","FIRRTL",1066),
    ("f1d69df9772bb446b77947772b991877db2b5aa3af8d1f1b34ee231c0820af12","da1c563858995423ced07a50bb5b24ea6878c3299de5ceb9e94a012caeb88022","FIRRTL",2838),
    ("3ee26d0911995f966409cfdd50ef8cf7f5611cf1258cb1447bfab0db06e76e96","bf56e7df6bfe7e822e29a5bffac5a156d78b30070eea28898dbd533cd054f847","FIRRTL",750),
    ("c35de9f754b70c50b2024b3e47424c8ee31c2008e2a336fffb5a6d96a4aa8c32","6cecd31bfb8fc4297b8ecc78ec925b46c4e088498fbb9f5dcb16165b56e2cbc8","FIRRTL",2276),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("583264eed46b021b475a8a51b97d58dadeefb91c336859dc65add53eb5928c63","dce2d6d21cdbda9274d3de26c40dab5e4c1fd9feaa7a61d5f1c7d88fff21eea5","FIRRTL",1041),
    ("3ac3c8a94031f0c1e77883ea1a6b549345bf13bca54d3cf1da67465872f1a674","e9259eb06cf4591169157aed6b8727cd47966717aabfa89be9d38bcb4803d7f5","FIRRTL",693),
    ("b02c6ac9ff174a79f83827544577d46e113eeb1c66c550b2aa11fd185d700be3","1dc0cf86261866aa763143816c9c72943fac9d24b44d1eca8f8703b245e4a267","FIRRTL",2060),
    ("9c0b71a6a161e9c9bbaec79ccbb487175e557a6b4b13f87eb5ab9ca99a4f5156","a4189fdfec429050479aab7cca0fd8a8ca5be88e7282993987cd2f4281b2ee24","FIRRTL",1838),
    ("c35de9f754b70c50b2024b3e47424c8ee31c2008e2a336fffb5a6d96a4aa8c32","6cecd31bfb8fc4297b8ecc78ec925b46c4e088498fbb9f5dcb16165b56e2cbc8","FIRRTL",2276),
    ("c100b2f411e4a542c642d19dfe5b98fc61ea8462e1ddd6f1146c39dc74ebc95e","6a6081de43dfcb1ffab90e917816395b2410059e7ee24ed419c910f32bfe81b0","FIRRTL",2252),
    ("b6341fd95f9485a2eaded54a93e0682ca6e474bf98a85777ce27371135d7ea10","5b26315cc5eaa2afe0df15889b8f6304697b308e5dd5c77767dd56568dff5350","FIRRTL",2128),
    ("1b32242eaa16c1760208361461ba390155cf30c3cefb565f6bff20db0678f1b3","1bed19bcaaeea23437001c661d558dac90dc74da2d503af29dd899a176c82258","FIRRTL",314),
    ("67f421527ac70f8c2c6ed11e0d06d03b0254086576b5d919e6ff01e7075bfe5e","fc9c4fbd80bb839043f46ee1f20d83598b68f7a26d6a4b5311ab09ffd909e512","FIRRTL",1213),
    ("482967124a384a7fcd0049821ad44bd99f7ba7c40275cdd6d3374f18c15b53e1","2afc158aa43bf8072b2013ea8025e644cec9b94e2bb2f154de18e70311be5698","FIRRTL",863),
    ("b7eb26113aab0930d6e12b73c56d66abf3c9583cb42277d13ecb76146943dabc","28d738a2bcbe0a9da3bc58ff5a6bbc03583bc4a7cefe85dc3b7ce3756a9d4ce9","FIRRTL",2147),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("c33434ede6325b6cb5cdf964aad3f680d013fb8f8e1b3742ae29c8ca33583afd","2a12119d4cf07c14f81f36daf2a942917953f1c8b9354a293f72ee937e6bf1ee","FIRRTL",2274),
    ("f1d69df9772bb446b77947772b991877db2b5aa3af8d1f1b34ee231c0820af12","da1c563858995423ced07a50bb5b24ea6878c3299de5ceb9e94a012caeb88022","FIRRTL",2838),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("39a7eacaf49cc3406a8612e1e3d1a5ef5c493fc131abcdc3a044fe8458f85761","d7ebc7ddc91d0a394d0f9b049873ae0298d3e3c039ee93b6b8578b1a1aef62ec","FIRRTL",683),
    ("f1d69df9772bb446b77947772b991877db2b5aa3af8d1f1b34ee231c0820af12","da1c563858995423ced07a50bb5b24ea6878c3299de5ceb9e94a012caeb88022","FIRRTL",2838),
    ("3ee26d0911995f966409cfdd50ef8cf7f5611cf1258cb1447bfab0db06e76e96","bf56e7df6bfe7e822e29a5bffac5a156d78b30070eea28898dbd533cd054f847","FIRRTL",750),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("3ac3c8a94031f0c1e77883ea1a6b549345bf13bca54d3cf1da67465872f1a674","e9259eb06cf4591169157aed6b8727cd47966717aabfa89be9d38bcb4803d7f5","FIRRTL",693),
    ("ea355a22abcf065a42a3cd5892fe7cf2b621202755d9a332b4980094e03d47a3","9fdc28e15db22ef7fd12decc8b7a7b0cc83c0863d3295c4645c538604d47e6ed","FIRRTL",2740),
    ("3ee26d0911995f966409cfdd50ef8cf7f5611cf1258cb1447bfab0db06e76e96","bf56e7df6bfe7e822e29a5bffac5a156d78b30070eea28898dbd533cd054f847","FIRRTL",750),
    ("5e4d7ecc2e6bca1fdbb1434d3adddb7f536053038188e46d95560b6bbc80406d","fa2f8dcc2902f5cfab04676c716c84409568d543829189694ea4bd8f2ffcab0d","FIRRTL",1103),
    ("044711e1765c048f99b151954f6dbaa72252e93aac57c3ed8d8dc85a877c1b1e","2080860c03139cd8291fb8ecd31c8ae9f8f65e7f1845305163ac9619e6d083d1","FIRRTL",48),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("3468f5996896e3004fc9153b44f517f7f0ccb6eb7f8fa6ca55e19f5215ff252b","2f93549609a2de13ef2757f3caf48af8fb02f33b6596a8a147b1dea18e1bfa19","FIRRTL",621),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533),
    ("ac1ff58c568b87bc174b7e127ef24ef2f5738918c1bd0f83e9d44d6312d1028f","ac842fc86b0cb5dd64e70bd5806a1ff1df9a52b776342e4f41fd75cfb0a7fd71","FIRRTL",2003),
    ("af2d65fc1d9d88c841f87b21b8911edb8625f6fd2e3ee10e2224f2c8b8b7a0c8","1a029c4e740ad91d8dd690fd384e164d0f36467c7020fda3f17b731ba8a4dd2d","FIRRTL",2044),
    ("adb479108d2116791d4ca90c3ed7a370f3030355290b5937a3b52de82cf58fc4","78961fe4ca756a35ca56deaed01b3e3431c65fe542419f6db5c3eda12b44c7fb","FIRRTL",2021),
    ("874b0d896425b3a2ca30c4e6bb3fb52e3c23e40d91e9b48570ec61e3d25531f4","32b475562366adbfc1cdbbd83419dc49a70f6b1d101a618a0281638ad4a4c0be","FIRRTL",1585),
    ("f1d69df9772bb446b77947772b991877db2b5aa3af8d1f1b34ee231c0820af12","da1c563858995423ced07a50bb5b24ea6878c3299de5ceb9e94a012caeb88022","FIRRTL",2838),
    ("ac82577e71073ea64b046017a7ab54bb8009d55bc9ed1891a544158c12da22e3","ffd806e7b99d5b9de3fb66b9aa59642742f651388bb9b4c9879122a71bbf66f3","FIRRTL",2012),
    ("bcb2f56674c1d96eea58222a00ef4a9468e9021ae6e262610629f7af197c2ae3","909fe6e45928c87b9449c09f02a845d834266d57bbe71c03227d27aad9e35406","FIRRTL",2203),
    ("2750d597b939b410daa1fd3fcd991a3b7d7c570095c47ce6c7a6bf02e81d65f9","d258e57ef3f08397ed918119302c6f64a02435899b9b088c760bfeb798443f8b","FIRRTL",468),
    ("a894435bdee63bce9985b19285ed0a53ecbb14b314785c58f5e42517673d65e6","0ecaecf2dddc761ea60d6685840ccacdd7e767add047b0abe669a6e6fd02ba4a","FIRRTL",1968),
    ("fbed171db0f27533312ce49be1a7e462084b80317b736ce773e6e92a093b68ca","9e4754190d89998b2690005d563766f67b0708aee78f702054e9f2a568eb1be1","FIRRTL",2963),
    ("1637710561bc60cd8f89b649ad398a82f1cf1bc5c0a0d175d783b68b4e141ab8","415f283db80b6131d49cdb7c099b4bc35af3b57a2f8ae1a4a0be816e1f15fa75","FIRRTL",264),
    ("f1d69df9772bb446b77947772b991877db2b5aa3af8d1f1b34ee231c0820af12","da1c563858995423ced07a50bb5b24ea6878c3299de5ceb9e94a012caeb88022","FIRRTL",2838),
    ("0658043d973d17626f2deb15cef7ed7957e2218638340c649e1fa6b59a6e89d6","7f301f9ce78f365d712f3acdf89bd0323823af6c157514bf5c030622e08ad1c5","FIRRTL",63),
    ("459de89d1794e74214a599c4904324f5bed5e8c37a3fb8335a2b5470eaaea953","f532d1171ed8bbd4200ae9bf6f75b571951b7d4518bfd2a95706fdcf0ef8a19e","TREADLE",841),
    ("4d21e8f015a254426450963acb495135922ba55f27dda786cc64fc5dac8825c9","0b6c305f8e1d9f37dc005bedd94049528c49c16bd07e030c1057edfd7ebcf0d4","TREADLE",923),
    ("09ec008877fed77f83fc84332c08f4a76794a6e2ab4a777a7d4696c00ed148e8","7d6799b5a853b702f2b1f669d31fd37a2a71092940292113401dac3f24440e15","FIRRTL",98),
    ("d92b7b6e5aa9b3b4b98fbd1181c86a7db0eaef95653b46d68accea3b020db24c","9c4f63d72929620d75a6bac4df8a37b94185f6c5438809e10ab67a650b451b66","FIRRTL",2533)
  )
  val count=55
  val augmentIndex=51
  val orderSha="de03a5c28363ea8bef354d1ecc34dfaed65dbe0481618c75925b773a55f2130c"
  val catalogSha="cdfb68914d7c421df167a2dd26103c426164dc13dbc85ffbd279c81d130ea31c"
  // Fixed annotation identity prerequisite, no annotation values or transform execution.
  def verifyAnnotationOwner():Unit={
    val firrtl=codeSource(classOf[firrtl2.stage.transforms.Compiler])
    need(fileSha(firrtl,256L*1024*1024)=="80fae7cd4516e6fe33469c2e135479f2c94bf9e5be4d00437de2df68ba40b47b","HASH")
    need(loadedJarSha(classOf[firrtl2.transforms.DedupedResult],firrtl)=="0e322fb86c30ab41e20deb486303a3168f9d29d0ba0a258ea742c94673d0fd8d","HASH")
  }
  def verify(transforms:Seq[Transform]):Unit={
    val firrtl=codeSource(classOf[firrtl2.stage.transforms.Compiler])
    val treadle=codeSource(classOf[PrepareAst])
    need(firrtl!=treadle,"LOCATION")
    need(fileSha(firrtl,256L*1024*1024)=="80fae7cd4516e6fe33469c2e135479f2c94bf9e5be4d00437de2df68ba40b47b","HASH")
    need(loadedJarSha(classOf[firrtl2.transforms.DedupedResult],firrtl)=="0e322fb86c30ab41e20deb486303a3168f9d29d0ba0a258ea742c94673d0fd8d","HASH")
    need(fileSha(treadle,256L*1024*1024)=="3d442dab6f28e74980f598dd4bd28c886f4e081d0e5433102dfc02aab1c57dc5","HASH")
    need(loadedJarSha(classOf[PrepareAst],treadle)=="8296f250758abb66c154106fa7b02eb59b2bae7087539b9de18a38ba47d95fbb","HASH")
    need(loadedJarSha(classOf[firrtl2.stage.transforms.Compiler],firrtl)=="99e096dca012ccd18ec4f5881761fd3fac0b1b55a04eeb9e88a8609620f1f782","HASH")
    need(loadedJarSha(classOf[AugmentPrintf],treadle)=="f532d1171ed8bbd4200ae9bf6f75b571951b7d4518bfd2a95706fdcf0ef8a19e","HASH")
    var index=0;var augmentCount=0;val digest=MessageDigest.getInstance("SHA-256")
    val iterator=transforms.iterator
    while(iterator.hasNext){
      need(index<55,"COUNT")
      val transform=iterator.next();val c=transform.getClass;val row=expected(index)
      need(c.getName.length>0 && c.getName.length<=512,"CLASS")
      need(sha(c.getName)==row._1,"ORDER")
      val location=if(row._3=="FIRRTL")firrtl else treadle
      need(loadedJarSha(c,location)==row._2,"HASH")
      if(c==classOf[AugmentPrintf]){need(index==51,"AUGMENT");augmentCount+=1}
      val line="PREPARE_SCHEDULE_ITEM_V1 i="+index+" k="+row._4+" sha="+row._2+" jar="+row._3+"\n"
      digest.update(line.getBytes(StandardCharsets.UTF_8));index+=1
    }
    need(index==55 && augmentCount==1 && hex(digest.digest())==orderSha,"ORDER")
  }
}
