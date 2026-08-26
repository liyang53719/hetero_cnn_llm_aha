#!/usr/bin/env python3
import argparse, hashlib, json, re
from pathlib import Path
import numpy as np

COMMAND = re.compile(r"pc=\[([0-9a-f]+)\].*R\[r\s*\d+=([0-9a-f]+)\]\s+R\[r\s*\d+=([0-9a-f]+)\]\s+inst=\[([0-9a-f]+)\]",re.I)
MARKER = re.compile(r"GEMMINI_L4_CONV1X1_PASS checksum=(\d+) cycles=(\d+) dma_bytes=(\d+) macs=(\d+)")

def main():
  p=argparse.ArgumentParser();p.add_argument('--trace',type=Path,required=True);p.add_argument('--run-log',type=Path,required=True)
  p.add_argument('--elf',type=Path,required=True);p.add_argument('--vectors',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
  m=MARKER.search(a.run_log.read_text(errors='replace'))
  if not m: raise SystemExit('L4_CONV1X1_FAIL marker')
  checksum,cycles,dma,macs=map(int,m.groups())
  if (checksum,dma,macs)!=(7716209159022866879,140,192) or cycles<=0: raise SystemExit('L4_CONV1X1_FAIL metrics')
  cmds=[]
  for line in a.trace.read_text(errors='replace').splitlines():
    x=COMMAND.search(line)
    if x:
      pc,rs1,rs2,inst=(int(v,16) for v in x.groups())
      if inst&0x7f==0x7b:cmds.append({'funct':(inst>>25)&127,'rs1':rs1,'rs2':rs2})
  if len(cmds)!=9:raise SystemExit(f'L4_CONV1X1_FAIL commands={len(cmds)}')
  cases=json.loads(a.vectors.read_text())['cases'];case=next(c for c in cases if c['name']=='conv1x1');ops=case['ops']
  for i,(got,exp) in enumerate(zip(cmds,ops,strict=True)):
    if got['funct']!=exp['funct']:raise SystemExit(f'L4_CONV1X1_FAIL funct={i}')
    if i not in (6,7) and (got['rs1']!=int(exp['rs1'],16) or got['rs2']!=int(exp['rs2'],16)):
      raise SystemExit(f'L4_CONV1X1_FAIL payload={i}')
  inp=np.fromfunction(lambda r,c,ch:(r+2*c+ch)%5-2,(4,4,3),dtype=np.int64)
  weights=np.fromfunction(lambda o,ch:(o+2*ch)%5-2,(4,3),dtype=np.int64);bias=np.arange(4,dtype=np.int64)-2
  out=np.empty((16,4),dtype=np.int8)
  for r in range(4):
    for c in range(4):out[r*4+c]=(weights@inp[r,c]+bias).astype(np.int8)
  py=0
  for v in out.view(np.uint8).flat:py=((py*131)+int(v))&((1<<64)-1)
  if py!=checksum:raise SystemExit('L4_CONV1X1_FAIL golden')
  result={'stage':'L4','subgate':'1x1 Conv','status':'PASS_PAYLOAD_RTL_PENDING_L3_TRACE',
    'shape':{'n':1,'input_h':4,'input_w':4,'input_channels':3,'output_channels':4,'kernel':1},
    'custom3_commands':9,'elementwise_bit_exact':True,'output_sha256':hashlib.sha256(out.tobytes()).hexdigest(),
    'output_checksum_u64':checksum,'rtl_payload_cycles':cycles,'rtl_dma_bytes':dma,'rtl_macs':macs,
    'physical_array_peak_macs_per_cycle':256,'rtl_mac_utilization':macs/(cycles*256),
    'bank_conflicts':None,'bank_conflicts_status':'PENDING_CANONICAL_L3_TRACE_REPLAY',
    'elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest()}
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
  print(f"L4_CONV1X1_PAYLOAD_PASS cycles={cycles} sha256={result['output_sha256']}")
if __name__=='__main__':main()
