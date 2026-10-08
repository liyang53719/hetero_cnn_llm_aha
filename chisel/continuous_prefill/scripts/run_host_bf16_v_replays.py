#!/usr/bin/env python3
"""Replay authentic V windows on an already-passed immutable production Host DUT."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
from verify_host_bf16_v_fixture import verify
from pack_host_bf16_v_fixture import pack_fixture
from host_bf16_v_execution import pass_result
ROOT=Path(__file__).resolve().parents[3]
PACK=Path(__file__).with_name('pack_host_bf16_v_fixture.py')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify_compiled_sources(build):
    """Recheck real compiled sources/HF; historical receipts stay untouched."""
    build=Path(build);sources=json.loads((build/'sources.sha256.json').read_text())
    prefixes=('chisel/continuous_prefill/src/main/','chisel/p0_safety/src/main/','integration/gemmini/','rtl/matrix/','rtl/integration/')
    for name,digest in sources.items():
        if name.startswith(prefixes) or name=='chisel/continuous_prefill/tests/host_bf16_v.cpp':
            if sha(ROOT/name)!=digest:raise ValueError('compiled source changed: '+name)
    ready=build/'build_ready.json'
    hf=Path(json.loads(ready.read_text())['hardfloat_source']) if ready.is_file() else Path(os.environ.get('HARDFLOAT_SOURCE',ROOT/'work/upstream/hardfloat_continuous'))
    recorded=json.loads((build/'hardfloat.sha256.json').read_text())
    directory=hf/'hardfloat/src/main/scala'
    actual={str(p.relative_to(hf)):sha(p) for p in directory.glob('*.scala')}
    if not recorded or actual!=recorded:raise ValueError('HardFloat source changed/unavailable; provide the build’s HARDFLOAT_SOURCE')

def run_replays(build:Path,out:Path,*,full128=False,session=None,only_full128=False):
    build,out=Path(build).resolve(),Path(out).resolve();exe=build/'obj/VHostBlockTop'
    if not out.is_relative_to(ROOT/'work') or out.exists():raise ValueError('fresh output under ignored work required')
    if only_full128 and not full128:raise ValueError('full128 must be enabled')
    prior=json.loads((build/'result.json').read_text())
    if not prior['status'].startswith('PASS_PRODUCTION_HOST_V_ONLY') or not prior['native_operator_gate_pass'] or prior['canonical_bit_differences']!=0:
        raise ValueError('representative actual Host numerical pass required')
    if session is not None and session.fresh and (prior.get('official_manifest_sha256')!=session.manifest_sha256 or prior.get('fresh_official_executions')!=2 or prior.get('reused_official_executions')!=0):
        raise ValueError('fresh replay must follow this invocation’s representative pass')
    identity={str(p):sha(p) for p in (exe,build/'generated/HostBlockTop.sv')}
    if identity[str(exe)]!=prior['binary_sha256'] or identity[str(build/'generated/HostBlockTop.sv')]!=prior['rtl_sha256']:
        raise ValueError('passed DUT changed')
    verify_compiled_sources(build)
    cases=[] if only_full128 else [('baseline','cold',1,17),('avx2','carried',47,81)]
    if full128:cases += [(v,p,0,128) for v in ('baseline','avx2') for p in ('cold','carried')]
    out.mkdir();results=[]
    for variant,phase,base,count in cases:
        name=f'{variant}_{phase}_base{base}_count{count}';case=out/name;case.mkdir();fixture=case/'fixture'
        pack_fixture(fixture,variant=variant,phase=phase,token_base=base,token_count=count,session=session)
        authenticated=verify(fixture,session=session)
        with (case/'run.log').open('w') as log:
            completed=subprocess.run([str(exe),str(fixture),str(case/'outputs'),'pass'],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        (case/'simulation.exit').write_text(str(completed.returncode)+'\n')
        text=(case/'run.log').read_text();print(text.strip(),flush=True)
        if completed.returncode:raise RuntimeError('Host replay failed: '+name)
        numerical=pass_result(build,fixture,case/'outputs',case/'run.log')
        verify(fixture,session=session)
        results.append(dict(name=name,source=authenticated,**numerical))
        if any(sha(Path(p))!=digest for p,digest in identity.items()):raise ValueError('immutable DUT changed during replay')
        (out/'progress.json').write_text(json.dumps(results,indent=2)+'\n')
    verify_compiled_sources(build)
    report=dict(status='PASS_PRODUCTION_HOST_V_WINDOWS'+('_AND_FULL128' if full128 else ''),cases=results,
                immutable_dut=identity,scope='V-only Host route; native full-block failures remain open; no Q/K or performance acceptance')
    if session is not None:report.update(session.evidence())
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('build',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--full128',action='store_true',help='All baseline/AVX2 cold/carried rows, after representative actual Host pass')
    args=parser.parse_args()
    run_replays(args.build,args.output,full128=args.full128)

if __name__=='__main__':main()
