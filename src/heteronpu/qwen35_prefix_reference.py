"""Independent FP64 embedding→GDN0/1/2→attention3 mathematical prefix.

No official outputs/states are injected into this recurrence. This is not a
BF16 producer-rounding oracle, final-model output, RTL, or performance model.
"""
from __future__ import annotations

import numpy as np

from .model_geometry import require
from .qwen35_gdn_numpy_reference import forward as gdn_forward
from .qwen35_numpy_reference import forward as attention_forward


def embedding_lookup(token_ids, rows):
    token_ids, rows = np.asarray(token_ids), np.asarray(rows)
    require(token_ids.dtype.kind in "iu" and token_ids.shape == (1, 128), "prefix token IDs need integer [1,128]")
    require(rows.shape == (256, 1024) and rows.dtype.kind == "f" and np.isfinite(rows).all(), "invalid real embedding rows")
    require(np.all((token_ids >= 0) & (token_ids < 256)), "token outside acquired embedding rows")
    return rows[token_ids].astype(np.float64, copy=True)


def verify_activation_links(embedding, records):
    require(len(records) == 4, "prefix requires four ordered layer records")
    previous = np.asarray(embedding)
    for layer, record in enumerate(records):
        require(record["layer"] == layer and type(record["layer"]) is int, "prefix layer order drift")
        x, y = np.asarray(record["input"]), np.asarray(record["output"])
        require(x.shape == previous.shape == y.shape and np.isfinite(x).all() and np.isfinite(y).all(), "invalid prefix boundary arrays")
        require(np.array_equal(x, previous), "prefix activation link broken")
        previous = y
    return True


def forward(token_ids, embedding_rows, weights, past=None, *, position_start=0, config=None):
    require(set(weights) == {0, 1, 2, 3}, "prefix needs all four real weight sets")
    require(type(position_start) is int and position_start in (0, 128), "prefix position_start must be 0 or 128")
    require(past is None if position_start == 0 else past is not None, "prefix cold/carried state mismatch")
    if past is not None:
        require(set(past) == {0, 1, 2, 3} and all(past[i] is not None for i in range(4)), "prefix needs independent state for each layer")
        require(past[3][0].shape == past[3][1].shape == (1, 2, 128, 256), "prefix carried KV geometry drift")
    embedding = embedding_lookup(token_ids, embedding_rows)
    x = embedding
    states, records = {}, []
    for layer in range(4):
        initial = None if past is None else past[layer]
        if layer < 3:
            y, state = gdn_forward(x, weights[layer], initial, config=config)
            names = ("conv_state", "recurrent_state")
        else:
            y, state = attention_forward(x, weights[layer], initial, position_start=position_start)
            names = ("key", "value")
        records.append({"layer": layer, "input": x.copy(), "output": y.copy(),
                        **{name: value.copy() for name, value in zip(names, state, strict=True)}})
        states[layer] = tuple(value.copy() for value in state)
        x = y
    verify_activation_links(embedding, records)
    return embedding, records, states
