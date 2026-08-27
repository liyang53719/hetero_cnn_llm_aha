#!/usr/bin/env python3
"""Randomized Gated DeltaNet chunk-prefill vs recurrent E0 equivalence gate."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from heteronpu.gated_deltanet import Geometry, delta_rule_chunk, delta_rule_recurrent


def case(rng: random.Random, tokens: int, chunk_size: int) -> tuple[float, float]:
    geometry = Geometry(qk_heads=1, v_heads=2, key_dim=2, value_dim=3)
    query = tuple((tuple(rng.uniform(-1, 1) for _ in range(2)),) for _ in range(tokens))
    key = tuple((tuple(rng.uniform(-1, 1) for _ in range(2)),) for _ in range(tokens))
    value = tuple(tuple(tuple(rng.uniform(-1, 1) for _ in range(3)) for _ in range(2)) for _ in range(tokens))
    log_decay = tuple(tuple(rng.uniform(-2.0, -0.01) for _ in range(2)) for _ in range(tokens))
    beta = tuple(tuple(rng.uniform(0.01, 0.99) for _ in range(2)) for _ in range(tokens))
    recurrent, recurrent_state = delta_rule_recurrent(
        geometry=geometry, query=query, key=key, value=value, log_decay=log_decay, beta=beta
    )
    chunked, chunked_state = delta_rule_chunk(
        geometry=geometry,
        query=query,
        key=key,
        value=value,
        log_decay=log_decay,
        beta=beta,
        chunk_size=chunk_size,
    )
    out_error = max(
        abs(a - b)
        for token_a, token_b in zip(recurrent, chunked, strict=True)
        for head_a, head_b in zip(token_a, token_b, strict=True)
        for a, b in zip(head_a, head_b, strict=True)
    )
    state_error = max(
        abs(a - b)
        for head_a, head_b in zip(recurrent_state.data, chunked_state.data, strict=True)
        for row_a, row_b in zip(head_a, head_b, strict=True)
        for a, b in zip(row_a, row_b, strict=True)
    )
    return out_error, state_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=int, default=100)
    parser.add_argument('--seed', type=int, default=3508)
    parser.add_argument('--output', default='reports/execution/gdn_chunk_e0_result.json')
    args = parser.parse_args()
    rng = random.Random(args.seed)
    worst_out = 0.0
    worst_state = 0.0
    histogram: dict[str, int] = {}
    for index in range(args.cases):
        tokens = rng.randint(1, 17)
        chunk_size = rng.choice((1, 2, 3, 4, 5, 8, 16, 64))
        out_error, state_error = case(rng, tokens, chunk_size)
        worst_out = max(worst_out, out_error)
        worst_state = max(worst_state, state_error)
        histogram[str(chunk_size)] = histogram.get(str(chunk_size), 0) + 1
    threshold = 5e-5
    result = {
        'schema_version': 1,
        'stage': 'L8',
        'subgate': 'Gated DeltaNet chunk-prefill E0',
        'status': 'PASS' if worst_out <= threshold and worst_state <= threshold else 'FAIL',
        'cases': args.cases,
        'seed': args.seed,
        'chunk_size_histogram': histogram,
        'max_output_abs_error': worst_out,
        'max_state_abs_error': worst_state,
        'threshold': threshold,
        'evidence_class': 'E0_executable_algorithmic_reference',
        'claim_boundary': 'Tiny float32 reference only; no kernel throughput or RTL claim.',
    }
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
