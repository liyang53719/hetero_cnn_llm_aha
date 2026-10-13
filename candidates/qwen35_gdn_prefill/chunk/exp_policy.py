"""Explicit chunk exp routing to the already retained caller-owned Scalar.

The P7 approximation supports gradual underflow; it is not correctly rounded
or bound to production Chisel. Legacy saturation is the unchanged default.
"""
from pathlib import Path
from ...qwen35_35b_exp.scalar import DecayScalar, OPERATION, POLICY
from ..prep.layout import GROUPED_35B
from ..rms_owner import ROOT, sha
from .vector import IEEE_POLICY

LEGACY_EXP = 'existing_ExpNegative_including_abs_ge_80_zero_saturation'
IEEE_EXP = '35b_chunk_' + POLICY

def validate_policy(policy, layout, scalar=None, vector=None):
    if policy not in (LEGACY_EXP, IEEE_EXP):
        raise ValueError('explicit supported chunk exp policy required')
    if policy == IEEE_EXP:
        if layout != GROUPED_35B:
            raise ValueError('new chunk exp requires explicit GROUPED_35B')
        if scalar is not None and (not isinstance(scalar, DecayScalar) or scalar.enable_ieee_exp is not True):
            raise ValueError('new chunk exp requires enabled caller-owned DecayScalar')
        if vector is not None and vector.exception_policy != IEEE_POLICY:
            raise ValueError('new chunk exp requires explicit finite IEEE Vector policy')

def operation(policy):
    return OPERATION if policy == IEEE_EXP else 'exp_negative'

def identity(policy):
    paths=('candidates/qwen35_35b_exp/scalar.py',
           'candidates/qwen35_gdn_prefill/conv/scalar.py',
           'candidates/qwen35_gdn_prefill/prep/scalar.py')
    return dict(policy=policy, operation=operation(policy),
        production_new_opcode_bound=False, correctly_rounded_claim=False,
        torch_bitexact_claim=False,
        compound_sources={p:sha((ROOT/p).read_bytes()) for p in paths} if policy==IEEE_EXP else {})
