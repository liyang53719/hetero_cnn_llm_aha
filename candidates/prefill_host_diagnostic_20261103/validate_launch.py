"""Dormant one-shot launch identity, not execution or numerical self-approval.
A future separately authorized launch adds ONLY LAUNCH to the reviewed source.
The source commit cannot embed its own SHA; the launch binds it as its parent.
"""
import hashlib,json,os,pathlib,re,subprocess
P=pathlib.Path
LAUNCH='ci_launch/p0_m128_prefill_host_diagnostic_20261103_once.json'
NONCE='p0_m128_prefill_host_diagnostic_20261103_once'
SCHEMA='SAME_JOB_P0_M128_PREFILL_HOST_DIAGNOSTIC_ONE_SHOT_V1'
MODE='SAME_JOB_P0_M128_HOST_DIAGNOSTIC'
EXPECTED_SOURCE_PARENT='15054841ae1394879e30c1351dab6ded702d7a63'
CATALOG='candidates/same_job_execution_20261030/SOURCE_PINS.json'
IDENTITY='prefill-host-diagnostic-identity.json'
ADMISSION='prefill-host-diagnostic-launch.json'
STATE_DIR='prefill-host-diagnostic-state'

def need(v,m):
 if not v:raise ValueError(m)
def digest(v,n):return type(v)is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',v)is not None
def read(p,cap):
 p=P(p);need(p.is_file()and not any(q.is_symlink()for q in(p,*p.parents))and 0<p.stat().st_size<=cap,'bounded regular launch metadata')
 return json.loads(p.read_text(),object_pairs_hook=unique)
def unique(pairs):
 d={}
 for k,v in pairs:
  need(k not in d,'duplicate JSON member');d[k]=v
 return d

def validate(event,manifest,attempt,head,parent,diff,source_parent):
 need(attempt=='1','retry not admitted')
 need(type(manifest)is dict and set(manifest)=={'schema','source_sha','source_parent','profile','nonce','source_catalog_sha256'},'exact one-shot launch keys')
 need(manifest['schema']==SCHEMA and manifest['profile']==MODE and manifest['nonce']==NONCE,'unique diagnostic launch contract')
 sha=manifest['source_sha'];need(digest(sha,40)and digest(head,40)and digest(manifest['source_catalog_sha256'],64),'exact reviewed source identities')
 need(EXPECTED_SOURCE_PARENT is not None and source_parent==manifest['source_parent']==EXPECTED_SOURCE_PARENT,'exact reviewed source parent')
 need(type(event)is dict and event.get('ref')=='refs/heads/main'and event.get('before')==sha==parent and event.get('after')==head and sha!=head,'exact direct launch from reviewed source')
 need(event.get('deleted',False)is False and event.get('forced',False)is False,'normal non-forced source launch')
 need(diff=='A\t'+LAUNCH+'\n','only unique newly added launch manifest')
 return sha

def main():
 need(os.environ.get('GITHUB_EVENT_NAME')=='push','push only')
 event=read(os.environ['GITHUB_EVENT_PATH'],2<<20);manifest=read(LAUNCH,4096)
 def git(*args):return subprocess.check_output(['git',*args],text=True,timeout=15).strip()
 parents=git('rev-list','--parents','-n','1','HEAD').split();need(len(parents)==2,'exactly one launch parent')
 sourceparents=git('rev-list','--parents','-n','1',parents[1]).split();need(len(sourceparents)==2,'exactly one source parent; fetch depth three')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True,timeout=15)
 source=validate(event,manifest,os.environ.get('GITHUB_RUN_ATTEMPT'),parents[0],parents[1],diff,sourceparents[1])
 need(os.environ.get('GITHUB_SHA')==parents[0],'actual launch HEAD')
 catalog=P(CATALOG);need(catalog.is_file()and not catalog.is_symlink()and catalog.stat().st_size<=2<<20,'bounded frozen source catalog')
 need(hashlib.sha256(catalog.read_bytes()).hexdigest()==manifest['source_catalog_sha256'],'independently launched source catalog hash')
 run=os.environ['GITHUB_RUN_ID'];need(run.isascii()and run.isdigit()and 0<int(run)<1<<63,'actual run ID')
 blob=git('rev-parse','HEAD:'+LAUNCH);need(digest(blob,40),'actual launch blob')
 identity=dict(run_id=int(run),artifact_name='hetero-common-dut-'+run,source_commit=source,launch_commit=parents[0],launch_manifest_path=LAUNCH,launch_manifest_blob_sha=blob)
 dest=P(os.environ['RUNNER_TEMP'])
 for name,value in ((IDENTITY,identity),(ADMISSION,dict(schema='SAME_JOB_DIAGNOSTIC_LAUNCH_IDENTITY_V1',manifest=manifest,identity=identity))):
  with(dest/name).open('x')as f:json.dump(value,f,sort_keys=True);f.write('\n')
 with open(os.environ['GITHUB_OUTPUT'],'a')as f:f.write('source_sha='+source+'\n')
 print('P0_HOST_DIAGNOSTIC_LAUNCH_IDENTITY_VALIDATED')

def safe_failure():
 # No exception text, environment, arbitrary source strings, paths or traceback.
 p=P(os.environ['RUNNER_TEMP'])/STATE_DIR/'ENTRY_SUMMARY.json'
 prior=read(p,4096)
 if prior.get('status')!='FAILED':
  prior=dict(schema='P0_HOST_DIAGNOSTIC_SAFE_ENTRY_V1',status='FAILED',reason_code='LAUNCH_REJECTED',execution_mode=MODE,numerical_pass=False,raw_payloads_uploaded=False)
  tmp=p.with_suffix('.tmp')
  with tmp.open('x')as f:json.dump(prior,f,sort_keys=True);f.write('\n')
  tmp.replace(p)
if __name__=='__main__':
 try:main()
 except Exception:
  try:safe_failure()
  except Exception:pass # Initial safe receipt remains if filesystem is unavailable.
  raise SystemExit(1)
