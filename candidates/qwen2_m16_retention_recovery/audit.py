"""Read-only posthoc recovery of a fixed, completed M16 model with failed JSON seal."""
import argparse,datetime,hashlib,json,math,sys
from pathlib import Path
from types import SimpleNamespace
from candidates.qwen2_m16_stage_diagnostic import common as c,geometry as g,inputs as inp,reference as old
ROOT=c.ROOT;HERE=Path(__file__).resolve().parent
BASE=c.BASE/'cost01';MODEL=BASE/'model';OUT=BASE/'recovery01'
FREEZE=ROOT/'work/qwen2_m16_retention_recovery/SOURCE_FREEZE.json'
FIXED={
 'work/qwen2_m16_stage_diagnostic/SOURCE_FREEZE.json':'ac2051b618f6626969628ed50c40a47a5e386dc44799e3418df5603e7cd5dca7',
 'work/qwen2_m16_stage_diagnostic/cost01/model/RESULT.json':'361eeebec7241dfbbf69ee9a4eb052b8cb3138518e0ca37a4cef4121aa599b06',
 'work/qwen2_m16_stage_diagnostic/cost01/model.SUPERVISOR.json':'8afb257915551c5b1d0f36ab2e5f9e3681d2dfd56dbad95c431e9d90671c83af',
 'work/qwen2_m16_stage_diagnostic/cost01/model/attention_observation/summary.json':'7d9c0d4e0a31eb8a97529c383c8e234c2bf6d6ff6e3ab8ef4deb13f7aebca71d',
 'work/qwen2_m16_stage_diagnostic/cost01/model/SOURCES_BEFORE.json':'c24290a8a9e8fe1ba564471adf8ccdc63e7a0b9c9ff667de24caa46bc47c46fc',
 'work/qwen2_m16_stage_diagnostic/cost01/model/STAGES.jsonl':'cc17d22755a0320f070122e905b3f362823735eb75b8ebb98c704db920a57ee9'}
EXTRA=('candidates/qwen2_supervisor_recovery/observation.py',)

def regular(path):
    g.need(path.resolve()==path and path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'canonical read-only evidence file')
    return path

def digest(path):return inp.sha(regular(path))
def file_spec(path):return dict(bytes=regular(path).stat().st_size,sha256=digest(path))
def read(path):return json.loads(regular(path).read_text())

def sources_now():
    c.dependencies()
    g.need(digest(c.FREEZE)==FIXED[str(c.FREEZE.relative_to(ROOT))],'original freeze externally pinned')
    prior=read(c.FREEZE)['sources']
    g.need(len(prior)==135,'original135 source set')
    result={name:digest(ROOT/name) for name in prior}
    g.need(result==prior,'original execution source changed')
    for path in HERE.iterdir():
        if path.is_file():result[str(path.relative_to(ROOT))]=digest(path)
    for name in EXTRA:result[name]=digest(ROOT/name)
    return result

def require_sources():
    f=read(FREEZE);now=sources_now();g.need(f['sources']==now,'independent recovery source freeze changed');return now

def validate_execution(r):
    g.need(r['status']=='M16_MODEL_FAILED' and r['model_completed'] is False and r['actual_outputs_sealed'] is False and
      r['error_type']=='ValueError' and r['error']=='saved observer receipt differs','only the exact failed serialization boundary')
    g.need(r['whole_block_terminal'] is True and r['finalfence'] is True and r['fullblock_pass'] is False and
      r['formal_reference_contract'] is False and r['reference_executed'] is False and r['old_wrapper_optimizations_loaded'] is False,'original terminal/scope')
    g.need(not any(key in r for key in ('native_after','artifact_after','source_post_verified','input_post_verified','native_post_verified','local_retention')),'original postchecks were not reached')
    h=r['execution']['host'];a=h['accepted'];t=h['launch_result']
    g.need(t['status'] is None and t['completed']==21 and t['jobs']==17 and a['completion_fire']==21 and
      a['request_fire']==a['owner_result_fire']==17 and a['result_fire']==1 and h['reset_required'] is False,'real original21/17/1 no reset')
    g.need([v['pc'] for v in h['completions']]==list(range(21)) and all(v['status'] is None for v in h['completions']),'original ordered completions')
    g.need(set(h['events'])==set(range(22)) and len(h['requests'])==17,'original event and request coverage')
    g.need(r['backend_debts'] and not any(r['backend_debts'].values()) and r['failed_debts'] and not any(r['failed_debts'].values()),'actual final/failure debt snapshots empty')
    g.exact_totals(r['exact64_projections']);g.v_totals(h['qkv_reductions'])
    native=r['statistics']['total']['native']
    silu=SimpleNamespace(calls=r['failure_counters']['silu_calls'],sf_calls=lambda:native['silu_calls'],sf_failures=lambda:native['silu_failures'])
    g.need(g.whole(r['matrix'],t,silu,r['statistics'])==r['whole_accounting'],'original actual accounting rechecked')
    return True

