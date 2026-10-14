"""Source-bound isolated O cost admission. No numeric acceptance or oracle gate.

Only the two exact archived operands are inputs. Frozen source/metadata is
provenance; no reference tensor can be opened, at any stage. This Python audit
hook is a source-pinned experiment guard, not a hostile-code OS sandbox.
"""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pathlib
import re
import sys
import sysconfig
import types

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / 'work/qwen2_dense_o_cost_m128_20261014'
SCOPE = 'ISOLATED_COST_REPLAY_NOT_SAME_CHAIN'
FULLCHAIN_MANIFEST = 'c9a30a111e5f7eee72d180fcbd5c8b6f4834ad960c9495575fba5660dffbace6'
FULLCHAIN_FREEZE = 'candidates/qwen2_live_fullblock_model_m128/FREEZE.json'
FULLCHAIN_FREEZE_SHA256 = '29261e2da470c76a414a4e35c84b3d079aa128fbb7dc3d319b0fc5b8a507562d'
DRIVER = 'candidates/qwen2_resident_matrix/ffn_fullgroup/down_driver.py'
DRIVER_MODULE = 'public_ffn_original_down'
DRIVER_SHA256 = 'f836f751dacd1182c027e1e02260308bb4609fc02c5624685caafaebe0efcd50'
PATHLIB_SHA256 = '10ba48ae8063cfe7589436041d0d4628c05f427c7709cf8e75e486f8930cc32c'
INPUTS = {
    'att': dict(path='work/qwen2_live_attention_numeric_m128_bounded_20261014/m128_pv32_bounded_actual_v2/att.f32le',
                bytes=786432, sha256='d8e888f201396a6125a93c0602aaf3e53bf4700d4298db0795aa8a1355149287'),
    'wo': dict(path='work/qwen2_live_tail_inputs_m128/reconstruct01/inputs/wo.bin',
               bytes=4718592, sha256='69532da7bcc69b44b0bb627a4c0142f83b6713833d8ec08d6f73926eae80722c'),
}
NATIVE_ARTIFACT = {
    'library': dict(path='work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/build/official_bf16_matrix_silu.so',
                    sha256='a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa'),
    'receipt': dict(path='work/qwen2_live_attention_numeric_m128_20261014/m128_pv32_actual_v1/build/official_bf16_compile.json',
                    sha256='2d3415f027e7703c5e353de3db5c77f8cad0fe3ebbd598d5b5812343d0c10d62'),
}
LIMITS = dict(work_wall_seconds=60, outer_wall_seconds=70, rss_bytes=2147483648,
              output_bytes=2097152, log_bytes=262144, file_bytes=1048576,
              poll_seconds=0.1, threads=1, automatic_retry=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for raw in iter(lambda: stream.read(1 << 20), b''):
            digest.update(raw)
    return digest.hexdigest()


def manifest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON value: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def pins():
    return _parse((HERE / 'pins.json').read_bytes())


def _canonical(path):
    path = Path(path).absolute()
    require(path.resolve() == path, 'aliased path refused: ' + str(path))
    require(not any(part.is_symlink() for part in (path, *path.parents)),
            'symlink path refused: ' + str(path))
    return path


def _sha_spec(path, expected):
    path = _canonical(path)
    require(path.is_file(), 'missing pinned file: ' + str(path))
    actual = dict(bytes=path.stat().st_size, sha256=sha(path))
    require(actual['sha256'] == expected['sha256'] and
            ('bytes' not in expected or actual['bytes'] == expected['bytes']),
            'pinned file identity drift: ' + str(path))
    return actual


def verify_dependencies():
    p = pins()
    require(type(p.get('schema')) is int and p['schema'] == 1 and p.get('scope') == SCOPE and
            p.get('stage') == 'DENSE_O_M128' and
            p.get('actual_execution_authorized') is False and
            p.get('numerical_acceptance') is False, 'isolated cost-only admission scope')
    require(p.get('fullchain_source_manifest') == FULLCHAIN_MANIFEST,
            'frozen fullchain source manifest required')
    require(p.get('inputs') == INPUTS and p.get('native_artifact') == NATIVE_ARTIFACT,
            'exact saved att, readonly wo, and original native artifacts required')
    require(all(type(p['inputs'][name]['bytes']) is int for name in INPUTS), 'exact integer input lengths required')
    _sha_spec(ROOT / FULLCHAIN_FREEZE, {'sha256': FULLCHAIN_FREEZE_SHA256})
    frozen = _parse((ROOT / FULLCHAIN_FREEZE).read_bytes())
    closure = frozen.get('source_sha256')
    require(type(closure) is dict and len(closure) == 266 and manifest(closure) == FULLCHAIN_MANIFEST,
            'frozen266 fullchain closure required')
    expected = dict(closure, **{FULLCHAIN_FREEZE: FULLCHAIN_FREEZE_SHA256})
    require(p.get('dependency_sha256') == expected, 'unchanged frozen266 plus freeze dependency closure required')
    for name, digest in expected.items():
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts and
                type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'invalid source pin')
        _sha_spec(ROOT / name, {'sha256': digest})
    runtime = p.get('runtime_read_sha256')
    require(type(runtime) is dict and bool(runtime), 'runtime code provenance required')
    inherited = _parse((ROOT / 'candidates/qwen2_live_fullblock_model_m128/pins.json').read_bytes())
    require(runtime == inherited['runtime_read_sha256'], 'unchanged pinned runtime read closure required')
    for name, digest in runtime.items():
        _sha_spec(Path(name) if Path(name).is_absolute() else ROOT / name, {'sha256': digest})
    return p


