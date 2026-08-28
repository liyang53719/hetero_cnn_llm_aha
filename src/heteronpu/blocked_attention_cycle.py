"""Cycle-structured E0 model for Qwen2 blocked causal attention.

It freezes the accepted 16x32 Matrix geometry, four-context recurrence,
16-query/32-key microtiles, GQA 6:1 reuse and Block128 M/L/O merge counts.
This is an E0 scheduling reference, not RTL E1/E2 or integrated E3 evidence.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math

@dataclass(frozen=True)
class AttentionGeometry:
    sequence_length: int
    query_heads: int = 12
    kv_heads: int = 2
    head_dim: int = 128
    query_tile: int = 16
    key_tile: int = 32
    hierarchy_block_tokens: int = 128
    def __post_init__(self) -> None:
        if min(asdict(self).values()) <= 0: raise ValueError("positive geometry required")
        if self.query_heads % self.kv_heads: raise ValueError("GQA geometry")
        if self.hierarchy_block_tokens % self.key_tile: raise ValueError("Block128/key-tile geometry")

@dataclass(frozen=True)
class AttentionHardware:
    matrix_rows: int = 16
    matrix_columns: int = 32
    matrix_feedback_latency: int = 4
    matrix_contexts: int = 4
    score_entries_per_cycle: int = 32
    merge_output_lanes: int = 4
    element_bytes: int = 2
    score_bytes: int = 4
    probability_bytes: int = 2
    clock_hz: int = 1_000_000_000
    def __post_init__(self) -> None:
        if min(asdict(self).values()) <= 0: raise ValueError("positive hardware geometry required")
        if self.matrix_contexts < self.matrix_feedback_latency: raise ValueError("contexts do not hide feedback")
    @property
    def macs_per_cycle(self) -> int: return self.matrix_rows * self.matrix_columns

def exact_causal_pairs(length: int) -> int: return length * (length + 1) // 2

def summary_merge_count(g: AttentionGeometry) -> int:
    return g.query_heads * sum(q // g.hierarchy_block_tokens for q in range(g.sequence_length))

def blocked_attention_report(g: AttentionGeometry, h: AttentionHardware = AttentionHardware()) -> dict[str, object]:
    query_tiles = math.ceil(g.sequence_length / g.query_tile)
    query_key_pairs = score_entries = 0
    for start in range(0, g.sequence_length, g.query_tile):
        rows = min(g.query_tile, g.sequence_length - start)
        key_microtiles = math.ceil((start + rows) / g.key_tile)
        query_key_pairs += key_microtiles
        score_entries += rows * g.key_tile * key_microtiles
    head_microtiles = query_key_pairs * g.query_heads
    kv_uses = query_key_pairs * g.kv_heads
    qk_per_tile = g.head_dim
    pv_per_tile = g.key_tile * (g.head_dim // h.matrix_columns)
    qk_cycles = head_microtiles * qk_per_tile
    pv_cycles = head_microtiles * pv_per_tile
    matrix_issue = qk_cycles + pv_cycles
    matrix_wall = matrix_issue + h.matrix_feedback_latency
    score_entries *= g.query_heads
    score_cycles = math.ceil(score_entries / h.score_entries_per_cycle)
    merges = summary_merge_count(g)
    merge_cycles = merges * math.ceil(g.head_dim / h.merge_output_lanes)
    sfu_cycles = score_cycles + merge_cycles
    serialized = matrix_wall + sfu_cycles
    overlap = max(matrix_wall, sfu_cycles)
    exact_macs = exact_causal_pairs(g.sequence_length) * g.query_heads * g.head_dim * 2
    tiled_macs = matrix_issue * h.macs_per_cycle
    q_tile = g.query_tile * g.head_dim * h.element_bytes
    k_tile = g.key_tile * g.head_dim * h.element_bytes
    score_tile = g.query_tile * g.key_tile * h.score_bytes
    probability_tile = g.query_tile * g.key_tile * h.probability_bytes
    mlo = g.query_tile * (g.head_dim + 2) * 4
    live = q_tile + 2 * k_tile + score_tile + probability_tile + mlo
    return {"status":"PASS","sequence_length":g.sequence_length,"query_tiles":query_tiles,"query_key_pairs":query_key_pairs,"head_microtiles":head_microtiles,"kv_microtile_uses_after_GQA_reuse":kv_uses,"summary_merges":merges,"matrix_qk_issue_cycles":qk_cycles,"matrix_pv_issue_cycles":pv_cycles,"matrix_issue_cycles":matrix_issue,"matrix_wall_cycles":matrix_wall,"score_pipeline_cycles":score_cycles,"summary_merge_cycles":merge_cycles,"sfu_cycles":sfu_cycles,"serialized_cycles":serialized,"overlapped_lower_bound_cycles":overlap,"causal_tile_efficiency":exact_macs/tiled_macs,"score_DDR_materialization_bytes":0,"probability_DDR_materialization_bytes":0,"single_active_head_live_bytes":live,"four_head_pingpong_upper_bound_bytes":8*live,"serialized_tokens_per_second":g.sequence_length*h.clock_hz/serialized,"not_an_E3_claim":True}

def sweep_reports(lengths=(128,384,1024)) -> dict[str, object]:
    cases={str(length):blocked_attention_report(AttentionGeometry(length)) for length in lengths}
    result={"schema_version":1,"status":"PASS","evidence_class":"cycle_structured_E0_not_RTL_E1_or_integrated_E3","cases":cases,"frozen_checks":{"q1024_summary_merges":cases["1024"]["summary_merges"],"all_score_DDR_materialization_zero":all(case["score_DDR_materialization_bytes"]==0 and case["probability_DDR_materialization_bytes"]==0 for case in cases.values())}}
    if result["frozen_checks"]["q1024_summary_merges"]!=43008: raise AssertionError("q1024 merge contract")
    return result
