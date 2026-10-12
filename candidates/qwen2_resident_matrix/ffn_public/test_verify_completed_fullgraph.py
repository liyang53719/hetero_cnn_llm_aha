"""Postprocessing cannot manufacture an actual terminal or change old evidence."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from candidates.qwen2_resident_matrix.ffn_public import verify_completed_fullgraph as verify


def complete():
    return dict(status='FAILED', error='software recipe timeout; no completion claimed',
                rows=128, prelaunch_intermediate_payloads=[], rtl_executed=False, scala_executed=False,
                native_policy='UNCHANGED_FAIL_POLICY_PENDING', execution=dict(
                    same_owner_and_banks=True, same_physical_memory_and_services=True,
                    host=dict(launch_result=dict(completed=21, jobs=17, status=None),
                              accepted=dict(result_fire=1, completion_fire=21, owner_result_fire=17),
                              reset_required=False,
                              completions=[dict(pc=i, status=None) for i in range(21)])))


class CompletedFullgraphTests(unittest.TestCase):
    def test_only_actual_complete_model_timeout_qualifies(self):
        verify.terminal(complete())

    def test_other_failures_and_partial_or_duplicate_terminal_rejected(self):
        for path, value in [(['status'], 'PASS'), (['error'], 'Numerical'), (['rows'], 16),
                (['prelaunch_intermediate_payloads'], ['n0']), (['rtl_executed'], True),
                (['scala_executed'], True), (['native_policy'], 'ACCEPTED'),
                (['execution','same_owner_and_banks'], False),
                (['execution','same_physical_memory_and_services'], False),
                (['execution','host','launch_result'], None),
                (['execution','host','launch_result','completed'], 20),
                (['execution','host','launch_result','jobs'], 16),
                (['execution','host','launch_result','status'], 3),
                (['execution','host','accepted','result_fire'], 0),
                (['execution','host','accepted','result_fire'], 2),
                (['execution','host','accepted','completion_fire'], 20),
                (['execution','host','accepted','owner_result_fire'], 16),
                (['execution','host','reset_required'], True)]:
            data = complete(); target = data
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                verify.terminal(data)

    def test_completion_identity_and_failure_preserved(self):
        for replacement in [list(reversed(complete()['execution']['host']['completions'])),
                            [dict(pc=i, status=3 if i==20 else None) for i in range(21)]]:
            data = complete(); data['execution']['host']['completions'] = replacement
            with self.assertRaisesRegex(ValueError, 'completion identity'):
                verify.terminal(data)
        data = complete(); before = copy.deepcopy(data); verify.terminal(data)
        self.assertEqual(before, data)
        self.assertEqual(data['status'], 'FAILED')

    def test_exact_bytes_hash_and_length_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary) / 'reference'; raw = b'\0\1\2\3'; p.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
            self.assertEqual(verify.checked(p, sha, 4), raw)
            for h, size in [('0'*64, 4), (sha, 3), (sha, 5)]:
                with self.assertRaisesRegex(ValueError, 'identity drift'):
                    verify.checked(p, h, size)
            p.write_bytes(raw[:-1]+b'\4')
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                verify.checked(p, sha, 4)

    def test_archived_reference_requires_exact_source_input_and_shape(self):
        data = dict(readonly_sha256='arena', input_x_sha256='input', positions=[0, 1])
        oracle = dict(completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE', shape=dict(tokens=128),
                      source_identity=dict(source='sha', binary='elf', flags=['-O2']), input=data)
        summary = dict(binaries=dict(oracle_provenance=copy.deepcopy(oracle['source_identity'])),
                       input_spec=dict(original_input=copy.deepcopy(data)), loaded_inputs=dict(x=dict(sha256='input')))
        verify.oracle_binding(summary, oracle, dict(sha256='arena'))
        for path, value in [(['shape','tokens'], 16), (['source_identity','source'], 'changed'),
                            (['source_identity','binary'], 'other-elf'), (['source_identity','flags'], []),
                            (['input','input_x_sha256'], 'different-input'), (['input','positions'], [1,2]),
                            (['input','readonly_sha256'], 'other-arena'), (['completion_status'], 'PARTIAL')]:
            changed = copy.deepcopy(oracle); target = changed
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                verify.oracle_binding(summary, changed, dict(sha256='arena'))

    def test_changed_actual_or_reference_bytes_fail_without_tolerance(self):
        raw = b'\0\0\0\0'; verify.identical_stage(raw, raw, raw, 1)
        for actual, independent, saved, count in [(b'\1\0\0\0',raw,raw,1),
                (raw,b'\1\0\0\0',raw,1), (raw,raw,b'\1\0\0\0',1),
                (raw,raw,raw,2), (b'',b'',b'',1)]:
            with self.subTest(actual=actual, count=count), self.assertRaises(ValueError):
                verify.identical_stage(actual, independent, saved, count)


if __name__ == '__main__':
    unittest.main()
