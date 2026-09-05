#!/usr/bin/env python3
"""Reproducible evidence inventory. Never generates a measured RTL receipt."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = ['config/qwen2_1p5b_300tps_budget_800mhz.json',
             'config/model_profiles/qwen3_5_35b_a3b.json',
             'reports/execution/qwen38_full_shape_budget.json',
             'reports/execution/OPERATOR_MODEL_CANARIES_V3.json',
             'tb/tb_qwen2_root_owner_canary_v3.sv']
    q2, q35, q38, _ = [json.loads((ROOT / p).read_text()) for p in paths[:4]]
    h = q35['hidden_size']; m = q35['moe']; g = q35['gated_deltanet']; a = q35['full_attention']
    # Conservative projection/expert-only MAC lower bound; exclude gates, router,
    # recurrence, attention QK/PV, convolution, norms, final head and all stalls.
    expert = 3*h*m['intermediate_size']*(m['top_k']+m['shared_experts'])
    gdn = h*(2*g['qk_heads']*g['key_dim']+2*g['v_heads']*g['value_dim'])
    att = h*(2*a['q_heads']*a['head_dim']+2*a['kv_heads']*a['head_dim'])
    pattern = q35['layer_pattern']
    q35_lower = 1024*(len(pattern)*expert+pattern.count('gated_deltanet')*gdn+pattern.count('full_attention')*att)
    values = [
        ('Qwen2-1.5B', q2['useful_macs_total'], 'existing_full_request_useful_mac_budget'),
        ('Qwen3.5-35B-A3B', q35_lower, 'projection_expert_only_lower_bound_not_full_model'),
        ('Qwen3.8-Flash-Next', q38['cases']['1024']['prefill']['total_macs'], 'local_profile_analytical_budget_not_full_request_measurement')]
    result = {'status': 'PERFORMANCE_OPEN', 'clock_hz': 800000000,
              'bf16_macs_per_cycle': 512, 'peak_gmac_per_second': 409.6,
              'evidence_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
              'models': []}
    for name, macs, scope in values:
        result['models'].append(dict(model=name, analytical_scope=scope,
            analytical_macs=macs, optimistic_compute_only_tps=1024*409600000000/macs,
            measured_q1024_cycles=None, measured_tokens_per_second=None,
            measured_wall_mac_utilization=None))
    result['nonclaims'] = ['No full-request counters in current four root canaries',
        'Qwen3.5 lower bound excludes substantial work; its TPS is an upper bound only',
        'Qwen3.8 existing budget is not a measured matrix-only MAC numerator',
        'Historical 1GHz performance and current 800MHz measurements are distinct',
        'Admission unit tests do not establish payload performance']
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
