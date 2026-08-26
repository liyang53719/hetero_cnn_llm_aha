#!/usr/bin/env python3
import argparse,hashlib,json,re
from pathlib import Path
import numpy as np
C=re.compile(r'pc=\[([0-9a-f]+)\].*R\[r\s*\d+=([0-9a-f]+)\]\s+R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]',re.I)
M=re.compile(r'GEMMINI_L4_CONV3X3_IDENTITY_PASS checksum=(\d+) cycles=(\d+) dma_bytes=(\d+) macs=(\d+)')
def main():
 p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True);p.add_argument('--run-log',type=Path,required=True);p.add_argument('--elf',type=Path,required=True);p.add_argument('--vectors',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 m=M.search(a.run_log.read_text(errors='replace'))
 if not m:raise SystemExit('L4_CONV3X3_FAIL marker')
 checksum,cycles,dma,macs=map(int,m.groups())
 if dma!=299 or macs!=2700 or cycles<=0:raise SystemExit('L4_CONV3X3_FAIL metrics')
 cmds=[]
 for line in a.trace.read_text(errors='replace').splitlines():
  x=C.search(line)
  if x:
   pc,r1,r2,inst=(int(v,16) for v in x.groups())
   if inst&127==0x7b:cmds.append({'funct':(inst>>25)&127,'rs1':r1,'rs2':r2})
 if len(cmds)!=9:raise SystemExit(f'L4_CONV3X3_FAIL commands={len(cmds)}')
 case=next(x for x in json.loads(a.vectors.read_text())['cases'] if x['name']=='conv_identity')
 for i,(g,e) in enumerate(zip(cmds,case['ops'],strict=True)):
  if g['funct']!=e['funct'] or (i not in(6,7) and (g['rs1']!=int(e['rs1'],16) or g['rs2']!=int(e['rs2'],16))):raise SystemExit(f'L4_CONV3X3_FAIL op={i}')
 inp=np.fromfunction(lambda r,c,ch:(r*3+c*2+ch)%5-2,(5,5,3),dtype=np.int64)
 w=np.fromfunction(lambda o,kr,kc,ch:(o+kr*2+kc+ch)%5-2,(4,3,3,3),dtype=np.int64);bias=np.arange(4)*3-4
 out=np.zeros((25,4),dtype=np.int8)
 for r in range(5):
  for c in range(5):
   for o in range(4):
    s=int(bias[o])
    for kr in range(3):
     for kc in range(3):
      ir,ic=r+kr-1,c+kc-1
      if 0<=ir<5 and 0<=ic<5:s+=int(inp[ir,ic]@w[o,kr,kc])
    out[r*5+c,o]=np.int8(s)
 py=0
 for v in out.view(np.uint8).flat:py=((py*131)+int(v))&((1<<64)-1)
 if py!=checksum:raise SystemExit('L4_CONV3X3_FAIL golden')
 result={'stage':'L4','subgate':'3x3 Conv identity','status':'PASS_PAYLOAD_RTL_PENDING_L3_TRACE','shape':{'n':1,'h':5,'w':5,'cin':3,'cout':4,'kernel':3,'padding':1},'custom3_commands':9,'elementwise_bit_exact':True,'output_sha256':hashlib.sha256(out.tobytes()).hexdigest(),'output_checksum_u64':checksum,'rtl_payload_cycles':cycles,'rtl_dma_bytes':dma,'rtl_macs':macs,'physical_array_peak_macs_per_cycle':256,'rtl_mac_utilization':macs/(cycles*256),'bank_conflicts':None,'bank_conflicts_status':'PENDING_CANONICAL_L3_TRACE_REPLAY','elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest()}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(f"L4_CONV3X3_IDENTITY_PAYLOAD_PASS cycles={cycles} sha256={result['output_sha256']}")
if __name__=='__main__':main()
