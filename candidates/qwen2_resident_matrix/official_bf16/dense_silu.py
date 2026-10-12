"""Opt-in BF16 tensor boundaries over the existing Matrix/SiLU host owners.

Public descriptor extents and packet words remain FP32. This module never
rounds an accumulator or selects the packed-output ``output_bf16`` flag.
Bindings come from validated public Jobs, before their original drivers run;
the admitted owner's Job is checked again at every actual Matrix group.
No RTL, whole-chain acceptance, hardware timing or new arithmetic unit is
established by this software policy increment.
"""
import ctypes as C
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from types import MappingProxyType

from ..ffn_attention.matrix_service import (
    DenseLibraryAdapter, MatrixService, configure_library, require,
)
from ..transposed_down.model import Job as DenseJob


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
POLICY_VERSION = 'official_bf16_dense_silu_v1'
STRICT_FLAGS = ('-shared', '-fPIC', '-O2', '-ffp-contract=off', '-fno-fast-math')
TRANSLATION_UNITS = (
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/official_bf16/silu_recipe.cpp',
)
SOURCE_CLOSURE = TRANSLATION_UNITS + (
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
    'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp',
)
JOB_FIELDS = ('kind', 'tag', 'a', 'b', 'dst', 'm', 'n', 'k', 'write_bytes',
              'weight_bf16', 'activation_bf16', 'output_bf16')
ROLE_SHAPES = MappingProxyType({
    'q_raw': (1536, 1536), 'k_raw': (1536, 256), 'v_raw': (1536, 256),
    'dense_o': (1536, 1536), 'gate': (1536, 8960), 'up': (1536, 8960),
    'down': (8960, 1536),
})
DOWN_GROUPS = ((0, 2560), (2560, 5120), (5120, 7680), (7680, 8960))


def bf16_rne_word(value):
    """RNE materialization into a 4-byte FP32 word; preserves nonfinite bits.

    A finite FP32 value can round to BF16 infinity. It is returned as infinity
    so the existing owner finite-value validation rejects that exact packet.
    This helper does not silently clamp, flush subnormals, or rewrite NaNs.
    """
    require(type(value) is int and 0 <= value <= 0xffffffff, 'FP32 word width')
    if value & 0x7f800000 == 0x7f800000:
        return value
    return (value + 0x7fff + ((value >> 16) & 1)) & 0xffff0000


def _job_snapshot(job):
    require(is_dataclass(job) and getattr(type(job), '__dataclass_params__').frozen,
            'Dense BF16 policy needs an immutable validated public Job')
    fields = asdict(job)
    require(set(JOB_FIELDS) <= fields.keys() and
            all(name == 'c' and value == 0 for name, value in fields.items()
                if name not in JOB_FIELDS), 'unsupported Dense public Job fields')
    return tuple((name, fields[name]) for name in JOB_FIELDS)


@dataclass(frozen=True)
class DenseBinding:
    """Immutable explicit role and complete public Job identity."""
    role: str
    job_fields: tuple

    def __post_init__(self):
        require(type(self.job_fields) is tuple and
                all(type(item) is tuple and len(item) == 2 for item in self.job_fields) and
                tuple(name for name, _ in self.job_fields) == JOB_FIELDS,
                'immutable complete Dense Job binding')
        fields = dict(self.job_fields)
        require(self.role in ROLE_SHAPES, 'unknown explicit Dense role')
        require(all(type(fields[name]) is bool for name in
                    ('weight_bf16', 'activation_bf16', 'output_bf16')),
                'Dense dtype flags must be booleans')
        require(all(type(fields[name]) is int for name in
                    ('tag', 'a', 'b', 'dst', 'm', 'n', 'k', 'write_bytes')),
                'Dense geometry, address and tag fields must be integers')
        DenseJob(**fields).validate()
        require((fields['k'], fields['n']) == ROLE_SHAPES[self.role],
                'explicit Dense role/logical shape mismatch')
        require(fields['weight_bf16'] and not fields['activation_bf16'] and
                not fields['output_bf16'] and fields['write_bytes'] == fields['m'] * fields['n'] * 4,
                'BF16 values require existing four-byte FP32 storage and spans')

    @classmethod
    def from_job(cls, job, role):
        return cls(role, _job_snapshot(job))

    @property
    def tag(self):
        return dict(self.job_fields)['tag']

    @property
    def logical_k(self):
        return dict(self.job_fields)['k']

    def materializes(self, group_start, group_end):
        require((group_start, group_end) in (DOWN_GROUPS if self.role == 'down' else ((0, self.logical_k),)),
                'Matrix group does not match bound logical K/chunk policy')
        return self.role not in ('q_raw', 'k_raw', 'v_raw') and group_end == self.logical_k


