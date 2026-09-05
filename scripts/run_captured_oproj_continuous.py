#!/usr/bin/env python3
"""Full1024 FP32 OProj through real DMA/Matrix. Block on child exit, no polling."""
import fcntl,hashlib,json,os,re,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    out=ROOT/'work/results/q1024_captured_oproj_replay';out.mkdir(exist_ok=True)
    own=(out/'coordinator.lock').open('a');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
    buildpath=ROOT/'reports/execution/CAPTURED_OPROJ_BUILD_RESULT.json';build=json.loads(buildpath.read_text())
    assert build['status']=='PASS_OPROJ_SIMULATOR_BUILD_ONLY'
    sim=ROOT/build['binary'];assert sha(sim)==build['binary_sha256']
    for p,h in build['source_sha256'].items():assert sha(ROOT/p)==h
    fixture=ROOT/'work/results/q1024_captured_oproj_fp32';mp=fixture/'manifest.json';m=json.loads(mp.read_text())
    assert sha(mp)==build['fixture_sha256'] and m['operand_dtype']=='BF16' and m['output_dtype']=='FP32'
    for p,h in m['files'].items():assert sha(fixture/p)==h
    for p,h in m['source_sha256'].items():assert sha(ROOT/p)==h
    recipes=[ROOT/'scripts/oproj_fp32_start.tcl',ROOT/'scripts/oproj_fp32_resume.tcl']
    identity={str(p.relative_to(ROOT)):sha(p) for p in [sim,buildpath,mp,*recipes]}
    previous=None;chain=[];actual=out/'actual_fp32.memh'
    for segment in range(100):
        rp=out/f'segment_{segment:03d}.json'
        if rp.exists():
            r=json.loads(rp.read_text());assert r['identity']==identity and r['status'] in ['CHECKPOINT','NUMERICAL_COMPLETE']
            assert sha(Path(r['log']))==r['log_sha256']
        else:
            assert shutil.disk_usage(ROOT).free>50*1024**3
            if previous:
                for p,h in previous['checkpoint_files'].items():assert sha(Path(p))==h
            elif actual.exists():raise AssertionError('Preserve prior output; cannot start a new run over it')
            checkpoint=out/f'segment_{segment:03d}.chk';assert not checkpoint.exists()
            control=out/'next_control.tcl';control.write_text('set qwen_checkpoint_target {'+str(checkpoint)+'}\n')
            log=out/f'segment_{segment:03d}.log';recipe=recipes[bool(previous)]
            env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G'}
            if previous:env['QWEN_RESTORE_PATH']=previous['checkpoint']
            cmd=['bash',str(ROOT/'scripts/run_memory_capped.sh'),'timeout','--signal=INT','--kill-after=30s','600',str(sim),
                 '+OPERATOR=oproj','+PROJECTION=0','+BATCHES=64','+FULL_Q1024',f'+COMMANDS={fixture}/commands.memh',
                 f'+RECORDS={ROOT/m["records"]}',f'+ADDR={fixture}/addresses.memh',f'+INPUT_TENSOR={fixture}/activation.memh',
                 f'+WEIGHT_TENSOR={fixture}/weight.memh',f'+EXPECTED_TENSOR={fixture}/expected.memh',f'+OUTPUT_TENSOR={actual}',
                 '-ucli','-do',str(recipe)]
            r=dict(status='RUNNING',segment=segment,identity=identity,command=cmd,cwd=str(ROOT),start=time.time(),log=str(log),control_sha256=sha(control))
            print(f'OPROJ_CONTINUOUS_START segment={segment}',flush=True)
            with log.open('w') as stream:
                p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
                r['pid']=p.pid;rp.write_text(json.dumps(r,indent=2)+'\n');rc=p.wait()
            r.update(returncode=rc,end=time.time(),log_sha256=sha(log));text=log.read_text()
            try:
                assert rc==0 and not re.search(r'Fatal:|Error-\[|Error:|%Error',text)
                if previous:
                    entry=re.search(r'^SEGMENT_ENTRY_CYCLE (\d+)$',text,re.M)
                    assert entry and int(entry[1])==previous['saved_cycle']
                marker=re.search(r'^GROUP8_PINNED_IDMA_FP32_NUMERICAL_PASS .+$',text,re.M)
                if marker:
                    assert 'CAPTURED_ATTENTION_OPROJ_PINNED_IDMA_PASS' in text
                    metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',marker[0])}
                    assert metrics['batches']==64 and metrics['checked_fp32']==1572864 and metrics['useful_macs']==2415919104
                    assert metrics['read_bytes']==23592960 and metrics['write_bytes']==6291456 and metrics['flat_requests']==76800
                    assert metrics['wall_cycles']>0 and metrics['useful_macs']<=512*metrics['wall_cycles']
                    got=actual.read_text().splitlines();gold=(fixture/'expected.memh').read_text().splitlines()
                    assert len(got)==98304 and len(gold)==len(got) and all(int(a,16)==int(b,16) for a,b in zip(got,gold))
                    r.update(status='NUMERICAL_COMPLETE',metrics=metrics,output_sha256=sha(actual))
                else:
                    saved=re.search(r'^SEGMENT_SAVED_CYCLE (\d+)$',text,re.M)
                    assert saved and int(saved[1])>(previous['saved_cycle'] if previous else 0)
                    files=[checkpoint,Path(str(checkpoint)+'.ucli')]+sorted(Path(str(checkpoint)+'.FILES').rglob('*'))
                    assert checkpoint.is_file() and files[1].is_file() and len(files)>2
                    r.update(status='CHECKPOINT',saved_cycle=int(saved[1]),checkpoint=str(checkpoint),checkpoint_files={str(p):sha(p) for p in files if p.is_file()})
            except Exception:
                r['status']='FAILED';rp.write_text(json.dumps(r,indent=2)+'\n');raise
            rp.write_text(json.dumps(r,indent=2)+'\n')
        chain.append({'segment':segment,'receipt_sha256':sha(rp),'status':r['status']})
        if r['status']=='NUMERICAL_COMPLETE':
            assert sha(actual)==r['output_sha256']
            for p,h in build['source_sha256'].items():assert sha(ROOT/p)==h
            result=dict(status='PASS_FULL1024_OPROJ_FP32_NUMERICAL_ONLY',chain=chain,identity=identity,metrics=r['metrics'],output_sha256=sha(actual),
                        clock_hz=800000000,useful_mac_utilization=r['metrics']['useful_macs']/(512*r['metrics']['wall_cycles']),
                        full_model_tokens_per_second=None,nonclaims=['OProj projection only, not full decoder/model','No PPA closure for modified control','DDR bandwidth-envelope model not DRAM bank/refresh calibration'])
            (ROOT/'reports/execution/Q1024_CAPTURED_OPROJ_FP32_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
            print(result['status'],flush=True);return
        previous=r
    raise AssertionError('Segment guard exceeded; investigate without expanding budget')
if __name__=='__main__':main()
