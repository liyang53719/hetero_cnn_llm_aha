"""Adversarial synthetic artifacts only: no model capture, compilation or RTL run.

The source verifier is explicitly mocked when issuing the unit fixture's live
session. None of these test results constitute production numerical acceptance.
"""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import host_bf16_gdn_execution as execution
from host_bf16_gdn_descriptor import HostGdnDenseBinding, HostGdnConvBinding, build_gdn_commands
from pack_host_bf16_gdn_fixture import GdnFixtureSession, conv_recipe, CHANNELS, TAPS


class HostGdnExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='test_gdn_execution_', dir=execution.ROOT / 'work')
        self.base = Path(self.temp.name)
        self.fixture = self.base / 'fixture'; self.fixture.mkdir()
        self.make_fixture()
        self.source_check = patch.object(execution, 'verify', return_value=dict(
            status='PASS_AUTHENTICATED_HOST_GDN_FIXTURE', native_gate_pass=True,
            verification='EXPLICIT_SYNTHETIC_UNIT_MOCK'))
        self.source_identity = patch.object(execution, '_source_identity', return_value={'synthetic_source': 'unit-only'})
        self.mock_verify = self.source_check.start(); self.source_identity.start()
        self.addCleanup(self.source_check.stop); self.addCleanup(self.source_identity.stop)
        self.addCleanup(self.temp.cleanup)
        self.authority = execution.authenticate_fixture(self.fixture)
        self.layout, self.specs = execution._layout(self.fixture)
        self.canonical = execution._canonical(self.fixture, self.specs)

    def make_fixture(self):
        """Meaningful synthetic signed zeros/history; mocked source authority."""
        base = 0x120000000; cb = base; db = base + 0x1000; meta = base + 0x2000; cursor = base + 0x10000
        def allocate(size):
            nonlocal cursor
            address = cursor; cursor += (size + 63) // 64 * 64 + 0x1000
            return address
        aa = [allocate(2048) for _ in range(2)]
        wd = allocate(1024 * CHANNELS * 2); wc = allocate(CHANNELS * TAPS * 2); hi = allocate(CHANNELS * TAPS * 2)
        scratch = cursor; cursor += 0x1000
        dense, conv, histories = [], [], []
        for _ in range(2):
            dense.append(allocate(CHANNELS * 2)); conv.append(allocate(CHANNELS * 2)); histories.append(allocate(CHANNELS * TAPS * 2))
        bindings = [HostGdnDenseBinding(1, aa[0], wd, dense[0]),
                    HostGdnConvBinding(1, dense[0], wc, conv[0], hi, histories[0], True),
                    HostGdnDenseBinding(1, aa[1], wd, dense[1]),
                    HostGdnConvBinding(1, dense[1], wc, conv[1], histories[0], histories[1], False, 1)]
        commands, records = build_gdn_commands(bindings)
        def write(name, raw): (self.fixture / name).write_bytes(raw)
        write('host_commands.bin', b''.join(c.pack().to_bytes(16, 'little') for c in commands))
        write('host_descriptors.bin', b''.join(records[i].pack().to_bytes(16, 'little') for i in range(len(records))))
        launch = 'HOST_GDN_DENSE_CONV_V1\n' + ' '.join(map(str, [base, cursor, cb, cb + 64, 4, db, db + 960, 60, meta, scratch, wd, wc, hi])) + '\n'
        for pc, (b, c) in enumerate(zip(bindings, commands)):
            is_dense = pc % 2 == 0
            launch += ' '.join(map(str, [pc // 2, int(is_dense), b.activation_ddr, b.weight_ddr, b.output_ddr,
                    0 if is_dense else b.history_input_ddr, 0 if is_dense else b.history_output_ddr,
                    12 if is_dense else 18, pc, pc + 1, c.dst])) + '\n'
        write('launch.txt', launch.encode())
        write('weight_dense.bf16le', bytes(1024 * CHANNELS * 2))
        weights = np.zeros((CHANNELS, TAPS), dtype='<u2'); weights[:, 2:] = 0x3f80
        write('weight_conv.bf16le', weights.tobytes())
        history = np.zeros_like(weights); write('initial_history.bf16le', history.tobytes())
        for token in range(2):
            raw = np.resize(np.array([0, 0x8000, 0x3f00 + token * 128, 0xbf00], dtype='<u2'), (1, CHANNELS))
            native_dense = raw.copy(); native_dense[0, 0] ^= 0x8000
            cv, output, history = conv_recipe(raw, weights, history, token == 0)
            native_output = output.copy(); native_output[0, 0] ^= 0x8000
            native_history = history.copy(); native_history[0, 0] ^= 0x8000
            for name, data in [('activation', bytes(2048)), ('independent_dense', raw.tobytes()),
                               ('native_dense', native_dense.tobytes()), ('expected_conv', cv.tobytes()),
                               ('expected_output', output.tobytes()), ('expected_history', history.tobytes()),
                               ('native_output', native_output.tobytes()), ('native_history', native_history.tobytes()),
                               ('conditioned_output', native_output.tobytes())]:
                write(name + str(token) + '.bf16le', data)
        write('c_matrix', b'UNIT TEST DUMMY, NEVER EXECUTED')
        write('manifest.json', json.dumps({'native_full_block_status': 'NOT_EVALUATED_BY_SYNTHETIC_TEST'}).encode())

    def fake_artifacts(self, mode='pass'):
        output = self.base / ('mock_' + mode); output.mkdir()
        log = self.base / (mode + '.log'); lines = []; cycle = 0
        def event(kind, **fields):
            self.assertEqual(set(fields), set(execution.SCHEMA[kind].split()))
            lines.append(execution.PREFIX + kind + ' ' + ' '.join(key + '=' + str(value) for key, value in fields.items()))
        modes = [mode, 'pass'] if mode == 'reset-recovery' else [mode]
        for run, selected in enumerate(modes):
            directory = output if run == 0 else output / 'recovery'; directory.mkdir(exist_ok=True)
            memory = execution._initial(self.fixture, self.layout, self.specs, selected)
            for name in execution.OPERATIONS:
                (directory / ('reference_' + name + '.bf16le')).write_bytes(self.canonical[name])
            failed = 2 if selected == 'output-alias' else 0 if selected == 'reset-recovery' else 3
            successful = 4 if selected == 'pass' else failed
            completions = 4 if selected == 'pass' else failed + 1
            ack_total = 0; accepted_total = 0
            event('BEGIN', run=run, mode=selected, commands=4, epoch=9 + run)
            for pc in range(completions):
                spec = self.specs[pc]; ok = pc < successful; ack = 0
                if ok or selected == 'last-history-ack-error':
                    for name, low, length in spec['spans']:
                        for address in range(low, low + length, 1024):
                            size = min(1024, low + length - address); final = int(address + size == spec['final_end']); cycle += 1
                            event('WRITE_REQUEST', run=run, pc=pc, cycle=cycle, address=address, bytes=size, final=final)
                            cycle += 64; error = int(selected == 'last-history-ack-error' and pc == 3 and final)
                            event('WRITE_ACK', run=run, pc=pc, cycle=cycle, address=address, bytes=size, error=error, final=final)
                            accepted_total += size
                            if not error:
                                offset = address - self.layout['base']; source = address - low
                                memory[offset:offset + size] = self.canonical[name][source:source + size]
                                ack += size; ack_total += size
                status = 0 if ok else 9 if selected == 'output-alias' else 3
                engine = 2 if spec['dense'] else 3
                for _ in range(11):
                    cycle += 1
                    event('COMPLETION_HOLD', run=run, pc=pc, cycle=cycle,
                          word=pc | engine << 29 | status << 32 | (pc + 1) << 40)
                cycle += 1
                event('COMMAND', run=run, cycle=cycle, operation=spec['name'], pc=pc, status=status,
                      signal=pc + 1, write_ack_bytes=ack, published=int(ok), previous_outputs_preserved=1, guards_unchanged=1)
                (directory / ('writable_after_command' + str(pc) + '.bin')).write_bytes(memory[self.layout['scratch'] - self.layout['base']:])
            (directory / 'ddr_after.bin').write_bytes(memory)
            for spec in self.specs:
                for name, address, size in spec['spans']:
                    offset = address - self.layout['base']
                    (directory / ('actual_' + name + '.bf16le')).write_bytes(memory[offset:offset + size])
            published = sum(spec['bytes'] for spec in self.specs[:successful])
            metadata = sum(spec['records'] + 1 for spec in self.specs[:completions])
            if selected == 'pass':
                for name in execution.OPERATIONS:
                    event('NATIVE', run=run, stage=name, **execution._native(self.fixture, name, self.canonical[name]))
                event('PASS', run=run, scope=execution.SCOPE, commands=4, tokens=2, checked_bf16=73728,
                      canonical_bit_differences=0, independent_terminal_checked=1, native_operator_gate='PASS', cycles=cycle,
                      write_ack_bytes=ack_total, metadata_reads=metadata, logical_matrix_engines=1, physical_matrix_slices=8,
                      idma_instances=1, shared_scalar_services=1, unchanged_guards=1, prior_outputs_preserved=1,
                      delayed_final_ack_commands=4, completion_backpressure_commands=4, actual_dma_intermediate_sources=1,
                      history_generations=2, output_spans=6, input_norm_dut=0, full_block_supported=0)
            else:
                event('FAULT_PASS', run=run, mode=selected, failed_pc=failed, status=status, successful_commands=successful,
                      write_ack_bytes=ack_total, published_bytes=published, failed_command_published_bytes=0,
                      previous_outputs_preserved=1, guards_unchanged=1)
            event('END', run=run, status=0 if selected == 'pass' else status, result_epoch=9 + run,
                  result_pc=completions - 1, completions=completions, successful=successful,
                  issued_jobs=2 if selected == 'output-alias' else completions, metadata_reads=metadata,
                  read_beats=metadata, read_ack_beats=metadata, write_beats=accepted_total // 64,
                  write_ack_beats=accepted_total // 64, published_bytes=published, reset_required=int(selected != 'pass'))
        if mode == 'reset-recovery':
            event('RESET_RECOVERY_PASS', same_dut=1, unchanged_input_constants=1, expected_output_injection=0, commands=4)
        log.write_text('\n'.join(lines) + '\n')
        return output, log

    def verify(self, output, log, mode='pass'):
        return execution.verify_execution(self.fixture, output, log, mode, authority=self.authority)

    @staticmethod
    def replace_field(line, key, value):
        return ' '.join((key + '=' + str(value)) if part.startswith(key + '=') else part for part in line.split())

    def test_all_modes_check_six_spans_and_never_claim_dut_identity(self):
        for mode in execution.MODES:
            with self.subTest(mode=mode):
                output, log = self.fake_artifacts(mode); result = self.verify(output, log, mode)
                self.assertEqual(result['status'], 'PASS_HOST_GDN_ARTIFACT_CHECK_ONLY')
                self.assertFalse(result['actual_dut_identity_verified'])
                self.assertFalse(result['full_block_supported']); self.assertFalse(result['input_norm_dut'])
                final = result['runs'][-1]
                self.assertEqual(len(final['actual_sha256']), 6)
                self.assertEqual(final['successful_commands'], 4 if mode in ('pass', 'reset-recovery') else 2 if mode == 'output-alias' else 3)
                if mode in ('pass', 'reset-recovery'):
                    self.assertEqual(final['write_ack_bytes'], 147456)
                    self.assertEqual(final['metadata_reads'], 64)
                    self.assertEqual(set(final['native_history']), {'history0', 'history1'})
                    self.assertEqual(final['native']['conv0']['same_input_bit_differences'], 1)
                    self.assertEqual(final['native']['conv0']['same_input_numeric_differences'], 0)
                if mode == 'last-history-ack-error':
                    self.assertEqual(final['published_bytes'], 86016)
                    self.assertEqual(final['write_ack_bytes'], 146432)
        self.assertEqual(self.mock_verify.call_count, 1, 'cached authority must not repeat model recomputation')

    def test_authority_is_opaque_and_bound_to_all_bytes_and_sources(self):
        with self.assertRaises(TypeError): execution.ExecutionSession()
        forged = object.__new__(execution.ExecutionSession)
        with self.assertRaisesRegex(ValueError, 'unissued'): forged.verify(self.fixture)
        for fake in ({'status': 'PASS_AUTHENTICATED_HOST_GDN_FIXTURE'}, object()):
            with self.assertRaisesRegex(ValueError, 'issued ExecutionSession'):
                execution.verify_execution(self.fixture, self.base, self.base / 'none', 'pass', authority=fake)
            with self.assertRaisesRegex(ValueError, 'live GdnFixtureSession'):
                execution.authenticate_fixture(self.fixture, session=fake)
        with self.assertRaisesRegex(ValueError, 'one source authority'):
            execution.verify_execution(self.fixture, self.base, self.base / 'none', 'pass', authority=self.authority, session=object())
        for name in ('manifest.json', 'c_matrix', 'native_dense0.bf16le', 'activation0.bf16le'):
            path = self.fixture / name; raw = path.read_bytes(); path.write_bytes(raw + b'!')
            with self.assertRaisesRegex(ValueError, 'bytes/inventory changed'): self.authority.verify(self.fixture)
            path.write_bytes(raw)
        with patch.object(execution, '_source_identity', return_value={'synthetic_source': 'changed'}):
            with self.assertRaisesRegex(ValueError, 'source identity changed'): self.authority.verify(self.fixture)
        other = self.base / 'other'; other.mkdir()
        with self.assertRaisesRegex(ValueError, 'different authenticated'): self.authority.verify(other)
        copied = self.authority.verify(self.fixture); copied['native_gate_pass'] = False
        self.assertTrue(self.authority.verify(self.fixture)['native_gate_pass'])

    def test_factory_rejects_unissued_gdn_session_and_authentication_race(self):
        forged = object.__new__(GdnFixtureSession)
        with patch.object(execution, 'verify', side_effect=lambda fixture, session: session.verify(fixture)):
            with self.assertRaisesRegex(ValueError, 'unissued'): execution.authenticate_fixture(self.fixture, session=forged)
        def mutate(fixture, session):
            (fixture / 'c_matrix').write_bytes(b'changed during independent recomputation')
            return dict(status='PASS_AUTHENTICATED_HOST_GDN_FIXTURE', native_gate_pass=True)
        with patch.object(execution, 'verify', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during authentication'): execution.authenticate_fixture(self.fixture)

    def test_missing_duplicate_unknown_and_reordered_events_rejected(self):
        output, log = self.fake_artifacts(); original = log.read_text(); rows = original.splitlines()
        command = next(row for row in rows if row.startswith(execution.PREFIX + 'COMMAND '))
        hold = next(row for row in rows if row.startswith(execution.PREFIX + 'COMPLETION_HOLD '))
        ack = next(row for row in rows if row.startswith(execution.PREFIX + 'WRITE_ACK '))
        mutations = [original + execution.PREFIX + 'FAIL: synthetic\n', original.replace(command, command + '\n' + command),
                     original.replace(command + '\n', ''), original.replace(hold + '\n', ''), original.replace(ack, ack + '\n' + ack),
                     original.replace('result_epoch=9', 'result_epoch=10'), original.replace('result_pc=3', 'result_pc=2'),
                     original.replace(command, command + ' unknown=1'), original.replace(ack, ack + ' bytes=1024'),
                     original.replace('metadata_reads=64', 'metadata_reads=63')]
        # Removing the first ACK leaves a real write pending at the next request.
        mutations.append(original.replace(ack + '\n', '', 1))
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index):
                log.write_text(changed)
                with self.assertRaises(ValueError): self.verify(output, log)

    def test_completion_backpressure_final_ack_delay_and_engine_rejected(self):
        output, log = self.fake_artifacts(); original = log.read_text(); rows = original.splitlines()
        final_index = next(i for i, row in enumerate(rows) if row.startswith(execution.PREFIX + 'WRITE_REQUEST ') and 'final=1' in row)
        request = rows[final_index]; ack = rows[final_index + 1]
        cycle = int(dict(part.split('=') for part in request.split()[1:])['cycle'])
        hold = next(row for row in rows if row.startswith(execution.PREFIX + 'COMPLETION_HOLD ') and 'pc=1 ' in row)
        word = int(dict(part.split('=') for part in hold.split()[1:])['word'])
        command = next(row for row in rows if row.startswith(execution.PREFIX + 'COMMAND '))
        mutations = [original.replace(ack, self.replace_field(ack, 'cycle', cycle + 1)),
                     original.replace(hold, self.replace_field(hold, 'word', word ^ (1 << 29))),
                     original.replace(command + '\n', '').replace(ack, command + '\n' + ack)]
        first_hold = {}; repeated = []
        for row in rows:
            if row.startswith(execution.PREFIX + 'COMPLETION_HOLD '):
                pc = dict(part.split('=') for part in row.split()[1:])['pc']
                first_hold.setdefault(pc, row); row = first_hold[pc]
            repeated.append(row)
        mutations.append('\n'.join(repeated) + '\n')
        for changed in mutations:
            log.write_text(changed)
            with self.assertRaises(ValueError): self.verify(output, log)

    def test_write_gap_readonly_alias_overlap_and_fault_flag_rejected(self):
        output, log = self.fake_artifacts(); original = log.read_text(); rows = original.splitlines()
        request = next(row for row in rows if row.startswith(execution.PREFIX + 'WRITE_REQUEST '))
        ack = next(row for row in rows if row.startswith(execution.PREFIX + 'WRITE_ACK '))
        second = [row for row in rows if row.startswith(execution.PREFIX + 'WRITE_REQUEST ')][1]
        addresses = [self.layout['scratch'], self.specs[0]['activation'], self.specs[1]['output'],
                     self.specs[0]['output'] + execution.OUTPUT_BYTES - 64]
        mutations = [original.replace(request, self.replace_field(request, 'address', address)) for address in addresses]
        mutations += [original.replace(second, self.replace_field(second, 'address', self.specs[0]['output'])),
                      original.replace(ack, self.replace_field(ack, 'error', 1)),
                      original.replace(request, self.replace_field(request, 'final', 1)),
                      original.replace(request, self.replace_field(request, 'bytes', 1088))]
        for changed in mutations:
            log.write_text(changed)
            with self.assertRaises(ValueError): self.verify(output, log)

    def test_final_readonly_guard_prior_output_and_raw_history_corruption_rejected(self):
        output, log = self.fake_artifacts()
        cases = [('ddr_after.bin', self.specs[0]['activation'] - self.layout['base']),
                 ('ddr_after.bin', self.layout['scratch'] - self.layout['base']),
                 ('writable_after_command3.bin', self.specs[0]['output'] - self.layout['scratch']),
                 ('writable_after_command2.bin', self.specs[1]['history_out'] - self.layout['scratch']),
                 ('writable_after_command0.bin', self.specs[3]['output'] - self.layout['scratch']),
                 ('actual_history1.bf16le', 6), ('actual_dense0.bf16le', 6), ('reference_conv0.bf16le', 6)]
        for filename, offset in cases:
            with self.subTest(filename=filename, offset=offset):
                path = output / filename; raw = path.read_bytes(); changed = bytearray(raw); changed[offset] ^= 1
                path.write_bytes(changed)
                with self.assertRaises(ValueError): self.verify(output, log)
                path.write_bytes(raw)

    def test_actual_and_cpp_reference_agreeing_on_wrong_answer_still_rejected(self):
        output, log = self.fake_artifacts()
        for prefix in ('actual_', 'reference_'):
            path = output / (prefix + 'dense0.bf16le'); changed = bytearray(path.read_bytes()); changed[6] ^= 1; path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, 'independent canonical'): self.verify(output, log)

    def test_missing_extra_and_symlink_artifacts_rejected(self):
        output, log = self.fake_artifacts()
        path = output / 'unclaimed.bin'; path.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'inventory drift'): self.verify(output, log)
        path.unlink(); path.symlink_to(output / 'ddr_after.bin')
        with self.assertRaisesRegex(ValueError, 'symlink'): self.verify(output, log)
        path.unlink(); (output / 'reference_conv1.bf16le').unlink()
        with self.assertRaises(FileNotFoundError): self.verify(output, log)

    def test_native_event_metrics_come_from_raw_actual_bytes(self):
        output, log = self.fake_artifacts(); original = log.read_text()
        native = next(row for row in original.splitlines() if row.startswith(execution.PREFIX + 'NATIVE ') and 'stage=conv0 ' in row)
        changes = [('bit_differences', 0), ('max_abs', .01), ('mean_abs', .001),
                   ('same_input_bit_differences', 0), ('same_input_numeric_differences', 1),
                   ('same_input_max_bf16_ulp', 1), ('signed_zero_numeric_equal', 0), ('gate', 'FAIL')]
        for key, value in changes:
            with self.subTest(metric=key):
                log.write_text(original.replace(native, self.replace_field(native, key, value)))
                with self.assertRaises(ValueError): self.verify(output, log)
        log.write_text(original.replace(native + '\n', ''))
        with self.assertRaisesRegex(ValueError, 'missing native comparisons'): self.verify(output, log)

    def test_fixed_native_thresholds_signed_zero_and_one_ulp(self):
        plus = np.array([0, 0x8000, 0x3f80], dtype='<u2').tobytes()
        minus = np.array([0x8000, 0, 0x3f80], dtype='<u2').tobytes()
        metric = execution._metric(plus, minus)
        self.assertEqual(metric['bit_differences'], 2); self.assertEqual(metric['max_abs'], 0)
        self.assertEqual(metric['gate'], 'PASS')
        bad = np.array([0x7fc0], dtype='<u2').tobytes()
        with self.assertRaisesRegex(ValueError, 'nonfinite'): execution._metric(bad, bad)
        self.assertEqual(execution._metric(np.array([0x3f80], dtype='<u2').tobytes(), bytes(2))['gate'], 'FAIL')
        name = 'conv0'; target_path = self.fixture / 'conditioned_output0.bf16le'
        target = np.frombuffer(self.canonical[name], dtype='<u2').copy(); index = int(np.flatnonzero(target == 0x3e9f)[0]) if np.any(target == 0x3e9f) else 2
        # The numerical native target remains exactly canonical; same-input ULP
        # is a separate unchanged condition and must reject two ULPs.
        native_path = self.fixture / 'native_output0.bf16le'; native_path.write_bytes(self.canonical[name])
        target[index] += 1; target_path.write_bytes(target.tobytes())
        self.assertEqual(execution._native(self.fixture, name, self.canonical[name])['same_input_max_bf16_ulp'], 1)
        target[index] += 1; target_path.write_bytes(target.tobytes())
        with self.assertRaisesRegex(ValueError, 'one-BF16-ULP'): execution._native(self.fixture, name, self.canonical[name])

    def test_reset_recovery_must_include_both_runs_and_exact_terminal_marker(self):
        output, log = self.fake_artifacts('reset-recovery'); original = log.read_text()
        marker = original.splitlines()[-1]
        for changed in (original.replace(marker + '\n', ''), original.replace('same_dut=1', 'same_dut=0'),
                        original + marker + '\n', original.replace('run=1 mode=pass commands=4 epoch=10', 'run=1 mode=pass commands=4 epoch=9')):
            log.write_text(changed)
            with self.assertRaises(ValueError): self.verify(output, log, 'reset-recovery')

    def test_fault_partial_history_cannot_be_published_or_written_on_error(self):
        output, log = self.fake_artifacts('last-history-ack-error'); original = log.read_text()
        log.write_text(original.replace('failed_command_published_bytes=0', 'failed_command_published_bytes=61440'))
        with self.assertRaises(ValueError): self.verify(output, log, 'last-history-ack-error')
        log.write_text(original)
        path = output / 'actual_history1.bf16le'; raw = bytearray(path.read_bytes()); raw[-1024:] = self.canonical['history1'][-1024:]; path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'not actual physical DDR'): self.verify(output, log, 'last-history-ack-error')

    def test_run_case_rejects_forged_authority_before_any_dut_work(self):
        with patch.object(execution, '_build_identity') as identity, patch.object(execution.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'issued ExecutionSession'):
                execution.run_case(self.base / 'not_a_build', self.fixture, authority={})
            identity.assert_not_called(); run.assert_not_called()

    def test_run_case_timeout_requires_a_bounded_positive_integer(self):
        with patch.object(execution, '_build_identity') as identity, patch.object(execution.subprocess, 'run') as run:
            for timeout in (0, -1, 21601, 5400.0, True, '5400', None):
                with self.subTest(timeout=timeout):
                    with self.assertRaisesRegex(ValueError, 'timeout_seconds'):
                        execution.run_case(self.base / 'not_a_build', self.fixture, authority=self.authority,
                                           timeout_seconds=timeout)
            identity.assert_not_called(); run.assert_not_called()

    def test_run_case_bounded_runner_contract_and_no_reauthentication(self):
        build = self.base / 'fake_build'; build.mkdir()
        fake_identity = {str(build / 'obj/VHostBlockTop'): 'binary', str(build / 'generated/HostBlockTop.sv'): 'rtl',
                         str(build / 'build_ready.json'): 'ready'}
        result = dict(status='PASS_HOST_GDN_ARTIFACT_CHECK_ONLY', actual_dut_identity_verified=False)
        with patch.object(execution, '_build_identity', return_value=fake_identity), \
             patch.object(execution, 'verify_all_build_sources') as sources, \
             patch.object(execution, 'verify_execution', return_value=result) as audit, \
             patch.object(execution.subprocess, 'run') as run:
            run.return_value.returncode = 0
            observed = execution.run_case(build, self.fixture, authority=self.authority, source_root=self.base / 'frozen')
            self.assertTrue(observed['actual_dut_identity_verified'])
            self.assertEqual(run.call_args.kwargs['timeout'], 5400)
            self.assertEqual(run.call_args.args[0][-1], 'pass')
            self.assertIs(audit.call_args.kwargs['authority'], self.authority)
            self.assertEqual(sources.call_count, 2)
            self.assertEqual(sources.call_args.kwargs['source_root'], self.base / 'frozen')
            self.assertEqual(self.mock_verify.call_count, 1)
            self.assertEqual((build / 'pass.exit').read_text(), '0\n')
            self.assertEqual(json.loads((build / 'pass.result.json').read_text())['status'], 'PASS_PRODUCTION_HOST_GDN_CASE')
            execution.run_case(build, self.fixture, authority=self.authority, label='custom_timeout', timeout_seconds=1800)
            self.assertEqual(run.call_args.kwargs['timeout'], 1800)


if __name__ == '__main__':
    unittest.main()
