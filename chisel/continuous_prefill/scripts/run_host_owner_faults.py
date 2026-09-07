#!/usr/bin/env python3
"""Run the fixed eight owner fault cases on an already verified tiny16 DUT.

Every case must report its exact error, prior completion count, and lockout.
An ordinary numeric PASS is a failure here. No source or generated RTL changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

CASES = {
    'bad-first-op': (0, 0), 'missing-bias': (2, 2),
    'wrong-softmax': (11, 10), 'wrong-dependency': (1, 1),
    'descriptor-shape': (0, 0), 'read-error': (1, 1),
    'write-error': (1, 1), 'last-write-error': (1, 1),
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def check_log(mode: str, text: str, code: int) -> dict:
    require(mode in CASES, 'unknown fault case')
    require(code == 0, 'fault simulator failed')
    require(not re.search(r'HOST_BLOCK_ALL_OWNERS_PASS|HOST_BLOCK_FAIL|%Error|\bFatal\b', text), 'ordinary PASS or fatal in fault run')
    pc, prior = CASES[mode]
    lines = re.findall(r'^HOST_BLOCK_FAULT_PASS mode=(\S+) pc=(\d+) prior_completions=(\d+) next_owner_not_started=(\d+)\s*$', text, re.M)
    require(lines == [(mode, str(pc), str(prior), '1')], 'missing, duplicated or incorrect fault receipt')
    errors = re.findall(r'^EXPECTED_ERROR pc=(\d+) status=(\d+)\s*$', text, re.M)
    require(len(errors) == 1 and int(errors[0][0]) == pc and int(errors[0][1]) != 0, 'missing nonzero failure status')
    completed = [int(n) for n in re.findall(r'^OWNER_COMPLETION pc=(\d+) ', text, re.M)]
    require(completed == list(range(prior)), 'consumer published after failure or missing prior completion')
    return {'mode': mode, 'failed_pc': pc, 'prior_completions': prior,
            'status': int(errors[0][1]), 'next_owner_not_started': True}


def run(build: Path, out: Path) -> dict:
    require(not out.exists(), 'output must be a new directory')
    fixture = build / 'fixture'
    exe = build / 'obj/VHostBlockTop'
    require(exe.is_file() and os.access(exe, os.X_OK), 'missing executable DUT')
    require((build / 'gate.exit').read_text().strip() == '0', 'baseline gate did not pass')
    require((build / 'simulation.exit').read_text().strip() == '0', 'baseline simulator did not pass')
    manifest = json.loads((fixture / 'manifest.json').read_text())
    require((manifest['shape']['H'], manifest['shape']['F'], manifest['tokens']) == (64, 128, 16), 'fixed fault gate requires tiny16')
    files = [exe, fixture / 'host_commands.bin', fixture / 'host_descriptors.bin',
             fixture / 'manifest.json', build / 'generated/HostBlockTop.sv', build / 'sources.sha256.json']
    before = {str(p.relative_to(build)): digest(p) for p in files}
    out.mkdir(parents=True)
    cases = []
    for mode in CASES:
        directory = out / mode
        directory.mkdir()
        log = directory / 'run.log'
        with log.open('xb') as stream:
            completed = subprocess.run([str(exe), str(fixture), str(directory / 'tensors'), mode],
                                       stdout=stream, stderr=subprocess.STDOUT, timeout=600)
        (directory / 'simulation.exit').write_text(str(completed.returncode) + '\n')
        case = check_log(mode, log.read_text(), completed.returncode)
        case['log_sha256'] = digest(log)
        cases.append(case)
    require(before == {str(p.relative_to(build)): digest(p) for p in files}, 'DUT/fixture changed during fault runs')
    result = {'schema': 1, 'status': 'PASS_EIGHT_ACTUAL_OWNER_FAULT_REJECTIONS',
              'cases': cases, 'inputs_sha256': before, 'reset_recovery_tested': False,
              'scope': 'Actual original Matrix and pinned-iDMA tiny DUT; failure and reset-required lockout, not reset recovery or real-size numerical signoff.'}
    with (out / 'RESULT.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.build.resolve(), args.output.resolve()), indent=2))
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        raise SystemExit('OWNER_FAULT_GATE_FAILED: ' + str(error))
