"""Source-only synthetic 16-row event traces; never inputs to the RTL gate."""
from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tile16_trace_under_test', ROOT / 'scripts/verify_matrix_norm_rope_tile16_trace.py')
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


class SyntheticCases(dict):
    """Each token has distinct activations/results, but shares its head weights."""
    def __init__(self):
        super().__init__()
        self.weights = {}

    def __missing__(self, case):
        token = case // 10 if case < 320 else 16
        role = 0 if case < 320 and case % 10 < 8 else 1
        head = case % 10 if role == 0 else case % 10 - 8 if case < 320 else case - 320
        columns = 512 if role == 0 else 256
        raw = np.asarray([0x3e00 + head * 16 + i % 32 for i in range(columns)], dtype=np.uint32)
        projected = raw + token * 128
        fp32 = projected << 16
        steps = np.repeat(fp32.reshape(-1, 1, 32), 1024, axis=1).reshape(-1, 32)
        activation = np.zeros(1024, dtype=np.uint32)
        activation[0] = 0x3f80 + token * 128
        if (role, head) not in self.weights:
            weight = np.zeros(1024 * columns, dtype=np.uint32)
            weight[:columns] = raw
            self.weights[role, head] = weight
        normalized = v.head_trace(tuple(int(x) << 16 for x in projected[:256]), (0,) * 256)
        norm = np.asarray([x >> 16 for x in normalized['output_bf16']], dtype=np.uint32)
        result = dict(columns=columns, projected=projected, projected_fp32=fp32, steps=steps,
                      activation=activation, weight=self.weights[role, head], norm_weight=np.zeros(256, dtype=np.uint32),
                      norm=norm, rope=norm.copy(), trig=np.asarray([0x3f80] * 32 + [0] * 32, dtype=np.uint32),
                      norm_trace=normalized, rope_flags=0)
        self[case] = result
        return result


@pytest.fixture(scope='module')
def cases():
    return SyntheticCases()


def packet(event, **fields):
    return dict(event=event, **fields)


def begin(kind='main', name='tail_1', transaction=1):
    default_count = (int(name[5:]) if name.startswith('tail_') else 128 if name == 'token_count128_admitted'
                     else 16 if kind in ('fault', 'reset') else 1)
    case, role, start, count = next((x[1:] for x in v.MAIN if x[0] == name), (8, 1, 0, default_count))
    return dict(event='begin', transaction=transaction, kind=kind, name=name, case=case,
                role=role, start_token=start, token_count=count, checking=1, **v._bases(start, kind == 'boundary'))


def descriptors(b):
    count = {'bad_command': 0, 'malformed_descriptor': 1, 'unsupported_FP32_output': 5}.get(b['name'], 6)
    for i, data in enumerate(v._descriptors(b['role'], b['name'])[:count], 1):
        yield packet('descriptor_request', index=i)
        yield packet('descriptor', index=i, data=f'{data:032x}', error=0)


def dma(index, kind, src, dst, rb, rows, ss, ds, words=None):
    yield packet('dma', index=index, kind=kind, source=f'{src:016x}', destination=f'{dst:016x}',
                 row_bytes=rb, rows=rows, source_stride=ss, destination_stride=ds)
    if words is not None:
        for beat, data in enumerate(words):
            yield packet('dma_data', index=index, source=f'{src + beat * ss:016x}',
                         destination=f'{dst + beat * ds:016x}', data=f'{v._packed(data):0128x}')
    yield packet('dma_ack', index=index, error=0)


def read(region, address, words=None, raw=None):
    yield packet('l2_read', region=region, byte_address=address)
    yield packet('l2_response', byte_address=address, error=0,
                 data=f'{v._packed(words) if raw is None else raw:0128x}')


def write(region, address, words):
    yield packet('l2_write', region=region, byte_address=address, mask='f' * 16, data=f'{v._packed(words):0128x}')
    yield packet('l2_ack', byte_address=address, error=0)


