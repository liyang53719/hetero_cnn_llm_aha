"""Explicit chunk exp routing to the already retained caller-owned Scalar.

The P7 approximation supports gradual underflow; it is not correctly rounded
or bound to production Chisel. Legacy saturation is the unchanged default.
"""
from ...qwen35_35b_exp.scalar import DecayScalar, OPERATION, POLICY
from ..prep.layout import EQUAL_HEADS, GROUPED_35B
from ..rms_owner import ROOT, sha
from .vector import IEEE_POLICY, POLICY_MASKS

LEGACY_EXP = 'existing_ExpNegative_including_abs_ge_80_zero_saturation'
IEEE_EXP = '35b_chunk_' + POLICY
# Separate opt-in; the pre-existing GROUPED_35B contract is not broadened.
EQUAL_HEADS_EXPERIMENTAL_EXP = 'experimental_equal_heads_chunk_' + POLICY
CANDIDATE_POLICIES = (IEEE_EXP, EQUAL_HEADS_EXPERIMENTAL_EXP)

def validate_policy(policy, layout, scalar=None, vector=None):
    if policy not in (LEGACY_EXP, *CANDIDATE_POLICIES):
        raise ValueError('explicit supported chunk exp policy required')
    if policy in CANDIDATE_POLICIES:
        if policy == IEEE_EXP and layout != GROUPED_35B:
            raise ValueError('new chunk exp requires explicit GROUPED_35B')
        if policy == EQUAL_HEADS_EXPERIMENTAL_EXP and layout != EQUAL_HEADS:
            raise ValueError('experimental equal-head chunk exp requires explicit EQUAL_HEADS')
        if scalar is not None and (not isinstance(scalar, DecayScalar) or scalar.enable_ieee_exp is not True):
            raise ValueError('new chunk exp requires enabled caller-owned DecayScalar')
        if vector is not None and vector.exception_policy != IEEE_POLICY:
            raise ValueError('new chunk exp requires explicit finite IEEE Vector policy')
        if (policy == EQUAL_HEADS_EXPERIMENTAL_EXP and vector is not None and
                vector.fatal_mask != POLICY_MASKS[IEEE_POLICY]):
            raise ValueError('experimental equal-head chunk exp requires coherent IEEE mask 28')

def operation(policy):
    if policy not in (LEGACY_EXP, *CANDIDATE_POLICIES):
        raise ValueError('explicit supported chunk exp policy required')
    return OPERATION if policy in CANDIDATE_POLICIES else 'exp_negative'

def identity(policy):
    paths=('candidates/qwen35_35b_exp/scalar.py',
           'candidates/qwen35_gdn_prefill/conv/scalar.py',
           'candidates/qwen35_gdn_prefill/prep/scalar.py')
    extra = {}
    if policy == EQUAL_HEADS_EXPERIMENTAL_EXP:
        paths += ('candidates/qwen35_gdn_prefill/chunk/exp_policy.py',)
        extra = dict(experimental=True, numerical_acceptance=None,
                     full_block_validated=False, rtl_validated=False,
                     admitted_layout='EQUAL_HEADS', required_vector_fatal_mask=28)
    return dict(policy=policy, operation=operation(policy), **extra,
        production_new_opcode_bound=False, correctly_rounded_claim=False,
        torch_bitexact_claim=False,
        compound_sources={p:sha((ROOT/p).read_bytes()) for p in paths} if policy in CANDIDATE_POLICIES else {})
