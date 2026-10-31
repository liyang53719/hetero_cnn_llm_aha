"""Build-only single-A launch. Transport stays disabled pending explicit approval."""
import hashlib,json,os,pathlib,re,subprocess
LAUNCH='ci_launch/five_m128_split_build_only_20261031_once.json'
NONCE='five_m128_split_build_only_20261031_once'
SCHEMA='FIXED4096_SPLIT_BUILD_ONLY_SEVEN_FILE_ONE_SHOT_V1'
# Only a separately reviewed source publication may bind the user's actual
# seven-file transfer approval receipt. No manifest boolean supplies authority.
ACCEPTED_TRANSFER_APPROVAL_SHA256=None

def need(v,m):
 if not v:raise ValueError(m)
def validate(event,manifest,attempt,head,parent,diff):
 need(attempt=='1','no retry')
 need(set(manifest)=={'schema','source_sha','nonce','transfer_approval_sha256'}and manifest['schema']==SCHEMA and manifest['nonce']==NONCE,'exact build-only manifest')
 need(ACCEPTED_TRANSFER_APPROVAL_SHA256 is not None and manifest['transfer_approval_sha256']==ACCEPTED_TRANSFER_APPROVAL_SHA256,'SEVEN_FILE_TRANSFER_APPROVAL_PENDING')
 sha=manifest['source_sha'];need(isinstance(sha,str)and re.fullmatch('[0-9a-f]{40}',sha),'source SHA')
 need(event.get('ref')=='refs/heads/main'and event.get('before')==sha==parent and event.get('after')==head and sha!=head,'direct reviewed source parent')
 need(diff=='A\t'+LAUNCH+'\n','only single new launch path')
 return sha

def main():
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text());manifest=json.loads(pathlib.Path(LAUNCH).read_text())
 parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True).split();need(len(parents)==2,'single parent')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True)
 sha=validate(event,manifest,os.environ['GITHUB_RUN_ATTEMPT'],parents[0],parents[1],diff)
 need(os.environ['GITHUB_SHA']==parents[0],'actual launch HEAD');rid=int(os.environ['GITHUB_RUN_ID']);need(rid>0,'actual run')
 blob=subprocess.check_output(['git','rev-parse','HEAD:'+LAUNCH],text=True).strip();need(re.fullmatch('[0-9a-f]{40}',blob),'launch blob')
 identity=dict(run_id=rid,artifact_name='hetero-common-dut-'+str(rid),source_commit=sha,launch_commit=parents[0],launch_manifest_path=LAUNCH,launch_manifest_blob_sha=blob)
 with (pathlib.Path(os.environ['RUNNER_TEMP'])/'hetero-split-build-identity.json').open('x')as f:json.dump(identity,f,sort_keys=True);f.write('\n')
 with open(os.environ['GITHUB_OUTPUT'],'a')as f:f.write('source_sha='+sha+'\n')
if __name__=='__main__':main()
