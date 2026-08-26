#!/usr/bin/env python3
import argparse,json,re
from pathlib import Path
TR=re.compile(r'L4_MATRIX_L3_TRACE_PASS case_id=(\d+) cycles=(\d+) semantic_dma_bytes=(\d+) physical_dma_bytes=(\d+) descriptor_bytes=(\d+) reads=(\d+) writes=(\d+) conflicts=(\d+) rstall=(\d+) wstall=(\d+) promotions=(\d+)')
def parse(path,case):
 m=TR.search(path.read_text(errors='replace'))
 if not m or int(m.group(1))!=case:raise SystemExit(f'L4_POOL_RESIDUAL_FAIL trace{case}')
 return list(map(int,m.groups()[1:]))
def main():
 p=argparse.ArgumentParser();p.add_argument('--rtl',type=Path,required=True);p.add_argument('--canonical-log',type=Path,required=True);p.add_argument('--pool-log',type=Path,required=True);p.add_argument('--residual-log',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();base=json.loads(a.rtl.read_text())
 if 'dedicated=10000' not in a.canonical_log.read_text(errors='replace'):raise SystemExit('L4_POOL_RESIDUAL_FAIL canonical')
 pool=parse(a.pool_log,4);res=parse(a.residual_log,5)
 if pool[:6] != [6,80,128,64,2,1] or res[:6] != [7,192,192,64,3,1] or pool[6]<=0 or res[6]<=0:raise SystemExit('L4_POOL_RESIDUAL_FAIL metrics')
 base.update({'status':'PASS','canonical_endpoint_operations':10000,'canonical_matrix_completions':20000,
  'canonical_direct_policy':'dedicated output zero-filled to full 512-bit beat for Gemmini ExtMem read response',
  'pool_trace':{'cycles':pool[0],'semantic_bytes':pool[1],'physical_bytes':pool[2],'descriptor_bytes':pool[3],'reads':pool[4],'writes':pool[5],'conflicts':pool[6],'read_stalls':pool[7],'write_stalls':pool[8]},
  'residual_trace':{'cycles':res[0],'semantic_bytes':res[1],'physical_bytes':res[2],'descriptor_bytes':res[3],'reads':res[4],'writes':res[5],'conflicts':res[6],'read_stalls':res[7],'write_stalls':res[8]},'canonical_endpoint_status':'PASS'})
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(base,indent=2)+'\n');print('L4_POOL_RESIDUAL_COMPLETE_PASS canonical=10000 pool_cycles=6 residual_cycles=7')
if __name__=='__main__':main()
