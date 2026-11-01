"""Read only closed original_high gzip; bounded finite telemetry, not acceptance.
No raw message/source/annotation/argv/path is returned. Missing/incomplete capture
is UNAVAILABLE, never an inferred compiler failure or proof of task completion.
"""
import gzip,json,pathlib,re,zlib
P=pathlib.Path
MAX_COMPRESSED=150_000_000
MAX_RAW=32*1024*1024
MAX_LINE=65536
MAX_LINES=100000
PHASES={p+'.'+s for p in ('elaborate','high.save','high.identity','official.low','low.save','low.identity')for s in ('begin','end')}|{'PASS_HIGH_AND_LOW_DIAGNOSTIC_ONLY'}
ARTIFACTS={'original-high.fir','official-low.fir','SCOPE.txt'}|{p+'-'+s for p in ('high','low')for s in ('annotations.json','hierarchy.tsv','top-ports.fir','extmodules.fir','summary.txt')}
EXCEPTIONS={
 'firrtl2.transforms.CheckCombLoops$CombLoopException':'CHECK_COMB_LOOPS',
 'firrtl2.passes.CheckInitialization$RefNotInitializedException':'CHECK_INITIALIZATION',
 'firrtl2.passes.CheckWidths$BitsWidthException':'WIDTH_CHECK',
 'firrtl2.passes.CheckWidths$WidthTooBigException':'WIDTH_CHECK',
 'firrtl2.passes.CheckWidths$UnknownWidth':'WIDTH_CHECK',
 'firrtl2.passes.PassException':'UNKNOWN',
 'firrtl2.passes.PassExceptions':'UNKNOWN',
 'firrtl2.FirrtlInternalException':'UNKNOWN',
 'chisel3.ChiselException':'UNKNOWN',
 'chisel3.internal.Errors':'UNKNOWN',
 'java.lang.IllegalArgumentException':'UNKNOWN',
 'java.lang.IllegalStateException':'UNKNOWN',
 'java.lang.OutOfMemoryError':'JVM_OUT_OF_MEMORY',
 'java.lang.StackOverflowError':'JVM_STACK_OVERFLOW',
 'java.lang.AssertionError':'ASSERTION',
 'java.lang.RuntimeException':'UNKNOWN',
 'java.io.IOException':'IO_EXCEPTION',
}
FILES={'CheckCombLoops.scala','CheckInitialization.scala','CheckWidths.scala','ExpandWhens.scala','Compiler.scala','Stage.scala','Transform.scala','Forms.scala','Errors.scala','Builder.scala','Predef.scala','DiagnoseOriginalHostMoePhaseV5.scala','HostBlockTopV4.scala','Qwen2Block.scala','OrderedRms1536Reduction32.scala','OrderedRmsSramReadBridge32.scala','HostOrderedRms32WiringV1.scala','QwenOwnerProtocol.scala','UnifiedMoeSharedArithmeticAdapterV5.scala','RuntimeRmsNormEngine.scala'}
# Exact selected159 source basenames, not an arbitrary path/name passthrough.
FILES |= {'HostBlockCommandsV4.scala', 'GdnRuntimeChunkLeafCollection.scala', 'TypedTensorReader.scala', 'OrderedRms1536Reduction32.scala', 'EmitHeteroFP32Alu.scala', 'GdnRmsNormOwner.scala', 'RecFNToIN.scala', 'HeteroRuntimeMoeMerge.scala', 'HostRuntimeOwnerGuardV5.scala', 'IdmaWeightBurst.scala', 'UnifiedMoeLogical32SigmoidConsumerV5.scala', 'TransposedDenseBanks.scala', 'GdnRuntimeChunkNumericPolicy.scala', 'HostRuntimeMoePhaseAllocatorV5.scala', 'GdnRuntimeRawPrepOwnerV7.scala', 'StreamingDense.scala', 'UnifiedMoeDownDescriptorV4.scala', 'DiagnoseOriginalHostMoePhaseV5.scala', 'MoeBf16VectorConsumerV2.scala', 'UnifiedOverlapProtocolV2.scala', 'FfnResidentCoordinator.scala', 'classifyRecFN.scala', 'RetainedIdma.scala', 'Rms32PortRefsV1.scala', 'rawFloatFromRecFN.scala', 'DenseTileSumBridge.scala', 'HostMoeDenseRoutingV5.scala', 'GdnRecurrentOwner.scala', 'PartialRopeRuntimeOwnerV12.scala', 'GdnRuntimeChunkLayout.scala', 'MatrixAccumulatorSeedProtocol.scala', 'UnifiedMoeSharedArithmeticAdapterV5.scala', 'HostRuntimeLaunchV4.scala', 'HostMoeRuntimePhaseProtocolV5.scala', 'HostRuntimeChunkWiringV9.scala', 'GdnChunkStateTransferOwner.scala', 'OrderedRmsSramReadBridge32.scala', 'UnifiedMoeSharedFfnPlanV5.scala', 'UnifiedSharedOperationProtocolV3.scala', 'UnifiedVectorElement32BankV4.scala', 'UnifiedMoePhaseResidualOwnerV5.scala', 'UnifiedMoeSharedArithmeticProtocolV5.scala', 'GdnGatedNormOwner.scala', 'QkNorm256Owner.scala', 'Bf16KvAppendOwner.scala', 'SharedMemoryArbiter.scala', 'common.scala', 'QwenOwnerProtocol.scala', 'HostBlockCommands.scala', 'UnifiedMoePhaseTileMergePortsV5.scala', 'HostMoeArithmeticLeaseWiringV5.scala', 'RoundAnyRawFNToRecFN.scala', 'HeteroOperatorPrimitiveProtocol.scala', 'UnifiedMoeDownTileReaderV5.scala', 'ElementwiseRegisterLoan.scala', 'GdnInputPrepOwner.scala', 'DivSqrtRecF64.scala', 'SharedL2Fabric.scala', 'OverlappedSilu.scala', 'HostMoeWeightScanV4.scala', 'HeldDecoupledOffer.scala', 'HostMoePhaseControlV5.scala', 'UnifiedMoeRouterSelectionClientV2.scala', 'HeteroSelectionMemoryPrimitives.scala', 'primitives.scala', 'UnifiedMoeProducerBindingV5.scala', 'UnifiedMoeRouterLogitReaderV2.scala', 'UnifiedMoeDenseWritebackV2.scala', 'GdnRuntimeConv4OwnerRecoveredV7.scala', 'DivSqrtRecF64_mulAddZ31.scala', 'MoeBf16ScalarConsumer.scala', 'AddRecFN.scala', 'GdnElementwiseOwner.scala', 'TensorProgram.scala', 'HostRuntimeChunkProtocolV9.scala', 'CompareRecFN.scala', 'GdnChunkAddressPlan.scala', 'GdnConv4Owner.scala', 'GdnRuntimeElementwiseOwnerV15.scala', 'HostMoeSharedGatePlanV5.scala', 'GdnRuntimeChunkExecuteOwner.scala', 'RecFNToRecFN.scala', 'GdnRuntimeRawPrepReceiptV8.scala', 'BlockAxiAdapter.scala', 'BlockWritebackFence.scala', 'GdnRuntimeRmsNormOwnerV3.scala', 'MatrixPipeline.scala', 'GdnRuntimeChunkDerivedAndPairV2Owner.scala', 'rawFloatFromIN.scala', 'UnifiedMoePhaseMergeOwnerV5.scala', 'INToRecFN.scala', 'UnifiedSharedFormatProtocolV3.scala', 'MulRecFN.scala', 'GdnRuntimeChunkCoordinator.scala', 'HostOrderedRms32WiringV1.scala', 'DenseBlockReductionCoordinator.scala', 'RetainedMatrix.scala', 'HostBlockTopV4.scala', 'Bf16CausalGqaRuntimeOwnerV14.scala', 'DenseReadPlanner.scala', 'HostMoePhaseLifetimeWiringV5.scala', 'Record128Reader.scala', 'UnifiedMoeLogical32SwiGluConsumerV3.scala', 'GdnRuntimeChunkLoadPrepOwner.scala', 'UnifiedMoeRuntimeExpertLoopV4.scala', 'PackedAttentionStreamClient.scala', 'fNFromRecFN.scala', 'UnifiedMoeRouterDenseV2.scala', 'recFNFromFN.scala', 'UnifiedMoeRouteGroupV2.scala', 'FfnTileSiluBridge.scala', 'ElementwiseMemoryEngine.scala', 'HostRuntimeGatedDependencyV10.scala', 'GdnChunkProtocol.scala', 'UnifiedMoeSharedGateSigmoidOwnerV5.scala', 'QkNorm256RuntimeOwnerV11.scala', 'UnifiedMoeActivationGroupOwnerV3.scala', 'GdnRuntimeChunkExecuteOwnerV8.scala', 'EmitHeteroBF16Fma.scala', 'UnifiedMoeRouterNumericalOwnerV2.scala', 'TransposedDenseOwner.scala', 'UnifiedScalarPolicyV2.scala', 'Qwen2Block.scala', 'HostRuntimePrefixLeaseWiringV8.scala', 'MatrixAccumulatorSeedController.scala', 'UnifiedMoeRoutedSelectionReaderV5.scala', 'PartialRope64Owner.scala', 'BlockFloat.scala', 'GdnOwnerProtocol.scala', 'VectorSilu.scala', 'GdnRuntimeChunkLoadPrepV2Owner.scala', 'Protocol.scala', 'UnifiedMoeRouterPipelineBindingV2.scala', 'UnifiedMoeActivationGatherV2.scala', 'GdnRuntimeGatedNormProtocolV10.scala', 'UnifiedMoeGatherFfnPlanV3.scala', 'Bf16CausalGqaOwner.scala', 'BlockScalarFloatPolicyV2.scala', 'GdnRecurrentProtocol.scala', 'LocalSramConfig.scala', 'UnifiedVectorElement32ProtocolV4.scala', 'WideMatrix.scala', 'GdnRuntimeRawPrepProtocolV7.scala', 'UnifiedMoeFfnGroupSequencerV3.scala', 'DivSqrtRecFN_small.scala', 'DenseOwnerIO.scala', 'MulAddRecFN.scala', 'resizeRawFloat.scala', 'rawFloatFromFN.scala', 'HostResidualCommands.scala', 'Public21QkvReductionRouter.scala', 'HostMoePhaseContextV4.scala', 'Bf16KvAppendRuntimeOwnerV13.scala', 'GdnRmsNormFixedBankOwner.scala', 'BurstProtocol.scala', 'HostMoeSelectionServiceV5.scala', 'GdnRuntimeGatedNormOwnerV10.scala', 'GdnRuntimeChunkTransposeV2Owner.scala', 'UnifiedRuntimeProfile.scala'}
METHODS={'apply','execute','run','transform','main','check','visit','onStmt','onModule','onExpr','elaborate','toLowFirrtl','require','assert','foreach','map','phase','inventory','mark','save','annotations','reportErrors','throwErrors','checkCombLoops','findSCCs'}
PHASE_RE=re.compile(r'HOST_PHASE ([A-Za-z_.]+) wall_ns=([0-9]{1,16}) process_cpu_ns=([0-9]{1,16})')
ARTIFACT_RE=re.compile(r'HOST_ARTIFACT ([A-Za-z0-9_.-]+) bytes=([0-9]{1,12}) sha256=([0-9a-f]{64})')
EXCEPTION_RE=re.compile(r'(?:(?:Exception in thread "main" |Caused by: ))?([A-Za-z0-9_.$]+)(?::.*)?')
STACK_RE=re.compile(r'\s*at ((?:firrtl2|chisel3|scala|java\.lang|heteronpu\.continuous|chiseltest\.simulator)\.[A-Za-z0-9_.$]+)\(([A-Za-z0-9_]+\.scala):([0-9]{1,7})\)')
def need(v,m):
 if not v:raise ValueError(m)
