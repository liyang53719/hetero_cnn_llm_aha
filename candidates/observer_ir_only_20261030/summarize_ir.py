"""Exact metadata projection. Never uploads logs, IR, paths, errors, or data payloads."""
import argparse,json,math,pathlib,re
from check_ir import NAMES
STAGES=('jdk','compile_tools','jars','verilator_bytes','runtime_identity','compile155','original_ir')
FLAGS=('numerical_pass','canonical_pass','target_host_qualified','sv_generated','generated_abi_qualification','physical_resource_or_qor_qualification','block_numerical_pass')
COMPLETE='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY'
def need(x):
 if not x:raise ValueError('bounded summary schema')
def read(path):
 need(path.is_file() and not path.is_symlink() and path.stat().st_size<=65536)
 x=json.loads(path.read_text());need(type(x) is dict);return x
def number(x,nullable=False):
 need((x is None and nullable) or (type(x) in (int,float) and math.isfinite(x) and 0<=x<=2**53));return x
def admission_projection(value):
 need(type(value) is dict)
 need(value.get('scope')=='REPO_WORK_AGGREGATE')
 status=value.get('status');reason=value.get('reason');complete=value.get('census_complete');called=value.get('execute_called')
 need(type(complete) is bool and type(called) is bool)
 need((status=='ADMITTED' and reason=='NONE' and complete and called)
      or (status=='REJECTED' and reason in ('ENTRY_CAP','ROOT_INVALID','NONREGULAR_ENTRY','DISK_RESERVE','TREE_CAP','FILE_CAP','CENSUS_UNREADABLE','CENSUS_REJECTED') and not complete and not called))
 out=dict(scope='REPO_WORK_AGGREGATE',status=status,reason=reason,census_complete=complete,execute_called=called)
 for key in ('entry_cap','reserved_entries','entries_observed','bytes_observed','largest_file_bytes'):
  v=number(value.get(key));need(type(v) is int);out[key]=v
 need(out['entry_cap']==100000 and out['reserved_entries']==8)
 if status=='ADMITTED':need(out['entries_observed']+out['reserved_entries']<=out['entry_cap'])
 return out

def project(raw,identity):
 need(type(raw) is dict and type(identity) is dict)
 out={'schema':'OBSERVER_IR_SAFE_SUMMARY_V1','scope':'ORIGINAL_HIGH_AND_OFFICIAL_LOW_ONLY',**{k:False for k in FLAGS}}
 for k in ('source_commit','launch_commit','launch_manifest_blob_sha'):
  need(type(identity.get(k)) is str and re.fullmatch('[0-9a-f]{40}',identity[k]));out[k]=identity[k]
 need(type(identity.get('run_id')) is int and identity['run_id']>0);out['run_id']=identity['run_id']
 status=raw.get('status','OBSERVATION_UNAVAILABLE');need(status in (COMPLETE,'FAILED_OR_INCOMPLETE','OBSERVATION_UNAVAILABLE'));out['status']=status
 need(all(raw.get(k,False) is False for k in FLAGS))
 stages=raw.get('stages',[]);need(type(stages) is list and len(stages)<=7);out['stages']=[]
 for i,row in enumerate(stages):
  need(type(row) is dict and row.get('name')==STAGES[i] and type(row.get('complete')) is bool)
  exitcode=row.get('native_exit');need(exitcode is None or type(exitcode) is int and -255<=exitcode<=255)
  out['stages'].append(dict(name=STAGES[i],native_exit=exitcode,complete=row['complete'],error_count=number(row.get('error_count')),elapsed_seconds=number(row.get('elapsed_seconds'),True),observed_peak_rss=number(row.get('observed_peak_rss'),True)))
  if 'admission' in row:
   admission=admission_projection(row['admission'])
   if admission['status']=='REJECTED':need(not row['complete'] and exitcode is None and row['error_count']>=1)
   out['stages'][-1]['admission']=admission
 if status==COMPLETE:
  need(len(stages)==7 and all(r['complete'] and r['native_exit']==0 and r['error_count']==0 for r in stages))
  need(all(r.get('admission',{}).get('status','ADMITTED')=='ADMITTED' for r in out['stages']))
  artifacts=raw.get('artifacts');need(type(artifacts) is dict and set(artifacts)==set(NAMES));out['artifacts']={}
  for name in NAMES:
   row=artifacts[name];need(type(row) is dict and type(row.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}',row['sha256']))
   size=number(row.get('bytes'));need(type(size) is int and 0<size<=384*1024**2);out['artifacts'][name]={'bytes':size,'sha256':row['sha256']}
  ports=raw.get('measured_top_port_counts');need(type(ports) is dict and set(ports)=={'high','low'} and ports['low']==122)
  out['measured_top_port_counts']={k:number(ports[k]) for k in ('high','low')}
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--work',type=pathlib.Path,required=True);p.add_argument('--identity',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 source=a.work/'IR_SUMMARY.json'
 raw=read(source) if source.exists() else {}
 data=json.dumps(project(raw,read(a.identity)),indent=2)+'\n';need(len(data.encode())<=65536)
 with a.output.open('x') as f:f.write(data)
if __name__=='__main__':main()
