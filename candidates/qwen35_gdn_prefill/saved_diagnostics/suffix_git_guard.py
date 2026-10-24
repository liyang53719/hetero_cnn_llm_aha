"""Exact read-only Git source-identity allowance, adapted from the retained slice runner.

No source-identity function or numerical implementation is replaced. Git keeps
the original subprocess.run timeout, captured stdout, and inherited owned group.
All other subprocesses stay denied. This is not a native-code security sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import time

from suffix_case import case


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SourceGitGuard:
    def __init__(self, plan, environment, log):
        self.root = Path(plan['repository'])
        self.environment = dict(environment)
        self.pins = plan['git_source_identity']['execution_pins']
        self.log = Path(log)
        self.expected = case(plan['case'])['git_calls']
        self.counts = {name: 0 for name in self.expected}
        self.calls = []
        if plan['git_source_identity']['expected_calls'] != self.expected:
            raise ValueError('fixed successful suffix source-identity call contract')

    def audit(self, event, arguments):
        if event != 'subprocess.Popen':
            return
        executable, argv, cwd, env = arguments
        valid = (executable == 'git' and type(argv) is list and len(argv) == 3 and
                 argv[:2] == ['git', 'show'] and type(argv[2]) is str and
                 argv[2].startswith('HEAD:') and cwd is not None and
                 os.fspath(cwd) == str(self.root) and Path(cwd).resolve() == self.root and env is None)
        name = argv[2][5:] if valid else None
        if not valid or name not in self.expected or self.counts[name] >= self.expected[name]:
            raise RuntimeError('only bounded exact owner source-identity Git shows permitted')
        if dict(os.environ) != self.environment or self.environment.get('PATH') != '/usr/bin:/bin':
            raise RuntimeError('Git must inherit the exact sanitized child environment')
        for filename, expected in self.pins.items():
            if digest(filename) != expected:
                raise RuntimeError('Git executable/config/HEAD identity drift: ' + filename)
        self.counts[name] += 1
        record = dict(ordinal=len(self.calls) + 1, source=name, call_for_source=self.counts[name],
                      argv=list(argv), cwd=str(cwd), inherited_sanitized_environment=True,
                      original_source_timeout_seconds=10, monotonic=time.monotonic())
        self.calls.append(record)
        with self.log.open('a') as stream:
            stream.write(json.dumps(record, sort_keys=True) + '\n')

    def report(self):
        return dict(scope='EXACT_READ_ONLY_SOURCE_IDENTITY_GIT_SHOW_ONLY',
                    observed_calls=self.counts, expected_success_calls=self.expected,
                    total_calls=len(self.calls), expected_success_total=sum(self.expected.values()),
                    complete=self.counts == self.expected, compilation=False, numerical_execution=False)
