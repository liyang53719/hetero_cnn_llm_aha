"""Frozen recurrence tests; these do not stand in for RTL or Host execution."""
import numpy as np
import pytest
from heteronpu.qwen35_gdn_recurrent_fp32 import recurrent_step, exp_negative_recipe, expand_bf16
from heteronpu.qwen35_gdn_numpy_reference import recurrent_gated_delta_rule


def test_fp32_state_and_bf16_output_with_independent_fp64():
    rng = np.random.default_rng(3509)
    q = rng.normal(0, .02, (2,128)).astype(np.float32)
    k = rng.normal(0, .03, (2,128)).astype(np.float32)
    v = rng.normal(0, .2, (2,128)).astype(np.float32)
    gates = np.array([[-.7,.8],[-.08,.1]],np.float32)
    out, state, core = recurrent_step(q,k,v,gates)
    fpout, fpstate = recurrent_gated_delta_rule(q[None,None]*np.sqrt(128),k[None,None],v[None,None],gates[None,None,:,0],gates[None,None,:,1],normalize_qk=False)
    assert out.dtype == np.dtype('<u2') and state.dtype == np.float32
    np.testing.assert_allclose(state,fpstate[0],atol=1e-4,rtol=1e-4)
    np.testing.assert_allclose(core,fpout[0,0],atol=1e-4,rtol=1e-4)
    carried_out, carried, _ = recurrent_step(q,k,v,gates,state)
    assert not np.array_equal(out,carried_out) and np.max(np.abs(carried-state)) > 0


def test_preserves_input_state_and_real_subnormals():
    # Exact minimum-subnormal states must not be truncated through BF16.
    smallest=np.array([1],dtype=np.uint32).view(np.float32)[0]
    state=np.full((1,16,32),smallest,dtype=np.float32)
    original=state.copy()
    q=np.full((1,16),.125,np.float32);k=np.zeros((1,16),np.float32);v=np.zeros((1,32),np.float32)
    out, result, _=recurrent_step(q,k,v,np.array([[0.,0.]],np.float32),state)
    np.testing.assert_array_equal(state.view(np.uint32),original.view(np.uint32))
    np.testing.assert_array_equal(result.view(np.uint32),original.view(np.uint32))
    assert not expand_bf16(out).any()


@pytest.mark.parametrize('g', [-80., -100., 0.1, np.inf, np.nan])
def test_rejects_exp_domain_instead_of_saturating_state(g):
    with pytest.raises(ValueError): exp_negative_recipe(np.array([g],np.float32))


def test_signed_zero_exp_and_beta_validation():
    np.testing.assert_array_equal(exp_negative_recipe(np.array([-0.,0.],np.float32)),np.ones(2,np.float32))
    q=np.ones((1,16),np.float32);v=np.ones((1,32),np.float32)
    for b in [-.01,1.01,float('nan')]:
        with pytest.raises(ValueError): recurrent_step(q,q,v,np.array([[0.,b]],np.float32))