class OfficialMatrixService(MatrixService):
    """Same serialized Matrix resource, with explicitly bound Dense outputs."""
    def __init__(self, library, bindings=()):
        super().__init__(library)
        self._bindings = {}
        for binding in bindings:
            self._bind(binding)

    @property
    def bindings(self):
        return MappingProxyType(self._bindings)

    def _bind(self, binding):
        require(isinstance(binding, DenseBinding), 'Dense policy binding type')
        previous = self._bindings.get(binding.tag)
        require(previous is None or previous == binding, 'conflicting Dense role/Job rebind')
        require(previous is not None or self.owner is None, 'bind Dense Job before Matrix acquisition')
        self._bindings[binding.tag] = binding
        return binding

    def bind_dense_job(self, job, role):
        return self._bind(DenseBinding.from_job(job, role))

    def acquire(self, owner, mode, tag):
        if mode == 'dense':
            require(tag in self._bindings, 'Dense acquisition has no explicit validated Job binding')
        return super().acquire(owner, mode, tag)

    def dense_library(self, owner):
        self._check_owner(owner, 'dense')
        if self._dense is None:
            self._dense = OfficialDenseLibraryAdapter(self, owner, self._bindings[self.owner_tag])
        return self._dense

    def report(self):
        result = super().report()
        result.update(numerical_policy=POLICY_VERSION,
            dense_bindings=[dict(role=b.role, job=dict(b.job_fields)) for b in self._bindings.values()],
            storage_word_bytes=4, accumulator_materialization=False)
        return result


class OfficialDenseLibraryAdapter(DenseLibraryAdapter):
    """Round completed output snapshots before the unchanged digest fence."""
    def __init__(self, service, owner, binding):
        super().__init__(service, owner)
        self._binding = binding
        self._group_range = None
        self._materialize = False

    @property
    def binding(self):
        return self._binding

    def td_group(self, start, end, contexts):
        self._check()
        require(_job_snapshot(self.owner.job) == self.binding.job_fields,
                'admitted Dense owner Job differs from immutable role binding')
        require(type(start) is int and type(end) is int, 'Matrix logical K boundaries')
        materialize = self.binding.materializes(start, end)
        rc = super().td_group(start, end, contexts)
        if rc == 0:
            self._group_range = (start, end)
            self._materialize = materialize
        return rc

    def td_step(self, k, context, clear, last, finish, emit, a, b, output):
        self._check()
        require(self._group_range is not None, 'Dense step before a bound Matrix group')
        if last:
            address = C.cast(output, C.c_void_p).value
            base = self.service.resource_address
            require(address is not None and (address + 16384 <= base or
                    base + self.service.lib.matrix_accumulator_bytes() <= address),
                    'Dense result buffer aliases the live Matrix accumulator')
        # This is the inherited adapter's single arithmetic call, followed by
        # output materialization BEFORE its immutable retirement digest. The
        # caller-provided output packet never aliases accum[5][16][256].
        rc = self.service.lib.td_step(k, context, clear, last, finish, emit, a, b, output)
        if rc >= 0:
            self.service.counts['dense_steps'] += 1
        if rc == 1:
            require(bool(last) and k + 1 == self._group_range[1],
                    'completed Dense packet before actual group K terminal')
            if self._materialize:
                words = C.cast(output, C.POINTER(C.c_uint32))
                overflow = 0
                for index in range(4096):
                    source = int(words[index])
                    rounded = bf16_rne_word(source)
                    overflow += (source & 0x7f800000 != 0x7f800000 and
                                 rounded & 0x7f800000 == 0x7f800000)
                    words[index] = rounded
                self.service.counts['dense_bf16_packets'] += 1
                self.service.counts['dense_bf16_words'] += 4096
                self.service.counts['dense_bf16_overflow_words'] += overflow
            else:
                self.service.counts['dense_fp32_packets'] += 1
            digest = hashlib.sha256(C.string_at(output, 4096 * 4)).digest()
            self.pending.append((self.ticket, context, bool(last), digest))
        return rc


def configure_silu_library(library):
    p = C.POINTER(C.c_uint32)
    for name in ('sf_vector', 'sf_vector_bf16_v1'):
        getattr(library, name).argtypes, getattr(library, name).restype = [p] * 6, C.c_int
    for name in ('sf_reset', 'sf_reset_bf16_v1'):
        getattr(library, name).argtypes, getattr(library, name).restype = [], C.c_int
    for name in ('sf_bf16_v1_calls', 'sf_bf16_v1_failures'):
        getattr(library, name).argtypes, getattr(library, name).restype = [], C.c_uint64
    library.sf_reference.argtypes, library.sf_reference.restype = [p, p, p, C.c_uint], C.c_int
    return library


