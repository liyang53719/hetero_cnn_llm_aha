"""Explicit fixed-runtime synthetic all-tie witness; never a routing acceptance gate."""
import argparse,ast,json
from pathlib import Path
from types import SimpleNamespace
from .reference import ROOT,definition,sha
from ..qwen35_35b_rms import reference as rms

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists() or a.out.is_symlink() or not a.out.resolve().is_relative_to(ROOT/'work'):
        raise ValueError('fresh ignored work report required')
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    if not torch.set_flush_denormal(False):raise ValueError('gradual underflow required')
    runtime=rms.runtime_identity();cls=definition();scope=dict(torch=torch,nn=torch.nn,F=torch.nn.functional)
    exec(compile(ast.Module(body=[cls],type_ignores=[]),rms.SOURCE,'exec'),scope)
    model=scope[cls.name](SimpleNamespace(num_experts_per_tok=8,num_experts=256,hidden_size=2048)).to(torch.bfloat16)
    records=[]
    for m in (16,128):
        with torch.inference_mode(),torch.autocast(device_type='cpu',enabled=False):
            logits,scores,ids=model(torch.zeros(1,m,2048,dtype=torch.bfloat16))
        if tuple(logits.shape)!=(m,256) or tuple(scores.shape)!=(m,8) or tuple(ids.shape)!=(m,8):raise ValueError('original geometry')
        if not bool((scores==0.125).all() and (logits==0).all()):raise ValueError('zero fixture reference')
        records.append(dict(m=m,first_tie_ids=ids[0].tolist(),ids_sha256=sha(ids.numpy().astype('<i8').tobytes()),scores_sha256=sha(scores.view(torch.uint16).numpy().tobytes())))
    report=dict(scope='OFFICIAL_SYNTHETIC_ALL_ZERO_ROUTER_TIE_SMOKE_ONLY',actual_payload=False,candidate_owner=False,full_block=False,records=records,runtime=runtime)
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(records))
if __name__=='__main__':main()
