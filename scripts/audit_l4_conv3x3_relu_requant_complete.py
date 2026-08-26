#!/usr/bin/env python3
import argparse,json,re
from pathlib import Path
R=re.compile(r'L4_MATRIX_L3_TRACE_PASS case_id=3 cycles=(\d+) semantic_dma_bytes=(\d+) physical_dma_bytes=(\d+) descriptor_bytes=(\d+) reads=(\d+) writes=(\d+) conflicts=(\d+) rstall=(\d+) wstall=(\d+) promotions=(\d+)')
def main():
 p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--trace-log',type=Path,required=True);p.add_argument('--descriptor-log',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();q=json.loads(a.payload.read_text());m=R.search(a.trace_log.read_text(errors='replace'))
 if not m:raise SystemExit('L4_REQUANT_RELU_COMPLETE_FAIL trace')
 cy,se,ph,de,rd,wr,co,rs,ws,pr=map(int,m.groups())
 if(se,ph,de,rd,wr)!=(299,448,256,9,2)or cy<=0 or co<=0:raise SystemExit('L4_REQUANT_RELU_COMPLETE_FAIL metrics')
 if 'GEMMINI_DESCRIPTOR_V2_PIPELINE_PASS cycles=723 issued=85 rejects=4'not in a.descriptor_log.read_text(errors='replace'):raise SystemExit('L4_REQUANT_RELU_COMPLETE_FAIL descriptor')
 q.update({'status':'PASS','canonical_l3_trace_cycles':cy,'physical_dma_bytes':ph,'descriptor_bytes':de,'canonical_l3_reads':rd,'canonical_l3_writes':wr,'bank_conflicts':co,'bank_conflicts_status':'RTL_MEASURED','read_stalls':rs,'write_stalls':ws,'descriptor_promotions':pr});a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(q,indent=2)+'\n');print(f"L4_REQUANT_RELU_COMPLETE_PASS payload_cycles={q['rtl_payload_cycles']} l3_cycles={cy} conflicts={co}")
if __name__=='__main__':main()
