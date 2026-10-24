"""Cold policy/schema/provenance gates, not arithmetic or native acceptance."""
import inspect
from types import SimpleNamespace
import unittest
from . import exp_policy as ep
from . import model as m
from .vector import IEEE_POLICY, LEGACY_POLICY
from ..prep.layout import EQUAL_HEADS, GROUPED_35B
from ...qwen35_35b_exp.scalar import DecayScalar, OPERATION


class EqualHeadsExpPolicyTests(unittest.TestCase):
    def resources(self):
        # Gate fixtures only. Do not initialize or execute a Scalar/native backend.
        scalar = object.__new__(DecayScalar)
        scalar.enable_ieee_exp = True
        return scalar, SimpleNamespace(exception_policy=IEEE_POLICY, fatal_mask=28)

    def test_named_policy_layouts_remain_disjoint(self):
        s, v = self.resources()
        ep.validate_policy(ep.EQUAL_HEADS_EXPERIMENTAL_EXP, EQUAL_HEADS)
        with self.assertRaises(ValueError):
            m.ChunkOwner(None, None, exp_policy=ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
        ep.validate_policy(ep.EQUAL_HEADS_EXPERIMENTAL_EXP, EQUAL_HEADS, s, v)
        ep.validate_policy(ep.IEEE_EXP, GROUPED_35B, s, v)
        for policy, layout in ((ep.IEEE_EXP, EQUAL_HEADS),
                               (ep.EQUAL_HEADS_EXPERIMENTAL_EXP, GROUPED_35B)):
            with self.assertRaises(ValueError):
                ep.validate_policy(policy, layout, s, v)
        with self.assertRaises(ValueError):
            ep.validate_policy('automatic', EQUAL_HEADS, s, v)
        for helper in (ep.operation, ep.identity):
            with self.assertRaises(ValueError):
                helper('automatic')

    def test_enabled_decay_and_explicit_coherent_28_required(self):
        s, v = self.resources()
        for scalar in (object(), SimpleNamespace(enable_ieee_exp=True)):
            with self.assertRaises(ValueError):
                ep.validate_policy(ep.EQUAL_HEADS_EXPERIMENTAL_EXP, EQUAL_HEADS, scalar, v)
        s.enable_ieee_exp = False
        with self.assertRaises(ValueError):
            ep.validate_policy(ep.EQUAL_HEADS_EXPERIMENTAL_EXP, EQUAL_HEADS, s, v)
        s.enable_ieee_exp = True
        for vector in (SimpleNamespace(exception_policy=LEGACY_POLICY, fatal_mask=30),
                       SimpleNamespace(exception_policy=IEEE_POLICY, fatal_mask=30)):
            with self.assertRaises(ValueError):
                ep.validate_policy(ep.EQUAL_HEADS_EXPERIMENTAL_EXP, EQUAL_HEADS, s, vector)

    def test_default_and_original_operation_selection(self):
        self.assertEqual(inspect.signature(m.ChunkOwner).parameters['exp_policy'].default, ep.LEGACY_EXP)
        self.assertEqual(inspect.signature(m.ChunkJob).parameters['exp_policy'].default, ep.LEGACY_EXP)
        self.assertEqual(ep.operation(ep.LEGACY_EXP), 'exp_negative')
        self.assertEqual(ep.operation(ep.IEEE_EXP), OPERATION)
        self.assertEqual(ep.operation(ep.EQUAL_HEADS_EXPERIMENTAL_EXP), OPERATION)

    def test_identity_pins_helper_and_declines_acceptance(self):
        identity = ep.identity(ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
        self.assertTrue(identity['experimental'])
        self.assertIsNone(identity['numerical_acceptance'])
        for field in ('production_new_opcode_bound', 'correctly_rounded_claim',
                      'torch_bitexact_claim', 'full_block_validated', 'rtl_validated'):
            self.assertIs(identity[field], False)
        self.assertEqual(identity['required_vector_fatal_mask'], 28)
        helper = 'candidates/qwen35_gdn_prefill/chunk/exp_policy.py'
        self.assertEqual(identity['compound_sources'][helper], ep.sha((ep.ROOT / helper).read_bytes()))
        # Source identity used by TypedChunkDriver's preterminal comparison retains it.
        owner_identity = m.source_identity(IEEE_POLICY, EQUAL_HEADS,
                                          exp_policy=ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
        self.assertEqual(owner_identity['exp_identity'], identity)


if __name__ == '__main__':
    unittest.main()
