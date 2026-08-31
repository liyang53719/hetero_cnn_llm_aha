from heteronpu.l10_early_ppa import analyze_ppa, default_component_evidence, risk_class
from heteronpu.l5_evidence_boundary import audit_l5_boundary
from heteronpu.qwen2_payload_closure import build_plan, plan_report


def test_l10_risk_class_and_scenarios():
    report = analyze_ppa(default_component_evidence())
    assert report["status"] == "PASS_EARLY_PPA_PREFLIGHT_WITH_CRITICAL_MARGIN_RISK"
    assert report["minimum_margin"]["component"] == "attention_merge8"
    assert report["minimum_margin"]["margin_ps"] < 0.01
    assert "attention_merge8" in report["route_scenarios"]["one_ps"]["failing_components"]
    assert risk_class(0.00490451) == "VERY_LOW_SUB_5PS"


def test_l5_boundary_keeps_full_payload_open():
    full = {
        "status": "PASS_CYCLE_E3",
        "layers": 28,
        "sequence": 1024,
        "non_claims": ["not a 28-layer payload numerical simulation"],
    }
    cross = {
        "status": "PASS",
        "layers": 4,
        "non_claims": ["reference hidden snapshots anchor each layer; this is not a full q1024 payload RTL simulation"],
        "rtl": {"bf16_bit_exact": 7840},
    }
    final = {"remaining_local_gates": ["L5.6_full_model"]}
    report = audit_l5_boundary(full, cross, final)
    assert report["status"] == "PASS_BOUNDARY_NORMALIZED"
    assert report["subgates"]["L5.6d_full_28_layer_payload_numerical_RTL"] == "OPEN"


def test_l5_boundary_rejects_overclaim():
    full = {
        "status": "PASS_CYCLE_E3",
        "layers": 28,
        "sequence": 1024,
        "non_claims": ["not a 28-layer payload numerical simulation"],
    }
    cross = {
        "status": "PASS",
        "layers": 4,
        "non_claims": ["reference hidden snapshots anchor each layer; this is not a full q1024 payload RTL simulation"],
        "rtl": {"bf16_bit_exact": 7840},
    }
    report = audit_l5_boundary(full, cross, {"remaining_local_gates": []})
    assert report["status"] == "FAIL_BOUNDARY_INCONSISTENT"
    assert "final_validation_does_not_keep_full_payload_open" in report["errors"]


def test_payload_plan_covers_all_layers_and_phases():
    plan = build_plan()
    assert len(plan) == 168
    assert {item.layer for item in plan} == set(range(28))
    assert {item.continuity_group for item in plan} == set(range(7))
    report = plan_report(plan)
    assert report["status"] == "PASS_FULL_PAYLOAD_CLOSURE_PLAN"
    assert report["sample_values"] == 28 * 6 * 64
