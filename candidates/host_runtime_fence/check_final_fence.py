"""Source contract/negative controls only, not RTL or numerical verification."""
import json
from pathlib import Path
P=Path(__file__).parent
checks=[
'(!officialBf16.B || l.profileId=/=0.U || l.commands===21.U)',
'val runtimeFinalDrained=Input(Bool())',
'pc+1.U<cfg.commands && !txResidual2Valid',
'finalRows===128.U',
'sameAllocation(a,runtimeHistoryTensor) && sameAllocation(b,runtimeStateTensor)',
'sameAllocation(a,pendingAttentionCache) && sameAllocation(b,sourceTensor(0))',
'((pc+1.U===cfg.commands) =/= runtimeFence)',
'when(io.runtimeFinalDrained){',
'runtimeTransaction===runtimeFenceTransaction',
'cfg.asUInt===runtimeFenceHost.asUInt && pc+1.U===cfg.commands',
'io.runtimeAuthority.currentFault || !io.runtimeFinalDrained || runtimeCheckpointCommitted',
'currentHistoryAddress:=pendingHistoryAddress;currentHistoryEnd:=pendingHistoryEnd',
'currentStateAddress:=pendingStateAddress;currentStateEnd:=pendingStateEnd',
'attentionContext:=runtimeFinalTensor;attentionLength:=pendingAttentionLength',
'!runtimeNormProfile || runtimeResultQualified',
'!io.runtimeFinalDrained || !runtimeCheckpointCommitted',
'!(l.profileId===0.U && officialBf16.B)',
]
# Frozen counts from exact compiled source; do not learn expectations from mutated input.
expected={'(!officialBf16.B || l.profileId=/=0.U || l.commands===21.U)': 1, 'val runtimeFinalDrained=Input(Bool())': 1, 'pc+1.U<cfg.commands && !txResidual2Valid': 1, 'finalRows===128.U': 1, 'sameAllocation(a,runtimeHistoryTensor) && sameAllocation(b,runtimeStateTensor)': 1, 'sameAllocation(a,pendingAttentionCache) && sameAllocation(b,sourceTensor(0))': 1, '((pc+1.U===cfg.commands) =/= runtimeFence)': 1, 'when(io.runtimeFinalDrained){': 1, 'runtimeTransaction===runtimeFenceTransaction': 1, 'cfg.asUInt===runtimeFenceHost.asUInt && pc+1.U===cfg.commands': 1, 'io.runtimeAuthority.currentFault || !io.runtimeFinalDrained || runtimeCheckpointCommitted': 1, 'currentHistoryAddress:=pendingHistoryAddress;currentHistoryEnd:=pendingHistoryEnd': 2, 'currentStateAddress:=pendingStateAddress;currentStateEnd:=pendingStateEnd': 2, 'attentionContext:=runtimeFinalTensor;attentionLength:=pendingAttentionLength': 1, '!runtimeNormProfile || runtimeResultQualified': 1, '!io.runtimeFinalDrained || !runtimeCheckpointCommitted': 2, '!(l.profileId===0.U && officialBf16.B)': 1}
def verify(s):
    missing=[x for x in checks if s.count(x)!=expected[x] or expected[x]==0]
    if missing:raise ValueError(missing)
s=(P/'source/HostBlockCommandsV4.scala').read_text();verify(s)
for c in checks:
    try:verify(s.replace(c,'REMOVED_REQUIRED_CONTRACT',1))
    except ValueError:pass
    else:raise RuntimeError('negative control accepted: '+c)
print(json.dumps({'scope':'SOURCE_CONTRACT_ONLY_NOT_DUT','required_fragments':len(checks),'rejected_mutations':len(checks),'status':'PASS'},indent=2))
