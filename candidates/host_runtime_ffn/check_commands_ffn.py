"""Source binding checks only, never a Scala typecheck/elaboration/DUT claim."""
from pathlib import Path
import hashlib,json
C=Path(__file__).resolve().parent
BASE=C.parent/'host_runtime_postnorm/source/HostBlockCommandsV4.scala'
SOURCE=C/'source/HostBlockCommandsV4.scala'
r=json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals']['HostBlockCommandsV4.scala']
b=BASE.read_bytes()
if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('exact published Commands baseline required')
def need(ok,message):
    if not ok:raise ValueError(message)
def between(s,a,b):
    need(s.count(a)==1 and s.count(b)==1,'unique source delimiters')
    return s.split(a,1)[1].split(b,1)[0]
def check(s):
    b=BASE.read_text()
    anchors=[
      'val runtimeFfnReceipt=Input(Valid(new HostRuntimeFfnStagedReceiptV17))',
      'val runtimeFfnProfile=enableRuntimeOutput.B && (cfg.profileId===1.U || cfg.profileId===2.U)',
      'postnormCommitValid && postnormCurrent && postnormJob.m===m',
      'io.runtimePostnormReceipt.bits.asUInt===postnormPhysicalReceipt.asUInt',
      'postnormPhysicalReceipt.host.asUInt===cfg.asUInt',
      'postnormPhysicalReceipt.transactionId===runtimeTransaction',
      'val ffnK=Mux(ffnDown,3584.U(16.W),1024.U(16.W))',
      'val ffnN=Mux(ffnDown,1024.U(16.W),3584.U(16.W))',
      'rdRole>=4.U && rdRole<=6.U',
      'val ffnWeightRole=Mux(runtimeGdnProfile,rdRole+9.U,rdRole+6.U)',
      'sourceAllowed(b,ffnWeightRole) && ffnWeightIdentity',
      'sameAllocation(a,runtimeFfnTensors(0)) && sameAllocation(b,runtimeFfnTensors(1))',
      'sameAllocation(a,txResidual1Tensor) && sameAllocation(b,runtimeFfnTensors(3))',
      'bound.runtimeFfnPhase:=0.U',
      'bound.public21Reduction:=officialBf16.B && cfg.profileId===0.U && dense &&',
      '(pc===1.U || pc===4.U || pc===7.U)',
      '!bound.public21Reduction && bound.cold && bound.expectedGeneration===0.U',
      'bound.runtimeFfnPhase:=Mux(runtimeFfnDense,Mux(ffnDown,4.U,rdRole-3.U),Mux(ffnSilu,3.U,5.U))',
      'bound.gdnElementwiseOp:=Mux(runtimeFfnElement && ffnSilu,GdnElementwiseOp.SiluMul.U,GdnElementwiseOp.Add.U)',
      'val downActivationBf16=nativeProjection || gdnProjection || attentionBlockDense || runtimeDenseProjection || runtimeDenseO || runtimeFfnDense',
      'val workspaceCapacityOK=downK<=2560.U || workspaceExtent>=(downN.pad(64)>>5)*16384.U',
      'ffnProof.logicalJob.asUInt===bound.asUInt && ffnProof.job.asUInt===ffnExpectedPhysical.asUInt',
      'ffnProof.job.tag=/="hffffffff".U && ffnProof.result.tag===ffnProof.job.tag',
      'ffnProof.result.usefulMacs===ffnExpectedMacs && ffnProof.result.executedMacs>=ffnProof.result.usefulMacs',
      'ffnPhysicalReceipt.asUInt===ffnProof.asUInt',
      'io.done.bits.asUInt===ffnLogicalResult.asUInt && !io.runtimeAuthority.currentFault && !residentFault',
      '(boundRuntimeFfn && !runtimeFfnPendingExact)',
      'when(boundRuntimeFfn){\n          // Every numerical materialization',
      'is(5.U){txResidual2Valid:=true.B;txResidual2:=bound.dst}',
    ]
    for a in anchors:need(a in s,'missing actual Commands binding: '+a)
    need(s.count('badRuntimeGqaMacs(r) || badRuntimePostnormAck(r) || badRuntimeFfnAck(r)')==2,'both actual return branches fence FFN')
    legacy=between(s,'    val officialRoleOK=WireDefault(true.B)','    // Runtime RMS validation is independent of legacy constructor branches.')
    need(legacy==between(b,'    val officialRoleOK=WireDefault(true.B)','    // Runtime RMS validation is independent of legacy constructor branches.'),'legacy Qwen2/GDN M1/Attention M1 program and numeric-policy validation unchanged')
    launch_a='    val (launchProfile,launchKnown)=UnifiedRuntimeProfile.decode(l.profileId)'
    # This exact seal is the existing launch predicate, not a test bypass.
    old_lines=[x for x in b.splitlines() if 'l.profileId===0.U' in x or 'profileSupported' in x]
    need(old_lines and all(x in s for x in old_lines),'closed runtime launch seal unchanged')
    completion=between(s,'        when(boundRuntimeFfn){\n          // Every numerical materialization','        }.elsewhen(bound.kind===QwenOwnerKind.GdnConv.U){')
    need(all(x not in completion for x in ('stateValid:=','attentionCacheValid:=','currentGeneration:=','attentionGeneration:=')),'Residual2 remains staging not final root')
    for a,z in (('{','}'),('(',')'),('[',']')):need(s.count(a)==s.count(z),'balanced '+a)
    return len(anchors)+6

