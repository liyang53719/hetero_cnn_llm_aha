"""Two real -I -S -B CLI denial paths using only synthetic metadata.

No actual/reference artifact, model/native import, network, child process,
signal, or result-file write is permitted. The audit hook exists only in this
isolated smoke process, never in the unittest discovery interpreter.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import stat
import sys
import tempfile
import types

HERE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert str(HERE) not in sys.path, 'smoke must start without the package on sys.path'
workspace = Path(tempfile.mkdtemp(prefix='synthetic_isolated_cold_handoff_'))
missing = workspace / 'MISSING_HANDOFF.json'
unreviewed = workspace / 'UNREVIEWED_HANDOFF.json'
unreviewed.write_bytes(b'{}\n')
output = workspace / 'MUST_NOT_EXIST.json'
code_sha = hashlib.sha256((HERE / 'CODE_PINS.json').read_bytes()).hexdigest()
configs = []
for case, handoff in (('missing', missing), ('unreviewed', unreviewed)):
    data = dict(schema=1, scope='REVIEWED_POST_TERMINAL_COLD128_CONFIGURATION',
        source_commit='1'*40, full_driver_sha256='5'*64,
        paths=dict(repository='source', harness='evidence', run_directory='evidence/run',
                   fixture='fixture', numpy_site='python_site'),
        files={key: dict(path=path, bytes=1, sha256='2'*64) for key, path in (
            ('plan', 'evidence/PLAN.json'), ('reference_freeze', 'evidence/REFERENCE_FREEZE.json'),
            ('native_manifest', 'reference/native/manifest.json'))},
        terminal=dict(retained_exec_session=7, executor_exit_code=1,
            owner_identity=dict(pid=5, ppid=2, group=5, start=123, session=5),
            boot_id='a015bb85-7341-467e-9d31-616e413f7d75', work_start_monotonic=100.))
    data['files']['terminal_manifest'] = dict(path=handoff.name, bytes=3, sha256='0'*64)
    config = workspace / (case + '_config.json')
    config.write_text(json.dumps(data))
    configs.append((case, handoff, config, hashlib.sha256(config.read_bytes()).hexdigest()))
initial_path = list(sys.path)
stdlib = Path(os.__file__).resolve().parent
allowed = {HERE / name for name in ('cold_postterminal.py', 'launch_cold.py', 'terminal_gate.py', 'CODE_PINS.json')}
allowed.update((missing, unreviewed, *(row[2] for row in configs)))
executed = []


def audit(event, args):
    if event == 'import' and args[0].split('.')[0] in ('numpy', 'torch', 'transformers', 'candidates', 'heteronpu'):
        raise AssertionError('isolated smoke forbids model/native imports')
    if event.startswith(('subprocess.', 'socket.')) or event in ('os.system', 'os.kill', 'os.killpg',
            'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn', 'os.posix_spawnp', 'ctypes.dlopen'):
        raise AssertionError('isolated smoke forbids process/network/native actions')
    if event == 'exec':
        executed.append(args[0].co_filename)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = Path(os.fsdecode(args[0])).absolute()
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise AssertionError('isolated smoke forbids file output creation')
        if name not in allowed and not (name.is_relative_to(stdlib) and name.suffix in ('.py', '.pyc')):
            raise AssertionError('isolated smoke forbids unlisted artifact access: ' + str(name))


sys.addaudithook(audit)
try:
    for case, handoff, config, config_sha in configs:
        sys.path[:] = initial_path
        executed.clear()
        sys.argv = [str(HERE / 'cold_postterminal.py'), '--config', str(config),
                    '--reviewed-config-sha256', config_sha, '--reviewed-code-pins-sha256', code_sha,
                    '--terminal-manifest', str(handoff), '--reviewed-terminal-sha256', '0' * 64,
                    '--output', str(output)]
        try:
            runpy.run_path(str(HERE / 'cold_postterminal.py'), run_name='__main__')
        except FileNotFoundError as error:
            assert case == 'missing' and Path(error.filename) == missing, str(error)
        except ValueError as error:
            assert case == 'unreviewed' and str(error) == 'terminal gate: receipt hash', str(error)
        else:
            raise AssertionError('unadmitted handoff unexpectedly returned')
        assert str(HERE / 'terminal_gate.py') in executed, 'genuine pinned local gate must execute'
        assert sys.path == initial_path, 'isolated bootstrap must not mutate import search paths'
        assert not output.exists(), 'unadmitted handoff must not create output'
    print(json.dumps(dict(status='PASS', isolated=True, synthetic_cases=2,
                          actual_access=False, model_native_execution=False, output_created=False)))
finally:
    unreviewed.unlink()
    for _, _, config, _ in configs:
        config.unlink()
    workspace.rmdir()
