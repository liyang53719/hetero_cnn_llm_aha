from pathlib import Path
import json,hashlib,re
ROOT=Path(__file__).resolve().parents[1]
ORACLE=ROOT/'reference/CONTRACT.json'
raw=ORACLE.read_bytes()
if hashlib.sha256(raw).hexdigest()!='721b8eb2d2c3ff668320ca5eac98b8f64f892abb36bb1833d7c4cdf0dafa9faf': raise ValueError('independent oracle identity')
c=json.loads(raw); source=(ROOT/'source/UnifiedRuntimeProfile.scala').read_text()
widths={k:int(v) for k,v in re.findall(r'val (\w+) = UInt\((\d+)\.W\)',source)}
if widths!=c['fields']:raise ValueError(('field contract',widths,c['fields']))
names=['Qwen2Attention','Qwen35SmallGdn','Qwen35SmallAttention','Qwen35MoeGdn','Qwen35MoeAttention']
for i,name in enumerate(names):
 body=re.search(r'is\(UnifiedProfileId\.'+name+r'\.U\) \{(.*?)\n      \}',source,re.S).group(1)
 p={k:0 for k in widths};p['profileId']=i
 for k,v in re.findall(r'p\.(\w+) := (\d+)\.U',body):p[k]=int(v)
 if p!=c['profiles'][i]:raise ValueError(('profile mismatch',name,p,c['profiles'][i]))
vectors_raw=(ORACLE.parent/'ADMISSION_VECTORS.json').read_bytes()
vectors=json.loads(vectors_raw)['vectors']
def scala_bigint(v):
    return 'BigInt(%d)'%v if -2147483648<=v<=2147483647 else 'BigInt("%d")'%v
