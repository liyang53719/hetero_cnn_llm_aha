#!/usr/bin/env python3
"""Source-shape and Boolean drain conjunction checks, never a Chisel DUT test."""
from pathlib import Path
import hashlib,json,itertools
P=Path(__file__).resolve().parent
BASE=P.parent/'host_runtime_ffn/source/HostBlockTopV4.scala'
r=json.loads((P/'SOURCE_PINS.json').read_text())['source_check_originals']['HostBlockTopV4.scala']
b=BASE.read_bytes()
if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('exact published Top baseline required')
def check(s):
 start=s.index('  // Private final-fence observation')
 end=s.index('  io.result<>cmd.io.result;io.completion<>cmd.io.completion',start)
 if s[:start]+s[end:]!=BASE.read_text():raise ValueError('unrelated Top change')
 rhs=s[start:end]
 terms=['physicalDrained','phaseDenseDrained','phaseArithmeticDrained','moeSelection.io.resourcesDrained','cmd.io.metadataDrained','!runtimeGuard.io.localBusy','!runtimeGuard.io.phaseReserved','!phaseAllocator.io.reserved','!lifetime.active','!n1ImageValid']
 expression=rhs.split('cmd.io.runtimeFinalDrained:=',1)[1]
 if ''.join(expression.split())!='&&'.join(terms):raise ValueError('drain source differs')
 if 'io.launch.bits' in expression or '.fire' in expression:raise ValueError('host grant/fire dependency')
 return terms
s=(P/'source/HostBlockTopV4.scala').read_text();terms=check(s)
for x in terms:
 try:check(s.replace(x+' &&','true.B &&',1) if x!=terms[-1] else s.replace('!n1ImageValid\n','true.B\n',1))
 except ValueError:pass
 else:raise ValueError('missing source not rejected '+x)
count=0
for v in itertools.product((False,True),repeat=10):
 actual=all(v)
 if actual!=(sum(v)==10):raise ValueError('conjunction model')
 count+=1
print(json.dumps({'scope':'SOURCE_AND_BOOLEAN_MODEL_ONLY_NOT_DUT','status':'PASS','conjunction_cases':count,'source_mutations':len(terms),'no_new_modules':True}))
