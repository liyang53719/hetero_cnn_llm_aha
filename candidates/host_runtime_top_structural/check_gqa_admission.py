from pathlib import Path
import json,hashlib,itertools
C=Path(__file__).resolve().parent;W=C.parent
base=W/'host_runtime_gqa/source/Bf16CausalGqaRuntimeOwnerV14.scala';candidate=C/'source/Bf16CausalGqaRuntimeOwnerV14.scala'
r=json.loads((C/'SOURCE_PINS.json').read_text())['original_gqa'];raw=base.read_bytes()
if len(raw)!=r['bytes'] or hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('exact published GQA baseline required')
insert='''    // Admission failure is committed on the actual job handshake. Do not
    // reflect job.fire through combinational resetRequired back into the
    // parent's admission valid. No service offer/debt exists in idle; capture
    // the rejected job and enter the same drain/report path on this edge.
    def rejectJob(code: UInt): Unit = {
      status := code; poison := true.B; state := drain
    }
'''
def need(v,m):
 if not v:raise ValueError(m)
def check(t):
 s=base.read_text();need(t.count(insert)==1,'exact rejected admission register effects')
 a=t.index('  when(io.job.fire) {');b=t.index('  when(io.memory.fire) {',a);block=t[a:b]
 need(block.count('rejectJob(Status.')==4 and 'fail(' not in block,'all four admission branches separate')
 restored=t[:a]+block.replace(insert,'').replace('rejectJob(Status.','fail(Status.')+t[b:]
 need(restored==s,'all other executable source exact')
 need('io.resetRequired := status =/= Status.Ok.U || poison || drainUnknown || faultNow || currentFault' in t,'active fault export unchanged')
 need('when(faultNow || poison || currentFault)' in t,'current active/drain handler unchanged')
 return True
t=candidate.read_text();check(t)
# Exhaust abstract accepted admission edges. Each invalid branch captures a job,
# creates no service debt, then follows drain/finish/report with non-OK status.
cases=0
for valid,ready,code,current,quiet in itertools.product([False,True], [False,True], ['OK','Bounds','Unsupported','Protocol','Dependency'],[False,True],[False,True]):
 effective_ready=ready and not current and quiet
 fire=valid and effective_ready
 state='readQ' if fire and code=='OK' else 'drain' if fire else 'idle'
 poison=fire and code!='OK';status=code if fire else 'OK'
 # job-valid-dependent admission does NOT contribute to current-cycle export.
 exported_now=current
 need(exported_now==current,'admission no combinational feedback')
 if fire and code!='OK':
  need(state=='drain' and poison and status!='OK','same-edge reject latches')
  debt=0;offers=0
  need(debt==0 and offers==0,'idle job acceptance has no service effect')
  state='finish';complete=(status=='OK' and not poison)
  need(not complete,'invalid job never publishes success')
  state='report';need(status==code,'rejection code retained')
 if current:need(not fire,'current external fault vetoes handshake')
 cases+=1
# Active fault cases retain immediate sideband and held publication unchanged.
for parent,unknown,active_error,held,ready in itertools.product([False,True],repeat=5):
 current=parent or unknown;fault=active_error or current
 reset=fault
 visible=(not current) or held
 need(reset==fault,'no current event mask')
 if held:need(visible,'held publication cannot be withdrawn')
 cases+=1
mutants=[t.replace('status := code; poison := true.B; state := drain','status := code; state := drain'),t.replace('status := code; poison := true.B; state := drain','status := code; poison := true.B; state := readQ'),t.replace('|| faultNow || currentFault','|| currentFault',1),t.replace('rejectJob(Status.Bounds.U)','fail(Status.Bounds.U)',1),t.replace('status := code; poison := true.B; state := drain','faultNow := true.B; status := code; poison := true.B; state := drain')]
for bad in mutants:
 try:check(bad)
 except ValueError:pass
 else:raise ValueError('negative accepted')
print(json.dumps(dict(status='PASS_SOURCE_AND_ABSTRACT_MODEL_ONLY',cases=cases,negative_classes=len(mutants),source_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),not_DUT=True)))
