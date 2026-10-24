"""Exclusive software mapping of the retained 16 FP32 Add/Mul lanes.

The current ElementwiseMemoryEngine faults on inexact underflow. This adapter
defaults to that policy. An explicit ieee_rne candidate accepts finite gradual
underflow without changing rounded bits or flags; its control is NOT connected
to the current Chisel ElementwiseMemoryEngine. That gap remains explicit.
Host calls/issue counts are NOT measured hardware cycles or achieved throughput.
"""
from collections import Counter
import ctypes as C
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess

from ..rms_owner import ROOT, ArithmeticFault, finite, sha


LEGACY_POLICY = 'legacy_vector_fatal_underflow'
IEEE_POLICY = 'ieee_rne_finite_gradual_underflow'
POLICY_MASKS = {LEGACY_POLICY: 30, IEEE_POLICY: 28}

LEGACY_BACKEND = 'legacy_host_postfix_uf_v1'
FINITE_MUL_UF_BACKEND = 'finite_mul_tininess_r2'
ARITHMETIC_BACKENDS = (LEGACY_BACKEND, FINITE_MUL_UF_BACKEND)
VECTOR_ABI = 'gdn_vector16_add_mul_policy_trace_v1'


@dataclass(frozen=True)
class BackendIdentity:
    backend: str
    implementation_version: str
    source: str
    source_sha256: str
    abi: str
    library_sha256: str


def backend_source(arithmetic_backend):
    """Closed, source-pinned choices; never discover a backend from a receipt."""
    if type(arithmetic_backend) is not str or arithmetic_backend not in ARITHMETIC_BACKENDS:
        raise ValueError('explicit supported Vector arithmetic backend required')
    if arithmetic_backend == LEGACY_BACKEND:
        name, version, digest = ('candidates/qwen35_gdn_prefill/chunk/vector16.cpp',
            'vector16-host-v1', 'ef614bd591129c9294e0a3846ca3b4a72c9fdd80ef626d188196cd1f4f0e6919')
    else:
        name, version, digest = ('candidates/qwen35_uf_predicate_r2/vector16_tininess.cpp',
            'vector16-finite-mul-uf-r2', 'a54c125ba27357123c5edb1ec4ff0dad0e883f3dd47b66852d7e2f56fdceeec7')
    source = (ROOT / name).resolve(strict=True)
    if sha(source.read_bytes()) != digest:
        raise ValueError('Vector16 pinned arithmetic source changed: ' + name)
    return source, dict(backend=arithmetic_backend, implementation_version=version,
                       source=name, source_sha256=digest, abi=VECTOR_ABI)


FLAGS = ('-std=c++17', '-O2', '-shared', '-fPIC', '-fno-fast-math',
         '-ffp-contract=off', '-frounding-math')


class VectorArithmeticFault(ArithmeticFault):
    def __init__(self, reason, operation, a, b, result=None, flags=None, lane_flags=None, environment=None):
        super().__init__(reason)
        def padded(values):
            return None if values is None else list(values) + [None] * (16 - len(values))
        self.diagnostic = dict(resource='Vector16', operation=operation, active_lanes=len(a),
            a_words=padded(a), b_words=padded(b), result_words=padded(result),
            exception_flags=flags, lane_exception_flags=padded(lane_flags),
            host_environment_status=environment, reason=reason)


def build_library(directory, *, arithmetic_backend=LEGACY_BACKEND):
    """Explicit one-compiler-process host build; no parallel build or RTL."""
    source, backend = backend_source(arithmetic_backend)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / ('gdn_vector16.so' if arithmetic_backend == LEGACY_BACKEND
                          else 'gdn_vector16_finite_mul_tininess_r2.so')
    compiler = shutil.which('g++')
    if compiler is None:
        raise RuntimeError('g++ required for the generic 16-lane host adapter')
    argv = [compiler, *FLAGS, str(source), '-o', str(output)]
    subprocess.run(argv, check=True, capture_output=True, timeout=60)
    # Recheck the pinned input after compilation, before issuing a receipt.
    backend_source(arithmetic_backend)
    output.with_suffix('.json').write_text(json.dumps(dict(
        status='PASS_HOST_BUILD_ONLY', argv=argv, source_sha256=sha(source.read_bytes()),
        library_sha256=sha(output.read_bytes()), compiler_sha256=sha(Path(compiler).read_bytes()),
        arithmetic_backend=backend, hardware_simulation=False, compiler_processes=1), indent=2) + '\n')
    return output


