#!/usr/bin/env python3
"""Execute existing cold-repeat/fault driver against the pipelined Host DUT.

Unlike the non-pipelined weight-cache gate, this entry requires the real
StreamingDenseOwner, MatrixPipelineService, and 16-lane VectorSiluOwner.
This is a tiny two-layer lifecycle gate, NOT real-size performance evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from audit_matrix_topology import audit
from run_weight_burst_lifecycle import run, verify, require


def scope(base: Path) -> dict:
    data=json.loads((base/'generated/SCOPE.json').read_text())
    require(data.get('pipelined') is True and data.get('silu_lanes')==16 and data.get('dense_contexts')==5,
            'not the production pipeline')
    return audit(base/'generated/HostBlockTop.sv',4096)


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--verify-only',action='store_true')
    a=p.parse_args();base=a.base.resolve();out=a.output.resolve()
    topology=scope(base)
    if not a.verify_only:
        require(not a.output.is_symlink() and not out.exists(),'preserve previous outputs')
        run(a.repo.resolve(),base,out)
    result=verify(base,out)
    require(len(result['cases'])==7 and result['total_checked_fp32']==319488,'incomplete pipeline lifecycle')
    report={'status':'PASS_PRODUCTION_PIPELINE_TINY2_LIFECYCLE',
            'cases':result['cases'],'total_checked_fp32':319488,'bit_differences':0,
            'topology':topology,'actual_gate_rerun':not a.verify_only,
            'baseline_source_commit':(base/'source_base_commit.txt').read_text().strip(),
            'baseline_result_sha256':hashlib.sha256((base/'RESULT.json').read_bytes()).hexdigest(),
            'scope':{'tokens':16,'layers':2,'hidden':64,'ffn':128,'matrix_macs':4096,
                     'synthetic_weights':True,'pipelined':True,'same_dut_per_case':True,
                     'real_dimension_performance':False,'full_network_q1024':False,'dc_signoff':False}}
    text=json.dumps(report,indent=2,allow_nan=False)+'\n'
    if not a.verify_only:
        with (out/'PIPELINE_LIFECYCLE.json').open('x') as f:f.write(text)
    print(text,end='')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:
        raise SystemExit('PIPELINE_LIFECYCLE_REJECTED: '+str(e))
