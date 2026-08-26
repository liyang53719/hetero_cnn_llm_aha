#!/usr/bin/env python3
"""Audit no-bias WS and 1x1 Conv official/raw traces against v2 vectors."""
from __future__ import annotations
import argparse,json,re,subprocess
from pathlib import Path

PATTERN=re.compile(r"R\[r\s*\d+=([0-9a-f]+)\]\s+R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]",re.I)
ROOT=Path(__file__).resolve().parents[1]
def parse(path:Path):
    out=[]
    for line in path.read_text(errors="replace").splitlines():
        m=PATTERN.search(line)
        if m:
            rs1,rs2,inst=(int(x,16) for x in m.groups())
            if inst&127==0x7b:out.append(((inst>>25)&127,rs1,rs2))
    return out
def expected(name:str):
    data=json.loads((ROOT/"tests/vectors/gemmini_descriptor_v2_programs.json").read_text())
    case=next(x for x in data["cases"] if x["name"]==name)
    return [(x["funct"],int(x["rs1"],16),int(x["rs2"],16)) for x in case["ops"]]
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--result-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    ws=parse(a.result_root/"no_bias_ws.trace");conv=parse(a.result_root/"conv1x1.trace")
    if len(ws)!=22 or len(conv)!=18:raise SystemExit(f"commit count mismatch ws={len(ws)} conv={len(conv)}")
    ws_off,ws_raw=ws[:11],ws[11:];cv_off,cv_raw=conv[:9],conv[9:]
    for i,(left,right) in enumerate(zip(ws_off,ws_raw,strict=True)):
        fields=[j for j,(x,y) in enumerate(zip(left,right)) if x!=y]
        if fields and not(i==7 and fields==[2]):raise SystemExit(f"WS official/raw mismatch {i} {fields}")
    for i,(left,right) in enumerate(zip(cv_off,cv_raw,strict=True)):
        fields=[j for j,(x,y) in enumerate(zip(left,right)) if x!=y]
        if fields and not(i==6 and fields==[2]):raise SystemExit(f"Conv official/raw mismatch {i} {fields}")
    ws_exp=expected("loop_ws_no_bias");cv_exp=expected("conv1x1")
    for i in [0,1,2,3,4,5,8,9,10]:
        if ws_raw[i]!=ws_exp[i]:raise SystemExit(f"WS v2 mismatch {i}")
    if ws_raw[7][0]!=ws_exp[7][0] or ws_raw[7][1]!=0:raise SystemExit("WS no-bias D encoding mismatch")
    for i in [0,1,2,3,4,5,8]:
        if cv_raw[i]!=cv_exp[i]:raise SystemExit(f"Conv1x1 v2 geometry mismatch {i}")
    logs=(a.result_root/"no_bias_ws.log").read_text()+(a.result_root/"conv1x1.log").read_text()
    if "GEMMINI_L2_NO_BIAS_WS_PASS" not in logs or "GEMMINI_L2_CONV1X1_PASS" not in logs:raise SystemExit("numerical marker missing")
    upstream=ROOT/"work/upstream/chipyard_gemmini"
    clean=subprocess.run(["git","-C",str(upstream),"status","--porcelain"],capture_output=True,text=True,check=True).stdout==""
    result={"status":"PASS","no_bias_ws_custom3_per_path":11,"conv1x1_custom3_per_path":9,
            "official_raw_equal_except_output_destination":True,"v2_non_address_payload_match":True,
            "numerical_markers":True,"upstream_clean":clean}
    if not clean:raise SystemExit("upstream worktree dirty")
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
