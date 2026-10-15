"""Explicit all-fresh14 tail consumer. Metadata reader never opens operand bytes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
ACQUIRE='candidates/qwen2_live_tail_acquisition_m128/acquire.py'
ACQUIRE_SHA='b63259ae7c3118eae9d221202ae33dc9732587b78b58a9a1538052a2a03bcb93'
SOURCE='candidates/qwen2_fullblock_ci_prepare/fresh_tail.py'
RECIPE='qwen2-all-fresh14-materialization-v1'
OUTPUT_HASHES={
 'gamma1':'e8e9d18c28e26e06d89fbb591b749cb77617e32cc17607f2b92e4b6a1828c70a',
 'wd':'90b75c3a30d975516e17cc61ba0fe2e41eff5b7d98c1cc9361b25f0d172a53ec',
 'wg':'be5cdf567f7ac2f91f63bfad26194336f4f857596716b3c365986b4ad1e5a44f',
 'wo':'69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c',
 'wu':'59f200f6eb3b67e947248d6f5f0308c28ec0256b93893342e2f27d028c80a040'}

def need(ok,message):
    if not ok: raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def contract(root=ROOT):
    root=Path(root);p=root/ACQUIRE
    need(p.resolve()==p and sha(p.read_bytes())==ACQUIRE_SHA,'fixed acquisition source drift')
    spec=importlib.util.spec_from_file_location('_allfresh_tail_acquire',p)
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    n,pins=a.load_contract(root)
    return a,n,pins

def validate_manifest(m,relative,n,pins,current,a):
    expected=dict(schema=1,status=a.STATUS,acquisition='fresh_HTTP206',model_id=pins['model_id'],
        revision=pins['revision'],pins_sha256=a.PIN_SHA256,output_directory=relative,
        payload_bytes=87297024,http_range_count=14,boundaries=a.BOUNDARIES)
    need(type(m) is dict and set(m)==set(expected)|{'started_at','completed_at','before','after','tensors'},'manifest fields')
    n['fields'](m,expected,'fresh14 manifest')
    need(n['same'](m['before'],current) and n['same'](m['after'],current),'acquisition source boundary')
    start,end=a.parse_time(m['started_at']),a.parse_time(m['completed_at'])
    need(start<=end,'acquisition interval')
    need(type(m['tensors']) is list and len(m['tensors'])==5,'five tensor records')
    count=0
    for entry,tensor in zip(m['tensors'],pins['tensors']):
        need(type(entry) is dict and set(entry)==set(tensor)|{'file','http_ranges'},'tensor fields')
        n['fields'](entry,tensor,'fixed tensor')
        need(entry['file']==tensor['local_name']+'.bin','fixed tensor filename')
        receipts=entry['http_ranges']
        need(type(receipts) is list and len(receipts)==len(tensor['segments']),'fresh range coverage')
        for receipt,segment in zip(receipts,tensor['segments']):
            n['verify_http'](receipt,segment,pins)
            need(start<=a.parse_time(receipt['acquired_at'])<=end,'fresh receipt interval')
            count+=1
    need(count==14,'fourteen actual receipt records required')
    return m

def metadata(root,subset,seal_sha256):
    """Only source/manifest reads and raw stat; caller must supply reviewed seal digest."""
    need(type(seal_sha256) is str and re.fullmatch('[0-9a-f]{64}',seal_sha256),'reviewed raw seal digest required')
    a,n,pins=contract(root);directory=a.stage_path(root,subset)
    seal=a.safe_path(root,subset+'/'+a.SEAL);raw=seal.read_bytes()
    need(sha(raw)==seal_sha256,'reviewed fresh acquisition seal drift')
    current=a.snapshot(root,pins)
    m=validate_manifest(n['parse'](raw),subset,n,pins,current,a)
    need({p.name for p in directory.iterdir()}=={a.SEAL}|{t['local_name']+'.bin' for t in pins['tensors']},'raw inventory')
    for t in pins['tensors']:
        p=a.safe_path(root,subset+'/'+t['local_name']+'.bin')
        need(p.is_file() and p.stat().st_size==t['bytes'],'raw stat size')
    need(n['same'](current,a.snapshot(root,pins)),'source drift during metadata read')
    return dict(status='FRESH14_METADATA_VERIFIED_PAYLOAD_NOT_READ',manifest=m,manifest_sha256=seal_sha256,
        raw_payloads_read=False,proof_files={str(seal.relative_to(root)):dict(bytes=len(raw),sha256=seal_sha256)})

def audit_raw(root,subset,seal_sha256):
    record=metadata(root,subset,seal_sha256)
    a,n,pins=contract(root)
    full=a.read_new(root,subset,n,pins)
    need(full['manifest_sha256']==seal_sha256,'full audit seal identity')
    return {**record,'status':'FRESH14_RAW_PAYLOADS_VERIFIED','raw_payloads_read':True,
        'full_audit':full}

def materialize(root,subset,out,seal_sha256):
    a,n,pins=contract(root)
    record=audit_raw(root,subset,seal_sha256)
    source_before={**a.snapshot(root,pins),SOURCE:a.identity(root/SOURCE)}
    output=a.stage_path(root,out);directory=a.stage_path(root,subset)
    need(not output.exists() and not output.is_relative_to(directory) and not directory.is_relative_to(output),'fresh disjoint output')
    widen,transpose=n['conversion_functions'](root,pins)
    outputs={}
    for tensor in pins['tensors']:
        role=tensor['role'];spec=pins['roles'][role]
        raw=a.safe_path(root,subset+'/'+tensor['local_name']+'.bin').read_bytes()
        n['validate_raw_bytes'](raw,tensor)
        data=widen(raw) if spec['widened'] else transpose(raw,*spec['source_shape'])
        n['verify_correspondence'](raw,data,spec)
        need(len(data)==spec['bytes'] and sha(data)==OUTPUT_HASHES[role],'typed role byte/hash')
        outputs[role]=data
    need(source_before=={**a.snapshot(root,pins),SOURCE:a.identity(root/SOURCE)},'transform source drift')
    audit_raw(root,subset,seal_sha256)
    output.parent.mkdir(parents=True,exist_ok=True);output.mkdir(exist_ok=False)
    for role,data in outputs.items():
        a.write_new(output/(role+'.bin'),data)
        need(a.identity(output/(role+'.bin'))==dict(bytes=len(data),sha256=OUTPUT_HASHES[role]),'typed write readback')
    audit_raw(root,subset,seal_sha256)
    need(source_before=={**a.snapshot(root,pins),SOURCE:a.identity(root/SOURCE)},'source drift during output')
    ready=dict(schema=1,recipe_id=RECIPE,status='FIVE_ALL_FRESH_TAIL_ROLES_READY',
        subset=subset,output=out,raw_seal_sha256=seal_sha256,pins_sha256=a.PIN_SHA256,
        fresh_http206_receipts=14,reused_tensors=0,created_at=a.stamp(),sources=source_before,
        roles={role:{**pins['roles'][role],'sha256':OUTPUT_HASHES[role]} for role in outputs},
        model_executed=False,rtl_executed=False,old_pass_inherited=False)
    need(a.parse_time(ready['created_at'])>=a.parse_time(record['manifest']['completed_at']),'creation timestamp')
    a.write_new(output/'INPUTS_READY.json',a.encode(ready))
    return ready


def input_metadata(root,out,ready_sha256,seal_sha256):
    """Read exactly pinned input metadata and stat roles, never typed/raw payloads."""
    need(type(ready_sha256) is str and re.fullmatch('[0-9a-f]{64}',ready_sha256),'reviewed input digest required')
    a,n,pins=contract(root);directory=a.stage_path(root,out)
    raw=a.safe_path(root,out+'/INPUTS_READY.json').read_bytes()
    need(sha(raw)==ready_sha256,'reviewed input metadata drift')
    ready=n['parse'](raw)
    expected=dict(schema=1,recipe_id=RECIPE,status='FIVE_ALL_FRESH_TAIL_ROLES_READY',output=out,
        raw_seal_sha256=seal_sha256,pins_sha256=a.PIN_SHA256,fresh_http206_receipts=14,
        reused_tensors=0,sources={**a.snapshot(root,pins),SOURCE:a.identity(root/SOURCE)},
        roles={role:{**spec,'sha256':OUTPUT_HASHES[role]} for role,spec in pins['roles'].items()},
        model_executed=False,rtl_executed=False,old_pass_inherited=False)
    need(type(ready) is dict and set(ready)==set(expected)|{'subset','created_at'},'input metadata fields')
    n['fields'](ready,expected,'fresh14 input metadata')
    source=metadata(root,ready['subset'],seal_sha256)
    need(a.parse_time(ready['created_at'])>=a.parse_time(source['manifest']['completed_at']),'input creation interval')
    need({p.name for p in directory.iterdir()}=={'INPUTS_READY.json'}|{role+'.bin' for role in pins['roles']},'typed inventory')
    for role,spec in pins['roles'].items():
        p=a.safe_path(root,out+'/'+role+'.bin')
        need(p.is_file() and p.stat().st_size==spec['bytes'],'typed stat size')
    return dict(status='FRESH14_INPUT_METADATA_VERIFIED_PAYLOAD_NOT_READ',ready=ready,
        raw_payloads_read=False,typed_payloads_read=False,
        proof_files={**source['proof_files'],out+'/INPUTS_READY.json':dict(bytes=len(raw),sha256=ready_sha256)})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','metadata','audit','materialize'),default='check')
    p.add_argument('--execute',action='store_true');p.add_argument('--subset');p.add_argument('--out');p.add_argument('--seal-sha256')
    x=p.parse_args()
    if x.action=='check':
        need(not any((x.execute,x.subset,x.out,x.seal_sha256)),'cold flags')
        contract();result=dict(status='NOT_EXECUTED',raw_payloads_read=False)
    else:
        need(x.execute and x.subset and x.seal_sha256 and bool(x.out)==(x.action=='materialize'),'exact action arguments')
        result=materialize(ROOT,x.subset,x.out,x.seal_sha256) if x.action=='materialize' else \
            (metadata if x.action=='metadata' else audit_raw)(ROOT,x.subset,x.seal_sha256)
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
