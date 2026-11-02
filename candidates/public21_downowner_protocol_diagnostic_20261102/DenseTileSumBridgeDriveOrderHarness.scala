// Test-only observation of the original bridge; no production source changes.
package heteronpu.continuous
import chisel3._
import chisel3.util.experimental.BoringUtils
class DenseTileSumBridgeDriveOrderHarness extends Module {
  val bridge=Module(new DenseTileSumBridge(enableMatrixProducerOrder=true))
  val io=IO(chiselTypeOf(bridge.io));io<>bridge.io
  val diagnostic=IO(Output(new Bundle {val inflight=Bool();val unexpected=Bool()}))
  diagnostic.inflight:=false.B;diagnostic.unexpected:=false.B
  BoringUtils.addSource(bridge.inflight,"bridge_order_inflight");BoringUtils.addSink(diagnostic.inflight,"bridge_order_inflight")
  BoringUtils.addSource(bridge.unexpected,"bridge_order_unexpected");BoringUtils.addSink(diagnostic.unexpected,"bridge_order_unexpected")
}
