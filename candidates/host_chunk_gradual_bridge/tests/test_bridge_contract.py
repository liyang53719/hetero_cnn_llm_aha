"""Pure bridge SPECIFICATION tests; no Scala/RTL/FP arithmetic is executed.

Bank result payloads are deliberate opaque sentinels, not computed FP results.
The separate source guard connects this truth table to the candidate expressions.
"""
from dataclasses import dataclass
from itertools import product
import unittest


@dataclass(frozen=True)
class Request:
    format_only: bool = False
    gradual: bool = False
    policy: int = 0
    multiply: bool = False
    a: tuple = tuple(0x3F800001 + i for i in range(16))
    b: tuple = (0,) * 16


@dataclass(frozen=True)
class Retained:
    physical_policy: int
    raw_policy: int
    tag: int
    client: int = 10


def encode(request, tag=7):
    if request.format_only and request.gradual:
        raise ValueError("mutually exclusive modes")
    if request.format_only and (request.policy != 0 or request.multiply or any(request.b)):
        raise ValueError("noncanonical format")
    if request.gradual and request.policy != 0:
        raise ValueError("noncanonical gradual")
    policy = 4 if request.format_only else 3 if request.gradual else 2 if request.policy == 3 else request.policy
    return {
        "retained": Retained(policy, request.policy, tag),
        "multiply": False if request.format_only else request.multiply,
        "a": request.a + (0,) * 16,
        "b": ((0,) * 16 if request.format_only else request.b) + (0,) * 16,
    }


def project(retained, *, policy, tag, arith_valid, format_valid, values, flags, error=False):
    ordinary = retained.client == 10
    format_only = ordinary and retained.physical_policy == 4
    gradual = ordinary and retained.physical_policy == 3
    arithmetic = retained.client in (6, 7) or (ordinary and not format_only)
    if policy != retained.physical_policy or tag != retained.tag or arith_valid != arithmetic or format_valid:
        return None  # actual adapter quarantines; no completion/refund
    return {
        "format_only": format_only,
        "gradual": gradual,
        "policy": retained.raw_policy,
        "arith_valid": arith_valid,
        "values": values[:16],
        "flags": flags[:16],
        "error": error or (not format_only and retained.raw_policy == 3),
    }


def execute_accepts(result, *, format_only, job_gradual):
    return (result["format_only"] == format_only
            and result["gradual"] == (not format_only and job_gradual)
            and result["policy"] == 0
            and result["arith_valid"] == (not format_only))


def derived_accepts(result, *, job_gradual):
    return (not result["format_only"] and result["gradual"] == job_gradual
            and result["policy"] == 0 and result["arith_valid"])


