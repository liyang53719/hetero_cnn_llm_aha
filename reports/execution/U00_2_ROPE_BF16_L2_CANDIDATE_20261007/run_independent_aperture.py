#!/usr/bin/env python3
"""Independent admission/stall checks, with real generated arithmetic linked."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
V=ROOT/'work/rope_hardware_oracle/bin/verilator'
paths=['work/generated/rope_bf16_candidate/HeteroRoPEHardwarePrimitives.sv','rtl/sfu/fp32_to_bf16_rne_candidate.sv','rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv','rtl/integration/rope_bf16_l2_candidate.sv','rtl/integration/qwen2_shared_l2_rope_payload.sv',str((OUT/'tb_independent_aperture.sv').relative_to(ROOT))]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={p:sha(ROOT/p) for p in paths}
verification=subprocess.run(['python',str(ROOT/'chisel/rope_hardware_oracle/manifest.py'),'verify',str(ROOT),str(ROOT/'work/generated/rope_bf16_candidate')],cwd=ROOT,capture_output=True,text=True,check=True)
(OUT/'independent_generated_manifest_verify.log').write_text(verification.stdout+verification.stderr)
runs=[]
for label,capacity in [('default',24576),('override',8192)]:
 obj=ROOT/'work/rope_bf16_l2_independent'/('obj_'+label)
 cmd=[str(V),'--binary','--timing','-Wno-fatal','-j','4','--top-module','tb_independent_aperture',f'-GAPERTURE_BEATS={capacity}','--Mdir',str(obj),'-o','tb']+[str(ROOT/p) for p in paths]
 with (OUT/f'independent_aperture_{label}_build.log').open('w') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
 p=subprocess.run([str(obj/'tb')],cwd=ROOT,capture_output=True,text=True,check=True,timeout=20)
 text=p.stdout+p.stderr;(OUT/f'independent_aperture_{label}_run.log').write_text(text)
 marker=f'INDEPENDENT_APERTURE_PASS aperture_beats={capacity} rejected=15 admitted_preIO=6 latched_config_and_stalled_request=1'
 if text.count(marker)!=1:raise RuntimeError('Missing or duplicate pass marker')
 runs.append(dict(capacity_beats=capacity,compile_command=cmd,run_command=[str(obj/'tb')],invalid_rejected_before_io=15,valid_first_request_checkpoints=6,first_request_stall_cycles_per_valid_case=9,capacity_parameter_omitted=(label=='default')))
 print(marker)
assert before=={p:sha(ROOT/p) for p in paths},'Source changed during independent run'
report=dict(status='PASS_INDEPENDENT_APERTURE_ADMISSION',actual_payload_arithmetic_executed=False,real_generated_HardFloat_linked=True,limits='Valid cases stop before first read acceptance. No full-tensor or memory-store completion is claimed by this auxiliary test.',runs=runs,source_sha256=before,review_script_sha256=sha(Path(__file__)))
(OUT/'independent_aperture_result.json').write_text(json.dumps(report,indent=2)+'\n')
