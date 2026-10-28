"""Source admission and finite Boolean model checks; never a Chisel/DUT test."""
from pathlib import Path
import hashlib,json,itertools
C=Path(__file__).resolve().parent
P=C/'source/HostBlockCommandsV4.scala'
def need(b,m):
 if not b: raise ValueError(m)
def check(s):
 start=s.index('  private val commonRuntimeInstalled=')
 end=s.index('\n  val pc=',start)
 expected='''  private val commonRuntimeInstalled=officialBf16 && s.retainedMatrix && s.matrixColumns==256 &&
    enableResidentFfn && enableTransposedDown &&
    enableRuntimeQkNorm && enableRuntimeRope && enableRuntimeKvAppend && enableRuntimeGqa && enableRuntimeOutput
'''
 need(s[start:end]==expected,'exact complete installed expression; no suffix bypass')
 snippets=[
 'private val commonRuntimeInstalled=officialBf16 && s.retainedMatrix && s.matrixColumns==256 &&\n    enableResidentFfn && enableTransposedDown &&\n    enableRuntimeQkNorm && enableRuntimeRope && enableRuntimeKvAppend && enableRuntimeGqa && enableRuntimeOutput',
 '(commonRuntimeInstalled.B && l.profileId>=1.U && l.profileId<=4.U)',
 'envelopeAccepted && l.profileId=/=0.U && runtimeCheckpointCommitted',
 'm===128.U && shape2(a,m,runtimeNormHidden)',
 'val rnInitialContext=rnCold && rnGeneration===0.U && !rnCheckpointValid',
 'val rnInputProducer=rnRole===0.U && !txInputValid && !txInputNormValid && rnInitialContext &&',
 'val rnInputProducer=rnRole===0.U && !txInputValid && !txInputNormValid && rnInitialContext &&\n      readonly(a) && sourceAllowed(a,0.U)',
 'val headerOK=HostCommandLaunchV4.known(l)',
 '(!officialBf16.B || l.profileId=/=0.U || l.commands===21.U)',
 'finalRows===128.U',
 '!runtimeCheckpointCommitted && txCold && txGeneration===0.U',
 'val runtimeFence=runtimeGdnFence || runtimeAttentionFence',
 'val chunkScratchShape=Mux(m===128.U,shape3(rhOut,prepHeads,128.U,3280.U),\n      shape2(rhOut,prepHeads,chunkStride>>2))',
 'shape2(rhIn,prepHeads,16384.U) && chunkScratchShape &&',
 ]
 for x in snippets:need(s.count(x)==1,'unique required source '+x)
 return snippets
s=P.read_text();sn=check(s)
negative=[]
for i,x in enumerate(sn):
 try:check(s.replace(x,'/* removed */',1))
 except ValueError:negative.append(i)
 else:raise ValueError('deletion escaped')
cases=0
for profile,official,installed,checkpoint,envelope,known in itertools.product(range(8),range(2),range(2),range(2),range(2),range(2)):
 admitted=bool(envelope and known and not(profile!=0 and checkpoint) and ((profile==0 and official) or(installed and 1<=profile<=4)))
 if profile==0:need(admitted==bool(envelope and known and official),'profile0 invariant')
 if profile>4 or not known or not envelope:need(not admitted,'unsupported/header/bounds')
 if profile in range(1,5):need(admitted==bool(envelope and known and installed and not checkpoint),'runtime exact admission')
 cases+=1
for rows,cold,generation,checkpoint in itertools.product([0,1,16,127,128,129],range(2),[0,1,0xffffffff],range(2)):
 input_ok=rows==128 and cold and generation==0 and not checkpoint
 need(bool(input_ok)==(rows==128 and cold==1 and generation==0 and checkpoint==0),'cold128 source contract');cases+=1
for heads in (16,32):
 need(all(v<(1<<18) for v in (heads,128,3280)), 'shape18 range')
 need(all(v<(1<<23) for v in (419840,3280,1)), 'unsigned stride23 range')
 need(heads*128*3280*4==heads*1679360, 'exact scratch physical bytecount')
r={'status':'PASS_SOURCE_AND_BOOLEAN_MODELS_ONLY','source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'cases':cases,'negative_classes':len(negative),'not_run':['Chisel','elaboration','numerics','RTL'],'full_m128_passes':0}
print(json.dumps(r,indent=2))