def evidence_inventory(r,summary):
    from candidates.qwen2_exact64_diagnostic_fullblock.retention import ACTUAL_NAMES
    g.need(r['observation']==summary,'JSON observer records identical')
    inventory={}
    g.need(set(r['sealed_actual_outputs'])==ACTUAL_NAMES|{'silu'},'all20 actual commitments already existed')
    for name,spec in r['sealed_actual_outputs'].items():
        filename='actual_'+name+'.f32le';g.need(file_spec(MODEL/filename)==spec,'original actual commitment');inventory[filename]=dict(spec)
    for name,f in summary['fields'].items():
        for suffix,mult,key in (('.u32le',4,'raw_sha256'),('.presence',1,'presence_sha256'),('.count.u16le',2,'frequency_sha256')):
            filename='attention_observation/'+name+suffix;spec=dict(bytes=f['words']*mult,sha256=f[key])
            g.need(file_spec(MODEL/filename)==spec,'original observer commitment');inventory[filename]=spec
    inventory['attention_observation/summary.json']=file_spec(MODEL/'attention_observation/summary.json')
    # Structural validator is reused on a distinct recovery envelope; the
    # failed execution report itself is never patched into a fake success.
    envelope=dict(observation=summary,local_retention=dict(schema=1,scope='DIAGNOSTIC_SOFTWARE_OWNER',
      status='LOCAL_ACTUALS_RETAINED_BEFORE_ORACLE',local_only=True,upload_authorized=False,
      oracle_payloads_read=False,reference_operands_in_execution=False,inventory=inventory))
    old.validate_inventory(envelope);old.recheck_saved_coverage(MODEL)
    g.need({p.name for p in (MODEL/'attention_observation').iterdir()}=={Path(n).name for n in inventory if n.startswith('attention_observation/')},'exact original31 observer files')
    return inventory

def inspect():
    sources=require_sources()
    g.need(all(digest(ROOT/name)==pin for name,pin in FIXED.items()),'fixed external failed execution identities')
    r=read(MODEL/'RESULT.json');sup=read(BASE/'model.SUPERVISOR.json');validate_execution(r)
    g.need(sup['phase']=='MODEL' and sup['status']=='INCOMPLETE' and sup['returncode']==1 and sup['stop_reason'] is None,'original supervision remains failure')
    prior=read(c.FREEZE)['sources']
    g.need(r['sources']==prior==read(MODEL/'SOURCES_BEFORE.json'),'original pre-execution source identity')
    for name in read(c.FREEZE)['own_sources']:
        g.need(digest(MODEL/'executed_sources'/Path(name).name)==prior[name],'original executed own-source snapshot')
    inventory=evidence_inventory(r,read(MODEL/'attention_observation/summary.json'))
    pins,native=c.check_environment();_,_,artifact=c.artifacts();_,records=inp.load_inputs()
    g.need(native==r['native_before'] and artifact==r['artifact_before'] and records==r['input_records'] and
      c.runtime_python(pins)==r['framework_sources'],'posthoc source inputs and native identities match execution-before')
    g.need(require_sources()==sources and all(digest(ROOT/name)==pin for name,pin in FIXED.items()),'all frozen evidence remains unchanged')
    return r,dict(schema=1,status='RECOVERED_M16_DIAGNOSTIC',scope='POSTHOC_READONLY_RETENTION_RECOVERY',
      original_run='FAIL',original_model_status=r['status'],original_supervisor_status=sup['status'],
      original_inprocess_postchecks='NOT_REACHED',current_identity_check='POSTHOC',
      continuous_identity_claim=False,original_completion_seal=False,model_reexecuted=False,
      reference_executed=False,formal_reference_contract=False,fullblock_pass=False,performance='NO_GO',
      actual_public_terminal='RETIRED_21_COMPLETIONS_17_JOBS_1_LAUNCH',fixed_prior_sha256=FIXED,
      sources=sources,inventory=inventory,native_posthoc=native,artifact_posthoc=artifact,input_posthoc=records,
      framework_sources_posthoc=c.runtime_python(pins),difference='TEN_SHAPE_TUPLES_SERIALIZED_AS_JSON_LISTS',
      local_only=True,upload_authorized=False)

def validate_seal(seal,checked):
    value=dict(seal);when=value.pop('posthoc_utc',None)
    g.need(type(when) is str and datetime.datetime.fromisoformat(when).utcoffset() is not None,'posthoc timestamp')
    g.need(value==checked,'distinct recovery seal must match current read-only evidence checks')
    return True

def sealed():
    r,checked=inspect();seal=read(OUT/'SEAL.json');validate_seal(seal,checked)
    return r,seal,digest(OUT/'SEAL.json')

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');a=ap.parse_args(argv)
    if not a.execute:print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    c.limits(10,15)
    g.need(not OUT.exists(),'fresh independent recovery receipt');r,seal=inspect();OUT.mkdir()
    seal['posthoc_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();c.save(OUT/'SEAL.json',seal)
    print(json.dumps(dict(status=seal['status'],original_run='FAIL',inprocess_postchecks='NOT_REACHED',files=len(seal['inventory']),formal_reference_contract=False)))
    return 0
if __name__=='__main__':raise SystemExit(main())
