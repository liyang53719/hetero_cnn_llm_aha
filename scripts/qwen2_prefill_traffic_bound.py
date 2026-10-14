#!/usr/bin/env python3
"""Source-bound optimistic weight-traffic limit, not a full cycle simulator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
# Reviewed 3cd847d -> f16df50: the Qwen2 Host keeps both H2048 borrower
# switches false. Existing geometry, arithmetic and owner serialization
# are unchanged; these models do not cover the enabled borrower path.
SOURCE_PINS = {
    BASE + 'DenseReadPlanner.scala': '0f4c981b32170344c316e0b8dfe6296f2f497d4901365e05e0b9d730d1fd1886',
    BASE + 'StreamingDense.scala': '18d99633b57e5f394f99c242231a5ee009dcf125c03c8940674a01a7965ee789',
    BASE + 'BlockAxiAdapter.scala': '52e8b5281f0517c3b08ceefff06c14bf85942a7d913c997548f54e7e804d3421',
    BASE + 'IdmaWeightBurst.scala': '3d0afaff91e8cc8915e99ad3276339bda7d044404b39cd1c2a77c621b990f5ff',
    BASE + 'MatrixPipeline.scala': 'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
    BASE + 'QwenOwnerProtocol.scala': '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d',
    BASE + 'HostBlockCommands.scala': '68749c376fffeaed47a2b2965ec7e3af594b5409c7cd08d31c16535d75073757',
    BASE + 'HostBlockTop.scala': 'e018e8ba50129c81f0c4c7385fe6ddc1fe65ee52678b1c036ef11671085e304d',
    BASE + 'Qwen2Block.scala': '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4',
    'config/upstream/weight_headers/qwen2_1p5b/config.json': 'a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/RetainedMatrix.scala': '80dc285af2208b3f3aa3d811a561cfe729e2c764b45c1da62de360f9578321bb',
    'rtl/integration/qwen2_matrix_command_endpoint.sv': '057ce15d3b9fd5153c8873498f9cf1b3f17d7eea64e8928c1208496b3d0bd53a',
    'rtl/matrix/bf16_outer_product_array_glue512.sv': '8d02ba89ffa8b32acbd8bf5677906c71bedd698ac6337df0aa0c06dca1c78fa9',
    'rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv': 'e9cdc568bb11f13db3d7653e375e79baa751af4080a9f5bdbc9a3353bbdde471',
    'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv': 'a4c37b485f1e7eeed3012372024e8e7207bc33af6ff97bc307a5572aced6890e',
    'rtl/matrix/candidates/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv': 'e1afd499281df0493f1660bbfe8b1a5f6bfeea9e49899b0368372d23d4c790c2',
    'rtl/matrix/candidates/rev8b_b/bf16_context_tag_pipeline5_rev8b_b_candidate.sv': '0271a1627089578a95144fd0cddd4b9d8d39a6cd27ea327eb48ca399c9bc3ac0',
    'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv': 'ad985950e9129c524f685385dac75db9f3bd4ca632e125f7e1b54103271fb418',
    'rtl/matrix/candidates/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv': 'be5c10cfe04fe053620883f5bf84646afc990f8c363e1d280ef2dc6b1341148b',
    'rtl/matrix/candidates/rev8b_b/bf16_cluster_flags_glue32_rev8b_b_candidate.sv': '4d39ce9f81ceab8853b1d91f757e8d237d891cc8a875a904599726f5c80d6d3f',
    'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv': '0d3bbeee52db023598ebc457420cd2ed8063051363b5c89699730b7f0cbfe6bc',
    'rtl/matrix/candidates/rev8b_b/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv': '991c73df8b263e0a7283e6eb01be85fe283740b450a42a7d1e693114e1bef64b',
    'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv': '541d4a717df08ef65e0ac047c1f83e06b1e3e1bead6553bd97ada24a32a30d59',
}
MATRICES = [('q',1536,1536), ('k',1536,256), ('v',1536,256),
            ('o',1536,1536), ('gate',1536,8960), ('up',1536,8960),
            ('down',8960,1536)]
HOST_SOURCE_PINS = {
    BASE + 'Protocol.scala': '5c94def481dede0195f989608c1827ded32f2d83c752617945695f7d82f64783',
    BASE + 'ElementwiseMemoryEngine.scala': 'cb8a338051cce94dda613603df892bd0f43b6ea62423ad1f9d28b24f98b73845',
    BASE + 'VectorSilu.scala': '758f48c6f945fe78fafeb9d4086c43d4041ece5ead9a90b947379f7f522c32f9',
    BASE + 'OverlappedSilu.scala': 'd15173c8105c6d9139623c890a4b6488edac3027e06cef61ca6af06440684dea',
}


def verify_sources(root: Path) -> dict:
    for name, expected in SOURCE_PINS.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('source changed; re-audit bound before use: ' + name)
    return dict(SOURCE_PINS)


def calculate(tokens: int, weight_dtype: str = 'BF16') -> dict:
    if type(tokens) is not int or tokens not in (128, 1024):
        raise ValueError('bound supports the explicit M128 and M1024 cold-prefill workloads only')
    if weight_dtype not in ('BF16', 'FP32'):
        raise ValueError('unsupported weight transport precision')
    bytes_per_weight = 2 if weight_dtype == 'BF16' else 4
    budget = 768 * 1024
    b_bytes = 16 * 160 * 32
    a_words_per_bank = min(5 * (8960 // 16), (budget - b_bytes) // (16 * 32))
    a_bytes = 16 * a_words_per_bank * 32
    phases = []
    for name, k, n in MATRICES:
        # Exact DenseScratchGeometry.tokenTiles selection, capped by five
        # accumulator contexts even where physical A SRAM has spare words.
        mt = max(t for t in range(1,6) if k <= a_words_per_bank * 16 // t)
        rows = mt * 16
        repeats = (tokens + rows - 1) // rows
        phases.append(dict(name=name,k=k,n=n,rows_per_group=rows,
            max_m_contexts=mt,weight_full_reads=repeats,
            weight_elements=k*n,weight_bytes=k*n*bytes_per_weight,
            ingress_weight_bytes=k*n*bytes_per_weight*repeats,
            active_a_bf16_bytes=rows*k*2,
            active_a_words_per_bank=mt*(k//16),
            inactive_a_bytes=a_bytes-rows*k*2,
            useful_macs=tokens*k*n))
    dense_macs = sum(p['useful_macs'] for p in phases)
    # One cold causal complete block: 12 heads, dim128, QK and PV.
    attention_macs = 2 * 12 * 128 * (tokens * (tokens+1) // 2)
    total_macs = dense_macs + attention_macs
    traffic = sum(p['ingress_weight_bytes'] for p in phases)
    read_cycles = (traffic+63)//64
    compute_cycles = (total_macs+4095)//4096
    optimistic_cycles = max(read_cycles,compute_cycles)
    return dict(schema_version=1,status='CONDITIONAL_SOURCE_BOUND_NOT_CYCLE_PREDICTION',
        workload=dict(model='Qwen2-1.5B-Instruct',layer=0,batch=1,tokens=tokens,
                      past_tokens=0,causal=True,weight_dtype=weight_dtype),
        scope=dict(actual_model_run=False,actual_rtl_run=False,
                   full_block_cycle_prediction=False,hardware_acceptance=False),
        fixed_resources=dict(matrix_macs_per_cycle=4096,axi_r_bytes_per_cycle=64,
            scratch_budget_bytes=budget,a_words_per_bank=a_words_per_bank,
            a_allocated_bytes=a_bytes,b_ping_pong_allocated_bytes=b_bytes,
            scratch_total_allocated_bytes=a_bytes+b_bytes,
            max_accumulator_contexts=5,
            accumulators_included_in_scratch_budget=False),
        dense_phases=phases,dense_useful_macs=dense_macs,
        qk_pv_useful_macs=attention_macs,total_useful_macs=total_macs,
        weight_ingress_bytes=traffic,weight_read_cycles_lower_bound=read_cycles,
        compute_cycles_lower_bound=compute_cycles,
        whole_block_cycles_lower_bound=optimistic_cycles,
        useful_utilization_upper_bound=total_macs/(4096*optimistic_cycles),
        target_cycle_budgets={str(p)+'_percent':total_macs*100//(4096*p) for p in (80,90)},
        predicted_full_block_cycles=None,rtl_measured_cycles=None,rtl_measured_utilization=None,
        assumptions=['current five-context StreamingDense schedule and Qwen2 maxK8960',
            'all seven Dense matrices fetched through the single 512-bit AXI R ingress',
            'each row group fetches every weight exactly once; no persistent full-weight cache',
            'one R beat every cycle with no bubbles; ideal overlap of compute and ingress',
            'full cold causal QK/PV logical MAC numerator, including those outside the weight bound'],
        omitted_costs=['activation/parameter/descriptor reads','all output/state writes and ACKs',
            'Norm/RoPE/softmax/SiLU/residual scalar and vector cycles',
            'actual memory latency/backpressure','setup/drain and dependent phase gaps'])


def report(root: Path, tokens: int, weight_dtype: str = 'BF16') -> dict:
    pins = verify_sources(root)
    result = calculate(tokens,weight_dtype)
    result['source_sha256'] = pins
    return result


def host_schedule_report(root: Path, tokens: int, weight_dtype: str = 'BF16') -> dict:
    """A stricter lower bound for the existing pipelined Host, not simulation.

    Every non-overlapping arithmetic request gets only ONE cycle here, even
    division/exp and the pending Matrix request. Actual latencies are larger.
    Dense, core and SiLU owners are serialized by QwenOwnerKernel.active/mode.
    """
    base = report(root, tokens, weight_dtype)
    for name, expected in HOST_SOURCE_PINS.items():
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('source changed; re-audit Host bound before use: ' + name)
    pairs = 12 * tokens * (tokens + 1) // 2
    counts = {
        'causal_head_query_key_pairs': pairs,
        'qk_matrix_requests': pairs * 8,
        'pv_matrix_requests': pairs * 8,
        'qk_reduction_scalar_adds': pairs * 16,
        'qk_scale_scalar_multiplies': pairs,
        'softmax_diff_exp_sum_scalar_requests': pairs * 3,
        'softmax_reciprocal_scalar_requests': 12 * tokens,
        'pv_probability_scalar_multiplies': pairs * 8,
        'two_norm_scalar_and_vector_issue_cycles': 3656 * tokens,
        'qkv_bias_vector_issue_cycles': 128 * tokens,
        'qk_rope_vector_issue_cycles': 336 * tokens,
        'two_residual_vector_issue_cycles': 192 * tokens,
        'silu_16_lane_primitive_issue_cycles': 3360 * tokens,
    }
    # The pairs item describes the iteration space, not an additional operation.
    non_dense = sum(v for k, v in counts.items() if k != 'causal_head_query_key_pairs')
    dense_ideal = (base['dense_useful_macs'] + 4095) // 4096
    matrix_only = dense_ideal + 16 * pairs
    ideal_dense_total = dense_ideal + non_dense
    current_dense = max(dense_ideal, base['weight_read_cycles_lower_bound'])
    total = current_dense + non_dense
    macs = base['total_useful_macs']
    return dict(schema_version=1, status='HOST_SOURCE_LOWER_BOUND_NOT_CYCLE_PREDICTION',
        workload=base['workload'], profile='Host real / 4096 MAC / pipelined / weight-read-beats16',
        scope=base['scope'], matrix_macs_per_cycle=4096, issue_counts=counts,
        useful_macs=macs, useful_macs_per_attention_matrix_request=16,
        attention_slice_mask=1, attention_requests_single_inflight=True,
        matrix_only_cycles_lower_bound=matrix_only,
        matrix_only_utilization_upper_bound=macs/(4096*matrix_only),
        non_dense_cycles_lower_bound=non_dense,
        ideal_dense_cycles_lower_bound=dense_ideal,
        ideal_dense_whole_block_cycles_lower_bound=ideal_dense_total,
        ideal_dense_whole_block_utilization_upper_bound=macs/(4096*ideal_dense_total),
        current_dense_cycles_lower_bound=current_dense,
        whole_block_cycles_lower_bound=total,
        useful_utilization_upper_bound=macs/(4096*total),
        predicted_full_block_cycles=None, rtl_measured_cycles=None, rtl_measured_utilization=None,
        assumptions=['valid successful complete cold Host block; all stages execute',
            'one cycle per Matrix/scalar/vector request, including div and exp',
            'current QK diagonal/PV row0 mapping; only sixteen useful MAC per request',
            'current sixteen-lane Vector/OverlappedSiLU, not autonomous scalar SiLU',
            'owners serialize; OverlappedSiLU only overlaps memory inside its owner',
            'Dense lower bound reuses the fixed single-read-port weight bound'],
        omitted_costs=['actual arithmetic latency and request/result handshakes',
            'non-Dense memory traffic, KV copy, descriptors and final ACKs',
            'Dense activation/output traffic and all pipeline setup/drain'],
        source_sha256={**base['source_sha256'], **HOST_SOURCE_PINS})


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--tokens',type=int,choices=(128,1024),default=128)
    p.add_argument('--weight-dtype',choices=('BF16','FP32'),default='BF16')
    p.add_argument('--host-schedule', action='store_true',
                   help='include the existing serialized Host arithmetic mapping as a strict lower bound')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    result=(host_schedule_report if args.host_schedule else report)(args.root,args.tokens,args.weight_dtype)
    text=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('x') as f:f.write(text)
    else:print(text,end='')


if __name__ == '__main__':
    main()
