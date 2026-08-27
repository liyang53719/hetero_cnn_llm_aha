from __future__ import annotations

import math
from pathlib import Path

from heteronpu.moe_router import ExpertWeights, execute_moe
from heteronpu.mtp import TransactionalLog, resolve_speculation
from heteronpu.qwen38_runtime import (
    TinyQwen38Config,
    TinyQwen38TextModel,
    trace_operator_set,
)
from heteronpu.qwen38_schedule import build_qwen38_schedule
from heteronpu.model_support import ModelProfile

ROOT = Path(__file__).resolve().parents[1]


def assert_close_tuple(lhs, rhs, atol=2e-6):
    assert len(lhs) == len(rhs)
    assert max(abs(a - b) for a, b in zip(lhs, rhs, strict=True)) <= atol


def test_qwen38_tiny_text_prefill_equals_incremental_decode():
    model = TinyQwen38TextModel.random(seed=3801)
    tokens = (1, 4, 7, 3, 9, 2, 11, 5)

    prefill, prefill_state = model.run(tokens)
    state = model.initial_state()
    incremental = []
    for token in tokens:
        result, state = model.step(token, state)
        incremental.append(result)

    assert prefill_state.token_index == state.token_index == len(tokens)
    for lhs, rhs in zip(prefill, incremental, strict=True):
        assert_close_tuple(lhs.hidden, rhs.hidden)
        assert lhs.qsa_selected == rhs.qsa_selected
        assert lhs.routes == rhs.routes

    selected_lengths = [len(row) for result in prefill for row in result.qsa_selected]
    assert selected_lengths
    assert selected_lengths[-1] < len(tokens)

    operators = trace_operator_set(prefill)
    expected = {
        'PLE_NGRAM_HASH_LOOKUP','PLE_GATE_DILATED_DWCONV','GDN_RECURRENT_STATE_UPDATE',
        'QSA_COMPRESS_TOPK','SPARSE_QK_ONLINE_SOFTMAX_PV','ATTENTION_OUTPUT_GATE_PROJECTION',
        'MOE_ROUTER_TOPK','MOE_ROUTED_EXPERT_GEMM','MOE_SHARED_EXPERT','GR_ATTN_READ','GR_MOE_WRITE',
    }
    assert expected <= operators


def test_qwen38_state_is_persistent_and_copy_isolation_holds():
    model = TinyQwen38TextModel.random(seed=3802)
    first, state = model.run((2, 6, 1, 8))
    checkpoint = state.copy()
    branch_a, state_a = model.run((3, 4), state)
    branch_b, state_b = model.run((9, 10), checkpoint)
    assert state_a.token_index == state_b.token_index == 6
    assert branch_a[-1].hidden != branch_b[-1].hidden
    assert checkpoint.token_index == 4
    qsa_a = next(layer.qsa for layer in state_a.layers if layer.qsa is not None)
    qsa_b = next(layer.qsa for layer in state_b.layers if layer.qsa is not None)
    assert len(qsa_a.keys) == len(qsa_b.keys) == 6
    assert qsa_a.keys[-1] != qsa_b.keys[-1]


def test_qwen38_moe_executes_routed_and_shared_paths():
    import random
    rng = random.Random(7)
    hidden = (0.2, -0.4, 0.1, 0.6)
    router = tuple(tuple(rng.uniform(-0.3, 0.3) for _ in hidden) for _ in range(4))
    experts = tuple(ExpertWeights.random(rng, 4, 3) for _ in range(4))
    shared = ExpertWeights.random(rng, 4, 3)
    gate = tuple(rng.uniform(-0.3, 0.3) for _ in hidden)
    result = execute_moe(hidden, router=router, experts=experts, top_k=2, shared_expert=shared, shared_gate=gate)
    assert len(result.routes) == 2
    assert math.isclose(sum(route.weight for route in result.routes), 1.0, rel_tol=0, abs_tol=2e-7)
    assert any(abs(x) > 0 for x in result.routed_output)
    assert any(abs(x) > 0 for x in result.shared_output)
    assert_close_tuple(result.output, tuple(a + b for a, b in zip(result.routed_output, result.shared_output, strict=True)), atol=2e-6)


