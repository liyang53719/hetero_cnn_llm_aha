"""Exclusive software mapping of the retained 16 FP32 Add/Mul lanes.

The current ElementwiseMemoryEngine faults on inexact underflow. This adapter
preserves that policy; changing it would require an explicit RTL policy change.
Host calls/issue counts are NOT measured hardware cycles or achieved throughput.
"""
from collections import Counter
import ctypes as C
import json
from pathlib import Path
import shutil
import subprocess

from ..rms_owner import ArithmeticFault, finite, sha


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


def build_library(directory):
    """Explicit one-compiler-process host build; no parallel build or RTL."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name('vector16.cpp').resolve()
    output = directory / 'gdn_vector16.so'
    compiler = shutil.which('g++')
    if compiler is None:
        raise RuntimeError('g++ required for the generic 16-lane host adapter')
    argv = [compiler, *FLAGS, str(source), '-o', str(output)]
    subprocess.run(argv, check=True, capture_output=True, timeout=60)
    output.with_suffix('.json').write_text(json.dumps(dict(
        status='PASS_HOST_BUILD_ONLY', argv=argv, source_sha256=sha(source.read_bytes()),
        library_sha256=sha(output.read_bytes()), compiler_sha256=sha(Path(compiler).read_bytes()),
        hardware_simulation=False, compiler_processes=1), indent=2) + '\n')
    return output


class Vector16:
    def __init__(self, library):
        self.library = Path(library).resolve(strict=True)
        receipt = json.loads(self.library.with_suffix('.json').read_text())
        source = Path(__file__).with_name('vector16.cpp').resolve()
        if (receipt.get('status') != 'PASS_HOST_BUILD_ONLY' or
                receipt.get('source_sha256') != sha(source.read_bytes()) or
                receipt.get('library_sha256') != sha(self.library.read_bytes()) or
                receipt.get('argv', [])[1:] != [*FLAGS, str(source), '-o', str(self.library)]):
            raise ValueError('Vector16 requires its exact strict host build receipt')
        compiler = Path(receipt['argv'][0]).resolve(strict=True)
        if receipt.get('compiler_sha256') != sha(compiler.read_bytes()):
            raise ValueError('Vector16 compiler identity changed after host build')
        self.build_receipt = receipt
        self.lib = C.CDLL(str(self.library))
        self.lib.gdn_vector16.argtypes = (C.c_uint, C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.c_uint)
        self.lib.gdn_vector16.restype = C.c_int
        self.lib.gdn_vector16_trace.argtypes = (*self.lib.gdn_vector16.argtypes, C.POINTER(C.c_uint32))
        self.lib.gdn_vector16_trace.restype = C.c_int
        self.lib.gdn_vector16_mul_add_trace.argtypes = (
            C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint32),
            C.POINTER(C.c_uint32), C.c_uint, C.POINTER(C.c_uint32), C.POINTER(C.c_int))
        self.lib.gdn_vector16_mul_add_trace.restype = C.c_uint
        self.lib.gdn_vector16_environment.argtypes = ()
        self.lib.gdn_vector16_environment.restype = C.c_int
        self.a, self.b, self.output = ((C.c_uint32 * 16)() for _ in range(3))
        self.total = (C.c_uint32 * 16)()
        self.lane_flags = (C.c_uint32 * 16)()
        self.issue_flags = (C.c_int * 2)()
        self.client, self.calls, self.lane_ops, self.flags = None, Counter(), Counter(), Counter()
        self.host_calls = Counter()
        self.resource_address = C.addressof(self.output)
        self.library_sha256 = sha(self.library.read_bytes())

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
        if flags & 30 or not all(finite(v) for v in result):
            raise VectorArithmeticFault('retained Vector policy: invalid/div0/overflow/inexact-underflow',
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
        stage = self.lib.gdn_vector16_mul_add_trace(self.a, self.b, self.total,
            self.output, len(a), self.lane_flags, self.issue_flags)
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
        if flags & 30 or not all(finite(v) for v in result):
            raise VectorArithmeticFault('retained Vector policy: invalid/div0/overflow/inexact-underflow',
                operation, a if stage == 1 else total, b if stage == 1 else list(self.b)[:len(a)],
                result, flags, list(self.lane_flags)[:len(a)])
        return result
