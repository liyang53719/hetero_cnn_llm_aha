"""Synthetic parser controls only: no model, EDA, build or numerical execution."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import host_bf16_attention_block_execution as execution
import host_block_mac_profile as profile


def event(prefix, kind, fields, **values):
    return prefix + kind + ''.join(' ' + key + '=' + str(values.get(key, 0)) for key in fields)


def actual(kind, **values):
    return event(execution.PREFIX, kind, execution.FIELDS[kind].split(), **values)


def counter(kind, **values):
    return event(profile.PREFIX, kind, profile.FIELDS[kind], **values)


def synthetic(mode='pass'):
    """Intentionally not DDR/audit evidence; test only the parser's contract."""
    lines = ['synthetic counter parser fixture, never DUT evidence']
    begin_cycle, wide, stalls, transfers = 36, 7, 9, 12
    for run in range(2):
        failing = mode != 'pass' and run == 1
        status = 3 if failing else 0
        count = 21 if failing else 22
        lines += [actual('BEGIN', run=run, mode=mode, epoch=9 + run, commands=22,
                         old_length=run, old_generation=run),
                  counter('BEGIN', run=run, cycle=begin_cycle, wide_steps=wide,
                          pipeline_stalls=stalls, idma_transfers=transfers)]
        for pc in range(count):
            n = pc + 1
            cycle = begin_cycle + n * 100
            lines += [actual('COMMAND', run=run, pc=pc, cycle=cycle,
                             status=status if pc == 20 else 0),
                      counter('COMMAND', run=run, pc=pc, cycle=cycle,
                              useful_macs=n * 256, executed_macs=n * 512,
                              wide_steps=wide + n * 2, pipeline_stalls=stalls + n * 3,
                              read_beats=n * 2, read_ack_beats=n * 2,
                              write_beats=n, write_ack_beats=n)]
        end_cycle = cycle + 1
        wide += count * 2
        stalls += count * 3
        transfers += count * 3
        lines.append(counter('END', run=run, cycle=end_cycle, cycles=end_cycle - begin_cycle,
                             useful_macs=count * 256, executed_macs=count * 512,
                             wide_steps=wide, pipeline_stalls=stalls,
                             read_beats=count * 2, read_ack_beats=count * 2,
                             write_beats=count, write_ack_beats=count,
                             idma_transfers=transfers, status=status))
        for offset in range(1, 8):
            lines.append(actual('RESULT_HOLD', run=run, cycle=end_cycle + offset,
                                epoch=9 + run, pc=count - 1, status=status,
                                completed=count - int(failing)))
        lines.append(actual('END', run=run, status=status, completions=count,
                            successful=count - int(failing), useful_macs=count * 256,
                            read_beats=count * 2, read_ack_beats=count * 2,
                            write_beats=count, write_ack_beats=count,
                            idma_transfers=count * 3))
        begin_cycle = end_cycle + 8
    lines.append(actual('PAIR', same_dut=1, resets_between_launches=0,
                        reference_injection=0, cache_prefill=0, launches=2))
    return '\n'.join(lines) + '\n'


def change(text, starts, key, value):
    lines = text.splitlines()
    index, = [i for i, line in enumerate(lines) if line.startswith(starts + ' ')]
    fields = lines[index].split(' ')
    field_index, = [i for i, field in enumerate(fields) if field.startswith(key + '=')]
    fields[field_index] = key + '=' + str(value)
    lines[index] = ' '.join(fields)
    return '\n'.join(lines) + '\n'


