"""One unique source-only compile plus eight owner protocol cases. This file never dispatches CI."""
import json,os,pathlib,re,subprocess
LAUNCH='ci_launch/prefill_owner_protocol_20261103_once.json'
NONCE='prefill_owner_protocol_20261103_once'
def need(v,m):
 if not v:raise ValueError(m)
def main():
 need(os.environ.get('GITHUB_REPOSITORY')=='liyang53719/hetero_cnn_llm_aha','exact repository')
 need(os.environ.get('GITHUB_RUN_ATTEMPT')=='1','no automatic rerun')
 e=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text());d=json.loads(pathlib.Path(LAUNCH).read_text());parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True,timeout=5).split()
 need(set(d)=={'schema','source_sha','nonce','through','driver_sha256'}and d['schema']=='REAL_OWNER_PROTOCOL_SOURCE_ONLY_ONCE_V1'and d['nonce']==NONCE,'exact launch schema')
 need(d['through']=='compile_and_protocol8'and d['driver_sha256']=='2c66667ae5ed85b5712f5e946d82dc881a41a45bd3835af64ced1e66ccec0688','exact preapproved protocol mode and driver')
 need(len(parents)==2 and re.fullmatch('[0-9a-f]{40}',d['source_sha'])and parents[1]==d['source_sha']==e.get('before'),'exact reviewed source parent')
 need(parents[0]==e.get('after')==os.environ['GITHUB_SHA']and e.get('ref')=='refs/heads/main','exact main launch')
 diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True,timeout=5);need(diff=='A\t'+LAUNCH+'\n','only new unique launch file')
 dst=pathlib.Path(os.environ['RUNNER_TEMP'])/'owner-protocol-identity.json'
 with dst.open('x')as f:json.dump(dict(source_commit=d['source_sha'],launch_commit=parents[0],run_id=os.environ['GITHUB_RUN_ID'],attempt=1,through='compile_and_protocol8',driver_sha256=d['driver_sha256']),f)
 with open(os.environ['GITHUB_OUTPUT'],'a')as f:f.write('source_sha='+d['source_sha']+'\n')
if __name__=='__main__':main()
