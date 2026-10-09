#!/usr/bin/env python3
"""Replay production GDN core physical ACK evidence with live source authority.

The driver's PASS line is not authority. This checker replays each byte strobe,
checks every completion snapshot and both whole-DDR images, then verifies the
cold fence precedes actual carried history/state reads. File-only replay never
authenticates a DUT. Only run_case binds the existing production build identity.
Native stage comparisons remain diagnostics; a canonical core pass is not a
native/full-GDN-block pass. Fault and checkpoint restore are not implemented.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from host_bf16_qkv_execution import require, sha, _expect
from host_bf16_gdn_execution import _build_identity, verify_all_build_sources
from pack_host_bf16_gdn_core_fixture import (ROOT, GdnCoreFixtureSession,
    ACTUAL_DENSE_MACS, build_layout, _write_launch, frozen_operator_metrics, ulp_metric)

PREFIX = 'HOST_BF16_GDN_CORE_'
SCOPE = 'GDN_CORE_M1_BEFORE_OUTPUT_PROJECTION'
SCHEMA = {
    'BEGIN': 'run commands epoch mode same_dut reset_between_launches',
    'CARRY_READ': 'run pc cycle address bytes producer',
    'WRITE_REQUEST': 'run pc cycle address bus_bytes final',
    'WRITE_ACK': 'run pc cycle address bus_bytes write_bytes mask error final',
    'COMPLETION_HOLD': 'run pc cycle word',
    'NATIVE': 'run stage elements element_bytes bit_mismatches max_abs mean_abs same_input_max_bf16_ulp fixed_operator_gate acceptance',
    'COMMAND': 'run cycle operation pc status signal write_ack_bytes canonical_bit_mismatches previous_outputs_preserved guards_unchanged persistent_commit expected_committed_generation',
    'END': 'run status result_epoch result_pc completions issued_jobs metadata_reads read_beats read_ack_beats write_beats write_ack_beats write_ack_bytes published_bytes committed_generation canonical_bit_mismatches frozen_operator_gate native_core_gate full_block_supported',
    'PASS': 'scope tokens heads commands owner_jobs fences canonical_bit_mismatches actual_dense_macs same_dut reset_between_launches actual_ack_history_state_carry expected_output_injection logical_matrix_engines physical_matrix_slices idma_instances shared_scalar_services input_norm_dut o_projection_dut residual_dut ffn_dut native_core_gate frozen_operator_gate native_full_block_gate full_block_supported',
}


def _events(log, *, prefix=PREFIX):
    events = []
    for line in Path(log).read_text().splitlines():
        if not line.startswith(prefix):
            continue
        tokens = line.split()
        kind = tokens[0][len(prefix):]
        require(kind in SCHEMA, 'unknown/failure core event: ' + kind)
        pairs = [token.split('=', 1) for token in tokens[1:]]
        require(all(len(pair) == 2 for pair in pairs), 'malformed core event')
        data = dict(pairs)
        require(len(data) == len(pairs) and set(data) == set(SCHEMA[kind].split()),
                'duplicate/unknown/missing core fields: ' + kind)
        events.append((kind, data))
    require(events, 'missing core execution events')
    return events


def _native_metrics(actual, native, element_bytes):
    require(len(actual) == len(native) and len(actual) % element_bytes == 0, 'native geometry')
    dtype = '<u2' if element_bytes == 2 else '<u4'
    a, b = np.frombuffer(actual, dtype=dtype), np.frombuffer(native, dtype=dtype)
    af, bf = ((a.astype('<u4') << 16).view('<f4'), (b.astype('<u4') << 16).view('<f4')) if element_bytes == 2 else (a.view('<f4'), b.view('<f4'))
    error = np.abs(af.astype(np.float64)-bf.astype(np.float64))
    require(error.size and np.isfinite(error).all(), 'nonfinite native comparison')
    return dict(elements=int(a.size), element_bytes=element_bytes, bit_mismatches=int(np.count_nonzero(a != b)),
                max_abs=float(error.max()), mean_abs=float(error.mean()),
                acceptance='UNASSIGNED_DIAGNOSTIC_ONLY')


def _initial(fixture, layout):
    memory = bytearray(bytes.fromhex('3cc35aa5') * ((layout['limit']-layout['base'])//4))
    def load(name, address, size):
        data = (fixture / name).read_bytes()
        require(len(data) == size and layout['base'] <= address < address+size <= layout['limit'], 'initial physical span')
        offset = address-layout['base']
        memory[offset:offset+size] = data
    for entry in layout['inputs']:
        require(not entry['file'].startswith(('expected_', 'native_')), 'reference DDR initialization forbidden')
        load(entry['file'], entry['address'], entry['bytes'])
    for launch in layout['launches']:
        token = launch['token']
        load(f'host_commands{token}.bin', launch['command_base'], launch['command_limit']-launch['command_base'])
        load(f'host_descriptors{token}.bin', launch['descriptor_base'], launch['descriptor_limit']-launch['descriptor_base'])
    return memory


def _frozen_gates(fixture, manifest):
    arrays = {}
    for prefix in ('expected', 'native', 'conditioned'):
        roles = ('conv', 'conv_before_silu') if prefix == 'conditioned' else ('qkv', 'z', 'ab', 'conv', 'conv_before_silu')
        arrays[prefix] = [{role: np.fromfile(fixture / f'{prefix}_{role}{token}.bf16le', dtype='<u2')
                           for role in roles} for token in range(2)]
    metrics = frozen_operator_metrics(arrays['expected'], arrays['native'], arrays['conditioned'])
    require(metrics == manifest['frozen_operator_metrics'], 'frozen operator metrics changed')
    require(manifest['native_operator_gate_pass'] is True and all(x['passed'] for x in metrics),
            'unchanged native Dense/Conv/SiLU gates failed; canonical equality cannot bypass them')
    return metrics


def audit_artifacts(fixture, output, log, *, session, _profile=None):
    """Check actual evidence; requires generate_fixture's live, unforgeable session."""
    block = _profile is not None
    authority = _profile.GdnBlockFixtureSession if block else GdnCoreFixtureSession
    commands, fence_pc = (17, 16) if block else (8, 7)
    dense_macs = _profile.ACTUAL_DENSE_MACS if block else ACTUAL_DENSE_MACS
    require(type(session) is authority, 'live fixture session required; saved receipts are not authority')
    fixture, output, log = Path(fixture), Path(output), Path(log)
    manifest = session.verify(fixture)
    operator_metrics = (_profile._frozen_gates if block else _frozen_gates)(fixture, manifest)
    require(not output.is_symlink() and not log.is_symlink(), 'evidence symlink')
    layout = (_profile.build_layout if block else build_layout)()
    require(manifest['layout'] == layout, 'fixture physical/public ABI layout drift')
    packed = {}
    (_profile._write_launch if block else _write_launch)(layout, lambda name, raw: packed.update({name: raw}))
    require(all((fixture / name).read_bytes() == raw for name, raw in packed.items()), 'launch/public helper packing drift')
    require({p.name for p in output.iterdir()} == {'cold', 'carried'}, 'unexpected core evidence directory')
    events, cursor = _events(log, prefix=_profile.PREFIX if block else PREFIX), 0
    log_identity = sha(log)
    expected = _initial(fixture, layout)
    scratch = layout['scratch']-layout['base']
    reports, artifacts, last_cycle, fence_cycle = [], {}, 0, None
    cumulative_fixed_pass = True
    for token, launch in enumerate(layout['launches']):
        directory = output / ('cold' if token == 0 else 'carried')
        require(directory.is_dir() and not directory.is_symlink(), 'missing/symlink core run')
        inventory = {'ddr_after.bin'} | {f'writable_after_command{i}.bin' for i in range(commands)}
        for op in launch['operations']:
            for span in op['writes']:
                inventory.add('actual_' + span['expected'].removeprefix('expected_'))
        require({p.name for p in directory.iterdir()} == inventory, 'stage snapshot/output inventory')
        raw = {}
        for name in inventory:
            path = directory / name
            require(path.is_file() and not path.is_symlink(), 'core artifact file/symlink')
            raw[name] = path.read_bytes()
            artifacts[str(path)] = sha(path)
        require(cursor < len(events) and events[cursor][0] == 'BEGIN', 'missing core run begin')
        _expect(events[cursor][1], run=token, commands=commands, epoch=9+token, mode='cold' if token == 0 else 'carried',
                same_dut=1, reset_between_launches=0)
        cursor += 1
        total_bytes, physical_beats, per_command, metrics, carry_seen = 0, 0, [], {}, {}
        for pc, op in enumerate(launch['operations']):
            acked = {s['name']: bytearray(s['bytes']) for s in op['writes']}
            actual = {s['name']: raw['actual_' + s['expected'].removeprefix('expected_')] for s in op['writes']}
            require(all(len(actual[s['name']]) == s['bytes'] for s in op['writes']), 'actual stage size')
            pending, ack_bytes, holds, final_acks, native_seen = None, 0, 0, 0, set()
            op_bytes = sum(s['bytes'] for s in op['writes'])
            while cursor < len(events) and events[cursor][0] != 'COMMAND':
                kind, event = events[cursor]
                require(kind in ('WRITE_REQUEST', 'WRITE_ACK', 'CARRY_READ', 'COMPLETION_HOLD', 'NATIVE'), 'unexpected event before command')
                _expect(event, run=token)
                if kind == 'NATIVE':
                    name = event['stage']
                    require(name in actual and name not in native_seen and pending is None and ack_bytes == op_bytes, 'native event without complete actual output')
                    span = next(s for s in op['writes'] if s['name'] == name)
                    metric = _native_metrics(actual[name], (fixture / span['native']).read_bytes(), span['element_bytes'])
                    fixed = name in ('qkv', 'z', 'ab', 'conv')
                    conditioned_ulp = 0
                    if name == 'conv':
                        conditioned = (fixture / f'conditioned_conv{token}.bf16le').read_bytes()
                        same = ulp_metric(np.frombuffer(actual[name], '<u2'), np.frombuffer(conditioned, '<u2'))
                        conditioned_ulp = same['max_bf16_ulp']
                        if not block: require(same['pass_'], 'actual same-input SiLU fixed one-ULP gate failed')
                    if fixed:
                        if not block: require(metric['max_abs'] <= .03125 and metric['mean_abs'] <= .005, 'actual fixed Dense/Conv gate failed')
                        metric['acceptance'] = 'FROZEN_OPERATOR_THRESHOLDS'
                    fixed_pass = metric['max_abs'] <= .03125 and metric['mean_abs'] <= .005 and conditioned_ulp <= 1
                    if fixed: cumulative_fixed_pass &= fixed_pass
                    metric.update(same_input_max_bf16_ulp=conditioned_ulp, fixed_operator_gate=('PASS' if fixed_pass else 'FAIL') if fixed else 'UNASSIGNED')
                    for key, value in metric.items():
                        if isinstance(value, float):
                            require(math.isclose(float(event[key]), value, rel_tol=1e-12, abs_tol=1e-15), 'native numerical report drift')
                        else:
                            _expect(event, **{key: value})
                    native_seen.add(name)
                    metrics[name] = metric
                    cursor += 1
                    continue
                _expect(event, pc=pc)
                cycle = int(event['cycle'])
                require(cycle >= last_cycle, 'nonmonotonic physical event cycle')
                last_cycle = cycle
                if kind == 'WRITE_REQUEST':
                    address, size = int(event['address']), int(event['bus_bytes'])
                    require(pending is None and op_bytes and ack_bytes < op_bytes and size in range(64, 1025, 64), 'overlapping or invalid write request')
                    require(address % 64 == 0 and (address & 1023)+size <= 1024, 'invalid AXI request geometry')
                    require(any(s['address'] <= address and address+size <= s['address']+s['bytes'] for s in op['writes']), 'request outside stage output')
                    require(int(event['final']) in (0, 1), 'final request flag')
                    pending = dict(address=address, remaining=size, cycle=cycle, final=int(event['final']))
                elif kind == 'WRITE_ACK':
                    address, mask = int(event['address']), int(event['mask'])
                    require(pending is not None and address == pending['address'] and cycle > pending['cycle'], 'ACK without matching physical request')
                    _expect(event, bus_bytes=64, error=0, write_bytes=mask.bit_count())
                    span = next((s for s in op['writes'] if s['address'] <= address < address+64 <= s['address']+s['bytes']), None)
                    require(span is not None, 'ACK outside exact output span')
                    require(mask == (1 << 64)-1, 'unsupported output strobe: production GDN stages require complete 64B beats')
                    name, offset = span['name'], address-span['address']
                    for byte in range(64):
                        if mask >> byte & 1:
                            require(acked[name][offset+byte] == 0, 'duplicate physical byte ACK')
                            acked[name][offset+byte] = 1
                            expected[address-layout['base']+byte] = actual[name][offset+byte]
                    ack_bytes += mask.bit_count()
                    physical_beats += 1
                    pending['remaining'] -= 64
                    pending['address'] += 64
                    final = bool(pending['final'] and pending['remaining'] == 0)
                    _expect(event, final=int(final))
                    if final:
                        require(ack_bytes == op_bytes and cycle-pending['cycle'] >= 53, 'final ACK was not delayed or did not cover all output bytes')
                        final_acks += 1
                    if not pending['remaining']:
                        pending = None
                elif kind == 'CARRY_READ':
                    address, size, producer = map(int, (event['address'], event['bytes'], event['producer']))
                    require(token == 1 and fence_cycle is not None and cycle > fence_cycle, 'carried read before actual cold fence')
                    source = next((s for s in op['reads'] if s['producer'] == producer and producer >= 0 and producer < commands and
                                   s['address'] <= address < address+size <= s['address']+s['bytes']), None)
                    require(source is not None and address % 64 == size % 64 == 0 and size > 0, 'unbound carried source read')
                    seen = carry_seen.setdefault(producer, bytearray(source['bytes']//64))
                    start = (address-source['address'])//64
                    seen[start:start+size//64] = bytes([1])*(size//64)
                else:
                    require(pending is None and ack_bytes == op_bytes, 'completion held before exact ACK closure')
                    _expect(event, word=pc | op['engine'] << 29 | op['event_signal'] << 40)
                    holds += 1
                cursor += 1
            require(cursor < len(events), 'missing command completion')
            event = events[cursor][1]
            cycle = int(event['cycle'])
            require(cycle >= last_cycle and pending is None and ack_bytes == op_bytes, 'command before complete ACK replay')
            last_cycle = cycle
            _expect(event, run=token, operation=op['kind'], pc=pc, status=0, signal=op['event_signal'], write_ack_bytes=ack_bytes,
                    canonical_bit_mismatches=0, previous_outputs_preserved=1, guards_unchanged=1,
                    persistent_commit=int(pc == fence_pc), expected_committed_generation=token+int(pc == fence_pc))
            require(final_acks == int(pc != fence_pc) and holds >= 11, 'final ACK/completion backpressure coverage')
            require(native_seen == set(actual), 'missing stage native diagnostics')
            for span in op['writes']:
                name = span['name']
                require(all(acked[name]), 'physical ACK byte coverage incomplete')
                require(actual[name] == (fixture / span['expected']).read_bytes(), 'actual stage differs from shared canonical recipe: ' + name)
            require(raw[f'writable_after_command{pc}.bin'] == expected[scratch:], 'completion snapshot differs from physical ACK replay')
            if pc == fence_pc:
                fence_cycle = cycle
            total_bytes += ack_bytes
            per_command.append(dict(pc=pc, operation=op['kind'], write_ack_bytes=ack_bytes,
                                    final_ack_count=final_acks, completion_hold_cycles=holds))
            cursor += 1
        require(cursor < len(events) and events[cursor][0] == 'END', 'missing successful run result')
        event = events[cursor][1]
        _expect(event, run=token, status=0, result_epoch=9+token, result_pc=fence_pc, completions=commands, issued_jobs=commands-1,
                metadata_reads=launch['descriptor_records']+commands, write_beats=physical_beats, write_ack_beats=physical_beats,
                write_ack_bytes=total_bytes, published_bytes=total_bytes, committed_generation=token+1,
                canonical_bit_mismatches=0, native_core_gate='UNASSIGNED_DIAGNOSTIC_ONLY', full_block_supported=int(block))
        _expect(event, frozen_operator_gate='PASS' if cumulative_fixed_pass else 'FAIL')
        require(physical_beats * 64 == total_bytes, 'full-beat physical write accounting')
        require(int(event['read_beats']) == int(event['read_ack_beats']) and int(event['read_beats']) > launch['descriptor_records']+commands, 'read ACK accounting')
        require(raw['ddr_after.bin'] == expected, 'whole physical DDR differs from accepted strobed-write replay')
        if token:
            require(set(carry_seen) == ({4, 6} if block else {3, 5}) and all(all(v) for v in carry_seen.values()), 'both actual carried state spans must be read after fence')
        else:
            require(not carry_seen, 'cold launch imported a previous state')
        reports.append(dict(token=token, committed_generation=token+1, commands=per_command,
                            native_diagnostics=metrics, write_ack_bytes=total_bytes, physical_write_beats=physical_beats,
                            physical_ddr_bytes_checked=len(expected), canonical_bit_mismatches=0,
                            carried_history_state_read_beats={str(k): len(v) for k, v in carry_seen.items()},
                            ddr_after_sha256=artifacts[str(directory / 'ddr_after.bin')]))
        cursor += 1
    require(cursor < len(events) and events[cursor][0] == 'PASS', 'missing final core closure')
    _expect(events[cursor][1], scope='GDN_FULL_BLOCK' if block else 'GDN_CORE_ONLY', tokens=2, heads=16, commands=2*commands, owner_jobs=2*(commands-1), fences=2,
            canonical_bit_mismatches=0, actual_dense_macs=dense_macs, same_dut=1, reset_between_launches=0,
            actual_ack_history_state_carry=1, expected_output_injection=0, logical_matrix_engines=1,
            physical_matrix_slices=8, idma_instances=1, shared_scalar_services=1,
            input_norm_dut=int(block), o_projection_dut=int(block), residual_dut=int(block), ffn_dut=int(block),
            native_core_gate='UNASSIGNED_DIAGNOSTIC_ONLY', frozen_operator_gate='PASS' if cumulative_fixed_pass else 'FAIL',
            native_full_block_gate='DEFERRED_TO_AUDIT' if block else 'NOT_ESTABLISHED', full_block_supported=int(block))
    require(cursor+1 == len(events), 'unexpected or duplicate trailing evidence')
    require(sha(log) == log_identity and all(sha(path) == digest for path, digest in artifacts.items()), 'evidence changed during audit')
    session.verify(fixture)
    return dict(status='PASS_HOST_GDN_CORE_ARTIFACT_CHECK_ONLY', scope=SCOPE, actual_dut_identity_verified=False,
                source_immutability_verified=False, canonical_core_pass=True, native_core_gate_pass=None,
                native_operator_gate_pass=True, frozen_operator_metrics=operator_metrics,
                native_full_block_gate_pass=None, full_block_supported=False, fault_restore_supported=False,
                input_norm_dut=False, o_projection_dut=False, residual_dut=False, ffn_dut=False,
                fixture_sha256=sha(fixture / 'manifest.json'), log_sha256=log_identity,
                artifact_sha256=artifacts, runs=reports, actual_useful_dense_macs=dense_macs,
                actual_ack_history_state_carry=True, raw_carried_state_read_address_trace_available=True,
                raw_all_read_address_trace_available=False)


def run_case(build, fixture, *, session, label='core_cold_carried', source_root=ROOT, timeout_seconds=21600):
    """Use one existing core-profile binary; do not rebuild or accept saved authority."""
    build, fixture = Path(build).resolve(), Path(fixture).resolve()
    require(type(session) is GdnCoreFixtureSession, 'live GdnCoreFixtureSession required')
    require(type(timeout_seconds) is int and 0 < timeout_seconds <= 21600, 'bounded actual runtime required')
    require(type(label) is str and label and all(c.isalnum() or c in '_-' for c in label), 'invalid output label')
    manifest = session.verify(fixture)
    _frozen_gates(fixture, manifest)
    identity = _build_identity(build, profile='core')
    verify_all_build_sources(build, label+'_initial_source_verify.log', source_root=source_root)
    output, log = build / label, build / (label+'.log')
    require(not output.exists() and not output.is_symlink() and not log.exists() and not log.is_symlink(), 'fresh evidence paths required')
    with log.open('w') as stream:
        process = subprocess.run([str(build / 'obj/VHostBlockTop'), str(fixture), str(output)],
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=timeout_seconds)
    (build / (label+'.exit')).write_text(str(process.returncode)+'\n')
    require(_build_identity(build, profile='core') == identity, 'DUT identity changed during execution')
    verify_all_build_sources(build, label+'_final_source_verify.log', source_root=source_root)
    session.verify(fixture)
    require(process.returncode == 0, 'production Host GDN core execution failed; no acceptance')
    result = audit_artifacts(fixture, output, log, session=session)
    result.update(status='PASS_PRODUCTION_HOST_GDN_CORE_CANONICAL', actual_dut_identity_verified=True,
                  source_immutability_verified=True, binary_sha256=identity[str(build / 'obj/VHostBlockTop')],
                  rtl_sha256=identity[str(build / 'generated/HostBlockTop.sv')],
                  build_ready_sha256=identity[str(build / 'build_ready.json')])
    (build / (label+'.result.json')).write_text(json.dumps(result, indent=2)+'\n')
    return result
