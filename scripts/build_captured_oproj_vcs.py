#!/usr/bin/env python3
"""Build the existing pinned DMA/Matrix path, without regenerating any fixtures."""
import argparse,fcntl,hashlib,json,os,re,shlex,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_list():
    # Parse the existing explicit source array as text; never execute its build
    # script, which would regenerate unrelated Q/K/V fixtures.
    recipe=ROOT/'scripts/run_qwen2_group8_pinned_idma_vcs.sh'
    found=re.search(r';S=\(([^\n]+)\)\nDEBUG_ARGS=',recipe.read_text())
    assert found,'Canonical source list changed: audit before building'
    sources=[Path(x.replace('$ROOT',str(ROOT)).replace('$C',str(ROOT/'rtl/matrix/candidates')))
             for x in shlex.split(found[1])]
    assert len(sources)==len(set(sources)) and all(p.is_file() for p in sources)
    assert all('$' not in str(p) for p in sources)
    return recipe,sources
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--enumerate-only',action='store_true');a=parser.parse_args()
    recipe,sources=source_list()
    if a.enumerate_only:
        print(json.dumps(dict(status='SOURCE_ENUMERATION_ONLY_NOT_BUILD_PASS',sources=len(sources),recipe_sha256=sha(recipe))));return
    decision=ROOT/'reports/execution/Q1024_RESIDUAL_PRECISION_DECISION.json'
    policy=json.loads(decision.read_text())
    assert policy['status']=='APPROVED_IMPLEMENTATION_AND_REFERENCE_ALIGNED', 'Resolve OProj/residual BF16-vs-FP32 contract before build'
    fixture=ROOT/'work/results/q1024_captured_oproj'
    manifest=json.loads((fixture/'manifest.json').read_text())
    assert manifest['operation']=='l0.oproj' and manifest['dimensions']==[1024,1536,1536]
    for name,h in manifest['files'].items():assert sha(fixture/name)==h
    for name,h in manifest['source_sha256'].items():assert sha(ROOT/name)==h
    gate=ROOT/'reports/execution/Q1024_ATTENTION_OPROJ_INPUT_RESULT.json'
    assert sha(gate)==manifest['input_gate_sha256']
    assert json.loads(gate.read_text())['status']=='PASS_CAPTURED_ATTENTION_TO_OPROJ_INPUT'
    idma=ROOT/'work/upstream/idma';vd=idma/'target/sim/vcs'
    commit=subprocess.check_output(['git','-C',str(idma),'rev-parse','HEAD'],text=True).strip()
    assert commit=='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'
    assert not subprocess.check_output(['git','-C',str(idma),'status','--porcelain'],text=True).strip()
    axi=list((idma/'.bender/git/checkouts').glob('axi-*/include'));assert len(axi)==1,axi
    # This checkout uses VCS's default WORK mapping, not synopsys_sim.setup.
    assert (vd/'AN.DB').exists(),'Missing previously compiled pinned dependency library; reproduce baseline first'
    out=ROOT/'work/results/q1024_captured_oproj_build';out.mkdir(exist_ok=True)
    binary=vd/'simv_captured_oproj_checkpoint'
    assert not binary.exists(),'Preserve prior build identity; audit before rebuild'
    lock=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
    source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}
    tool=Path('/home/yang/tools/synopsys/vcs/W-2024.09/bin')
    jobs=[]
    def run(label,cmd):
        assert shutil.disk_usage(ROOT).free>50*1024**3
        full=['bash',str(ROOT/'scripts/run_memory_capped.sh'),'timeout','--signal=INT','--kill-after=30s','600',*map(str,cmd)]
        result=dict(command=full,cwd=str(vd),start=time.time(),status='RUNNING')
        log=out/f'{label}.log'
        with log.open('w') as stream:
            p=subprocess.Popen(full,cwd=vd,stdout=stream,stderr=subprocess.STDOUT,
                env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G'})
            result['pid']=p.pid;(out/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n');rc=p.wait()
        result.update(returncode=rc,status='PASS_BUILD_STEP_ONLY' if rc==0 else 'FAIL',log_sha256=sha(log),end=time.time())
        (out/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n');jobs.append(result)
        assert rc==0,f'Inspect {log}'
    run('analyze',[tool/'vlogan','-sverilog','-full64','-timescale=1ns/1ps','+define+SYNTHESIS','+define+USE_UPSTREAM_IDMA',
                   f'+incdir+{idma}/src/include',f'+incdir+{axi[0]}',f'+incdir+{ROOT}',*sources])
    run('elaborate',[tool/'vcs','-full64','-debug_access+r','-top','tb_qwen2_group8_pinned_idma','-o',binary])
    for path,h in source_hashes.items():assert sha(ROOT/path)==h
    result=dict(status='PASS_OPROJ_SIMULATOR_BUILD_ONLY',binary=str(binary.relative_to(ROOT)),binary_sha256=sha(binary),
                source_sha256=source_hashes,fixture_sha256=sha(fixture/'manifest.json'),idma_commit=commit,jobs=jobs,
                nonclaims=['No regenerated or edited generated RTL','Same DMA/Matrix RTL as projection path','No numerical replay or timing PASS yet'])
    (ROOT/'reports/execution/CAPTURED_OPROJ_BUILD_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'])
if __name__=='__main__':main()
