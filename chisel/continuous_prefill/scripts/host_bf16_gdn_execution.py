#!/usr/bin/env python3
"""Audit actual Host Dense0/Conv0/Dense1/Conv1 execution artifacts.

The driver PASS marker is not authority. Replay every successful physical write
ACK from the raw actual files, check its source-authenticated canonical bytes,
and compare every completion snapshot and the complete final DDR image. A
standalone artifact audit does not authenticate a DUT; run_case also binds the
production binary, RTL and build sources before and after bounded execution.

Importing this module neither captures a model nor builds/runs a DUT. Persisted
receipts cannot replace an in-process, independently authenticated authority.
"""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import math
import subprocess
import sys
import weakref
import numpy as np

from host_bf16_gdn_descriptor import (CHANNELS, TAPS, HIDDEN,
    HostGdnDenseBinding, HostGdnConvBinding, build_gdn_commands,
    parse_host_gdn_descriptor)
from host_bf16_qkv_execution import require, sha, _expect, _native_metrics as _qkv_native_metrics
from pack_host_bf16_gdn_fixture import ROOT, GdnFixtureSession, _sources, conv_recipe, ulp_metric
from verify_host_bf16_gdn_fixture import verify

BUILD_STATUS = 'BUILT_HOST_GDN_DENSE_CONV_ONLY_NOT_NUMERICAL_PASS'
SCOPE = 'DENSE_QKV_CONV4_SILU_ONLY'
MODES = ('pass', 'last-history-ack-error', 'activation-read-error',
         'weight-read-error', 'output-alias', 'reset-recovery')
PREFIX = 'HOST_BF16_GDN_'
OPERATIONS = ('dense0', 'conv0', 'dense1', 'conv1')
OUTPUT_BYTES = CHANNELS * 2
HISTORY_BYTES = OUTPUT_BYTES * TAPS
SCHEMA = {
    'BEGIN': 'run mode commands epoch',
    'WRITE_REQUEST': 'run pc cycle address bytes final',
    'WRITE_ACK': 'run pc cycle address bytes error final',
    'COMPLETION_HOLD': 'run pc cycle word',
    'COMMAND': 'run cycle operation pc status signal write_ack_bytes published previous_outputs_preserved guards_unchanged',
    'NATIVE': 'run stage elements bit_differences max_abs mean_abs same_input_bit_differences same_input_numeric_differences same_input_max_bf16_ulp signed_zero_numeric_equal gate',
    'PASS': 'run scope commands tokens checked_bf16 canonical_bit_differences independent_terminal_checked native_operator_gate cycles write_ack_bytes metadata_reads logical_matrix_engines physical_matrix_slices idma_instances shared_scalar_services unchanged_guards prior_outputs_preserved delayed_final_ack_commands completion_backpressure_commands actual_dma_intermediate_sources history_generations output_spans input_norm_dut full_block_supported',
    'FAULT_PASS': 'run mode failed_pc status successful_commands write_ack_bytes published_bytes failed_command_published_bytes previous_outputs_preserved guards_unchanged',
    'END': 'run status result_epoch result_pc completions successful issued_jobs metadata_reads read_beats read_ack_beats write_beats write_ack_beats published_bytes reset_required',
    'RESET_RECOVERY_PASS': 'same_dut unchanged_input_constants expected_output_injection commands',
}


def _fixture_path(fixture):
    fixture = Path(fixture)
    require(not fixture.is_symlink(), 'fixture root symlink')
    fixture = fixture.resolve()
    require(fixture.is_relative_to(ROOT / 'work') and fixture != ROOT / 'work'
            and fixture.is_dir(), 'fixture must be under ignored work')
    return fixture


def _fixture_bytes(fixture):
    paths = list(fixture.iterdir())
    require(paths and all(p.is_file() and not p.is_symlink() for p in paths),
            'fixture file inventory/symlink')
    return {p.name: p.read_bytes() for p in paths}


