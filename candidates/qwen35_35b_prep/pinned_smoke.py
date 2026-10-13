"""Explicit fixed-runtime official Prep smoke; not part of Torch-free CI discovery."""
import unittest
import json
import struct
import numpy as np
from .test_reference import inputs,bf16
from . import reference as r

class PinnedNumericalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        cls.torch = torch
        cls.data = inputs(3)
        conv, ab, alog, bias = cls.data
        # Include exact signed-zero/subnormal V boundaries in both head groups.
        bits = np.frombuffer(conv, "<u2").copy().reshape(3, r.CONV)
        bits[0, 4096:4100] = [0, 0x8000, 1, 0x8001]
        bits[1, -4:] = [0x3f81, 0xbf82, 0x8000, 1]
        cls.data = bits.tobytes(), ab, alog, bias
        cls.raw, cls.identity = r.native_prep(*cls.data, 3)
        cls.output = np.frombuffer(cls.raw, "<u4").reshape(3, r.CORE)

    def test_official_fullshape_repeat_interleave_and_value_widen(self):
        output = self.output
        for offset in (0, 4096):
            heads = output[:, offset:offset + 4096].reshape(3, 32, 128)
            np.testing.assert_array_equal(heads[:, ::2], heads[:, 1::2])
            self.assertFalse(np.array_equal(heads[:, 1], heads[:, 2]))
        conv = np.frombuffer(self.data[0], "<u2").reshape(3, 8192)
        np.testing.assert_array_equal(output[:, 8192:12288], conv[:, 4096:].astype("<u4") << 16)
        self.assertTrue(np.all(output[:, 12288:].reshape(3, 32, 16)[..., 2:] == 0))

    def test_chunk_fp32_l2norm_then_scale_and_bf16_beta_match_explicit_control(self):
        torch = self.torch
        conv = torch.frombuffer(bytearray(self.data[0]), dtype=torch.bfloat16).reshape(1, 3, 8192)
        q, k, _ = torch.split(conv, [2048, 2048, 4096], dim=-1)
        for role, tensor in enumerate((q, k)):
            x = tensor.reshape(1, 3, 16, 128).repeat_interleave(2, dim=2).transpose(1, 2).float().contiguous()
            norm = x * torch.rsqrt((x * x).sum(-1, keepdim=True) + 1e-6)
            if role == 0:
                norm = norm * (128 ** -.5)
            expected = norm.transpose(1, 2).contiguous().numpy().reshape(3, 4096).view("<u4")
            np.testing.assert_array_equal(self.output[:, role * 4096:(role + 1) * 4096], expected)
        ab = torch.frombuffer(bytearray(self.data[1]), dtype=torch.bfloat16).reshape(3, 64)
        gates = self.output[:, 12288:].reshape(3, 32, 16)
        beta = ab[:, 32:].sigmoid().float().numpy().view("<u4")
        np.testing.assert_array_equal(gates[..., 1], beta)
        self.assertTrue(np.any(beta != ab[:, 32:].float().sigmoid().numpy().view("<u4")))
        alog = torch.frombuffer(bytearray(self.data[2]), dtype=torch.float32)
        bias = torch.frombuffer(bytearray(self.data[3]), dtype=torch.bfloat16)
        expected_g = -alog.float().exp() * torch.nn.functional.softplus(ab[:, :32].float() + bias)
        np.testing.assert_array_equal(gates[..., 0], expected_g.numpy().view("<u4"))

    def test_original_alog_low_bits_affect_g_and_m1_is_token_independent(self):
        conv, ab, alog, bias = self.data
        original, identity = r.native_prep(conv[:8192 * 2], ab[:64 * 2], alog, bias, 1)
        self.assertEqual(original, self.raw[:12800 * 4])
        rounded = np.frombuffer(alog, "<u4").copy() & np.uint32(0xffff0000)
        modified, _ = r.native_prep(conv[:8192 * 2], ab[:64 * 2], rounded.tobytes(), bias, 1)
        self.assertNotEqual(r._roles(original, 1)["g"], r._roles(modified, 1)["g"])
        for name in ("query", "key", "value", "beta", "gate_padding"):
            self.assertEqual(r._roles(original, 1)[name], r._roles(modified, 1)[name])
        self.assertEqual(identity["a_log_sha256"], r.sha(alog))

    def test_identity_records_pins_runtime_hashes_and_no_acceptance(self):
        identity = self.identity
        self.assertEqual(identity["source"]["source_sha256"], r.SOURCE_SHA)
        self.assertEqual(identity["runtime"]["torch_version"], "2.10.0+cpu")
        self.assertEqual(identity["runtime"]["cpu_capability"], "DEFAULT")
        self.assertEqual(identity["output_sha256"], r.sha(self.raw))
        self.assertEqual(identity["conv_sha256"], r.sha(self.data[0]))
        self.assertEqual(identity["output_shape"], [3, 12800])
        self.assertFalse(identity["scalar_or_owner_called"])
        self.assertFalse(identity["actual_prep_output_consumed"])
        self.assertIsNone(r.diagnose(self.raw, self.raw, 3, identity=identity)["passed"])
        json.dumps(identity, allow_nan=False)

    def test_official_finite_gate_below_minus80_is_not_clamped_or_rejected(self):
        alog = np.full(32, 6, dtype="<f4").tobytes()
        raw, identity = r.native_prep(bytes(8192 * 2), bytes(64 * 2), alog, bytes(32 * 2), 1)
        g = np.frombuffer(r._roles(raw, 1)["g"], "<f4")
        self.assertTrue(np.isfinite(g).all())
        self.assertTrue(np.all(g < -80))
        self.assertEqual(identity["a_log_sha256"], r.sha(alog))
        self.assertIsNone(r.diagnose(raw, raw, 1, identity=identity)["passed"])


if __name__ == "__main__":
    unittest.main()
