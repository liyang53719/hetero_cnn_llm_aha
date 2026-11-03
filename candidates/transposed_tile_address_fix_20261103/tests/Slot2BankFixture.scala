// Test-only observability. Production bank implementation, geometry and ports
// are inherited unchanged from the exact source selected by the run plan.
package heteronpu.continuous
import chisel3._

class Slot2BankFixture extends TransposedDownDenseBanks(
    enableFfnTiles=true, enableMatrixProducerOrder=true) {
  val diagnostic=IO(Output(new Bundle {
    val issueRead=Bool();val issueWrite=Bool();val issueWord=UInt(11.W);val issueLane=UInt(3.W)
    val commit=Bool();val commitWord=UInt(11.W);val commitLane=UInt(3.W)
    val activationPacked=UInt(2048.W);val tilePacked=UInt(512.W)
  }))
  val observe=tileSignals.get
  diagnostic.issueRead:=observe.issueRead;diagnostic.issueWrite:=observe.issueWrite
  diagnostic.issueWord:=observe.word;diagnostic.issueLane:=observe.lane
  diagnostic.commit:=observe.commit;diagnostic.commitWord:=observe.commitWord
  diagnostic.commitLane:=observe.commitLane
  diagnostic.activationPacked:=io.response.bits.activation.asUInt
  diagnostic.tilePacked:=io.tiles.get.response.bits.value.asUInt
}
