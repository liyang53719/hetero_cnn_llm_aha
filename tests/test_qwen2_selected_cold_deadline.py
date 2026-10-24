"""Mock-only regression for the selected Qwen2 cold CI aggregate deadline.

No candidate imports, subprocesses, affinity changes or resource-limit changes.
Run from any directory with Python -I -B, optionally -O.
"""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch


WORKFLOW = (Path(__file__).resolve().parents[1] / '.github/workflows' /
            'qwen2-selected-scala-model-cold.yml')
COUNTS = (26, 10, 17, 8, 15) * 2


def workflow_source():
    text = WORKFLOW.read_text(encoding='utf-8')
    start = "          python -I -B - <<'PY'\n"
    end = '          PY\n'
    if text.count(start) != 1:
        raise ValueError('expected one isolated workflow Python block')
    rest = text.split(start, 1)[1]
    if rest.count(end) != 1:
        raise ValueError('expected one workflow Python block terminator')
    return textwrap.dedent(rest.split(end, 1)[0])


def exercise(*, final_child_time=10.0, final_log_time=None):
    output = io.StringIO()
    state = {'now': 0.0, 'calls': 0, 'log_advanced': False}
    commands = []

    def run(command, **kwargs):
        index = state['calls']
        if index >= len(COUNTS):
            raise AssertionError('unexpected extra subprocess request')
        commands.append((command, kwargs))
        state['calls'] += 1
        state['now'] = final_child_time if state['calls'] == 10 else float(state['calls'])
        return SimpleNamespace(returncode=0,
            stdout=f'Ran {COUNTS[index]} tests in 0.001s\n\nOK\n')

    def emit(*args, **kwargs):
        print(*args, **dict(kwargs, file=output))
        if (final_log_time is not None and state['calls'] == 10 and
                args and str(args[0]).startswith('Ran ') and not state['log_advanced']):
            state['now'] = final_log_time
            state['log_advanced'] = True

    error = None
    with ExitStack() as stack:
        stack.enter_context(patch('subprocess.run', side_effect=run))
        stack.enter_context(patch('time.monotonic', side_effect=lambda: state['now']))
        stack.enter_context(patch('os.sched_getaffinity', return_value={3, 7}))
        affinity = stack.enter_context(patch('os.sched_setaffinity'))
        resources = stack.enter_context(patch('resource.setrlimit'))
        try:
            exec(compile(workflow_source(), str(WORKFLOW), 'exec'), {'print': emit})
        except SystemExit as exc:
            error = str(exc)
        affinity.assert_not_called()
        resources.assert_not_called()
    return error, output.getvalue(), commands


class SelectedColdDeadlineTests(unittest.TestCase):
    def check_rejected(self, **kwargs):
        error, output, commands = exercise(**kwargs)
        self.assertEqual(error, 'Cold aggregate exceeded 120-second budget')
        self.assertEqual(len(commands), 10)
        self.assertNotIn('PASS_COLD_TESTS_ONLY', output)
        if kwargs.get('final_child_time', 0) >= 120:
            self.assertNotIn('=== run_existing_numeric_regressions.py; optimized=True; expected=15', output)

    def test_final_child_beyond_aggregate_deadline_rejects(self):
        self.check_rejected(final_child_time=120.01)

    def test_exact_aggregate_deadline_rejects(self):
        self.check_rejected(final_child_time=120.0)

    def test_final_logging_beyond_deadline_rejects(self):
        self.check_rejected(final_child_time=119.0, final_log_time=120.01)

    def test_normal_completion_preserves_both_76_test_totals(self):
        error, output, commands = exercise()
        self.assertIsNone(error)
        self.assertEqual(len(commands), 10)
        result = json.loads(output.splitlines()[-1])
        self.assertEqual(result['status'], 'PASS_COLD_TESTS_ONLY')
        self.assertEqual((result['normal_tests'], result['optimized_tests']), (76, 76))
        for index, (command, kwargs) in enumerate(commands):
            self.assertEqual('-O' in command, index >= 5)
            self.assertEqual(command[1:3], ['-I', '-B'])
            self.assertEqual(kwargs['timeout'], 30)
            self.assertFalse(kwargs['check'])
            self.assertTrue(callable(kwargs['preexec_fn']))
        self.assertFalse(result['native_execution'])
        self.assertFalse(result['scala_execution'])
        self.assertFalse(result['full_m128_acceptance'])
        self.assertFalse(result['rtl_acceptance'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
