#!/usr/bin/env python3
"""Queue behind OProj and consume only its verified actual FP32 output."""
import fcntl,hashlib,json,os,re,shutil,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pack(path,words,width):
    with path.open('w') as stream:
        for i in range(0,len(words),16):stream.write(f'{sum(int(w)<<(width*j) for j,w in enumerate(words[i:i+16])):0128x}\n')
def main():
    out=ROOT/'work/results/q1024_captured_residual_fp32';out.mkdir(exist_ok=True)
    own=(out/'coordinator.lock').open('a');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a')
    print('WAIT_OPROJ_COMMON_LOCK blocking_no_polling',flush=True);fcntl.flock(lock,fcntl.LOCK_EX)
    ppath=ROOT/'reports/execution/Q1024_CAPTURED_OPROJ_FP32_RESULT.json';p=json.loads(ppath.read_text())
    assert p['status']=='PASS_FULL1024_OPROJ_FP32_NUMERICAL_ONLY'
    actual=ROOT/'work/results/q1024_captured_oproj_replay/actual_fp32.memh';assert sha(actual)==p['output_sha256']
    assert p['metrics']['checked_fp32']==1572864
    inputs=ROOT/'work/results/qwen2_q1024_layer0_tail_inputs';im=json.loads((inputs/'manifest.json').read_text())
    hidden=inputs/'hidden_bf16.bin';assert sha(hidden)==im['hashes'][hidden.name]
    reference=ROOT/'work/results/q1024_tail_from_captured_attention';ref=json.loads((reference/'result.json').read_text())
    expected=reference/'residual1_fp32.bin';assert sha(expected)==ref['output_sha256'][expected.name]
    fixture=ROOT/'work/results/q1024_captured_oproj_fp32/manifest.json';fm=json.loads(fixture.read_text())
    assert fm['source_sha256'][str(reference.relative_to(ROOT))+'/oproj_fp32.bin']==ref['output_sha256']['oproj_fp32.bin']
    # OProj collector proved every output word equal to this same exact reference.
    assert sha(fixture)==json.loads((ROOT/'reports/execution/CAPTURED_OPROJ_BUILD_RESULT.json').read_text())['fixture_sha256']
    assert not (out/'result.json').exists(),'Preserve completed residual run'
    pack(out/'hidden.memh',struct.unpack('<1572864H',hidden.read_bytes()),16)
    pack(out/'expected.memh',struct.unpack('<1572864I',expected.read_bytes()),32)
    source=[ROOT/'work/generated/l5_all_primitives/HeteroAllPrimitives.sv',ROOT/'rtl/sfu/fp32_vector_alu.sv',ROOT/'rtl/sfu/fp32_residual_stream.sv',ROOT/'tb/tb_captured_residual_fp32.sv']
    hashes={str(x.relative_to(ROOT)):sha(x) for x in source};jobs=[]
    def run(name,cmd):
        assert shutil.disk_usage(ROOT).free>50*1024**3
        full=['bash',str(ROOT/'scripts/run_memory_capped.sh'),'timeout','--signal=INT','--kill-after=30s','600',*map(str,cmd)]
        r=dict(status='RUNNING',command=full,start=time.time(),cwd=str(ROOT));log=out/f'{name}.log'
        with log.open('w') as f:
            child=subprocess.Popen(full,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,
                env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G'})
            r['pid']=child.pid;(out/f'{name}.json').write_text(json.dumps(r,indent=2)+'\n');rc=child.wait()
        r.update(returncode=rc,status='PASS' if rc==0 else 'FAIL',log_sha256=sha(log),end=time.time());jobs.append(r)
        (out/f'{name}.json').write_text(json.dumps(r,indent=2)+'\n');assert rc==0,str(log)
    run('build',[ROOT/'work/toolchain/conda/bin/verilator','--binary','--timing','--threads','4','-j','4','-Wno-fatal',
          '-MAKEFLAGS','AR=/usr/bin/ar CXX=/usr/bin/g++','--top-module','tb_captured_residual_fp32','--Mdir',out/'obj','-o','tb',*source])
    result_path=out/'actual_residual_fp32.memh'
    run('simulation',[out/'obj/tb',f'+VECTORS={out}',f'+ACTUAL_OPROJ={actual}',f'+OUTPUT={result_path}'])
    log=(out/'simulation.log').read_text();marker=re.search(r'CAPTURED_RESIDUAL_FP32_PASS rows=1024 values=1572864 beats=(\d+) cycles=(\d+) actual_oproj_input=1',log)
    assert marker and int(marker[1])==98304
    got=result_path.read_text().splitlines();gold=(out/'expected.memh').read_text().splitlines()
    assert len(got)==98304 and len(got)==len(gold) and all(int(x,16)==int(y,16) for x,y in zip(got,gold))
    for path,h in hashes.items():assert sha(ROOT/path)==h
    r=dict(status='PASS_ACTUAL_OPROJ_TO_FP32_RESIDUAL_NUMERICAL_STREAM',values=1572864,cycles=int(marker[2]),
           output_sha256=sha(result_path),oproj_proof_sha256=sha(ppath),input_sha256=sha(actual),hidden_sha256=sha(hidden),expected_sha256=sha(expected),
           source_sha256=hashes,jobs=jobs,full_model_tokens_per_second=None,
           nonclaims=['Real FP32 ALU arithmetic but file-fed stream test, not descriptor/DDR integrated residual','No full decoder/model performance or PPA PASS'])
    (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    (ROOT/'reports/execution/Q1024_CAPTURED_RESIDUAL_FP32_RESULT.json').write_text(json.dumps(r,indent=2)+'\n')
    print(r['status'],flush=True)
if __name__=='__main__':main()
