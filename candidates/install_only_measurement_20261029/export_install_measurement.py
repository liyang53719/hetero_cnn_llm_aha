#!/usr/bin/env python3
"""Export bounded, path-free historical INSTALL_ONLY measurements, never payloads."""
import argparse,hashlib,json,math
from pathlib import Path
EXPECTED='5d576a08735254a983db7ab31b77d686d2d1456dbdaa4fdf2670f046a5789179'
BINDING='619bf929c237329fc4f87817624a07816a59c2ed3918766da1342df538967332'
NAMES=['cache','qwen2','qwen35_08b','qwen35_35b']
FIELDS=['elapsed_seconds','observed_peak_rss','observed_cpu_seconds','supervisor_cpu_seconds','peak_tree_bytes','disk_census_count','disk_census_total_seconds','disk_census_max_seconds','process_sample_max_gap_seconds']
def need(x,m):
 if not x:raise ValueError(m)
def export(path):
 raw=path.read_bytes();need(len(raw)<=128*1024 and hashlib.sha256(raw).hexdigest()==EXPECTED,'exact historical input pin');r=json.loads(raw)
 need(r['binding_sha256']==BINDING and r['later_dut_numeric']=='NOT_RUN','scope')
 need([s['stage'] for s in r['stages']]==NAMES,'four exact install stages');out=[]
 for s in r['stages']:
  need(s['native_exit']==0 and s['errors']==[],'terminal process result')
  need(s['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and s['reader_join_barrier']['complete'] is True,'owned cleanup')
  p={'stage':s['stage'],'native_exit':0,'errors_count':0,'cleanup_complete':True,'reader_join_complete':True}
  for k in FIELDS:
   v=s[k];need(type(v) in (int,float) and math.isfinite(v) and 0<=v<10**14,'bounded numeric metric');p[k]=v
  h=s['receipt_sha256'];need(len(h)==64 and all(c in '0123456789abcdef' for c in h),'receipt hash');p['receipt_sha256']=h;out.append(p)
 total=r['actual_final_install_tree']['bytes'];free=r['disk_free_after'];need(type(total)==int and type(free)==int and 0<total<2**40 and 0<free<2**40,'size fields')
 return {'schema':'HISTORICAL_INSTALL_ONLY_MEASUREMENT_V1','status':'PASS_NATIVE_INSTALL_ONLY_NOT_REFERENCE_OR_DUT','raw_measurement_sha256':EXPECTED,'executed_binding_sha256':BINDING,'executed_runner_sha256':'810a3edb4a61a6101abc8da5c94473e5ed1f6777776815183870bae3aef087cf','stages':out,'final_unique_inode_logical_bytes':total,'observed_free_disk_after_bytes':free,'scope':{'reference_executed':False,'dut_executed':False,'eda_executed':False,'weights_downloaded':False,'peak_is_mathematical_upper_bound':False,'current_free_disk_claim':False,'sampling_gap_is_reported':True,'archive_or_runtime_payload_included':False},'limitations':['Observed maxima are samples, not continuous peak upper bounds.','Three shared runtime roots do not prove the five per-profile install strategy fits.','Historical free disk is not current admission.','The exporter reproduces this summary from the pinned retained measurement; it is not an installer or a fresh-run qualification.']}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=export(a.input);body=json.dumps(r,indent=2)+'\n';need(len(body.encode())<16*1024,'bounded summary');a.output.open('x').write(body)
