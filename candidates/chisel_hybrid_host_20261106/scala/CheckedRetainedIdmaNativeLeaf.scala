package heteronpu.continuous.model

import com.sun.jna.{Library, Native, Pointer}
import com.sun.jna.ptr.IntByReference

/** New checked-lifecycle copy of the original candidate JNA transport.
  * Only changes are independent class names, additive ABI validation and
  * checked destroy error propagation; original transport bit mapping preserved.
  * Experimental bridge to the real pre-existing iDMA RTL leaf only.
  * Only isolated candidate registration exists; scheduling qualification is outstanding.
  * Never reads fixture/reference files and never implements a memcpy fallback.
  */
trait CheckedIdmaLeafNative extends Library {
  def retained_idma_create(): Pointer
  def retained_idma_destroy_checked(handle: Pointer): Int
  def retained_idma_abi_version(): Int
  def retained_idma_response_words(): Int
  def retained_idma_request_words(): Int
  def retained_idma_drive(handle: Pointer, resetN: Int, requestValid: Int,
    source: Long, destination: Long, length: Int, responseReady: Int,
    readResponse: Array[Int], writeResponse: Array[Int]): Int
  def retained_idma_eval(handle: Pointer): Int
  def retained_idma_clock(handle: Pointer, level: Int): Int
  def retained_idma_read(handle: Pointer, requestReady: IntByReference,
    responseValid: IntByReference, responseError: IntByReference,
    busy: IntByReference, readRequest: Array[Int], writeRequest: Array[Int]): Int
}
final case class CheckedIdmaLeafOutputs(requestReady: Boolean, responseValid: Boolean,
  responseError: Boolean, busy: Int, readRequest: BigInt, writeRequest: BigInt)

final class CheckedRetainedIdmaNativeLeaf(verifiedLibraryPath: String, expectedLibrarySha256: String) extends AutoCloseable {
  require(expectedLibrarySha256.matches("[0-9a-f]{64}"),"explicit native library pin")
  private def libraryHash():String={
    val p=java.nio.file.Paths.get(verifiedLibraryPath)
    require(p.isAbsolute && java.nio.file.Files.size(p)<=512L*1024*1024,"bounded absolute library")
    val d=java.security.MessageDigest.getInstance("SHA-256")
    val in=java.nio.file.Files.newInputStream(p);val buf=new Array[Byte](8192)
    try {var n=in.read(buf);while(n != -1){d.update(buf,0,n);n=in.read(buf)}}finally{in.close()}
    d.digest().map(b=>f"${b&255}%02x").mkString
  }
  require(libraryHash()==expectedLibrarySha256,"actual native library bytes")
  private val api=Native.load(verifiedLibraryPath,classOf[CheckedIdmaLeafNative])
  require(libraryHash()==expectedLibrarySha256,"native library unchanged after load")
  require(api.retained_idma_abi_version()==1 && api.retained_idma_response_words()==17 && api.retained_idma_request_words()==25,"checked original iDMA native ABI")
  private val handle=api.retained_idma_create()
  require(handle!=null && Pointer.nativeValue(handle)!=0,"native leaf construction")
  private var closed=false
  private def check(code:Int):Unit=require(code==0,"real iDMA leaf API error "+code)
  private def open():Unit=require(!closed,"closed iDMA leaf")
  private def bit(x:Boolean):Int=if(x)1 else 0
  private def words(x:BigInt,width:Int):Array[Int]={
    require(x>=0 && x.bitLength<=width,"complete unsigned packed ABI")
    Array.tabulate((width+31)/32)(i=>((x>>(32*i))&BigInt("ffffffff",16)).toInt)
  }
  private def packed(x:Array[Int],width:Int):BigInt={
    val out=x.zipWithIndex.foldLeft(BigInt(0)){case(a,(v,i))=>a|(BigInt(v.toLong&0xffffffffL)<<(32*i))}
    require(out.bitLength<=width,"native output width");out
  }
  def drive(resetN:Boolean,requestValid:Boolean,source:BigInt,destination:BigInt,
    length:Long,responseReady:Boolean,readResponse:BigInt,writeResponse:BigInt):Unit={
    open();require(source>=0&&source.bitLength<=64&&destination>=0&&destination.bitLength<=64)
    require(length>=0&&length<=0xffffffffL)
    check(api.retained_idma_drive(handle,bit(resetN),bit(requestValid),source.toLong,
      destination.toLong,length.toInt,bit(responseReady),words(readResponse,532),words(writeResponse,532)))
  }
  def evaluate():Unit={open();check(api.retained_idma_eval(handle))}
  def clock(level:Boolean):Unit={open();check(api.retained_idma_clock(handle,bit(level)))}
  def read():CheckedIdmaLeafOutputs={
    open();val ready=new IntByReference;val valid=new IntByReference
    val error=new IntByReference;val busy=new IntByReference
    val read=new Array[Int](25);val write=new Array[Int](25)
    check(api.retained_idma_read(handle,ready,valid,error,busy,read,write))
    for(v<-Seq(ready.getValue,valid.getValue,error.getValue))require(v==0||v==1)
    require(busy.getValue>=0&&busy.getValue<=255)
    CheckedIdmaLeafOutputs(ready.getValue==1,valid.getValue==1,error.getValue==1,
      busy.getValue,packed(read,785),packed(write,785))
  }
  override def close():Unit={if(!closed){closed=true;check(api.retained_idma_destroy_checked(handle))}}
}
