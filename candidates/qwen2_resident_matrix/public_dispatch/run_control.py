#!/usr/bin/env python3
"""Opt-in actual current Host decoder RTL; downstream owner returns are mocks."""
import argparse,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import run_elementwise_register_loan_tests as common
BASE=Path(__file__).resolve().parent

def validate_fixture(root,pin):
    common.require(root.is_dir() and common.sha(root/'gate.json')==pin,'explicit gate manifest pin')
    gate=json.loads((root/'gate.json').read_bytes())
    common.require(gate['scope']=='METADATA_CONTROL_ONLY' and gate['arithmetic_executed'] is False,'fixture scope')
    common.require([v['directory'] for v in gate['fixtures']]==['m16','m128','m16_relocated'],'exact fixture set')
    for name,expected in gate['source_sha256'].items():
        p=(ROOT/name).resolve();common.require(p.is_relative_to(ROOT) and common.sha(p)==expected,'generated fixture source '+name)
    records=[common.record(root/'gate.json')]
    for entry in gate['fixtures']:
        folder=root/entry['directory'];manifest=folder/'manifest.json'
        common.require(common.sha(manifest)==entry['manifest_sha256'],'fixture manifest identity')
        data=json.loads(manifest.read_bytes());records.append(common.record(manifest))
        common.require(data['arithmetic_executed'] is False and data['weights_materialized'] is False,'no payload fixture')
        common.require(len(data['accepted_jobs'])==19 and len(data['expected_completions'])==21,'current control coverage')
        for table in data['tables'].values():
            path=(folder/table['file']).resolve();common.require(path.is_relative_to(folder.resolve()),'metadata path escape')
            common.require(common.sha(path)==table['sha256'] and path.stat().st_size==table['bytes'],'metadata identity')
            records.append(common.record(path))
    return records

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True)
    a.add_argument('--fixture-root',type=Path,required=True);a.add_argument('--gate-sha256',required=True);args=a.parse_args()
    out=args.out.resolve();common.require(not out.exists(),'fresh output directory')
    fixture=args.fixture_root.resolve();records=validate_fixture(fixture,args.gate_sha256)
    wrapper=shutil.which('sbt-chiseltest');common.require(wrapper,'source pinned toolchain env.sh')
    files=[p for p in BASE.iterdir() if p.is_file()]
    before=common.sources();before.update({str(p.resolve()):common.sha(p) for p in files})
    env=os.environ.copy();env['HETERO_PUBLIC21_FIXTURE_ROOT']=str(fixture)
    cmd=[wrapper,'set Test / unmanagedSources += file("'+str(BASE/'Qwen2Public21DispatchControlSpec.scala')+'")',
         'testOnly heteronpu.continuous.Qwen2Public21DispatchControlSpec']
    summary=dict(status='RUNNING',scope='CURRENT_MAIN_ACTUAL_PUBLIC21_DECODER_CONTROL_ONLY',source_before=before,command=cmd,
        fixtures=records,arithmetic_executed=False,owner_completion_mock=True,kernel_bound=False,numerical_acceptance=False,
        full_block_rtl=False,wrapper=common.record(wrapper),hardware_performance_measured=False)
    out.mkdir(parents=True);dest=out/'summary.json';dest.write_text(json.dumps(summary,indent=2)+'\n');start=time.monotonic()
    with (out/'test.log').open('w') as log:
        p=subprocess.Popen(cmd,cwd=ROOT/'chisel/continuous_prefill',env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            log.write('\nTIMEOUT process group terminated\n');code=124
    text=(out/'test.log').read_text();after={p:common.sha(p) for p in before}
    unchanged=all(common.record(r['path'])==r for r in records)
    markers=[x for x in text.splitlines() if x.startswith('PUBLIC21_CURRENT_')]
    ok=code==0 and before==after and unchanged and len(markers)==5 and 'All tests passed.' in text and 'Total number of tests run: 1' in text and 'canceled 0, ignored 0, pending 0' in text
    paths=ROOT/'chisel/continuous_prefill/test_run_dir/Current_Qwen2_public21_decoder_should_match_all_physical_dispatch_contracts_relocation_and_failclosed_lifetime_fences'
    generated=[common.record(p) for p in sorted(paths.rglob('*')) if p.is_file() and p.suffix in ('.sv','.fir','.so')]
    summary.update(status='PASS_ACTUAL_DECODER_CONTROL_ONLY' if ok else 'FAILED',returncode=code,host_seconds=time.monotonic()-start,
        source_after=after,sources_unchanged=before==after,fixtures_unchanged=unchanged,markers=markers,log=common.record(out/'test.log'),
        generated_records=generated,generated_records_scope='CURRENT_TEST_DIRECTORY_INVENTORY_CACHE_REUSE_POSSIBLE')
    dest.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:summary[k] for k in ('status','host_seconds','returncode','sources_unchanged','fixtures_unchanged')}))
    raise SystemExit(0 if ok else 1)
if __name__=='__main__':main()
