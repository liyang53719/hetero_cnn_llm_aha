"""Link original generated RTL model and Python-reference bench; never execute it."""
from pathlib import Path
import subprocess,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
R=Path(__file__).resolve().parent
O=ROOT/'round_20261110T0933/host/obj_hier'
B=ROOT/'round_20261110T0933/python_host_binding'
H=ROOT/'round_20261110T0833/host_real_interface'
V=ROOT/'runtime_recovery_0133/verilator-runtime/verilator-package/usr/share/verilator/include'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if sha(B/'host_python_reference.cpp')!='ac0065e5f50250a041cc2c0893192b6b395d6f2f0cff0a782be3ba330ed14ba5':raise ValueError('bench pin changed')
 libs=[O/'libVHostBlockTopV4.a',O/'libverilated.a']
 for p in libs:
  if not p.is_file():raise ValueError('complete archive unavailable: '+str(p))
 cmd=['g++','-std=c++17','-O1','-pthread','-DOWNER_MATRIX_MACS=4096','-DOWNER_PIPELINED=1','-DOWNER_WEIGHT_READ_BEATS=16','-DOWNER_BF16_WEIGHTS=0']
 for p in [O,B,H,V,V/'vltstd']:cmd+=['-I',str(p)]
 cmd += [str(B/'host_python_reference.cpp'),'-Wl,--start-group',*[str(p) for p in libs],'-Wl,--end-group','-o',str(R/'real_host_python_reference.local')]
 (R/'link_command.json').write_text(json.dumps(cmd,indent=2))
 with (R/'link.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 result=dict(exit=r.returncode,scope='LINK_ONLY_NO_EXECUTION',libraries={str(p):sha(p) for p in libs})
 if r.returncode==0:result['executable_sha256']=sha(R/'real_host_python_reference.local')
 (R/'link_result.json').write_text(json.dumps(result,indent=2));return r.returncode
if __name__=='__main__':sys.exit(main())
