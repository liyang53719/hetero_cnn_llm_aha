#!/usr/bin/env python3
"""Small transport/lifecycle checks; none of these run or pass the DUT gate."""
from contextlib import ExitStack
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import real2_ci as ci
from pack_owner_multilayer_fixture import pack_layers
from pack_owner_bf16_weights import convert

COMMIT = 'a' * 40
SHA = 'b' * 64


class PackageBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.payload = {name: b'fixture' for name in ci.BASE_FILES | ci.RECEIPT_FILES}
        self.manifest = {'schema': ci.SCHEMA, 'status': ci.BUILT, 'source_commit': COMMIT,
                         'execution_eligible': True,
                         'files': {n: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)} for n, b in self.payload.items()}}

    def archive(self, changes=None, manifest=None, omit=None, extra=None):
        path = self.root / ('package' + str(len(list(self.root.glob('*.gz')))) + '.tar.gz')
        with tarfile.open(path, 'w:gz', format=tarfile.USTAR_FORMAT) as tar:
            def add(name, data, kind=tarfile.REGTYPE, linkname=''):
                info = tarfile.TarInfo(name)
                info.mode = 0o755 if name == 'obj/VHostBlockTop' else 0o644
                info.type = kind; info.linkname = linkname
                info.size = len(data) if kind == tarfile.REGTYPE else 0
                tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
            add(ci.MANIFEST, ci.encoded(manifest or self.manifest))
            for name, data in self.payload.items():
                if name != omit:
                    args = (changes or {}).get(name, (name, data))
                    add(*args)
            for row in extra or []:
                add(*row)
        return path

    def check(self, archive, **kwargs):
        return ci.validate_archive(archive, kwargs.pop('sha', ci.sha(archive)), kwargs.pop('commit', COMMIT), **kwargs)

    def test_valid_bounded_archive(self):
        self.assertEqual(self.check(self.archive()), self.manifest)

    def test_trusted_digest_and_commit_are_required(self):
        archive = self.archive()
        for kwargs in ({'sha': 'c' * 64}, {'commit': 'd' * 40}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(archive, **kwargs)

    def test_rejects_modified_binary_even_when_archive_digest_is_updated(self):
        with self.assertRaisesRegex(ValueError, 'payload digest'):
            self.check(self.archive(changes={'obj/VHostBlockTop': ('obj/VHostBlockTop', b'altered')}))

    def test_rejects_symlinks_hardlinks_devices_and_directories(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE, tarfile.DIRTYPE]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.check(self.archive(changes={'obj/VHostBlockTop': ('obj/VHostBlockTop', b'', kind, '/tmp/elsewhere')}))

    def test_rejects_traversal_absolute_and_noncanonical_names(self):
        for name in ['../outside', '/tmp/outside', 'obj/../outside', 'obj//VHostBlockTop', 'obj\\VHostBlockTop']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(self.archive(changes={'obj/VHostBlockTop': (name, b'fixture')}))

    def test_rejects_extra_duplicate_missing_and_raw_tensor_payload(self):
        for kwargs in [{'extra': [('obj/simulator.o', b'object')]},
                       {'extra': [('obj/VHostBlockTop', b'fixture')]},
                       {'extra': [('tensors/l0_y_actual.f32le', b'tensor')]},
                       {'omit': 'generated/HostBlockTop.sv'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(self.archive(**kwargs))

    def test_rejects_second_tar_after_end_marker(self):
        archive = self.archive()
        extra = io.BytesIO()
        with tarfile.open(fileobj=extra, mode='w') as tar:
            info = tarfile.TarInfo('extra.txt'); info.size = 1; info.mode = 0o644
            tar.addfile(info, io.BytesIO(b'x'))
        with archive.open('ab') as stream:
            stream.write(gzip.compress(extra.getvalue()))
        with self.assertRaisesRegex(ValueError, 'extra file'):
            self.check(archive)

    def test_rejects_oversized_declared_payload(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['files']['obj/VHostBlockTop']['bytes'] = ci.MAX_BYTES + 1
        with self.assertRaises(ValueError):
            self.check(self.archive(manifest=manifest))

    def test_inspection_package_cannot_be_used_as_execution_package(self):
        manifest = copy.deepcopy(self.manifest)
        manifest.update(execution_eligible=False, status='INSPECTION_ONLY_NOT_NUMERICAL_PASS')
        archive = self.archive(manifest=manifest)
        with self.assertRaisesRegex(ValueError, 'cannot execute'):
            self.check(archive)
        self.assertFalse(self.check(archive, inspection=True)['execution_eligible'])

    def test_invalid_archive_creates_no_extraction_directory(self):
        archive = self.archive(extra=[('../outside', b'x')])
        output = self.root / 'unpacked'
        with self.assertRaises(ValueError):
            ci.unpack(self.root, archive, ci.sha(archive), COMMIT, output, True)
        self.assertFalse(output.exists())
        self.assertFalse((self.root / 'outside').exists())

    def test_unpacked_modification_is_rejected(self):
        for name, data in self.payload.items():
            path = self.root / 'evidence' / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        ci.save(self.root / 'evidence' / ci.MANIFEST, self.manifest)
        (self.root / 'evidence/obj/VHostBlockTop').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'unpacked payload changed'):
            ci.validate_unpacked(self.root / 'evidence', COMMIT)

    def test_idma_map_must_match_build_receipt(self):
        sources = ci.encoded({'rtl/file.sv': '0' * 64})
        commits = ci.encoded({'idma': ci.IDMA_PIN})
        identity = {'commits': {'idma': ci.IDMA_PIN}, 'files_verified': 1,
                    'export_manifest_sha256': hashlib.sha256(sources).hexdigest()}
        ci.verify_idma_receipts(identity, sources, commits)
        for changed in [sources.replace(b'0000', b'1111'), sources + b'\n']:
            with self.assertRaises(ValueError):
                ci.verify_idma_receipts(identity, changed, commits)


class FixedFixtureTest(unittest.TestCase):
    def test_original_multilayer_fixture_preserves_actual_layer_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shape = dict(H=1536, F=8960, HEADS=12, KVHEADS=2, HD=128, MAX_TOKENS=1024)
            pack_layers(shape, 16, 2, root / 'fp32', 9467985920)
            convert(root / 'fp32', root / 'fixture')
            (root / 'generated').mkdir()
            scope = dict(matrix_macs=4096, weight_read_burst_beats=16, pipelined=True,
                         burst_writes=False, commit_tail_read=False, overlap_silu=False,
                         host_commands=True, block_launch=False, retained_matrix=True,
                         pinned_idma=True, physical_matrix_slices=8, hidden=1536, ffn=8960)
            ci.save(root / 'generated/SCOPE.json', scope)
            ci.real2_contract(root)
            fixture = ci.read_json(root / 'fixture/manifest.json')
            fixture['tensors']['l1_x']['address'] += 64
            ci.save(root / 'fixture/manifest.json', fixture)
            with self.assertRaisesRegex(ValueError, 'alias'):
                ci.real2_contract(root)


class VerilatorToolIdentityTest(unittest.TestCase):
    def test_debian_forwarder_and_actual_elf_have_separate_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'usr'
            root = prefix / 'share/verilator'
            entry = root / 'bin/verilator_bin'; entry.parent.mkdir(parents=True)
            entry.write_text('my $relpath = "../../../bin";\nexec { "$RealBin/$relpath/$RealScript" } @ARGV;\n')
            backend = prefix / 'bin/verilator_bin'; backend.parent.mkdir()
            backend.write_bytes(b'\x7fELFtest executable bytes')
            launcher = prefix / 'bin/verilator'; launcher.write_text('launcher')
            with mock.patch.object(ci, 'run_text', return_value='Verilator 5.032') as version:
                forwarder, actual = ci.verilator_backend_identity(launcher, root)
            self.assertEqual(forwarder['kind'], 'DEBIAN_PERL_FORWARDER')
            self.assertEqual(actual['kind'], 'ELF')
            self.assertEqual(actual['path'], str(backend))
            self.assertEqual(actual['sha256'], ci.sha(backend))
            self.assertNotEqual(actual['sha256'], forwarder['sha256'])
            version.assert_any_call([str(backend), '--version'])
            backend.write_bytes(b'#!not an ELF')
            with self.assertRaisesRegex(ValueError, 'not an ELF'):
                ci.verilator_backend_identity(launcher, root)

    def test_unknown_wrapper_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'verilator_bin').write_text('#!/bin/sh\nexec some-other-compiler "$@"\n')
            with self.assertRaisesRegex(ValueError, 'unrecognized'):
                ci.verilator_backend_identity(root / 'verilator', root)


class RunFailureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        helper = self.repo / ci.SCRIPT
        helper.parent.mkdir(parents=True); helper.write_text('test helper')
        self.evidence = self.root / 'evidence'; self.evidence.mkdir()
        (self.evidence / 'obj').mkdir()
        self.binary = self.evidence / 'obj/VHostBlockTop'
        ci.save(self.evidence / ci.MANIFEST, {'test': 'mock lifecycle only'})
        ci.save(self.evidence / 'transfer_receipt.json', {'package_sha256': SHA, 'source_commit': COMMIT,
                'inspection_only': False, 'archive_verified_before_extraction': True,
                'package_manifest_sha256': ci.sha(self.evidence / ci.MANIFEST)})

    def run_mock(self, body, timeout=2, preflight_error=None):
        self.binary.write_text('#!' + sys.executable + '\n' + body + '\n')
        self.binary.chmod(0o755)
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(ci, 'clean_commit', side_effect=preflight_error))
            stack.enter_context(mock.patch.object(ci, 'validate_unpacked', return_value={'packager_source_sha256': ci.sha(self.repo / ci.SCRIPT)}))
            stack.enter_context(mock.patch.object(ci, 'validate_maps'))
            stack.enter_context(mock.patch.object(ci, 'runtime_identity', return_value={'test': True}))
            result = ci.execute(self.repo, self.evidence, self.root, COMMIT, SHA, timeout)
        return result, ci.read_json(self.evidence / 'run_state.json')

    def test_nonzero_child_exit_is_preserved_without_gate_pass(self):
        code, state = self.run_mock('print("PROGRESS pc=17 cycle=123", flush=True)\nraise SystemExit(7)')
        self.assertEqual(code, 1); self.assertEqual(state['simulator_exit'], 7)
        self.assertEqual(state['process_launches'], 1)
        self.assertEqual((self.evidence / 'simulation.exit').read_text(), '7\n')
        self.assertFalse((self.evidence / 'gate.exit').exists())
        self.assertIn('pc=17', state['last_progress'])

    def test_timeout_records_real_signal_exit_and_never_passes(self):
        code, state = self.run_mock('import time\nprint("PROGRESS pc=16", flush=True)\ntime.sleep(10)', timeout=0.1)
        self.assertEqual(code, 1); self.assertTrue(state['timed_out'])
        self.assertEqual(state['simulator_exit'], -signal.SIGTERM)
        self.assertFalse((self.evidence / 'gate.exit').exists())
        self.assertEqual(state['process_launches'], 1)

    def test_preflight_rejection_does_not_launch_binary_or_fabricate_exit(self):
        code, state = self.run_mock('raise SystemExit(0)', preflight_error=ValueError('source changed'))
        self.assertEqual(code, 1); self.assertIsNone(state['simulator_exit'])
        self.assertEqual(state['process_launches'], 0)
        self.assertFalse((self.evidence / 'simulation.exit').exists())
        self.assertFalse((self.evidence / 'gate.exit').exists())

    def test_zero_binary_exit_still_requires_original_verifiers(self):
        code, state = self.run_mock('raise SystemExit(0)')
        self.assertEqual(code, 1); self.assertEqual(state['simulator_exit'], 0)
        self.assertIn('original verifier failed', state['error'])
        self.assertFalse((self.evidence / 'gate.exit').exists())

    def test_interruption_summary_never_infers_success_from_partial_outputs(self):
        ci.save(self.evidence / 'run_state.json', {'status': 'RUNNING_CONTINUOUS_42_COMMANDS', 'simulator_exit': None})
        (self.evidence / 'run.log').write_text('PROGRESS pc=17 cycle=5831053\n')
        (self.evidence / 'tensors').mkdir()
        (self.evidence / 'tensors/output.f32le').write_bytes(b'raw')
        (self.evidence / 'all_owner_elements.csv.gz').write_bytes(b'raw')
        output = self.root / 'summary'
        result = ci.summarize(self.evidence, output)
        self.assertFalse(result['numerical_pass'])
        self.assertEqual({p.name for p in output.iterdir()}, {'SUMMARY.json'})
        summary = ci.read_json(output / 'SUMMARY.json')
        self.assertIsNone(summary['simulator_exit'])
        self.assertIn('pc=17', summary['last_progress'])
        self.assertIn('run.log', summary['log_hashes'])

    def completed_receipts(self):
        accepted = {'status': ci.PASS, 'source_commit': COMMIT, 'commands': 42,
                    'descriptor_records': 430, 'checked_fp32': 1409024, 'bit_differences': 0}
        ci.save(self.evidence / 'REAL2_ACCEPTANCE.json', accepted)
        state = {'status': ci.PASS, 'source_commit': COMMIT, 'simulator_exit': 0,
                 'timed_out': False, 'signal': None, 'process_launches': 1,
                 'acceptance_sha256': ci.sha(self.evidence / 'REAL2_ACCEPTANCE.json'),
                 'verifier_exits': {'production_source_identity.py': 0,
                                   'verify_host_block_gate.py': 0, 'verify_real_two_layer.py': 0}}
        ci.save(self.evidence / 'run_state.json', state)
        for name in ['simulation.exit', 'gate.exit']:
            (self.evidence / name).write_text('0\n')
        return state, accepted

    def test_summary_requires_true_exit_and_intact_original_acceptance(self):
        mutations = ['missing_simulation_exit', 'nonzero_simulation_exit', 'missing_gate_exit',
                     'nonzero_gate_exit', 'missing_acceptance', 'bad_acceptance_status',
                     'wrong_commit', 'incomplete_coverage', 'changed_acceptance',
                     'timed_out', 'signal', 'repeated_process', 'failed_verifier']
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                state, accepted = self.completed_receipts()
                if mutation == 'missing_simulation_exit': (self.evidence / 'simulation.exit').unlink()
                elif mutation == 'nonzero_simulation_exit': (self.evidence / 'simulation.exit').write_text('7\n')
                elif mutation == 'missing_gate_exit': (self.evidence / 'gate.exit').unlink()
                elif mutation == 'nonzero_gate_exit': (self.evidence / 'gate.exit').write_text('1\n')
                elif mutation == 'missing_acceptance': (self.evidence / 'REAL2_ACCEPTANCE.json').unlink()
                elif mutation in ['bad_acceptance_status', 'wrong_commit', 'incomplete_coverage', 'changed_acceptance']:
                    if mutation == 'bad_acceptance_status': accepted['status'] = 'PENDING'
                    elif mutation == 'wrong_commit': accepted['source_commit'] = 'd' * 40
                    elif mutation == 'incomplete_coverage': accepted['checked_fp32'] = 1
                    else: accepted['extra'] = 'changed after verification'
                    ci.save(self.evidence / 'REAL2_ACCEPTANCE.json', accepted)
                    if mutation != 'changed_acceptance':
                        state['acceptance_sha256'] = ci.sha(self.evidence / 'REAL2_ACCEPTANCE.json')
                elif mutation == 'timed_out': state['timed_out'] = True
                elif mutation == 'signal': state['signal'] = signal.SIGTERM
                elif mutation == 'repeated_process': state['process_launches'] = 2
                elif mutation == 'failed_verifier': state['verifier_exits']['verify_real_two_layer.py'] = 1
                ci.save(self.evidence / 'run_state.json', state)
                output = self.root / ('summary-' + str(index))
                result = ci.summarize(self.evidence, output)
                self.assertFalse(result['numerical_pass'])
                self.assertNotEqual(result['status'], ci.PASS)
                self.assertFalse((output / 'REAL2_ACCEPTANCE.json').exists())

    def test_summary_accepts_complete_receipts_and_only_copies_compact_artifacts(self):
        self.completed_receipts()
        output = self.root / 'summary'
        result = ci.summarize(self.evidence, output)
        self.assertTrue(result['numerical_pass'])
        self.assertEqual({p.name for p in output.iterdir()}, {'SUMMARY.json', 'REAL2_ACCEPTANCE.json'})

    def test_successful_build_summary_is_explicitly_not_numerical(self):
        (self.evidence / 'build.exit').write_text('0\n')
        ci.save(self.evidence / 'build_receipt.json', {'status': ci.BUILT})
        (self.evidence / 'build.log').write_text('x' * 10000 + 'BUILD FINISHED\n')
        output = self.root / 'summary'
        result = ci.summarize(self.evidence, output)
        self.assertEqual(result['status'], ci.BUILT)
        self.assertFalse(result['numerical_pass'])
        summary = ci.read_json(output / 'SUMMARY.json')
        self.assertIsNone(summary['simulator_exit'])
        self.assertEqual(len(summary['log_tails']['build.log']), 4096)
        self.assertTrue(summary['log_tails']['build.log'].endswith('BUILD FINISHED\n'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
