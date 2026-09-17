"""Audit real-shape Qwen2 HostBlock counters and same-clock AXI roofline bounds.

A log audit cannot prove payload correctness, source identity, SRAM capacity,
clock closure or model throughput. Keep those gates separate. This parser is
explicitly for the existing 21-command/layer Qwen2 path, not Qwen35/Qwen38.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import re

MARKER = 'HOST_BLOCK_ALL_OWNERS_PASS'
REQUIRED = {'tokens', 'hidden', 'ffn', 'layers', 'host_commands', 'completed', 'owner_jobs',
            'matrix_commands', 'sfu_commands', 'kv_commands', 'checked_fp32', 'bit_differences',
            'useful_macs', 'executed_macs', 'cycles', 'read_bytes', 'write_ack_bytes',
            'host_intermediate_writes', 'legacy_block_launch', 'original_matrix_instances',
            'logical_matrix_engines', 'matrix_macs', 'original_idma_instances', 'score_ddr_accesses'}


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def parse_summary(text: str) -> dict[str, int]:
    need(not re.search(r'\bFAIL(?:ED|URE)?\b|_FAIL\b|%Error|\bFatal\b', text, flags=re.I), 'failure in log')
    lines = [line for line in text.splitlines() if line.startswith(MARKER + ' ')]
    need(len(lines) == 1, 'missing/duplicate terminal summary')
    fields = {}
    for token in lines[0].split()[1:]:
        match = re.fullmatch(r'([a-zA-Z0-9_]+)=([^\s=]+)', token)
        need(match is not None, 'malformed summary field')
        key, value = match.groups()
        need(key not in fields, 'duplicate summary key: ' + key)
        fields[key] = value
    need(REQUIRED <= fields.keys(), 'missing mandatory counters')
    values = {}
    for key in sorted(REQUIRED):
        need(re.fullmatch(r'0|[1-9][0-9]*', fields[key]) is not None, 'invalid unsigned counter: ' + key)
        values[key] = int(fields[key])
        need(values[key] < 2**64, 'counter exceeds uint64: ' + key)
    return values


def audit(text: str, clock_hz: int = 800_000_000, bytes_per_beat: int = 64,
          target: Fraction = Fraction(1, 2)) -> dict:
    need(type(clock_hz) is int and 0 < clock_hz <= 10**12, 'invalid nominal clock')
    need(type(bytes_per_beat) is int and bytes_per_beat == 64, 'this ABI is one 512-bit AXI read/write channel')
    need(isinstance(target, Fraction) and 0 < target <= 1, 'invalid target utilization')
    c = parse_summary(text)
    t, h, f, layers = (c[k] for k in ('tokens', 'hidden', 'ffn', 'layers'))
    need(h == 1536 and f == 8960 and 0 < t <= 1024 and 0 < layers <= 3, 'not the frozen real-shape Qwen2 HostBlock scope')
    for key, per_layer in (('host_commands', 21), ('completed', 21), ('owner_jobs', 19),
                           ('matrix_commands', 9), ('sfu_commands', 11), ('kv_commands', 1)):
        need(c[key] == layers * per_layer, 'incomplete/changed command contract: ' + key)
    for key in ('bit_differences', 'host_intermediate_writes', 'legacy_block_launch', 'score_ddr_accesses'):
        need(c[key] == 0, 'forbidden numerical/data-flow scope: ' + key)
    need(c['logical_matrix_engines'] == c['original_idma_instances'] == 1, 'wrong shared-engine configuration')
    need(c['matrix_macs'] in (512, 4096) and c['original_matrix_instances'] * 512 == c['matrix_macs'], 'wrong physical MAC denominator')
    kv = 256
    expected_values = layers * t * (10 * h + 7 * kv + 3 * f)
    need(c['checked_fp32'] == expected_values, 'partial/changed tensor comparison count')
    dense = layers * t * (2 * h * h + 2 * h * kv + 3 * h * f)
    causal_attention = layers * h * t * (t + 1)  # QK and PV, no masked-future MACs
    need(c['useful_macs'] == dense + causal_attention, 'changed/incorrect useful MAC count')
    cycles, peak, useful, executed = (c[k] for k in ('cycles', 'matrix_macs', 'useful_macs', 'executed_macs'))
    read_bytes, write_bytes = c['read_bytes'], c['write_ack_bytes']
    need(cycles > 0 and useful <= executed <= peak * cycles, 'physically impossible MAC counters')
    need(write_bytes == expected_values * 4, 'write ACK bytes do not cover all FP32 tensors')
    need(read_bytes > 0 and write_bytes > 0 and read_bytes % 64 == write_bytes % 64 == 0, 'invalid memory-byte scope')
    read_min, write_min = ceil_div(read_bytes, bytes_per_beat), ceil_div(write_bytes, bytes_per_beat)
    compute_min = ceil_div(executed, peak)
    # Independent AXI read/write channels may overlap; summing the two minima
    # would create an unjustified bottleneck. This is an optimistic LOWER bound.
    lower = max(read_min, write_min, compute_min)
    need(cycles >= lower, 'cycles below compute/AXI lower bound')
    useful_wall = Fraction(useful, peak * cycles)
    executed_wall = Fraction(executed, peak * cycles)
    efficiency = Fraction(useful, executed)
    upper = min(Fraction(1), Fraction(useful, peak * lower))
    target_cycles = Fraction(useful, peak) / target
    return {
        'status': 'PASS_COUNTER_AUDIT_ONLY',
        'scope': {'new_rtl_run': False, 'numeric_outputs_recompared': False,
                  'physical_timing_signoff': False, 'full_model_tokens_per_second': None,
                  'measurement': 'supplied Qwen2 block log only',
                  'bound_assumption': 'unchanged traffic/work; one 512-bit AXI channel per direction at compute clock'},
        'input_sha256': hashlib.sha256(text.encode()).hexdigest(), 'counters': c,
        'derived_work': {'dense_macs': dense, 'causal_attention_macs': causal_attention},
        'metrics': {'useful_wall_mac_utilization': float(useful_wall),
                    'executed_wall_mac_utilization': float(executed_wall),
                    'useful_fraction_of_executed': float(efficiency),
                    'nominal_clock_hz': clock_hz, 'latency_ms_at_nominal_clock': cycles * 1000 / clock_hz,
                    'useful_gmac_s_at_nominal_clock': float(useful_wall) * peak * clock_hz / 1e9},
        'bounds': {'read_min_cycles': read_min, 'write_min_cycles': write_min,
                   'compute_min_cycles': compute_min, 'optimistic_wall_min_cycles': lower,
                   'useful_wall_upper_bound': float(upper),
                   'target_utilization': float(target), 'target_cycles_budget': float(target_cycles),
                   'target_feasible_with_unchanged_traffic': target <= upper,
                   'read_gb_s_required_at_target': float(Fraction(read_bytes * clock_hz, 1) / target_cycles) / 1e9,
                   'axi_read_peak_gb_s': bytes_per_beat * clock_hz / 1e9},
    }
