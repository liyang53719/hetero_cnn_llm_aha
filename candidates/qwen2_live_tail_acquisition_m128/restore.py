#!/usr/bin/env python3
"""Bounded per-segment recovery; pinned local reuse has explicitly missing HTTP receipts."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fresh_tail_acquisition',HERE/'acquire.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
ROOT=a.ROOT
PREFIX='work/qwen2_live_tail_segment_recovery_m128'
STATE='RECOVERY_STATE.json'
SEAL='RAW_READY.json'
REUSED_ROLES=('wo','gamma1')
STATUS='PINNED_TAIL_RAW_READY_MIXED_PROVENANCE_NO_MODEL_EXECUTION'


def stage(relative):
    path=a.safe_path(ROOT,relative)
    parts=relative.split('/')
    a.need(len(parts)==4 and '/'.join(parts[:2])==PREFIX and
        all(a.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',p) for p in parts[2:]),'recovery namespace/run/stage')
    return path


def sources(pins):
    result=a.snapshot(ROOT,pins)
    result[a.PACKAGE+'/restore.py']=a.identity(HERE/'restore.py')
    return result


def child(out,name):
    return a.safe_path(ROOT,str(out.relative_to(ROOT))+'/'+name)


def segments(pins):
    return [(t,s) for t in pins['tensors'] for s in t['segments']]


def state_read(relative,namespace,pins):
    out=stage(relative)
    state=namespace['parse'](child(out,STATE).read_bytes())
    expected=dict(schema=1,status='INCOMPLETE_RECOVERY_STATE',output_directory=relative,
                  pins_sha256=a.PIN_SHA256,model_id=pins['model_id'],revision=pins['revision'])
    a.need(type(state) is dict and set(state)==set(expected)|{'created_at','sources','reused'},'state fields')
    namespace['fields'](state,expected,'recovery state')
    a.parse_time(state['created_at'])
    a.need(namespace['same'](state['sources'],sources(pins)),'recovery source drift')
    a.need(type(state['reused']) is list and len(state['reused'])==2,'two reused tensors')
    for entry,tensor in zip(state['reused'],pins['tensors'][:2]):
        a.need(entry['role']==tensor['role'] and entry['role'] in REUSED_ROLES,'reused role')
        a.need(entry['provenance']=='hash_verified_local_copy_from_incomplete_attempt' and
               entry['http_receipts_available'] is False and entry['http_acquired_at'] is None,
               'reuse cannot claim HTTP receipt/time')
        namespace['validate_raw_bytes'](child(out,tensor['local_name']+'.bin').read_bytes(),tensor)
    return out,state


def initialize(relative,incomplete,namespace,pins):
    out=stage(relative)
    a.need(not out.exists(),'fresh output required')
    source=a.stage_path(ROOT,incomplete)
    a.need(not (source/a.SEAL).exists(),'only explicitly incomplete attempt reuse')
    expected_names={t['local_name']+'.bin' for t in pins['tensors'][:2]}
    a.need({p.name for p in source.iterdir()}==expected_names,'incomplete source inventory changed')
    values=[]
    for tensor in pins['tensors'][:2]:
        name=tensor['local_name']+'.bin'
        data=a.safe_path(ROOT,incomplete+'/'+name).read_bytes()
        namespace['validate_raw_bytes'](data,tensor)
        values.append((tensor,name,data))
    before=sources(pins)
    out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(exist_ok=False)
    (out/'segments').mkdir(exist_ok=False)
    reused=[]
    for tensor,name,data in values:
        a.write_new(out/name,data)
        reused.append(dict(role=tensor['role'],file=name,bytes=len(data),sha256=a.digest(data),
            provenance='hash_verified_local_copy_from_incomplete_attempt',source_directory=incomplete,
            source_file=name,http_receipts_available=False,http_acquired_at=None,copied_at=a.stamp()))
    a.need({p.name for p in source.iterdir()}==expected_names,'incomplete source inventory changed during copy')
    for tensor,name,data in values:
        a.need(a.identity(source/name)==dict(bytes=len(data),sha256=a.digest(data)),'reuse source changed')
    a.need(namespace['same'](before,sources(pins)),'source changed during initialization')
    state=dict(schema=1,status='INCOMPLETE_RECOVERY_STATE',output_directory=relative,
        pins_sha256=a.PIN_SHA256,model_id=pins['model_id'],revision=pins['revision'],
        created_at=a.stamp(),sources=before,reused=reused)
    a.write_new(out/STATE,a.encode(state))
    return dict(status='LOCAL_REUSE_READY_12_HTTP_RANGES_PENDING',out=relative,reused_roles=list(REUSED_ROLES),
                reused_bytes=sum(len(data) for _,_,data in values),historical_http_receipts_reconstructed=False)


def read_segment(out,index,segment,namespace,pins):
    name=f'{index:02d}'
    raw=child(out,'segments/'+name+'.bin').read_bytes()
    receipt=namespace['parse'](child(out,'segments/'+name+'.json').read_bytes())
    namespace['verify_http'](receipt,segment,pins)
    a.need(len(raw)==segment['bytes'] and a.digest(raw)==segment['sha256'],'persisted segment bytes/hash')
    return raw,receipt


def fetch(relative,index,namespace,pins):
    out,state=state_read(relative,namespace,pins)
    a.need(type(index) is int and 2<=index<14,'only missing pinned segment indices 2..13')
    a.need(not (out/SEAL).exists(),'completed recovery is immutable')
    tensor,segment=segments(pins)[index]
    raw_path=child(out,f'segments/{index:02d}.bin');receipt_path=child(out,f'segments/{index:02d}.json')
    if receipt_path.exists():
        read_segment(out,index,segment,namespace,pins)
        return dict(status='ALREADY_VERIFIED_SEGMENT',index=index,network_used=False)
    # Exactly one bounded official request. Caller applies an outer hard timeout.
    # If an interrupted call wrote bytes but no receipt, fetch fresh proof again;
    # reuse only the identical hash-pinned bytes and never fabricate that proof.
    raw,receipt=a.download(segment,pins)
    namespace['verify_http'](receipt,segment,pins)
    if raw_path.exists():
        a.need(a.identity(raw_path)==dict(bytes=segment['bytes'],sha256=segment['sha256']),
               'partial segment differs from pins')
    else:
        a.write_new(raw_path,raw)
    a.need(namespace['same'](state['sources'],sources(pins)),'source drift during segment fetch')
    a.write_new(receipt_path,a.encode(receipt))
    read_segment(out,index,segment,namespace,pins)
    return dict(status='PINNED_SEGMENT_HTTP206_READY',index=index,role=tensor['role'],
        bytes=len(raw),sha256=a.digest(raw),acquired_at=receipt['acquired_at'],network_used=True)


def verify_all(relative,namespace,pins,seal_required=True):
    out,state=state_read(relative,namespace,pins)
    expected_segments={f'{i:02d}{suffix}' for i in range(2,14) for suffix in ('.bin','.json')}
    a.need({p.name for p in child(out,'segments').iterdir()}==expected_segments,'12 exact persisted ranges required')
    records=[]
    flat=segments(pins)
    for tensor in pins['tensors']:
        raw=child(out,tensor['local_name']+'.bin').read_bytes()
        namespace['validate_raw_bytes'](raw,tensor)
        if tensor['role'] in REUSED_ROLES:
            provenance=next(r for r in state['reused'] if r['role']==tensor['role'])
            receipts=[]
        else:
            receipts=[]
            for index,(candidate,segment) in enumerate(flat):
                if candidate['role']!=tensor['role']:continue
                segment_raw,receipt=read_segment(out,index,segment,namespace,pins)
                offset=segment['start']-tensor['start']
                a.need(raw[offset:offset+segment['bytes']]==segment_raw,'assembled range mismatch')
                a.need(a.parse_time(receipt['acquired_at'])>=a.parse_time(state['created_at']),'new HTTP receipt predates state')
                receipts.append(receipt)
            provenance=dict(provenance='fresh_HTTP206',http_receipts_available=True)
        records.append({**tensor,'file':tensor['local_name']+'.bin','provenance':provenance,'http_ranges':receipts})
    required={STATE,'segments'}|{t['local_name']+'.bin' for t in pins['tensors']}
    if seal_required:required.add(SEAL)
    a.need({p.name for p in out.iterdir()}==required,'unexpected recovery inventory')
    a.need(namespace['same'](state['sources'],sources(pins)),'final source drift')
    if seal_required:
        ready=namespace['parse'](child(out,SEAL).read_bytes())
        expected=dict(schema=1,status=STATUS,output_directory=relative,model_id=pins['model_id'],
            revision=pins['revision'],pins_sha256=a.PIN_SHA256,payload_bytes=87297024,
            verified_segment_hashes=14,fresh_http206_receipts=12,reused_tensors_without_http_receipts=2,
            boundaries=a.BOUNDARIES,sources=state['sources'],tensors=records,
            state_sha256=a.digest(child(out,STATE).read_bytes()))
        a.need(set(ready)==set(expected)|{'completed_at'},'ready exact fields')
        namespace['fields'](ready,expected,'ready receipt')
        a.parse_time(ready['completed_at'])
    return out,state,records


def finalize(relative,namespace,pins):
    out,state=state_read(relative,namespace,pins)
    a.need(not (out/SEAL).exists(),'already sealed')
    flat=segments(pins)
    for tensor in pins['tensors'][2:]:
        raw=bytearray()
        for index,(candidate,segment) in enumerate(flat):
            if candidate['role']==tensor['role']:
                part,_=read_segment(out,index,segment,namespace,pins);raw.extend(part)
        namespace['validate_raw_bytes'](bytes(raw),tensor)
        path=child(out,tensor['local_name']+'.bin')
        if path.exists():a.need(a.identity(path)==dict(bytes=tensor['bytes'],sha256=tensor['sha256']),'existing assembled tensor mismatch')
        else:a.write_new(path,raw)
    out,state,records=verify_all(relative,namespace,pins,seal_required=False)
    ready=dict(schema=1,status=STATUS,output_directory=relative,model_id=pins['model_id'],
        revision=pins['revision'],pins_sha256=a.PIN_SHA256,payload_bytes=87297024,
        verified_segment_hashes=14,fresh_http206_receipts=12,reused_tensors_without_http_receipts=2,
        boundaries=a.BOUNDARIES,sources=state['sources'],tensors=records,
        state_sha256=a.digest(child(out,STATE).read_bytes()),completed_at=a.stamp())
    a.write_new(out/SEAL,a.encode(ready))
    verify_all(relative,namespace,pins)
    return dict(status=STATUS,out=relative,payload_bytes=87297024,fresh_http206_receipts=12,
        reused_tensors_without_http_receipts=2,manifest_sha256=a.digest(child(out,SEAL).read_bytes()))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','init','segment','finalize','audit'),default='check')
    p.add_argument('--execute',action='store_true');p.add_argument('--download',action='store_true')
    p.add_argument('--out');p.add_argument('--reuse-incomplete');p.add_argument('--index',type=int)
    args=p.parse_args(argv)
    if args.action=='check':a.need(not any((args.execute,args.download,args.out,args.reuse_incomplete,args.index is not None)),'cold flags')
    else:
        a.need(args.execute and args.out,'explicit execute and output required')
        a.need(bool(args.download)==(args.action=='segment'),'download only and required for segment')
        a.need((args.index is not None)==(args.action=='segment'),'segment index required only for segment')
        a.need(bool(args.reuse_incomplete)==(args.action=='init'),'reuse source required only for init')
    namespace,pins=a.load_contract()
    if args.action=='check':result=dict(status='NOT_EXECUTED',cold_check='PASS',raw_read=False,network_used=False,outputs_written=False)
    elif args.action=='init':result=initialize(args.out,args.reuse_incomplete,namespace,pins)
    elif args.action=='segment':result=fetch(args.out,args.index,namespace,pins)
    elif args.action=='finalize':result=finalize(args.out,namespace,pins)
    else:
        out,_,_=verify_all(args.out,namespace,pins)
        result=dict(status='VERIFIED_MIXED_PROVENANCE_TAIL_RAW_ONLY',out=args.out,
                    manifest_sha256=a.digest(child(out,SEAL).read_bytes()))
    print(json.dumps(result,sort_keys=True),flush=True)
    return result


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,ImportError) as error:
        print(json.dumps(dict(status='REJECTED',reason=str(error))),file=sys.stderr,flush=True)
        raise SystemExit(2)
