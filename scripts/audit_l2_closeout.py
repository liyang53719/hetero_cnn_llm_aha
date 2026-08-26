#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
def clean(path):return subprocess.run(["git","-C",str(ROOT/path),"status","--porcelain"],capture_output=True,text=True,check=True).stdout==""
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--pytest-log",type=Path,required=True);p.add_argument("--open-log",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 pytest=a.pytest_log.read_text(errors="replace");opent=a.open_log.read_text(errors="replace")
 aha=(ROOT/"work/results/l2_aha_garnet_full_numerical.log").read_text(errors="replace")
 idma=load("work/results/l2_kv_idma_basic/vcs/result.json")
 matrix=load("work/results/l2_gemmini_v2_coverage/result.json")
 boundary=load("work/results/l2_descriptor_v2_pipeline/macro_boundary.json")
 top=(ROOT/"rtl/integration/hetero_npu_gemmini_rocc_integration_v0.sv").read_text()
 checks={
  "python_62_pass":"62 passed" in pytest,
  "open_rtl":"OPEN_RTL_GATE_PASS" in opent,
  "matrix_pipeline":"GEMMINI_DESCRIPTOR_V2_PIPELINE_PASS" in opent,
  "matrix_shell_busy_event":"GEMMINI_ROCC_INTEGRATION_PASS" in opent,
  "matrix_retained_coverage":matrix.get("status")=="PASS" and matrix.get("upstream_clean") is True,
  "matrix_macro_boundary":boundary.get("status")=="PASS",
  "aha_input_readback":"AHA_GARNET_INPUT_READBACK_PASS" in aha,
  "aha_numerical":"AHA_GARNET_GAUSSIAN_NUMERICAL_PASS cycles=19914" in aha,
  "kv_open_rtl":"KV_DESCRIPTOR_V2_IDMA_ADAPTER_PASS" in opent,
  "kv_idma_vcs":idma.get("status")=="PASS" and idma.get("kv_idma_requests")==4,
  "kv_bf16_byte_exact":idma.get("bf16_byte_exact") is True,
  "production_matrix":"gemmini_descriptor_v2_pipeline u_gemmini_rocc" in top,
  "production_kv":"kv_descriptor_v2_idma_adapter u_kv" in top,
  "chipyard_clean":clean("work/upstream/chipyard_gemmini"),
  "aha_clean":clean("work/upstream/aha"),
  "idma_clean":clean("work/upstream/idma"),
 }
 result={"status":"PASS" if all(checks.values()) else "FAIL","canonical_stage":"L2",
         "scope":"Matrix+AHA+KV/iDMA wrapper-only macro integration","checks":checks,
         "cpu_affinity":"taskset -c 8-23","upstream_patches":0}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 print(json.dumps(result,sort_keys=True));return 0 if result["status"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
