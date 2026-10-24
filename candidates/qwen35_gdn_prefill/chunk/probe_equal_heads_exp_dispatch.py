"""Explicit tiny original-owner Scalar dispatch probe; never builds a backend.

Caller must provide a verified existing R2 library and an external resource cap.
The real Vector16 is constructed for policy admission but no Vector arithmetic
is issued. This is not a chunk, full-block, upstream, numerical or RTL pass.
"""
from . import exp_policy as ep
from .model import ChunkOwner
from .vector import Vector16, IEEE_POLICY
from ...qwen35_35b_exp.scalar import DecayScalar, OPERATION


def probe(library):
    sources_before = ep.identity(ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
    scalar = DecayScalar(enable_softplus=True, enable_ieee_exp=True)
    vector = Vector16(library, exception_policy=IEEE_POLICY,
                      arithmetic_backend='finite_mul_tininess_r2')
    owner = ChunkOwner(scalar, vector, exp_policy=ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
    # No monkeypatch, hooks, surrogate owners or alternate arithmetic injection.
    assert owner._exp.__func__ is ChunkOwner._exp
    assert scalar.op.__func__ is DecayScalar.op
    assert scalar._evaluate_exp.__func__ is DecayScalar._evaluate_exp
    sid, vid = id(scalar), id(vector)
    native_before = (dict(vector.lane_ops), dict(vector.calls))
    assert scalar.acquire(owner)
    rows = []
    try:
        for raw, expected in ((0xc2a00000, 0x05bfecba),
                              (0xc2aeac50, 0x007fffe6),
                              (0xc2b72752, 0x0001d7fd),
                              (0xc2cff1b4, 1), (0xc2cff1b5, 0)):
            result = owner._exp(raw)
            assert result == expected, (hex(raw), hex(result), hex(expected))
            rows.append(dict(input_word=raw, output_word=result))
        assert scalar.calls[OPERATION] == len(rows)
        assert scalar.calls['exp_negative'] == 0
        assert owner.exp_stats['saturated_abs_ge_80'] == 0
    finally:
        scalar.release(owner)
    assert (id(owner.scalar), id(owner.vector)) == (sid, vid)
    assert native_before == (dict(vector.lane_ops), dict(vector.calls))
    assert sources_before == ep.identity(ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
    return dict(scope='TINY_ORIGINAL_CHUNK_OWNER_SCALAR_DISPATCH_ONLY', rows=rows,
                exp_stats=dict(owner.exp_stats), scalar_calls=dict(scalar.calls),
                decay_internal_calls=dict(scalar.decay_internal_calls),
                vector_arithmetic_executed=False, original_owner_executed=True,
                full_chunk_executed=False, full_block_executed=False,
                source_identity=sources_before, numerical_acceptance=None,
                production_new_opcode_bound=False, rtl_validated=False)
