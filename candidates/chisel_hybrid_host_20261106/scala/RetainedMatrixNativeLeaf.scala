package heteronpu.continuous.model
import com.sun.jna.{Library,Pointer}
import com.sun.jna.ptr.LongByReference
trait MatrixLeafNative extends Library {
 def retained_matrix_abi_version():Int
 def retained_matrix_contract_sha256():String
 def retained_matrix_create():Pointer
 def retained_matrix_destroy(handle:Pointer):Int
 def retained_matrix_drive(handle:Pointer,words:Array[Int],count:Int):Int
 def retained_matrix_eval(handle:Pointer):Int
 def retained_matrix_clock(handle:Pointer,level:Int):Int
 def retained_matrix_read(handle:Pointer,words:Array[Int],count:Int):Int
 def retained_matrix_edge_counts(handle:Pointer,positive:LongByReference,negative:LongByReference):Int
}
/** One independent generated RTL endpoint. Never contains floating-point arithmetic. */
final class RetainedMatrixNativeLeaf(pin:NativeLibraryPin) extends AutoCloseable {
 private val api=pin.load(classOf[MatrixLeafNative])
 require(api.retained_matrix_abi_version()==MatrixNativeLayout.abiVersion,"native Matrix ABI")
 require(api.retained_matrix_contract_sha256()==MatrixNativeLayout.contractSha256,"native Matrix port contract")
 private val handle=api.retained_matrix_create();NativeApiChecks.pointer(handle)
 private var closed=false
 private def open():Unit=require(!closed,"closed native Matrix endpoint")
 def drive(values:Map[String,BigInt]):Unit={open();val w=MatrixNativeLayout.encode(values);NativeApiChecks.check(api.retained_matrix_drive(handle,w,w.length))}
 def evaluate():Unit={open();NativeApiChecks.check(api.retained_matrix_eval(handle))}
 def clock(level:BigInt):Unit={open();NativeApiChecks.check(api.retained_matrix_clock(handle,NativeApiChecks.bit(level)))}
 def read():Map[String,BigInt]={open();val w=new Array[Int](MatrixNativeLayout.outputWords);NativeApiChecks.check(api.retained_matrix_read(handle,w,w.length));MatrixNativeLayout.decode(w)}
 def edgeCounts:(Long,Long)={open();val p=new LongByReference;val n=new LongByReference;NativeApiChecks.check(api.retained_matrix_edge_counts(handle,p,n));(p.getValue,n.getValue)}
 override def close():Unit={if(!closed){closed=true;NativeApiChecks.check(api.retained_matrix_destroy(handle))}}
}
