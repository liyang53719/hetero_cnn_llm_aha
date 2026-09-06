#!/usr/bin/env python3
"""Actual finished block runs only. Does not promote synthetic weights to models."""
import hashlib,json,re,sys
from pathlib import Path
p=Path(sys.argv[1]);layout=json.loads((p/'generated/layout.json').read_text());records=[]
retained=bool(layout.get('retained_matrix',False))
for f in sorted(p.glob('tokens_*.log')):
    text=f.read_text();lines=[s for s in text.splitlines() if s.startswith('CONTINUOUS_QWEN2_BLOCK_PASS ')]
    if len(lines)!=1:raise RuntimeError('missing/duplicate final success '+str(f))
    r=dict(re.findall(r'(\w+)=([^ ]+)',lines[0]))
    for k,v in list(r.items()):
        if k!='hash':r[k]=float(v) if '.' in v or 'e' in v.lower() else int(v)
    if r['phases']!=15 or r['host_intermediate_writes']!=0 or r['full_model']!=0 or r['canonical_512_array']!=int(retained):raise RuntimeError('scope mismatch')
    for key in ['hidden','ffn','heads','kv_heads']:
        if r[key]!=layout[key]:raise RuntimeError('shape mismatch '+key)
    t,h,fsize,kv=r['tokens'],r['hidden'],r['ffn'],r['kv_heads']*layout['head_dim']
    macs=t*(2*h*h+2*h*kv+3*h*fsize)+t*(t+1)*h
    if r['macs']!=macs or r['executed_macs']!=macs*(32 if retained else 1):raise RuntimeError('MAC ledger mismatch')
    checked=t*(9*h+3*kv+3*fsize)
    if r['checked_fp32']!=checked:raise RuntimeError('incomplete numerical coverage')
    ids=[int(re.search(r'phase=(\d+)',s).group(1)) for s in text.splitlines() if s.startswith('STAGE_CHECK ')]
    if ids!=list(range(15)):raise RuntimeError('missing/duplicate/out-of-order stages')
    r['log_sha256']=hashlib.sha256(f.read_bytes()).hexdigest();r['log']=f.name;records.append(r)
if not records:raise RuntimeError('no finished numerical run')
print(json.dumps(dict(status='PASS_CONTINUOUS_BLOCK_NUMERICAL_SCOPE',source_commit=(p/'source_commit.txt').read_text().strip(),runs=records,
 io='single-beat AXI4 512-bit',canonical_matrix_512_integration=retained,canonical_performance_schedule=False,official_weights=False,full_model=False,dc=False),indent=2))
