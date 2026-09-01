#!/usr/bin/env python3
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--chains',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);m=[json.loads(x)for x in a.manifest.read_text().splitlines()];cmd=[m[i]for i in (2,5,8)];chains={x['root']:x for x in map(json.loads,a.chains.read_text().splitlines())};addresses=[]
for c in cmd:
 for role in ('src0','src1','dst'):
  root=c['roots'][role];base=next(x for x in chains[root]['records']if x['record_type']=='tensor_base');addresses.append(base['address'])
(a.out/'bias_commands.memh').write_text(''.join(x['word'].removeprefix('0x')+'\n'for x in cmd));(a.out/'bias_addresses.memh').write_text(''.join(f'{x:014x}\n'for x in addresses));print(json.dumps({'operations':[x['operation']for x in cmd],'addresses':addresses},sort_keys=True))
