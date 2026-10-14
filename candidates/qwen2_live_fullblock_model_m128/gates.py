"""Exact full-launch admission; no historical activation or preseal oracle reads.

The reviewed wrapper loads and hashes the thirteen checkpoint inputs before
installing this audit hook. Once installed, only fourteen readonly producer
roles are operands; raw checkpoint provenance and frozen oracle bytes reopen
only after the fresh public21/17-owner/one-launch-result output seal.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

from candidates.qwen2_live_attention_model_m128_bounded.v2 import gates as v2
from candidates.qwen2_fullblock_reference_m128 import recipe as R

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / 'work/qwen2_live_fullblock_numeric_m128_20261014'
DATA = ROOT / 'work/qwen2_live_qkv_inputs_m128/frozen01'
TAIL_INPUTS = ROOT / 'work/qwen2_live_tail_inputs_m128/reconstruct01/inputs'
REFERENCE = ROOT / 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen'
ROLES = frozenset(('x', 'gamma0', 'wq', 'wk', 'wv', 'bq', 'bk', 'bv', 'rope',
                   'wo', 'gamma1', 'wg', 'wu', 'wd'))
REFERENCES = R.NAMES
REFERENCE_METADATA = ('REFERENCE.json', 'SEAL.json', 'BOUNDARY_BEFORE.json',
                      'BOUNDARY_AFTER.json', 'WRAPPER_BEFORE.json', 'WRAPPER_AFTER.json')
# Exact CPython 3.12 runtime helper used only for fd-relative output cleanup.
SHUTIL_SOURCE_SHA256 = '53496e06742fe008fee2bccc8caeac77473e69923bec05358bd43eea467db1f8'
require, sha, manifest = v2.require, v2.sha, v2.manifest


def pins():
    return R.parse((HERE / 'pins.json').read_bytes())


def _canonical(path):
    path = Path(path).absolute()
    require(path.resolve() == path, 'aliased path refused: ' + str(path))
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'symlink path refused: ' + str(path))
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
    require(p.get('scope') == 'M128_SOFTWARE_PUBLIC21_FULLBLOCK' and
            type(p.get('rows')) is int and p['rows'] == 128 and
            p.get('actual_execution_authorized') is False, 'fullblock admission scope')
    dependency = p.get('dependency_sha256')
    require(type(dependency) is dict and bool(dependency), 'source closure required')
    inherited = v2.sources()
    require(all(dependency.get(name) == digest for name, digest in inherited.items()),
            'unchanged bounded-v2 closure required')
    for name, digest in dependency.items():
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts and
                type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'invalid source pin')
        _sha_spec(ROOT / name, {'sha256': digest})
    require(p.get('fullblock_reference_pins_sha256') == R.PINS_SHA256 and
            p.get('frozen_contract_sha256') == R.FROZEN_CONTRACT_SHA256,
            'reviewed fullblock reference code pins required')
    for key, path in (('data_path', DATA), ('reference_path', REFERENCE)):
        require(p.get(key) == str(path.relative_to(ROOT)), 'fixed ' + key + ' binding')
    for name in REFERENCE_METADATA:
        require(str((REFERENCE / name).relative_to(ROOT)) in dependency,
                'fresh frozen reference metadata must be source-pinned: ' + name)
    for name, digest in p.get('runtime_read_sha256', {}).items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        _sha_spec(path, {'sha256': digest})
    return p


def sources():
    result = dict(verify_dependencies()['dependency_sha256'])
    for path in HERE.iterdir():
        if path.is_file() and (path.suffix in ('.py', '.md') or path.name in ('pins.json', 'BUDGET.json')):
            result[str(path.relative_to(ROOT))] = sha(_canonical(path))
    return result


def require_review(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value),
            'independent parent go and reviewed fullblock source manifest required')
    current = sources()
    require(manifest(current) == value, 'reviewed fullblock source manifest drift')
    return current


def require_budget():
    """No caller/CLI timing override and no inherited pc12 deadline."""
    value = R.parse((HERE / 'BUDGET.json').read_bytes())
    require(value.get('status') == 'REVIEWED_FIXED_WHOLE_BLOCK_BUDGET',
            'fullblock budget unreviewed; representative timing and fixed source budget required')
    for key in ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes',
                'file_bytes', 'log_bytes', 'progress_loop_interval'):
        require(type(value.get(key)) is int and value[key] > 0, 'reviewed positive integer budget: ' + key)
    require(value['outer_wall_seconds'] >= value['inner_wall_seconds'] + 7,
            'outer watchdog must reserve seven seconds beyond the inner deadline')
    require(value.get('automatic_retry') is False, 'automatic retry must remain disabled')
    require(value['progress_loop_interval'] == 131072, 'unchanged Attention progress interval required')
    require(type(value.get('poll_seconds')) in (int, float) and 0 < value['poll_seconds'] <= 1,
            'reviewed bounded poll_seconds required')
    require(value['file_bytes'] <= value['output_bytes'], 'file cap must fit total output cap')
    return value


def data_path(value):
    require(type(value) is str and value == str(DATA.relative_to(ROOT)), 'exact published prefix input directory required')
    require(_canonical(DATA).is_dir(), 'prefix input directory missing')
    return DATA


def reference_path(value):
    require(type(value) is str and value == str(REFERENCE.relative_to(ROOT)),
            'exact fresh frozen fullblock reference directory required')
    require(_canonical(REFERENCE).is_dir(), 'frozen reference directory missing')
    return REFERENCE


def fresh_output(out, data):
    out = _canonical(out)
    require(out.parent == OUTPUT_ROOT and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', out.name),
            'output must be a fresh direct child of fullblock numeric work directory')
    require(not out.exists() and Path(data) == DATA and
            all(not out.is_relative_to(p) and not p.is_relative_to(out) for p in (DATA, TAIL_INPUTS, REFERENCE)),
            'output exists/overlaps inputs or reference')


def reference_recipe():
    p = verify_dependencies()
    rp = R.load_pins(ROOT)
    R.source_check(ROOT, rp)
    frozen = R.require_frozen_references(rp, ROOT)
    require(p['fullblock_reference_pins_sha256'] == R.PINS_SHA256, 'fullblock recipe identity drift')
    return rp, frozen


def require_final_reference():
    rp, frozen = reference_recipe()
    require(set(rp['producer_roles']) == ROLES and len(rp['raw_tensors']) == 13 and
            set(frozen['outputs']) == REFERENCES, 'exact 14-role/13-raw/29-reference contract required')
    validate_reference_metadata(DATA, REFERENCE, recipe=(rp, frozen))
    return pins()


def validate_reference_metadata(data, reference, *, recipe=None):
    """Only code-pinned metadata and file stat; never old runtime rehash or payloads."""
    require(Path(data) == DATA and Path(reference) == REFERENCE, 'fixed input/reference namespaces required')
    rp, frozen = reference_recipe() if recipe is None else recipe
    metadata = {name: R.parse(_canonical(REFERENCE / name).read_bytes()) for name in REFERENCE_METADATA}
    ref, seal = metadata['REFERENCE.json'], metadata['SEAL.json']
    R.fields(seal, dict(schema=1, status='SEALED_FRESH_FROZEN_REPRODUCTION_REFERENCE_ONLY',
        mode='frozen', run_id='fullblock_pair_v2', manifest='REFERENCE.json',
        dut_executed=False, numerical_acceptance_claimed=False, retries=0), 'fresh reference seal')
    R.fields(ref, dict(status='FRESH_OFFICIAL_AST_FULLBLOCK_CAPTURE_ONLY', stage='frozen',
        source_pins_sha256=R.PINS_SHA256, official_ast_subset_executed=True,
        official_model_ast_nodes=38, official_activation_ast_nodes=14,
        frozen29_hash_matches=True, prior18_fresh_hash_matches=True,
        wrapper_boundary_unchanged=True, dut_executed=False, actual_or_typed_input_read=False,
        materialized_producer_payload_read=False, saved_reference_payload_read=False,
        numerical_acceptance_claimed=False, old_pass_inherited=False,
        full_official_forward_executed=False, dynamic_cache_executed=False,
        full_29_node_acceptance=False), 'fresh reference manifest')
    require(R.same(ref['outputs'], frozen['outputs']), 'fresh frozen29 observations differ from reviewed contract')
    R.validate_observations(ref['outputs'], rp)
    source = R.source_manifest(ROOT)
    require(R.same(ref['source_manifest'], source) and R.same(seal['source_manifest'], source),
            'fresh reference source closure drift')
    require(R.same(seal['resources'], ref['resources']), 'reference resource seal differs')
    R.fields(seal['resources'], dict(returncode=0, limit_reason=None), 'successful bounded reference')
    require(not seal['resources']['descendant_cleanup']['remaining_descendants'], 'reference descendants not drained')
    for name in REFERENCE_METADATA:
        if name != 'SEAL.json':
            _sha_spec(REFERENCE / name, seal['files'][name])
    boundaries = [metadata[name] for name in REFERENCE_METADATA if name not in ('REFERENCE.json', 'SEAL.json')]
    require(all(R.same(boundaries[0], b) for b in boundaries[1:]), 'fresh reference boundary drift')
    R.fields(ref['boundary'], dict(unchanged=True,
        before_sha256=seal['files']['BOUNDARY_BEFORE.json']['sha256'],
        after_sha256=seal['files']['BOUNDARY_AFTER.json']['sha256']), 'reference boundary identity')
    require(R.same(boundaries[0]['raw13'], {s['path']: {k:s[k] for k in ('bytes','sha256')}
            for s in rp['raw_tensors']}), 'reference raw13 provenance differs')
    require(R.same(boundaries[0]['pins'], dict(bytes=(R.HERE/'pins.json').stat().st_size, sha256=R.PINS_SHA256)),
            'reference producer geometry pins differ')
    require(R.same(boundaries[0]['native_files'], rp['runtime_native_files']), 'recorded reference runtime identity drift')
    expected_files = {n+'.f32le' for n in REFERENCES} | {'mask.bf16le', *REFERENCE_METADATA,
        'GO.json', 'OBSERVATIONS.json', 'STAGES.jsonl', 'stdout.log', 'stderr.log'}
    require(set(seal['files']) == expected_files - {'SEAL.json'}, 'sealed reference exact inventory drift')
    require({p.name for p in REFERENCE.iterdir()} == expected_files, 'fresh reference directory inventory drift')
    for name, spec in ref['outputs'].items():
        require(R.same(seal['files'][spec['file']], {k:spec[k] for k in ('bytes','sha256')}),
                'reference payload seal identity drift: '+name)
        R.stat_only(ROOT, str((REFERENCE/spec['file']).relative_to(ROOT)), spec['bytes'])
    mask = dict(bytes=rp['mask_contract']['native_bytes'], sha256=rp['mask_contract']['native_sha256'])
    require(R.same(seal['files']['mask.bf16le'], mask), 'reference mask sidecar seal drift')
    R.stat_only(ROOT, str((REFERENCE/'mask.bf16le').relative_to(ROOT)), mask['bytes'])
    return ref


def _input_specs():
    rp = R.load_pins(ROOT)
    require(set(rp['producer_roles']) == ROLES, 'exact fourteen executable input roles required')
    return rp


def input_identity():
    rp = _input_specs()
    return {name: _sha_spec(ROOT/spec['path'], spec) for name, spec in rp['producer_roles'].items()}


def raw_identity(data):
    require(Path(data) == DATA, 'fixed raw provenance input required')
    rp = _input_specs()
    require(len(rp['raw_tensors']) == 13, 'exact thirteen raw provenance tensors required')
    return {spec['local_name']: _sha_spec(ROOT/spec['path'], spec) for spec in rp['raw_tensors']}


def validate_inputs(data, reference):
    rp, frozen = reference_recipe()
    ref = validate_reference_metadata(data, reference, recipe=(rp, frozen))
    inputs = {name: R.checked(ROOT, spec['path'], spec) for name, spec in rp['producer_roles'].items()}
    require(set(inputs) == ROLES, 'exact fourteen executable input roles required')
    ready = dict(status='PINNED_FULLBLOCK_FOURTEEN_READONLY_INPUTS_READY',
        roles={name:spec['record'] for name,spec in rp['producer_roles'].items()})
    # Original prefix-nine records predate the readonly metadata field. Their
    # immutable role identities are checked by recipe.metadata_check; the live
    # fixture/PhysicalMemory binding independently enforces readonly providers.
    require(all(ready['roles'][name]['readonly'] is True for name in ('wo','gamma1','wg','wu','wd')),
            'tail initial roles must remain readonly')
    evidence = {spec['path']:sha(ROOT/spec['path']) for spec in rp['input_metadata'].values()}
    evidence.update({str((REFERENCE/name).relative_to(ROOT)):sha(REFERENCE/name) for name in REFERENCE_METADATA})
    raw = raw_identity(data)
    return inputs, ready, evidence, dict(raw_tensors=raw, raw_payloads_rehashed_before_gate=13,
        raw_tensor_metadata={s['local_name']:{k:s[k] for k in ('bytes','sha256')} for s in rp['raw_tensors']},
        input_roles=14, input_identity={name:{k:spec[k] for k in ('bytes','sha256')}
                                      for name,spec in rp['producer_roles'].items()},
        official_reference_nodes_metadata=len(ref['outputs']), reference_payloads_read_before_seal=0,
        source_pin_sha256=R.PINS_SHA256, frozen_contract_sha256=R.FROZEN_CONTRACT_SHA256,
        full_checkpoint_sha256_verified=False, saved_actual_inputs_loaded=False)


def _token_bytes(name, raw, shape):
    if name not in R.TOKEN_MAJOR:
        return raw
    batch, heads, tokens, width = shape
    require(batch == 1, 'fixed single-batch reference layout')
    stride = width * 4
    return b''.join(raw[(head*tokens+token)*stride:(head*tokens+token+1)*stride]
                    for token in range(tokens) for head in range(heads))


def validate_references(data, reference):
    rp, frozen = reference_recipe()
    ref = validate_reference_metadata(data, reference, recipe=(rp, frozen))
    values = {}
    for name, spec in ref['outputs'].items():
        raw = R.checked(ROOT, str((REFERENCE/spec['file']).relative_to(ROOT)), spec)
        require(R.sha(_token_bytes(name, raw, spec['shape'])) == spec['token_major_sha256'],
                'fixed reference layout identity drift: '+name)
        native = bytearray()
        for (word,) in struct.iter_unpack('<I', raw):
            require(word & 0x7f800000 != 0x7f800000, 'nonfinite frozen reference: '+name)
            if name == 'softmax_fp32':
                native.extend(struct.pack('<I', word))
            else:
                require(word & 0xffff == 0, 'reference must be exact BF16 widening: '+name)
                native.extend(struct.pack('<H', word >> 16))
        require(R.sha(native) == spec['native_sha256'], 'native reference identity drift: '+name)
        values[name] = raw
    mask = R.checked(ROOT, str((REFERENCE/'mask.bf16le').relative_to(ROOT)),
        dict(bytes=rp['mask_contract']['native_bytes'], sha256=rp['mask_contract']['native_sha256']))
    expected = b''.join(struct.pack('<H', 0 if k <= q else 0xff7f) for q in range(128) for k in range(128))
    require(mask == expected and values['mask'] == b''.join(struct.pack('<I', w << 16)
            for (w,) in struct.iter_unpack('<H', mask)), 'exact native/export mask correspondence')
    require(values['cache_k'] == values['k'] and
            _token_bytes('cache_v',values['cache_v'],ref['outputs']['cache_v']['shape']) == values['v'] and
            _token_bytes('pv',values['pv'],ref['outputs']['pv']['shape']) == values['att'],
            'cold cache/PV correspondence drift')
    return ref, values


def correspondence():
    return v2.correspondence()


class OracleGate(v2.OracleGate):
    """Preserve exact v2 native/FENV admission, replace extension-based payload rules.

    All unlisted work files are forbidden, including historical .json/.u32le/
    .presence and extensionless data. This hook is a source-reviewed orchestration
    guard, not a sandbox for arbitrary native code or adversarial Python.
    """
    def __init__(self, data, out, reference):
        require(Path(data) == DATA and Path(reference) == REFERENCE, 'fixed fullblock gate namespaces')
        super().__init__(data, _canonical(out), reference)
        require(self.out.parent == OUTPUT_ROOT, 'fullblock output namespace required')
        p = verify_dependencies()
        rp = R.load_pins(ROOT)
        self.input_paths = {ROOT/s['path'] for s in rp['producer_roles'].values()}
        self.raw_paths = {ROOT/s['path'] for s in rp['raw_tensors']}
        self.reference_paths = {REFERENCE/(n+'.f32le') for n in REFERENCES} | {REFERENCE/'mask.bf16le'}
        require((len(self.input_paths), len(self.raw_paths), len(self.reference_paths)) == (14, 13, 30),
                'exact input/raw/reference path counts required')
        self.metadata_paths = {ROOT/name for name in p['dependency_sha256']}
        # The fullblock reference recipe transitively pins preserved M16/M128
        # source closures. source_check rehashes these exact files after seal;
        # denying them would recreate the old postseal validation self-lock.
        self.metadata_paths |= {ROOT/name for name in rp['sources']}
        for closure in rp['preserved_execution_closures'].values():
            self.metadata_paths |= {ROOT/name for name in closure['sha256']}
        self.metadata_paths |= {path for path in HERE.iterdir() if path.is_file() and
                               (path.suffix in ('.py','.md') or path.name in ('pins.json','BUDGET.json'))}
        self.runtime_paths = {Path(n) if Path(n).is_absolute() else ROOT/n
                              for n in p.get('runtime_read_sha256', {})}
        self.runtime_paths |= {Path(s['path']) if Path(s['path']).is_absolute() else ROOT/s['path']
                               for s in rp['runtime_native_files'].values()}
        self.runtime_paths |= {self.ctypes_path}
        self.shutil_path = Path(shutil.__file__).resolve()
        require(sha(self.shutil_path) == SHUTIL_SOURCE_SHA256, 'shutil cleanup source drift')
        self.expected_cleanup = v2.code_in(compile(self.shutil_path.read_text(), str(self.shutil_path),
            'exec', dont_inherit=True, optimize=sys.flags.optimize), '_rmtree_safe_fd')
        self.input_reads = []
        self.source_cache_bypasses = []
        self.cleanup_directory_reads = []

    def open_after_seal(self, seal):
        require(not self.opened and type(seal) is dict, 'one fresh whole-launch seal required')
        for key in ('actual_outputs_sealed', 'finalfence', 'same_live_identity'):
            require(seal.get(key) is True, 'whole-launch seal missing '+key)
        for key, value in (('public_completions',21), ('actual_owner_jobs',17), ('accepted_launch_results',1)):
            require(type(seal.get(key)) is int and seal[key] == value, 'whole-launch seal count: '+key)
        debt = seal.get('outstanding_debts')
        require(type(debt) is dict and all(v is None or v is False or type(v) is int and v == 0
                                         for v in debt.values()), 'whole-launch seal has outstanding debts')
        self.opened = True

    def _readonly(self, mode, flags):
        require((mode is None or isinstance(mode,str) and all(c not in mode for c in 'wa+x')) and
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_CREAT|os.O_TRUNC) == 0,
                'pinned inputs, code, provenance and references must remain read-only')

    def _deny(self, path):
        self.blocked += 1
        raise ValueError('unapproved payload/historical artifact or reference before whole-launch seal: '+str(path))

    def _cleanup_directory(self, raw, mode, flags, frame):
        """Resolve audit's omitted dir_fd only for the original shutil helper."""
        if (Path(raw).is_absolute() or frame.f_globals is not shutil.__dict__ or
                frame.f_code is not shutil._rmtree_safe_fd.__code__ or frame.f_code != self.expected_cleanup):
            return None
        require(mode is None and type(flags) is int and
                flags & ~getattr(os,'O_CLOEXEC',0) == os.O_RDONLY|os.O_NONBLOCK,
                'cleanup directory open flags drift')
        require(raw not in ('','.','..') and Path(raw).name == raw and
                frame.f_locals.get('name') == raw, 'cleanup name must be exact original directory entry')
        fd = frame.f_locals.get('dirfd')
        require(type(fd) is int and fd >= 0, 'cleanup requires original live parent dirfd')
        parent = _canonical(os.readlink('/proc/self/fd/'+str(fd)))
        path = _canonical(parent/raw)
        require(parent.is_relative_to(self.out) and path != self.out and path.is_relative_to(self.out)
                and path.is_dir() and _canonical(frame.f_locals['path']) == path,
                'cleanup directory must be inside the current output')
        require(sha(self.shutil_path) == SHUTIL_SOURCE_SHA256, 'shutil source drift at cleanup admission')
        self.cleanup_directory_reads.append(str(path.relative_to(self.out)))
        return path

    def audit(self, event, args):
        # Keep direct ctypes call frames: super().audit here would insert an
        # extra Python frame and invalidate the exact original v2 FENV proof.
        if event == 'ctypes.dlopen' and args[0] is None:
            require(not self.opened and self.environment_handle is None, 'FENV handle only once before seal')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__init__')
            self._original_environment_frames(frame.f_back)
            require(frame.f_locals.get('name') is None, 'FENV handle must target current process')
            self.environment_handle = id(frame.f_locals['self'])
            self.environment_events.append(dict(event=event, target=None,
                caller='ScalarService.__init__ -> ScalarService._check_environment -> ctypes.CDLL.__init__',
                source_sha256=v2.pins()['scalar_source_sha256'], admitted=True))
            return
        if event == 'ctypes.dlsym' and getattr(args[0], '_name', 'not-current-process') is None:
            require(id(args[0]) == self.environment_handle and args[1] == 'fegetround',
                    'current-process symbol restricted to original fegetround probe')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__getitem__')
            self._ctypes_frame(frame.f_back, '__getattr__')
            self._original_environment_frames(frame.f_back.f_back)
            self.environment_events.append(dict(event=event, symbol='fegetround', admitted=True))
            return
        if event == 'ctypes.dlopen':
            return super().audit(event, args)
        if event == 'import' and args[0].split('.')[0] in ('torch', 'transformers'):
            self._deny(args[0])
        if event != 'open' or not isinstance(args[0], (str,bytes)):
            return
        raw = os.fsdecode(args[0])
        mode, flags = args[1], args[2]
        cleanup = self._cleanup_directory(raw, mode, flags, sys._getframe(1))
        if cleanup is not None:
            return
        path = _canonical(raw)
        if path.is_relative_to(self.out):
            return
        self._readonly(mode, flags)
        if path.suffix == '.pyc':
            try:
                source = _canonical(importlib.util.source_from_cache(str(path)))
            except (ValueError, NotImplementedError):
                source = None
            if source in self.metadata_paths and source.suffix == '.py':
                # SourceFileLoader catches this as an ordinary cache miss and
                # reads the source-bound .py; no unreviewed pyc bytes are read.
                self.source_cache_bypasses.append(str(path))
                raise FileNotFoundError(errno.ENOENT, 'use pinned source instead of bytecode cache', str(path))
        if path in self.input_paths:
            self.input_reads.append(str(path.relative_to(ROOT)))
            return
        if path in self.reference_paths:
            if not self.opened:
                self._deny(path)
            self.reference_reads.append(str(path.relative_to(ROOT)))
            return
        if path in self.raw_paths:
            if not self.opened:
                self._deny(path)
            self.provenance_reads.append(str(path.relative_to(ROOT)))
            return
        if path in self.artifacts.values():
            self.artifact_reads.append(dict(event=event, path=str(path.relative_to(ROOT))))
            return
        if path in self.metadata_paths or path in self.runtime_paths:
            return
        # Ordinary stdlib source imports/tracebacks remain available. Third-party
        # runtime bytes and every file under work require exact pinned admission.
        if (not path.is_relative_to(ROOT/'work') and path.suffix in ('.py','.pyc') and
                path.is_relative_to(Path(sys.base_prefix).resolve())):
            return
        if str(path) in ('/proc/self/stat', '/proc/self/statm', '/proc/self/status'):
            return
        self._deny(path)
