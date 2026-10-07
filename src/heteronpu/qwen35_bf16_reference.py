"""Independent NumPy producer-rounded reference for pinned 0.8B attention3.

BF16 arrays are losslessly represented by float32 values, never FP32 activations.
NumPy FP32 GEMM/reductions have a different backend/order from native torch.
This oracle does NOT promise backend bit identity or define hardware reduction
order. Every materialized producer is retained; no native intermediate injection.
"""
from __future__ import annotations

import numpy as np

from .model_geometry import require


def bf16(value):
    """Finite FP32 -> BF16 round-to-nearest, ties-to-even, preserving signed zero."""
    x = np.asarray(value, dtype=np.float32)
    require(np.isfinite(x).all(), "BF16 reference rejects nonfinite conversion")
    bits = x.view(np.uint32)
    rounded = (bits + np.uint32(0x7FFF) + ((bits >> 16) & 1)) & np.uint32(0xFFFF0000)
    out = rounded.view(np.float32)
    require(np.isfinite(out).all(), "BF16 reference rejects finite overflow")
    return out


def require_bf16(value, name):
    x = np.asarray(value)
    require(x.dtype == np.float32 and np.isfinite(x).all(), name + " must be finite decoded BF16")
    require(np.array_equal(x.view(np.uint32) & 0xFFFF, np.zeros(x.shape, dtype=np.uint32)), name + " has unrounded FP32 bits")
    return x


def producer_compare(actual, expected, *, block=False):
    """Pre-existing spec/numerical_contract.md limits, not fitted to this run."""
    a, b = np.asarray(actual, dtype=np.float64), np.asarray(expected, dtype=np.float64)
    require(a.shape == b.shape and a.size > 0, "producer shape mismatch/empty")
    require(np.isfinite(a).all() and np.isfinite(b).all(), "nonfinite producer")
    error = np.abs(a-b)
    maximum, mean = (0.05, 0.01) if block else (0.03125, 0.005)
    return {"elements": a.size, "max_abs_error": float(error.max()), "mean_abs_error": float(error.mean()),
            "max_abs_limit": maximum, "mean_abs_limit": mean,
            "mismatches_over_max": int(np.count_nonzero(error > maximum)),
            "bit_different": int(np.count_nonzero(np.asarray(actual, dtype=np.float32).view(np.uint32) != np.asarray(expected, dtype=np.float32).view(np.uint32))),
            "numerically_different": int(np.count_nonzero(a != b)),
            "pass": bool(error.max() <= maximum and error.mean() <= mean)}


