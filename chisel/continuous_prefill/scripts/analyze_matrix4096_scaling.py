#!/usr/bin/env python3
"""Explain measured Matrix4096 scaling; never substitute a theoretical speedup.

Input must be the all-output comparison produced by compare_matrix4096_real2.
QK/Softmax/PV completion intervals are combined: their delayed completion events
are not independent timings of those three physical arithmetic operations.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

OPCODES = ["SFU_RMSNORM", "MATRIX_GEMM", "SFU_VECTOR", "SFU_ROPE",
           "MATRIX_GEMM", "SFU_VECTOR", "SFU_ROPE", "MATRIX_GEMM",
           "SFU_VECTOR", "KV_APPEND", "MATRIX_QK", "SFU_SOFTMAX",
           "MATRIX_PV", "MATRIX_GEMM", "SFU_VECTOR", "SFU_RMSNORM",
           "MATRIX_GEMM", "MATRIX_GEMM", "SFU_ACTIVATION", "MATRIX_GEMM",
           "SFU_VECTOR"]
BUCKETS = {"MATRIX_GEMM":"dense_including_operand_io", "SFU_RMSNORM":"norm",
           "SFU_VECTOR":"vector", "SFU_ROPE":"rope", "KV_APPEND":"kv_copy",
           "MATRIX_QK":"attention_fused", "SFU_SOFTMAX":"attention_fused",
           "MATRIX_PV":"attention_fused", "SFU_ACTIVATION":"activation"}

def require(ok: bool, message: str) -> None:
    if not ok: raise ValueError(message)

def integer(value, label: str, positive: bool=False) -> int:
    require(type(value) is int and value >= int(positive), "invalid " + label)
    return value

def analyze(report: dict) -> dict:
    require(report["status"] == "PASS_MATRIX4096_REAL16_TWO_LAYER_EXACT_COMPARISON", "not a complete numeric comparison")
    require((report["tokens"],report["layers"],report["checked_fp32"],report["bit_differences"]) == (16,2,1409024,0), "wrong scope")
    old, new = report["baseline_512"], report["matrix4096"]
    for data, peak in ((old,512),(new,4096)):
        require(data["matrix_macs_per_cycle"] == peak and data["clock_target_hz"] == 800000000, "wrong hardware clock/peak")
        c=integer(data["cycles"],"cycles",True);u=integer(data["useful_macs"],"useful",True);e=integer(data["executed_macs"],"executed",True)
        require(u == 1498202112 and u <= e <= c*peak, "workload/capacity mismatch")
        require(math.isclose(data["useful_wall_mac_utilization"],u/(c*peak),rel_tol=1e-12), "misreported utilization")
        for key in ("ddr_read_bytes","ddr_write_ack_bytes"): integer(data[key],key)
    require(math.isclose(report["wall_cycle_speedup"],old["cycles"]/new["cycles"],rel_tol=1e-12), "misreported speedup")
    entries=report["per_command_durations"]
    require(len(entries)==42, "incomplete timing trace")
    sums={name:[0,0] for name in sorted(set(BUCKETS.values()))}
    for pc,item in enumerate(entries):
        require(type(item["pc"]) is int and item["pc"]==pc and item["opcode"]==OPCODES[pc%21], "PC/opcode mismatch")
        for i,key in enumerate(("baseline_cycles","matrix4096_cycles")):
            sums[BUCKETS[item["opcode"]]][i]+=integer(item[key],key)
    totals=[sum(x[i] for x in sums.values()) for i in range(2)]
    # The gate's final receipt occurs one clock after the last completion.
    require(totals==[old["cycles"]-1,new["cycles"]-1],"unaccounted or duplicated wall cycles")
    rows=[]
    for name,(a,b) in sums.items():
        rows.append({"category":name,"baseline_cycles":a,"matrix4096_cycles":b,
                     "speedup":a/b if b else None,"new_wall_fraction":b/new["cycles"]})
    dense=sums["dense_including_operand_io"][0]
    ideal_non_dense=old["cycles"]-dense
    # This is an explicitly hypothetical Amdahl bound, not an RTL measurement:
    # even all Dense time (INCLUDING I/O) is assumed to scale perfectly by 8.
    ideal=old["cycles"]/(ideal_non_dense+dense/8)
    weight_bytes=2*(2*1536*1536+2*1536*256+3*1536*8960)*4
    require(old["ddr_read_bytes"]>=weight_bytes and new["ddr_read_bytes"]>=weight_bytes,"missing frozen weight traffic")
    return {"schema":1,"status":"PASS_MEASURED_MATRIX4096_SCALING_ANALYSIS",
            "source":report["tested_source"],"baseline_source":report["baseline_source"],
            "wall_speedup":report["wall_cycle_speedup"],"capacity_ratio":8,
            "useful_utilization_ratio":new["useful_wall_mac_utilization"]/old["useful_wall_mac_utilization"],
            "per_category":rows,"receipt_tail_cycles":1,
            "hypothetical_all_dense_time_8x_speedup":ideal,
            "hypothetical_bound_assumptions":"All Dense cycles, including DDR/SRAM/control, divide by eight; every other measured category unchanged. Not a forecast or acceptance target.",
            "frozen_fp32_container_weight_bytes":weight_bytes,
            "new_weight_fraction_of_read_bytes":weight_bytes/new["ddr_read_bytes"],
            "read_traffic_ratio":new["ddr_read_bytes"]/old["ddr_read_bytes"],
            "write_traffic_ratio":new["ddr_write_ack_bytes"]/old["ddr_write_ack_bytes"],
            "scope":{"real16_two_synthetic_layers":True,"same_host_graph":True,
                     "physical_timing_signoff":False,"full_model_throughput":False,
                     "requires_original_full_comparison":True}}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--comparison",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    try:
        require(not a.output.exists() and not a.output.is_symlink(),"preserve previous output")
        raw=a.comparison.read_bytes();r=analyze(json.loads(raw));r["comparison_sha256"]=hashlib.sha256(raw).hexdigest()
        text=json.dumps(r,indent=2,allow_nan=False)+"\n"
        with a.output.open("x") as f:f.write(text)
        print(text,end="")
    except (ValueError,TypeError,KeyError,OSError,ZeroDivisionError) as e:raise SystemExit("SCALING_ANALYSIS_REJECTED: "+str(e))
