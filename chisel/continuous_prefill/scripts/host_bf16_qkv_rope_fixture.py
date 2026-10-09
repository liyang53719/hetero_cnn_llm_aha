#!/usr/bin/env python3
"""Bounded seven-command fixtures from code-pinned retained Host/oracle evidence.

Only cold0/base0/position0 and carried127/base127/position255 are admitted.
This module never captures a model or runs an arithmetic reference. All eight
D allocations start as sentinels; independent/native files are audit-only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.command import Command128
from host_bf16_qkv_descriptor import HostQkvBinding, parse_host_qkv_descriptor
from host_bf16_qk_rope_descriptor import (
    HostQkNormBinding, HostPartialRopeBinding, build_host_qkv_rope_commands,
    parse_host_qk_rope_descriptor,
)

OWNER = ROOT / 'work/qk_norm_rope_owner_fixture'
OWNER_SHA = '890da192e5d11d95661db68e5b3b8210f205ac165a8ed12a0bad952160e413ab'
OLD_FIXTURE = ROOT / 'work/host_qkv_projection_frozen_6ie4nawh'
OLD_BUILD = ROOT / 'work/host_qkv_projection_build_20261009T0146Z'
NAMES = ('q', 'k', 'v', 'norm_q', 'gate', 'norm_k', 'rope_q', 'rope_k')
PC = (0, 1, 2, 3, 3, 4, 5, 6)
WIDTHS = (4096, 512, 512, 2048, 2048, 512, 2048, 512)
COMMAND_NAMES = ('q', 'k', 'v', 'norm_q', 'norm_k', 'rope_q', 'rope_k')
HEADER = 'base limit cb cl db dl meta scratch aa rows first count position trig trig_tokens gamma_q gamma_k'.split()
COMMAND_FIELDS = 'name engine records signal input input_bytes constant constant_bytes span_first span_count'.split()
SPAN_FIELDS = 'name pc allocation allocation_bytes begin bytes'.split()
SOURCES = (
    'chisel/continuous_prefill/scripts/host_bf16_qkv_rope_fixture.py',
    'chisel/continuous_prefill/scripts/host_bf16_qkv_rope_execution.py',
    'chisel/continuous_prefill/scripts/host_bf16_qk_rope_descriptor.py',
    'chisel/continuous_prefill/scripts/host_bf16_qkv_descriptor.py',
    'chisel/continuous_prefill/tests/host_bf16_qkv_rope.cpp',
    'chisel/continuous_prefill/tests/host_physical_axi.h',
    'src/heteronpu/command.py', 'src/heteronpu/descriptor_chain.py',
    'src/heteronpu/gemmini_descriptor_v2.py', 'src/heteronpu/gemmini_rocc_lowering.py',
    'src/heteronpu/abi_validation.py',
)


def require(ok, reason):
    if not ok: raise ValueError(reason)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def file_sha(path): return sha(Path(path).read_bytes())
def checked(path, digest):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'missing/symlink evidence: '+str(path))
    raw = path.read_bytes()
    require(sha(raw) == digest, 'pinned evidence drift: '+str(path))
    return raw


def source_identity(): return {name: file_sha(ROOT/name) for name in SOURCES}


def retained(case):
    require(case in ('cold0', 'carried127'), 'unsupported retained window')
    root = json.loads(checked(OWNER/'manifest.json', OWNER_SHA))
    owner_raw = checked(OWNER/case/'manifest.json', root['cases'][case]['sha256'])
    owner = json.loads(owner_raw)
    require(owner['independent_reference']['status'] == 'PASS_INDEPENDENT_C_ALL_NODES_AND_FLAGS', 'independent C nodes/flags missing')
    require(owner['native_full_block_failures']['baseline']['gate_pass'] is False and
            owner['native_full_block_failures']['avx2']['gate_pass'] is False, 'native full-block failure hidden')
    payload = {}
    for name, info in owner['files'].items():
        require(Path(name).name == name, 'owner file escape')
        payload[name] = checked(OWNER/case/name, info['sha256'])
        require(len(payload[name]) == info['bytes'], 'owner length')
    provenance = owner['host_provenance']
    report = json.loads(checked(OLD_BUILD/(case+'_pass.result.json'), provenance['report']['sha256']))
    require(report['status'] == 'PASS_PRODUCTION_HOST_QKV_CASE' and report['actual_dut_identity_verified'] is True
            and report['numerical_acceptance_eligible'] is True, 'original actual Host admission')
    old = json.loads(checked(OLD_FIXTURE/case/'manifest.json', provenance['fixture_manifest']['sha256']))
    original = {}
    for name, info in old['files'].items():
        require(Path(name).name == name, 'old fixture file escape')
        original[name] = checked(OLD_FIXTURE/case/name, info['sha256'])
        require(len(original[name]) == info['bytes'], 'old fixture length')
    for name, owner_name in zip('qkv', ('packed_q.bf16le', 'k.bf16le', 'v.bf16le')):
        actual = checked(OLD_BUILD/(case+'_pass')/('actual_'+name+'.bf16le'), report['runs'][0]['actual_sha256'][name])
        require(actual == payload[owner_name] == original['independent_'+name+'.bf16le'], 'actual projection/oracle predecessor drift')
    first, position = (0, 0) if case == 'cold0' else (127, 255)
    require((owner['token_base'], owner['token_count'], owner['positionBase']) == (first, 1, position), 'retained position/window')
    require(old['input_sha256'] == report['input_sha256'] == provenance['input_sha256'], 'original input identity')
    require(sha(original['activation.bf16le']) == provenance['input_sha256']['activation_tensor'], 'activation bytes')
    require(all(sha(original['weight_'+r+'.bf16le']) == provenance['input_sha256']['weight_tensor'][r] for r in 'qkv'), 'weight bytes')
    return owner, payload, original


def fresh(case, variant, session, reference_session, attention_reference_session):
    """Select live, input-bound expected data; never execute or seed a DUT."""
    from pack_host_bf16_qkv_fixture import pack_fixture
    from host_bf16_qk_rope_reference import FreshAttentionReferenceSession
    require(type(attention_reference_session) is FreshAttentionReferenceSession,
            'live independent attention reference authority required')
    require(case in ('cold0', 'carried127'), 'unsupported fresh window')
    phase, first, position = ('cold', 0, 0) if case == 'cold0' else ('carried', 127, 255)
    with tempfile.TemporaryDirectory(prefix='host_chain_input_pack_', dir=ROOT/'work') as temporary:
        directory = Path(temporary)/'projection'
        projection = pack_fixture(directory, variant=variant, phase=phase, token_base=first, token_count=1,
                                  session=session, reference_session=reference_session)
        original = {name: checked(directory/name, info['sha256']) for name, info in projection['files'].items()}
    payloads, proof = attention_reference_session.select(
        original['activation.bf16le'], {r: original['weight_'+r+'.bf16le'] for r in 'qkv'},
        session=session, projection_reference_session=reference_session,
        variant=variant, phase=phase, token_base=first, token_count=1)
    payload = {name+'.bf16le': raw for name, raw in payloads.items()}
    for r, name in zip('qkv', ('packed_q','k','v')):
        require('independent_'+r+'.bf16le' in original, 'missing independent projection terminal')
        payload[name+'.bf16le'] = original['independent_'+r+'.bf16le']
    receipt = attention_reference_session.verify(session=session, projection_reference_session=reference_session)
    failures=receipt['native_full_block_failures']
    require(set(failures)==set(projection['native_full_block_failures']) and all(
        all(failures[variant][key]==value for key,value in report.items())
        for variant,report in projection['native_full_block_failures'].items()), 'capture/native audit identity differs')
    owner = dict(token_base=first, positionBase=position,
                 native_full_block_failures=failures,
                 host_provenance=dict(source_mode='fresh_ref', prior_projection_dut_executed=False,
                                      projection_fixture=projection, attention_reference_sha256=attention_reference_session.receipt_sha256),
                 independent_reference=proof)
    return owner, payload, original


def contents(case, *, variant='baseline', session=None, reference_session=None, attention_reference_session=None):
    authorities = (session, reference_session, attention_reference_session)
    is_fresh = any(a is not None for a in authorities)
    require(not is_fresh or all(a is not None for a in authorities), 'all three live authorities are required for fresh references')
    require(is_fresh or variant == 'baseline', 'retained actual Host source covers baseline only')
    owner, payload, original = (fresh(case, variant, *authorities) if is_fresh else retained(case))
    first, position = owner['token_base'], owner['positionBase']
    h = dict(base=0x120000000, rows=128, first=first, count=1, position=position, trig_tokens=position+1)
    h.update(cb=h['base'], cl=h['base']+128, db=h['base']+4096, dl=h['base']+4096+1856, meta=h['base']+8192)
    cursor = h['meta']+4096
    def allocate(size):
        nonlocal cursor
        address = cursor; cursor += (size+63)//64*64+4096
        return address
    h['aa'] = allocate(128*2048)
    weights = [allocate(1024*n*2) for n in WIDTHS[:3]]
    h['gamma_q'], h['gamma_k'] = allocate(512), allocate(512)
    h['trig'] = allocate(h['trig_tokens']*128)
    h['scratch'] = cursor
    addresses = [allocate(128*n*2) for n in WIDTHS]
    h['limit'] = cursor
    ps = [HostQkvBinding(i, 128, first, 1, h['aa'], weights[i], addresses[i]) for i in range(3)]
    ns = [HostQkNormBinding(i, 128, first, 1, addresses[i], h['gamma_q' if i==0 else 'gamma_k'], addresses[3 if i==0 else 5], addresses[4] if i==0 else 0) for i in range(2)]
    rs = [HostPartialRopeBinding(i, 128, first, 1, addresses[3 if i==0 else 5], h['trig'], addresses[6+i], position+1, position) for i in range(2)]
    commands, records = build_host_qkv_rope_commands(ps, ns, rs)
    raw_commands = b''.join(c.pack().to_bytes(16, 'little') for c in commands).ljust(128, b'\0')
    raw_records = b''.join(records[i].pack().to_bytes(16, 'little') for i in range(114)).ljust(1856, b'\0')
    specs = []
    for i, binding in enumerate((*ps, *ns, *rs)):
        if i<3: source, size, const, const_size, sf, sc = binding.job['a'], 2048, weights[i], 1024*binding.n*2, i, 1
        elif i<5: source, size, const, const_size, sf, sc = binding.job['input'], binding.input_columns*2, binding.weight_ddr, 512, 3 if i==3 else 5, 2 if i==3 else 1
        else: source, size, const, const_size, sf, sc = binding.job['input'], binding.n*2, h['trig']+position*128, 128, i+1, 1
        specs.append(dict(zip(COMMAND_FIELDS, (COMMAND_NAMES[i], 2 if i<3 else 3, 21 if i<3 else binding.record_count, i+1, source, size, const, const_size, sf, sc))))
    spans = [dict(zip(SPAN_FIELDS, (name, pc, address, 128*n*2, address+first*n*2, n*2))) for name, pc, address, n in zip(NAMES, PC, addresses, WIDTHS)]
    launch = '\n'.join(['HOST_QKV_ROPE_V1', ' '.join(str(h[k]) for k in HEADER)] +
                       [' '.join(str(c[k]) for k in COMMAND_FIELDS) for c in specs] +
                       [' '.join(str(s[k]) for k in SPAN_FIELDS) for s in spans])+'\n'
    files = {'launch.txt': launch.encode(), 'host_commands.bin': raw_commands, 'host_descriptors.bin': raw_records,
             'activation.bf16le': original['activation.bf16le']}
    for r in 'qkv':
        files['weight_'+r+'.bf16le'] = original['weight_'+r+'.bf16le']
        n = WIDTHS['qkv'.index(r)]
        files['native_'+r+'.bf16le'] = original['native_'+r+'.bf16le'][first*n*2:(first+1)*n*2]
    for name in ('q_gamma.bf16le', 'k_gamma.bf16le', 'trig.bf16le', 'native_norm_q.bf16le', 'native_norm_k.bf16le', 'native_rope_q_prefix.bf16le', 'native_rope_k_prefix.bf16le'):
        files[name] = payload[name]
    for name, original_name in zip(NAMES, ('packed_q', 'k', 'v', 'norm_q', 'gate', 'norm_k', 'rope_q', 'rope_k')):
        files['independent_'+name+'.bf16le'] = payload[original_name+'.bf16le']
    source_hashes = source_identity()
    if is_fresh:
        authorities = (reference_session.verify(session=session),
                       attention_reference_session.verify(session=session, projection_reference_session=reference_session))
        for authority in authorities:
            for name, digest in authority['source_sha256'].items():
                require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'reference source path escape')
                require(file_sha(ROOT/name) == digest, 'reference source closure drift')
                source_hashes[name] = digest
        original_checks = owner['independent_reference']['original_operator_checks']
        original_gate = owner['independent_reference']['original_operator_gate_pass']
    else:
        original_checks = owner.get('native_diagnostics', {})
        original_gate = set(original_checks) == {'q', 'k'} and all(
            row['norm_vs_native']['max_abs'] <= 0.03125 and row['norm_vs_native']['mean_abs'] <= 0.005
            and row['norm_same_actual_host_input'] is True
            and row['rope_on_native_norm_same_input_vs_native']['bit_differences'] == 0
            for row in original_checks.values())
    input_hashes = dict(activation_tensor=sha(files['activation.bf16le']),
                        activation_window=sha(files['activation.bf16le'][first*2048:(first+1)*2048]),
                        weight_tensor={r:sha(files['weight_'+r+'.bf16le']) for r in 'qkv'},
                        constants={n:sha(files[n+'.bf16le']) for n in ('q_gamma','k_gamma','trig')},
                        independent_terminals={n:sha(files['independent_'+n+'.bf16le']) for n in NAMES})
    receipt = dict(status='PREPARED_HOST_QKV_QKNORM_ROPE_NOT_EXECUTED', scope='QKV_QKNORM_PARTIAL_ROPE_ONLY',
                   case=case, variant=variant, source_mode='fresh_ref' if is_fresh else 'retained_actual',
                   owner_manifest_sha256=None if is_fresh else OWNER_SHA, source_sha256=source_hashes,
                   native_full_block_failures=owner['native_full_block_failures'],
                   source_provenance=owner['host_provenance'], independent_reference=owner['independent_reference'],
                   original_operator_gate_pass=original_gate, original_operator_checks=original_checks,
                   input_sha256=input_hashes,
                   input_injection=False, full_block_supported=False,
                   files={n: dict(bytes=len(raw), sha256=sha(raw)) for n, raw in sorted(files.items())})
    return files, receipt


def pack(output, case, *, variant='baseline', session=None, reference_session=None, attention_reference_session=None):
    output = Path(output)
    require(not output.exists() or not any(output.iterdir()), 'fixture output must be empty')
    files, receipt = contents(case, variant=variant, session=session, reference_session=reference_session,
                              attention_reference_session=attention_reference_session)
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items(): (output/name).write_bytes(raw)
    (output/'manifest.json').write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    return receipt


def verify(fixture, *, session=None, reference_session=None, attention_reference_session=None):
    fixture = Path(fixture)
    raw = (fixture/'manifest.json').read_bytes(); receipt = json.loads(raw)
    files, expected = contents(receipt['case'], variant=receipt['variant'], session=session,
                              reference_session=reference_session, attention_reference_session=attention_reference_session)
    require(receipt == expected, 'fixture/source/provenance receipt differs from code-pinned reconstruction')
    require(set(p.name for p in fixture.iterdir()) == set(files)|{'manifest.json'}, 'unknown/missing fixture file')
    for name, data in files.items(): require(checked(fixture/name, sha(data)) == data, 'fixture mismatch')
    return dict(status='PASS_FRESH_SEVEN_COMMAND_FIXTURE' if receipt['source_mode']=='fresh_ref' else 'PASS_RETAINED_SEVEN_COMMAND_FIXTURE', fixture_sha256=sha(raw), case=receipt['case'],
                source_sha256=receipt['source_sha256'], owner_manifest_sha256=receipt['owner_manifest_sha256'],
                source_mode=receipt['source_mode'], input_sha256=receipt['input_sha256'],
                original_operator_gate_pass=receipt['original_operator_gate_pass'],
                original_operator_checks=receipt['original_operator_checks'],
                native_full_block_failures=receipt['native_full_block_failures'], actual_chain_executed=False)


def layout(fixture):
    lines = (Path(fixture)/'launch.txt').read_text().splitlines()
    require(len(lines)==17 and lines[0]=='HOST_QKV_ROPE_V1', 'launch shape')
    require(len(lines[1].split())==len(HEADER), 'launch header')
    h = dict(zip(HEADER, map(int, lines[1].split())))
    def rows(lines, names):
        out=[]
        for line in lines:
            fields=line.split();require(len(fields)==len(names), 'launch record')
            out.append(dict(zip(names, [fields[0]]+list(map(int,fields[1:])))))
        return out
    cs, spans = rows(lines[2:9],COMMAND_FIELDS), rows(lines[9:],SPAN_FIELDS)
    command_raw=(Path(fixture)/'host_commands.bin').read_bytes();record_raw=(Path(fixture)/'host_descriptors.bin').read_bytes()
    require(len(command_raw)==128 and len(record_raw)==1856 and not any(command_raw[112:]) and not any(record_raw[1824:]),'metadata padding')
    records={i:int.from_bytes(record_raw[i*16:(i+1)*16],'little') for i in range(114)}
    commands=[Command128.unpack(int.from_bytes(command_raw[i*16:(i+1)*16],'little')) for i in range(7)]
    bindings=[(parse_host_qkv_descriptor if i<3 else parse_host_qk_rope_descriptor)(c,records) for i,c in enumerate(commands)]
    rebuilt, recs=build_host_qkv_rope_commands(bindings[:3],bindings[3:5],bindings[5:])
    require([c.pack() for c in rebuilt]==[c.pack() for c in commands] and all(recs[i].pack()==records[i] for i in records),'canonical seven-command chains')
    return h,cs,spans


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--case',choices=('cold0','carried127'));p.add_argument('--verify',action='store_true');a=p.parse_args()
    print(json.dumps(verify(a.output) if a.verify else pack(a.output,a.case),indent=2))
