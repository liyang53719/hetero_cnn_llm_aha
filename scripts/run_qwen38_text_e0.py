#!/usr/bin/env python3
"""Run the executable tiny Qwen3.8 text reference and emit frozen evidence."""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import struct

from heteronpu.model_support import ModelProfile
from heteronpu.qwen38_runtime import TinyQwen38TextModel, trace_operator_set
from heteronpu.qwen38_schedule import build_qwen38_schedule


def hash_vectors(vectors) -> str:
    digest = hashlib.sha256()
    for vector in vectors:
        for value in vector:
            digest.update(struct.pack('<f', float(value)))
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='config/model_profiles/qwen3_8_flash_next.json')
    parser.add_argument('--output', default='reports/execution/qwen38_text_e0_result.json')
    parser.add_argument('--seed', type=int, default=3801)
    parser.add_argument('--tokens', default='1,4,7,3,9,2,11,5')
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    profile = ModelProfile.load(root / args.profile)
    tokens = tuple(int(x) for x in args.tokens.split(',') if x)
    model = TinyQwen38TextModel.random(seed=args.seed)

    prefill, state_prefill = model.run(tokens)
    state_incremental = model.initial_state()
    incremental = []
    for token in tokens:
        result, state_incremental = model.step(token, state_incremental)
        incremental.append(result)

    max_diff = 0.0
    for lhs, rhs in zip(prefill, incremental, strict=True):
        max_diff = max(max_diff, *(abs(a - b) for a, b in zip(lhs.hidden, rhs.hidden, strict=True)))

    op_counts = Counter(event.op for result in prefill for event in result.trace)
    engine_counts = Counter(event.engine for result in prefill for event in result.trace)
    qsa_selected = [list(row) for result in prefill for row in result.qsa_selected]
    routes = [[list(layer) for layer in result.routes] for result in prefill]
    schedule = build_qwen38_schedule(profile.layer_pattern, ple_layer_ids=tuple(x - 1 for x in profile.raw['ple']['layer_ids']), include_mtp=True)

    required_runtime_ops = {
        'PLE_NGRAM_HASH_LOOKUP',
        'PLE_GATE_DILATED_DWCONV',
        'GDN_RECURRENT_STATE_UPDATE',
        'QSA_COMPRESS_TOPK',
        'SPARSE_QK_ONLINE_SOFTMAX_PV',
        'ATTENTION_OUTPUT_GATE_PROJECTION',
        'MOE_ROUTER_TOPK',
        'MOE_ROUTED_EXPERT_GEMM',
        'MOE_SHARED_EXPERT',
        'GR_ATTN_READ',
        'GR_MOE_WRITE',
    }
    executed = trace_operator_set(prefill)
    status = 'PASS' if max_diff == 0.0 and required_runtime_ops <= executed and executed <= schedule.operator_names else 'FAIL'

    result = {
        'schema_version': 1,
        'stage': 'L8',
        'subgate': 'Qwen3.8-Flash-Next executable text E0',
        'status': status,
        'evidence_class': 'E0_executable_architectural_reference',
        'official_profile': {
            'model_id': profile.raw['model_id'],
            'revision': profile.raw['revision'],
            'layers': profile.raw['num_hidden_layers'],
            'linear_attention_layers': profile.layer_pattern.count('linear_attention'),
            'qsa_layers': profile.layer_pattern.count('qwen_sparse_attention'),
            'hidden_size': profile.raw['hidden_size'],
            'activated_experts': profile.raw['moe']['top_k'],
        },
        'tiny_reference': {
            'seed': args.seed,
            'tokens': list(tokens),
            'layers': len(model.config.layer_pattern),
            'layer_pattern': list(model.config.layer_pattern),
            'hidden_size': model.config.hidden_size,
            'branches': model.config.branches,
            'experts': model.config.num_experts,
            'top_k': model.config.top_k,
        },
        'prefill_incremental_max_abs_diff': max_diff,
        'final_hidden_sha256': hash_vectors(result.hidden for result in prefill),
        'final_hyper_sha256': hash_vectors(result.hyper for result in prefill),
        'operator_counts': dict(sorted(op_counts.items())),
        'engine_counts': dict(sorted(engine_counts.items())),
        'operator_coverage': sorted(executed),
        'qsa_selected_tokens': qsa_selected,
        'expert_routes': routes,
        'state': {
            'tokens_committed': state_prefill.token_index,
            'incremental_tokens_committed': state_incremental.token_index,
            'copy_isolation_tested_by_pytest': True,
        },
        'schedule': {
            'micro_ops': len(schedule.micro_ops),
            'operator_types': len(schedule.operator_names),
            'all_runtime_ops_have_owner': executed <= schedule.operator_names,
            'local_rtl_dependencies': len(schedule.local_dependencies()),
        },
        'claim_boundary': 'Text-only tiny E0. No official weights, vision, E1 RTL, E3 performance, or E4 PPA claim.',
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
