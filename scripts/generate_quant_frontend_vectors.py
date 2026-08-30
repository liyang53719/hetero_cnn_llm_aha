#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from heteronpu.quant_operand_frontend import StorageFormat,_random_payload,decode_block
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--blocks-per-format',type=int,default=32);p.add_argument('--seed',type=int,default=6801);a=p.parse_args();rng=random.Random(a.seed);a.output.parent.mkdir(parents=True,exist_ok=True)
with a.output.open('w') as out:
 for fmt in StorageFormat:
  for block_id in range(a.blocks_per_format):
   payload,count=_random_payload(fmt,rng)
   for beat in decode_block(fmt,payload,fp16_element_count=count):
    out.write(json.dumps({'format':fmt.name,'block_id':block_id,'group':beat.group_index,'payload_hex':payload.hex(),'fp16_element_count':count,'offset':beat.offset,'valid_count':beat.valid_count,'integer_quants':beat.integer_quants,'fp16_bits':beat.fp16_bits,'block_scale_fp16':beat.block_scale_fp16,'subscale_s8':beat.subscale_s8,'last':beat.last},separators=(',',':'))+'\n')
