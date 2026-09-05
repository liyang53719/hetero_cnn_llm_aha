#!/usr/bin/env python3
"""Full captured OProj -> real residual arithmetic -> real fabric RTL, tile by tile."""
import fcntl,hashlib,json,os,re,shutil,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pack(path,values,width):
    n=512//width
    with path.open('w') as f:
        for i in range(0,len(values),n):f.write(f'{sum(int(w)<<(width*j) for j,w in enumerate(values[i:i+n])):0128x}\n')
def main():
    out=ROOT/'work/results/q1024_captured_residual_l2';out.mkdir(exist_ok=True)
    own=(out/'coordinator.lock').open('a');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    lock=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a')
    print('WAIT_COMMON_HEAVY_LOCK blocking_no_polling',flush=True);fcntl.flock(lock,fcntl.LOCK_EX)
    ppath=ROOT/'reports/execution/Q1024_CAPTURED_OPROJ_FP32_RESULT.json';p=json.loads(ppath.read_text())
    assert p['status']=='PASS_FULL1024_OPROJ_FP32_NUMERICAL_ONLY' and p['metrics']['checked_fp32']==1572864
    actual=ROOT/'work/results/q1024_captured_oproj_replay/actual_fp32.memh';assert sha(actual)==p['output_sha256']
    inp=ROOT/'work/results/qwen2_q1024_layer0_tail_inputs';im=json.loads((inp/'manifest.json').read_text())
    hidden=inp/'hidden_bf16.bin';assert sha(hidden)==im['hashes'][hidden.name]
    refdir=ROOT/'work/results/q1024_tail_from_captured_attention';ref=json.loads((refdir/'result.json').read_text())
    expected=refdir/'residual1_fp32.bin';assert sha(expected)==ref['output_sha256'][expected.name]
    fixture=ROOT/'work/results/q1024_captured_oproj_fp32/manifest.json';fm=json.loads(fixture.read_text())
    assert sha(fixture)==json.loads((ROOT/'reports/execution/CAPTURED_OPROJ_BUILD_RESULT.json').read_text())['fixture_sha256']
    assert fm['source_sha256'][str((refdir/'oproj_fp32.bin').relative_to(ROOT))]==ref['output_sha256']['oproj_fp32.bin']
    assert not (out/'result.json').exists(),'Preserve completed result'
    pack(out/'hidden_memory.memh',struct.unpack('<1572864H',hidden.read_bytes()),16)
    pack(out/'expected.memh',struct.unpack('<1572864I',expected.read_bytes()),32)
    sources=[ROOT/x for x in ['work/generated/l5_all_primitives/HeteroAllPrimitives.sv','rtl/sfu/fp32_vector_alu.sv','rtl/sfu/fp32_residual_stream.sv',
      'rtl/integration/bf16_residual_gearbox.sv','rtl/integration/residual_l2_stream_reader.sv','rtl/integration/residual_l2_stream_writer.sv','rtl/integration/residual_l2_tile.sv',
      'rtl/fabric/shared_l2_fabric.sv','tb/tb_captured_residual_l2_numeric.sv']]
    hashes={str(x.relative_to(ROOT)):sha(x) for x in sources};jobs=[]
    def run(label,cmd):
        assert shutil.disk_usage(ROOT).free>50*1024**3
        full=['bash',str(ROOT/'scripts/run_memory_capped.sh'),'timeout','--signal=INT','--kill-after=30s','600',*map(str,cmd)]
        r=dict(status='RUNNING',command=full,cwd=str(ROOT),start=time.time());log=out/f'{label}.log'
        with log.open('w') as f:
            child=subprocess.Popen(full,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,
                env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G'})
            r['pid']=child.pid;(out/f'{label}.json').write_text(json.dumps(r,indent=2)+'\n');rc=child.wait()
        r.update(status='PASS' if rc==0 else 'FAIL',returncode=rc,log_sha256=sha(log),end=time.time());jobs.append(r)
        (out/f'{label}.json').write_text(json.dumps(r,indent=2)+'\n');assert rc==0,str(log)
    run('build',[ROOT/'work/toolchain/conda/bin/verilator','--binary','--timing','--threads','4','-j','4','-Wno-fatal',
                '-MAKEFLAGS','AR=/usr/bin/ar CXX=/usr/bin/g++','--top-module','tb_captured_residual_l2_numeric','--Mdir',out/'obj','-o','tb',*sources])
    output=out/'actual_residual_fp32.memh'
    run('simulation',[out/'obj/tb',f'+VECTORS={out}',f'+ACTUAL_OPROJ={actual}',f'+OUTPUT={output}'])
    m=re.search(r'CAPTURED_RESIDUAL_L2_NUMERICAL_PASS tiles=64 values=1572864 local_cycles_sum=(\d+) bank_conflicts=(\d+)',(out/'simulation.log').read_text());assert m
    got=output.read_text().splitlines();gold=(out/'expected.memh').read_text().splitlines()
    assert len(got)==98304 and len(gold)==len(got) and all(int(a,16)==int(b,16) for a,b in zip(got,gold))
    for path,h in hashes.items():assert sha(ROOT/path)==h
    r=dict(status='PASS_FULL1024_RESIDUAL_REAL_ALU_BEHAVIORAL_FABRIC',fp32_values=1572864,tiles=64,
           local_tile_cycles_sum=int(m[1]),bank_conflicts=int(m[2]),output_sha256=sha(output),oproj_proof_sha256=sha(ppath),
           hidden_sha256=sha(hidden),expected_sha256=sha(expected),source_sha256=hashes,jobs=jobs,full_model_tokens_per_second=None,
           nonclaims=['Host TB stages tiles through fabric ports; no descriptor/DDR frontend in this test','Fabric banks are behavioral storage, not ARM macro closure','Local tile cycle sum is not full-request performance','No full-model or PPA PASS'])
    (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    (ROOT/'reports/execution/Q1024_CAPTURED_RESIDUAL_L2_RESULT.json').write_text(json.dumps(r,indent=2)+'\n')
    print(r['status'],flush=True)
if __name__=='__main__':main()
