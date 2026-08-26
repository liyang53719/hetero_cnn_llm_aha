#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path
NORM=['e4df991f7d9ee2c5a61738c1ab393f54c293fc169fedea16b00a22df017bad0d','106c69ed91c925f9e4f5e36d0e8309e5963d2227a41094f338aed724ec4761b8','c73b44f0a58b9a4aef98d47b685dc4b18789c56116e32e28f419337064f095a2','03ccb1f09871e8c9462072a77930e7fe0b5b64cd250613a846f1325ad58bd55d','7ed75e752cb93f0d3f4d30438fda20f84c11ed83b4072a42d8b62843de4aa539','de9e539ab9bcc5dc94ac2098be709af3244d46f11074895c66adffee4dc46888','474cf914778fa559cf64afe35027b1f38ea175ea5806843a29d747a2319d4fcd','2219c77dd78520ca5560cfc8f93fdc6c570ec0f3348cb0811ad830b8b67f47a9']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',type=int,required=True);ap.add_argument('--norm2',type=Path,required=True);ap.add_argument('--gate',type=Path,required=True);ap.add_argument('--up',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 if sha(a.norm2)!=NORM[a.batch]:raise SystemExit('Q128_GATE_UP_NORM_HASH_FAIL')
 m={'batch_index':a.batch,'tokens':[a.batch*16,a.batch*16+15],'shape':[16,1536,8960],'steps_each':430080,'steps_total':860160,'norm2_sha256':NORM[a.batch],'gate_sha256':sha(a.gate),'up_sha256':sha(a.up)};a.output.write_text(json.dumps(m,indent=2)+'\n');print(f"L5_Q128_GATE_UP_MANIFEST_PASS batch={a.batch} gate_sha256={m['gate_sha256']}")
if __name__=='__main__':main()
