"""One reviewed source parent, one protocol-only job, no artifact transfer."""
import json,os,pathlib,re,subprocess
LAUNCH='ci_launch/public21_downowner_protocol_identityfix_20261102_once.json'
NONCE='public21_downowner_protocol_identityfix_20261102_once'
SCHEMA='PUBLIC21_DOWNOWNER_PROTOCOL_SOURCE_ONLY_ONE_SHOT_V1'
def need(value,message):
 if not value:raise ValueError(message)
def validate(event,manifest,attempt,head,parent,diff):
 need(attempt=='1','no workflow retry')
 need(type(manifest) is dict and set(manifest)=={'schema','source_sha','nonce'},'exact launch fields')
 need(manifest['schema']==SCHEMA and manifest['nonce']==NONCE,'fixed protocol-only scope')
 sha=manifest['source_sha'];need(type(sha) is str and re.fullmatch('[0-9a-f]{40}',sha),'source SHA')
 need(type(event) is dict and event.get('ref')=='refs/heads/main' and event.get('before')==sha==parent and event.get('after')==head and sha!=head,'direct reviewed source parent')
 need(diff=='A\t'+LAUNCH+'\n','only one new launch path')
 return sha
def bounded_json(path,cap):
 p=pathlib.Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=cap,'bounded regular JSON');return json.loads(p.read_text())
def main():
 event=bounded_json(os.environ['GITHUB_EVENT_PATH'],2<<20);manifest=bounded_json(LAUNCH,4096)
 parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True).split();need(len(parents)==2,'single parent')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True)
 sha=validate(event,manifest,os.environ['GITHUB_RUN_ATTEMPT'],parents[0],parents[1],diff)
 need(os.environ['GITHUB_SHA']==parents[0],'actual launch HEAD');rid=int(os.environ['GITHUB_RUN_ID']);need(rid>0,'actual run')
 blob=subprocess.check_output(['git','rev-parse','HEAD:'+LAUNCH],text=True).strip();need(re.fullmatch('[0-9a-f]{40}',blob),'launch blob')
 identity=dict(schema='PUBLIC21_DOWNOWNER_PROTOCOL_JOB_IDENTITY_V1',run_id=rid,source_commit=sha,launch_commit=parents[0],launch_manifest_path=LAUNCH,launch_manifest_blob_sha=blob,scope='PROTOCOL_ONLY_MOCK_MATRIX_VECTOR_DDR_NO_NUMERICAL_PASS_NO_ARTIFACT_TRANSFER')
 with (pathlib.Path(os.environ['RUNNER_TEMP'])/'public21-b-identity.json').open('x') as f:json.dump(identity,f,sort_keys=True);f.write('\n')
 with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('source_sha='+sha+'\n')
if __name__=='__main__':main()
