#!/usr/bin/env python3
"""Validate original local reference routes; emits only occupancy, never IDs."""
import argparse,collections,hashlib,json,pathlib,struct
p=argparse.ArgumentParser();p.add_argument('--p3-reference',type=pathlib.Path,required=True);p.add_argument('--p4-reference',type=pathlib.Path,required=True);a=p.parse_args()
expected=json.loads((pathlib.Path(__file__).resolve().parent/'OCCUPANCY_REFERENCE_SUMMARY.json').read_text())
for record,d in zip(expected,[a.p3_reference,a.p4_reference]):
 result=(d/'RESULT.json').read_bytes();assert hashlib.sha256(result).hexdigest()==record['source_result_sha256']
 r=json.loads(result)['tensor_records']['stage.mlp.gate.0.2'];b=(d/r['file']).read_bytes()
 assert len(b)==8192 and r['shape']==[128,8] and r['dtype']=='torch.int64'
 assert hashlib.sha256(b).hexdigest()==record['ids_sha256']==r['sha256']
 ids=struct.unpack('<1024q',b);assert all(0<=v<256 for v in ids)
 assert all(len(set(ids[i:i+8]))==8 for i in range(0,1024,8))
 c=collections.Counter(ids);h=collections.Counter(c.values())
 assert {str(k):v for k,v in h.items()}==record['occupancy_histogram']
 print(json.dumps({'profile':record['profile'],'verified_reference_occupancy_only':True,'active_experts':len(c),'routes':len(ids),'not_dut_routing':True}))
