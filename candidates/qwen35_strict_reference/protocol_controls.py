"""Protocol MOCK controls only: not a numeric FP32 oracle or native/HW test.

Writing this file does not run controls. A separately authorized harness may
call run_controls(module) with the strict_reference module already supplied.
"""


def run_controls(module):
    """Run 13 grouped assertion controls against explicit scripted MOCKs."""
    R = module.TraceReply
    A, B, ACC = 0x3F800001, 0x3F800002, 0xBF800000
    PRODUCT, VALUE = 0x3F800003, 0x34C00000
    groups, cases = [], 0

    class MockTrace:
        """Return supplied TraceReply fixtures, deliberate faults, or exceptions."""

        def __init__(self, replies):
            self.replies = list(replies)
            self.calls = []

        def __call__(self, op, a, b):
            self.calls.append((op, a, b))
            assert self.replies, 'unexpected extra MOCK service call'
            reply = self.replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return reply

    def invoke(reference, a=A, b=B, acc=ACC):
        nonlocal cases
        cases += 1
        return reference.evaluate(a, b, acc)

    def exercise(replies, a=A, b=B, acc=ACC):
        mock = MockTrace(replies)
        result = invoke(module.StrictReference(mock), a, b, acc)
        assert not mock.replies, 'expected MOCK service call did not occur'
        assert result['policy'] == module.POLICY_ID
        return result, mock.calls

    def blank(result):
        for key in ('product', 'mulFlags', 'value', 'addFlags', 'passesCompleted'):
            assert type(result[key]) is int and result[key] == 0, key
        for key in ('productValid', 'mulFlagsValid', 'valueValid',
                    'addFlagsValid', 'accCommit'):
            assert result[key] is False, key

    def mul_only(result, flags=1):
        assert result['product'] == PRODUCT and result['productValid'] is True
        assert result['mulFlags'] == flags and result['mulFlagsValid'] is True
        assert result['value'] == 0 and result['valueValid'] is False
        assert result['addFlags'] == 0 and result['addFlagsValid'] is False
        assert result['passesCompleted'] == 1 and result['accCommit'] is False

    # 1. Every input is admitted before either pass, including the accumulator.
    for slot in range(3):
        for bad in (False, True, -1, 0x100000000, 1.0, '0', None):
            inputs = [A, B, ACC]
            inputs[slot] = bad
            result, calls = exercise([], *inputs)
            assert result['status'] == 'BAD_INPUT' and calls == []
            assert result['traceCalls'] == 0 and result['backendReturn'] is None
            blank(result)
    groups.append('all-input word preadmission')

    # 2. qNaN, sNaN and both infinities are rejected in all three positions.
    for slot in range(3):
        for bad in (0x7FC00001, 0x7F800001, 0x7F800000, 0xFF800000):
            inputs = [A, B, ACC]
            inputs[slot] = bad
            result, calls = exercise([], *inputs)
            assert result['status'] == 'NONFINITE_INPUT' and calls == []
            assert result['traceCalls'] == 0 and result['backendReturn'] is None
            blank(result)
    groups.append('all-input finite preadmission')

    # 3. Negative ABI results never promote sentinel outputs to diagnostics.
    for reply in (R(-7, 0xDEADBEEF, 0xDEADBEEF, True),
                  R(-8, object(), object(), True)):
        result, calls = exercise([reply])
        assert result['status'] == 'MUL_BACKEND_ERROR'
        assert result['backendReturn'] == reply.return_code
        assert result['traceCalls'] == 1 and calls == [(1, A, B)]
        blank(result)
    groups.append('negative Mul ABI')

    # 4. Environment rejection means an adapter call, but no native trace call.
    for stage in ('MUL', 'ADD'):
        replies = [] if stage == 'MUL' else [R(1, PRODUCT, 1, True)]
        replies.append(R(-9, 0xDEADBEEF, 0xDEADBEEF, False))
        result, calls = exercise(replies)
        assert result['status'] == stage + '_BACKEND_ERROR'
        assert result['backendReturn'] == -9
        assert result['traceCalls'] == (0 if stage == 'MUL' else 1)
        assert len(calls) == (1 if stage == 'MUL' else 2)
        blank(result) if stage == 'MUL' else mul_only(result)
    groups.append('negative environment without trace')

    # 5. A failed Add preserves valid Mul diagnostics, never Add or commit.
    result, calls = exercise([R(1, PRODUCT, 1, True),
                              R(-10, 0xDEADBEEF, 0xDEADBEEF, True)])
    assert result['status'] == 'ADD_BACKEND_ERROR'
    assert result['backendReturn'] == -10 and result['traceCalls'] == 2
    assert calls == [(1, A, B), (0, PRODUCT, ACC)]
    mul_only(result)
    groups.append('negative Add preserves Mul')

    # 6-7. Malformed nonnegative replies at either stage are protocol failures.
    malformed = [
        (R(32, VALUE, 32, True), 1),
        (R(0, VALUE, 1, True), 1),
        (R(0, -1, 0, True), 1),
        (R(0, 0x100000000, 0, True), 1),
        (R(0, True, 0, True), 1),
        (R(0, 1.0, 0, True), 1),
        (R(0, VALUE, 0, False), 0),
        (R(True, VALUE, 1, True), 1),
        (R(0.0, VALUE, 0, True), 1),
        (R(1, VALUE, True, True), 1),
        (R(0, VALUE, 0.0, True), 1),
        (R(0, VALUE, 0, 1), 0),
        (None, 0),
    ]
    for stage in ('MUL', 'ADD'):
        for reply, traces in malformed:
            prefix = [] if stage == 'MUL' else [R(1, PRODUCT, 1, True)]
            result, calls = exercise(prefix + [reply])
            assert result['status'] == stage + '_BACKEND_PROTOCOL'
            assert result['backendReturn'] is None
            assert result['traceCalls'] == traces + len(prefix)
            assert len(calls) == 1 + len(prefix)
            blank(result) if stage == 'MUL' else mul_only(result)
        groups.append('malformed ' + stage + ' reply')

    # 8. Every fatal flag bit and nonfinite delivered product suppress Add.
    for flags, product in [(f, PRODUCT) for f in (2, 4, 8, 16, 30, 31)] + [
            (0, 0x7F800000), (0, 0x7FC00001)]:
        result, calls = exercise([R(flags, product, flags, True)])
        assert result['status'] == 'MUL_FATAL' and calls == [(1, A, B)]
        assert result['product'] == product and result['productValid'] is True
        assert result['mulFlags'] == flags and result['mulFlagsValid'] is True
        assert result['value'] == 0 and result['valueValid'] is False
        assert result['addFlags'] == 0 and result['addFlagsValid'] is False
        assert result['passesCompleted'] == 1 and result['traceCalls'] == 1
        assert result['accCommit'] is False and result['backendReturn'] is None
    groups.append('fatal Mul suppresses Add')

    # 9. Valid fatal Add diagnostics remain available without a proposed commit.
    for flags, value in [(f, VALUE) for f in (2, 4, 8, 16, 30, 31)] + [
            (0, 0xFF800000), (0, 0x7F800001)]:
        result, calls = exercise([R(1, PRODUCT, 1, True),
                                  R(flags, value, flags, True)])
        assert result['status'] == 'ADD_FATAL'
        assert result['product'] == PRODUCT and result['productValid'] is True
        assert result['mulFlags'] == 1 and result['mulFlagsValid'] is True
        assert result['value'] == value and result['valueValid'] is True
        assert result['addFlags'] == flags and result['addFlagsValid'] is True
        assert result['passesCompleted'] == 2 and result['traceCalls'] == 2
        assert result['accCommit'] is False and result['backendReturn'] is None
        assert calls == [(1, A, B), (0, PRODUCT, ACC)]
    groups.append('fatal Add retains diagnostics')

    # 10. NX alone is permitted on either or both passes.
    for mul_flags, add_flags in ((0, 0), (1, 0), (0, 1), (1, 1)):
        result, calls = exercise([R(mul_flags, PRODUCT, mul_flags, True),
                                  R(add_flags, VALUE, add_flags, True)])
        assert result['status'] == 'OK' and result['accCommit'] is True
        assert result['product'] == PRODUCT and result['value'] == VALUE
        assert result['mulFlags'] == mul_flags and result['addFlags'] == add_flags
        assert all(result[k] is True for k in (
            'productValid', 'mulFlagsValid', 'valueValid', 'addFlagsValid'))
        assert result['passesCompleted'] == 2 and result['traceCalls'] == 2
        assert result['backendReturn'] is None and len(calls) == 2
    groups.append('NX-only success')

    # 11. The delivered rounded-word fixture, not a recomputation/FMA, feeds Add.
    # These fixtures check wiring only; they do not establish FP32 arithmetic.
    for delivered in (PRODUCT, 0x3F000001):
        result, calls = exercise([R(1, delivered, 1, True), R(0, VALUE, 0, True)])
        assert calls == [(1, A, B), (0, delivered, ACC)]
        assert result['product'] == delivered and result['status'] == 'OK'
    groups.append('exact Mul-then-Add operand order')

    # 12. Reusing a wrapper never leaks prior outputs, flags, counts or errors.
    mock = MockTrace([R(1, PRODUCT, 1, True), R(1, VALUE, 1, True),
                      R(-11, 0xDEADBEEF, 0xDEADBEEF, True)])
    reference = module.StrictReference(mock)
    first = invoke(reference)
    saved = dict(first)
    failed = invoke(reference)
    rejected = invoke(reference, True, B, ACC)
    assert first['status'] == 'OK' and first['accCommit'] is True
    assert failed['status'] == 'MUL_BACKEND_ERROR'
    assert failed['backendReturn'] == -11 and failed['traceCalls'] == 1
    assert rejected['status'] == 'BAD_INPUT'
    assert rejected['backendReturn'] is None and rejected['traceCalls'] == 0
    blank(failed)
    blank(rejected)
    assert first is not failed and failed is not rejected and first is not rejected
    assert first == saved and not mock.replies and len(mock.calls) == 3
    groups.append('fresh per-request diagnostics')

    # 13. Backend exceptions, especially deadline failures, propagate unchanged.
    for error_type in (RuntimeError, TimeoutError):
        for stage in ('MUL', 'ADD'):
            fault = error_type('intentional MOCK failure')
            prefix = [] if stage == 'MUL' else [R(1, PRODUCT, 1, True)]
            mock = MockTrace(prefix + [fault])
            try:
                invoke(module.StrictReference(mock))
            except BaseException as actual:
                assert actual is fault, 'exception was replaced or swallowed'
            else:
                raise AssertionError('backend exception was swallowed')
            assert not mock.replies and len(mock.calls) == 1 + len(prefix)
    groups.append('exceptions propagate unchanged')

    assert len(groups) == 13
    return {'mode': 'PROTOCOL_MOCK_ONLY', 'groups': len(groups), 'cases': cases}
