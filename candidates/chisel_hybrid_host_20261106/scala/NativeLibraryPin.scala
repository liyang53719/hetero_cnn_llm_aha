package heteronpu.continuous.model
import com.sun.jna.{Library,Native,Pointer}
import java.nio.file.{Files,Paths}
/** The path and hash are actual library bytes, not a qualification token. */
final case class NativeLibraryPin(path:String,sha256:String) {
 require(Paths.get(path).isAbsolute,"absolute native library path")
 require(sha256.matches("[0-9a-f]{64}"),"explicit native library SHA-256")
 def verify():Unit={
  val p=Paths.get(path);require(Files.isRegularFile(p)&&Files.size(p)>0&&Files.size(p)<=512L*1024*1024,"bounded native library")
  val d=java.security.MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(p);val buf=new Array[Byte](8192)
  try{var n=in.read(buf);while(n!= -1){d.update(buf,0,n);n=in.read(buf)}}finally{in.close()}
  require(d.digest().map(b=>f"${b&255}%02x").mkString==sha256,"actual native library bytes")
 }
 def load[T<:Library](kind:Class[T]):T={verify();val api=Native.load(path,kind);verify();api}
}
private[model] object NativeApiChecks {
 def check(code:Int):Unit=require(code==0,"native original RTL API status "+code)
 def pointer(p:Pointer):Unit=require(p!=null&&Pointer.nativeValue(p)!=0,"native original RTL construction")
 def bit(x:BigInt):Int={require(x==0||x==1,"one-bit native value");x.toInt}
 def quoted(x:String):String="\""+x.flatMap{
  case '"'=>"\\\"";case '\\'=>"\\\\";case c if c<' '=>f"\\u${c.toInt}%04x";case c=>c.toString}+"\""
}
