#!/usr/bin/env python3
import argparse,json,re
from pathlib import Path
R=re.compile(r'L4_MATRIX_L3_TRACE_PASS case_id=1 cycles=(\d+) semantic_dma_bytes=(\d+) physical_dma_bytes=(\d+) descriptor_bytes=(\d+) reads=(\d+) writes=(\d+) conflicts=(\d+) rstall=(\d+) wstall=(\d+) promotions=(\d+)')
def main():
 p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--trace-log',type=Path,required=True);p.add_argument('--descriptor-log',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 payload=json.loads(a.payload.read_text());m=R.search(a.trace_log.read_text(errors='replace'))
 if not m:raise SystemExit('L4_CONV1X1_COMPLETE_FAIL trace')
 cycles,semantic,physical,desc,reads,writes,conflicts,rs,ws,prom=map(int,m.groups())
 if (semantic,physical,desc,reads,writes)!=(140,256,256,7,1) or cycles<=0 or conflicts<=0:raise SystemExit('L4_CONV1X1_COMPLETE_FAIL metrics')
 if 'GEMMINI_DESCRIPTOR_V2_PIPELINE_PASS cycles=723 issued=85 rejects=4' not in a.descriptor_log.read_text(errors='replace'):raise SystemExit('L4_CONV1X1_COMPLETE_FAIL descriptor')
 if payload['status']!='PASS_PAYLOAD_RTL_PENDING_L3_TRACE':raise SystemExit('L4_CONV1X1_COMPLETE_FAIL payload')
 result=dict(payload);result.update({'status':'PASS','canonical_l3_trace_cycles':cycles,'physical_dma_bytes':physical,
  'descriptor_bytes':desc,'canonical_l3_reads':reads,'canonical_l3_writes':writes,'bank_conflicts':conflicts,
  'bank_conflicts_status':'RTL_MEASURED','read_stalls':rs,'write_stalls':ws,'descriptor_promotions':prom})
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(f"L4_CONV1X1_COMPLETE_PASS payload_cycles={payload['rtl_payload_cycles']} l3_cycles={cycles} conflicts={conflicts}")
if __name__=='__main__':main()