def body(b, cases):
    yield packet('accepted_start')
    yield from descriptors(b)
    if b['kind'] == 'reject':
        return
    role = b['role']; heads, tiles = (8, 16) if role == 0 else (2, 8)
    ps, ns = (8192, 4096) if role == 0 else (1024, 1024)
    index = 0
    staged_tokens = {}
    for batch in range(b['start_token'], b['start_token'] + b['token_count'], 16):
        rows = min(16, b['start_token'] + b['token_count'] - batch)
        for row in range(rows):
            yield from dma(index, 1, 0x100000000 + (batch + row) * 2048, b['act_base'] + row * 2, 2, 1024, 2, 64)
            staged_tokens[row] = batch + row
            index += 1
        activation_words = []
        for k in range(1024):
            address = b['act_base'] + k * 64
            raw = bytearray(0xa5 ^ ((address // 64 * 17 + byte * 13) & 255) for byte in range(64))
            for row, token in staged_tokens.items():
                raw[row * 2:row * 2 + 2] = int(cases[v._case_id(role, token, 0)]['activation'][k]).to_bytes(2, 'little')
            activation_words.append(int.from_bytes(raw, 'little'))
        for head in range(heads):
            row_cases = [cases[v._case_id(role, batch + row, head)] for row in range(rows)]
            yield packet('projection_begin', head=head, batch_start=batch, rows=rows)
            for tile in range(tiles):
                yield from dma(index, 1, 0x200000000 + head * tiles * 64 + tile * 64, b['wgt_base'], 64, 1024, ps, 64)
                index += 1
                full_rows = sum(v._packed(ex['steps'][tile * 1024], 4) << (row * 1024) for row, ex in enumerate(row_cases))
                full_rows_hex = f'{full_rows:04096x}'
                for k in range(1024):
                    yield from read(5, b['act_base'] + k * 64, raw=activation_words[k])
                    off = k * tiles * 32 + tile * 32
                    yield from read(6, b['wgt_base'] + k * 64, row_cases[0]['weight'][off:off + 32])
                    yield packet('matrix', head=head, batch_start=batch, rows=rows, tile=tile, index=tile * 1024 + k,
                                 context=0, last=int(k == 1023), fp32_rows=full_rows_hex)
                for row, ex in enumerate(row_cases):
                    yield from write(0, b['packed_base'] + tile * 1024 + row * 64, ex['projected'][tile * 32:tile * 32 + 32])
                yield from dma(index, 3, b['packed_base'] + tile * 1024,
                               0x300000000 + batch * ps + head * tiles * 64 + tile * 64, 64, rows, 64, ps,
                               [ex['projected'][tile * 32:tile * 32 + 32] for ex in row_cases])
                index += 1
            for row, ex in enumerate(row_cases):
                token = batch + row; case = v._case_id(role, token, head)
                yield packet('head_begin', case=case, head=head, token=token, row=row)
                for tile in range(tiles):
                    yield from read(0, b['packed_base'] + tile * 1024 + row * 64, ex['projected'][tile * 32:tile * 32 + 32])
                for beat in range(8):
                    yield from read(3, b['gamma_base'] + beat * 64, ex['norm_weight'][beat * 32:beat * 32 + 32])
                n = ex['norm_trace']
                yield packet('norm', status=0, mean_eps=f"{n['mean_eps']:08x}", inv=f"{n['inverse']:08x}", flags=n['aggregate_flags'],
                             norm=f"{v._packed(ex['norm']):01024x}", gate=f"{v._packed(ex['projected'][256:]) if role == 0 else 0:01024x}")
                for beat in range(8):
                    yield from write(1, b['norm_base'] + beat * 64, ex['norm'][beat * 32:beat * 32 + 32])
                for beat in range(8):
                    yield from read(1, b['norm_base'] + beat * 64, ex['norm'][beat * 32:beat * 32 + 32])
                for beat in range(2):
                    yield from read(4, b['trig_base'] + (token - b['start_token']) * 128 + beat * 64, ex['trig'][beat * 32:beat * 32 + 32])
                for beat in range(8):
                    yield from write(2, b['rope_base'] + beat * 64, ex['rope'][beat * 32:beat * 32 + 32])
                for name, local, ddr in [('norm', 'norm_base', 0x400000000), ('rope', 'rope_base', 0x500000000)]:
                    if b['kind'] == 'boundary':
                        ddr = (1 << 56) - (2048 if name == 'norm' else 1024)
                    yield from dma(index, 3, b[local], ddr + token * ns + head * 512, 64, 8, 64, 64,
                                   [ex[name][beat * 32:beat * 32 + 32] for beat in range(8)])
                    index += 1
                yield packet('head_done', case=case, head=head, token=token, row=row)
            yield packet('projection_done', head=head, batch_start=batch, rows=rows,
                         matrix_inputs=tiles * 1024, matrix_outputs=tiles * 1024, write_acks=rows * (tiles + 16))


def transaction(b, cases):
    yield b
    counts = Counter(); flags = 0; current_case = None; completed_tokens = 0; read_bytes = write_bytes = 0; q = None
    for raw in body(b, cases):
        r = dict(raw); event = r['event']
        if event == 'head_begin': current_case = r['case']
        if event == 'norm': flags |= cases[current_case]['norm_trace']['aggregate_flags']
        if event == 'l2_write' and r['region'] == 2: flags |= cases[current_case]['rope_flags']
        if event == 'head_done':
            r['flags'] = flags
            if r['head'] == (7 if b['role'] == 0 else 1) and r['row'] == min(16, b['start_token'] + b['token_count'] - (r['token'] - r['row'])) - 1:
                completed_tokens += r['row'] + 1
        if event == 'dma': q = r
        if b['kind'] == 'reset' and event == 'dma' and r['index'] == (63 if b['name'] == 'reset_late_row' else 111):
            yield r
            yield packet('reset_flush', stage=0 if b['name'] == 'reset_late_row' else 1)
            return
        failed = b['kind'] == 'fault' and event == 'dma_ack' and r['index'] == (0 if b['name'] == 'token_count128_admitted' else 111)
        if failed: r['error'] = 1
        if event == 'dma_ack' and not failed:
            if q['kind'] == 3: write_bytes += q['row_bytes'] * q['rows']
            else: read_bytes += q['row_bytes'] * q['rows']
        counts[event] += 1
        yield r
        if failed: break
    status = v.REJECTS[b['name']] if b['kind'] == 'reject' else 6 if b['kind'] == 'fault' else 0
    yield packet('done', status=status)
    yield packet('terminal', status=status, matrix_inputs=counts['matrix'], matrix_outputs=counts['matrix'], matrix_steps=counts['matrix'],
                 dma_count=counts['dma'], write_requests=counts['l2_write'], write_acks=counts['l2_ack'],
                 completed_heads=counts['head_done'], completed_tokens=completed_tokens,
                 total_tiles=(128 if b['role'] == 0 else 16) if counts['dma'] else 0, flags=flags,
                 ddr_read_bytes=read_bytes, ddr_write_bytes=write_bytes)


def complete_records(records):
    cycle = 0; owner = None; dma_rows = 0; accepted_cycle = done_cycle = 0
    for raw in records:
        r = dict(raw)
        if r['event'] == 'begin': owner = r['transaction']
        else:
            r['transaction'] = owner
            if r['event'] == 'dma': dma_rows = r['rows'] if r['kind'] == 1 else 0
            if 'cycle' in v.SCHEMA[r['event']]:
                cycle += dma_rows + 1 if r['event'] == 'dma_ack' else 1
                r['cycle'] = cycle
                if r['event'] == 'accepted_start': accepted_cycle = cycle
                if r['event'] == 'done': done_cycle = cycle
            if r['event'] == 'terminal': r['command_cycles'] = done_cycle - accepted_cycle + 1
        yield r


def consume(records, cases, validate_json=False):
    active = None
    for raw in records:
        r = v._record(json.dumps(raw) + '\n') if validate_json else raw
        if r['event'] == 'begin': active = v.Transaction(r, cases)
        else: active.consume(r)
    return active


def mutate(records, event, field, value, occurrence=0):
    out = list(records)
    index = [i for i, r in enumerate(out) if r['event'] == event][occurrence]
    out[index] = {**out[index], field: value}
    return out


@pytest.fixture(scope='module')
def short(cases):
    return list(complete_records(transaction(begin(), cases)))


def test_complete_short_tail_all512_lanes(short, cases):
    result = consume(short, cases, validate_json=True)
    assert result.completed_heads == 2 and result.completed_tokens == 1
    assert result.counts['matrix'] == 16384 and result.counts['dma'] == 37
    assert result.counts['l2_write'] == result.counts['l2_ack'] == 48
    assert result.read_bytes == 2048 + 65536 * 16 and result.write_bytes == 3072


@pytest.mark.parametrize('n', [3, 17])
def test_multirow_and_second_batch_tail_have_real_row_distinction(cases, n):
    result = consume(complete_records(transaction(begin(name='tail_' + str(n)), cases)), cases)
    batches = (n + 15) // 16
    assert result.completed_heads == n * 2 and result.completed_tokens == n
    assert result.projections == batches * 2
    assert result.counts['matrix'] == batches * 16384
    assert result.counts['dma'] == n + 32 * batches + 4 * n
    assert result.counts['l2_read'] == 32768 * batches + 52 * n
    assert result.read_bytes == 2048 * n + 1048576 * batches
    assert result.write_bytes == 3072 * n


@pytest.mark.parametrize('event,field,value,occurrence', [
    ('begin','checking',0,0),('begin','packed_base',0,0),('begin','token_count',2,0),
    ('projection_begin','rows',16,0),('projection_begin','head',1,0),('projection_begin','batch_start',1,0),
    ('projection_done','matrix_inputs',0,0),('projection_done','write_acks',1,0),
    ('head_begin','case',9,0),('head_begin','row',1,0),('head_begin','token',1,0),
    ('head_done','flags',0,0),('head_done','row',1,0),
    ('descriptor','data','0'*32,0),('descriptor','error',1,0),
    ('dma','index',1,0),('dma','destination','0000000000010002',0),('dma','rows',16,0),
    ('dma','source_stride',8192,1),('dma','destination_stride',64,2),
    ('dma_ack','index',1,0),('dma_ack','error',1,0),
    ('matrix','index',1,0),('matrix','tile',1,0),('matrix','rows',2,0),('matrix','last',1,0),
    ('matrix','context',1,0),('matrix','fp32_rows','0'*4096,0),
    ('l2_read','byte_address',0,0),('l2_response','data','0'*128,0),('l2_response','error',1,0),
    ('l2_write','byte_address',0,0),('l2_write','mask','0'*16,0),('l2_write','data','0'*128,0),
    ('l2_ack','byte_address',0,0),('l2_ack','error',1,0),
    ('dma_data','index',0,0),('dma_data','destination','0000000300000200',0),('dma_data','data','0'*128,0),
    ('norm','flags',0,0),('norm','norm','0'*1024,0),('norm','gate','1'+'0'*1023,0),
    ('norm','mean_eps','00000000',0),('norm','inv','00000000',0),
    ('done','status',8,0),('terminal','status',8,0),('terminal','matrix_steps',0,0),
    ('terminal','completed_heads',1,0),('terminal','completed_tokens',0,0),('terminal','flags',0,0),
    ('terminal','total_tiles',128,0),('terminal','ddr_read_bytes',0,0),('terminal','ddr_write_bytes',0,0),
])
def test_identity_geometry_data_flags_and_forged_completion_fail(short,cases,event,field,value,occurrence):
    with pytest.raises(ValueError): consume(mutate(short,event,field,value,occurrence),cases)


@pytest.mark.parametrize('row,lane', [(0,0),(0,31),(1,0),(15,31)])
def test_wrong_active_or_inactive_matrix_lane_rejected(short,cases,row,lane):
    original = next(r for r in short if r['event'] == 'matrix')['fp32_rows']
    changed = f'{int(original,16) ^ (1 << ((row*32+lane)*32)):04096x}'
    with pytest.raises(ValueError,match='row mismatch'):
        consume(mutate(short,'matrix','fp32_rows',changed),cases)


@pytest.mark.parametrize('event',['accepted_start','projection_begin','projection_done','head_begin','head_done','matrix','norm','dma_data','dma_ack','l2_ack','done'])
def test_missing_duplicate_or_reordered_events_rejected(short,cases,event):
    i = next(i for i,r in enumerate(short) if r['event']==event)
    j = next((j for j in range(i+1,len(short)) if short[j]['event']==event), i+1)
    reordered = list(short); reordered[i],reordered[j] = reordered[j],reordered[i]
    for records in (short[:i]+short[i+1:], short[:i+1]+[short[i]]+short[i+1:], reordered):
        with pytest.raises(ValueError): consume(records,cases)


@pytest.mark.parametrize('event',['descriptor','dma_ack','l2_response','l2_ack'])
def test_no_early_done_head_or_projection_while_response_pending(short,cases,event):
    i=next(i for i,r in enumerate(short) if r['event']==event)
    for terminal in (packet('done',status=0,cycle=1),packet('head_done',case=8,head=0,token=0,row=0,flags=1),
                     packet('projection_done',head=0,batch_start=0,rows=1,matrix_inputs=8192,matrix_outputs=8192,write_acks=24)):
        with pytest.raises(ValueError,match='before owner response/ACK'): consume(short[:i]+[terminal],cases)


@pytest.mark.parametrize('name',list(v.REJECTS))
def test_exact_negative_status_and_no_traffic(cases,name):
    records=list(complete_records(transaction(begin('reject',name),cases)))
    result=consume(records,cases,True)
    assert result.completed_heads==result.completed_tokens==result.read_bytes==result.write_bytes==0
    with pytest.raises(ValueError): consume(mutate(records,'done','status',0),cases)
    with pytest.raises(ValueError,match='side effects'):
        consume(records[:2]+[packet('projection_begin',head=0,batch_start=0,rows=1)]+records[2:],cases)


@pytest.mark.parametrize('name',['last_row_last_head_DMA_error','token_count128_admitted'])
def test_faults_do_not_complete_failed_batch(cases,name):
    records=list(complete_records(transaction(begin('fault',name),cases)))
    result=consume(records,cases)
    assert result.completed_heads==(0 if name=='token_count128_admitted' else 31)
    assert result.completed_tokens==0
    with pytest.raises(ValueError): consume(mutate(records,'terminal','completed_tokens',16),cases)
    with pytest.raises(ValueError): consume(mutate(records,'dma_ack','error',0,-1),cases)


@pytest.mark.parametrize('name,completed,index',[('reset_late_row',15,63),('reset_late_head',31,111)])
def test_reset_requires_exact_late_row_and_pending_dma(cases,name,completed,index):
    records=list(complete_records(transaction(begin('reset',name),cases)))
    result=consume(records,cases)
    assert result.completed_heads==completed and result.completed_tokens==0
    assert result.pending['dma']['index']==index
    with pytest.raises(ValueError): consume(mutate(records,'reset_flush','stage',9),cases)


def test_public_negative_suite_and_frozen_inventory_without_vectors(tmp_path):
    records=(r for i,(kind,name,_) in enumerate(v._suite_sequence('negative'),1) for r in transaction(begin(kind,name,i),{}))
    path=tmp_path/'negative.jsonl'
    path.write_text(''.join(json.dumps(r)+'\n' for r in complete_records(records)))
    result=v.verify_trace(path,tmp_path,suite='negative')
    assert result['transactions']==35 and result['bitexact_matrix_packets']==0
    assert len(v._suite_sequence('all'))==49
    assert len(v._suite_sequence('tail'))==3
    with pytest.raises(ValueError): v.verify_trace(path,tmp_path,suite='all')
    with pytest.raises(ValueError): v.verify_trace(path,tmp_path,suite='main',required_main=0)


def test_primary_inventory_matches_independent_counter_equations():
    contract=json.loads((ROOT/'config/upstream/qwen3_5_0p8b/matrix_norm_rope_tile16_contract.json').read_text())['frozen_gate']
    commands=contract['commands_per_variant']
    packets=sum(((c['count']+15)//16)*c['heads']*(16 if c['role']=='q' else 8)*1024 for c in commands)
    observations=sum(c['count']*c['heads']*(16 if c['role']=='q' else 8)*1024*32 for c in commands)
    assert packets==contract['primary_matrix_packets_per_variant']==294912
    assert observations==contract['primary_active_fp32_accumulator_values_per_variant']==150994944
    assert sum(c['count']*c['heads'] for c in commands)==contract['primary_heads_per_variant']==320
    assert [(x[0],x[2],x[3],x[4]) for x in v.MAIN]==[('cold_Q',0,0,16),('cold_K',1,0,16),('carried_Q',0,112,16),('carried_K',1,112,16)]


def public_records(tmp_path,monkeypatch,cases,records,suite='tail'):
    monkeypatch.setattr(v,'Cases',lambda root:cases)
    # Keep public inventory strict; boundary is a complete one-token K command.
    path=tmp_path/'trace.jsonl.gz'
    with gzip.open(path,'wt') as stream:
        for r in records: stream.write(json.dumps(r)+'\n')
    return v.verify_trace(path,tmp_path,suite=suite)


def test_public_full_shorttail_gzip_and_whole_wall_interval(tmp_path,monkeypatch,cases):
    records=list(complete_records(transaction(begin('boundary','legal_exact_1p5MiB_end'),cases)))
    result=public_records(tmp_path,monkeypatch,cases,records,'boundary')
    t=result['terminals'][0]
    assert t['accepted_to_done_cycles']==next(r['cycle'] for r in records if r['event']=='done')-records[1]['cycle']+1
    assert t['fixed_matrix_lanes']==512 and not t['whole_block_metric']
    assert t['useful_fma']==524288 and 0<t['candidate_useful_wall_fraction']<1
    assert result['matrix_lanes_checked_per_packet']==512
    for event,field,value in [('dma_ack','cycle',0),('dma_ack','transaction',9),('begin','transaction',2)]:
        with pytest.raises(ValueError): public_records(tmp_path,monkeypatch,cases,mutate(records,event,field,value),'boundary')
    with pytest.raises(ValueError): public_records(tmp_path,monkeypatch,cases,records[:-1],'boundary')


def test_collapsed_hardware_cycles_cannot_forge_utilization(tmp_path,monkeypatch,cases):
    records=complete_records(transaction(begin('boundary','legal_exact_1p5MiB_end'),cases))
    collapsed=({**r,'cycle':1} if 'cycle' in r else r for r in records)
    with pytest.raises(ValueError): public_records(tmp_path,monkeypatch,cases,collapsed,'boundary')


@pytest.mark.parametrize('field,value',[('transaction',True),('cycle',1.0),('index','0'),('error',2),('extra',0)])
def test_exact_json_schema_types_and_error_bits(field,value):
    r=packet('dma_ack',transaction=1,cycle=1,index=0,error=0)
    with pytest.raises(ValueError): v._record(json.dumps({**r,field:value})+'\n')


@pytest.mark.parametrize('line',[
    '{"event":"done","event":"done","transaction":1,"cycle":1,"status":0}\n',
    '{"event":"done","transaction":1,"cycle":NaN,"status":0}\n',
    '{"event":"done","transaction":1,"cycle":1,"status":0}', '[]\n','{}\n','\n',
])
def test_malformed_duplicate_or_truncated_json_rejected(line):
    with pytest.raises(ValueError): v._record(line)


@pytest.mark.parametrize('name,heads,packets',[('cold_Q',128,131072),('carried_K',32,16384)])
def test_full_primary_role_geometry_gate_and_absolute_trig(cases,name,heads,packets):
    result=consume(complete_records(transaction(begin('main',name),cases)),cases)
    assert result.completed_heads==heads and result.completed_tokens==16
    assert result.counts['matrix']==packets
    assert result.counts['l2_ack']==heads*(32 if name=='cold_Q' else 24)


def test_active_rows_cannot_be_swapped_or_repeated(cases):
    prefix=[]
    for r in complete_records(transaction(begin(name='tail_3'),cases)):
        prefix.append(r)
        if r['event']=='matrix': break
    word=int(prefix[-1]['fp32_rows'],16);mask=(1<<1024)-1
    row0=word&mask;row2=(word>>2048)&mask
    assert row0!=row2
    for changed in ((word&~(mask|(mask<<2048)))|(row2)|(row0<<2048),
                    (word&~(mask<<2048))|(row0<<2048)):
        altered=prefix[:-1]+[{**prefix[-1],'fp32_rows':f'{changed:04096x}'}]
        with pytest.raises(ValueError,match='row mismatch'):consume(altered,cases)


def test_tile_major_gather_and_strided_ddr_rows_are_not_compact(cases):
    records=list(complete_records(transaction(begin(name='tail_3'),cases)))
    i=next(i for i,r in enumerate(records) if r['event']=='l2_read' and r['region']==0 and r['byte_address']==0x40000+1024)
    altered=records[:i]+[{**records[i],'byte_address':0x40000+64}]+records[i+1:]
    with pytest.raises(ValueError,match='read order/address'):consume(altered,cases)
    i=next(i for i,r in enumerate(records) if r['event']=='dma_data' and r['source']=='0000000000040040')
    wrong_destination=f"{int(records[i]['destination'],16)-1024+64:016x}"
    for fields in ({'destination':wrong_destination},{'data':records[i-1]['data']}):
        with pytest.raises(ValueError):consume(records[:i]+[{**records[i],**fields}]+records[i+1:],cases)


@pytest.mark.parametrize('request_event,response',[('descriptor_request','descriptor'),('dma','dma_ack'),('l2_read','l2_response')])
def test_request_response_cannot_forge_zero_latency(short,cases,request_event,response):
    req=next(r for r in short if r['event']==request_event)
    with pytest.raises(ValueError,match='response before request'):
        consume(mutate(short,response,'cycle',req['cycle']),cases)


def test_same_cycle_write_ack_allowed_but_duplicated_channel_cycle_rejected(short,cases):
    req=next(r for r in short if r['event']=='l2_write')
    assert consume(mutate(short,'l2_ack','cycle',req['cycle']),cases).completed_heads==2
    first=next(r for r in short if r['event']=='matrix')
    with pytest.raises(ValueError,match='one channel/cycle'):
        consume(mutate(short,'matrix','cycle',first['cycle'],1),cases)
    with pytest.raises(ValueError,match='cycle denominator'):
        consume(mutate(short,'terminal','command_cycles',1),cases)


def test_earlier_row_flags_survive_later_exact_rows(cases):
    modified={}
    for case in (8,18,28,9,19,29):
        ex=cases[case]
        modified[case]={**ex,'norm_trace':{**ex['norm_trace'],'aggregate_flags':int(case==8)}}
    records=list(complete_records(transaction(begin(name='tail_3'),modified)))
    assert consume(records,modified).flags==1
    with pytest.raises(ValueError,match='head flags'):
        consume(mutate(records,'head_done','flags',0,1),modified)
    with pytest.raises(ValueError,match='shape/flags'):
        consume(mutate(records,'terminal','flags',0),modified)


def test_live_vector_loader_extent_byte_order_and_arithmetic_links(tmp_path,cases):
    ex=cases[9];folder=tmp_path/'case9';folder.mkdir()
    for name in ('projected_fp32','projected','norm','rope','activation','weight','norm_weight','trig'):
        width=8 if name=='projected_fp32' else 4
        (folder/(name+'.memh')).write_text(''.join(f'{int(x):0{width}x}\n' for x in ex[name]))
    ex['steps'].astype('<u4').tofile(folder/'projected_steps.bin')
    got=v.load_case(tmp_path,9,{})
    assert got['columns']==256 and np.array_equal(got['steps'],ex['steps'])
    for name in ('projected_fp32','projected','norm','rope'):
        path=folder/(name+'.memh');original=path.read_text();width=8 if name=='projected_fp32' else 4
        for bad in (original[:-1],original+'0'*width+'\n','0'*width+'\n'+original.split('\n',1)[1]):
            path.write_text(bad)
            with pytest.raises(ValueError):v.load_case(tmp_path,9,{})
        path.write_text(original)
    path=folder/'projected_steps.bin';original=path.read_bytes()
    for bad in (original[:-1],original+b'\x00',original[:1023*32*4]+b'\x00'*4+original[1023*32*4+4:]):
        path.write_bytes(bad)
        with pytest.raises(ValueError):v.load_case(tmp_path,9,{})
    path.write_bytes(original)
    for case in (-1,322,True):
        with pytest.raises(ValueError):v.load_case(tmp_path,case,{})


def test_case_cache_is_bounded_and_reloads_evicted_case(monkeypatch,tmp_path):
    calls=[];weights_ids=[]
    def load(root,case,weights):
        calls.append(case);weights_ids.append(id(weights));return {'case':case}
    monkeypatch.setattr(v,'load_case',load)
    cache=v.Cases(tmp_path)
    for case in range(41):assert cache[case]['case']==case
    assert len(cache.cache)==40 and calls==list(range(41))
    assert cache[40]['case']==40 and len(calls)==41
    assert cache[0]['case']==0 and calls[-1]==0 and len(calls)==42
    assert len(set(weights_ids))==1