def sources():
    result = dict(verify_dependencies()['dependency_sha256'])
    for path in HERE.iterdir():
        if path.is_file() and (path.suffix in ('.py', '.md') or path.name == 'pins.json'):
            result[str(path.relative_to(ROOT))] = sha(_canonical(path))
    return result


def require_review(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
            'one-use parent go and independently reviewed exact source manifest required')
    current = sources()
    require(manifest(current) == value, 'reviewed isolated O source manifest drift')
    return current


def fresh_output(out):
    out = _canonical(out)
    require(_canonical(OUTPUT_ROOT) == OUTPUT_ROOT and out.parent == OUTPUT_ROOT and
            re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', out.name),
            'output must be a fresh direct child of isolated O cost work directory')
    require(not out.exists(), 'single-use output already exists')
    return out


def input_identity():
    verify_dependencies()
    return {name: _sha_spec(ROOT / spec['path'], spec) for name, spec in INPUTS.items()}


def load_inputs():
    p = verify_dependencies()
    result = {}
    for name, spec in p['inputs'].items():
        path = _canonical(ROOT / spec['path'])
        require(path.is_file() and path.stat().st_size == spec['bytes'], 'input length drift: ' + name)
        raw = path.read_bytes()
        require(len(raw) == spec['bytes'] and hashlib.sha256(raw).hexdigest() == spec['sha256'],
                'input hash drift: ' + name)
        result[name] = raw
    return result


def _code_in(code, name):
    found = [value for value in code.co_consts if isinstance(value, types.CodeType) and value.co_name == name]
    require(len(found) == 1, 'ambiguous pinned code: ' + name)
    return found[0]