class ModeBridgeContract(unittest.TestCase):
    def reply(self, retained, **overrides):
        args = dict(policy=retained.physical_policy, tag=retained.tag,
                    arith_valid=retained.physical_policy != 4, format_valid=False,
                    values=tuple(0x00000001 + i * 0x01000101 for i in range(32)),
                    flags=tuple(range(32)), error=False)
        args.update(overrides)
        return project(retained, **args)

    def test_exhaustive_64_mode_policy_multiply_b_combinations(self):
        accepted = 0
        for fmt, gradual, policy, multiply, bzero in product((False, True), (False, True), range(4), (False, True), (False, True)):
            request = Request(fmt, gradual, policy, multiply, b=(0 if bzero else 0x3F800000,) * 16)
            legal = ((not fmt and not gradual) or
                     (gradual and not fmt and policy == 0) or
                     (fmt and not gradual and policy == 0 and not multiply and bzero))
            with self.subTest(fmt=fmt, gradual=gradual, policy=policy, multiply=multiply, bzero=bzero):
                if not legal:
                    with self.assertRaises(ValueError):
                        encode(request)
                else:
                    retained = encode(request)["retained"]
                    self.assertEqual(retained.physical_policy, 4 if fmt else 3 if gradual else 2 if policy == 3 else policy)
                    self.assertEqual(retained.raw_policy, policy)
                    accepted += 1
        self.assertEqual(accepted, 21)

    def test_each_nonzero_b_lane_invalidates_format(self):
        for lane in range(16):
            b = tuple(1 if i == lane else 0 for i in range(16))
            with self.subTest(lane=lane), self.assertRaises(ValueError):
                encode(Request(format_only=True, b=b))

    def test_gradual_both_ops_keep_raw_inputs_and_zero_high16(self):
        a = tuple(0x3F800001 + i for i in range(16))
        b = tuple(0x00000001 + i for i in range(16))
        for multiply in (False, True):
            packet = encode(Request(gradual=True, multiply=multiply, a=a, b=b))
            self.assertEqual(packet["multiply"], multiply)
            self.assertEqual(packet["a"], a + (0,) * 16)
            self.assertEqual(packet["b"], b + (0,) * 16)

    def test_actual_low16_fp32_and_all_five_flags_preserved(self):
        retained = encode(Request(gradual=True))["retained"]
        for flag in range(32):
            values = tuple(0x00000001 + i for i in range(32))
            result = self.reply(retained, values=values, flags=(flag,) * 32)
            self.assertEqual(result["values"], values[:16])
            self.assertEqual(result["flags"], (flag,) * 16)
            self.assertTrue(result["gradual"])
            self.assertTrue(result["arith_valid"])
            self.assertFalse(result["format_only"])
            self.assertFalse(result["error"])
        # UF|NX is opaque real metadata, not zeroed or promoted to an error here.
        self.assertEqual(self.reply(retained, flags=(3,) * 32)["flags"], (3,) * 16)

    def test_format_only_policy4_reserved_flags_invalid(self):
        retained = encode(Request(format_only=True))["retained"]
        values = tuple((0x3F80 + i) << 16 for i in range(32))
        result = self.reply(retained, values=values, flags=(0,) * 32)
        self.assertEqual(result["values"], values[:16])
        self.assertEqual(result["flags"], (0,) * 16)
        self.assertTrue(result["format_only"])
        self.assertFalse(result["gradual"])
        self.assertFalse(result["arith_valid"])

    def test_legacy_policy012_and_raw3_keep_diagnostic_meaning(self):
        for policy in range(4):
            retained = encode(Request(policy=policy))["retained"]
            self.assertEqual(retained.physical_policy, 2 if policy == 3 else policy)
            result = self.reply(retained)
            self.assertEqual(result["policy"], policy)
            self.assertFalse(result["gradual"])
            self.assertFalse(result["format_only"])
            self.assertEqual(result["error"], policy == 3)

    def test_real_bank_errors_forwarded_for_every_mode(self):
        for req in (Request(), Request(gradual=True), Request(format_only=True), Request(policy=3)):
            result = self.reply(encode(req)["retained"], error=True)
            self.assertTrue(result["error"])

    def test_bad_tag_policy_and_flag_validity_do_not_complete(self):
        for req in (Request(), Request(gradual=True), Request(format_only=True), Request(policy=3)):
            retained = encode(req)["retained"]
            self.assertIsNone(self.reply(retained, tag=retained.tag + 1))
            self.assertIsNone(self.reply(retained, policy=(retained.physical_policy + 1) % 8))
            self.assertIsNone(self.reply(retained, arith_valid=retained.physical_policy == 4))
            self.assertIsNone(self.reply(retained, format_valid=True))

    def test_held_response_uses_old_packet_not_next_offer(self):
        gradual = encode(Request(gradual=True), tag=101)["retained"]
        format_packet = encode(Request(format_only=True), tag=102)["retained"]
        # Old result survives arbitrary newer offer. Project has no live input.
        for _ in range(4):
            self.assertTrue(self.reply(gradual)["gradual"])
            self.assertFalse(self.reply(gradual)["format_only"])
        with self.assertRaises(ValueError):
            encode(Request(gradual=True, format_only=True), tag=103)
        self.assertTrue(self.reply(gradual)["gradual"])
        # After old-pop/new-push, new retained policy takes over atomically.
        self.assertTrue(self.reply(format_packet)["format_only"])
        self.assertFalse(self.reply(format_packet)["gradual"])
        self.assertIsNone(self.reply(format_packet, tag=101, policy=3))

    def test_execute_mode_response_checks_positive_and_negative(self):
        for fmt, job_gradual in product((False, True), repeat=2):
            good = dict(format_only=fmt, gradual=not fmt and job_gradual, policy=0, arith_valid=not fmt)
            self.assertTrue(execute_accepts(good, format_only=fmt, job_gradual=job_gradual))
            for field in ("format_only", "gradual", "arith_valid"):
                bad = dict(good, **{field: not good[field]})
                self.assertFalse(execute_accepts(bad, format_only=fmt, job_gradual=job_gradual))
            for policy in (1, 2, 3):
                self.assertFalse(execute_accepts(dict(good, policy=policy), format_only=fmt, job_gradual=job_gradual))

    def test_derived_mode_response_checks_positive_and_negative(self):
        for job_gradual in (False, True):
            good = dict(format_only=False, gradual=job_gradual, policy=0, arith_valid=True)
            self.assertTrue(derived_accepts(good, job_gradual=job_gradual))
            for field in ("format_only", "gradual", "arith_valid"):
                self.assertFalse(derived_accepts(dict(good, **{field: not good[field]}), job_gradual=job_gradual))
            for policy in (1, 2, 3):
                self.assertFalse(derived_accepts(dict(good, policy=policy), job_gradual=job_gradual))


if __name__ == "__main__":
    unittest.main(verbosity=2)
