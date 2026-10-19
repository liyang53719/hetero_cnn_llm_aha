"""Tiny pure fixtures only. Explicit flags are checked before loading the candidate."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use Python -I -S -B.')
if __name__ == '__main__' and sys.argv[1:] != ['--execute-cold']:
    print('SOURCE_ONLY: pass --execute-cold to run tiny pure fixtures; no native tools or network.')
    raise SystemExit(0)

import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import types

HERE = Path(__file__).resolve().parent
MODULE_PIN = 'f1cb8595247b2c991c77e4fa7404fc1cd618bb28f9e173eb43d7e00a58c49b50'
MODULE_SIZE = 26517
raw = (HERE / 'host_emission.py').read_bytes()
if len(raw) != MODULE_SIZE or hashlib.sha256(raw).hexdigest() != MODULE_PIN:
    raise ValueError('candidate raw bytes differ before compile')
m = types.ModuleType('_tiny_host_emission')
m.__file__ = str(HERE / 'host_emission.py')
exec(compile(raw, m.__file__, 'exec', dont_inherit=True), m.__dict__)


def main():
    passed = []
    def good(name, action):
        action()
        passed.append(name)
    def bad(name, action):
        try:
            action()
        except (ValueError, FileNotFoundError):
            passed.append(name)
        else:
            raise AssertionError('negative unexpectedly accepted: ' + name)

    bad('duplicate JSON keys rejected', lambda: m.unique_json(b'{"a":1,"a":2}'))
    for value in ('../x', '/x', 'a//b', './x', 'a\\b'):
        bad('unsafe relative path ' + repr(value), lambda v=value: m.relative(v))
    good('fixed portable source pin manifest', lambda: m.source_pins())
    with tempfile.TemporaryDirectory(prefix='host93-tiny-') as root:
        root = Path(root)
        path = root / 'tiny'
        path.write_bytes(b'ab')
        pin = m.byte_identity(b'ab')
        good('bounded same file bytes', lambda: m.read_bytes(path, 2, pin))
        bad('wrong input size', lambda: m.read_bytes(path, 2, {'bytes': 1, 'sha256': pin['sha256']}))
        bad('wrong input digest', lambda: m.read_bytes(path, 2, {'bytes': 2, 'sha256': '0'*64}))
        bad('strict input cap', lambda: m.read_bytes(path, 1))
        (root / 'link').symlink_to(path)
        bad('symlink input rejected', lambda: m.read_bytes(root / 'link', 2))
        bad('inventory rejects links', lambda: m.inventory(root, 32, 16))
        (root / 'link').unlink()
        (root / 'empty').mkdir()
        inv = m.inventory(root, 2, 2)
        if not (inv['complete'] and inv['directories'] == ['empty'] and (inv['files'] == {'tiny': pin})): raise AssertionError('explicit tiny condition')
        passed.append('complete files and empty directories')
        bad('inventory aggregate cap', lambda: m.inventory(root, 1, 2))
        bad('inventory entry cap', lambda: m.inventory(root, 2, 2, 1))
        script = root / 'module.py'
        original = b'VALUE = 11\n'
        script.write_bytes(b'VALUE = 99\n')
        loaded = m.load_source(script, original, m.byte_identity(original))
        if not (loaded.VALUE == 11): raise AssertionError('explicit tiny condition')
        passed.append('same checked buffer compiled despite different disk bytes')
        bad('source tamper rejected before compile', lambda: m.load_source(script, original, m.byte_identity(b'VALUE = 12\n')))
        fixture = root / 'acquisition'
        fixture.mkdir()
        (fixture / 'j.jar').write_bytes(b'ab')
        (fixture / 'ACQUISITION.json').write_bytes(b'{}')
        plan = {'artifacts': [{'relative_destination': 'j.jar', 'sha256': pin['sha256'],
                              'known_size_bytes': 2, 'max_transfer_bytes': 3}]}
        good('tiny acquisition actual bytes', lambda: m._acquired(fixture, plan, {'ACQUISITION.json'}, 4))
        (fixture / 'surprise').write_bytes(b'x')
        bad('extra acquisition file fails closed', lambda: m._acquired(fixture, plan, {'ACQUISITION.json'}, 5))
        repo = root / 'repo'
        repo.mkdir()
        (repo / '.git').mkdir()
        called = []
        callback = lambda *args: called.append(args)
        bad('existing work rejected before phase', lambda: m.run(repo, fixture, callback))
        bad('work inside repo rejected before phase', lambda: m.run(repo, repo / 'new', callback))
        if not (called == [] and (not (repo / 'new').exists())): raise AssertionError('explicit tiny condition')
        passed.append('negative run guards invoke no runner')
    receipt = {'record': {'exit_code': 0, 'cleanup_confirmed': True}, 'raw_log': b'ok\n',
               'usage': {'synthetic': True}, 'evidence_root': 'tiny-only'}
    good('original bounded receipt accepted', lambda: m._accept_phase(receipt))
    bad('cleanup unconfirmed', lambda: m._accept_phase({**receipt, 'record': {'exit_code': 0, 'cleanup_confirmed': False}}))
    bad('exit failure', lambda: m._accept_phase({**receipt, 'record': {'exit_code': 1, 'cleanup_confirmed': True}}))
    bad('raw log must be bytes', lambda: m._accept_phase({**receipt, 'raw_log': 'ok'}))
    with tempfile.TemporaryDirectory(prefix='host93-bootstrap-tiny-') as root:
        root = Path(root)
        fixture = root / 'fixture.py'
        marker = root / 'marker'
        good_raw = b"from pathlib import Path\nPath('marker').write_text('ran')\n"
        fixture_pin = m.byte_identity(good_raw)
        for optimized in (False, True):
            label = '-O' if optimized else 'normal'
            for kind in ('good', 'short', 'same_size_bad_sha', 'missing_I', 'missing_S', 'missing_B'):
                marker.unlink(missing_ok=True)
                content = good_raw[:-1] if kind == 'short' else good_raw.replace(b"'ran'", b"'bad'") if kind == 'same_size_bad_sha' else good_raw
                fixture.write_bytes(content)
                flags = ['-I', '-S', '-B']
                if kind.startswith('missing_'):
                    flags.remove('-' + kind[-1])
                if optimized:
                    flags.append('-O')
                child = subprocess.run([sys.executable, *flags, '-c', m.BOOTSTRAP, str(fixture),
                                        str(fixture_pin['bytes']), fixture_pin['sha256']],
                                       cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=5, check=False,
                                       env={'PATH': '/usr/bin:/bin', 'HOME': str(root)})
                if kind == 'good':
                    if child.returncode != 0 or not marker.is_file() or marker.read_text() != 'ran':
                        raise AssertionError('actual bootstrap valid fixture failed: ' + label)
                elif child.returncode == 0 or marker.exists():
                    raise AssertionError('actual bootstrap executed invalid fixture: ' + label + '/' + kind)
                passed.append('actual bootstrap ' + label + '/' + kind)
    for source in (raw, m.BOOTSTRAP):
        if any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(source))):
            raise AssertionError('production entry contains optimization-sensitive assert')
    passed.append('production entry and bootstrap contain no bare assert')
    if not (m.LIMITS['acquire_jar87']['as_bytes'] == 512 * 1024 ** 2): raise AssertionError('explicit tiny condition')
    if not (m.LIMITS['assemble']['cpu_seconds'] == 40): raise AssertionError('explicit tiny condition')
    if not (all((x['work_seconds'] <= x['total_seconds'] - 15 for x in m.LIMITS.values()))): raise AssertionError('explicit tiny condition')
    passed.append('original acquisition and assembly budgets restored')
    if not (m.LIMITS['class']['total_seconds'] == 330 and m.LIMITS['class']['work_seconds'] == 300): raise AssertionError('explicit tiny condition')
    if not (m.LIMITS['chirrtl']['total_seconds'] == 90 and m.LIMITS['chirrtl']['work_seconds'] == 60): raise AssertionError('explicit tiny condition')
    if not (m.LIMITS['sv']['total_seconds'] == 390 and m.LIMITS['sv']['work_seconds'] == 360): raise AssertionError('explicit tiny condition')
    passed.append('fixed compute limits')
    print(json.dumps({'status': 'PASS_TINY_PURE_COLD_ONLY', 'checks': passed, 'check_count': len(passed),
                      'network': False, 'production_assembly': False, 'java': False,
                      'firtool': False, 'new_rtl': False, 'full_block_rtl_passes': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