def base():return dict(schema='MODEL_ORIGINAL_IR_CLOSED_LOG_DIAGNOSTIC_V1',stage='original_high',status='UNAVAILABLE',reason='CLOSED_CAPTURE_REQUIRED',phases=[],artifacts=[],exceptions=[],stack=[],raw_bytes_scanned=0,lines_scanned=0,scan_complete=False,numerical_pass=False,structural_acceptance=False)
def safe_json(d):
 raw=json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False)
 need(len(raw.encode())<=8192,'bounded diagnostic');return raw

def project(stage_dir,report):
 d=base()
 # Do not inspect a file that the original owner has not closed and reaped.
 if not(type(report)is dict and type(report.get('native_exit'))is int and isinstance(report.get('cleanup_proof'),dict)and report['cleanup_proof'].get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and isinstance(report.get('log_capture'),dict)and report['log_capture'].get('pipe_eof_observed')is True and report['log_capture'].get('gzip_finalized')is True):return safe_json(d)
 p=P(stage_dir)/'frontend.log.gz'
 try:
  need(p.is_file()and all(not x.is_symlink()for x in(p,*p.parents))and 0<p.stat().st_size<=MAX_COMPRESSED,'bounded regular gzip')
 except (OSError,ValueError):d['reason']='LOG_FILE_UNAVAILABLE';return safe_json(d)
 d.update(status='OBSERVED_CLOSED_LOG',reason='NONE')
 try:
  with gzip.open(p,'rb')as f:
   while True:
    line=f.readline(min(MAX_LINE+1,MAX_RAW-d['raw_bytes_scanned']+1))
    if not line:d['scan_complete']=True;break
    d['raw_bytes_scanned']+=len(line);d['lines_scanned']+=1
    if len(line)>MAX_LINE or d['raw_bytes_scanned']>MAX_RAW or d['lines_scanned']>MAX_LINES:
     d.update(status='PARTIAL_CLOSED_LOG',reason='SCAN_BOUND');break
    try:text=line.rstrip(b'\r\n').decode('utf-8',errors='strict')
    except UnicodeError:continue
    m=PHASE_RE.fullmatch(text)
    if m and m[1]in PHASES and len(d['phases'])<13:
     if int(m[2])<=2**53 and int(m[3])<=2**53:d['phases'].append(dict(phase=m[1],wall_ns=int(m[2]),process_cpu_ns=int(m[3])))
     continue
    m=ARTIFACT_RE.fullmatch(text)
    if m and m[1]in ARTIFACTS and int(m[2])<=384*1024**2 and len(d['artifacts'])<13:
     d['artifacts'].append(dict(name=m[1],bytes=int(m[2]),sha256=m[3]));continue
    m=EXCEPTION_RE.fullmatch(text)
    if m and m[1]in EXCEPTIONS and len(d['exceptions'])<8:
     category=EXCEPTIONS[m[1]]
     if m[1]=='java.lang.IllegalArgumentException'and ': requirement failed' in text:category='REQUIREMENT_REJECTED'
     row=dict(exception_class=m[1],category=category)
     if row not in d['exceptions']:d['exceptions'].append(row)
     continue
    m=STACK_RE.fullmatch(text)
    if m and m[2]in FILES and 0<int(m[3])<=1000000 and len(d['stack'])<16:
     method=m[1].rsplit('.',1)[-1]
     if method not in METHODS:method='ANON_FUN'if re.fullmatch(r'\$anonfun\$[A-Za-z0-9_]+\$[0-9]+',method)else'OTHER_METHOD'
     row=dict(basename=m[2],function=method,line=int(m[3]))
     if row not in d['stack']:d['stack'].append(row)
 except (OSError,EOFError,gzip.BadGzipFile,zlib.error):d.update(status='PARTIAL_CLOSED_LOG',reason='GZIP_INVALID',scan_complete=False)
 return safe_json(d)
