"""Narrow added-once manifest trigger. No credential or network access."""
import json,os,pathlib,re,subprocess
LAUNCH='ci_launch/fixed_frontend_r5_20261029_once.json'
def validate(event,manifest,attempt,head,parent,diff):
 if attempt!='1':raise ValueError('retry not admitted')
 if set(manifest)!={'schema','source_sha','profile','nonce'} or manifest['schema']!='FRONTEND_R5_ONE_SHOT_V1' or manifest['profile']!='FIXED4096_VECTOR32_FRONTEND_ONLY' or manifest['nonce']!='fixed_frontend_r5_20261029_once':raise ValueError('launch contract')
 sha=manifest['source_sha']
 if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('reviewed source SHA')
 if event.get('ref')!='refs/heads/main' or event.get('before')!=sha or parent!=sha or event.get('after')!=head:raise ValueError('exact direct launch from reviewed source')
 if diff!='A\t'+LAUNCH+'\n':raise ValueError('only unique newly added launch manifest')
 return sha
if __name__=='__main__':
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text());manifest=json.loads(pathlib.Path(LAUNCH).read_text());parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True).split()
 if len(parents)!=2:raise ValueError('exactly one parent')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True)
 sha=validate(event,manifest,os.environ['GITHUB_RUN_ATTEMPT'],parents[0],parents[1],diff)
 with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('source_sha='+sha+'\n')
 print('ONE_SHOT_SOURCE_IDENTITY_VALIDATED '+sha)
