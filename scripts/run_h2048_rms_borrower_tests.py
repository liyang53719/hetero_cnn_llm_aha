#!/usr/bin/env python3
"""Bounded production-service RMS borrower RTL tests with immutable receipts.

Synthetic control tests run by default. Frozen real inputs require explicit
manifest pins. A successful run is a local RMS operator result, not a block pass.
"""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, time
from pathlib import Path
import run_elementwise_register_loan_tests as common
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT/'chisel/continuous_prefill'

def require(ok, why):
    if not ok: raise ValueError(why)
def record(p):
    p=Path(p).resolve(); raw=p.read_bytes()
    return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def sources():
    result=common.sources()
    for name in ('run_h2048_rms_borrower_tests.py','prepare_h2048_borrower_replay.py','test_prepare_h2048_borrower_replay.py'):
        p=ROOT/'scripts'/name;result[str(p.resolve())]=record(p)['sha256']
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--actual-fixture-root',type=Path)
    p.add_argument('--tokens',default='1,16,128')
    p.add_argument('--scalar-epilogue',action='store_true',
        help='new same-bank H2048 Scalar ablation; production core.elem remains configured but idle')
    for m in (1,16,128):p.add_argument(f'--m{m}-manifest-sha256')
    a=p.parse_args();require(not a.out.exists(),'fresh evidence directory required')
    wrapper=shutil.which('sbt-chiseltest');require(wrapper is not None,'source pinned toolchain env.sh')
    env=os.environ.copy();fixtures=[];tokens=[]
    env['HETERO_H2048_USE_VECTOR_EPILOGUE']='false' if a.scalar_epilogue else 'true'
    epilogue='scalar' if a.scalar_epilogue else 'vector'
    tests=['heteronpu.continuous.GdnRmsNormFixedBankOwnerSpec',
           'heteronpu.continuous.GdnRmsNormFixedBankCoreSpec','heteronpu.continuous.GdnRmsNormOwnerSpec']
    if a.scalar_epilogue:
        tests=['heteronpu.continuous.GdnRmsNormFixedBankScalarBaselineSpec']
    if a.actual_fixture_root is not None:
        tokens=[int(x) for x in a.tokens.split(',')]
        require(tokens and len(set(tokens))==len(tokens) and all(x in (1,16,128) for x in tokens),'supported distinct token cases')
        tests=['heteronpu.continuous.GdnRmsNormFixedBankReplaySpec']
        env['HETERO_H2048_FIXTURE_ROOT']=str(a.actual_fixture_root.resolve())
        env['HETERO_H2048_REPLAY_TOKENS']=','.join(map(str,tokens))
        for m in tokens:
            d=a.actual_fixture_root/('h2048_borrower_replay_m1_from_m16' if m==1 else f'h2048_borrower_replay_m{m}')
            manifest=record(d/'manifest.json');pin=getattr(a,f'm{m}_manifest_sha256')
            require(pin is not None and re.fullmatch('[0-9a-f]{64}',pin) and manifest['sha256']==pin,'explicit fixture manifest pin')
            data=json.loads((d/'manifest.json').read_bytes())
            require(data['tokens']==m and data['width']==2048,'fixture dimensions')
            require(data['allowed_dut_input_files']==['stimulus/input.bf16le','stimulus/weights.bf16le'],'DUT input allowlist')
            require(set(data['assertion_only_files'])==set(data['files'])-set(data['allowed_dut_input_files']),'assertion-only partition')
            for name,expected in data['files'].items():
                path=(d/name).resolve();require(path.is_relative_to(d.resolve()),'fixture path escape')
                r=record(path);require(r['bytes']==expected['bytes'] and r['sha256']==expected['sha256'],'fixture identity '+name)
                require(expected['role']==('DUT_MEMORY_INPUT' if name.startswith('stimulus/') else 'HOST_ASSERTION_ONLY'),'fixture role')
                fixtures.append(r)
            producer=record(data['summary']['path'])
            require(producer['bytes']==data['summary']['bytes'] and producer['sha256']==data['summary']['sha256'],'producer summary identity')
            fixtures.extend((manifest,producer));env[f'HETERO_H2048_M{m}_MANIFEST_SHA']=pin
    else:
        require(all(getattr(a,f'm{m}_manifest_sha256') is None for m in (1,16,128)),'dangling actual fixture pin')
    a.out.mkdir(parents=True)
    before=sources();summary=dict(status='RUNNING',scope='LOCAL_CORE_SERVICE_RMS_ACTUAL_RTL' if fixtures else 'LOCAL_RMS_SYNTHETIC_RTL',
        tests=tests,tokens=tokens,source_before=before,wrapper=record(wrapper),fixtures=fixtures,
        arithmetic_inverse_from_dut=True,full_block=False,kernel_end_to_end=False,physical_ppa=False,
        epilogue=epilogue,borrower_bank_bytes=6144,
        generated_records_scope='CACHED_DIRECTORY_INVENTORY_ONLY',
        generated_records_current_run_causality_verified=False,
        generated_records_epilogue_identity_verified=False,
        baseline_identity='H2048_SAME_BANK_SCALAR_ABLATION' if a.scalar_epilogue else 'H2048_VECTOR_BORROWER')
    dest=a.out/'summary.json';dest.write_text(json.dumps(summary,indent=2)+'\n')
    started=time.monotonic()
    with (a.out/'test.log').open('w') as output:
        process=subprocess.Popen([wrapper,'testOnly '+' '.join(tests)],cwd=PROJECT,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=1200 if fixtures else 600)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            output.write('\nTIMEOUT: process group terminated\n');code=124
    log=(a.out/'test.log').read_text();after=sources()
    count=sum(int(x) for x in re.findall(r'Total number of tests run: (\d+)',log))
    markers=[line for line in log.splitlines() if line.startswith(('GDN_RMSNORM_FIXED_BANK_RTL','H2048_FIXED_BANK_ACTUAL_RTL_PASS'))]
    observation_markers=[line for line in log.splitlines() if line.startswith(('H2048_PHASE_CYCLES','H2048_ARITHMETIC_CYCLES'))]
    actual_tokens=[int(re.search(r'tokens=(\d+)',line).group(1)) for line in markers if line.startswith('H2048_FIXED_BANK_ACTUAL_RTL_PASS')]
    # Historical test directories may remain, and a simulator may reuse caches.
    # This inventory is deliberately NOT evidence of current-run generation or
    # mode-specific arithmetic/resource identity. Existing summaries stay intact.
    generated=set()
    for directory in (PROJECT/'test_run_dir').glob('GdnRmsNormFixedBank*'):
        generated.update(f for f in directory.rglob('*') if f.is_file() and f.suffix in ('.sv','.fir','.so'))
    unchanged=before==after;fixture_unchanged=all(record(r['path'])==r for r in fixtures)
    expected=1 if fixtures or a.scalar_epilogue else 3
    good=code==0 and unchanged and fixture_unchanged and count==expected and bool(re.search(r'canceled 0, ignored 0, pending 0',log)) and 'All tests passed.' in log
    if fixtures:good=good and actual_tokens==tokens
    good=good and bool(markers) and all(f'epilogue={epilogue}' in line for line in markers)
    summary.update(status='PASS_LOCAL_RMS_RTL_ONLY' if good else 'FAILED',returncode=code,host_seconds=time.monotonic()-started,
        source_after=after,sources_unchanged=unchanged,fixtures_unchanged=fixture_unchanged,test_count=count,
        markers=markers,observation_markers=observation_markers,log=record(a.out/'test.log'),generated_records=[record(x) for x in sorted(generated)])
    dest.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('status','test_count','sources_unchanged','fixtures_unchanged','scope','host_seconds')}))
    raise SystemExit(0 if good else 1)
if __name__=='__main__':main()
