"""Explicit bounded local M128 RMS+Linear diagnostic. No full block or CI."""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
DATA=ROOT/'work/qwen2_live_qkv_inputs_m128/recovered_20261015_0018/inputs'
OLD=ROOT/'work/qwen2_fullblock_recovery_numeric_m128_20261015/attempt01'
OUT=ROOT/'work/qwen2_aten_q_projection_candidate/local01'
INPUTS={
 'x':'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df',
 'gamma0':'320e4ac88269676897cf9c3b4996f966a6100ced2bc0f684216c200bc82b7180',
 'wq':'ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72',
 'bq':'47506ca51cfd69119a774c09466b718c0b400b84b9a392bc1e9bcb691f28b72d'}
COLS=[0,1,31,32,127,255,1023,1535]
def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def run(*,execute=False):
    if not execute:return {'status':'NOT_EXECUTED'}
    start=time.monotonic()
    resource.setrlimit(resource.RLIMIT_CPU,(90,90))
    resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
    need(not OUT.exists(),'fresh fixed output required')
    need('torch' not in sys.modules,'fresh torch process required')
    need(os.environ.get('ATEN_CPU_CAPABILITY')=='avx2','ATen AVX2 before import')
    need(os.environ.get('PYTHONPATH')==str(ROOT/'work/runtime_recovery/site-packages'),'fixed installed runtime')
    sys.path.insert(0,str(ROOT))
    from candidates.qwen2_runtime_relocation import runtime
    pins=runtime._expected('full29')
    native=runtime.check_native(pins,family='full29')
    sources={str(p.relative_to(ROOT)):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.cpp')}
    raw={k:(DATA/(k+'.bin')).read_bytes() for k in INPUTS}
    need(all(hashlib.sha256(v).hexdigest()==INPUTS[k] for k,v in raw.items()),'fixed input identities')
    old=json.loads((OLD/'RESULT.json').read_text())
    old_report_sha=sha(OLD/'RESULT.json')
    need(all(old['input_identity_before'][k]['sha256']==v for k,v in INPUTS.items()),'old input identity differs')
    old_payload={}
    old_records={}
    for name in ('n0','qr'):
        record=next(p for p in old['producers'] if p['name']==name)
        need(record['owner_terminal'] is True and record['finite'] is True and record['ack_bytes']==record['bytes'], 'old producer not complete')
        old_payload[name]=(OLD/(name+'.f32le')).read_bytes()
        need(hashlib.sha256(old_payload[name]).hexdigest()==record['sha256'],'old payload hash')
        old_records[name]=record
    source_drift=[p for p,h in old['source_sha256_before'].items() if sha(ROOT/p)!=h]
    # Explicitly authorized historical-admission drift; never inherited as a
    # current closure PASS. All other source identities must still match.
    known_drift={'candidates/qwen2_fullblock_recovery/audit_probe.py',
                 'candidates/qwen2_fullblock_recovery/gates.py'}
    need(set(source_drift)==known_drift,'unexpected arithmetic/input/source drift')
    import torch
    import numpy as np
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    def runtime_state():
        return dict(torch=torch.__version__,commit=torch.version.git_version,
            capability=torch.backends.cpu.get_cpu_capability(),threads=torch.get_num_threads(),
            interop_threads=torch.get_num_interop_threads(),mkldnn_enabled=torch.backends.mkldnn.enabled,
            deterministic=torch.are_deterministic_algorithms_enabled())
    expected=dict(torch='2.10.0+cpu',commit='449b1768410104d3ed79d3bcfe4ba1d65c7f22c0',
        capability='AVX2',threads=4,interop_threads=1,mkldnn_enabled=False,deterministic=True)
    need(runtime_state()==expected,'local candidate runtime mismatch')
    src='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
    need(sha(ROOT/src)==pins['sources'][src]['sha256'],'official model source identity')
    # Execute the unmodified official RMS class only, not a rewritten formula.
    tree=ast.parse((ROOT/src).read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen2RMSNorm')
    ns={'torch':torch,'nn':torch.nn}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),src,'exec'),ns)
    x=np.frombuffer(raw['x'],'<f4').reshape(128,1536).copy()
    gamma=np.frombuffer(raw['gamma0'],'<f4').copy()
    w=np.frombuffer(raw['wq'],'<u2').reshape(1536,1536).copy()
    bias=np.frombuffer(raw['bq'],'<f4').copy()
    norm=ns['Qwen2RMSNorm'](1536).to(torch.bfloat16)
    linear=torch.nn.Linear(1536,1536,bias=True,dtype=torch.bfloat16)
    with torch.no_grad():
        norm.weight.copy_(torch.from_numpy(gamma).to(torch.bfloat16))
        linear.weight.copy_(torch.from_numpy(w.T.copy()).view(torch.bfloat16))
        linear.bias.copy_(torch.from_numpy(bias).to(torch.bfloat16))
        n0=norm(torch.from_numpy(x).reshape(1,128,1536).to(torch.bfloat16))
        need(n0.is_contiguous() and tuple(n0.shape)==(1,128,1536),'original Linear geometry')
        official=linear(n0).float().numpy().reshape(128,1536).copy()
        n0f=n0.float().numpy().reshape(128,1536).copy()
    need(n0f.tobytes()==old_payload['n0'],'old n0 not equal to new official n0')
    from scripts import qwen2_layer0_model_gate as gate
    policy=gate.load_policy(ROOT)
    need(policy['operator']=={'max_abs':0.03125,'mean_abs':0.005},'original operator threshold drift')
    measured=np.frombuffer(old_payload['qr'],'<f4').reshape(128,1536)
    metrics=gate.compare(measured,official)
    OUT.mkdir(parents=True)
    from candidates.qwen2_aten_q_projection_candidate.model import Candidate,compile_library,SCHEDULE
    command=compile_library(OUT/'candidate.so',execute=True)
    candidate=Candidate(OUT/'candidate.so')
    candidate_n0=candidate.rms(x,gamma)
    rms_metrics=gate.compare(candidate_n0,n0f)
    # Candidate input is produced from raw x/gamma, never official n0.
    candidate_raw,candidate_q=candidate.project(candidate_n0,w,bias,COLS)
    candidate_metrics=gate.compare(candidate_q,official[:,COLS].copy())
    need(runtime_state()==expected,'runtime drift')
    need(runtime.check_native(pins,family='full29')==native,'native drift')
    need(all(sha(ROOT/p)==h for p,h in sources.items()),'candidate source drift')
    need(all(sha(DATA/(k+'.bin'))==v for k,v in INPUTS.items()),'input drift')
    need(sha(OLD/'RESULT.json')==old_report_sha and all(sha(OLD/(n+'.f32le'))==r['sha256'] for n,r in old_records.items()),'old receipt drift')
    report=dict(schema=1,status='COMPLETED_LOCAL_DIAGNOSTIC',scope='M128 RMS plus Q projection only',
        official_linear_shape=[1,128,1536],official_linear_output=[1,128,1536],runtime=expected,
        local_native_identity=native,ci_runtime_equivalence_claimed=False,sources=sources,
        input_sha256=INPUTS,old_result_status=old['status'],old_producers=old_records,
        old_source_closure_unchanged=False,old_admission_audit_source_drift=source_drift,
        all_other_old_source_identities_match=True,old_n0_equals_new_official=True,
        old_model_qr=metrics,old_model_qr_verdict=gate.stage_verdict('qr',metrics,'bf16',policy),
        old_dut_fresh_executed=False,fullblock_executed=False,rtl_executed=False,
        policy=policy,candidate_rms=rms_metrics,candidate_qr_selected=candidate_metrics,
        candidate_columns=COLS,candidate_schedule=SCHEDULE,compiler_argv=command,
        candidate_library_sha256=sha(OUT/'candidate.so'),host_wall_seconds=time.monotonic()-start,
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        limits=dict(cpu_seconds=90,address_space_bytes=4<<30,external_wall_seconds=150),
        limitation='Existing failed fullblock attempt prefix artifact versus new official subchain; no new fullblock/RTL acceptance.')
    (OUT/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:report[k] for k in ('status','old_model_qr_verdict','candidate_rms','candidate_qr_selected','host_wall_seconds')}))
    return report

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args()
    run(execute=a.execute)
