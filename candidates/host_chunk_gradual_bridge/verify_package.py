#!/usr/bin/env python3
"""Verify this source/metadata package only; never execute compiler or DUT."""
from pathlib import Path, PurePosixPath
import csv, hashlib, json, re

HERE=Path(__file__).resolve().parent
def require(value,message):
    if not value: raise ValueError(message)
def load(name): return json.loads((HERE/name).read_text())
def identity(data): return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def verify():
    manifest=load('MANIFEST.json');expected=manifest['files']
    actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file()}
    require(actual==set(expected)|{'MANIFEST.json'},'exact file allowlist')
    total=0
    for name,row in expected.items():
        rel=PurePosixPath(name);p=HERE/name
        require(not rel.is_absolute() and '..' not in rel.parts,'relative path')
        require(not p.is_symlink(),'no symlink')
        data=p.read_bytes();data.decode('utf-8')
        require(identity(data)==row,'file hash '+name)
        require(p.suffix in {'.md','.json','.py','.scala','.tsv'},'text/source only')
        require(b'\0' not in data and not data.startswith(b'\x7fELF'),'no binary')
        require(b'/work'+b'space/' not in data and b'/home/'+b'agent/' not in data,'no private runtime paths')
        require(len(data)<128*1024,'per-file cap')
        total+=len(data)
    require(total<300*1024,'small package cap')
    src=load('SOURCE_PINS.json')['sources'];require(len(src)==4,'four sources')
    for row in src:
        require(row['byte_identical_to_actual_compiler_input'],'unmodified source')
        require(identity((HERE/row['path']).read_bytes())=={k:row[k] for k in ('bytes','sha256')},'actual source pin')
    with (HERE/'BASELINE_CLASS_PINS.tsv').open() as f: baseline=list(csv.DictReader(f,delimiter='\t'))
    require(len(baseline)==903 and len({r['relative'] for r in baseline})==903,'903 unique classes')
    for row in baseline:
        rel=PurePosixPath(row['relative'])
        require(not rel.is_absolute() and '..' not in rel.parts and rel.suffix=='.class','relative class identity')
        require(int(row['bytes'])>0 and re.fullmatch('[0-9a-f]{64}',row['sha256']),'class metadata')
    scope=load('CLASS_SCOPE.json');deps=load('DEPENDENCY_PINS.json');facts=load('ACTUAL_FACTS.json')
    require(len(scope['removed_replaced9'])==9 and len(scope['added_unchanged8'])==8 and len(scope['new_actual17'])==17,'class composition')
    require(904-9+8==len(baseline),'baseline composition arithmetic')
    require(not ({r['relative'] for r in baseline}&{r['relative'] for r in scope['new_actual17']}),'no shadowed baseline')
    require(sum(int(r['bytes']) for r in baseline)==deps['baseline']['bytes'],'baseline bytes')
    require(len(deps['ordered_classpath'])==106,'106 ordered JAR identities')
    require(deps['status']=='REQUIRES_PARENT_NOT_SELF_CONTAINED' and not deps['baseline']['source_build_closure_included'],'requires parent')
    require(facts['class_count']==17 and facts['source_count']==4 and facts['native_compiler_exit']==0 and facts['outer_tool_exit']==0,'actual narrow compile')
    require(facts['full_m128_passes']==0 and facts['five_block_M128_Chisel_RTL']=='0/5 unchanged','no full pass')
    require(facts['packaging_compiler_or_dut_executions']==0,'no new compile')
    recipe=load('REPRODUCTION.json')
    require(recipe['status']=='REQUIRES_PARENT_MANUAL_RECIPE_NOT_SELF_CONTAINED','manual recipe')
    require(recipe['argv_template'].count('scala.tools.nsc.Main')==1,'compiler entry only')
    return {'status':'PASS_PUBLIC_PACKAGE_ONLY','files':len(actual),'bytes':total+(HERE/'MANIFEST.json').stat().st_size,'four_sources_unchanged':True,'requires_parent':True,'five_block_M128_Chisel_RTL':'0/5 unchanged','compiler_or_dut_executions':0}
if __name__=='__main__':print(json.dumps(verify(),sort_keys=True))