def run():
    s=SOURCE.read_text();count=check(s)
    mutants={
      'open_profiles':('cfg.profileId===1.U || cfg.profileId===2.U','cfg.profileId>=1.U && cfg.profileId<=4.U'),
      'missing_postnorm_bits':('io.runtimePostnormReceipt.bits.asUInt===postnormPhysicalReceipt.asUInt','true.B'),
      'bypass_physical_identity':('ffnProof.logicalJob.asUInt===bound.asUInt && ffnProof.job.asUInt===ffnExpectedPhysical.asUInt','true.B'),
      'bypass_completion_receipt':('(boundRuntimeFfn && !runtimeFfnPendingExact)','false.B'),
      'swap_silu_operands':('sameAllocation(a,runtimeFfnTensors(0)) && sameAllocation(b,runtimeFfnTensors(1))','sameAllocation(a,runtimeFfnTensors(1)) && sameAllocation(b,runtimeFfnTensors(0))'),
      'physical_tag_as_semantics':('(pc===1.U || pc===4.U || pc===7.U)','(bound.tag(15,0)===1.U || bound.tag(15,0)===4.U || bound.tag(15,0)===7.U)'),
      'change_dense_geometry':('val ffnK=Mux(ffnDown,3584.U(16.W),1024.U(16.W))','val ffnK=Mux(ffnDown,8960.U(16.W),1536.U(16.W))'),
    }
    rejected=[]
    for name,(a,b) in mutants.items():
      need(a in s,'mutant source anchor')
      try:check(s.replace(a,b))
      except ValueError:rejected.append(name)
      else:raise ValueError('source mutation not caught '+name)
    result={'status':'PASS_COMMANDS_SOURCE_AND_MUTATIONS_NOT_DUT','checks':count,'mutations_rejected':rejected,
      'source':{'path':str(SOURCE),'bytes':SOURCE.stat().st_size,'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
      'base':{'path':str(BASE),'bytes':BASE.stat().st_size,'sha256':hashlib.sha256(BASE.read_bytes()).hexdigest()},
      'scope':'Original typed Commands actual continuation and strict receipts; source/model only; no Scala/RTL/numerical DUT/physical resource proof.'}
    print(json.dumps(result,indent=2))
if __name__=='__main__':run()
