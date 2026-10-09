"""Cheap negative evidence checks; these tests do not stand in for an RTL run."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import host_bf16_gdn_block_execution as execution
from pack_host_bf16_gdn_block_fixture import GdnBlockFixtureSession


class GdnBlockExecutionTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'actual.log'
            path.write_text(text)
            return execution._events(path)

    def test_failure_marker_unknown_fields_and_duplicate_fields_reject(self):
        for text in ('HOST_BF16_GDN_BLOCK_FAIL: watchdog\n',
                     'HOST_BF16_GDN_BLOCK_WRITE_ACK run=0\n',
                     'HOST_BF16_GDN_BLOCK_CARRY_READ run=1 pc=5 cycle=8 address=64 bytes=64 producer=5 pc=6\n',
                     'HOST_BF16_GDN_BLOCK_CARRY_READ run=1 pc=5 cycle=8 address=64 bytes=64 producer=5 injected=1\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)

    def test_raw_unsupported_mask_is_parsed_without_integer_truncation(self):
        line = 'HOST_BF16_GDN_BLOCK_WRITE_ACK run=1 pc=5 cycle=99 address=4096 bus_bytes=64 write_bytes=32 mask=18446744069414584320 error=0 final=1\n'
        event = self.parse(line)[0][1]
        self.assertEqual(int(event['mask']), 0xffffffff00000000)
        self.assertEqual(int(event['mask']).bit_count(), int(event['write_bytes']))

    def test_native_fp32_error_is_not_bf16_truncated_or_a_pass_gate(self):
        a = np.array([1, -0.0], '<f4')
        b = np.array([np.nextafter(np.float32(1), np.float32(2)), 0.0], '<f4')
        metric = execution._native_metrics(a.tobytes(), b.tobytes(), 4)
        self.assertEqual(metric['bit_mismatches'], 2)
        self.assertEqual(metric['max_abs'], 2**-23)
        self.assertNotIn('pass', metric)
        self.assertEqual(metric['acceptance'], 'UNASSIGNED_DIAGNOSTIC_ONLY')

    def test_saved_or_forged_source_authority_cannot_admit_evidence(self):
        for authority in (None, {}, {'source_authenticated': True}):
            with self.subTest(authority=authority), self.assertRaisesRegex(ValueError, 'live'):
                execution.audit_artifacts('/tmp', '/tmp', '/tmp', session=authority)
        forged = object.__new__(GdnBlockFixtureSession)
        with self.assertRaisesRegex(ValueError, 'unissued'):
            execution.audit_artifacts('/tmp', '/tmp', '/tmp', session=forged)

    def test_physical_replay_closes_and_rejects_state_and_mask_tampering(self):
        # A compact artificial transcript tests the replay parser, never DUT
        # numerical/source acceptance. Source admission is explicitly mocked;
        # this path does not issue a production source authority.
        layout = copy.deepcopy(execution.build_layout())
        address = layout['base'] + 0x5000
        remap = {}
        for entry in layout['inputs']:
            remap[entry['address']] = address
            entry.update(address=address, bytes=64)
            address += 128
        layout['scratch'] = address
        for launch in layout['launches']:
            for op in launch['operations']:
                for span in op['writes']:
                    remap[span['address']] = address
                    span.update(address=address, bytes=64)
                    address += 128
        layout['limit'] = address
        for launch in layout['launches']:
            for op in launch['operations']:
                for read in op['reads']:
                    read.update(address=remap[read['address']], bytes=64)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); fixture, output = root/'fixture', root/'output'
            fixture.mkdir(); output.mkdir(); (fixture/'manifest.json').write_text('{}\n')
            for entry in layout['inputs']:
                (fixture/entry['file']).write_bytes(bytes(64))
            execution._write_launch(layout, lambda name, raw: (fixture/name).write_bytes(raw))
            memory = execution._initial(fixture, layout)
            transcript, cycle = [], 100
            def emit(kind, **fields):
                self.assertEqual(set(fields), set(execution.SCHEMA[kind].split()))
                transcript.append(execution.PREFIX+kind+' '+' '.join(f'{k}={v}' for k,v in fields.items()))
            for token, launch in enumerate(layout['launches']):
                directory = output/('carried' if token else 'cold'); directory.mkdir()
                emit('BEGIN', run=token, commands=17, epoch=9+token, mode='carried' if token else 'cold', same_dut=1, reset_between_launches=0)
                count, physical = 0, 0
                for pc, op in enumerate(launch['operations']):
                    for source in op['reads']:
                        if 0 <= source['producer'] < token*17:
                            cycle += 1
                            emit('CARRY_READ', run=token, pc=pc, cycle=cycle, address=source['address'], bytes=64, producer=source['producer'])
                    stage_bytes = sum(s['bytes'] for s in op['writes']); acknowledged = 0
                    for span in op['writes']:
                        for name in (span['expected'], span['native']):
                            (fixture/name).write_bytes(bytes(64))
                        if span['name'] == 'conv':
                            (fixture/f'conditioned_conv{token}.bf16le').write_bytes(bytes(64))
                        (directory/('actual_'+span['expected'].removeprefix('expected_'))).write_bytes(bytes(64))
                        masks = ((1<<64)-1,)
                        for mask in masks:
                            final = int(acknowledged+mask.bit_count() == stage_bytes)
                            cycle += 1
                            emit('WRITE_REQUEST', run=token, pc=pc, cycle=cycle, address=span['address'], bus_bytes=64, final=final)
                            cycle += 54
                            emit('WRITE_ACK', run=token, pc=pc, cycle=cycle, address=span['address'], bus_bytes=64,
                                 write_bytes=mask.bit_count(), mask=mask, error=0, final=final)
                            for byte in range(64):
                                if mask >> byte & 1:
                                    memory[span['address']-layout['base']+byte] = 0
                            acknowledged += mask.bit_count(); physical += 1
                    for _ in range(11):
                        cycle += 1
                        emit('COMPLETION_HOLD', run=token, pc=pc, cycle=cycle, word=pc|op['engine']<<29|op['event_signal']<<40)
                    for span in op['writes']:
                        fixed = span['name'] in ('qkv', 'z', 'ab', 'conv')
                        emit('NATIVE', run=token, stage=span['name'], elements=64//span['element_bytes'], element_bytes=span['element_bytes'],
                             bit_mismatches=0, max_abs=0, mean_abs=0, same_input_max_bf16_ulp=0,
                             fixed_operator_gate='PASS' if fixed else 'UNASSIGNED',
                             acceptance='FROZEN_OPERATOR_THRESHOLDS' if fixed else 'UNASSIGNED_DIAGNOSTIC_ONLY')
                    cycle += 1
                    emit('COMMAND', run=token, cycle=cycle, operation=op['kind'], pc=pc, status=0, signal=op['event_signal'],
                         write_ack_bytes=acknowledged, canonical_bit_mismatches=0, previous_outputs_preserved=1,
                         guards_unchanged=1, persistent_commit=int(pc==16), expected_committed_generation=token+int(pc==16))
                    (directory/f'writable_after_command{pc}.bin').write_bytes(memory[layout['scratch']-layout['base']:])
                    count += acknowledged
                (directory/'ddr_after.bin').write_bytes(memory)
                emit('END', run=token, status=0, result_epoch=9+token, result_pc=16, completions=17, issued_jobs=16, metadata_reads=233,
                     read_beats=300, read_ack_beats=300, write_beats=physical, write_ack_beats=physical, write_ack_bytes=count,
                     published_bytes=count, committed_generation=token+1, canonical_bit_mismatches=0,
                     frozen_operator_gate='PASS', native_core_gate='UNASSIGNED_DIAGNOSTIC_ONLY', full_block_supported=1)
            emit('PASS', scope='GDN_FULL_BLOCK', tokens=2, heads=16, commands=34, owner_jobs=32, fences=2, canonical_bit_mismatches=0,
                 actual_dense_macs=execution.ACTUAL_DENSE_MACS, same_dut=1, reset_between_launches=0, actual_ack_history_state_carry=1,
                 expected_output_injection=0, logical_matrix_engines=1, physical_matrix_slices=8, idma_instances=1,
                 shared_scalar_services=1, input_norm_dut=1, o_projection_dut=1, residual_dut=1, ffn_dut=1,
                 native_core_gate='UNASSIGNED_DIAGNOSTIC_ONLY', frozen_operator_gate='PASS', native_full_block_gate='DEFERRED_TO_AUDIT', full_block_supported=1)
            log = root/'actual.log'; baseline='\n'.join(transcript)+'\n'; log.write_text(baseline)
            fake = object.__new__(GdnBlockFixtureSession)
            with patch.object(GdnBlockFixtureSession, 'verify', return_value={'layout': layout, 'native_full_block_gate_pass': False, 'native_operator_gate_pass': True, 'native_full_block_metrics': [{'checks': {}}, {'checks': {}}]}), \
                 patch.object(execution, 'build_layout', return_value=layout), \
                 patch.object(execution, '_frozen_gates', return_value=[]):
                result = execution.audit_artifacts(fixture, output, log, session=fake)
                self.assertTrue(result['canonical_block_pass'])
                self.assertFalse(result['native_full_block_gate_pass'])
                self.assertFalse(result['overall_pass'])
                self.assertEqual(result['status'], 'FAIL_HOST_GDN_BLOCK_NATIVE_ACCEPTANCE')
                self.assertFalse(result['actual_dut_identity_verified'])
                self.assertFalse(result['source_immutability_verified'])
                self.assertIsNone(result['native_core_gate_pass'])
                self.assertEqual(result['runs'][1]['carried_history_state_read_beats'], {'4': 1, '6': 1})
                # Missing beat, illegal masks, a changed readonly word, and absent carried
                # state reads must each defeat an otherwise intact PASS line.
                line = next(x for x in transcript if 'WRITE_ACK ' in x and 'pc=6 ' in x)
                for mask in (0, 0xffffffff, 0xffffffff00000000, 0xfffffffeffffffff):
                    bad = line.replace('mask=18446744073709551615 ', f'mask={mask} ').replace('write_bytes=64 ', f'write_bytes={mask.bit_count()} ')
                    log.write_text(baseline.replace(line, bad, 1))
                    with self.assertRaisesRegex(ValueError, 'unsupported output strobe'):
                        execution.audit_artifacts(fixture, output, log, session=fake)
                log.write_text(baseline.replace(line+'\n', '', 1))
                with self.assertRaises(ValueError): execution.audit_artifacts(fixture, output, log, session=fake)
                log.write_text(baseline)
                final = output/'carried/ddr_after.bin'; saved = final.read_bytes()
                modified = bytearray(saved); modified[layout['metadata_limit']-layout['base']] ^= 1; final.write_bytes(modified)
                with self.assertRaisesRegex(ValueError, 'whole physical DDR'): execution.audit_artifacts(fixture, output, log, session=fake)
                final.write_bytes(saved)
                log.write_text('\n'.join(x for x in transcript if not ('CARRY_READ ' in x and 'producer=6' in x))+'\n')
                with self.assertRaisesRegex(ValueError, 'carried state spans'): execution.audit_artifacts(fixture, output, log, session=fake)


if __name__ == '__main__':
    unittest.main()
