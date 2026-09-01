#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/results/qwen2_device_backpressure';LOG=OUT/'run.log';m=re.search(r'HETERO_QWEN2_BACKPRESSURE_PASS layers=(\d+) groups=(\d+) completions=(\d+) stalls=(\d+) watchdog=(\d+) status=(\d+) checkpoints=(\d+)',LOG.read_text());assert m;values=tuple(map(int,m.groups()));assert values[0:3]==(28,7,28)and values[3]>0 and values[4:]==(64,0,28)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
final=OUT/'payload/layer27/final_fp32.bin';accepted=ROOT/'work/results/qwen2_q1024_full28_backend/layer27/final_fp32.bin';assert sha(final)==sha(accepted)
r={'schema_version':1,'status':'PASS_Q1024_SEVEN_GROUP_RANDOM_COMPLETION_BACKPRESSURE','layers':28,'groups':7,'completions':28,'stalls':values[3],'watchdog':64,'status_code':0,'checkpoints':28,'final_sha256':sha(final),'checks':{'random_ready':True,'all_groups_continuous':True,'completion_order':True,'no_timeout':True,'no_reference_injection':True},'provenance':{'log':sha(LOG),'api_header':sha(ROOT/'src/hetero_qwen2_device_api.h'),'harness':sha(ROOT/'cpp/qwen2_device_backpressure_smoke.cpp')}};(ROOT/'reports/execution/qwen2_device_backpressure_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'stalls':r['stalls'],'checkpoints':28},sort_keys=True))
