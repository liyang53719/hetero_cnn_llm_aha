"""Bounded experimental BF16 head transaction and physical byte-store contract.

This is transport preparation, not a new numerical oracle or producer policy.
The original frozen arithmetic/native corpus remains authoritative.
"""
from __future__ import annotations
import numpy as np
from .model_geometry import require

POLICY = 0xB1
HEAD_DIM = 256
ROTARY_DIM = 64
DATA_BASE = 0x1000
TRIG_BASE = 0x2000
DST_BASE = 0x3000


def admit(*, heads, head_dim, rotary_dim, data_beats, policy,
          source, trig, destination, addr_width=10, l2_beats=None):
    fields = (heads, head_dim, rotary_dim, data_beats, policy,
              source, trig, destination, addr_width)
    require(all(type(x) is int for x in fields), 'integer fields required')
    require(1 <= addr_width <= 58, 'address width out of range')
    require(heads in (1, 2) and head_dim == HEAD_DIM and rotary_dim == ROTARY_DIM,
            'unsupported candidate geometry')
    require(data_beats == 8 * heads and policy == POLICY,
            'unsupported candidate policy or beat count')
    require(source >= 0 and trig >= 0 and destination >= 0, 'negative address')
    require(source % 64 == 0 and trig % 64 == 0 and destination % 2 == 0,
            'unsupported alignment')
    if l2_beats is None:
        l2_beats = min(1 << addr_width, 24576)
    require(type(l2_beats) is int and 0 < l2_beats <= 1 << addr_width, 'fabric capacity')
    limit = l2_beats * 64
    require(source + heads * 512 <= limit and trig + 128 <= limit and
            destination + heads * 512 <= limit, 'address truncation or range overflow')
    return {'reads': data_beats + 2, 'pairs': 32 * heads,
            'writes': data_beats + int(destination % 64 != 0)}


def tensor_from_pairs(inputs, native_outputs, tail):
    """Assemble 1/2 source heads; expected rotated words are frozen native bits."""
    require(isinstance(inputs, np.ndarray) and inputs.dtype == np.uint32 and
            inputs.ndim == 2 and inputs.shape[1] == 4 and len(inputs) in (32, 64),
            'pair shape/dtype')
    heads = len(inputs) // 32
    require(isinstance(native_outputs, np.ndarray) and native_outputs.dtype == np.uint32
            and native_outputs.shape == (heads * 32, 2), 'native output shape/dtype')
    require(not np.any(inputs & 0xFFFF) and not np.any(native_outputs & 0xFFFF),
            'transport accepts exact BF16 source words only')
    require(isinstance(tail, np.ndarray) and tail.dtype == np.uint16 and
            tail.shape == (heads, 192), 'tail shape/dtype')
    pairs = inputs.reshape(heads, 32, 4)
    require(all(np.array_equal(pairs[h, :, 2:], pairs[0, :, 2:]) for h in range(heads)),
            'coefficient row differs across grouped heads')
    source = np.empty((heads, 256), dtype=np.uint16)
    expected = np.empty_like(source)
    source[:, :32] = pairs[:, :, 0] >> 16
    source[:, 32:64] = pairs[:, :, 1] >> 16
    source[:, 64:] = tail
    expected[:, :32] = native_outputs.reshape(heads, 32, 2)[:, :, 0] >> 16
    expected[:, 32:64] = native_outputs.reshape(heads, 32, 2)[:, :, 1] >> 16
    expected[:, 64:] = tail
    trig = (pairs[0, :, 2:].T >> 16).astype(np.uint16)
    return source, trig, expected


def adversarial_tail(seed, heads):
    """Synthetic bypass transport data, never labelled historical model payload."""
    require(type(seed) is int and seed >= 0 and heads in (1, 2), 'tail parameters')
    special = np.array([0, 0x8000, 0x7F80, 0xFF80, 0x7FC1, 0xFFC2,
                        0x7F81, 0xFF81, 1, 0x8001, 0x7F7F, 0xFF7F], dtype=np.uint16)
    rng = np.random.default_rng(seed)
    tail = rng.integers(0, 65536, size=(heads, 192), dtype=np.uint16)
    for h in range(heads):
        tail[h, :len(special)] = special
    return tail


def pack_beat(words):
    require(isinstance(words, np.ndarray) and words.dtype == np.uint16 and
            words.shape == (32,), 'beat requires 32 uint16 words')
    return sum(int(word) << (16 * lane) for lane, word in enumerate(words))


def expected_packets(tensor, destination):
    require(isinstance(tensor, np.ndarray) and tensor.dtype == np.uint16 and
            tensor.shape in ((1, 256), (2, 256)), 'tensor shape/dtype')
    require(type(destination) is int and destination >= 0 and destination % 2 == 0,
            'destination must be nonnegative BF16-aligned')
    # Byte-addressed independently of RTL's BF16-lane packet assembly.
    raw = tensor.astype('<u2', copy=False).tobytes()
    packets = []
    first = destination // 64 * 64
    for address in range(first, destination + len(raw), 64):
        mask = value = 0
        for lane in range(64):
            index = address + lane - destination
            if 0 <= index < len(raw):
                mask |= 1 << lane
                value |= raw[index] << (8 * lane)
        packets.append((address // 64, mask, value))
    return packets
