"""Unique old/new fixed4096 SV-only launch; no Verilator/GCC/link/numerics."""
import json,os,pathlib,re,subprocess
LAUNCH='ci_launch/observer_fixed4096_sv_only_difference_20261031_portlabel_once.json'
def validate(event,manifest,attempt,head,parent,diff):
 if attempt!='1':raise ValueError('retry not admitted')
 if set(manifest)!={'schema','source_sha','profile','nonce'} or manifest['schema']!='OBSERVER_FIXED4096_SV_ONLY_DIFFERENCE_ONE_SHOT_V1' or manifest['profile']!='FIXED4096_OLD_NEW_SV_ONLY_TWO_MODULE_DIFFERENCE' or manifest['nonce']!='observer_fixed4096_sv_only_difference_20261031_portlabel_once':raise ValueError('observer SV-only launch contract')
 sha=manifest['source_sha']
 if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('reviewed source SHA')
 if event.get('ref')!='refs/heads/main' or event.get('before')!=sha or parent!=sha or event.get('after')!=head or sha==head:raise ValueError('exact direct launch from reviewed source')
 if diff!='A\t'+LAUNCH+'\n':raise ValueError('only unique newly added launch manifest')
 return sha
if __name__=='__main__':
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text());manifest=json.loads(pathlib.Path(LAUNCH).read_text());parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True).split()
 if len(parents)!=2:raise ValueError('exactly one parent')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True)
 sha=validate(event,manifest,os.environ['GITHUB_RUN_ATTEMPT'],parents[0],parents[1],diff)
 if os.environ['GITHUB_SHA']!=parents[0]:raise ValueError('actual launch HEAD')
 run_id=int(os.environ['GITHUB_RUN_ID'])
 if run_id<=0:raise ValueError('actual run ID')
 blob=subprocess.check_output(['git','rev-parse','HEAD:'+LAUNCH],text=True).strip()
 if not re.fullmatch('[0-9a-f]{40}',blob):raise ValueError('actual launch blob')
 identity=dict(run_id=run_id,artifact_name='hetero-observer-sv-only-summary-'+str(run_id),source_commit=sha,launch_commit=parents[0],launch_manifest_path=LAUNCH,launch_manifest_blob_sha=blob)
 dest=pathlib.Path(os.environ['RUNNER_TEMP'])/'hetero-observer-sv-only-identity.json'
 with dest.open('x') as f:json.dump(identity,f,sort_keys=True);f.write('\n')
 with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('source_sha='+sha+'\n')
 print('OBSERVER_SV_ONLY_SOURCE_IDENTITY_VALIDATED '+sha)
