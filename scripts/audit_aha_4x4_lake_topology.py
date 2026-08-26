#!/usr/bin/env python3
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];AHA=ROOT/'work/upstream/aha';G=AHA/'garnet'
garnet=(G/'garnet.py').read_text();util=(G/'cgra/util_onyx.py').read_text()
checks={
 'width_drives_glb': 'num_glb_tiles=args.width // 2' in garnet,
 'ratio_tuple': 'args.mem_ratio = (1, args.mem_ratio)' in util,
 'ratio_formula': 'mem_tile_ratio = tile_max - mem_ratio[0]' in util,
 'column_layout': 'use_mem_core = (x - x_min) % tile_max >= mem_tile_ratio' in util,
}
if not all(checks.values()):raise SystemExit('AHA_4X4_TOPOLOGY_AUDIT_FAIL source contract changed')
def topology(width,height,ratio):
 mem_cols=sum(1 for x in range(width) if x%ratio>=ratio-1);mem=mem_cols*height
 return {'mem_ratio':ratio,'memory_columns':mem_cols,'lake_mem_tiles':mem,'pe_tiles':width*height-mem}
target=[topology(4,4,r) for r in range(1,9)];baseline=topology(4,16,4)
feasible=[x for x in target if x['lake_mem_tiles']==16 and x['pe_tiles']>0]
result={'status':'BLOCKED_DEPENDENCY','reason':'pinned column-layout generator cannot produce width=4 height=4 with 16 Lake MemCore tiles and any PE tile',
 'aha_commit':subprocess.check_output(['git','-C',str(AHA),'rev-parse','HEAD'],text=True).strip(),
 'garnet_commit':subprocess.check_output(['git','-C',str(G),'rev-parse','HEAD'],text=True).strip(),
 'image_digest':'sha256:a8784f2cfe96609a7e4403c29f6a82bd00c882c8564ef747541f78be75fa2b2b',
 'source_sha256':{'garnet.py':hashlib.sha256(garnet.encode()).hexdigest(),'cgra/util_onyx.py':hashlib.sha256(util.encode()).hexdigest()},
 'baseline_4x16_mem_ratio4':baseline,'target_4x4_enumeration':target,'feasible_with_16_lake_and_compute':feasible,
 'fixed_policy':'do not substitute 4x16 baseline or all-memory 4x4 for production 4x4 compute SFU'}
out=ROOT/'reports/execution/aha_4x4_lake_topology_result.json';out.write_text(json.dumps(result,indent=2)+'\n')
print('AHA_4X4_LAKE_TOPOLOGY_BLOCKED_DEPENDENCY baseline_mem=16 target_ratio4_mem=4 target_ratio1_pe=0')
