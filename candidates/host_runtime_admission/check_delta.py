from pathlib import Path
import hashlib,json,itertools
C=Path(__file__).resolve().parent
p=C/'source/HostBlockCommandsV4.scala';b=C.parent/'host_runtime_fence/source/HostBlockCommandsV4.scala'
r=json.loads((C/'SOURCE_PINS.json').read_text())['original_commands']
data=b.read_bytes()
if len(data)!=r['bytes'] or hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('exact published predecessor required')
s=p.read_text();old=b.read_text()
def need(x,m):
 if not x:raise ValueError(m)
oldstart=old.index('  // During incremental migration');oldend=old.index('\n  val pc=',oldstart)
start=s.index('  // The original common constructor');end=s.index('\n  val pc=',start)
expected_installed='''  // The original common constructor admits runtime profiles through the same
  // typed-record parser and real owners. Admission is not numerical acceptance.
  // Legacy partial constructors remain unsupported: all installed runtime tail
  // services and the fixed production Dense path must be present together.
  private val commonRuntimeInstalled=officialBf16 && s.retainedMatrix && s.matrixColumns==256 &&
    enableResidentFfn && enableTransposedDown &&
    enableRuntimeQkNorm && enableRuntimeRope && enableRuntimeKvAppend && enableRuntimeGqa && enableRuntimeOutput
'''
need(s[start:end]==expected_installed,'exact entire inserted installed block, no suffix bypass')
undo=s[:start]+old[oldstart:oldend]+s[end:]
a='''    .elsewhen(envelopeAccepted && !((l.profileId===0.U && officialBf16.B) ||
      (commonRuntimeInstalled.B && l.profileId>=1.U && l.profileId<=4.U))){'''
need(undo.count(a)==1,'exact admission replacement')
undo=undo.replace(a,'    .elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B)){')
a='m===128.U && shape2(a,m,runtimeNormHidden)'
need(undo.count(a)==1,'exact norm row change')
undo=undo.replace(a,'m>0.U && m<=128.U && shape2(a,m,runtimeNormHidden)')
start=undo.index('    // SHAPE4 dimensions are18-bit.')
end=undo.index('    val chunkProgram=',start)
expected_scratch='''    // SHAPE4 dimensions are18-bit. M128's419840 FP32 words/head cannot be
    // encoded as one dimension; rank3 preserves exactly128*3280 words/head.
    // This changes descriptor geometry only, not physical scratch layout/size.
    val chunkScratchShape=Mux(m===128.U,shape3(rhOut,prepHeads,128.U,3280.U),
      shape2(rhOut,prepHeads,chunkStride>>2))
'''
need(undo[start:end]==expected_scratch,'exact entire inserted scratch block, no suffix bypass')
undo=undo[:start]+undo[end:]
need(undo.count('shape2(rhIn,prepHeads,16384.U) && chunkScratchShape &&')==1,'scratch predicate exact')
undo=undo.replace('shape2(rhIn,prepHeads,16384.U) && chunkScratchShape &&','shape2(rhIn,prepHeads,16384.U) && shape2(rhOut,prepHeads,chunkStride>>2) &&')
need(undo==old,'all arithmetic/provenance/transport/state source outside five edits identical')
for heads in [16,32]:
 dims=(heads,128,3280,1);strides=(419840,3280,1)
 need(all(0<x<2**18 for x in dims),'dimension encoding')
 need(all(0<x<2**23 for x in strides),'decoder forbids stride sign bit23')
 need(strides==(dims[1]*dims[2]*dims[3],dims[2]*dims[3],dims[3]),'canonical stride')
 need(heads*128*3280*4==heads*1679360,'physical bytes')
need(872448//4==218112<2**18,'M16 rank2 preserved')

# Independent full capability truth table: each constituent can disable new admission,
# while profile0 keeps original official admission independently.
count=0
for caps in itertools.product([False,True],repeat=10):
 official,retained,col256,resident,down,qknorm,rope,kv,gqa,out=caps
 installed=all(caps)
 for profile in range(8):
  for checkpoint in [False,True]:
   actual=(profile==0 and official) or (installed and 1<=profile<=4)
   actual=actual and not(profile!=0 and checkpoint)
   if profile==0:need(actual==official,'unchanged profile0')
   elif 1<=profile<=4:need(actual==(all(caps) and not checkpoint),'complete physical and service contract')
   else:need(not actual,'invalid profile')
   count+=1
# Runtime norm is the sole transaction bootstrap. The predecessor predicates are
# source-identical; verify exact live provenance gates at each entry.
requirements=[
 'val rdLive=txInputValid && txInputNormValid && sameAllocation(a,runtimeInputNormTensor)',
 'val rnInputProducer=rnRole===0.U && !txInputValid && !txInputNormValid && rnInitialContext &&',
 'readonly(a) && sourceAllowed(a,0.U)',
 '.elsewhen(runtimeNormProfile && ((pc+1.U===cfg.commands) =/= runtimeFence))',
 'sourceValid(0) && txInputNormValid && txOValid && txResidual1Valid && txPostNormValid &&',
 'postnormCurrent && postnormCommitValid && producedCount<producedCapacity.U',
 'val finalRows=runtimeFinalTensor.dims(0)',
 'finalRows===128.U',
 'when(io.runtimeFinalDrained){',
 'val headerOK=HostCommandLaunchV4.known(l)',
 'io.launch.ready:=state===idle && !poison && !moePhaseLiveFault && !runtimeIdentityExhausted',
 'bound.public21Reduction:=officialBf16.B && cfg.profileId===0.U && dense &&',
]
for x in requirements:need(x in s,'preserved '+x)
print(json.dumps(dict(status='PASS_EXACT_FIVE_EDIT_INVERSE_AND_BOOLEAN_MODELS_ONLY',capability_cases=count,provenance_checks=len(requirements),structural_pass_inherited=False,full_m128_passes=0,rtl_passes=0)))
