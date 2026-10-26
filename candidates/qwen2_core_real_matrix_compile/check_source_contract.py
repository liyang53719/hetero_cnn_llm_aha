"""Limited literal connection contract, not a Scala/Chisel compiler or behavior proof."""
import re
from pathlib import Path
H=Path(__file__).resolve().parent
FORWARD={'group.valid':'group.valid','group.bits.opcode':'group.bits.opcode','group.bits.sliceMask':'group.bits.sliceMask','group.bits.tag':'group.bits.tag','step.valid':'step.valid','step.bits':'step.bits','result.ready':'result.ready','done.ready':'done.ready','abort':'abort'}
REVERSE={'group.ready','step.ready','result.valid','done.valid'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def clean(s):return re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)
def check(core,collection):
 c=clean(core);k=clean(collection)
 need(c.count('Module(new OrderedQkBehaviorCore(true))')==1,'original ordered core')
 need(c.count('Module(new MatrixPipelineService(returnTagBits=0,enableTransposedDense=false,enableAccumulatorSeed=false,enablePackedDrainStatus=true))')==1,'original service exact optional features')
 need(c.count('Module(new LegacyMatrixStreamClient)')==1,'original legacy client')
 need(c.count('Module(new ')==3,'no duplicate or replacement datapaths')
 need('val select=core.io.packedQkActive.get' in c,'actual lifetime lease select')
 need('core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get' in c,'physical service drain, no counter stub')
 need('legacy.io.request<>core.io.matrixRequest.get' in c and 'core.io.matrixResult.get<>legacy.io.result' in c,'PV legacy route')
 need('core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps' in c,'actual issue counter not synthetic')
 need('for((client,chosen)<-Seq((p,select),(l,!select)))' in c,'two mutually exclusive clients')
 actual=re.findall(r'matrix\.io\.port\.([\w.]+):=Mux\(select,p\.([\w.]+),l\.([\w.]+)\)',c)
 need(len(actual)==len(FORWARD) and {a for a,_,_ in actual}==set(FORWARD),'all nine forward signals once')
 for a,b,d in actual:need(b==d==FORWARD[a],'matching selected forward fields')
 actual_reverse=re.findall(r'client\.([\w.]+):=chosen&&matrix\.io\.port\.([\w.]+)',c)
 need(len(actual_reverse)==4 and {a for a,b in actual_reverse}==REVERSE and all(a==b for a,b in actual_reverse),'ready/valid reverse gate')
 for p in ('result','done'):need(f'client.{p}.bits:=matrix.io.port.{p}.bits' in c,'payload broadcast with gated valid')
 need('core.io.launch.valid:=false.B' in c and 'core.io.ownerJob.get<>io.ownerJob' in c,'owner-driven launch')
 need('io.ownerJob.bits.kind===QwenOwnerKind.Attention.U' in c,'narrow Attention asserted scope')
 need('io.resetRequired:=core.io.resetRequired||matrix.io.resetRequired||legacy.io.resetRequired' in c,'poison visibility')
 need('io.issuedSliceSteps:=matrix.io.acceptedSteps' in c,'issued-not-completed count label')
 need(k.count('Module(new OrderedQkRealMatrixCore)')==1,'selected shell in collection')
 for leaf in ('Pre','Mul','Post','Round'):need(k.count('Module(new HeteroBF16Fma'+leaf+')')==1,'original common FMA leaf '+leaf)
 need(k.count('Module(new ')==5,'one shell and four ABI definition roots only')
 need('observation:=top.observation' in k and 'scoreWrite:=top.scoreWrite' in k,'readonly original probes retained')
 need('extends App' not in k and 'emitCHIRRTL' not in k and 'Process' not in k,'no executable emitter in this source gate')
 return dict(status='PASS_LITERAL_SOURCE_CONNECTION_SUBSET_ONLY_NOT_CHISEL_COMPILE',forward_fields=len(actual),reverse_gates=len(actual_reverse),common_abi_roots=4)
if __name__=='__main__':
 import json
 print(json.dumps(check((H/'source/OrderedQkRealMatrixCore.scala').read_text(),(H/'source/OrderedQkRealMatrixCollection.scala').read_text()),sort_keys=True))