def forward(x, weights, past=None, *, position_start=0):
    """Complete fixed B1/M128 layer, all official BF16 materialization points.

    FP32 accumulation is NumPy float32 matmul/sum; no BF16 running sum. The
    reduction tree is intentionally named rather than assumed equal to torch.
    Source cos/sin are independently recomputed in FP32, then stored as BF16.
    """
    x = require_bf16(x, "input")
    require(x.shape == (1, 128, 1024), "only B1 M128 H1024 supported")
    require(type(position_start) is int and position_start in (0, 128), "only cold/carried M128 positions supported")
    shapes = {"input_layernorm.weight": (1024,), "post_attention_layernorm.weight": (1024,),
              "self_attn.q_norm.weight": (256,), "self_attn.k_norm.weight": (256,),
              "self_attn.q_proj.weight": (4096, 1024), "self_attn.k_proj.weight": (512, 1024),
              "self_attn.v_proj.weight": (512, 1024), "self_attn.o_proj.weight": (1024, 2048),
              "mlp.gate_proj.weight": (3584, 1024), "mlp.up_proj.weight": (3584, 1024),
              "mlp.down_proj.weight": (1024, 3584)}
    require(set(weights) == set(shapes), "unsupported/missing layer3 parameter")
    w = {k: require_bf16(v, k) for k, v in weights.items()}
    require(all(w[k].shape == s for k,s in shapes.items()), "unsupported weight geometry")
    require((past is None) == (position_start == 0), "position and cache mismatch")
    if past is not None:
        require(len(past) == 2, "invalid past cache")
        past = tuple(require_bf16(v, "past") for v in past)
        require(all(v.shape == (1,2,128,256) for v in past), "only past128 supported")
    trace, counters = [], {}
    def save(path, op, y, dtype="bfloat16"):
        y = np.asarray(y, dtype=np.float32)
        if dtype == "bfloat16": y = bf16(y)
        key = (path, op); i = counters.get(key, 0); counters[key] = i+1
        trace.append({"key": f"{path}|{op}|{i}", "dtype": dtype, "value": y.copy()})
        return y
    def norm(y, path):
        square = save(path,"aten.pow.Tensor_Scalar",y*y,"float32")
        mean = save(path,"aten.mean.dim",np.mean(square,axis=-1,keepdims=True,dtype=np.float32),"float32")
        mean = save(path,"aten.add.Tensor",mean+np.float32(1e-6),"float32")
        inv = save(path,"aten.rsqrt.default",np.float32(1)/np.sqrt(mean),"float32")
        n = save(path,"aten.mul.Tensor",y*inv,"float32")
        scale = save(path,"aten.add.Tensor",np.float32(1)+w[path+".weight"],"float32")
        n = save(path,"aten.mul.Tensor",n*scale,"float32")
        return save(path,"cast_bf16",n)
    def linear(y,path):
        return save(path,"aten.linear.default",np.matmul(y,w[path+".weight"].T,dtype=np.float32))
    n = norm(x,"input_layernorm")
    packed = linear(n,"self_attn.q_proj").reshape(1,128,8,512)
    q, gate = packed[...,:256],packed[...,256:].reshape(1,128,2048)
    q = norm(q,"self_attn.q_norm").transpose(0,2,1,3)
    k = norm(linear(n,"self_attn.k_proj").reshape(1,128,2,256),"self_attn.k_norm").transpose(0,2,1,3)
    v = linear(n,"self_attn.v_proj").reshape(1,128,2,256).transpose(0,2,1,3)
    exponent = np.arange(0,64,2,dtype=np.float32)/np.float32(64)
    inv = np.float32(1)/np.power(np.float32(10000000),exponent)
    freq = np.arange(position_start,position_start+128,dtype=np.float32)[:,None]*inv
    cos,sin = bf16(np.tile(np.cos(freq),(1,2)))[None,None],bf16(np.tile(np.sin(freq),(1,2)))[None,None]
    def rope(y):
        rot = y[...,:64]; swapped = np.concatenate((-rot[...,32:],rot[...,:32]),axis=-1)
        a = save("self_attn","aten.mul.Tensor",rot*cos)
        b = save("self_attn","aten.mul.Tensor",swapped*sin)
        r = save("self_attn","aten.add.Tensor",a+b)
        return np.concatenate((r,y[...,64:]),axis=-1)
    q,k = rope(q),rope(k)
    if past is not None: k,v = np.concatenate((past[0],k),axis=2),np.concatenate((past[1],v),axis=2)
    logits = save("self_attn","aten.matmul.default",np.matmul(q,np.repeat(k,4,axis=1).swapaxes(-1,-2),dtype=np.float32))
    logits = save("self_attn","aten.mul.Tensor",logits*np.float32(1/16))
    allowed = np.arange(k.shape[2])[None,:] <= np.arange(position_start,position_start+128)[:,None]
    mask = np.where(allowed,0.,np.float32(-3.3895313892515355e38)).astype(np.float32)[None,None]
    logits = save("self_attn","aten.add.Tensor",logits+mask)
    exp = np.exp(logits-np.max(logits,axis=-1,keepdims=True))
    p = save("self_attn","aten.softmax.int",exp/np.sum(exp,axis=-1,keepdims=True,dtype=np.float32),"float32")
    p = save("self_attn","cast_bf16",p)
    attention = save("self_attn","aten.matmul.default",np.matmul(p,np.repeat(v,4,axis=1),dtype=np.float32))
    attention = attention.transpose(0,2,1,3).reshape(1,128,2048)
    sig = save("self_attn","aten.sigmoid.default",np.float32(1)/(np.float32(1)+np.exp(-gate)))
    gated = save("self_attn","aten.mul.Tensor",attention*sig)
    o = linear(gated,"self_attn.o_proj")
    residual = save("","aten.add.Tensor",x+o)
    n = norm(residual,"post_attention_layernorm")
    g = linear(n,"mlp.gate_proj")
    g = save("mlp.act_fn","aten.silu.default",g/(np.float32(1)+np.exp(-g)))
    u = linear(n,"mlp.up_proj")
    z = save("mlp","aten.mul.Tensor",g*u)
    out = save("","aten.add.Tensor",residual+linear(z,"mlp.down_proj"))
    return out,(k,v),trace,{"cos":cos[:,0],"sin":sin[:,0],"mask":mask}


