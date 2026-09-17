"""Synthetic export fixtures exercise receipt validation, not model inference."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heteronpu.block_receipt import ReceiptError, ComparisonUnavailable, read_json, verify, compare_files


def write(path, doc):
    path.write_text(json.dumps(doc, sort_keys=True))


def fixture(root):
    run = dict(design_sha='1'*40, reference_sha='2'*40, input_sha256='3'*64, model_revision='4'*40, run_id='fixture-not-rtl')
    tensors=[]; exports=[]
    for i,(name,dtype,role,raw) in enumerate([
        ('projection','f32le','tensor',struct.pack('<4f',0.,-0.,1.,-2.)),
        ('gdn_state','bf16le','state',struct.pack('<4H',0x3f80,0x4000,0x8000,0)),
        ('route','u32le','tensor',struct.pack('<4I',0,1,255,511))]):
        digest=hashlib.sha256(raw).hexdigest()
        for prefix in ('actual','ref'): (root/f'{prefix}_{name}.bin').write_bytes(raw)
        generation=2 if role=='state' else None
        tensors.append(dict(id=name,role=role,dtype=dtype,shape=[2,2],reference=f'ref_{name}.bin',reference_sha256=digest,comparison='bit_exact',generation=generation,producer_pc=i))
        exports.append(dict(id=name,file=f'actual_{name}.bin',sha256=digest,dtype=dtype,shape=[2,2],generation=generation,producer_pc=i))
    spec=dict(version=1,identity=run,tensors=tensors,commands=[dict(pc=i,write_ack_bytes=64) for i in range(3)])
    write(root/'manifest.json',spec)
    receipt=dict(version=1,manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),identity=deepcopy(run),exports=exports,
                 completions=[dict(pc=i,status=0,write_ack_bytes=64) for i in range(3)],
                 attestation=dict(cpu_fallback=0,host_intermediate_writes=0,unresolved_owners=0))
    write(root/'receipt.json',receipt)
    return spec,receipt


def run(root): return verify(root/'manifest.json',root/'receipt.json',root)


def test_full_inventory_and_scope(tmp_path):
    fixture(tmp_path); result=run(tmp_path)
    assert result['compared_elements']==12 and result['tensor_count']==2 and result['state_count']==1
    assert not result['hardware_execution_verified'] and not result['official_model_accepted']


@pytest.mark.parametrize('kind', ['missing','duplicate','extra','shape','dtype','generation','producer','run','reference_sha','manifest_sha',
    'completion_missing','completion_duplicate','completion_reorder','ack','status','injection','fallback','unresolved','bool','unknown_field'])
def test_receipt_corruption(tmp_path,kind):
    _,r=fixture(tmp_path)
    if kind=='missing': r['exports'].pop(1)
    elif kind=='duplicate': r['exports'].append(deepcopy(r['exports'][0]))
    elif kind=='extra': r['exports'][0]['id']='not_expected'
    elif kind=='shape': r['exports'][0]['shape']=[4]
    elif kind=='dtype': r['exports'][0]['dtype']='i32le'
    elif kind=='generation': r['exports'][1]['generation']=1
    elif kind=='producer': r['exports'][0]['producer_pc']=2
    elif kind=='run': r['identity']['run_id']='other_run'
    elif kind=='reference_sha': r['identity']['reference_sha']='a'*40
    elif kind=='manifest_sha': r['manifest_sha256']='0'*64
    elif kind=='completion_missing': r['completions'].pop()
    elif kind=='completion_duplicate': r['completions'].append(r['completions'][0])
    elif kind=='completion_reorder': r['completions'].reverse()
    elif kind=='ack': r['completions'][-1]['write_ack_bytes']=0
    elif kind=='status': r['completions'][-1]['status']=1
    elif kind=='injection': r['attestation']['host_intermediate_writes']=1
    elif kind=='fallback': r['attestation']['cpu_fallback']=1
    elif kind=='unresolved': r['attestation']['unresolved_owners']=1
    elif kind=='bool': r['completions'][0]['status']=False
    elif kind=='unknown_field': r['pass']=True
    write(tmp_path/'receipt.json',r)
    with pytest.raises(ReceiptError): run(tmp_path)


@pytest.mark.parametrize('kind', ['truncated','oversized','wrong_bits_with_new_hash','reference_modified','state_missing','tail_only','nan_actual','nan_reference'])
def test_byte_corruption(tmp_path,kind):
    _,r=fixture(tmp_path); a=tmp_path/r['exports'][0]['file']; data=a.read_bytes()
    if kind=='truncated': a.write_bytes(data[:-1])
    elif kind=='oversized': a.write_bytes(data+b'\0')
    elif kind=='wrong_bits_with_new_hash': a.write_bytes(struct.pack('<I',1)+data[4:]); r['exports'][0]['sha256']=hashlib.sha256(a.read_bytes()).hexdigest()
    elif kind=='reference_modified': (tmp_path/'ref_projection.bin').write_bytes(data[:-4]+struct.pack('<f',1.))
    elif kind=='state_missing': (tmp_path/'actual_gdn_state.bin').unlink()
    elif kind=='tail_only': a.write_bytes(data[:-1]+bytes([data[-1]^1]))
    elif kind=='nan_actual': a.write_bytes(struct.pack('<I',0x7fc00000)+data[4:])
    elif kind=='nan_reference': (tmp_path/'ref_projection.bin').write_bytes(struct.pack('<I',0x7fc00000)+data[4:])
    write(tmp_path/'receipt.json',r)
    with pytest.raises(ReceiptError): run(tmp_path)


@pytest.mark.parametrize('kind', ['same_path','symlink','hardlink','duplicate_inode','traversal','absolute'])
def test_file_alias_and_paths(tmp_path,kind):
    _,r=fixture(tmp_path); a=tmp_path/'actual_projection.bin'
    if kind=='same_path': r['exports'][0]['file']='ref_projection.bin'
    elif kind in ('symlink','hardlink'):
        a.unlink()
        if kind=='symlink': a.symlink_to(tmp_path/'ref_projection.bin')
        else: os.link(tmp_path/'ref_projection.bin',a)
    elif kind=='duplicate_inode': r['exports'][2]['file']='actual_projection.bin'
    elif kind=='traversal': r['exports'][0]['file']='../actual_projection.bin'
    elif kind=='absolute': r['exports'][0]['file']=str(a)
    write(tmp_path/'receipt.json',r)
    with pytest.raises(ReceiptError): run(tmp_path)


def test_approximate_contract_is_not_silently_accepted(tmp_path):
    s,r=fixture(tmp_path);s['tensors'][0]['comparison']='relative_0.002'
    write(tmp_path/'manifest.json',s)
    with pytest.raises(ComparisonUnavailable,match='C02'): run(tmp_path)


@pytest.mark.parametrize('text', ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json(tmp_path,text):
    p=tmp_path/'x.json';p.write_text(text)
    with pytest.raises(ReceiptError): read_json(p)


def test_full_scan_beyond_one_megabyte(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b'
    raw=struct.pack('<I',123)*(262144+5);a.write_bytes(raw);b.write_bytes(raw[:-4]+struct.pack('<I',124))
    r=compare_files(a,b,'u32le',len(raw))
    assert r['elements']==262149 and r['different_elements']==1 and r['first_difference']==262148


def test_zero_sign_and_integer_bits_are_not_approximate(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.write_bytes(struct.pack('<I',0));b.write_bytes(struct.pack('<I',0x80000000))
    assert compare_files(a,b,'f32le',4)['different_elements']==1


@pytest.mark.parametrize('kind', ['duplicate','zero_shape','bool_shape','empty','bad_hash','missing_pc','extra_key'])
def test_frozen_manifest_corruption(tmp_path,kind):
    s,r=fixture(tmp_path)
    if kind=='duplicate': s['tensors'].append(s['tensors'][0])
    elif kind=='zero_shape': s['tensors'][0]['shape']=[0,4]
    elif kind=='bool_shape': s['tensors'][0]['shape']=[True,4]
    elif kind=='empty': s['tensors']=[]
    elif kind=='bad_hash': s['tensors'][0]['reference_sha256']='main'
    elif kind=='missing_pc': s['commands'][0]['pc']=9
    elif kind=='extra_key': s['tensors'][0]['skip_comparison']=True
    write(tmp_path/'manifest.json',s)
    with pytest.raises(ReceiptError): run(tmp_path)
