"""Reuse exact original references under fresh shared-owner lease and caller stage.
Caller supplies actual strict-supervisor stage(name,argv,seconds,rss,extra_pins).
No model algorithm/seed/topk rewrite. No backend/DUT dependency or upload.
"""
import hashlib,importlib.util,json,pathlib,signal
P=pathlib.Path;D=P(__file__).resolve().parent
_policy_spec=importlib.util.spec_from_file_location('samejob_profile_policy', P(__file__).resolve().parent.parent/'profile_policy.py');profile_policy=importlib.util.module_from_spec(_policy_spec);_policy_spec.loader.exec_module(profile_policy)
MODELS=('qwen2_1p5b','qwen3_5_0p8b','qwen3_5_0p8b','qwen3_5_35b_a3b','qwen3_5_35b_a3b')
KEYS=('qwen2','qwen35_08b','qwen35_08b','qwen35_35b','qwen35_35b')
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p).resolve();return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def complete(r):return(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True

def run(b,stage):
 need(b['profiles']==list(range(5))and b['tokens']==128,'whole original registered reference round')
 profile_policy.require_source_pin(b['pins']);execution_policy=profile_policy.checked(b)
 repo=P(b['repo']);out=P(b['output']);need(not out.exists()and out.is_relative_to(P(b['owner_root'])),'fresh owning reference output');out.mkdir()
 owner_path=P(b['owner_module']);need(sha(owner_path)==b['pins'][str(owner_path)],'reviewed fresh owner module')
 spec=importlib.util.spec_from_file_location('fresh_owner_reference',owner_path);owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
 observed,_=owner.verify(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root']);need(observed['identity']==b['identity'],'actual samejob owner')
 profile_policy.require_same(b,observed)
 result={}
 for i in profile_policy.eligible(b):
  home=out/f'profile{i}';home.mkdir();dest=home/'actual/reference'
  with owner.lease(b['owner_manifest']['path'],b['owner_manifest']['sha256'],b['owner_root'],i,home)as selected:
   rt=selected[KEYS[i]];source=repo/'candidates'/('independent_reference_p0_cache_arm_20261028T2313'if i==0 else'independent_block_reference_prepare_v3_20261028T2312')/'run_reference.py'
   need(sha(source)==b['pins'][str(source)],'original arithmetic source')
   args=[str(source),'--profile',str(i),'--payload',b['payload'],'--config',str(repo/'config/upstream/weight_headers'/MODELS[i]/'config.json'),'--runtime-receipt',rt['receipt']['path'],'--runtime-receipt-sha256',rt['receipt']['sha256'],'--runtime-source-pins',rt['sidecar']['path'],'--runtime-source-pins-sha256',rt['sidecar']['sha256'],'--output',str(dest),'--execute-reviewed']
   phase=home/'PHASE.json'
   with phase.open('x')as f:json.dump(dict(argv=args,source_sha256=sha(source)),f,indent=2)
   r=stage(f'reference{i}',[rt['wrapper'],str(D/'reference_phase.py'),'--binding',str(phase),'--sha256',sha(phase)],b['wall_seconds'],3,{str(phase):sha(phase)},output_root=home/'actual',resource_profile='reference')
   if not complete(r):
    with(home/'OWNERSHIP_INCOMPLETE.json').open('x')as f:json.dump({'state':'HOLD_PARENT_LEASE'},f)
    while True:signal.pause()
   need(r['native_exit']==0 and not r['errors'],'reference failed no auto retry')
   receipt=dest/'RESULT.json';doc=json.loads(receipt.read_text());need(doc['profile']['profile']==i and doc['complete_block_tokens']==128 and doc['exact_baseline_observer_output_equal']is True and doc['hardware_executed']is False and doc['router_policy']=='UNMODIFIED_OFFICIAL_TORCH_TOPK','original independent reference contract')
   for row in doc['tensor_records'].values():
    p=dest/row['file'];need(p.resolve().is_relative_to(dest)and not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual reference tensor pin')
   result[str(i)]=pin(receipt)
 with(out/'REFERENCES.json').open('x')as f:json.dump(dict(execution_policy=execution_policy,scope='REGISTERED_FIVE_ELIGIBLE_SOFTWARE_REFERENCES_NOT_DUT',references=result,identity=b['identity']),f,indent=2)
 return result
