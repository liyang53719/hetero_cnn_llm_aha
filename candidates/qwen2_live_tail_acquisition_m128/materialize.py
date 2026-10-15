#!/usr/bin/env python3
"""Materialize five readonly roles from the newly verified mixed-provenance raw seal."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
RESTORE_SHA256='04a951cf15833ceb89eb14c34f5b76fa0a1df68cc8427ca035f62887ab0c7696'
restore_source=HERE/'restore.py'
if hashlib.sha256(restore_source.read_bytes()).hexdigest()!=RESTORE_SHA256:
    raise ValueError('reviewed raw verifier identity drift')
spec=importlib.util.spec_from_file_location('verified_tail_recovery',restore_source)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
a=r.a
ROOT=r.ROOT
RECIPE_ID='qwen2-tail-mixed-provenance-materialization-v1'
STATUS='FIVE_PINNED_TAIL_INPUT_ROLES_READY_NEW_RAW_IDENTITY'
# Corroborating output digests from the existing source-pinned byte transform.
# Raw pins and full independent byte-lane correspondence remain mandatory.
OUTPUT_HASHES={
 'gamma1':'e8e9d18c28e26e06d89fbb591b749cb77617e32cc17607f2b92e4b6a1828c70a',
 'wd':'90b75c3a30d975516e17cc61ba0fe2e41eff5b7d98c1cc9361b25f0d172a53ec',
 'wg':'be5cdf567f7ac2f91f63bfad26194336f4f857596716b3c365986b4ad1e5a44f',
 'wo':'69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c',
 'wu':'59f200f6eb3b67e947248d6f5f0308c28ec0256b93893342e2f27d028c80a040'}
BOUNDARIES={**a.BOUNDARIES,'materialization_executed':True,'network_used':False,
            'torch_imported':False,'numpy_imported':False}


def source_snapshot(pins):
    current=r.sources(pins)
    current[a.PACKAGE+'/materialize.py']=a.identity(HERE/'materialize.py')
    current['python_executable']=a.identity(Path(sys.executable).resolve())
    return current


def snapshot(subset,namespace,pins):
    directory,_,_=r.verify_all(subset,namespace,pins)
    inventory={}
    for path in sorted(directory.rglob('*')):
        relative=str(path.relative_to(ROOT))
        a.safe_path(ROOT,relative)
        if path.is_file():inventory[str(path.relative_to(directory))]=a.identity(path)
    return dict(sources=source_snapshot(pins),raw_files=inventory,physical_roles=pins['roles'])


def raw_values(subset,namespace,pins):
    directory=r.stage(subset)
    values={}
    for tensor in pins['tensors']:
        raw=r.child(directory,tensor['local_name']+'.bin').read_bytes()
        namespace['validate_raw_bytes'](raw,tensor)
        values[tensor['role']]=raw
    return values


def raw_manifest_identity(subset):
    relative=subset+'/'+r.SEAL
    return dict(path=relative,**a.identity(a.safe_path(ROOT,relative)))


def read_inputs(relative,subset,namespace,pins):
    directory=r.stage(relative)
    a.need(directory!=r.stage(subset),'raw/input alias')
    ready=namespace['parse'](r.child(directory,'INPUTS_READY.json').read_bytes())
    current=snapshot(subset,namespace,pins)
    expected=dict(schema=1,recipe_id=RECIPE_ID,status=STATUS,output_directory=relative,
        raw_directory=subset,raw_manifest=raw_manifest_identity(subset),model_id=pins['model_id'],
        revision=pins['revision'],pins_sha256=a.PIN_SHA256,boundaries=BOUNDARIES,
        raw_bytes=87297024,output_bytes=87300096,inverse_byte_lane_audit=True,
        raw_provenance=dict(fresh_http206_receipts=12,reused_tensors_without_http_receipts=2),
        before=current,after=current,python_version=sys.version)
    a.need(type(ready) is dict and set(ready)==set(expected)|{'created_at','roles'},'input receipt exact fields')
    namespace['fields'](ready,expected,'new input receipt')
    a.parse_time(ready['created_at'])
    a.need(type(ready['roles']) is dict and set(ready['roles'])==set(pins['roles']),'five readonly roles')
    a.need({p.name for p in directory.iterdir()}=={'INPUTS_READY.json'}|{role+'.bin' for role in pins['roles']},'input inventory')
    raw=raw_values(subset,namespace,pins)
    for role,role_spec in pins['roles'].items():
        record=ready['roles'][role]
        a.need(set(record)==set(role_spec)|{'sha256'},'exact role fields')
        namespace['fields'](record,{**role_spec,'sha256':OUTPUT_HASHES[role]},'role identity')
        data=r.child(directory,role+'.bin').read_bytes()
        a.need(len(data)==role_spec['bytes'] and a.digest(data)==OUTPUT_HASHES[role],'input byte/hash drift')
        namespace['verify_correspondence'](raw[role],data,role_spec)
    a.need(namespace['same'](current,snapshot(subset,namespace,pins)),'readback source/raw drift')
    return ready


def materialize(relative,subset,namespace,pins):
    out=r.stage(relative);raw_directory=r.stage(subset)
    a.need(not out.exists(),'fresh materialization output required')
    a.need(not out.is_relative_to(raw_directory) and not raw_directory.is_relative_to(out),'input/output overlap')
    before=snapshot(subset,namespace,pins)
    raw=raw_values(subset,namespace,pins)
    widen,transpose=namespace['conversion_functions'](ROOT,pins)
    outputs,records={},{}
    for role,role_spec in pins['roles'].items():
        a.need(role_spec['readonly'] is True,'readonly role required')
        data=widen(raw[role]) if role_spec['widened'] else transpose(raw[role],*role_spec['source_shape'])
        namespace['verify_correspondence'](raw[role],data,role_spec)
        a.need(a.digest(data)==OUTPUT_HASHES[role],'corroborating output hash drift')
        outputs[role]=data;records[role]={**role_spec,'sha256':a.digest(data)}
    a.need(namespace['same'](before,snapshot(subset,namespace,pins)),'source/raw drift before output')
    out.parent.mkdir(parents=True,exist_ok=True);out=r.stage(relative);out.mkdir(exist_ok=False)
    for role,data in outputs.items():
        a.write_new(out/(role+'.bin'),data)
        a.need(a.identity(out/(role+'.bin'))==dict(bytes=len(data),sha256=OUTPUT_HASHES[role]),'written role readback')
    after=snapshot(subset,namespace,pins)
    a.need(namespace['same'](before,after),'source/raw drift during output')
    ready=dict(schema=1,recipe_id=RECIPE_ID,status=STATUS,output_directory=relative,
        raw_directory=subset,raw_manifest=raw_manifest_identity(subset),model_id=pins['model_id'],
        revision=pins['revision'],pins_sha256=a.PIN_SHA256,boundaries=BOUNDARIES,
        raw_bytes=87297024,output_bytes=87300096,inverse_byte_lane_audit=True,
        raw_provenance=dict(fresh_http206_receipts=12,reused_tensors_without_http_receipts=2),
        before=before,after=after,python_version=sys.version,created_at=a.stamp(),roles=records)
    a.write_new(out/'INPUTS_READY.json',a.encode(ready))
    return dict(status=STATUS,out=relative,roles=5,bytes=87300096,
        manifest_sha256=a.digest((out/'INPUTS_READY.json').read_bytes()))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','materialize','audit'),default='check')
    p.add_argument('--execute',action='store_true');p.add_argument('--subset');p.add_argument('--out');p.add_argument('--inputs')
    args=p.parse_args(argv)
    if args.action=='check':a.need(not any((args.execute,args.subset,args.out,args.inputs)),'cold flags')
    else:
        a.need(args.execute and args.subset,'execute and verified raw subset required')
        a.need(bool(args.out)==(args.action=='materialize') and bool(args.inputs)==(args.action=='audit'),'exact action paths')
    namespace,pins=a.load_contract()
    if args.action=='check':result=dict(status='NOT_EXECUTED',cold_check='PASS',network_used=False,raw_read=False,outputs_written=False)
    elif args.action=='materialize':result=materialize(args.out,args.subset,namespace,pins)
    else:
        ready=read_inputs(args.inputs,args.subset,namespace,pins)
        result=dict(status='VERIFIED_FIVE_NEW_TAIL_ROLES_BYTE_CORRESPONDENCE_ONLY',inputs=args.inputs,
            roles=len(ready['roles']),bytes=sum(v['bytes'] for v in ready['roles'].values()),
            manifest_sha256=a.digest(r.child(r.stage(args.inputs),'INPUTS_READY.json').read_bytes()))
    print(json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,ImportError) as error:
        print(json.dumps(dict(status='REJECTED',reason=str(error))),file=sys.stderr,flush=True)
        raise SystemExit(2)
