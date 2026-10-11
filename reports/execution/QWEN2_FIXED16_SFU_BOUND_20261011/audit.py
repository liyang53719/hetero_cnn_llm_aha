#!/usr/bin/env python3
"""Read-only gate statistics and source/FSM bounds; no forward, build or RTL."""
from pathlib import Path
import hashlib
import json
import subprocess
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
SOURCES = [BASE + p for p in ('VectorSilu.scala', 'OverlappedSilu.scala',
    'BlockFloat.scala', 'QwenOwnerProtocol.scala', 'Qwen2Block.scala',
    'HostBlockTop.scala', 'StreamingDense.scala', 'DenseReadPlanner.scala',
    'MatrixPipeline.scala', 'RetainedMatrix.scala', 'BurstProtocol.scala')]
SOURCES += ['integration/gemmini/EmitHeteroFP32Alu.scala',
    'chisel/continuous_prefill/src/test/scala/heteronpu/continuous/BlockScalarFloatSpec.scala',
    'chisel/continuous_prefill/tests/qwen2_block.cpp',
    'scripts/qwen2_rectangular_attention_model.py',
    'scripts/qwen2_prefill_traffic_bound.py',
    'scripts/qwen2_block_recipe_model.py',
    'scripts/qwen2_bf16_materialization_candidate.py',
    'doc/QWEN2_PREFILL_RESIDENCY_AUDIT_20261011_CN.md']

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def sample(directory, collection, subdir, label):
    receipt = ROOT / directory / 'RESULT.json'
    report = json.loads(receipt.read_text())
    item = next(t for t in report[collection] if t['name'] == 'gate')
    path = receipt.parent / subdir / item['path']
    actual_hash = sha(path)
    assert actual_hash == item['sha256'], 'gate hash differs from saved receipt'
    values = np.fromfile(path, dtype='<f4')
    assert values.size == int(np.prod(item['shape'])) == 128 * 8960
    assert np.isfinite(values).all()
    groups = values.reshape(-1, 16)
    long_lane = np.abs(groups) < np.float32(80)
    n = len(groups)
    long = int(long_lane.any(axis=1).sum())
    return dict(label=label, saved_status=report['status'],
        saved_policy=report.get('policy', report.get('source_identity', {}).get('numerical_contract')),
        receipt=str(receipt.relative_to(ROOT)), receipt_sha256=sha(receipt),
        file=str(path.relative_to(ROOT)), sha256=actual_hash, expected_sha256=item['sha256'],
        hash_matches_receipt=True, shape=item['shape'], elements=int(values.size),
        finite=True, min=float(values.min()), max=float(values.max()),
        max_abs=float(np.abs(values).max()), groups_of_16=n,
        groups_any_abs_lt80=long, groups_all_abs_ge80=n-long,
        long_group_fraction=long/n, elements_abs_lt80=int(long_lane.sum()),
        silu_first_request_to_last_result_edge_span_lower_bound=21*n+17*long-1,
        hardware_branch_execution_verified=False, numerical_acceptance=False)

samples = [
    sample('work/qwen2_block_recipe_m128_release_20261011', 'stages', '.',
           'saved original ordered software recipe; not RTL'),
    sample('work/qwen2_bf16_candidate_v1_m128_final_20261011', 'tensors', 'tensors',
           'unapproved BF16 materialization-v1 diagnostic; not v0 hardware evidence')]

def bound(m):
    n = m*8960//16
    dense = m*46792704//4096
    pairs = 12*m*(m+1)//2
    full_ideal = dense + pairs//16
    universal = 21*n-1
    # All-long M1024 is only a conditional scenario; no M1024 array was read.
    all_long = 38*n-1
    relaxed = 7*n-1
    return dict(tokens=m, silu_groups=n, ideal_dense_cycles=dense,
        full_useful_macs=4096*full_ideal, full_ideal_4096_mac_cycles=full_ideal,
        full_cycle_budget_at_80_percent=full_ideal/0.8,
        universal_successful_silu_cycles_lower_bound=universal,
        universal_dense_plus_silu_lower_bound=dense+universal,
        universal_full_utilization_upper_bound=full_ideal/(dense+universal),
        all_long_silu_cycles_lower_bound=all_long,
        all_long_dense_plus_silu_lower_bound=dense+all_long,
        all_long_full_utilization_upper_bound=full_ideal/(dense+all_long),
        all_long_silu_only_full_utilization_upper_bound=full_ideal/all_long,
        all_long_branch_source='both saved arrays' if m==128 else 'conditional only; no array read',
        relaxed_exp_div_only_sfu_service_lower_bound=relaxed,
        relaxed_dense_plus_exp_div_only_upper_bound=full_ideal/(dense+relaxed))

result = dict(schema=1, status='SOURCE_BOUND_AND_SAVED_ARRAY_STATISTICS_NOT_RTL',
    source_git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    source_sha256={p:sha(ROOT/p) for p in SOURCES}, audit_script_sha256=sha(Path(__file__)),
    scope=dict(production_sources_changed=False, forward_executed=False,
        build_or_tests_executed=False, rtl_executed=False, new_weights=False,
        statistics_only=True, predicted_full_block_cycles=None, measured_cycles=None),
    primitive_minimum_intervals=dict(add_mul_request_ii=3, saturated_exp_request_ii=3,
        nonsaturated_exp_request_ii=20, divider_request_ii_lower_bound=4,
        exact_divider_latency_assumed=False),
    vector_wrapper=dict(phases=['ExpNegative','Add','Div','Mul','Mul','Mul'],
        source='VectorSilu.scala:27-67; BlockFloat.scala:39,55-108',
        saturated_successful_group_ii_lower_bound=21,
        any_nonsaturated_successful_group_ii_lower_bound=38,
        formula='21*N + 17*L - 1; first vector request.fire edge to last result.fire edge',
        timeline_all_long_minimum=dict(vector_request=0, exp_request=1, exp_result=20,
            add_request=21, add_result=23, div_request=24, div_result_earliest=27,
            mul1_request=28, mul1_result=30, mul2_request=31, mul2_result=33,
            mul3_request=34, mul3_result=36, vector_result=37, next_vector_request=38)),
    assumptions=[
        'Successful complete block: error-shortened execution is not accepted performance.',
        'Exactly the current 16 BlockScalarFloat cores and six-phase SiluVectorUnit wrapper.',
        'Both VectorSiluOwner and OverlappedSiluOwner use this same unit; memory overlap does not overlap separate vector jobs.',
        'Dense and Activation retain current exclusive Kernel active/mode scheduling when their bounds are summed.',
        'All other block stages, DMA, queues, loads/stores, ACKs, and precise divider delays are omitted.',
        'Finite inputs do not prove numerical success under legacy underflow rejection; no scalar status was simulated.',
        'The saved BF16-v1 gate distribution is not evidence that v0 RTL uses those values.',
        'Relaxed exp/div-only bound additionally permits all four Add/Mul phases and wrapper overhead to be free; existing scalar FSMs/16 lanes and owner serialization remain fixed.',
        'These bounds do not prove impossibility for all future 16-SFU microarchitectures with changed core FSMs, interfaces or owner overlap.'
    ], samples=samples, bounds=[bound(128),bound(1024)])
target = OUT/'RESULT.json'
with target.open('x') as f:
    json.dump(result,f,indent=2,allow_nan=False)
    f.write('\n')
print(json.dumps(dict(output=str(target),sha256=sha(target),samples=[dict(label=s['label'],
    groups=s['groups_of_16'],long_groups=s['groups_any_abs_lt80'],max_abs=s['max_abs']) for s in samples],
    bounds=result['bounds']),indent=2))
