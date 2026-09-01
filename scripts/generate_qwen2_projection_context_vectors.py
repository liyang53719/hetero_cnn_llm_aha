#!/usr/bin/env python3
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--chains',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
m=[json.loads(x)for x in a.manifest.read_text().splitlines()];cs=[m[i]for i in (1,4,7)];chains={x['root']:x for x in map(json.loads,a.chains.read_text().splitlines())};addresses=[];shapes=[];cols=[]
for command in cs:
 roots=[command['roots'][r]for r in ('src0','src1','dst')]
 for root in roots:
  rec=chains[root]['records'];base=next(x for x in rec if x['record_type']=='tensor_base');shape=next(x for x in rec if x['record_type']=='shape4');addresses.append(base['address']);shapes.append(sum(int(v)<<(18*i)for i,v in enumerate(shape['dims'])))
 cols.append(chains[roots[2]]['records'][1]['dims'][1])
(a.out/'projection_commands.memh').write_text(''.join(x['word'].removeprefix('0x')+'\n'for x in cs));(a.out/'projection_addresses.memh').write_text(''.join(f'{x:014x}\n'for x in addresses));(a.out/'projection_shapes.memh').write_text(''.join(f'{x:018x}\n'for x in shapes));(a.out/'projection_columns.memh').write_text(''.join(f'{x:05x}\n'for x in cols));print(json.dumps({'operations':[x['operation']for x in cs],'columns':cols,'strides':[x*2 for x in cols],'tiles':[x//32 for x in cols]},sort_keys=True))
