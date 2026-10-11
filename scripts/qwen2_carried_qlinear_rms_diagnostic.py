#!/usr/bin/env python3
"""Bounded single-operator diagnostic on sealed carried M128 inputs. No chain replay."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'src'))
import qwen2_carried_prefill_candidate as M
R,N=M.R,M.N


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--result-sha256',required=True)
    p.add_argument('--payload',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run=a.run.resolve();out=a.out.resolve()
    R.require(not out.exists(),'refuse existing diagnostic output')
    R.require(R.file_sha(run/'RESULT.json')==a.result_sha256,'sealed carried receipt changed')
    report=json.loads((run/'RESULT.json').read_text());M.validate_frozen(run,report,ROOT)
    R.require(report['tokens']==128 and report['status']=='DIAGNOSTIC_NOT_ACCEPTED','wrong diagnostic source')
    records={x['name']:x for x in report['tensors']};files={x['path']:x for x in report['artifacts']}
    actual={n:M.read_bound_tensor(run/'tensors'/records[n]['path'],records[n]['shape'],records[n]['sha256'])
            for n in ('x','n0','qr')}
    native={n:M.read_bound_tensor(run/'references/official_self_cache'/(n+'.f32le'),actual[n].shape,
             files['references/official_self_cache/'+n+'.f32le']['sha256']) for n in ('x','n0','qr')}
    payload_module=R.load_module(ROOT/'scripts/qwen2_layer0_payload.py','operator_payload')
    manifest,payload=payload_module.load_payload(ROOT,a.payload)
    R.require(R.file_sha(a.payload/'manifest.json')==report['payload_manifest_sha256'],'operator payload differs')
    shapes={r['local_name']:r['shape'] for r in manifest['tensors']}
    def weight(name):
        return torch.from_numpy((np.frombuffer(payload[name],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(shapes[name])).to(torch.bfloat16)
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    module,identity=N.runtime_identity(ROOT)
    R.require(identity==report['official_reference_identity'],'operator official runtime differs')
    source=(run/'candidate.cpp').read_text()
    R.require(R.sha(source.encode())==report['build']['cpp_sha256'],'carried producer source changed')
    norm=R.section(source,'  void norm(','  void dense(')
    helpers,_,_=R.extract_sources(ROOT)
    driver=helpers+R.HOST_PROBES+R.DRIVER+norm+'''\n};
int main(int argc,char** argv){try{
  need(argc==3,"usage: rms_only readonly_arena output");verifyFloatEnvironment();
  SoftwareRecipe model(128);std::ifstream f(argv[1],std::ios::binary|std::ios::ate);
  need(bool(f)&&uint64_t(f.tellg())==WRITABLE_START,"readonly arena length");
  f.seekg(0);f.read(reinterpret_cast<char*>(model.reference.data()),WRITABLE_START);need(bool(f),"arena read");
  model.norm(OFF_X,OFF_GAMMA0,OFF_N0);
  std::ofstream o(argv[2],std::ios::binary);o.write(reinterpret_cast<char*>(model.reference.data()+OFF_N0/4),128*H*4);
  need(bool(o),"norm write");return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
'''
    out.mkdir();(out/'rms_only.cpp').write_text(driver)
    (out/'block_layout.h').write_bytes((run/'block_layout.h').read_bytes())
    command=['/usr/bin/g++',*R.FLAGS,str(out/'rms_only.cpp'),'-o',str(out/'rms_only')]
    frozen=dict(status='DIAGNOSTIC_NOT_ACCEPTED',sealed_result_sha256=a.result_sha256,
        diagnostic_script_sha256=R.file_sha(Path(__file__)),source_cpp_sha256=report['build']['cpp_sha256'],
        norm_function_sha256=R.sha(norm.encode()),rms_only_cpp_sha256=R.file_sha(out/'rms_only.cpp'),
        readonly_arena_sha256=R.file_sha(run/'readonly_arena.f32le'),compile_command=command,
        official_reference_identity=identity,thread_limit=4,input_node_sha256={n:records[n]['sha256'] for n in actual})
    (out/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n');freeze_sha=R.file_sha(out/'FROZEN.json')
    build=subprocess.run(command,capture_output=True,text=True,timeout=30)
    (out/'build.log').write_text(build.stdout+build.stderr);R.require(build.returncode==0,'RMS helper compile failed')
    started=time.monotonic()
    done=subprocess.run([str(out/'rms_only'),str(run/'readonly_arena.f32le'),str(out/'rms_only_n0.f32le')],
                        capture_output=True,text=True,timeout=30)
    (out/'run.log').write_text(done.stdout+done.stderr);R.require(done.returncode==0,'RMS helper failed')
    cpp_n0=np.fromfile(out/'rms_only_n0.f32le',dtype='<f4').reshape(actual['n0'].shape)
    norm_layer=module.Qwen2RMSNorm(1536,eps=1e-6).to(torch.bfloat16).eval()
    norm_layer.weight=torch.nn.Parameter(weight('input_layernorm.weight'),requires_grad=False)
    q=weight('self_attn.q_proj.weight');bias=weight('self_attn.q_proj.bias')
    with torch.inference_mode():
        native_n0=norm_layer(torch.from_numpy(actual['x']).to(torch.bfloat16)).float().numpy()
        conditional=torch.nn.functional.linear(torch.from_numpy(actual['n0']).to(torch.bfloat16),q,bias).float().numpy()
        original=torch.nn.functional.linear(torch.from_numpy(native['n0']).to(torch.bfloat16),q,bias).float().numpy()
    # Observational decomposition of the current RMS equations, checked against
    # the exact extracted C++ helper before its per-row scalars are reported.
    x=actual['x'];squares=np.multiply(x,x,dtype=np.float32);total=np.zeros(x.shape[:-1]+(1,),dtype='<f4')
    for k in range(1536):total=np.add(total,squares[...,k:k+1],dtype=np.float32)
    mean=np.multiply(total,np.float32(1/1536),dtype=np.float32)
    variance=np.add(mean,np.float32(1e-6),dtype=np.float32)
    inverse=np.divide(np.float32(1),np.sqrt(variance,dtype=np.float32),dtype=np.float32)
    gamma=norm_layer.weight.float().detach().numpy()
    explained=N.bf16(N.bf16(x*inverse)*gamma)
    torch_mean=torch.from_numpy(x).pow(2).mean(-1,keepdim=True)
    torch_inverse=torch.rsqrt(torch_mean+1e-6)
    def metric(a,b):return N.compare(a,b)
    result=dict(**frozen,frozen_sha256=freeze_sha,status_detail='MODEL_ONLY_SINGLE_OPERATOR_DIAGNOSTIC',
        whole_chain_replayed=False,original_receipt_modified=False,raw_linear_pre_bias_export_available=False,
        calls=dict(extracted_original_cpp_rms=1,official_eager_rms=1,official_eager_q_linear=2),
        rms=dict(extracted_cpp_vs_sealed_actual=metric(cpp_n0,actual['n0']),
                 explicit_sequential_equations_vs_extracted_cpp=metric(explained,cpp_n0),
                 official_rms_vs_sealed_official=metric(native_n0,native['n0']),
                 original_actual_vs_official=metric(actual['n0'],native['n0']),
                 rows={str(t+128):dict(sequential_square_sum=float(total[0,t,0]),
                    sequential_mean=float(mean[0,t,0]),
                    official_mean=float(torch_mean[0,t,0]),sequential_inverse_sqrt=float(inverse[0,t,0]),
                    official_rsqrt=float(torch_inverse[0,t,0])) for t in (46,76)}),
        q_linear=dict(actual_qr_vs_official_linear_conditioned_actual_n0=metric(actual['qr'],conditional),
                      actual_qr_vs_official_linear_conditioned_official_n0=metric(actual['qr'],original),
                      official_n0_control_vs_sealed_official_qr=metric(original,native['qr']),
                      changed_input_only_effect=metric(conditional,original)),
        threshold_policy=N.load_policy(ROOT),seconds=time.monotonic()-started,
        rms_binary_sha256=R.file_sha(out/'rms_only'))
    R.require(result['rms']['extracted_cpp_vs_sealed_actual']['bit_exact']
              and result['rms']['explicit_sequential_equations_vs_extracted_cpp']['bit_exact']
              and result['rms']['official_rms_vs_sealed_official']['bit_exact']
              and result['q_linear']['official_n0_control_vs_sealed_official_qr']['bit_exact'],'operator control mismatch')
    R.require(R.file_sha(out/'FROZEN.json')==freeze_sha and R.file_sha(run/'RESULT.json')==a.result_sha256
              and R.file_sha(run/'readonly_arena.f32le')==frozen['readonly_arena_sha256'],'operator source changed')
    (out/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({section:{k:{z:v[z] for z in ('max_abs','mean_abs','different_elements','bit_exact')}
                              for k,v in result[section].items() if isinstance(v,dict) and 'max_abs' in v}
                      for section in ('rms','q_linear')},indent=2))
    return 1


if __name__=='__main__':raise SystemExit(main())