class MacProfileTests(unittest.TestCase):
    def collect(self, text, mode='pass'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stdout.log'
            path.write_text(text)
            return profile.collect(path, mode)

    def reject(self, text, mode='pass'):
        with self.assertRaises(ValueError):
            self.collect(text, mode)

    def test_exact_resource_denominator_and_cumulative_differences(self):
        text = synthetic()
        report = self.collect(text)
        self.assertEqual(report['status'], profile.STATUS)
        self.assertEqual(report['log_sha256'], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(report['fixed_resources'], dict(logical_matrix_engines=1,
                         physical_slices=8, rows_per_slice=16, columns_per_slice=32,
                         macs_per_cycle=4096))
        self.assertEqual(len(report['runs']), 2)
        for run, row in enumerate(report['runs']):
            self.assertEqual((row['run'], row['hardware_status'], row['cycles']), (run, 0, 2201))
            self.assertEqual((row['useful_macs'], row['executed_macs']), (5632, 11264))
            self.assertEqual((row['wide_steps'], row['pipeline_stalls'], row['idma_transfers']), (44, 66, 66))
            self.assertEqual(row['useful_utilization'], dict(numerator=5632, denominator=4096 * 2201))
            self.assertEqual([command['pc'] for command in row['commands']], list(range(22)))
            self.assertEqual(row['commands'][0]['wide_steps'], 2)
            self.assertEqual(row['commands'][0]['useful_macs'], 256)
            self.assertEqual(row['terminal_cycles'], 1)
            for key in ('cycles', *profile.SAMPLED_COUNTERS):
                self.assertEqual(sum(command[key] for command in row['commands']) +
                                 row['terminal_counter_deltas'][key], row[key])
        self.assertEqual(report['runs'][1]['cumulative_counter_begin'], report['runs'][0]['cumulative_counter_end'])

    def test_profile_consistency_never_grants_identity_numerical_or_qor_acceptance(self):
        report = self.collect(synthetic())
        for key in ('numerical_acceptance', 'actual_dut_identity_verified', 'performance_acceptance'):
            self.assertIs(report[key], False)
        serialized = json.dumps(report)
        self.assertNotIn('HOST_ATTN_BLOCK_COMMAND', serialized)
        self.assertNotIn('synthetic counter parser fixture', serialized)
        self.assertEqual(report['unavailable_counters'],
                         ['scalar_per_opcode_cycles', 'owner_internal_cycles', 'live_accepted_steps'])
        semantics = report['counter_semantics']
        self.assertIn('excludes seven result-hold clocks', semantics['cycles'])
        self.assertIn('not fully represented', semantics['executed_macs'])
        self.assertIn('not an additive cycle bucket', semantics['pipeline_stalls'])
        self.assertIn('DDR backpressure', semantics['command_windows'])

    def test_fault_pair_has_stats_but_no_utilization_on_either_attempt(self):
        report = self.collect(synthetic('final-residual-ack-error'), 'final-residual-ack-error')
        self.assertEqual([row['hardware_status'] for row in report['runs']], [0, 3])
        self.assertEqual([len(row['commands']) for row in report['runs']], [22, 21])
        self.assertEqual([row['useful_utilization'] for row in report['runs']], [None, None])
        self.reject(synthetic(), 'final-residual-ack-error')
        self.reject(synthetic('final-residual-ack-error'))

    def test_strict_fields_unsigned_uint64_and_unknown_events(self):
        text = synthetic()
        target = next(line for line in text.splitlines() if line.startswith('HOST_MAC_PROFILE_COMMAND'))
        for replacement in (target + ' invented=1', target + ' pc=0',
                            target.replace(' pc=0', ''), target.replace(' cycle=136', ' cycle=-1'),
                            target.replace(' cycle=136', ' cycle=+136'),
                            target.replace(' cycle=136', ' cycle=1.0'),
                            target.replace(' cycle=136', ' cycle=١٣٦'),
                            target.replace(' cycle=136', ' cycle=' + str(1 << 64)),
                            target.replace(' cycle=136', ' cycle=' + '9' * 21),
                            ' ' + target, target + ' ',
                            target.replace('PROFILE_COMMAND', 'PROFILE_UNKNOWN')):
            with self.subTest(replacement=replacement):
                self.reject(text.replace(target, replacement))
        for extra in ('HOST_MAC_PROFILE', 'HOST_MAC_PROFILE_END nonsense',
                      'HOST_ATTN_BLOCK_PREFIX numerical_acceptance=0', 'HOST_ATTN_BLOCK_FAIL: failed'):
            with self.subTest(extra=extra):
                self.reject(text + extra + '\n')

    def test_missing_duplicate_partial_and_detached_records(self):
        text = synthetic()
        lines = text.splitlines()
        prefixes = ('HOST_MAC_PROFILE_BEGIN', 'HOST_MAC_PROFILE_COMMAND', 'HOST_MAC_PROFILE_END',
                    'HOST_ATTN_BLOCK_BEGIN', 'HOST_ATTN_BLOCK_COMMAND', 'HOST_ATTN_BLOCK_END',
                    'HOST_ATTN_BLOCK_PAIR', 'HOST_ATTN_BLOCK_RESULT_HOLD')
        for prefix in prefixes:
            index = next(i for i, line in enumerate(lines) if line.startswith(prefix + ' '))
            with self.subTest(prefix=prefix, action='remove'):
                self.reject('\n'.join(lines[:index] + lines[index + 1:]))
            with self.subTest(prefix=prefix, action='duplicate'):
                self.reject('\n'.join(lines[:index] + [lines[index]] + lines[index:]))
        self.reject('\n'.join(line for line in lines if not line.startswith(profile.PREFIX)))
        self.reject('\n'.join(line for line in lines if line.startswith(profile.PREFIX)))
        self.reject('\n'.join(lines[:20]))
        profile_lines = [line for line in lines if line.startswith(profile.PREFIX)]
        detached = [line for line in lines if not line.startswith(profile.PREFIX)] + profile_lines
        self.reject('\n'.join(detached))

    def test_counter_bounds_reversals_ack_drift_and_terminal_clock(self):
        text = synthetic()
        command = 'HOST_MAC_PROFILE_COMMAND run=0 pc=1'
        for key, value in (('cycle', 136), ('useful_macs', 1), ('executed_macs', 0),
                           ('useful_macs', 1025), ('executed_macs', 1025),
                           ('executed_macs', 4096 * 200 + 512), ('wide_steps', 7),
                           ('wide_steps', 208), ('pipeline_stalls', 9),
                           ('pipeline_stalls', 210), ('read_beats', 1),
                           ('read_ack_beats', 5), ('write_ack_beats', 3)):
            with self.subTest(key=key, value=value):
                self.reject(change(text, command, key, value))
        for key, value in (('cycles', 2202), ('status', 3), ('idma_transfers', 11),
                           ('read_ack_beats', 43), ('write_ack_beats', 21), ('cycle', 2236)):
            with self.subTest(key=key, value=value):
                self.reject(change(text, 'HOST_MAC_PROFILE_END run=0', key, value))

    def test_same_dut_reset_reordering_and_counter_drift(self):
        text = synthetic()
        for key, value in (('cycle', 2244), ('wide_steps', 0), ('pipeline_stalls', 76),
                           ('idma_transfers', 79), ('run', 0)):
            with self.subTest(key=key):
                self.reject(change(text, 'HOST_MAC_PROFILE_BEGIN run=1', key, value))
        self.reject(change(text, 'HOST_ATTN_BLOCK_PAIR', 'resets_between_launches', 1))
        lines = text.splitlines()
        first = next(i for i, line in enumerate(lines) if line.startswith('HOST_ATTN_BLOCK_COMMAND run=0 pc=0 '))
        second = first + 2
        lines[first:first + 4] = lines[second:second + 2] + lines[first:first + 2]
        self.reject('\n'.join(lines))

    def test_actual_audit_cross_binding_rejects_counter_cycle_status_and_hold_drift(self):
        text = synthetic()
        for starts, key, value in (
                ('HOST_ATTN_BLOCK_BEGIN run=0', 'mode', 'final-residual-ack-error'),
                ('HOST_ATTN_BLOCK_BEGIN run=0', 'commands', 21),
                ('HOST_ATTN_BLOCK_COMMAND run=0 pc=1', 'cycle', 237),
                ('HOST_ATTN_BLOCK_COMMAND run=0 pc=1', 'status', 3),
                ('HOST_ATTN_BLOCK_END run=0', 'useful_macs', 5633),
                ('HOST_ATTN_BLOCK_END run=0', 'read_beats', 45),
                ('HOST_ATTN_BLOCK_END run=0', 'idma_transfers', 67),
                ('HOST_ATTN_BLOCK_END run=0', 'successful', 21),
                ('HOST_ATTN_BLOCK_END run=0', 'status', 3),
                ('HOST_ATTN_BLOCK_RESULT_HOLD run=0 cycle=2238', 'cycle', 2239),
                ('HOST_ATTN_BLOCK_RESULT_HOLD run=0 cycle=2238', 'completed', 21)):
            with self.subTest(starts=starts, key=key):
                self.reject(change(text, starts, key, value))

    def test_unrelated_stdout_is_hashed_without_becoming_payload(self):
        text = synthetic()
        one, two = self.collect(text), self.collect(text + 'additional stdout\n')
        self.assertNotEqual(one.pop('log_sha256'), two.pop('log_sha256'))
        self.assertEqual(one, two)

    def test_unknown_mode_missing_file_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stdout.log'
            with self.assertRaises(ValueError):
                profile.collect(path, 'pass')
            path.write_text(synthetic())
            with self.assertRaises(ValueError):
                profile.collect(path, 'diagnostic-prefix')
            alias = Path(directory) / 'alias.log'
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                profile.collect(alias, 'pass')


if __name__ == '__main__':
    unittest.main()
