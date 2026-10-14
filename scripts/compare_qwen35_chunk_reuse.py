"""Post-execution comparison of two sealed actual Chunk policies; no model execution."""
import argparse,hashlib,json
from pathlib import Path
sha=lambda b:hashlib.sha256(b).hexdigest()
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tokens',type=int,choices=(16,128),required=True)
parser.add_argument('--baseline',type=Path,required=True)
parser.add_argument('--candidate',type=Path,required=True)
args=parser.parse_args();m=args.tokens;old=args.baseline;new=args.candidate
if not __debug__:raise RuntimeError('comparison requires enabled assertions')
a=json.loads((old/'summary.json').read_bytes());b=json.loads((new/'summary.json').read_bytes())
assert b['tokens']==a['tokens']==m
assert b['status']==a['status'] and b['sources_unchanged'] and b['native_artifacts_unchanged']
assert b['source_sha256']==b['source_sha256_after']
for p,h in b['source_sha256'].items():assert sha(Path(p).read_bytes())==h,p
assert b['input_identity']==a['input_identity']
assert [x['stage'] for x in a['observations']]==[x['stage'] for x in b['observations']]
for report in (a,b):
 for rec in report['native_artifact_records']+[x['output'] for x in report['observations']]:
  raw=Path(rec['path']).read_bytes();assert len(raw)==rec['bytes'] and sha(raw)==rec['sha256'],rec['path']
assert {p.name for p in old.glob('*.actual.*')}=={p.name for p in new.glob('*.actual.*')}
assert len(b['execution']['terminals'])==13 and all(x['status'] is None for x in b['execution']['terminals'])
assert b['execution']['matrix_service']==a['execution']['matrix_service']
assert b['execution']['scalar_operations']==a['execution']['scalar_operations']
raws=[]
for p in sorted(old.glob('*.actual.*')):
 q=new/p.name;assert p.read_bytes()==q.read_bytes(),p.name
 raws.append(dict(name=p.name,bytes=p.stat().st_size,sha256=sha(q.read_bytes())))
x=a['execution']['chunk_staging'];y=b['execution']['chunk_staging']
for key in ('vector_issue_counts','vector_lane_operations','scalar_calls','decay_internal_calls','exp','vector_exception_flag_counts','host_call_counts'):
 assert x['owner'][key]==y['owner'][key],key
assert y['owner']['transpose_and_matmul_share_one_tile'] and y['owner']['shared_scratch_high_water_bytes']==1024
assert not y['owner']['shared_scratch_leased']
for key in ('write_bytes','source_read_bytes'):assert x['counts'][key]==y['counts'][key]
assert x['counts']['read_bytes']-y['counts']['read_bytes']==452984832*((m+63)//64)
assert y['counts']['ticks']==y['transport_prediction']['driver_ticks_no_stall']
assert not b['execution']['history_published'] and not y['generation_advanced']
r=dict(comparator_sha256=sha(Path(__file__).read_bytes()),tokens=m,status='PASS_SAME_PRODUCER_ROW4_REUSE_SOFTWARE_ONLY',old_summary_sha256=sha((old/'summary.json').read_bytes()),new_summary_sha256=sha((new/'summary.json').read_bytes()),outputs_byteexact=raws,old_counts=x['counts'],new_counts=y['counts'],matrix_unchanged=True,hardware_cycles=None,full_block=False,rtl_executed=False)
(new/'reuse_comparison.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
