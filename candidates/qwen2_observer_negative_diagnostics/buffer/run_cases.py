"""Exactly one execution per declared case; never enlarge budgets or retry."""
from pathlib import Path
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
cases = [('prepare', [], 0)]
for buffer in (0, 65536, 1048576):
    cases.append(('benchmark_' + str(buffer), ['benchmark', '--buffer', str(buffer)], 0))
cases.append(('benchmark_default_off', ['benchmark', '--default-off'], 0))
for case in ('clean_seal', 'abort_close', 'audit_invalid_seal', 'short_write', 'ioerror', 'partial_ioerror', 'byte_capacity', 'event_capacity', 'encode_failure', 'unexpected_exit'):
    for buffer in (0, 65536, 1048576):
        cases.append((case + '_' + str(buffer), ['negative', '--case', case, '--buffer', str(buffer)], 73 if case == 'unexpected_exit' else 0))
records = []
for name, args, expected_exit in cases:
    command = [sys.executable, '-I', '-B', str(root / 'diagnostic.py')] + (args or ['prepare']) + ['--result', name + '.json']
    start = time.perf_counter()
    with (root / (name + '.stdout')).open('x') as stdout, (root / (name + '.stderr')).open('x') as stderr:
        try:
            done = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=45, check=False)
            code = done.returncode
        except subprocess.TimeoutExpired:
            code = 'wall_timeout'
    record = {'case': name, 'command': command, 'exit': code, 'expected_exit': expected_exit,
              'parent_wall_seconds': time.perf_counter() - start, 'passed_exit': code == expected_exit}
    records.append(record)
    print(json.dumps(record), flush=True)
    # A failed case is preserved and never retried. Independent cases continue.
(root / 'RUNS.json').write_text(json.dumps(records, indent=2) + '\n')
sys.exit(0 if all(record['passed_exit'] for record in records) else 1)
