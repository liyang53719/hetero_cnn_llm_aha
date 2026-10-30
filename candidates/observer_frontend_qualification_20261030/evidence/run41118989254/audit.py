"""Read two exact saved frontend metadata files; never accept new SV or numerics.
No network, archive extraction, invocation of compiler/Make or source modification.
"""
import argparse,hashlib,importlib.util,json,pathlib,sys
D=pathlib.Path(__file__).resolve().parent
import os
# Point to an exact source checkout; checker still verifies the entire 644-pin closure.
ROOT=pathlib.Path(os.environ.get('HETERO_AUDIT_REPO_ROOT',str(D.parents[3]))).resolve()
Q=ROOT/'candidates/observer_frontend_qualification_20261030'
M=ROOT/'candidates/ci_frontend_materialization_r2_20261029'
IDENTITY=dict(run_id=41118989254,artifact_name='hetero-observer-frontend-summary-41118989254',source_commit='a06b51416090fce2ad3d04336c82a5b7a2d00b97',launch_commit='50f2e807f28f11e80ffc418461da94fe1ba3c80b',launch_manifest_path='ci_launch/observer_fixed4096_frontend_make_driver_20261030_once.json',launch_manifest_blob_sha='47edaa7b528863d6c213c7fac7a754982bc4cbe2')
PINS_SHA='99adde3413b505b67ee68939e992f6e11eb50274662a1042417ce8121b5797c8'
MODULES_SHA='0d80da62c042b5da4f2879525d4660df957579a169295a5844deb0d953f2067a'
SCANNER_SHA='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
OLD_NORMALIZED='6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5'
OBSERVERS={'HostBlockCommandsV4','FfnTileSiluBridge','FfnResidentCoordinator','QwenOwnerKernel','UnifiedMoeRouterNumericalOwnerV2','UnifiedMoeRouterPipelineBindingV2','UnifiedMoeRuntimeExpertLoopV4','HostBlockTopV4'}
def need(x,m):
 if not x:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def unique(rows):
 d={}
 for k,v in rows:need(k not in d,'duplicate key');d[k]=v
 return d
def read(p,cap):
 need(p.is_file()and not any(x.is_symlink()for x in (p,*p.parents)),'regular non-symlink input')
 need(0<p.stat().st_size<=cap,'input cap');b=p.read_bytes();need(len(b)<=cap,'read cap')
 x=json.loads(b,object_pairs_hook=unique);need(type(x)is dict,'document object');return x,b
def module_diff(old,new):
 a={r['module']:r for r in old};b={r['module']:r for r in new}
 need(len(a)==len(old)and len(b)==len(new),'unique modules')
 common=a.keys()&b.keys();norm=[n for n in sorted(common)if a[n]['normalized_sha256']!=b[n]['normalized_sha256']]
 return dict(old_module_count=len(a),new_module_count=len(b),module_order_unchanged=[x['module']for x in old]==[x['module']for x in new],added=sorted(b.keys()-a.keys()),removed=sorted(a.keys()-b.keys()),normalized_changed=norm,normalized_unchanged_count=len(common)-len(norm),raw_only_changed=[n for n in sorted(common)if a[n]['normalized_sha256']==b[n]['normalized_sha256']and a[n]['raw_sha256']!=b[n]['raw_sha256']],changed_outside_eight_observer_names=sorted(set(norm)-OBSERVERS),observer_names_not_changed=sorted(OBSERVERS-set(norm)),acceptance_authorized=False)
