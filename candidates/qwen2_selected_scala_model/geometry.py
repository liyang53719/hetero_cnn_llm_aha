"""Source issue geometry, never measured hardware cycles or utilization."""


def plan(length):
    if type(length) is not int or not 1 <= length <= 128:
        raise ValueError('canonical selected prefill length 1..128 required')
    pairs = 12 * length * (length + 1) // 2
    groups = 12 * sum((keys + 15) // 16 for keys in range(1, length + 1))
    qk_steps, pv_steps = 8 * groups, 8 * pairs
    return dict(
        evidence='SOURCE_WORK_PLAN_NOT_EXECUTION_OR_CYCLES',
        prefill_jobs=1, rows=length, installed_mac_lanes=4096,
        qk=dict(logical_m=1, logical_n='active keys 1..16', logical_k=128,
                issue_m=16, issue_n=256, issue_k=1, slice_mask=255,
                steps=qk_steps, groups=groups, useful_macs=128 * pairs,
                issued_active_capacity_macs=4096 * qk_steps,
                selected_lanes_per_step='16 * active keys; at most 256 of 4096'),
        pv=dict(logical_m=1, logical_n=16, logical_k='causal keys 1..rows',
                issue_m=16, issue_n=32, issue_k=1, slice_mask=1,
                steps=pv_steps, groups=12 * length * 8, useful_macs=128 * pairs,
                issued_active_capacity_macs=512 * pv_steps,
                selected_lanes_per_step=16),
        attention_useful_macs=256 * pairs,
        attention_issued_active_capacity_macs=4096 * qk_steps + 512 * pv_steps,
        whole_block_useful_macs=length * 46792704 + 256 * pairs,
        hardware_cycles=None, hardware_utilization=None,
        required_denominator='4096 * measured whole-block command-accept through final-completion-ACK cycles',
        omitted_from_issue_counts=['DMA', 'Scalar work', 'bank waits', 'backpressure',
                                  'client retirement', 'final completion ACK', 'other block operators'],
        memory_beats=dict(q_reads=96 * length, k_reads=8 * pairs,
                          v_reads=8 * pairs, output_write_acks=96 * length),
        logical_retention=dict(query_words=128, score_capacity_words=1024,
                               probability_capacity_words=1024, existing_dense_operand_words=256,
                               six_head_panel=False, six_head_kv_cache=False),
        scope='Per-head correspondence baseline underfills the fixed physical array; not the final 90% architecture schedule')
