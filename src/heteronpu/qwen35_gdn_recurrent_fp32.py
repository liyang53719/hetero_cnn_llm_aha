"""Independent frozen arithmetic oracle for the M1 GDN recurrent RTL owner.

Inputs are already normalized/scaled FP32 Q, normalized FP32 K, FP32-expanded
V, log-decay and beta. This deliberately does not claim the upstream projection,
QK normalization or gate-generation hardware is implemented. State stays FP32;
output is explicitly rounded BF16 after the last left-to-right dot product.
No torch, DUT simulator, expected-state injection, or BF16 state approximation.
"""
from __future__ import annotations
import math
import numpy as np


def bf16_rne(x):
    u = np.ascontiguousarray(x, dtype='<f4').view('<u4')
    return ((u + 0x7fff + ((u >> 16) & 1)) >> 16).astype('<u2')


def expand_bf16(x):
    return (np.asarray(x, dtype='<u2').astype('<u4') << 16).view('<f4')


def exp_negative_recipe(x):
    """Same published shared-scalar contract, separate IEEE FP32 rounding."""
    f = np.float32
    x = np.asarray(x, dtype=np.float32)
    if not np.isfinite(x).all() or np.any(x > 0) or np.any(x <= -80):
        raise ValueError('log-decay must be finite and -80 < g <= 0')
    t = np.multiply(np.abs(x), f(1 / math.log(2)), dtype=np.float32)
    integer = t.astype(np.int32)
    fraction = np.subtract(t, integer.astype(np.float32), dtype=np.float32)
    coefficients = [f((-math.log(2)) ** i / math.factorial(i)) for i in range(8)]
    h = np.full(x.shape, coefficients[7], dtype=np.float32)
    for i in range(6, -1, -1):
        h = np.add(np.multiply(h, fraction, dtype=np.float32), coefficients[i], dtype=np.float32)
    scale = ((127 - integer).astype('<u4') << 23).view('<f4')
    return np.multiply(h, scale, dtype=np.float32)


def recurrent_step(query, key, value, gates, initial_state=None):
    """One token; vectors [H,D], gates [H,2], state [H,Dk,Dv]."""
    q, k, v, gates = [np.asarray(x, dtype=np.float32) for x in (query, key, value, gates)]
    if q.ndim != 2 or k.shape != q.shape or v.ndim != 2 or v.shape[0] != q.shape[0]:
        raise ValueError('invalid Q/K/V geometry')
    h, dk = q.shape
    dv = v.shape[1]
    if not h or not dk or not dv or gates.shape != (h, 2):
        raise ValueError('invalid head/gate geometry')
    if not all(np.isfinite(x).all() for x in (q, k, v, gates)):
        raise ValueError('nonfinite recurrent input')
    if np.any(gates[:, 1] < 0) or np.any(gates[:, 1] > 1):
        raise ValueError('beta outside [0,1]')
    state = np.zeros((h, dk, dv), dtype=np.float32) if initial_state is None else np.array(initial_state, dtype=np.float32, copy=True)
    if state.shape != (h, dk, dv) or not np.isfinite(state).all():
        raise ValueError('invalid FP32 state')
    decay = exp_negative_recipe(gates[:, 0])
    with np.errstate(under='ignore', over='raise', invalid='raise'):
        decayed = np.multiply(state, decay[:, None, None], dtype=np.float32)
        prediction = np.zeros((h, dv), dtype=np.float32)
        for row in range(dk):
            p = np.multiply(decayed[:, row, :], k[:, row, None], dtype=np.float32)
            prediction = np.add(prediction, p, dtype=np.float32)
        delta = np.multiply(np.subtract(v, prediction, dtype=np.float32), gates[:, 1, None], dtype=np.float32)
        output = np.zeros((h, dv), dtype=np.float32)
        for row in range(dk):
            rank_one = np.multiply(k[:, row, None], delta, dtype=np.float32)
            state[:, row, :] = np.add(decayed[:, row, :], rank_one, dtype=np.float32)
            term = np.multiply(state[:, row, :], q[:, row, None], dtype=np.float32)
            output = np.add(output, term, dtype=np.float32)
    stored_output = bf16_rne(output)
    if not np.isfinite(expand_bf16(stored_output)).all():
        raise ValueError('BF16 output overflow')
    return stored_output, state, output