def audit(folder):
 need(folder.is_dir() and not folder.is_symlink(),'metadata directory')
 need({p.name for p in folder.iterdir()}=={'frontend-summary.json','frontend-qualification.json'},'exact two artifact files only')
 summary,sb=read(folder/'frontend-summary.json',65536);raw,qb=read(folder/'frontend-qualification.json',2031616)
 need(len(sb)+len(qb)<=2097152,'aggregate2MiB')
 need(summary['schema']=='OBSERVER_FRONTEND_SAFE_SUMMARY_V1'and summary['artifact_identity']==IDENTITY,'summary identity')
 need(summary['qualification_file']==dict(name='frontend-qualification.json',bytes=len(qb),sha256=sha(qb)),'two-file binding')
 need(raw['artifact_identity']==IDENTITY,'qualification identity')
 for r in (summary,raw):
  need(all(r.get(k)is False for k in ('archive_link_executed','numerical_pass','sv_accepted')),'scope flags')
 need(summary['full_block_profiles_completed']==0 and summary['final_rtl_replay']is False,'no numerical upgrade')
 result=dict(scope='SAVED_FRONTEND_METADATA_DIFFERENCE_AUDIT_NOT_ACCEPTANCE',artifact_identity=IDENTITY,summary_sha256=sha(sb),qualification_sha256=sha(qb),observed_status=summary['status'],acceptance_authorized=False,numerical_pass=False,sv_accepted=False,full_m128_pass_count=0)
 if summary['status']!='FRONTEND_QUALIFICATION_OBSERVED_UNREVIEWED':
  need(raw['schema']=='FRONTEND_QUALIFICATION_UNAVAILABLE_V1'and raw['status']==summary['status'],'unavailable typed receipt')
  result['status']='OBSERVATION_UNAVAILABLE_OR_INCOMPLETE_NOT_TASK_STOP';return result
 need(sha((Q/'SOURCE_PINS.json').read_bytes())==PINS_SHA,'published full sourcepins identity')
 sys.path.insert(0,str(Q));import export_metadata as e
 projector=e.checker(ROOT) # Independently verifies all644 source dependencies.
 q=projector.project_qualification(raw,IDENTITY)
 need([r['name']for r in summary['stages']]==list(e.PREP)+list(e.INNER),'exact24stages')
 need(all(r.get('strict_complete')is True and r.get('native_exit')==0 and r.get('error_count')==0 and all(r.get(k)is True for k in ('cleanup_complete','pipe_eof_observed','gzip_finalized'))for r in summary['stages']),'24 strict saved process receipts')
 need(summary['cpu_capability_observation']==q['cpu_capability_observation'],'CPUcap observation binding')
 old,old_bytes=read(M/'C7_MODULE_FINGERPRINTS.json',128<<10);need(sha(old_bytes)==MODULES_SHA and old['scanner_sha256']==q['sv']['scanner_sha256']==SCANNER_SHA,'same reviewed scanner/module baseline')
 # Avoid stale R2 JSON: it belongs to different scanner 2efe7..., not b49c757....
 import ast
 source=ast.parse((M/'check_fresh_sv.py').read_text());values={n.targets[0].id:ast.literal_eval(n.value)for n in source.body if isinstance(n,ast.Assign)and isinstance(n.targets[0],ast.Name)and n.targets[0].id in ('EXPECTED','SCANNER_SHA','MODULE_BASELINE_SHA')}
 need(values==dict(EXPECTED=OLD_NORMALIZED,SCANNER_SHA=SCANNER_SHA,MODULE_BASELINE_SHA=MODULES_SHA),'old hard gate anchors unchanged')
 result.update(status='STRICT_METADATA_VALIDATED_SV_DIFFERENCES_REQUIRE_REVIEW',old_sv=dict(raw_sha256=old['raw_sha256'],normalized_sha256=OLD_NORMALIZED,module_fingerprints_sha256=MODULES_SHA,scanner_sha256=SCANNER_SHA),new_sv={k:q['sv'][k]for k in ('raw_sha256','normalized_sha256','bytes','counts')},module_difference=module_diff(old['modules'],q['sv']['modules']),ports=dict(total=len(q['ports']),baseline_85_unchanged=True,new_observer_outputs=37,new_observer_bits=948),make_files=len(q['make_closure']),native_dependency_rows=len(q['native_dependency_metadata']),driver_object=q['driver_dependency']['object'],driver_depfile={k:v for k,v in q['driver_dependency']['depfile'].items()if k!='text'},driver_dependency_count=len(q['driver_dependency']['dependencies']),cpu_capability_observation=q['cpu_capability_observation'])
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--metadata-dir',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();r=audit(a.metadata_dir.resolve())
 with a.output.open('x')as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r,indent=2))