vector_rows=',\n'.join('    ("%s", Map(%s), %s, %s)'%(v['name'], ', '.join('"%s" -> %s'%(k,scala_bigint(val)) for k,val in v['launch'].items() if k!='cold'), str(v['launch']['cold']).lower(),str(v['admitted']).lower()) for v in vectors)
rows=',\n'.join('    Map('+', '.join('"%s" -> BigInt(%d)'%(k,v) for k,v in r.items())+')' for r in c['profiles'])
spec='''// SPDX-License-Identifier: Apache-2.0
// Expected table generated from independently config-derived CONTRACT_r2.json.
// This test has one DUT instance, no per-profile elaboration, and no MAC claims.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

class UnifiedBlockAdmissionSpec extends AnyFlatSpec with ChiselScalatestTester {
  private val expected = Seq(
'''+rows+'''
  )
  private val vectors = Seq(
'''+vector_rows+'''
  )
  behavior of "one fixed UnifiedBlockAdmission"
  it should "latch all five profiles without reset and fail closed on invalid jobs" in {
    test(new UnifiedBlockAdmission).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      var clocks = 0
      var acceptedLaunches = 0
      def tick(n: Int = 1): Unit = for (_ <- 0 until n) {
        assert(clocks < 4999, "5000 total including one framework reset")
        d.clock.step(); clocks += 1
      }
      d.clock.setTimeout(4999)
      def drive(id: Int, tag: Int): Unit = {
        val j=d.io.launch.bits
        j.version.poke(1.U); j.opcode.poke(0.U); j.profileId.poke(id.U)
        j.tag.poke(tag.U); j.tokens.poke(128.U); j.positionBase.poke(0.U)
        j.cacheCapacity.poke((if (id==0 || id==2 || id==4) 128 else 0).U)
        j.cacheLength.poke(0.U); j.expectedGeneration.poke(7.U); j.cold.poke(true.B)
        j.input.poke(0x10000.U); j.weights.poke(0x20000.U)
        j.output.poke(0x30000.U); j.scratch.poke(0x40000.U)
        j.stateIn.poke(0x50000.U); j.stateOut.poke(0x60000.U)
        j.kvK.poke(0x70000.U); j.kvV.poke(0x80000.U)
      }
      def expectProfile(id: Int): Unit = expected(id).foreach { case (name,value) =>
        d.io.context.profile.elements(name).asInstanceOf[UInt].expect(value.U)
        d.io.dispatch.bits.profile.elements(name).asInstanceOf[UInt].expect(value.U)
      }
      def launch(): Unit = {
        d.io.launch.valid.poke(true.B); d.io.launch.ready.expect(true.B)
        tick(); acceptedLaunches += 1; d.io.launch.valid.poke(false.B)
      }
      def consumeResult(status: Int, id: Int, tag: Int): Unit = {
        d.io.result.valid.expect(true.B)
        for (_ <- 0 until 3) {
          d.io.result.bits.version.expect(1.U); d.io.result.bits.status.expect(status.U)
          d.io.result.bits.profileId.expect(id.U); d.io.result.bits.tag.expect(tag.U)
          d.io.launch.ready.expect(false.B); tick()
        }
        d.io.result.ready.poke(true.B); tick(); d.io.result.ready.poke(false.B)
        d.io.result.valid.expect(false.B)
      }
      drive(0,0); d.io.launch.valid.poke(false.B); d.io.dispatch.ready.poke(false.B)
      d.io.result.ready.poke(false.B); d.io.completion.valid.poke(false.B)
      d.io.completion.bits.transactionId.poke(0.U)
      d.io.completion.bits.tag.poke(0.U); d.io.completion.bits.profileId.poke(0.U)
      d.io.completion.bits.status.poke(0.U); d.io.completion.bits.drained.poke(true.B)
      d.io.completion.bits.resetRequired.poke(false.B)
      d.io.completion.bits.acknowledgedWriteBytes.poke(64.U)
      d.io.completion.bits.issuedSliceSteps.poke(8.U)
      d.reset.poke(true.B); tick(2); d.reset.poke(false.B)

      // Five profiles, one physical DUT, no reset between transactions.
      for (id <- 0 until 5) {
        val tag=100+id; drive(id,tag); launch()
        d.io.dispatch.valid.expect(true.B); expectProfile(id)
        for (_ <- 0 until 3) {
          drive((id+1)%5,999); d.io.launch.valid.poke(true.B)
          d.io.launch.ready.expect(false.B); d.io.context.launch.tag.expect(tag.U)
          d.io.context.launch.tokens.expect(128.U); expectProfile(id); tick()
        }
        d.io.launch.valid.poke(false.B)
        d.io.dispatch.ready.poke(true.B); tick(); d.io.dispatch.ready.poke(false.B)
        d.io.dispatch.valid.expect(false.B); d.io.completion.ready.expect(true.B)
        tick(2); expectProfile(id)
        d.io.completion.bits.transactionId.poke(id.U)
        d.io.completion.bits.profileId.poke(id.U); d.io.completion.bits.tag.poke(tag.U)
        d.io.completion.valid.poke(true.B); tick(); d.io.completion.valid.poke(false.B)
        d.io.result.bits.acknowledgedWriteBytes.expect(64.U)
        d.io.result.bits.issuedSliceSteps.expect(8.U); d.io.resetRequired.expect(false.B)
        consumeResult(0,id,tag)
      }
      // Fresh jobs are rejected without dispatch; no unsigned wraparound.
      for (bad <- 0 until 13) {
        val id=if (bad==2) 5 else if (bad==10) 6 else if (bad==11) 7 else 0; val tag=200+bad; drive(id,tag)
        bad match {
          case 0 => d.io.launch.bits.version.poke(2.U)
          case 1 => d.io.launch.bits.opcode.poke(16.U)
          case 2 => ()
          case 3 => d.io.launch.bits.tokens.poke(0.U)
          case 4 => d.io.launch.bits.tokens.poke(129.U)
          case 5 => d.io.launch.bits.positionBase.poke(BigInt("ffffffff",16).U)
          case 6 => d.io.launch.bits.cacheLength.poke(BigInt("ffffffff",16).U)
          case 7 => d.io.launch.bits.cacheCapacity.poke(32769.U)
          case 8 => d.io.launch.bits.input.poke(0x10001.U)
          case 9 => d.io.launch.bits.kvV.poke(0x80001.U)
          case 10 | 11 => ()
          case 12 => d.io.launch.bits.cacheLength.poke(1.U); d.io.launch.bits.cacheCapacity.poke(256.U)
        }
        launch(); d.io.dispatch.valid.expect(false.B)
        consumeResult(1,id,tag); d.io.resetRequired.expect(false.B)
      }
      // Official-config-derived independent boundary vectors, still this DUT.
      for ((name, fields, cold, admitted) <- vectors) {
        fields.foreach { case (key,value) =>
          d.io.launch.bits.elements(key).asInstanceOf[UInt].poke(value.U)
        }
        d.io.launch.bits.cold.poke(cold.B)
        val id=fields("profileId").toInt; val tag=fields("tag").toInt
        launch()
        if (admitted) {
          d.io.dispatch.valid.expect(true.B); expectProfile(id)
          d.io.dispatch.bits.transactionId.expect((acceptedLaunches-1).U)
          d.io.dispatch.ready.poke(true.B); tick(); d.io.dispatch.ready.poke(false.B)
          d.io.completion.bits.transactionId.poke((acceptedLaunches-1).U)
          d.io.completion.bits.tag.poke(tag.U); d.io.completion.bits.profileId.poke(id.U)
          d.io.completion.valid.poke(true.B); tick(); d.io.completion.valid.poke(false.B)
          consumeResult(0,id,tag)
        } else {
          d.io.dispatch.valid.expect(false.B); consumeResult(1,id,tag)
        }
        d.io.resetRequired.expect(false.B)
      }
      // Same-DUT fail-closed stale identity; a protocol fault requires reset.
      drive(3,300); launch(); d.io.dispatch.ready.poke(true.B); tick()
      d.io.dispatch.ready.poke(false.B)
      d.io.completion.bits.transactionId.poke((acceptedLaunches-1).U)
      d.io.completion.bits.profileId.poke(1.U); d.io.completion.bits.tag.poke(300.U)
      d.io.completion.valid.poke(true.B); tick(); d.io.completion.valid.poke(false.B)
      d.io.result.bits.resetRequired.expect(true.B); d.io.resetRequired.expect(true.B)
      d.io.result.bits.acknowledgedWriteBytes.expect(0.U)
      consumeResult(2,3,300)
      drive(4,301); d.io.launch.valid.poke(true.B)
      for (_ <- 0 until 3) {d.io.launch.ready.expect(false.B); tick()}
      println(s"UNIFIED_PROFILE_CASE_PASS profiles=5 invalid=13 independentBoundaryVectors=74 sameDut=true betweenProfileReset=false explicitClocks=$clocks numerical=false")
    }
  }
}
'''
(ROOT/'source/UnifiedBlockAdmissionSpec.scala').write_text(spec)
print(json.dumps({'status':'SOURCE_CONTRACT_MATCH_AND_SPEC_GENERATED_NOT_COMPILED','profiles':5,'fields':len(widths),'bits':sum(widths.values()),'oracle_sha256':hashlib.sha256(raw).hexdigest()}))
