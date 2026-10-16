"""Pinned minimal real-owner compile closure. Preparation never invokes Scala/RTL."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
from candidates.qwen2_resident_matrix.raw_kv_parent.compose import ROOT,HERE,PREFIX,TARGETS,compose,sha,blob,need

SCALA='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
HEADER='// SPDX-License-Identifier: Apache-2.0\npackage heteronpu.continuous\nimport chisel3._\nimport chisel3.util._\n'

def section(text,start,end):
    need(text.count(start)==1 and text.count(end)==1,'ambiguous slice boundary')
    a=text.index(start);b=text.index(end,a)
    need(a<b,'slice ordering')
    return text[a:b]

def patch_one(tree,path,patch,first_hunks=None):
    text=(ROOT/patch).read_text();head='--- a/'+path+'\n'
    need(text.count(head)==1,'unique patch target required')
    body=head+text.split(head)[1].split('\n--- a/')[0]+'\n'
    # Some patches use diff --git separators; omit the following file header.
    body=body.split('\ndiff --git ')[0]+'\n'
    if first_hunks is not None:
        chunks=re.split(r'(?=^@@ )',body,flags=re.M)
        need(len(chunks)>first_hunks,'patch hunk closure')
        body=''.join(chunks[:first_hunks+1])
    subprocess.run(['patch','--batch','--fuzz=0','-p1'],input=body,text=True,cwd=tree,
                   check=True,capture_output=True,timeout=10)

def prepare(out, *, verify=True):
    out=Path(out);need(not out.exists(),'fresh compile-source directory required')
    pins=json.loads((HERE/'unit_pins.json').read_text()) if verify else None
    if verify:
        for p,h in pins['inputs'].items():need(blob((ROOT/p).read_bytes())==h,'unit source drift: '+p)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='parent-unit-source-') as d:
        tree=Path(d)/'source';compose(tree)
        for p in TARGETS:(out/Path(p).name).write_bytes((tree/p).read_bytes())
        for p in (SCALA+'Protocol.scala',SCALA+'BurstProtocol.scala',SCALA+'QwenOwnerProtocol.scala',
                  PREFIX+'MatrixAccumulatorSeedProtocol.scala'):
            dest=tree/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/p).read_bytes())
        for patch in ('transposed_route/combined_service.patch','transposed_seed/service_seed.patch'):
            patch_one(tree,SCALA+'BurstProtocol.scala',PREFIX+patch)
        # Only the policy and job ABI hunks precede QwenOwnerKernel. Kernel
        # selection/body is neither rewritten nor compiled in this unit.
        patch_one(tree,SCALA+'QwenOwnerProtocol.scala',PREFIX+'official_bf16/chisel_policy.patch',first_hunks=2)
        for p in (SCALA+'Protocol.scala',SCALA+'BurstProtocol.scala',PREFIX+'MatrixAccumulatorSeedProtocol.scala'):
            (out/Path(p).name).write_bytes((tree/p).read_bytes())
        q=(tree/(SCALA+'QwenOwnerProtocol.scala')).read_text()
        slices={
          'NumericPolicy':section(q,'sealed trait Qwen2NumericPolicy','/** Internal, decoded owner job.'),
          'OwnerKind':section(q,'object QwenOwnerKind','class QwenOwnerJob'),
          'OwnerJob':section(q,'class QwenOwnerJob','/** Internal cancellation/recovery only.'),
          'OwnerResult':section(q,'class QwenOwnerResult','/** No block launch is exposed.'),
          'Shape':section((ROOT/(SCALA+'Qwen2Block.scala')).read_text(),'case class QwenBlockShape(','case class BlockRegion('),
          'CycleProfile':section((ROOT/(SCALA+'StreamingDense.scala')).read_text(),'class DenseCycleProfile','class StreamingDenseOwner('),
          'F32':section((ROOT/(SCALA+'BlockFloat.scala')).read_text(),'object F32 {','class ScalarRequest'),
        }
        for name,text in slices.items():(out/(name+'.scala')).write_text(HEADER+text)
    generated={p.name:sha(p.read_bytes()) for p in sorted(out.glob('*.scala'))}
    slice_hashes={k:sha(v.encode()) for k,v in slices.items()}
    if verify:
        need(generated==pins['generated_sha256'],'compile closure drift')
        need(slice_hashes==pins['slice_sha256'],'exact original declaration slice drift')
    # Exact pinning is primary; these checks guard accidental scope expansion.
    source='\n'.join(p.read_text() for p in out.glob('*.scala'))
    need('import hardfloat' not in source and 'import gemmini' not in source,'arithmetic dependency leaked')
    need(set(re.findall(r'Module\(new (\w+)',source)) <= {'TransposedDenseBanks','TransposedDownDenseBanks','Queue'},'unexpected instantiated arithmetic/top')
    all_inputs=dict(pins['inputs']) if verify else {}
    parent=json.loads((HERE/'source_pins.json').read_text())
    all_inputs.update(parent['inputs'])
    for p in HERE.glob('*'):
        if p.is_file():all_inputs[str(p.relative_to(ROOT))]=blob(p.read_bytes())
    return dict(inputs={p:sha((ROOT/p).read_bytes()) for p in all_inputs},
                slices=slice_hashes,generated=generated,
                scope='actual Down owner and Banks; external synthetic Matrix/DMA control only')

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='parent-unit-prepare-') as d:
        result=prepare(Path(d)/'scala')
    print('PASS: prepared '+str(len(result['generated']))+' pinned Scala units; compile/RTL NOT RUN')
