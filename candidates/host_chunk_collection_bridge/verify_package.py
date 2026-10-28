#!/usr/bin/env python3
"""Verify source/pin metadata only; never execute compiler or DUT."""
from pathlib import Path, PurePosixPath
import csv, hashlib, json, re

R=Path(__file__).resolve().parent
def need(ok,message):
    if not ok:raise ValueError(message)
def load(n):return json.loads((R/n).read_text())
def ident(p):
    b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def classrow(row):return dict(relative=row['relative'],bytes=int(row['bytes']),sha256=row['sha256'])
def verify():
    manifest=load('MANIFEST.json')['files']
    actual={p.relative_to(R).as_posix() for p in R.rglob('*') if p.is_file()}
    need(actual==set(manifest)|{'MANIFEST.json'},'exact package allowlist')
    need(not any(p.is_symlink() for p in R.rglob('*')),'no symlinks')
    for name,pin in manifest.items():
        p=R/name;rel=PurePosixPath(name);data=p.read_bytes();data.decode('utf-8')
        need(not rel.is_absolute() and '..' not in rel.parts,'relative package path')
        need(ident(p)==pin,'package hash '+name)
        need(p.suffix in {'.scala','.py','.json','.md','.patch','.tsv'},'text source only')
        need(len(data)<64*1024 and b'\0' not in data,'small text only')
        need(b'/work'+b'space/' not in data and b'/home/'+b'agent/' not in data,'no private runtime paths')
    need(sum(p.stat().st_size for p in R.rglob('*') if p.is_file())<96*1024,'small package cap')
    delta=load('CLASS_DELTA.json');base=R/delta['base_package']
    for name,pin in delta['base_files'].items():need(ident(base/name)==pin,'pinned shared bridge '+name)
    with (base/'BASELINE_CLASS_PINS.tsv').open() as f:rows=[classrow(x) for x in csv.DictReader(f,delimiter='\t')]
    need(len(rows)==903 and len({r['relative'] for r in rows})==903,'original903')
    by={r['relative']:r for r in rows}
    need(len(delta['removed'])==9 and len(delta['added'])==3,'exact delta9+3')
    for row in delta['removed']:
        need(by.pop(row['relative'],None)==classrow(row),'actual removed class')
    for row in delta['added']:
        need(row['relative'] not in by,'new historical class not duplicated');by[row['relative']]=classrow(row)
    retained=sorted(by.values(),key=lambda x:x['relative'])
    digest=hashlib.sha256((json.dumps(retained,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
    need(len(retained)==delta['retained_class_count']==897,'retained897')
    need(sum(r['bytes'] for r in retained)==delta['retained_class_bytes'],'retained bytes')
    need(digest==delta['canonical_retained_sha256'],'retained exact hash set')
    sources=load('SOURCE_PINS.json');need(len(sources['sources'])==10,'ten source pins')
    names={x['name'] for x in sources['sources']}
    for row in sources['sources']:
        need(row['byte_identical_to_actual_compiler_input'],'actual compiler source pin')
        if row['location']!='requires_parent':need(ident(R/row['path'])=={k:row[k] for k in ('bytes','sha256')},'public source '+row['name'])
    candidate=(R/'source/GdnRuntimeChunkLeafCollection.scala').read_bytes()
    for old,new in [('new UnifiedVectorRequestV2','new UnifiedOrdinaryVectorRequestV5'),('new UnifiedVectorResultV2','new UnifiedOrdinaryVectorResultV5'),('new GdnRuntimeChunkExecuteOwner)','new GdnRuntimeChunkExecuteOwnerV8)')]:
        need(candidate.count(new.encode())==1,'exact replacement');candidate=candidate.replace(new.encode(),old.encode())
    orig=sources['original_collection']
    need(len(candidate)==orig['bytes'] and hashlib.sha256(candidate).hexdigest()==orig['sha256'],'inverse original hash; not parent bytes supplied')
    with (R/'CLASS_IDENTITIES.tsv').open() as f:classes=list(csv.DictReader(f,delimiter='\t'))
    need(len(classes)==44 and len({r['relative'] for r in classes})==44,'44 unique output metadata rows')
    counts={}
    for row in classes:
        need(row['relative'] not in by,'no baseline shadow')
        need(row['relative']==row['internal_name']+'.class' and row['source_file'] in names,'output identity')
        need(re.fullmatch('[0-9a-f]{64}',row['sha256']) and int(row['bytes'])>0,'output pin')
        counts[row['source_file']]=counts.get(row['source_file'],0)+1
    facts=load('ACTUAL_FACTS.json');recipe=load('REPRODUCTION.json')
    need(counts==facts['by_source'] and sum(int(r['bytes']) for r in classes)==facts['class_bytes'],'output totals')
    need(facts['class_count']==44 and facts['source_count']==10 and facts['native_compiler_exit']==0,'narrow actual compile')
    need(facts['full_m128_passes']==0 and facts['five_block_M128_Chisel_RTL']=='0/5 unchanged','no full pass')
    need(facts['publication_compiler_or_dut_executions']==0,'no extra execution')
    need(recipe['status']=='REQUIRES_PARENT_MANUAL_RECIPE_NOT_SELF_CONTAINED' and recipe['command_template_exact_inverse_verified'],'manual requires-parent recipe')
    return dict(status='PASS_PUBLIC_SOURCE_AND_METADATA_ONLY',files=len(actual),baseline_metadata_count=len(retained),output_metadata_count=len(classes),historical_parent_sources_required=5,compiler_or_dut_executions=0,full_m128_passes=0)
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True))
