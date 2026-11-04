"""Dormant source publication, then exactly one new nonce file in second push."""
import hashlib,json,os,pathlib,re,subprocess
P=pathlib.Path
LAUNCH='ci_launch/gdn32_compile_only_20261104_once.json'
NONCE='gdn32_compile_only_20261104_once'
WORKFLOW='.github/workflows/gdn32-compile-only.yml'
GENERATION='2b2f02d698f16a57ba696c52c4669a1226a68c5378efdc8ebe392cc1b9098f52'
SCHEMA='GDN32_FRESH162_COMPILE_ONLY_LAUNCH_V1'
def need(v,m):
 if not v:raise ValueError(m)
def validate(event,m,attempt,head,parent,diff,workflow_hash):
 need(attempt=='1','one attempt only')
 need(type(m)is dict and set(m)=={'schema','source_sha','nonce','generation_sha256','workflow_sha256'},'exact launch fields')
 need(m['schema']==SCHEMA and m['nonce']==NONCE and m['generation_sha256']==GENERATION and m['workflow_sha256']==workflow_hash,'exact source nonce/generation/workflow')
 source=m['source_sha'];need(isinstance(source,str)and re.fullmatch('[0-9a-f]{40}',source),'source hash')
 need(event.get('ref')=='refs/heads/main' and event.get('before')==source==parent and event.get('after')==head and source!=head,'direct source then launch push')
 need(diff=='A\t'+LAUNCH+'\n','only new exact nonce file')
 return source
def main():
 event=json.loads(P(os.environ['GITHUB_EVENT_PATH']).read_text());p=P(LAUNCH);need(p.is_file()and not p.is_symlink()and p.stat().st_size<4096,'bounded launch')
 m=json.loads(p.read_text());parents=subprocess.check_output(['git','rev-list','--parents','-n','1','HEAD'],text=True).split();need(len(parents)==2,'single parent')
 workflow_hash=hashlib.sha256(P(WORKFLOW).read_bytes()).hexdigest();diff=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-status','-r','HEAD'],text=True)
 source=validate(event,m,os.environ['GITHUB_RUN_ATTEMPT'],parents[0],parents[1],diff,workflow_hash);need(parents[0]==os.environ['GITHUB_SHA'],'actual launch HEAD')
 identity=dict(schema='GDN32_COMPILE_JOB_IDENTITY_V1',run_id=int(os.environ['GITHUB_RUN_ID']),source_commit=source,launch_commit=parents[0],generation_sha256=GENERATION,workflow_sha256=workflow_hash,nonce=NONCE,launch_manifest_sha256=hashlib.sha256(p.read_bytes()).hexdigest());need(identity['run_id']>0,'run identity')
 with (P(os.environ['RUNNER_TEMP'])/'gdn32-compile-identity.json').open('x')as f:json.dump(identity,f,sort_keys=True)
 with open(os.environ['GITHUB_OUTPUT'],'a')as f:f.write('source_sha='+source+'\n')
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'FAIL_LAUNCH','error_class':type(e).__name__}));raise SystemExit(1)
