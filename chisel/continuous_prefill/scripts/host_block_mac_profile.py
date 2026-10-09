#!/usr/bin/env python3
"""Collect bounded host counter evidence; never issue numerical or QoR acceptance.

The caller must independently audit the actual DDR/numerical artifacts and bind
this stdout digest to the fresh process, binary and source identities. Parsing a
synthetic log successfully establishes only consistency of its counter records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import host_bf16_attention_block_execution as execution


STATUS = 'CONSISTENT_HOST_BLOCK_MAC_PROFILE_ONLY'
PREFIX = 'HOST_MAC_PROFILE_'
MACS_PER_CYCLE = 8 * 16 * 32
UINT64_MAX = (1 << 64) - 1
CUMULATIVE = ('wide_steps', 'pipeline_stalls', 'idma_transfers')
LAUNCH_COUNTERS = ('useful_macs', 'executed_macs', 'read_beats',
                   'read_ack_beats', 'write_beats', 'write_ack_beats')
SAMPLED_COUNTERS = ('useful_macs', 'executed_macs', 'wide_steps',
                    'pipeline_stalls', 'read_beats', 'read_ack_beats',
                    'write_beats', 'write_ack_beats')
FIELDS = {
    'BEGIN': ('run', 'cycle', *CUMULATIVE),
    'COMMAND': ('run', 'pc', 'cycle', *SAMPLED_COUNTERS),
    'END': ('run', 'cycle', 'cycles', *SAMPLED_COUNTERS, 'idma_transfers', 'status'),
}
PATTERNS = {kind: re.compile(PREFIX + kind + ''.join(
    ' ' + key + r'=([0-9]+)' for key in fields)) for kind, fields in FIELDS.items()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _parse(text):
    """Preserve interleaving so detached copies cannot bind to actual events."""
    profiles, actual, position = [], [], 0
    for line in text.splitlines():
        if line.lstrip().startswith('HOST_MAC_PROFILE'):
            kind = line.split(' ', 1)[0][len(PREFIX):]
            match = PATTERNS.get(kind)
            match = match.fullmatch(line) if match else None
            require(match is not None, 'invalid/unknown MAC profile event or fields')
            values = match.groups()
            require(all(len(value) <= 20 for value in values), 'counter outside uint64')
            fields = dict(zip(FIELDS[kind], map(int, values)))
            require(all(value <= UINT64_MAX for value in fields.values()), 'counter outside uint64')
            profiles.append((position, kind, fields))
            require(len(profiles) <= 48, 'extra MAC profile events')
            position += 1
        elif line.lstrip().startswith(execution.PREFIX):
            require(line == line.lstrip(), 'indented actual audit event')
            kind, fields = execution.parse_events(line)[0]
            fields = {key: value if key == 'mode' else int(value)
                      for key, value in fields.items()}
            require(all(key == 'mode' or value <= UINT64_MAX
                        for key, value in fields.items()), 'actual counter outside uint64')
            actual.append((position, kind, fields))
            position += 1
    require(profiles and actual, 'missing MAC profile/actual audit events')
    return profiles, actual


def _samples(begin, commands, end):
    previous = {key: begin.get(key, 0) for key in SAMPLED_COUNTERS}
    previous['cycle'] = begin['cycle']
    windows = []
    for sample in [*commands, end]:
        elapsed = sample['cycle'] - begin['cycle']
        delta_cycles = sample['cycle'] - previous['cycle']
        require(delta_cycles > 0, 'reordered/duplicate MAC profile cycle')
        require(all(sample[key] >= previous[key] for key in SAMPLED_COUNTERS),
                'MAC profile counter reversal')
        require(sample['useful_macs'] <= sample['executed_macs'] <= MACS_PER_CYCLE * elapsed,
                'MAC counters exceed physical capacity/useful bound')
        require(sample['executed_macs'] % 512 == 0, 'executed MAC counter is not slice-step aligned')
        require(sample['wide_steps'] - begin['wide_steps'] <= elapsed and
                sample['pipeline_stalls'] - begin['pipeline_stalls'] <= elapsed,
                'matrix cycle counter exceeds elapsed cycles')
        require(sample['read_ack_beats'] <= sample['read_beats'] and
                sample['write_ack_beats'] <= sample['write_beats'], 'ACK counter exceeds requests')
        windows.append(dict(cycle=sample['cycle'], cycles=delta_cycles,
                            **{key: sample[key] - previous[key] for key in SAMPLED_COUNTERS}))
        previous = sample
    require(end['read_ack_beats'] == end['read_beats'] and
            end['write_ack_beats'] == end['write_beats'], 'undrained terminal AXI counters')
    return windows


def _bind_actual(actual, begin_record, command_records, end_record, mode, run):
    begin_pos, _, begin = begin_record
    end_pos, _, end = end_record
    events = [row for row in actual if row[1] != 'PAIR' and row[2]['run'] == run]
    require(events and events[0][1] == 'BEGIN' and events[-1][1] == 'END',
            'missing/reordered actual launch boundaries')
    require(sum(row[1] == 'BEGIN' for row in events) == 1 and
            sum(row[1] == 'END' for row in events) == 1, 'duplicate actual launch boundaries')
    first, last = events[0], events[-1]
    require(abs(first[0] - begin_pos) == 1, 'detached MAC profile BEGIN')
    expected_begin = dict(run=run, mode=mode, epoch=9 + run, commands=22,
                          old_length=run, old_generation=run)
    require(first[2] == expected_begin, 'actual BEGIN identity drift')
    failing = mode != 'pass' and run == 1
    status = 3 if failing else 0
    pcs = execution.completion_plan(failing)
    commands = [row for row in events if row[1] == 'COMMAND']
    require([row[2]['pc'] for row in commands] == pcs, 'actual COMMAND inventory/order drift')
    for actual_command, profile_command in zip(commands, command_records):
        ai, _, a = actual_command
        pi, _, p = profile_command
        require(abs(ai - pi) == 1, 'detached MAC profile COMMAND')
        require(a['cycle'] == p['cycle'] and a['run'] == p['run'] and a['pc'] == p['pc'],
                'actual COMMAND cycle/identity drift')
        require(a['status'] == (3 if failing and a['pc'] == 20 else 0),
                'actual COMMAND status drift')
    holds = [row for row in events if row[1] == 'RESULT_HOLD']
    require(len(holds) == 7 and [row[2]['cycle'] for row in holds] ==
            list(range(end['cycle'] + 1, end['cycle'] + 8)), 'terminal boundary/result-hold drift')
    require(end_pos < holds[0][0] and holds[-1][0] < last[0], 'reordered terminal profile/audit events')
    last_cycle = begin['cycle']
    for position, kind, event in events[1:-1]:
        require('cycle' in event and event['cycle'] >= last_cycle, 'actual event cycle reversal')
        last_cycle = event['cycle']
        if kind == 'RESULT_HOLD':
            require(event['epoch'] == 9 + run and event['pc'] == pcs[-1] and
                    event['status'] == status and event['completed'] == len(pcs) - int(failing),
                    'actual RESULT_HOLD identity drift')
        else:
            require(begin_pos < position < end_pos and
                    begin['cycle'] < event['cycle'] <= end['cycle'],
                    'actual traffic/completion outside launch profile')
    observed = last[2]
    require(observed['status'] == status and observed['completions'] == len(pcs) and
            observed['successful'] == len(pcs) - int(failing), 'actual END lifecycle drift')
    for key in LAUNCH_COUNTERS:
        if key in observed:
            require(observed[key] == end[key], 'actual END counter drift: ' + key)
    require(observed['idma_transfers'] == end['idma_transfers'] - begin['idma_transfers'],
            'actual END iDMA counter drift')


def collect(log_path, mode):
    """Return compact statistics for a complete two-launch stdout, or fail closed."""
    require(mode in execution.MODES, 'unsupported MAC profile mode')
    path = Path(log_path)
    require(path.is_file() and not path.is_symlink(), 'regular stdout log required')
    raw = path.read_bytes()
    profiles, actual = _parse(raw.decode('utf-8', errors='strict'))
    require(actual[-1][1] == 'PAIR' and sum(row[1] == 'PAIR' for row in actual) == 1,
            'missing/extra same-DUT pair receipt')
    require(actual[-1][2] == dict(same_dut=1, resets_between_launches=0,
            reference_injection=0, cache_prefill=0, launches=2), 'same-DUT pair identity drift')
    actual_runs = [row[2]['run'] for row in actual[:-1]]
    require(set(actual_runs) == {0, 1} and actual_runs == sorted(actual_runs),
            'actual launch ordering/inventory drift')
    cursor, runs, previous_end = 0, [], None
    for run in range(2):
        failing = mode != 'pass' and run == 1
        pcs = execution.completion_plan(failing)
        size = len(pcs) + 2
        records = profiles[cursor:cursor + size]
        require(len(records) == size and [row[1] for row in records] ==
                ['BEGIN', *('COMMAND' for _ in pcs), 'END'], 'incomplete/reordered MAC profile launch')
        require(all(row[2]['run'] == run for row in records), 'MAC profile run identity drift')
        begin, end = records[0][2], records[-1][2]
        commands = [row[2] for row in records[1:-1]]
        require([row['pc'] for row in commands] == pcs, 'MAC profile COMMAND inventory/order drift')
        require(end['status'] == (3 if failing else 0), 'MAC profile terminal status drift')
        require(end['cycles'] == end['cycle'] - begin['cycle'] and end['cycles'] > 0,
                'MAC profile elapsed cycle drift')
        require(end['idma_transfers'] >= begin['idma_transfers'], 'iDMA counter reversal')
        if previous_end is not None:
            require(begin['cycle'] > previous_end['cycle'] + 7, 'same-DUT launch cycle reversal')
            require(all(begin[key] == previous_end[key] for key in CUMULATIVE),
                    'same-DUT cumulative counter drift between launches')
        windows = _samples(begin, commands, end)
        _bind_actual(actual, records[0], records[1:-1], records[-1], mode, run)
        totals = {key: end[key] for key in LAUNCH_COUNTERS}
        totals.update({key: end[key] - begin[key] for key in CUMULATIVE})
        runs.append(dict(run=run, phase=('cold0', 'carried1')[run], hardware_status=end['status'],
            begin_cycle=begin['cycle'], end_cycle=end['cycle'], cycles=end['cycles'], **totals,
            cumulative_counter_begin={key: begin[key] for key in CUMULATIVE},
            cumulative_counter_end={key: end[key] for key in CUMULATIVE},
            useful_utilization=(dict(numerator=end['useful_macs'], denominator=MACS_PER_CYCLE * end['cycles'])
                                if mode == 'pass' else None),
            commands=[dict(pc=pc, **window) for pc, window in zip(pcs, windows[:-1])],
            terminal_cycles=windows[-1]['cycles'], terminal_counter_deltas=windows[-1]))
        previous_end = end
        cursor += size
    require(cursor == len(profiles) and profiles[-1][0] < actual[-1][0], 'extra/detached MAC profile events')
    return dict(status=STATUS, mode=mode, log_sha256=hashlib.sha256(raw).hexdigest(),
        numerical_acceptance=False, actual_dut_identity_verified=False, performance_acceptance=False,
        fixed_resources=dict(logical_matrix_engines=1, physical_slices=8, rows_per_slice=16,
                             columns_per_slice=32, macs_per_cycle=MACS_PER_CYCLE),
        counter_semantics=dict(
            cycles='Accepted-launch boundary through first terminal result; includes launch acceptance edge; excludes seven result-hold clocks.',
            useful_macs='Per-launch successful-owner receipt counter; not a numerical acceptance result.',
            executed_macs='Per-launch successful-owner receipt counter; faulted/partial owner physical work is not fully represented.',
            cumulative='wide_steps, pipeline_stalls and idma_transfers are raw hardware counters differenced at launch boundaries.',
            command_windows='Counter deltas between public command completions, including completion holds, host metadata and DDR backpressure; fused owners may account at one completion.',
            pipeline_stalls='Matrix step valid and not ready; may overlap other activity and is not an additive cycle bucket.',
            useful_utilization='Exact useful_macs/(4096*cycles); only reported for a complete successful pass-mode pair.'),
        unavailable_counters=['scalar_per_opcode_cycles', 'owner_internal_cycles', 'live_accepted_steps'],
        runs=runs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--mode', choices=execution.MODES, default='pass')
    args = parser.parse_args()
    print(json.dumps(collect(args.log, args.mode), indent=2))