class OracleGate:
    """Always-closed numerical oracle gate; narrow code/data/write admission."""
    def __init__(self, out):
        self.out = _canonical(out)
        require(self.out.parent == OUTPUT_ROOT, 'isolated O output namespace required')
        p = verify_dependencies()
        self.input_paths = {ROOT / s['path'] for s in INPUTS.values()}
        self.artifacts = {name: ROOT / s['path'] for name, s in NATIVE_ARTIFACT.items()}
        self.metadata_paths = {ROOT / name for name in p['dependency_sha256']}
        self.metadata_paths |= {path for path in HERE.iterdir() if path.is_file() and
                                (path.suffix in ('.py', '.md') or path.name == 'pins.json')}
        self.runtime_paths = {Path(n) if Path(n).is_absolute() else ROOT / n for n in p['runtime_read_sha256']}
        self.stdlib = Path(sysconfig.get_path('stdlib')).resolve()
        self.disposal = self.out / 'actual_dense.f32le'
        self.driver_path = ROOT / DRIVER
        require(sha(self.driver_path) == DRIVER_SHA256, 'original Dense driver source drift')
        self.expected_driver = _code_in(compile(self.driver_path.read_text(), str(self.driver_path),
            'exec', dont_inherit=True, optimize=sys.flags.optimize), '_execute_dense')
        self.pathlib_path = Path(pathlib.__file__).resolve()
        require(sha(self.pathlib_path) == PATHLIB_SHA256, 'pathlib source drift')
        path_code = _code_in(compile(self.pathlib_path.read_text(), str(self.pathlib_path),
            'exec', dont_inherit=True, optimize=sys.flags.optimize), 'Path')
        self.expected_pathlib = {name: _code_in(path_code, name) for name in ('open', 'write_bytes')}
        self.input_reads, self.artifact_reads, self.source_cache_bypasses, self.disposal_writes = [], [], [], []
        self.disposal_events = self.disposal_writes
        self.reference_reads = []
        self.blocked = 0
        self.opened = False

    def _deny(self, path):
        self.blocked += 1
        raise ValueError('unapproved payload, oracle, historical artifact or write: ' + str(path))

    def _readonly(self, mode, flags):
        require((mode is None or isinstance(mode, str) and all(c not in mode for c in 'wa+x')) and
                type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC) == 0,
                'pinned inputs, source, metadata and native artifacts must remain read-only')

    def _output_path(self, path):
        """Metadata/capped transport only. Never permit a second tensor output."""
        path = _canonical(path)
        if path.parent != self.out or path == self.disposal:
            self._deny(path)
        if path.name in ('down_seed_records_prefix.bin', 'down_prefix_transactions_prefix.jsonl'):
            return path
        if path.suffix in ('.json', '.jsonl', '.log') or (
                path.suffix == '.tmp' and Path(path.stem).suffix in ('.json', '.jsonl', '.log')):
            return path
        self._deny(path)

    def _disposal_frames(self, frame):
        for name in ('open', 'write_bytes'):
            require(frame is not None and frame.f_globals is pathlib.__dict__ and
                    frame.f_code is getattr(Path, name).__code__ and
                    frame.f_code == self.expected_pathlib[name] and
                    frame.f_locals.get('self') == self.disposal,
                    'disposal requires original Path.write_bytes call chain')
            frame = frame.f_back
        module = sys.modules.get(DRIVER_MODULE)
        require(module is not None and frame is not None and Path(module.__file__).resolve() == self.driver_path and
                frame.f_globals is module.__dict__ and
                frame.f_code is module._execute_dense.__code__ and frame.f_code == self.expected_driver and
                frame.f_locals.get('out') == self.out and
                frame.f_locals.get('output_path') == 'actual_dense.f32le' and
                frame.f_locals.get('legacy_down') is False,
                'disposal requires exact original Dense driver code frame')
        raw = frame.f_locals.get('raw')
        require(type(raw) is bytes and len(raw) == 786432, 'disposal requires complete M128 O bytes')
        require(sha(self.driver_path) == DRIVER_SHA256 and sha(self.pathlib_path) == PATHLIB_SHA256,
                'disposal source identity drift')

    def _dispose(self, mode, flags, frame):
        require(mode in ('w', 'wb') and type(flags) is int and
                flags & ~getattr(os, 'O_CLOEXEC', 0) == os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                'tensor disposal is exact write-only Path.write_bytes')
        require(self.disposal.is_symlink() and os.readlink(self.disposal) == '/dev/null' and
                self.disposal.resolve() == Path('/dev/null') and
                _canonical(self.disposal.parent) == self.out,
                'tensor disposal must remain the exact precreated /dev/null symlink')
        require(not self.disposal_writes, 'tensor disposal write is single-use')
        self._disposal_frames(frame)
        self.disposal_writes.append(dict(path=str(self.disposal), target='/dev/null', bytes=786432,
                                        caller='down_driver._execute_dense -> Path.write_bytes'))

    def audit(self, event, args):
        if event == 'import' and args[0].split('.')[0] in ('torch', 'transformers'):
            self._deny(args[0])
        if event == 'ctypes.dlopen':
            require(isinstance(args[0], (str, bytes)), 'current-process/unapproved native handle forbidden')
            path = _canonical(os.fsdecode(args[0]))
            require(path == self.artifacts['library'], 'only original pinned Matrix ELF may be loaded')
            self.artifact_reads.append(dict(event=event, path=str(path)))
            return
        if event in ('ctypes.dlsym', 'ctypes.dlsym/handle'):
            name = getattr(args[0], '_name', None)
            require(isinstance(name, (str, bytes)) and _canonical(os.fsdecode(name)) == self.artifacts['library'],
                    'symbols only from original pinned Matrix ELF; no current-process FENV')
            return
        if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork', 'os.forkpty'):
            self._deny(event)
        if event in ('os.symlink', 'os.link', 'os.chmod', 'os.chown', 'os.utime', 'os.truncate'):
            self._deny(event)
        if event == 'os.remove' and isinstance(args[0], (str, bytes)) and Path(os.fsdecode(args[0])).absolute() == self.disposal:
            require(len(args) < 2 or args[1] in (None, -1), 'fd-relative disposal removal forbidden')
            require(self.disposal.is_symlink() and os.readlink(self.disposal) == '/dev/null' and
                    self.disposal.resolve() == Path('/dev/null') and _canonical(self.disposal.parent) == self.out,
                    'disposal removal requires exact precreated /dev/null symlink')
            return
        if event in ('os.rename', 'os.remove', 'os.rmdir', 'os.mkdir'):
            names = args[:2] if event == 'os.rename' else args[:1]
            for name in names:
                require(isinstance(name, (str, bytes)), 'fd-relative output mutation forbidden')
                self._output_path(os.fsdecode(name))
            if event == 'os.rename':
                require(all(fd in (None, -1) for fd in args[2:]), 'fd-relative rename forbidden')
            elif event in ('os.remove', 'os.rmdir'):
                require(len(args) < 2 or args[1] in (None, -1), 'fd-relative removal forbidden')
            elif event == 'os.mkdir':
                require(len(args) < 3 or args[2] in (None, -1), 'fd-relative mkdir forbidden')
            return
        if event != 'open':
            return
        require(isinstance(args[0], (str, bytes)), 'unapproved raw file descriptor open')
        raw = os.fsdecode(args[0])
        lexical = Path(raw).absolute()
        mode, flags = args[1], args[2]
        if lexical == self.disposal:
            return self._dispose(mode, flags, sys._getframe(1))
        path = _canonical(lexical)
        if path.is_relative_to(self.out):
            return self._output_path(path)
        self._readonly(mode, flags)
        if path in self.input_paths:
            self.input_reads.append(str(path.relative_to(ROOT)))
            return
        if path in self.artifacts.values():
            self.artifact_reads.append(dict(event=event, path=str(path)))
            return
        if path in self.metadata_paths or path in self.runtime_paths:
            return
        if path.suffix == '.pyc':
            try:
                source = _canonical(importlib.util.source_from_cache(str(path)))
            except (ValueError, NotImplementedError):
                source = None
            if source in self.metadata_paths or source is not None and self._stdlib_source(source):
                self.source_cache_bypasses.append(str(path))
                raise FileNotFoundError(errno.ENOENT, 'use source instead of unreviewed bytecode cache', str(path))
        if self._stdlib_source(path):
            return
        if str(path) in ('/proc/self/stat', '/proc/self/statm', '/proc/self/status'):
            return
        self._deny(path)

    def _stdlib_source(self, path):
        return path.suffix == '.py' and path.is_relative_to(self.stdlib) and not any(
            name in ('site-packages', 'dist-packages') for name in path.relative_to(self.stdlib).parts)
