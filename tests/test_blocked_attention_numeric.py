import numpy as np
from heteronpu.blocked_attention_numeric import (
    AttentionGeometry,
    blocked_attention_numeric_report,
    blocked_causal_gqa_rows,
    dense_causal_gqa_rows,
    generate_inputs,
)


def test_small_dense_parity():
    g = AttentionGeometry(sequence=33, q_heads=4, kv_heads=2, head_dim=16, query_tile=8, kv_tile=8, block_tokens=16)
    q, k, v = generate_inputs(g, 17)
    rows = (0, 7, 15, 16, 32)
    got, counters = blocked_causal_gqa_rows(q, k, v, rows=rows, query_tile=8, kv_tile=8, block_tokens=16)
    ref = dense_causal_gqa_rows(q, k, v, rows)
    np.testing.assert_allclose(got, ref, rtol=2e-5, atol=2e-5)
    assert counters["score_ddr_bytes"] == 0
    assert counters["probability_ddr_bytes"] == 0


def test_expected_q1024_merge_count():
    assert AttentionGeometry(1024).expected_summary_merges == 43008


def test_full_report():
    report = blocked_attention_numeric_report()
    assert report["status"] == "PASS", report
    assert report["analytic_q1024_summary_merges"] == 43008
    assert report["maximum_error"]["max_abs"] <= 2e-4
