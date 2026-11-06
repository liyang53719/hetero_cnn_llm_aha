package heteronpu.continuous.model
import com.sun.jna.{Library,Pointer}
import com.sun.jna.ptr.{IntByReference,LongByReference}
trait IcgLeafNative extends Library {
 def retained_icg_abi_version():Int
 def retained_icg_create():Pointer
 def retained_icg_destroy(handle:Pointer):Int
 def retained_icg_drive(handle:Pointer,enable:Int,testEnable:Int):Int
 def retained_icg_eval(handle:Pointer):Int
 def retained_icg_clock(handle:Pointer,level:Int):Int
 def retained_icg_read(handle:Pointer,clock:IntByReference):Int
 def retained_icg_edge_counts(handle:Pointer,p:LongByReference,n:LongByReference,gp:LongByReference,gn:LongByReference):Int
}
/** Real tc_clk_gating low-transparent latch, not a Scala gate implementation. */
final class RetainedIcgNativeLeaf(pin:NativeLibraryPin) extends AutoCloseable {
 private val api=pin.load(classOf[IcgLeafNative]);require(api.retained_icg_abi_version()==65536,"native ICG ABI")
 private val handle=api.retained_icg_create();NativeApiChecks.pointer(handle)
 private var closed=false
 private def open():Unit=require(!closed,"closed native ICG")
 def drive(enable:BigInt,testEnable:BigInt):Unit={open();NativeApiChecks.check(api.retained_icg_drive(handle,NativeApiChecks.bit(enable),NativeApiChecks.bit(testEnable)))}
 def evaluate():Unit={open();NativeApiChecks.check(api.retained_icg_eval(handle))}
 def clock(level:BigInt):Unit={open();NativeApiChecks.check(api.retained_icg_clock(handle,NativeApiChecks.bit(level)))}
 def read():BigInt={open();val o=new IntByReference;NativeApiChecks.check(api.retained_icg_read(handle,o));val v=BigInt(o.getValue);NativeApiChecks.bit(v);v}
 def edgeCounts:Vector[Long]={open();val r=Vector.fill(4)(new LongByReference);NativeApiChecks.check(api.retained_icg_edge_counts(handle,r(0),r(1),r(2),r(3)));r.map(_.getValue)}
 override def close():Unit={if(!closed){closed=true;NativeApiChecks.check(api.retained_icg_destroy(handle))}}
}