def local_gemm_bound(actual, left, right):
    """Conditional FP32 summation bound for IDENTICAL native producer operands.

    Diagnostic only: does not inject values into or accept the independent graph.
    BF16 products are exact in FP32 absent under/overflow. gamma_K bounds FP32
    accumulation; the final BF16 half-bin is added. FP64 dot/absolute-dot error
    is conservatively included too. This does not certify an unknown backend.
    """
    a = require_bf16(left,"left").astype(np.float64)
    b = require_bf16(right,"right").astype(np.float64)
    y = require_bf16(actual,"actual").astype(np.float64)
    require(a.ndim >= 2 and b.ndim >= 2 and a.shape[-1] == b.shape[-2], "local GEMM shape mismatch")
    nonzero_a,nonzero_b = np.abs(a[a != 0]),np.abs(b[b != 0])
    if nonzero_a.size and nonzero_b.size:
        require(nonzero_a.min()*nonzero_b.min() >= np.finfo(np.float32).tiny, "local product underflow unsupported")
        require(nonzero_a.max()*nonzero_b.max() <= np.finfo(np.float32).max, "local product overflow unsupported")
    k = a.shape[-1]; u32,u64 = 2.**-24,2.**-53
    require(k*u32 < 1, "unsupported accumulation length")
    exactish = a@b
    abs_sum = np.abs(a)@np.abs(b)
    require(y.shape == exactish.shape and np.isfinite(exactish).all(), "local output shape/nonfinite")
    gamma32,gamma64 = k*u32/(1-k*u32),k*u64/(1-k*u64)
    # Upper estimate for the exact absolute dot, including FP64's reduction error.
    abs_upper = abs_sum/(1-gamma64)
    require(np.all(abs_upper <= np.finfo(np.float32).max), "possible intermediate accumulation overflow")
    exponent = np.frexp(np.abs(y))[1]
    half_bin = np.where(y == 0, 2.**-134, np.maximum(2.**-134, np.exp2(exponent.astype(np.float64)-9)))
    bound = (gamma32+gamma64)*abs_upper+half_bin
    error = np.abs(y-exactish)
    return {"elements":y.size,"K":k,"gamma_fp32":gamma32,"mismatches":int(np.count_nonzero(error > bound)),
            "max_error_to_bound_ratio":float(np.max(error/bound)),"max_abs_error_vs_fp64_dot":float(error.max()),
            "max_bound":float(bound.max()),"scope":"conditional_FP32_accumulation_and_BF16_RNE_local_audit_only"}


def softmax_invariants(probability, mask):
    """v0 FP32 row sum and exact masked-zero invariants, before BF16 cast."""
    p, mask = np.asarray(probability), np.asarray(mask)
    require(p.dtype == np.float32 and p.ndim == 4 and p.size > 0, "invalid FP32 probabilities")
    require(np.isfinite(p).all() and np.isfinite(mask).all(), "nonfinite softmax")
    require(mask.shape == (1, 1, p.shape[-2], p.shape[-1]), "softmax mask geometry")
    require(np.all((mask == 0) | (mask == np.float32(-3.3895313892515355e38))), "unsupported mask values")
    error = np.abs(p.sum(axis=-1, dtype=np.float64)-1)
    masked = np.broadcast_to(mask != 0, p.shape)
    masked_nonzeros = int(np.count_nonzero(p[masked]))
    valid_range = bool(np.all((p >= 0) & (p <= 1)))
    return {"invariant": "FP32_softmax_row_sum_and_causal_zeros", "rows": error.size,
            "max_row_sum_abs_error": float(error.max()), "row_sum_abs_limit": 2e-5,
            "masked_nonzeros": masked_nonzeros, "probabilities_in_unit_interval": valid_range,
            "pass": bool(error.max() <= 2e-5 and masked_nonzeros == 0 and valid_range)}


