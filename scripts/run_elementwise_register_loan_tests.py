#!/usr/bin/env python3
"""Bounded local RTL gate, with actual compile-source and generated-file receipts.

Default: two synthetic boundary/resource tests. Real frozen operand replay is an
explicit separate scope, never implied by a successful synthetic CI job.
"""
import argparse, hashlib, json, os, re, shutil, signal, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'chisel/continuous_prefill'
def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def record(p):
    p=Path(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def sources():
    hf=Path(os.environ['HARDFLOAT_SOURCE']).resolve()/'hardfloat/src/main/scala'
    paths=set()
    for directory in (PROJECT/'src/main/scala',PROJECT/'src/test/scala',ROOT/'chisel/p0_safety/src/main/scala',hf):
        require(directory.is_dir(),'compile directory '+str(directory));paths.update(directory.rglob('*.scala'))
    paths.update(ROOT/'integration/gemmini'/x for x in ('EmitHeteroFP32Alu.scala','EmitHeteroBF16Fma.scala'))
    paths.update((PROJECT/'build.sbt',PROJECT/'project/build.properties',Path(__file__).resolve(),ROOT/'scripts/prepare_rms_epilogue_loan_replay.py'))
    return {str(p.resolve()):sha(p) for p in sorted(paths)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--actual-fixture-root',type=Path);p.add_argument('--m16-manifest-sha256');p.add_argument('--m128-manifest-sha256');a=p.parse_args()
    require(not a.out.exists(),'fresh gate output');a.out.mkdir(parents=True)
    wrapper=shutil.which('sbt-chiseltest');require(wrapper is not None,'source the pinned toolchain env.sh first')
    env=os.environ.copy();tests=['heteronpu.continuous.ElementwiseRegisterLoanSpec'];fixtures=[]
    if a.actual_fixture_root is not None:
        tests.append('heteronpu.continuous.ElementwiseRegisterLoanReplaySpec');env['HETERO_RMS_LOAN_FIXTURE_ROOT']=str(a.actual_fixture_root.resolve())
        for m,h in ((16,a.m16_manifest_sha256),(128,a.m128_manifest_sha256)):
            manifest=a.actual_fixture_root/f'rms_loan_fixture_m{m}'/'manifest.json';require(h is not None and sha(manifest)==h,'actual fixture manifest pin')
            env[f'HETERO_RMS_LOAN_M{m}_MANIFEST_SHA']=h
            d=json.loads(manifest.read_bytes());require(d['tokens']==m and d['transactions']==m*128,'fixture shape')
            for name,r in d['files'].items():
                f=manifest.parent/name;require(f.stat().st_size==r['bytes'] and sha(f)==r['sha256'],'fixture file identity');fixtures.append(record(f))
            fixtures.append(record(manifest))
    else:require(a.m16_manifest_sha256 is None and a.m128_manifest_sha256 is None,'no dangling actual flags')
    before=sources();summary=dict(status='RUNNING',scope='LOCAL_EPILOGUE_RTL_WITH_FROZEN_ACTUAL_REPLAY' if fixtures else 'LOCAL_EPILOGUE_SYNTHETIC_RTL_ONLY',
        source_before=before,wrapper=record(wrapper),fixtures=fixtures,tests=tests,rtl_generated=False,rtl_simulated=False,full_block=False,top_bound=False)
    dest=a.out/'summary.json';dest.write_text(json.dumps(summary,indent=2)+'\n')
    started=time.monotonic()
    process=subprocess.Popen([wrapper,'testOnly '+' '.join(tests)],cwd=PROJECT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
    try:
        text,_=process.communicate(timeout=600);code=process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:text,_=process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);text,_=process.communicate()
        text+='\nTIMEOUT: bounded 600-second local RTL gate; process group terminated\n';code=124
    log=a.out/'test.log';log.write_text(text)
    after=sources();summary.update(returncode=code,source_after=after,sources_unchanged=before==after,host_seconds=time.monotonic()-started,log=record(log))
    summary['fixtures_unchanged']=all(record(x['path'])==x for x in fixtures)
    expected=3 if fixtures else 2
    summary['test_count']=sum(int(x) for x in re.findall(r'Total number of tests run: (\d+)',text))
    summary['zero_skips']=bool(re.search(r'canceled 0, ignored 0, pending 0',text))
    summary['markers']=[line for line in text.splitlines() if line.startswith(('ELEMENTWISE_REGISTER_LOAN_','RMS_EPILOGUE_ACTUAL_RTL_REPLAY_PASS'))]
    paths=set((ROOT/'work/elementwise_register_loan_rtl').glob('*'))
    for directory in (PROJECT/'test_run_dir').glob('ElementwiseRegisterLoan*'):
        paths.update(f for f in directory.rglob('*') if f.is_file() and f.suffix in ('.sv','.fir','.so'))
    summary['generated_records']=[record(x) for x in sorted(paths) if x.is_file()]
    success=code==0 and before==after and summary['fixtures_unchanged'] and summary['test_count']==expected and summary['zero_skips'] and 'All tests passed.' in text
    summary.update(status='PASS_LOCAL_EPILOGUE_RTL_ONLY' if success else 'FAILED',rtl_simulated=success,rtl_generated=success and bool(summary['generated_records']))
    dest.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','test_count','sources_unchanged','fixtures_unchanged','scope')}))
    raise SystemExit(0 if success else 1)
if __name__=='__main__':main()