def verify_library(library, *, arithmetic_backend=LEGACY_BACKEND):
    """Validate identity without loading or executing the native library.

    Original receipts without backend metadata remain valid ONLY for the
    explicit/default legacy source. A new backend always requires its full
    version/source/ABI record in addition to every original host build gate.
    """
    source, backend = backend_source(arithmetic_backend)
    library = Path(library).resolve(strict=True)
    receipt = json.loads(library.with_suffix('.json').read_text())
    library_sha256 = sha(library.read_bytes())
    if (type(receipt) is not dict or receipt.get('status') != 'PASS_HOST_BUILD_ONLY' or
            receipt.get('source_sha256') != backend['source_sha256'] or
            receipt.get('library_sha256') != library_sha256 or
            type(receipt.get('argv')) is not list or not receipt['argv'] or
            receipt['argv'][1:] != [*FLAGS, str(source), '-o', str(library)]):
        raise ValueError('Vector16 requires its exact strict host build receipt')
    if ('arithmetic_backend' in receipt or arithmetic_backend != LEGACY_BACKEND):
        if receipt.get('arithmetic_backend') != backend:
            raise ValueError('Vector16 arithmetic backend/version/source/ABI receipt mismatch')
    compiler = Path(receipt['argv'][0]).resolve(strict=True)
    if receipt.get('compiler_sha256') != sha(compiler.read_bytes()):
        raise ValueError('Vector16 compiler identity changed after host build')
    return library, receipt, BackendIdentity(**backend, library_sha256=library_sha256)