def diagnose_trace(native, reference, weights):
    """Evidence for first divergence; diagnostic witnesses never alter the oracle.

    Exact dyadic dot witnesses distinguish graph propagation from the first cold
    GEMM's same-operand rounding difference. They do not recover the opaque native
    accumulator or prove any particular CPU summation tree.
    """
    from fractions import Fraction

    require(len(native) == len(reference) and native, "diagnostic trace lengths differ")
    changed, failed = [], []
    for index, (a, b) in enumerate(zip(native, reference, strict=True)):
        require(a["key"] == b["key"] and a["dtype"] == b["dtype"], "diagnostic boundary drift")
        x, y = a["value"], b["value"]
        comparison = producer_compare(x, y)
        if not comparison["pass"]: failed.append(a["key"])
        if not np.array_equal(x.view(np.uint32), y.view(np.uint32)):
            diff = np.abs(x.astype(np.float64)-y.astype(np.float64))
            chosen = diff.argmax() if np.any(diff) else np.flatnonzero(x.view(np.uint32) != y.view(np.uint32))[0]
            coordinate = tuple(int(v) for v in np.unravel_index(chosen, diff.shape))
            changed.append({"index": index, "producer": a["key"], "storage_dtype": a["dtype"],
                            "max_abs_error": comparison["max_abs_error"], "coordinate": list(coordinate),
                            "native": float(x[coordinate]), "numpy": float(y[coordinate])})
    result = {"first_bit_difference": next(iter(changed), None),
              "first_bf16_difference": next((r for r in changed if r["storage_dtype"] == "bfloat16"), None),
              "first_operator_failure": next(iter(failed), None), "changed_producers": len(changed),
              "native_accumulation_tree_identified": False}
    first = result["first_bf16_difference"]
    if first and "cast_bf16" in first["producer"]:
        i, coordinate = first["index"], tuple(first["coordinate"])
        midpoint = (Fraction(first["native"])+Fraction(first["numpy"]))/2
        before_a, before_b = native[i-1]["value"][coordinate], reference[i-1]["value"][coordinate]
        result["first_cast_witness"] = {"native_precast": float(before_a), "numpy_precast": float(before_b),
            "midpoint_between_outputs": float(midpoint),
            "native_minus_midpoint": float(Fraction(float(before_a))-midpoint),
            "numpy_minus_midpoint": float(Fraction(float(before_b))-midpoint),
            "both_RNE_correct_for_own_input": bool(
                bf16(before_a).view(np.uint32) == np.float32(first["native"]).view(np.uint32) and
                bf16(before_b).view(np.uint32) == np.float32(first["numpy"]).view(np.uint32))}
    if first and first["producer"] == "self_attn.q_proj|aten.linear.default|0":
        i = first["index"]
        left_a, left_b = native[i-1]["value"], reference[i-1]["value"]
        same_inputs = np.array_equal(left_a.view(np.uint32), left_b.view(np.uint32))
        result["first_projection_operands_bit_identical"] = bool(same_inputs)
        if same_inputs:
            coordinate = tuple(first["coordinate"])
            left = left_a[coordinate[:-1]]
            right = weights["self_attn.q_proj.weight"][coordinate[-1]]
            exact = sum((Fraction(float(a))*Fraction(float(b)) for a, b in zip(left, right, strict=True)), Fraction())
            midpoint = (Fraction(first["native"])+Fraction(first["numpy"]))/2
            result["first_projection_exact_dot_witness"] = {"coordinate": list(coordinate),
                "packed_role": "gate" if coordinate[-1] % 512 >= 256 else "query",
                "exact_dot_numerator": str(exact.numerator), "exact_dot_denominator": str(exact.denominator),
                "exact_dot": float(exact), "midpoint_between_outputs": float(midpoint),
                "exact_dot_minus_midpoint": float(exact-midpoint), "scope": "selected_same_input_dot_only"}
    return result