def _source_identity(fixture, manifest):
    """Recheck producers and actual checkpoint payloads without model execution."""
    sources = _sources()
    require(sources == manifest['source_sha256'], 'producer source changed')
    identity = {str(ROOT / name): digest for name, digest in sources.items()}
    for name in ('host_bf16_gdn_execution.py', 'verify_host_bf16_gdn_fixture.py',
                 'host_bf16_qkv_execution.py'):
        path = Path(__file__).with_name(name)
        identity[str(path)] = sha(path)
    # Locate the installed official implementation without importing Torch.
    package = importlib.util.find_spec('transformers')
    require(package is not None and package.origin is not None, 'missing official Transformers source')
    framework = Path(package.origin).parent / 'models/qwen3_5/modeling_qwen3_5.py'
    require(sha(framework) == manifest['framework_source_sha256'], 'official framework source changed')
    identity[str(framework)] = sha(framework)
    expected_payloads = {'qwen35_layer0_payload', 'qwen35_prefix_payload'}
    require(set(manifest['source_payload_manifest_sha256']) == expected_payloads,
            'source payload inventory drift')
    for name, expected in manifest['source_payload_manifest_sha256'].items():
        directory = ROOT / 'work' / name
        path = directory / 'manifest.json'
        require(not directory.is_symlink() and not path.is_symlink() and sha(path) == expected,
                'source payload manifest changed: ' + name)
        identity[str(path)] = expected
        payload = json.loads(path.read_text())
        for tensor in payload['tensors']:
            filename = tensor['file']
            require(type(filename) is str and Path(filename).name == filename,
                    'source tensor path escape')
            path = directory / filename
            require(path.is_file() and not path.is_symlink()
                    and path.stat().st_size == tensor['bytes'] and sha(path) == tensor['sha256'],
                    'source tensor bytes changed: ' + filename)
            identity[str(path)] = tensor['sha256']
    return identity


_ISSUED = weakref.WeakKeyDictionary()


class ExecutionSession:
    """Opaque process-local authority, issued only after source authentication."""
    __slots__ = ('__weakref__',)

    def __init__(self):
        raise TypeError('use authenticate_fixture')

    def verify(self, fixture):
        require(self in _ISSUED, 'unissued execution authority')
        original, frozen, sources, admitted = _ISSUED[self]
        fixture = _fixture_path(fixture)
        require(fixture == original, 'different authenticated fixture directory')
        require(_fixture_bytes(fixture) == frozen, 'authenticated fixture bytes/inventory changed')
        manifest = json.loads(frozen['manifest.json'])
        require(_source_identity(fixture, manifest) == sources, 'authenticated source identity changed')
        return copy.deepcopy(admitted)


def authenticate_fixture(fixture, *, session=None):
    """Authenticate once, then cheaply reuse immutable in-memory evidence.

    With no live GdnFixtureSession, the existing verifier performs one fresh
    bounded two-token recomputation. Neither a dict nor a disk receipt can skip
    that step. A genuine generator-issued session avoids recomputing it.
    """
    fixture = _fixture_path(fixture)
    require(session is None or type(session) is GdnFixtureSession,
            'live GdnFixtureSession required')
    frozen = _fixture_bytes(fixture)
    admitted = verify(fixture, session=session)
    require(admitted['status'] == 'PASS_AUTHENTICATED_HOST_GDN_FIXTURE'
            and admitted['native_gate_pass'] is True, 'source authentication failed')
    require(_fixture_bytes(fixture) == frozen, 'fixture changed during authentication')
    sources = _source_identity(fixture, json.loads(frozen['manifest.json']))
    authority = object.__new__(ExecutionSession)
    _ISSUED[authority] = (fixture, frozen, sources, copy.deepcopy(admitted))
    authority.verify(fixture)
    return authority


def _admit(fixture, session, authority):
    require(session is None or authority is None, 'supply one source authority')
    if authority is not None:
        require(type(authority) is ExecutionSession, 'issued ExecutionSession required')
        return authority, authority.verify(fixture)
    authority = authenticate_fixture(fixture, session=session)
    return authority, authority.verify(fixture)