def test_qwen38_mtp_transaction_commits_only_accepted_state():
    journal = TransactionalLog.empty()
    journal.committed.extend(('base0', 'base1'))
    checkpoint = journal.checkpoint()
    for value in ('draft10', 'draft11', 'draft12'): journal.append(value)
    resolution = resolve_speculation((10, 11, 12), (10, 11, 99), journal, checkpoint)
    assert resolution.verification.accepted == 2
    assert resolution.state_committed == ('draft10', 'draft11')
    assert journal.committed == ['base0', 'base1', 'draft10', 'draft11']
    assert journal.speculative == []


def test_qwen38_schedule_matches_executed_text_operator_inventory():
    profile = ModelProfile.load(ROOT / 'config/model_profiles/qwen3_8_flash_next.json')
    schedule = build_qwen38_schedule(profile.layer_pattern, ple_layer_ids=(1,), include_mtp=True)
    schedule.validate()
    model = TinyQwen38TextModel.random(seed=3803)
    results, _ = model.run((1, 2, 3, 4, 5, 6))
    executed = trace_operator_set(results)
    assert executed <= schedule.operator_names
    assert {'MTP_DRAFT_BLOCK', 'MTP_TARGET_VERIFY', 'MTP_STATE_COMMIT_ROLLBACK'} <= schedule.operator_names
    assert schedule.local_dependencies()


def test_qwen38_profile_has_official_text_geometry_and_executable_e0_claim():
    profile = ModelProfile.load(ROOT / 'config/model_profiles/qwen3_8_flash_next.json')
    assert profile.raw['hidden_size'] == 2560
    assert profile.raw['num_hidden_layers'] == 48
    assert profile.layer_pattern.count('linear_attention') == 36
    assert profile.layer_pattern.count('qwen_sparse_attention') == 12
    assert profile.raw['qsa']['token_budget'] == 2048
    assert profile.raw['moe']['top_k'] == 10
    assert profile.raw['gated_residual']['branches'] == 4


def test_qwen38_frozen_contract_matches_runtime_hashes():
    import hashlib,json,struct
    contract = json.loads((ROOT / 'config/qwen38_tiny_e0_contract.json').read_text())
    model = TinyQwen38TextModel.random(seed=contract['tiny_seed'])
    results, _ = model.run(contract['tokens'])
    def digest(attribute):
        h = hashlib.sha256()
        for result in results:
            for value in getattr(result, attribute): h.update(struct.pack('<f', float(value)))
        return h.hexdigest()
    assert digest('hidden') == contract['expected']['final_hidden_sha256']
    assert digest('hyper') == contract['expected']['final_hyper_sha256']
    assert len(trace_operator_set(results)) == contract['expected']['operator_types']


def test_gated_deltanet_chunk_prefill_matches_recurrent_reference():
    import random
    from heteronpu.gated_deltanet import Geometry, delta_rule_chunk, delta_rule_recurrent
    rng = random.Random(35);geometry = Geometry(qk_heads=1, v_heads=2, key_dim=2, value_dim=3);tokens = 7
    query = tuple((tuple(rng.uniform(-1, 1) for _ in range(2)),) for _ in range(tokens))
    key = tuple((tuple(rng.uniform(-1, 1) for _ in range(2)),) for _ in range(tokens))
    value = tuple(tuple(tuple(rng.uniform(-1, 1) for _ in range(3)) for _ in range(2)) for _ in range(tokens))
    log_decay = tuple(tuple(rng.uniform(-1.5, -0.05) for _ in range(2)) for _ in range(tokens))
    beta = tuple(tuple(rng.uniform(0.05, 0.95) for _ in range(2)) for _ in range(tokens))
    recurrent, recurrent_state = delta_rule_recurrent(geometry=geometry,query=query,key=key,value=value,log_decay=log_decay,beta=beta)
    chunked, chunked_state = delta_rule_chunk(geometry=geometry,query=query,key=key,value=value,log_decay=log_decay,beta=beta,chunk_size=4)
    max_output_error = max(abs(a-b) for ta,tb in zip(recurrent,chunked,strict=True) for ha,hb in zip(ta,tb,strict=True) for a,b in zip(ha,hb,strict=True))
    max_state_error = max(abs(a-b) for ha,hb in zip(recurrent_state.data,chunked_state.data,strict=True) for ra,rb in zip(ha,hb,strict=True) for a,b in zip(ra,rb,strict=True))
    assert max_output_error < 2e-5
    assert max_state_error < 2e-5
