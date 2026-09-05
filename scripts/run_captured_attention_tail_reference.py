#!/usr/bin/env python3
"""Exact CPU golden from captured RTL attention, never a hardware fallback/PASS."""
import argparse,fcntl,hashlib,json,os,select,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wait-assembler',type=int);a=parser.parse_args()
    if a.wait_assembler:
        cmdline=Path(f'/proc/{a.wait_assembler}/cmdline')
        try:
            assert b'assemble_q1024_attention_payload.py' in cmdline.read_bytes()
            fd=os.pidfd_open(a.wait_assembler);events=select.poll();events.register(fd,select.POLLIN)
            print(f'WAIT_ASSEMBLER pid={a.wait_assembler} blocking_pidfd_no_polling',flush=True)
            events.poll();os.close(fd)
        except FileNotFoundError:pass
        except ProcessLookupError:pass
    gate=ROOT/'reports/execution/Q1024_ATTENTION_OPROJ_INPUT_RESULT.json'
    proof=json.loads(gate.read_text())
    assert proof['status']=='PASS_CAPTURED_ATTENTION_TO_OPROJ_INPUT'
    assert proof['independent_fp32_comparisons']==1572864 and proof['max_absolute_error']<=0.002
    captured=ROOT/'work/results/q1024_captured_attention_payload/attention_actual_token_major_fp32.bin'
    assert captured.stat().st_size==1024*1536*4 and sha(captured)==proof['fp32_sha256']
    inp=ROOT/'work/results/qwen2_q1024_layer0_tail_inputs'
    manifest=json.loads((inp/'manifest.json').read_text())
    assert manifest['model_revision']=='ba1cf1846d7df0a0591d6c00649f57e798519da8'
    for name,h in manifest['hashes'].items():assert sha(inp/name)==h
    out=ROOT/'work/results/q1024_tail_from_captured_attention';out.mkdir(exist_ok=True)
    link=out/'attention_fp32.bin'
    if link.is_symlink():assert link.resolve()==captured
    else:assert not link.exists();link.symlink_to(captured)
    lock=(ROOT/'work/results/q1024_continuous/coordinator.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
    source=ROOT/'src/qwen2_q1024_layer0_tail_backend.cpp'
    identity=dict(attention_sha256=sha(captured),input_manifest_sha256=sha(inp/'manifest.json'),source_sha256=sha(source))
    binary=out/'reference';jobs=[]
    def run(label,command):
        assert shutil.disk_usage(ROOT).free>50*1024**3
        log=out/f'{label}.log'
        full=['bash','scripts/run_memory_capped.sh','timeout','--signal=INT','--kill-after=30s','600',*command]
        job=dict(label=label,command=full,cwd=str(ROOT),start=time.time(),status='RUNNING')
        print(f'CPU_GOLDEN_START {label} hardware_pass=false',flush=True)
        with log.open('w') as stream:
            p=subprocess.Popen(full,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                env={**os.environ,'MIN_AVAILABLE_KIB':'10485760','MEMORY_HIGH':'24G','MEMORY_MAX':'30G','OMP_NUM_THREADS':'8','OMP_PROC_BIND':'true'})
            job['pid']=p.pid;(out/f'{label}.json').write_text(json.dumps(job,indent=2)+'\n');rc=p.wait()
        job.update(returncode=rc,status='PASS_REFERENCE_ONLY' if rc==0 else 'FAIL',log_sha256=sha(log),end=time.time())
        (out/f'{label}.json').write_text(json.dumps(job,indent=2)+'\n');jobs.append(job)
        assert rc==0,f'{label}: inspect {log}'
    assert not (out/'result.json').exists(),'Preserve prior reference run; inspect before reuse'
    run('build',['/usr/bin/g++','-std=c++20','-O3','-march=native','-fopenmp','-ffp-contract=off',str(source),'-o',str(binary)])
    for stage in ['oproj','gate','up','down']:run(stage,[str(binary),stage,str(inp),str(out),str(out)])
    expected={'oproj_fp32.bin':1024*1536*4,'residual1_fp32.bin':1024*1536*4,'postnorm_fp32.bin':1024*1536*4,
              'gate_fp32.bin':1024*8960*4,'up_fp32.bin':1024*8960*4,'silu_product_bf16.bin':1024*8960*2,
              'down_fp32.bin':1024*1536*4,'final_fp32.bin':1024*1536*4}
    outputs={}
    for name,size in expected.items():assert (out/name).stat().st_size==size;outputs[name]=sha(out/name)
    assert sha(source)==identity['source_sha256'] and sha(captured)==identity['attention_sha256']
    result=dict(status='PASS_CPU_TAIL_REFERENCE_FROM_CAPTURED_RTL_ATTENTION',identity=identity,output_sha256=outputs,jobs=jobs,
                measured_rtl_cycles=None,full_model_tokens_per_second=None,
                nonclaims=['CPU golden only, not RTL execution or fallback in a hardware performance trace','OProj and MLP still need full RTL payload replay','No complete decoder/model PASS'])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'reports/execution/Q1024_CAPTURED_TAIL_REFERENCE_RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'],flush=True)
if __name__=='__main__':main()
