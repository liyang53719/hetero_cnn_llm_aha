"""Fresh metadata only, after complete acquisition. No inheritance of old source-spec hashes."""
from pathlib import Path
import hashlib,json,math,sys
HERE=Path(__file__).resolve().parent
DATA=None
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(data, output):
 global DATA
 DATA=Path(data).resolve()
 summary=json.loads((DATA/'SUMMARY.json').read_text());need(summary['status']=='ACQUIRED_70_ORIGINAL_TENSORS_ONLY','acquisition incomplete')
 plan=json.loads((DATA/'ACQUISITION_PLAN.json').read_text());need(len(plan['specs'])==70,'tensor inventory')
 rows=[]
 for t in plan['specs']:
  receipt=DATA/t['model']/(t['name']+'.receipt.json');r=json.loads(receipt.read_text());p=DATA/r['file']
  need(p.is_file() and p.stat().st_size==t['bytes'],'actual payload size')
  need(sha(p)==r['actual_sha256'],'post-write source SHA')
  need(all(r[k]==t[k] for k in ('model','name','dtype','shape','bytes','start','end','revision','url','shard_bytes')),'receipt/plan semantic drift')
  need(math.prod(t['shape'])*{'BF16':2,'F32':4}[t['dtype']]==t['bytes'],'storage size')
  if t['verification']=='EXACT_NAME_SHA256':need(r['actual_sha256']==t['expected_sha256'],'retained pin mismatch')
  if t['verification']=='PUBLISHED_RAW_SOURCE_SET_MEMBERSHIP':need(r['actual_sha256'] in t['allowed_sha256'],'source-set mismatch')
  rows.append({k:r[k] for k in ('model','name','revision','dtype','shape','bytes','file','actual_sha256','verification','start','end','url')})
 out=Path(output)
 with out.open('x') as f:json.dump({'status':'FRESH_RAW_SOURCE_BINDINGS_ONLY_NOT_LOGICAL_PROVIDER_OR_DUT_PASS','acquisition_plan_sha256':sha(DATA/'ACQUISITION_PLAN.json'),'data_root_contract':'consumer supplied; paths are relative to verified acquisition root','semantic_binding':'fixed official revision/header name and exact byte ranges; unordered historical digest set is only independent consistency','tensor_count':70,'bytes':sum(r['bytes'] for r in rows),'rows':rows},f,indent=2);f.write('\n')
 print(json.dumps({'status':'POST_WRITE_70_RAW_TENSOR_HASHES_VERIFIED_ONLY','manifest_sha256':sha(out),'bytes':sum(r['bytes'] for r in rows),'logical_provider_rebuilt':False,'reference_executed':False,'dut_executed':False}))
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.data,a.output)