class SelectedSiluLibrary:
    """Explicit opt-in facade for the unchanged six-phase driver ABI."""
    numerical_policy = POLICY_VERSION
    sf_entrypoint = 'sf_vector_bf16_v1'

    def __init__(self, library):
        self.library = configure_silu_library(library)
        self.sf_vector = library.sf_vector_bf16_v1
        self.sf_reset = library.sf_reset_bf16_v1
        self.sf_calls = library.sf_bf16_v1_calls
        self.sf_failures = library.sf_bf16_v1_failures

    def __getattr__(self, name):
        return getattr(self.library, name)


def selected_library(library):
    return SelectedSiluLibrary(library)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compiler_identity():
    resolved = shutil.which('g++')
    require(resolved is not None, 'g++ compiler is unavailable')
    path = Path(resolved).resolve(strict=True)
    return dict(path=str(path), sha256=_sha(path), version=subprocess.check_output(
        [str(path), '--version'], text=True, timeout=10).splitlines()[0])


def build_library(out):
    """Compile the new source closure and return (CDLL, fresh receipt dict)."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    library_path = out / 'official_bf16_matrix_silu.so'
    receipt_path = out / 'official_bf16_compile.json'
    require(not library_path.exists() and not receipt_path.exists(),
            'BF16 build destination already contains a library or receipt')
    sources = {name: _sha(ROOT / name) for name in SOURCE_CLOSURE}
    compiler = compiler_identity()
    argv = [compiler['path'], *STRICT_FLAGS, *(str(ROOT / name) for name in TRANSLATION_UNITS),
            '-o', str(library_path)]
    receipt = dict(schema=1, policy=POLICY_VERSION, status='STARTED', argv=argv, compiler=compiler,
        returncode=None, stdout='', stderr='', source_sha256=sources,
        library=str(library_path), library_sha256=None,
        selected_silu_entrypoint='sf_vector_bf16_v1', original_silu_entrypoint='sf_vector',
        accumulator_source='candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
        hardware_simulation=False, official_framework_acceptance=False)
    def save_receipt():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        (out / 'official_bf16_compile.stdout.log').write_text(receipt['stdout'])
        (out / 'official_bf16_compile.stderr.log').write_text(receipt['stderr'])
    save_receipt()
    try:
        completed = subprocess.run(argv, text=True, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        def decoded(value):
            return value.decode(errors='replace') if isinstance(value, bytes) else (value or '')
        receipt.update(status='FAIL', failure_reason=str(error),
            stdout=decoded(getattr(error, 'stdout', '')), stderr=decoded(getattr(error, 'stderr', '')))
        save_receipt()
        raise
    receipt.update(status='FAIL', returncode=completed.returncode,
        stdout=completed.stdout, stderr=completed.stderr,
        library_sha256=_sha(library_path) if library_path.is_file() else None)
    save_receipt()
    require(completed.returncode == 0, 'BF16 strict host recipe compile failed: ' + completed.stderr)
    require(sources == {name: _sha(ROOT / name) for name in SOURCE_CLOSURE},
            'BF16 arithmetic source changed during compilation')
    require(compiler == compiler_identity(), 'BF16 compiler changed during compilation')
    receipt['status'] = 'PASS'
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    verify_library(receipt_path)
    return configure_silu_library(configure_library(C.CDLL(str(library_path)))), receipt


def verify_library(receipt):
    """Validate source closure, strict invocation, current compiler, and ELF."""
    data = json.loads(Path(receipt).read_text()) if isinstance(receipt, (str, Path)) else dict(receipt)
    require(data.get('schema') == 1 and data.get('policy') == POLICY_VERSION and data.get('status') == 'PASS' and
            data.get('returncode') == 0 and data.get('selected_silu_entrypoint') == 'sf_vector_bf16_v1' and
            data.get('original_silu_entrypoint') == 'sf_vector', 'BF16 compile receipt policy/ABI')
    binary = Path(data['library']).resolve()
    compiler = compiler_identity()
    require(compiler == data['compiler'], 'BF16 compiler identity changed')
    expected = [compiler['path'], *STRICT_FLAGS, *(str(ROOT / name) for name in TRANSLATION_UNITS), '-o', str(binary)]
    require(data['argv'] == expected, 'BF16 strict compiler flags or translation units changed')
    require(data['source_sha256'] == {name: _sha(ROOT / name) for name in SOURCE_CLOSURE},
            'BF16 arithmetic source closure drift')
    require(binary.read_bytes()[:4] == b'\x7fELF' and _sha(binary) == data['library_sha256'],
            'BF16 shared ELF drift')
    return data