def _layout(fixture):
    lines = (fixture / 'launch.txt').read_text().splitlines()
    require(len(lines) == 6 and lines[0] == 'HOST_GDN_DENSE_CONV_V1', 'launch format')
    fields = 'base limit cb cl commands db dl descriptors meta scratch dense_weight conv_weight initial_history'.split()
    values = list(map(int, lines[1].split()))
    require(len(values) == len(fields), 'launch header size')
    layout = dict(zip(fields, values))
    require(layout['commands'] == 4 and layout['descriptors'] == 60, 'GDN command inventory')
    require(0 <= layout['base'] < layout['meta'] < layout['scratch'] < layout['limit'] <= 1 << 56
            and all(layout[x] % 64 == 0 for x in ('base', 'limit', 'meta', 'scratch', 'cb', 'cl', 'db', 'dl')),
            'physical region geometry')
    commands = (fixture / 'host_commands.bin').read_bytes()
    descriptors = (fixture / 'host_descriptors.bin').read_bytes()
    require(len(commands) == layout['cl'] - layout['cb'] == 64
            and len(descriptors) == layout['dl'] - layout['db'] == 960, 'table geometry')
    require(layout['base'] <= layout['cb'] < layout['cl'] <= layout['db'] < layout['dl'] <= layout['meta'],
            'metadata physical allocation')
    records = {i: int.from_bytes(descriptors[i * 16:(i + 1) * 16], 'little') for i in range(60)}
    bindings = [parse_host_gdn_descriptor(int.from_bytes(commands[i * 16:(i + 1) * 16], 'little'), records)
                for i in range(4)]
    canonical_commands, canonical_records = build_gdn_commands(bindings)
    require(commands == b''.join(c.pack().to_bytes(16, 'little') for c in canonical_commands)
            and descriptors == b''.join(canonical_records[i].pack().to_bytes(16, 'little') for i in range(60)),
            'noncanonical command/descriptor dependency binding')
    names = 'token dense activation weight output history_in history_out records wait signal destination_root'.split()
    specs = []
    for pc, (line, binding, command) in enumerate(zip(lines[2:], bindings, canonical_commands)):
        values = list(map(int, line.split()))
        require(len(values) == len(names), 'launch operation fields')
        spec = dict(zip(names, values)); dense = type(binding) is HostGdnDenseBinding
        require(spec == dict(token=pc // 2, dense=int(dense), activation=binding.activation_ddr,
                    weight=binding.weight_ddr, output=binding.output_ddr,
                    history_in=0 if dense else binding.history_input_ddr,
                    history_out=0 if dense else binding.history_output_ddr,
                    records=12 if dense else 18, wait=pc, signal=pc + 1, destination_root=command.dst),
                'launch/descriptor operation binding')
        spec['name'] = OPERATIONS[pc]
        spec['spans'] = [(spec['name'], spec['output'], OUTPUT_BYTES)]
        if not dense:
            spec['spans'].append(('history' + str(pc // 2), spec['history_out'], HISTORY_BYTES))
        spec['bytes'] = sum(size for _, _, size in spec['spans'])
        spec['final_end'] = spec['spans'][-1][1] + spec['spans'][-1][2]
        require(all(layout['scratch'] <= address < address + size <= layout['limit']
                    for _, address, size in spec['spans']), 'output physical allocation')
        specs.append(spec)
    require(layout['dense_weight'] == specs[0]['weight'] == specs[2]['weight']
            and layout['conv_weight'] == specs[1]['weight'] == specs[3]['weight']
            and layout['initial_history'] == specs[1]['history_in'], 'launch constant binding')
    return layout, specs


def _initial(fixture, layout, specs, mode):
    memory = bytearray(bytes.fromhex('3cc35aa5') * ((layout['limit'] - layout['base']) // 4))
    def load(name, address, size, low, high):
        raw = (fixture / name).read_bytes()
        require(len(raw) == size and low <= address < address + size <= high, 'input physical allocation: ' + name)
        offset = address - layout['base']; memory[offset:offset + size] = raw
    for filename, start, end in (('host_commands.bin', 'cb', 'cl'), ('host_descriptors.bin', 'db', 'dl')):
        load(filename, layout[start], layout[end] - layout[start], layout['base'], layout['meta'])
    load('weight_dense.bf16le', layout['dense_weight'], HIDDEN * OUTPUT_BYTES, layout['meta'], layout['scratch'])
    load('weight_conv.bf16le', layout['conv_weight'], HISTORY_BYTES, layout['meta'], layout['scratch'])
    load('initial_history.bf16le', layout['initial_history'], HISTORY_BYTES, layout['meta'], layout['scratch'])
    for pc in (0, 2):
        load('activation' + str(pc // 2) + '.bf16le', specs[pc]['activation'], HIDDEN * 2, layout['meta'], layout['scratch'])
    if mode == 'output-alias':
        address = specs[1]['output']
        offset = layout['db'] + specs[2]['destination_root'] * 16 - layout['base']
        memory[offset + 7:offset + 13] = (address & ((1 << 48) - 1)).to_bytes(6, 'little')
        memory[offset + 15] = address >> 48
    return memory


def _canonical(fixture, specs):
    """Use authenticated integer/C Dense terminals and independently replay Conv."""
    values = {}
    weights = np.frombuffer((fixture / 'weight_conv.bf16le').read_bytes(), dtype='<u2').reshape(CHANNELS, TAPS)
    history = np.zeros((CHANNELS, TAPS), dtype='<u2')
    require((fixture / 'initial_history.bf16le').read_bytes() == history.tobytes(), 'cold history is not zero')
    for token in range(2):
        dense = (fixture / ('independent_dense' + str(token) + '.bf16le')).read_bytes()
        require(len(dense) == OUTPUT_BYTES, 'independent Dense terminal size')
        values['dense' + str(token)] = dense
        conv, output, history = conv_recipe(np.frombuffer(dense, dtype='<u2').reshape(1, CHANNELS), weights, history, token == 0)
        for prefix, result in (('conv', conv), ('output', output), ('history', history)):
            require((fixture / ('expected_' + prefix + str(token) + '.bf16le')).read_bytes() == result.tobytes(),
                    'independent Conv/history recipe mismatch: ' + prefix + str(token))
        values['conv' + str(token)] = output.tobytes()
        values['history' + str(token)] = history.tobytes()
    require(set(values) == {name for spec in specs for name, _, _ in spec['spans']}, 'canonical six-span inventory')
    return values


def _events(log):
    events = []
    for line in Path(log).read_text().splitlines():
        if not line.startswith(PREFIX):
            continue
        tokens = line.split(); kind = tokens[0][len(PREFIX):]
        require(kind in SCHEMA, 'unknown/failure driver event: ' + kind)
        fields = [token.split('=', 1) for token in tokens[1:]]
        require(all(len(pair) == 2 for pair in fields), 'malformed driver event')
        data = dict(fields)
        require(len(data) == len(fields) and set(data) == set(SCHEMA[kind].split()),
                'duplicate/unknown/missing event fields: ' + kind)
        events.append((kind, data))
    require(events, 'missing driver events')
    return events


def _metric(actual, native):
    require(len(actual) == len(native) and len(actual) > 0 and len(actual) % 2 == 0, 'native output geometry')
    return _qkv_native_metrics(actual, native, len(actual) // 2, 1, 'gdn')['gdn']


def _native(fixture, name, actual):
    if name.startswith('dense'):
        native_name = 'native_dense' + name[-1]
    elif name.startswith('history'):
        native_name = 'native_history' + name[-1]
    else:
        native_name = 'native_output' + name[-1]
    result = _metric(actual, (fixture / (native_name + '.bf16le')).read_bytes())
    result.update(same_input_bit_differences=0, same_input_numeric_differences=0,
                  same_input_max_bf16_ulp=0, signed_zero_numeric_equal=1)
    if name.startswith('conv'):
        target = (fixture / ('conditioned_output' + name[-1] + '.bf16le')).read_bytes()
        require(len(target) == len(actual), 'conditioned output geometry')
        conditioned = ulp_metric(np.frombuffer(actual, dtype='<u2'), np.frombuffer(target, dtype='<u2'))
        result.update(same_input_bit_differences=conditioned['bit_mismatches'],
                      same_input_numeric_differences=conditioned['numeric_mismatches'],
                      same_input_max_bf16_ulp=conditioned['max_bf16_ulp'])
        require(conditioned['pass_'], 'unchanged same-input one-BF16-ULP threshold failed: ' + name)
    require(result['gate'] == 'PASS', 'unchanged native operator threshold failed: ' + name)
    return result


def verify_execution(fixture, outputs, log, mode, *, session=None, authority=None):
    """Audit artifacts only; reuse a genuine session or authenticate independently."""
    fixture, outputs, log = map(Path, (fixture, outputs, log))
    require(mode in MODES, 'unknown execution mode')
    authority, admitted = _admit(fixture, session, authority)
    fixture = _fixture_path(fixture)
    manifest = json.loads((fixture / 'manifest.json').read_text())
    layout, specs = _layout(fixture)
    canonical = _canonical(fixture, specs)
    require(log.is_file() and not log.is_symlink(), 'execution log file/symlink')
    log_identity = sha(log)
    events = _events(log); cursor = 0; reports = []
    modes = [mode, 'pass'] if mode == 'reset-recovery' else [mode]
    for run_id, run_mode in enumerate(modes):
        directory = outputs if run_id == 0 else outputs / 'recovery'
        require(directory.is_dir() and not directory.is_symlink(), 'missing actual output directory')
        require(all(p.is_file() or p.is_dir() for p in directory.iterdir())
                and all(not p.is_symlink() for p in directory.iterdir()), 'output artifact symlink/special file')
        artifact_identity = {p.name: sha(p) for p in directory.iterdir() if p.is_file()}
        expected = _initial(fixture, layout, specs, run_mode)
        actuals, references = {}, {}
        for spec in specs:
            name = spec['name']
            references[name] = (directory / ('reference_' + name + '.bf16le')).read_bytes()
            require(references[name] == canonical[name], 'C++ reference differs from independent canonical: ' + name)
            for span, _, size in spec['spans']:
                actuals[span] = (directory / ('actual_' + span + '.bf16le')).read_bytes()
                require(len(actuals[span]) == size, 'actual six-span output length: ' + span)
        require(cursor < len(events) and events[cursor][0] == 'BEGIN', 'missing/duplicate BEGIN')
        _expect(events[cursor][1], run=run_id, mode=run_mode, commands=4, epoch=9 + run_id); cursor += 1
        failed_pc = 2 if run_mode == 'output-alias' else 0 if run_mode == 'reset-recovery' else 3
        successful = 4 if run_mode == 'pass' else failed_pc
        expected_completions = 4 if run_mode == 'pass' else failed_pc + 1
        pc = 0; pending = None; last_cycle = -1; held_word = None
        ack_bytes = [0] * 4; requested = [[] for _ in range(4)]; final_acks = [0] * 4
        holds = [0] * 4; last_hold_cycle = [-1] * 4; error_acks = 0
        snapshots = {}; native_events = {}; metrics = {}; history_metrics = {}; summary = None; end = None
        while cursor < len(events):
            kind, data = events[cursor]; cursor += 1
            require(kind not in ('BEGIN', 'RESET_RECOVERY_PASS'), 'missing END before new run')
            _expect(data, run=run_id)
            if kind in ('WRITE_REQUEST', 'WRITE_ACK', 'COMPLETION_HOLD', 'COMMAND'):
                require(summary is None and pc < expected_completions and int(data['pc']) == pc,
                        'missing/duplicate/out-of-order command event')
                cycle = int(data['cycle'])
                require(cycle >= last_cycle and cycle >= 0, 'event cycle reversal'); last_cycle = cycle
            if kind == 'WRITE_REQUEST':
                require(pending is None and held_word is None and error_acks == 0 and final_acks[pc] == 0,
                        'overlapping/write after terminal ACK or held completion')
                spec = specs[pc]; address = int(data['address']); size = int(data['bytes'])
                spans = [(name, lo, size_) for name, lo, size_ in spec['spans']
                         if lo <= address < address + size <= lo + size_]
                require(address % 64 == 0 and size % 64 == 0 and 0 < size <= 1024 and len(spans) == 1,
                        'write outside exact physical output/history span')
                require((address & 4095) + size <= 4096, 'write burst crosses 4K boundary')
                require(all(address + size <= lo or hi <= address for lo, hi in requested[pc]),
                        'duplicate/overlapping physical write')
                _expect(data, final=int(address + size == spec['final_end']))
                require(run_mode != 'output-alias' or pc < failed_pc, 'alias command issued a physical write')
                requested[pc].append((address, address + size)); pending = (data, spans[0])
            elif kind == 'WRITE_ACK':
                require(pending is not None, 'ACK without actual write request')
                request, span = pending
                for key in ('pc', 'address', 'bytes', 'final'):
                    require(data[key] == request[key], 'ACK/request identity mismatch')
                require(cycle > int(request['cycle']), 'early write ACK')
                if data['final'] == '1':
                    require(cycle - int(request['cycle']) >= 53, 'final ACK delay not exercised')
                require(data['error'] in ('0', '1'), 'invalid ACK error flag')
                address, size = int(data['address']), int(data['bytes'])
                if data['error'] == '1':
                    require(run_mode == 'last-history-ack-error' and pc == 3
                            and data['final'] == '1' and span[0] == 'history1' and error_acks == 0,
                            'unexpected/repeated write fault')
                    error_acks += 1
                else:
                    name, lo, _ = span; source = address - lo
                    raw = actuals[name][source:source + size]
                    require(raw == canonical[name][source:source + size],
                            'ACKed actual bytes differ from independent canonical: ' + name)
                    offset = address - layout['base']; expected[offset:offset + size] = raw
                    ack_bytes[pc] += size; final_acks[pc] += data['final'] == '1'
                pending = None
            elif kind == 'COMPLETION_HOLD':
                require(pending is None, 'completion exposed before write ACK')
                require(cycle > last_hold_cycle[pc], 'duplicate/non-increasing completion hold cycle')
                last_hold_cycle[pc] = cycle
                ok = pc < successful; status = 0 if ok else 9 if run_mode == 'output-alias' else 3
                engine = 2 if specs[pc]['dense'] else 3
                word = int(data['word']); expected_word = pc | engine << 29 | status << 32 | (pc + 1) << 40
                require(word == expected_word and (held_word is None or held_word == word),
                        'held completion identity changed')
                if ok:
                    require(ack_bytes[pc] == specs[pc]['bytes'] and final_acks[pc] == 1,
                            'completion visible before final ACK')
                held_word = word; holds[pc] += 1
            elif kind == 'COMMAND':
                require(pending is None and holds[pc] >= 11, 'publication before ACK/completion backpressure coverage')
                require(cycle > last_hold_cycle[pc], 'completion accepted before held cycle ended')
                ok = pc < successful; status = 0 if ok else 9 if run_mode == 'output-alias' else 3
                _expect(data, operation=specs[pc]['name'], status=status, signal=pc + 1,
                        write_ack_bytes=ack_bytes[pc], published=int(ok), previous_outputs_preserved=1, guards_unchanged=1)
                if ok:
                    require(ack_bytes[pc] == specs[pc]['bytes'] and final_acks[pc] == 1,
                            'successful completion before exact final ACK')
                elif run_mode != 'last-history-ack-error':
                    require(ack_bytes[pc] == 0 and not requested[pc], 'read/alias fault changed failed output')
                else:
                    require(error_acks == 1 and ack_bytes[pc] < specs[pc]['bytes']
                            and sum(hi - lo for lo, hi in requested[pc]) == specs[pc]['bytes'],
                            'last history ACK fault scope')
                snapshot = directory / ('writable_after_command' + str(pc) + '.bin')
                require(snapshot.read_bytes() == expected[layout['scratch'] - layout['base']:],
                        'physical coexistence/guard snapshot mismatch at command ' + str(pc))
                snapshots[snapshot.name] = sha(snapshot); pc += 1; held_word = None
            elif kind == 'NATIVE':
                require(run_mode == 'pass' and pc == 4 and summary is None
                        and data['stage'] in OPERATIONS and data['stage'] not in native_events,
                        'native event out of scope/repeated')
                native_events[data['stage']] = data
            elif kind in ('PASS', 'FAULT_PASS'):
                require(summary is None and pc == expected_completions and pending is None,
                        'premature/duplicate summary')
                require(kind == ('PASS' if run_mode == 'pass' else 'FAULT_PASS'), 'wrong result kind')
                summary = data
            elif kind == 'END':
                require(summary is not None and pending is None and pc == expected_completions,
                        'early/missing result termination')
                end = data; break
            else:
                raise ValueError('unexpected event ' + kind)
        require(end is not None, 'missing END')
        published = sum(specs[i]['bytes'] for i in range(successful))
        metadata = sum(1 + specs[i]['records'] for i in range(expected_completions))
        status = 0 if run_mode == 'pass' else 9 if run_mode == 'output-alias' else 3
        _expect(end, status=status, result_epoch=9 + run_id, result_pc=expected_completions - 1,
                completions=expected_completions, successful=successful,
                issued_jobs=2 if run_mode == 'output-alias' else expected_completions,
                metadata_reads=metadata, published_bytes=published, reset_required=int(run_mode != 'pass'))
        require(int(end['read_beats']) == int(end['read_ack_beats']) >= metadata
                and int(end['write_beats']) == int(end['write_ack_beats'])
                == sum(hi - lo for spans in requested for lo, hi in spans) // 64, 'ACK beat accounting')
        final = directory / 'ddr_after.bin'
        require(final.read_bytes() == expected, 'final physical DDR/source/guard/output mismatch')
        for index, spec in enumerate(specs):
            for name, address, size in spec['spans']:
                offset = address - layout['base']
                require(actuals[name] == expected[offset:offset + size], 'actual file not actual physical DDR: ' + name)
                if index < successful:
                    require(actuals[name] == canonical[name], 'canonical actual mismatch: ' + name)
                    target = history_metrics if name.startswith('history') else metrics
                    target[name] = _native(fixture, name, actuals[name])
        if run_mode == 'pass':
            require(set(native_events) == set(metrics) == set(OPERATIONS), 'missing native comparisons')
            for stage, result in metrics.items():
                observed = native_events[stage]
                _expect(observed, **{key: value for key, value in result.items() if key not in ('max_abs', 'mean_abs')})
                for key in ('max_abs', 'mean_abs'):
                    require(math.isfinite(float(observed[key]))
                            and math.isclose(float(observed[key]), result[key], rel_tol=1e-12, abs_tol=0.0),
                            'native metric not actual raw output')
            _expect(summary, scope=SCOPE, commands=4, tokens=2, checked_bf16=73728,
                    canonical_bit_differences=0, independent_terminal_checked=1, native_operator_gate='PASS',
                    write_ack_bytes=sum(ack_bytes), metadata_reads=metadata, logical_matrix_engines=1,
                    physical_matrix_slices=8, idma_instances=1, shared_scalar_services=1, unchanged_guards=1,
                    prior_outputs_preserved=1, delayed_final_ack_commands=4, completion_backpressure_commands=4,
                    actual_dma_intermediate_sources=1, history_generations=2, output_spans=6,
                    input_norm_dut=0, full_block_supported=0)
            require(int(summary['cycles']) > 0, 'missing actual cycles')
        else:
            _expect(summary, mode=run_mode, failed_pc=failed_pc, status=status, successful_commands=successful,
                    write_ack_bytes=sum(ack_bytes), published_bytes=published, failed_command_published_bytes=0,
                    previous_outputs_preserved=1, guards_unchanged=1)
            require(not native_events, 'fault run claimed complete native pass')
        expected_files = {'ddr_after.bin'} | set(snapshots)
        expected_files |= {'actual_' + name + '.bf16le' for name in canonical}
        expected_files |= {'reference_' + name + '.bf16le' for name in OPERATIONS}
        expected_dirs = {'recovery'} if mode == 'reset-recovery' and run_id == 0 else set()
        require({p.name for p in directory.iterdir() if p.is_file()} == expected_files
                and {p.name for p in directory.iterdir() if p.is_dir()} == expected_dirs,
                'output artifact inventory drift')
        require({p.name: sha(p) for p in directory.iterdir() if p.is_file()} == artifact_identity,
                'execution artifact changed during verification')
        reports.append(dict(run=run_id, mode=run_mode, status=status, successful_commands=successful,
            write_ack_bytes=sum(ack_bytes), published_bytes=published, metadata_reads=metadata,
            native=metrics, native_history=history_metrics,
            actual_sha256={name: sha(directory / ('actual_' + name + '.bf16le')) for name in canonical},
            reference_sha256={name: sha(directory / ('reference_' + name + '.bf16le')) for name in OPERATIONS},
            ddr_after_sha256=sha(final), writable_snapshot_sha256=snapshots,
            physical_ddr_bytes_checked=len(expected), physical_write_requests=sum(map(len, requested)),
            readonly_and_guard_bytes_checked=len(expected) - sum(ack_bytes), independent_terminal_checked=True,
            output_spans=6, write_ack_bytes_per_command=ack_bytes, final_ack_per_command=final_acks,
            completion_hold_cycles=holds, raw_read_address_trace_available=False))
    if mode == 'reset-recovery':
        require(cursor < len(events) and events[cursor][0] == 'RESET_RECOVERY_PASS', 'missing same-DUT reset result')
        _expect(events[cursor][1], same_dut=1, unchanged_input_constants=1, expected_output_injection=0, commands=4)
        cursor += 1
    require(cursor == len(events), 'unexpected/duplicate trailing execution event')
    authority.verify(fixture)
    require(sha(log) == log_identity, 'execution log changed during verification')
    return dict(status='PASS_HOST_GDN_ARTIFACT_CHECK_ONLY', actual_dut_identity_verified=False,
                numerical_acceptance_eligible=True, scope=SCOPE, mode=mode, runs=reports,
                fixture_sha256=sha(fixture / 'manifest.json'), log_sha256=sha(log),
                input_sha256={p.name: sha(p) for p in fixture.iterdir()}, source_admission=admitted,
                full_block_supported=False, input_norm_dut=False,
                native_full_block_status=manifest['native_full_block_status'])


def _build_identity(build):
    ready = json.loads((build / 'build_ready.json').read_text())
    require(ready['status'] == BUILD_STATUS and ready['numerical_pass'] is False,
            'expected GDN build-only receipt')
    require(ready['experimental_default_off'] is True and ready['operations'] == ['dense_qkv', 'conv4_silu']
            and ready['full_block_supported'] is False and ready['scalar_service_shared'] is True,
            'GDN build scope drift')
    executable = build / 'obj/VHostBlockTop'; rtl = build / 'generated/HostBlockTop.sv'
    require(sha(executable) == ready['binary_sha256'] and sha(rtl) == ready['rtl_sha256'], 'DUT binary/RTL identity drift')
    require(sha(build / 'sources.sha256.json') == ready['source_manifest_sha256'], 'built source-manifest identity drift')
    files = [executable, rtl, build / 'build_ready.json', build / 'sources.sha256.json', build / 'hardfloat.sha256.json']
    if ready.get('source_snapshot_manifest_sha256') is not None:
        require(sha(build / 'source_snapshot.json') == ready['source_snapshot_manifest_sha256'], 'source snapshot identity drift')
        files.append(build / 'source_snapshot.json')
    require(all(p.is_file() and not p.is_symlink() for p in files), 'build identity file/symlink')
    return {str(path): sha(path) for path in files}


def verify_all_build_sources(build, log_name='final_source_verify.log', *, source_root=ROOT):
    build, source_root = Path(build), Path(source_root)
    ready = json.loads((build / 'build_ready.json').read_text())
    require(sha(build / 'sources.sha256.json') == ready['source_manifest_sha256'], 'built source-manifest identity drift')
    with (build / log_name).open('w') as log:
        subprocess.run([sys.executable, str(source_root / 'chisel/continuous_prefill/scripts/production_source_identity.py'),
                        'verify', str(source_root), str(build), ready['hardfloat_source']],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)


def run_case(build, fixture, mode='pass', session=None, *, label=None, authority=None, source_root=ROOT,
             timeout_seconds=5400):
    """Run one fresh production case without rebuilding the DUT.

    Supply authority/session to reuse authentication; omitting both invokes the
    existing verifier's bounded reference recomputation before any DUT work.
    source_root may select the frozen source tree used by the build. Source and
    DUT identities are checked both before and after the bounded actual run.
    """
    build, fixture = Path(build), Path(fixture)
    require(mode in MODES, 'unknown actual driver case')
    require(type(timeout_seconds) is int and 0 < timeout_seconds <= 21600,
            'timeout_seconds must be a positive integer at most 21600')
    label = mode if label is None else label
    require(type(label) is str and label and all(c.isalnum() or c in '_-' for c in label), 'invalid output label')
    authority, _ = _admit(fixture, session, authority)
    identity = _build_identity(build)
    verify_all_build_sources(build, label + '_initial_source_verify.log', source_root=source_root)
    output = build / label; log = build / (label + '.log')
    require(not output.exists() and not output.is_symlink() and not log.exists() and not log.is_symlink(),
            'execution evidence must be fresh')
    with log.open('w') as stream:
        process = subprocess.run([str(build / 'obj/VHostBlockTop'), str(fixture), str(output), mode],
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=timeout_seconds)
    (build / (label + '.exit')).write_text(str(process.returncode) + '\n')
    require(process.returncode == 0, 'production Host GDN execution failed: ' + mode)
    result = verify_execution(fixture, output, log, mode, authority=authority)
    require(_build_identity(build) == identity, 'DUT or build receipt changed during execution')
    verify_all_build_sources(build, label + '_final_source_verify.log', source_root=source_root)
    result.update(status='PASS_PRODUCTION_HOST_GDN_CASE', actual_dut_identity_verified=True,
                  binary_sha256=identity[str(build / 'obj/VHostBlockTop')],
                  rtl_sha256=identity[str(build / 'generated/HostBlockTop.sv')],
                  build_ready_sha256=identity[str(build / 'build_ready.json')], source_immutability_verified=True)
    (build / (label + '.result.json')).write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'outputs', 'log'):
        parser.add_argument(name, type=Path)
    parser.add_argument('mode', choices=MODES)
    args = parser.parse_args()
    print(json.dumps(verify_execution(args.fixture, args.outputs, args.log, args.mode), indent=2))
