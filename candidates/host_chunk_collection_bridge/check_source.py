"""Collection successor source contracts only; no RTL or producer provenance proof."""
from pathlib import Path
import argparse, hashlib, json, re, sys

R=Path(__file__).resolve().parent
NEW=R/'source/GdnRuntimeChunkLeafCollection.scala'
BRIDGE=R.parent/'host_chunk_gradual_bridge/source'
REPLACEMENTS={
    'new UnifiedVectorRequestV2':'new UnifiedOrdinaryVectorRequestV5',
    'new UnifiedVectorResultV2':'new UnifiedOrdinaryVectorResultV5',
    'new GdnRuntimeChunkExecuteOwner)':'new GdnRuntimeChunkExecuteOwnerV8)',
}
checks=0
def need(ok, message):
    global checks
    if not ok: raise ValueError(message)
    checks+=1

def contract(candidate, original):
    inverse=candidate
    for a,b in REPLACEMENTS.items():
        need(original.count(a)==1 and candidate.count(b)==1, 'one replacement '+b)
        need(a not in candidate, 'no old interface '+a)
        inverse=inverse.replace(b,a)
    need(inverse==original, 'all other original bytes/wiring preserved')
    modules=re.findall(r'Module\(new (\w+)\)',candidate)
    need(modules==['GdnRuntimeChunkCoordinator','GdnChunkStateTransferOwner',
        'GdnRuntimeChunkLoadPrepV2Owner','GdnRuntimeChunkDerivedAndPairV2Owner',
        'GdnRuntimeChunkTransposeV2Owner','GdnRuntimeChunkExecuteOwnerV8'], 'exact six real instances')
    for line in [
        'val MemoryClients=5; val ScalarClients=2; val VectorClients=2',
        'val LoadScalar=0; val DerivedScalar=1',
        'val DerivedVector=0; val ExecuteVector=1',
        'io.scalar(GdnRuntimeChunkClient.LoadScalar)<>load.io.scalar',
        'io.scalar(GdnRuntimeChunkClient.DerivedScalar)<>derived.io.scalar',
        'io.vector(GdnRuntimeChunkClient.DerivedVector).request<>derived.io.vectorRequest',
        'derived.io.vectorResult<>io.vector(GdnRuntimeChunkClient.DerivedVector).result',
        'io.vector(GdnRuntimeChunkClient.ExecuteVector).request<>execute.io.vectorRequest',
        'execute.io.vectorResult<>io.vector(GdnRuntimeChunkClient.ExecuteVector).result',
        'coordinator.io.prepDone<>io.prepDone',
        'io.memory(i).request<>requests(i)',
        'responses(i)<>io.memory(i).response',
        'val requests=Seq(state.io.memory,load.io.memory,derived.io.memory,transpose.io.memory,execute.io.memory)',
        'val responses=Seq(state.io.response,load.io.response,derived.io.response,transpose.io.response,execute.io.response)',
        'val acceptedPulse=RegNext(fires.asUInt.orR,false.B)',
        'io.routeMetadataFault:=metadataFault',
        'coordinator.io.fabricDrained:=io.fabricDrained',
    ]: need(line in candidate,'actual endpoint retained: '+line)
    for leaf in ['state','load','derived','transpose','execute']:
        need(leaf+'.io.committed:=coordinator.io.committedSnapshot' in candidate, 'snapshot '+leaf)
        need(leaf+'.io.job.fire' in candidate,'actual fire '+leaf)
    need('val prepDone=Flipped(Decoupled(new GdnRuntimeInputPrepResult))' in candidate,'original producer ABI unchanged')
    need('io.prepDone.bits' not in candidate,'no receipt rewrite at Collection')
    need(not re.search(r'(?:Mem|SyncReadMem|Queue)\(',candidate),'no added storage/arbiter')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-source',type=Path,required=True,help='Exact historical Collection source; not included')
    args=parser.parse_args()
    original=args.parent_source.read_text();candidate=NEW.read_text()
    need(hashlib.sha256(original.encode()).hexdigest()=='8e52017144139161eed37eb8d635b601478ee3372ef1507e850afcbe35e9edaf','exact original')
    need(hashlib.sha256(candidate.encode()).hexdigest()=='15798b8c3cba4522968e55b6a7f3306e5e5212b6b5abd8537ff9b5d38def7ca8','exact successor')
    contract(candidate,original)
    for filename in ['GdnRuntimeChunkDerivedAndPairV2Owner.scala','GdnRuntimeChunkExecuteOwnerV8.scala']:
        source=(BRIDGE/filename).read_text()
        need('Decoupled(new UnifiedOrdinaryVectorRequestV5)' in source,'actual request '+filename)
        need('Flipped(Decoupled(new UnifiedOrdinaryVectorResultV5))' in source,'actual result '+filename)
        compact=re.sub(r'\s+','',source)
        need('UnifiedVectorPolicyV2.LegacyRaw.U' in compact and 'UnifiedVectorPolicyV2.RawFp32FiniteGradual' not in compact,'canonical V2 policy0 '+filename)
        need('io.vectorRequest.bits.gradual:=' in compact,'actual gradual mode '+filename)
        need('io.vectorRequest.bits.formatOnly:=' in compact,'actual format mode '+filename)
    derived=(BRIDGE/'GdnRuntimeChunkDerivedAndPairV2Owner.scala').read_text()
    execute=(BRIDGE/'GdnRuntimeChunkExecuteOwnerV8.scala').read_text()
    need('val scalar = new UnifiedScalarClientV2' in derived,'real Derived scalar endpoint')
    need('io.vectorRequest.bits.formatOnly:=false.B' in re.sub(r'\s+','',derived),'Derived does not format')
    need('io.vectorRequest.bits.gradual:= !formatOnly && requestedGradual' in execute,'Execute format clears gradual')
    need('TensorMath.bf16Rne' not in execute,'Execute has no local BF16 RNE')
    mutations=[
        (b,a) for a,b in REPLACEMENTS.items()
    ]+[
        ('request<>derived.io.vectorRequest','request<>execute.io.vectorRequest'),
        ('derived.io.vectorResult<>io.vector(GdnRuntimeChunkClient.DerivedVector).result','derived.io.vectorResult<>io.vector(GdnRuntimeChunkClient.ExecuteVector).result'),
        ('LoadScalar)<>load.io.scalar','LoadScalar)<>derived.io.scalar'),
        ('coordinator.io.prepDone<>io.prepDone','coordinator.io.prepDone.bits:=0.U.asTypeOf(coordinator.io.prepDone.bits)'),
        ('val acceptedPulse=RegNext(fires.asUInt.orR,false.B)','val acceptedPulse=RegNext(io.job.valid,false.B)'),
        ('coordinator.io.fabricDrained:=io.fabricDrained','coordinator.io.fabricDrained:=true.B'),
    ]
    for old,new in mutations:
        need(old in candidate,'mutation fixture bound')
        try: contract(candidate.replace(old,new,1),original)
        except ValueError: pass
        else: raise ValueError('mutation survived: '+old)
    for row in json.loads((R/'SOURCE_PINS.json').read_text())['sources']:
        if row['location']=='requires_parent':continue
        p=R/row['path'];data=p.read_bytes()
        need(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'public source pin '+row['name'])
    print(json.dumps(dict(status='PASS_COLLECTION_SOURCE_CONTRACT_ONLY',checks=checks,
        mutation_controls=len(mutations),optimize=sys.flags.optimize,
        changes=3,actual_vector_producers=2,actual_scalar_producers=2,memory_clients=5,
        producer_tag_binding='OPEN: historical Coordinator requires producer tag == Chunk context tag',
        elaboration=False,rtl=False,numerical=False),indent=2))

if __name__=='__main__': main()
