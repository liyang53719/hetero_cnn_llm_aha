"""Isolated finite FP32 two-pass reference adapter, not a hardware execution.

The bounded runner loads and pins the existing repaired ELF and verifies the
native symbols. No build, CDLL load, environment repair or old-model import
occurs in this module. A fake primitive is used ONLY by labelled protocol tests.
"""
from dataclasses import dataclass

POLICY_ID = 'finite-fp32-rne-separate-mul-add-hf-tiny-after-fatal30-v1'
FATAL_MASK = 30
EXP_MASK = 0x7F800000


@dataclass(frozen=True)
class TraceReply:
    return_code: int
    value: int
    lane_flags: int
    trace_called: bool


def word(x):
    return type(x) is int and 0 <= x <= 0xFFFFFFFF


def finite(x):
    return word(x) and x & EXP_MASK != EXP_MASK


class NativeTrace1:
    """Exactly lanes=1 through verified old-ABI entry in the new pinned ELF.

    ctypes functions are supplied by the frozen harness after source/ELF and
    address-to-mapping checks, not by resolving arbitrary names here. Standard
    FE preservation and MXCSR controls are checked by the harness separately.
    Negative environment codes mean trace was not called, not executed flags.
    Exceptions are not caught: deadline/resource failures remain hard failures.
    """
    def __init__(self, ctypes_module, trace, environment, diagnostic_environment):
        self.c = ctypes_module
        self.trace = trace
        self.environment = environment
        self.diagnostic_environment = diagnostic_environment
        self.calls = 0

    def __call__(self, op, a, b):
        if op not in (0, 1) or not finite(a) or not finite(b):
            raise ValueError('one finite binary32 Add/Mul operation required')
        for check in (self.environment, self.diagnostic_environment):
            code = check()
            if type(code) is not int or code > 0:
                raise ValueError('unexpected environment ABI result')
            if code < 0:
                return TraceReply(code, 0, 0, False)
        c = self.c
        va, vb = c.c_uint32(a), c.c_uint32(b)
        output, flags = c.c_uint32(0xDEADBEEF), c.c_uint32(0xDEADBEEF)
        self.calls += 1
        code = self.trace(op, c.byref(va), c.byref(vb), c.byref(output),
                          1, c.byref(flags))
        if va.value != a or vb.value != b:
            raise ValueError('native modified input storage')
        return TraceReply(code, output.value, flags.value, True)


class StrictReference:
    """All three inputs pre-admitted; one Mul and conditional Add, mask30 only.

    Returns a fresh plain diagnostic per request. Bad inputs and backend faults
    do not create arithmetic values/flags. A valid fatal pass retains its real
    value/flags, but no failed request proposes an accumulator commit.
    traceCalls is native calls reported by the bound adapter, NOT HW cycles.
    passesCompleted counts valid arithmetic diagnostics, NOT failed ABI calls.
    """
    def __init__(self, primitive):
        if not callable(primitive):
            raise TypeError('bound one-lane primitive required')
        self.primitive = primitive

    def evaluate(self, a, b, acc):
        result = dict(policy=POLICY_ID, status='BAD_INPUT', product=0,
                      productValid=False, mulFlags=0, mulFlagsValid=False,
                      value=0, valueValid=False, addFlags=0, addFlagsValid=False,
                      accCommit=False, passesCompleted=0, traceCalls=0,
                      backendReturn=None)
        if not all(word(x) for x in (a, b, acc)):
            return result
        if not all(finite(x) for x in (a, b, acc)):
            result['status'] = 'NONFINITE_INPUT'
            return result

        def receive(stage, reply):
            # Do not catch exceptions thrown by the service, including timers.
            if not isinstance(reply, TraceReply) or type(reply.trace_called) is not bool:
                result['status'] = stage + '_BACKEND_PROTOCOL'
                return False
            result['traceCalls'] += int(reply.trace_called)
            if type(reply.return_code) is not int:
                result['status'] = stage + '_BACKEND_PROTOCOL'
                return False
            if reply.return_code < 0:
                result['status'] = stage + '_BACKEND_ERROR'
                result['backendReturn'] = reply.return_code
                return False  # value/lane_flags, even sentinels, are INVALID.
            if (not reply.trace_called or reply.return_code > 31 or
                    not word(reply.value) or type(reply.lane_flags) is not int or
                    reply.lane_flags != reply.return_code):
                result['status'] = stage + '_BACKEND_PROTOCOL'
                return False
            return True

        m = self.primitive(1, a, b)
        if not receive('MUL', m):
            return result
        result.update(product=m.value, productValid=True, mulFlags=m.lane_flags,
                      mulFlagsValid=True, passesCompleted=1)
        if m.lane_flags & FATAL_MASK or not finite(m.value):
            result['status'] = 'MUL_FATAL'
            return result
        # Use the registered/delivered product, never original a*b or FMA.
        addition = self.primitive(0, m.value, acc)
        if not receive('ADD', addition):
            return result
        result.update(value=addition.value, valueValid=True,
                      addFlags=addition.lane_flags, addFlagsValid=True,
                      passesCompleted=2)
        if addition.lane_flags & FATAL_MASK or not finite(addition.value):
            result['status'] = 'ADD_FATAL'
            return result
        result.update(status='OK', accCommit=True)
        return result