class Vector16:
    def __init__(self, library, *, exception_policy=LEGACY_POLICY,
                 arithmetic_backend=LEGACY_BACKEND):
        if exception_policy not in POLICY_MASKS:
            raise ValueError("explicit supported Vector exception policy required")
        self.exception_policy = exception_policy
        self.fatal_mask = POLICY_MASKS[exception_policy]
        self.library, self.build_receipt, self.backend_identity = verify_library(
            library, arithmetic_backend=arithmetic_backend)
        self.lib = C.CDLL(str(self.library))
        self.lib.gdn_vector16.argtypes = (C.c_uint, C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.c_uint)
        self.lib.gdn_vector16.restype = C.c_int
        self.lib.gdn_vector16_trace.argtypes = (*self.lib.gdn_vector16.argtypes, C.POINTER(C.c_uint32))
        self.lib.gdn_vector16_trace.restype = C.c_int
        self.lib.gdn_vector16_mul_add_policy_trace.argtypes = (
            C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32), C.c_uint, C.POINTER(C.c_uint32), C.POINTER(C.c_int), C.c_uint)
        self.lib.gdn_vector16_mul_add_policy_trace.restype = C.c_uint
        self.lib.gdn_vector16_environment.argtypes = ()
        self.lib.gdn_vector16_environment.restype = C.c_int
        self.a, self.b, self.output = ((C.c_uint32 * 16)() for _ in range(3))
        self.total = (C.c_uint32 * 16)()
        self.lane_flags = (C.c_uint32 * 16)()
        self.issue_flags = (C.c_int * 2)()
        self.client, self.calls, self.lane_ops, self.flags = None, Counter(), Counter(), Counter()
        self.host_calls = Counter()
        self.resource_address = C.addressof(self.output)
        self.library_sha256 = self.backend_identity.library_sha256
        self.__loaded_arithmetic_identity = self._current_arithmetic_identity()

    @property
    def _loaded_arithmetic_identity(self):
        # Read-only admission baseline. This is an integrity guard against
        # accidental rebinding, not isolation from arbitrary Python code.
        return self.__loaded_arithmetic_identity

    def _current_arithmetic_identity(self):
        names = ('gdn_vector16', 'gdn_vector16_trace',
                 'gdn_vector16_mul_add_policy_trace', 'gdn_vector16_environment')
        try:
            return (self.backend_identity, self.library, self.library_sha256, id(self.lib),
                    tuple((id(getattr(self.lib, name)), tuple(getattr(self.lib, name).argtypes),
                           getattr(self.lib, name).restype, id(getattr(getattr(self.lib, name), 'errcheck', None)))
                          for name in names))
        except (AttributeError, TypeError) as error:
            raise ValueError('Vector16 loaded arithmetic binding changed') from error

    def arithmetic_identity(self):
        """Validate against the ORIGINAL constructor binding, never relabel it.

        No source reads or extra arithmetic occur on coordinator resource checks.
        File integrity is separately checked by pre/post execution snapshots.
        """
        current = self._current_arithmetic_identity()
        if current != self._loaded_arithmetic_identity:
            raise ValueError('Vector16 loaded arithmetic binding changed')
        return current

    def backend_report(self):
        self.arithmetic_identity()
        return asdict(self.backend_identity)

    def acquire(self, client):
        if self.client is not None:
            return False
        self.client = client
        return True

    def release(self, client):
        if self.client is not client:
            raise ValueError('Vector16 lease owner mismatch')
        self.client = None

    def op(self, client, operation, a, b):
        if self.client is not client:
            raise ValueError('Vector16 operation without exclusive lease')
        if operation not in ('add', 'mul') or not 1 <= len(a) == len(b) <= 16:
            raise ValueError('Vector16 supports only Add/Mul, 1..16 active lanes')
        for i, (x, y) in enumerate(zip(a, b)):
            if not all(type(v) is int and 0 <= v < 1 << 32 for v in (x, y)):
                raise ValueError('Vector16 requires FP32 words')
            if not finite(x) or not finite(y):
                raise VectorArithmeticFault('Vector16 nonfinite input', operation, a, b)
            self.a[i], self.b[i] = x, y
        self.calls[operation] += 1
        self.lane_ops[operation] += len(a)
        self.host_calls['single'] += 1
        flags = self.lib.gdn_vector16_trace(operation == 'mul', self.a, self.b, self.output, len(a), self.lane_flags)
        if flags < 0:
            raise VectorArithmeticFault('Vector16 requires RNE with FTZ/DAZ disabled',
                                        operation, a, b, environment=flags)
        self.flags[flags] += 1
        result = list(self.output)[:len(a)]
        if flags & self.fatal_mask or not all(finite(v) for v in result):
            raise VectorArithmeticFault('Vector fatal exception under explicit policy ' + self.exception_policy,
                operation, a, b, result, flags, list(self.lane_flags)[:len(a)])
        return result

    def mul_add(self, client, a, b, total):
        """Host batch of Mul(a,b), then Add(total,product), never an FMA.

        Counts and faults describe the individual logical issues. No Add is
        issued after a failed Mul, and diagnostics retain that failing stage.
        """
        if self.client is not client:
            raise ValueError('Vector16 operation without exclusive lease')
        if not 1 <= len(a) == len(b) <= 16:
            raise ValueError('Vector16 supports only Add/Mul, 1..16 active lanes')
        # Malformed Add operands must be rejected only AFTER the Mul. Keep the
        # original path for those inputs so even its validation order is exact.
        if len(total) != len(a) or any(type(v) is not int or not 0 <= v < 1 << 32 or
                                       not finite(v) for v in total):
            return self.op(client, 'add', total, self.op(client, 'mul', a, b))
        for i, (x, y) in enumerate(zip(a, b)):
            if not all(type(v) is int and 0 <= v < 1 << 32 for v in (x, y)):
                raise ValueError('Vector16 requires FP32 words')
            if not finite(x) or not finite(y):
                raise VectorArithmeticFault('Vector16 nonfinite input', 'mul', a, b)
            self.a[i], self.b[i], self.total[i] = x, y, total[i]
        self.calls['mul'] += 1
        self.lane_ops['mul'] += len(a)
        self.host_calls['mul_add'] += 1
        stage = self.lib.gdn_vector16_mul_add_policy_trace(self.a, self.b, self.total,
            self.output, len(a), self.lane_flags, self.issue_flags, self.fatal_mask)
        mul_flags, add_flags = self.issue_flags
        if mul_flags >= 0:
            self.flags[mul_flags] += 1
        if stage == 2:
            self.calls['add'] += 1
            self.lane_ops['add'] += len(a)
            if add_flags >= 0:
                self.flags[add_flags] += 1
        flags = mul_flags if stage == 1 else add_flags
        operation = 'mul' if stage == 1 else 'add'
        if flags < 0:
            raise VectorArithmeticFault('Vector16 requires RNE with FTZ/DAZ disabled',
                operation, a if stage == 1 else total,
                b if stage == 1 else list(self.b)[:len(a)], environment=flags)
        result = list(self.b if stage == 1 else self.output)[:len(a)]
        if flags & self.fatal_mask or not all(finite(v) for v in result):
            raise VectorArithmeticFault('Vector fatal exception under explicit policy ' + self.exception_policy,
                operation, a if stage == 1 else total, b if stage == 1 else list(self.b)[:len(a)],
                result, flags, list(self.lane_flags)[:len(a)])
        return result
