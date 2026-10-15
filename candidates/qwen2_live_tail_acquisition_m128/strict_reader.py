#!/usr/bin/env python3
"""Independent strict read-only validation of the unchanged recovery provenance."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RAW='work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/raw'
INPUTS='work/qwen2_live_tail_segment_recovery_m128/recovered_20261015_0027/inputs'
REUSE_SOURCE='work/qwen2_live_tail_acquisition_m128/recovered_20261015_0020/raw'
LEGACY_SOURCE_SHA256={
 'acquire.py':'b63259ae7c3118eae9d221202ae33dc9732587b78b58a9a1538052a2a03bcb93',
 'restore.py':'04a951cf15833ceb89eb14c34f5b76fa0a1df68cc8427ca035f62887ab0c7696',
 'materialize.py':'eb502ae268020e35f96dd6714de5ce471679162364bf5a48b29738b7c61a10da'}
METADATA_SHA256={
 RAW+'/RECOVERY_STATE.json':'681976b01d3c927a63d626348c3996deb3894510cb4b545c67f4f80c5abcdd7f',
 RAW+'/RAW_READY.json':'5e01469f36e53a1a7854aa28e0b382246c4bf80812b796854e64bef62eb3fa7b',
 INPUTS+'/INPUTS_READY.json':'f52b57f5331e04a95abcd235e036f5d2035f12c8b947f27b4b1d1f5d9060aca2'}


class Rejected(ValueError):pass


def need(ok,message):
    if not ok:raise Rejected(message)


def same(a,b):
    if type(a) is not type(b):return False
    if type(b) is dict:return a.keys()==b.keys() and all(same(a[k],b[k]) for k in b)
    if type(b) is list:return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b


def fields(value,expected,label):
    need(type(value) is dict and all(k in value and same(value[k],v) for k,v in expected.items()),
         label+' field/type/identity mismatch')


def utc(value):
    need(type(value) is str,'UTC timestamp string required')
    try:time=dt.datetime.fromisoformat(value)
    except ValueError as error:raise Rejected('invalid UTC timestamp') from error
    need(time.utcoffset()==dt.timedelta(0),'UTC timestamp required')
    return time


def canonical_reuse_directory(value):
    need(type(value) is str and bool(re.fullmatch(
        r'work/qwen2_live_tail_acquisition_m128/[A-Za-z0-9][A-Za-z0-9_-]{0,63}/[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value)),
        'canonical original fresh-acquisition namespace/run/stage required')
    need(value==REUSE_SOURCE,'this recovery original source directory identity')
    return value


def validate_provenance(state,ready,pins,inputs=None):
    """Pure metadata validation: no filesystem, payload reads, writes or network."""
    created=utc(state['created_at']);completed=utc(ready['completed_at'])
    need(completed>=created,'raw completion predates recovery state')
    need(type(state['reused']) is list and len(state['reused'])==2,'exactly two reuse records')
    need(type(ready['tensors']) is list and len(ready['tensors'])==5,'exactly five raw records')
    fields(ready,dict(payload_bytes=87297024,verified_segment_hashes=14,
        fresh_http206_receipts=12,reused_tensors_without_http_receipts=2),'raw provenance counts')
    reused={}
    directories=[]
    for record,tensor in zip(state['reused'],pins['tensors'][:2]):
        name=tensor['local_name']+'.bin'
        expected=dict(role=tensor['role'],file=name,bytes=tensor['bytes'],sha256=tensor['sha256'],
            provenance='hash_verified_local_copy_from_incomplete_attempt',source_file=name,
            http_receipts_available=False,http_acquired_at=None)
        need(type(record) is dict and set(record)==set(expected)|{'source_directory','copied_at'},
             'exact reuse record fields required')
        fields(record,expected,'reused tensor')
        directories.append(canonical_reuse_directory(record['source_directory']))
        need(utc(record['copied_at'])<=created,'copy occurs after recovery state creation')
        reused[tensor['role']]=record
    need(len(set(directories))==1,'both reused tensors must have the same original directory')
    receipts=[]
    for record,tensor in zip(ready['tensors'],pins['tensors']):
        need(type(record) is dict and set(record)==set(tensor)|{'file','provenance','http_ranges'},
             'exact raw tensor record fields')
        fields(record,{**tensor,'file':tensor['local_name']+'.bin'},'raw tensor')
        if tensor['role'] in reused:
            need(same(record['provenance'],reused[tensor['role']]),'ready/state reuse provenance differs')
            need(same(record['http_ranges'],[]),'reused tensor cannot claim HTTP receipts')
            continue
        need(same(record['provenance'],dict(provenance='fresh_HTTP206',http_receipts_available=True)),
             'fresh tensor provenance fields')
        need(type(record['http_ranges']) is list and len(record['http_ranges'])==len(tensor['segments']),
             'fresh tensor receipt coverage')
        for receipt,segment in zip(record['http_ranges'],tensor['segments']):
            expected=dict(requested_url=pins['shard']['url'],
                request_range=f"bytes={segment['start']}-{segment['end']}",status=206,
                content_range=f"bytes {segment['start']}-{segment['end']}/{pins['shard']['checkpoint_file_bytes']}",
                bytes=segment['bytes'],sha256=segment['sha256'])
            need(type(receipt) is dict and set(receipt)==set(expected)|{'acquired_at'},'exact fresh HTTP receipt fields')
            fields(receipt,expected,'fresh HTTP receipt')
            acquired=utc(receipt['acquired_at'])
            need(created<=acquired<=completed,'fresh HTTP receipt outside recovery interval')
            receipts.append(receipt)
    need(len(receipts)==12,'exact 12 fresh HTTP206 receipts')
    if inputs is not None:
        need(utc(inputs['created_at'])>=completed,'inputs creation predates raw completion')
        fields(inputs,dict(raw_provenance=dict(fresh_http206_receipts=12,reused_tensors_without_http_receipts=2)),
               'input provenance')
    return dict(status='STRICT_MIXED_PROVENANCE_METADATA_VERIFIED',
        verification_scope='metadata_only_no_tensor_payload_read',reused_records_verified=2,
        fresh_http206_receipts=12,time_chain_verified=True,
        historical_http_receipts_reconstructed=False)


def load_contract():
    for name,expected in LEGACY_SOURCE_SHA256.items():
        path=HERE/name
        need(not path.is_symlink() and path.is_file(),'regular legacy source required')
        need(hashlib.sha256(path.read_bytes()).hexdigest()==expected,'unchanged legacy source hash: '+name)
    spec=importlib.util.spec_from_file_location('unchanged_tail_materializer',HERE/'materialize.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    namespace,pins=module.a.load_contract()
    return module,namespace,pins


def verify_metadata(raw_relative=RAW,inputs_relative=INPUTS,*,include_inputs=True):
    """Reads frozen JSON and source metadata only; never reads/stat-walks tensor payloads."""
    need(raw_relative==RAW and inputs_relative==INPUTS,'fixed recovery identity required')
    module,namespace,pins=load_contract()
    paths=[RAW+'/RECOVERY_STATE.json',RAW+'/RAW_READY.json']
    if include_inputs:paths.append(INPUTS+'/INPUTS_READY.json')
    values=[]
    for relative in paths:
        data=module.a.safe_path(ROOT,relative).read_bytes()
        need(hashlib.sha256(data).hexdigest()==METADATA_SHA256[relative],'unchanged original receipt hash: '+relative)
        values.append(namespace['parse'](data))
    state,ready=values[:2];inputs=values[2] if include_inputs else None
    result=validate_provenance(state,ready,pins,inputs)
    return dict(result=result,state=state,raw=ready,inputs=inputs)


def read_raw(raw_relative=RAW):
    """Full payload hash audit plus strict original provenance metadata."""
    before=verify_metadata(raw_relative,include_inputs=False)
    module,namespace,pins=load_contract()
    result=module.r.verify_all(raw_relative,namespace,pins)
    after=verify_metadata(raw_relative,include_inputs=False)
    need(same(before,after),'strict metadata changed during full raw audit')
    return result


def read_inputs(inputs_relative=INPUTS,raw_relative=RAW):
    """Full raw/input hash and byte-lane audit; returns the unchanged INPUTS_READY dict."""
    before=verify_metadata(raw_relative,inputs_relative)
    module,namespace,pins=load_contract()
    ready=module.read_inputs(inputs_relative,raw_relative,namespace,pins)
    after=verify_metadata(raw_relative,inputs_relative)
    need(same(before,after) and same(ready,after['inputs']),'strict metadata changed during full input audit')
    return ready


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','metadata','raw-audit','inputs-audit'),default='check')
    p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    need(args.execute==(args.action!='check'),'explicit execute required only for receipt/payload reads')
    if args.action=='check':
        load_contract()
        result=dict(status='NOT_EXECUTED',cold_check='PASS',receipt_read=False,payload_read=False,network_used=False,outputs_written=False)
    elif args.action=='metadata':result=verify_metadata()['result']
    elif args.action=='raw-audit':
        read_raw();result=dict(status='STRICT_RAW_PROVENANCE_AND_FULL_PAYLOAD_VERIFIED',payload_read=True,network_used=False,outputs_written=False)
    else:
        ready=read_inputs();result=dict(status='STRICT_INPUT_PROVENANCE_AND_FULL_BYTE_CORRESPONDENCE_VERIFIED',
            payload_read=True,roles=len(ready['roles']),network_used=False,outputs_written=False)
    print(json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,ImportError) as error:
        print(json.dumps(dict(status='REJECTED',reason=str(error))),file=sys.stderr,flush=True)
        raise SystemExit(2)
