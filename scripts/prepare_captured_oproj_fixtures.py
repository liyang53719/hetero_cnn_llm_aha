#!/usr/bin/env python3
"""Use approved l0.oproj descriptors and captured attention, not relabeled Q."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pack(path,values):
    v=np.asarray(values,np.uint16).reshape(-1,32)
    with path.open('w') as stream:
        for row in v:stream.write(f'{sum(int(w)<<(16*i) for i,w in enumerate(row)):0128x}\n')
def main():
    captured=ROOT/'work/results/q1024_captured_attention_payload'
    proof=json.loads((ROOT/'reports/execution/Q1024_ATTENTION_OPROJ_INPUT_RESULT.json').read_text())
    assert proof['status']=='PASS_CAPTURED_ATTENTION_TO_OPROJ_INPUT' and proof['independent_fp32_comparisons']==1572864
    assert proof['max_absolute_error']<=0.002
    a=captured/'attention_actual_token_major_bf16.bin';assert sha(a)==proof['bf16_sha256']
    reference=ROOT/'work/results/q1024_tail_from_captured_attention'
    ref=json.loads((reference/'result.json').read_text())
    assert ref['status']=='PASS_CPU_TAIL_REFERENCE_FROM_CAPTURED_RTL_ATTENTION'
    assert ref['identity']['attention_sha256']==proof['fp32_sha256']
    inp=ROOT/'work/results/qwen2_q1024_layer0_tail_inputs'
    assert sha(inp/'manifest.json')==ref['identity']['input_manifest_sha256']
    inputs=json.loads((inp/'manifest.json').read_text())
    w=inp/'oproj_weight_bf16.bin';assert sha(w)==inputs['hashes'][w.name]
    expected=reference/'oproj_fp32.bin';assert sha(expected)==ref['output_sha256'][expected.name]
    out=ROOT/'work/results/q1024_captured_oproj';out.mkdir(exist_ok=True)
    assert not (out/'manifest.json').exists(),'Preserve existing fixture identity'
    pack(out/'activation.memh',np.fromfile(a,np.uint16).reshape(1024,1536))
    # External B storage is K-major N-contiguous, identical group8 packing to Q.
    pack(out/'weight.memh',np.fromfile(w,np.uint16).reshape(1536,1536).T)
    e=np.fromfile(expected,np.uint32);assert e.size==1024*1536
    pack(out/'expected.memh',((e+0x7fff+((e>>16)&1))>>16).astype(np.uint16))
    mf=ROOT/'reports/execution/llama_cpp_qwen2_graph_lowering_manifest.jsonl'
    cf=ROOT/'work/generated/qwen2_q1024_symbolic_descriptors/descriptor_chains.jsonl'
    commands=[json.loads(s) for s in mf.read_text().splitlines()]
    selected=[next(x for x in commands if x['operation']==name) for name in ['l0.oproj','l0.k','l0.v']]
    chains={c['root']:c for c in map(json.loads,cf.read_text().splitlines())}
    addresses=[]
    for cmd in selected:
        for role in ['src0','src1','dst']:
            records=chains[cmd['roots'][role]]['records']
            addresses.append(next(r for r in records if r['record_type']=='tensor_base')['address'])
    (out/'commands.memh').write_text(''.join(c['word'].removeprefix('0x')+'\n' for c in selected))
    (out/'addresses.memh').write_text(''.join(f'{x:014x}\n' for x in addresses))
    records=ROOT/'work/results/qwen2_group8_pinned_idma/records.memh';assert records.is_file()
    # Verify packed DDR addresses against the actual records the DUT will fetch.
    image=[int(x,16) for x in records.read_text().splitlines()]
    for role,addr in zip(['src0','src1','dst'],addresses[:3]):
        word=image[selected[0]['roots'][role]-4096]
        assert (word&255)==1 and (((word>>120)&255)<<48|((word>>56)&((1<<48)-1)))==addr
    result=dict(status='PASS_FIXTURE_PREPARATION_ONLY_RTL_NOT_RUN',operation='l0.oproj',
                dimensions=[1024,1536,1536],input_gate_sha256=sha(ROOT/'reports/execution/Q1024_ATTENTION_OPROJ_INPUT_RESULT.json'),
                source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [a,w,expected,mf,cf,records]},
                files={p.name:sha(p) for p in out.glob('*.memh')},records=str(records.relative_to(ROOT)),
                nonclaims=['CPU golden only supplies comparison, never preloaded to destination','No OProj RTL PASS until pinned iDMA/Matrix replay and actual destination export complete'])
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
