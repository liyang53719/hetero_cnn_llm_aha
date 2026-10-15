"""Cold tests only: synthetic metadata and mocked acquisition/transforms."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from candidates.qwen2_fullblock_ci_execution import inputs as m


class InputsTests(unittest.TestCase):
    def test_default_has_no_io_or_execution(self):
        output = io.StringIO()
        with patch('io.open', side_effect=AssertionError('filesystem I/O')), \
             patch.object(m, 'contracts', side_effect=AssertionError('contract load')), \
             patch.object(m, 'prepare', side_effect=AssertionError('execution')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(m.main([]), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'NOT_EXECUTED')

    def test_two_optins_required_before_io(self):
        for execute, download in ((False, False), (True, False), (False, True), (1, True), (True, 1)):
            with self.subTest(execute=execute, download=download), \
                 patch.object(m, 'preflight', side_effect=AssertionError('filesystem touched')), \
                 self.assertRaisesRegex(ValueError, 'both'):
                m.prepare(execute=execute, download=download)

    def test_partial_cli_optin_rejected(self):
        for flags in (['--execute'], ['--download']):
            with contextlib.redirect_stderr(io.StringIO()), patch.object(m, 'preflight') as preflight:
                self.assertEqual(m.main(flags), 2)
                preflight.assert_not_called()

    def test_sources_and_contracts_are_real_source_only(self):
        original = io.open
        def guarded(path, *args, **kwargs):
            text = str(path)
            if '/work/' in text or (text.endswith(('.bin', '.so', '.npz', '.f32le')) and not text.endswith('.header.bin')):
                raise AssertionError('payload/native read: ' + text)
            return original(path, *args, **kwargs)
        with patch('io.open', side_effect=guarded):
            q, pins, tail, a, n, tp = m.contracts(m.ROOT)
        self.assertEqual(len(pins['tensors']), 8)
        self.assertEqual(len(pins['roles']), 9)
        self.assertEqual(sum(len(t['segments']) for t in tp['tensors']), 14)
        self.assertEqual(len(tp['roles']), 5)
        self.assertNotIn('capture', q)
        self.assertIn('materialize', tail)

    def test_source_hash_drift(self):
        with patch.object(Path, 'read_bytes', return_value=b'changed source'), \
             self.assertRaisesRegex(ValueError, 'source drift'):
            m.source_check(m.ROOT)

    def test_wrong_workspace_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fixed isolated'):
            m.preflight(Path('/arbitrary/workspace'))

    def test_all_outputs_absent_and_disjoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.git').mkdir()
            with patch.object(m, 'ROOT', root), patch.object(m, 'CI_ROOT', root):
                self.assertEqual(m.preflight(root), root)
                for key in m.PATHS:
                    target = root / m.PATHS[key]
                    target.mkdir(parents=True)
                    with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'must be absent'):
                        m.preflight(root)
                    target.rmdir()
                paths = dict(m.PATHS)
                paths['tail_inputs'] = paths['qkv_raw'] + '/nested'
                with patch.object(m, 'PATHS', paths), self.assertRaisesRegex(ValueError, 'overlapping'):
                    m.preflight(root)

    def test_symlink_and_path_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'alias').symlink_to(root, target_is_directory=True)
            for path in ('/absolute', '../outside', './dot', 'x//y', 'x/../y', 'x\\y', 'alias/file'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    m.safe_path(root, path)

    def mocked_contracts(self):
        q = {name: Mock(name=name) for name in ('acquire', 'materialize', 'read_subset', 'read_inputs')}
        q['read_subset'].return_value = ({'acquisition': 'fresh_HTTP206'}, {}, 'a' * 64, Path('/unused'))
        q['read_inputs'].return_value = ({}, 'a' * 64, Path('/unused'))
        tail = {name: Mock(name=name) for name in ('materialize', 'input_metadata')}
        a = SimpleNamespace(acquire=Mock(return_value={'manifest_sha256': 'a' * 64}))
        return q, {}, tail, a, {}, {}

    def test_mocked_end_to_end_calls_only_fixed_acquisition_and_transform(self):
        contracts = self.mocked_contracts()
        record = {'bytes': 10, 'sha256': 'a' * 64}
        with patch.object(m, 'preflight', return_value=m.ROOT), \
             patch.object(m, 'contracts', return_value=contracts), \
             patch.object(m, 'identity', return_value=record), \
             patch.object(m, 'source_check') as sources:
            result = m.prepare(execute=True, download=True)
        q, pins, tail, a, n, tp = contracts
        q['acquire'].assert_called_once_with(m.ROOT, pins, m.ROOT / m.PATHS['qkv_raw'], download=True)
        q['materialize'].assert_called_once_with(m.ROOT, pins, m.PATHS['qkv_raw'], m.ROOT / m.PATHS['qkv_inputs'])
        a.acquire.assert_called_once_with(m.ROOT, m.PATHS['tail_raw'], n, tp)
        tail['materialize'].assert_called_once_with(m.ROOT, m.PATHS['tail_raw'], m.PATHS['tail_inputs'], 'a' * 64)
        tail['input_metadata'].assert_called_once_with(m.ROOT, m.PATHS['tail_inputs'], 'a' * 64, 'a' * 64)
        sources.assert_called_once_with(m.ROOT)
        self.assertEqual(result['status'], 'FRESH_CI_INPUTS_READY')
        self.assertEqual(set(result['metadata']), set(m.PATHS))
        self.assertFalse(result['model_executed'])
        self.assertFalse(result['reference_executed'])
        for record in result['metadata'].values():
            self.assertEqual(set(record), {'bytes', 'sha256'})

    def test_reused_qkv_rejected_before_tail(self):
        contracts = self.mocked_contracts()
        contracts[0]['read_subset'].return_value = ({'acquisition': 'verified_frozen_copy'}, {}, 'a' * 64, None)
        with patch.object(m, 'preflight', return_value=m.ROOT), \
             patch.object(m, 'contracts', return_value=contracts), \
             self.assertRaisesRegex(ValueError, 'entirely fresh'):
            m.prepare(execute=True, download=True)
        contracts[3].acquire.assert_not_called()

    def test_preflight_failure_never_acquires(self):
        with patch.object(m, 'contracts') as contracts, \
             self.assertRaisesRegex(ValueError, 'fixed isolated'):
            m.prepare(Path('/wrong'), execute=True, download=True)
        contracts.assert_not_called()

    def test_tail_seal_mismatch_never_materializes(self):
        contracts = self.mocked_contracts()
        with patch.object(m, 'preflight', return_value=m.ROOT), \
             patch.object(m, 'contracts', return_value=contracts), \
             patch.object(m, 'identity', return_value={'bytes': 10, 'sha256': 'b' * 64}), \
             self.assertRaisesRegex(ValueError, 'seal drift'):
            m.prepare(execute=True, download=True)
        contracts[2]['materialize'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
