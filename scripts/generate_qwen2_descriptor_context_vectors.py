#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--chains',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 commands=[json.loads(x)for x in a.manifest.read_text().splitlines()][:2];chains={x['root']:x for x in map(json.loads,a.chains.read_text().splitlines())};roots=[]
 for c in commands:roots += [c['roots'][x]for x in ('src0','src1','dst')]
 addr=[];dtype=[];shape=[]
 for r in roots:
  records=chains[r]['records'];base=next(x for x in records if x['record_type']=='tensor_base');sh=next(x for x in records if x['record_type']=='shape4')
  addr.append(base['address']);dtype.append({'BF16':5,'FP32':7}[base['dtype_symbol']]);shape.append(sum(int(v)<<(18*i)for i,v in enumerate(sh['dims'])))
 (a.out/'commands.memh').write_text(''.join(x['word'].removeprefix('0x')+'\n'for x in commands));(a.out/'addresses.memh').write_text(''.join(f'{x:014x}\n'for x in addr));(a.out/'dtypes.memh').write_text(''.join(f'{x:x}\n'for x in dtype));(a.out/'shapes.memh').write_text(''.join(f'{x:018x}\n'for x in shape));print(json.dumps({'roots':roots,'addresses':addr,'dtypes':dtype},sort_keys=True))
if __name__=='__main__':main()
