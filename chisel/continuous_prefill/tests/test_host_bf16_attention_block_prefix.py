"""Bounded recorder/CLI checks against a tiny mock, never a production DUT run."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

import pytest

HERE = Path(__file__).resolve().parent
DRIVER = HERE / 'host_bf16_attention_block.cpp'
PREFIX = HERE / 'host_attention_block_prefix.h'


def run(args):
    return subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=30)


@pytest.fixture(scope='module')
def binaries(tmp_path_factory):
    if not shutil.which('g++'):
        pytest.skip('bounded mock test requires g++')
    root = tmp_path_factory.mktemp('attention-block-prefix-mock')
    source = DRIVER.read_text() + PREFIX.read_text() + (HERE / 'host_physical_axi.h').read_text()
    ports = set(re.findall(r'\bd\.(\w+)', source)) - {'eval', 'PORT', 'io_launch_bits_regions_', 'io_axi_'}
    ports.update(re.findall(r'PREFIX_PORT\("[^"]+",(\w+)\)', source))
    for i in range(4):
        ports.update(f'io_launch_bits_regions_{i}_{k}' for k in ('base', 'limit', 'read', 'write'))
    for channel in ('ar', 'aw', 'w', 'r', 'b'):
        ports.update(f'io_axi_{channel}_{k}' for k in ('valid', 'ready'))
    for channel in ('ar', 'aw'):
        ports.update(f'io_axi_{channel}_bits_{k}' for k in ('addr', 'id', 'len', 'size', 'burst'))
    arrays = {'io_axi_r_bits_data', 'io_axi_w_bits_data'}
    declarations = '\n'.join(f'uint64_t {p}=0;' for p in sorted(ports - arrays))
    declarations += '\n' + '\n'.join(f'std::array<uint32_t,16> {p}{{}};' for p in sorted(arrays))
    (root / 'VHostBlockTop.h').write_text('#pragma once\n#include <array>\n#include <cstdint>\n'
        'struct VHostBlockTop {\n' + declarations + '\nvoid eval(){}\n};\n')
    (root / 'verilated.h').write_text('struct Verilated {static void commandArgs(int,char**) {}};\n')
    flags = ['g++', '-O2', '-std=c++17', '-ffp-contract=off', '-fno-fast-math', '-I', root, '-I', HERE]
    for name, source in (('mock', HERE / 'attention_block_prefix_mock.cpp'), ('driver-syntax', DRIVER)):
        result = run([*flags, source, '-o', root / name])
        assert result.returncode == 0, result.stderr
    return root


def execute(binaries, tmp_path, name, limit='111', variant='normal'):
    out = tmp_path / name
    result = run([binaries / 'mock', out, limit, variant])
    assert result.returncode == 0, result.stderr
    report = json.loads((out / 'prefix.json').read_text()) if limit != '0' else None
    events = (out / 'prefix_events.jsonl').read_bytes() if limit != '0' else None
    return out, result.stdout, report, events


def test_default_off_and_stop_after_ack_bookkeeping(binaries, tmp_path):
    base, baseline, _, _ = execute(binaries, tmp_path, 'disabled', '0')
    out, observed, report, data = execute(binaries, tmp_path, 'enabled')
    assert list(base.iterdir()) == []
    assert {p.name for p in out.iterdir()} == {'prefix.json', 'prefix_events.jsonl'}
    assert baseline == observed
    assert json.loads(observed)['eval_calls'] == 333
    assert report['schema'] == 'HOST_ATTENTION_BLOCK_PREFIX_V1'
    assert report['status'] == 'BOUNDED_DIAGNOSTIC_PREFIX'
    assert report['numerical_acceptance'] is False and report['prefix_reached'] is True
    assert report['cycles'] == report['cycle_limit'] == 111
    assert report['constructor_cycles'] == 36 and report['step_elapsed_ns'] > 0
    d = report['deterministic']
    assert report['memory_hash_is_noncryptographic'] is True
    assert d['memory_bytes'] == 256
    assert d['memory_fnv1a64'] == f"{json.loads(observed)['memory_fnv1a64']:016x}"
    assert (d['reset_cycles'], d['active_cycles']) == (6, 75)
    assert [d[c + '_handshakes'] for c in ('ar', 'aw', 'w', 'r', 'b')] == [1, 1, 2, 2, 1]
    end = d['terminal_event']
    assert end['pre_b_valid'] == end['pre_b_ready'] == 1
    assert end['end_write_acks'] == 2 and end['end_ack_bytes'] == end['end_physical_bytes'] == 128
    assert end['end_pending_valid'] == end['end_committing_beats'] == 0
    rows = [json.loads(line) for line in data.splitlines()]
    assert rows[0]['payload_encoding'] == 'le_u32x16_hex'
    assert [x['cycle'] for x in rows[1:]] == list(range(1, 112))
    assert any(x['pre_r_valid'] and not x['pre_r_ready'] for x in rows[1:])
    assert any(x['pre_b_valid'] and not x['pre_b_ready'] for x in rows[1:])
    assert not any('payload_le_hex' in key for key in end)
    assert rows[-1] == {**end, 'pre_w_payload_le_hex': '', 'pre_r_payload_le_hex': ''}
    assert report['event_bytes'] == len(data)
    fnv = 14695981039346656037
    for byte in data:
        fnv = ((fnv ^ byte) * 1099511628211) & ((1 << 64) - 1)
    assert report['prefix_fnv1a64'] == f'{fnv:016x}'


def test_payload_bits_and_timing_independent_trace(binaries, tmp_path):
    _, stdout, report, events = execute(binaries, tmp_path, 'normal')
    _, slow_stdout, slow_report, slow_events = execute(binaries, tmp_path, 'slow', variant='slow')
    assert stdout == slow_stdout and events == slow_events
    assert report['deterministic'] == slow_report['deterministic']
    assert slow_report['step_elapsed_ns'] > report['step_elapsed_ns']
    normal = [json.loads(line) for line in events.splitlines()][1:]
    for channel, variant in (('r', 'read'), ('w', 'write')):
        _, changed_stdout, changed_report, changed = execute(binaries, tmp_path, variant, variant=variant)
        assert hashlib.sha256(changed).digest() != hashlib.sha256(events).digest()
        assert changed_report['prefix_fnv1a64'] != report['prefix_fnv1a64']
        memory_hash = changed_report['deterministic']['memory_fnv1a64']
        assert memory_hash == f"{json.loads(changed_stdout)['memory_fnv1a64']:016x}"
        assert memory_hash != report['deterministic']['memory_fnv1a64']
        changed_rows = [json.loads(line) for line in changed.splitlines()][1:]
        first = next(x for x in normal if x[f'pre_{channel}_valid'])
        altered = changed_rows[first['cycle'] - 1]
        raw = bytes.fromhex(first[f'pre_{channel}_payload_le_hex'])
        altered_raw = bytes.fromhex(altered[f'pre_{channel}_payload_le_hex'])
        assert len(raw) == len(altered_raw) == 64
        assert altered_raw == bytes([raw[0] ^ 1]) + raw[1:]


def test_minimum_cap_and_incomplete_low_eval_are_distinct(binaries, tmp_path):
    _, stdout, report, _ = execute(binaries, tmp_path, 'minimum', '37')
    assert json.loads(stdout)['ticks'] == report['cycles'] == 37
    assert report['deterministic']['active_cycles'] == 1
    out = tmp_path / 'failed-low'
    failed = run([binaries / 'mock', out, '111', 'fail-low'])
    assert failed.returncode == 1 and 'synthetic final low eval failure' in failed.stderr
    assert not (out / 'prefix.json').exists()


@pytest.mark.parametrize('value', ['0', '36', '65537', '-1', '+4096', ' 4096', '4096 ', '4e3', '1.0', '0x1000', '99999999999999999', '٤٠٩٦', ''])
def test_driver_rejects_malformed_limit_before_fixture(binaries, tmp_path, value):
    out = tmp_path / 'must-not-exist'
    result = run([binaries / 'driver-syntax', tmp_path / 'no-fixture', out, 'pass', '--diagnostic-prefix=' + value])
    assert result.returncode == 1 and 'diagnostic prefix' in result.stderr
    assert not out.exists() and 'HOST_ATTN_BLOCK_PAIR' not in result.stdout


def test_normal_cli_and_valid_prefix_still_require_real_fixture(binaries, tmp_path):
    for args in ([], ['pass'], ['final-residual-ack-error'], ['--diagnostic-prefix=37'], ['pass', '--diagnostic-prefix=65536']):
        result = run([binaries / 'driver-syntax', tmp_path / 'no-fixture', tmp_path / 'absent', *args])
        assert result.returncode == 1 and 'physical aperture/contract' in result.stderr
        assert 'HOST_ATTN_BLOCK_PAIR' not in result.stdout
    for args in (['--diagnostic-prefix'], ['pass', '--diagnostic-prefix=37', 'extra'], ['prefix']):
        result = run([binaries / 'driver-syntax', tmp_path / 'no-fixture', tmp_path / 'absent', *args])
        assert result.returncode == 1
