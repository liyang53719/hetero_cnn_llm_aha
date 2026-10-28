"""Exact held-offer source fix/inverse only; no hardware execution."""
from pathlib import Path
import hashlib,json
C=Path(__file__).resolve().parent
s=(C/'source/HostBlockCommandsV4.scala').read_text()
new='when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired){fail(Status.Protocol.U)}'
old='when(state===issue && io.resident.get.resetRequired){fail(Status.Protocol.U)}'
def need(v,m):
 if not v:raise ValueError(m)
need(s.count(new)==1,'unique fixed guard')
newcomment='  // Legacy issue with no accepted debt terminates. Runtime prefix already\n  // exposes job.valid at issue: a late fault MUST NOT retract that offer.\n  // Keep the full bound job stable; Guard forbids fresh acceptance and the\n  // poisoned transaction remains held until the existing joint reset.'
oldcomment='  // reaching issue with no accepted owner debt must terminate, not hang.'
need(s.count(newcomment)==1,'unique comment delta')
r1=s.replace(new,old,1).replace(newcomment,oldcomment,1).encode()
pin=json.loads((C/'SOURCE_PINS.json').read_text())['r1_commands']
need(len(r1)==pin['bytes'] and hashlib.sha256(r1).hexdigest()==pin['sha256'],'exact r1 inverse')
print('PASS exact executable guard plus comments; r1 compilerPASS/protocolFAIL preserved; no DUT')
