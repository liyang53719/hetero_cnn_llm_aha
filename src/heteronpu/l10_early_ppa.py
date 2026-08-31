"""Evidence-aware L10 early-PPA preflight.

This module deliberately separates three levels of evidence:

* standalone/component synthesis;
* hierarchical/integrated synthesis;
* post-route/PVT/OCV/SAIF signoff.

Component areas are useful for risk screening but are not additive top-level
area unless ownership and hierarchy prove that the instances are disjoint.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ComponentEvidence:
    name: str
    stage: str
    wns_ns: float
    area: float
    evidence_class: str
    additive_group: str
    instances: int = 1
    unmapped: int = 0
    unresolved: int = 0
    blackboxes: int = 0
    notes: str = ""

    def validate(self) -> None:
        if not self.name or self.instances <= 0 or self.area < 0:
            raise ValueError(f"invalid component evidence: {self.name}")
        if min(self.unmapped, self.unresolved, self.blackboxes) < 0:
            raise ValueError(f"negative unresolved count: {self.name}")

    @property
    def margin_ps(self) -> float:
        return self.wns_ns * 1_000.0


@dataclass(frozen=True)
class RouteScenario:
    label: str
    degradation_ps: float


DEFAULT_SCENARIOS = (
    RouteScenario("one_ps", 1.0),
    RouteScenario("five_ps", 5.0),
    RouteScenario("ten_ps", 10.0),
    RouteScenario("twenty_ps", 20.0),
)


def risk_class(wns_ns: float) -> str:
    ps = wns_ns * 1_000.0
    if ps < 0:
        return "FAIL_TIMING"
    if ps < 0.1:
        return "CRITICAL_SUB_0P1PS"
    if ps < 1.0:
        return "EXTREME_SUB_1PS"
    if ps < 5.0:
        return "VERY_LOW_SUB_5PS"
    if ps < 20.0:
        return "LOW_SUB_20PS"
    return "SCREENING_MARGIN_GE_20PS"


def default_component_evidence() -> tuple[ComponentEvidence, ...]:
    """Accepted evidence currently present in main.

    The numbers are intentionally stored in one manifest so later local-agent
    results can replace them without editing the analysis algorithm.
    """
    return (
        ComponentEvidence(
            "block128_mlo", "L5.1", 0.0000136495, 0.0,
            "component_CLN22UL_DC", "attention_sfu", notes="area not frozen in current report",
        ),
        ComponentEvidence(
            "matrix_revision8b_b_h3", "L5.2", 0.00490451, 1_661_847.825806,
            "structural_H3_CLN22UL_DC", "matrix_cluster",
        ),
        ComponentEvidence(
            "attention_controller", "L5.3", 0.00191498, 1_773.408002,
            "component_CLN22UL_DC", "attention_control",
        ),
        ComponentEvidence(
            "block32_weight", "L5.3", 0.0000125766, 13_949.754056,
            "component_CLN22UL_DC", "attention_sfu",
        ),
        ComponentEvidence(
            "attention_tile16_8lane", "L5.5", 0.00011009, 277_390.658998,
            "component_CLN22UL_DC", "attention_sfu",
        ),
        ComponentEvidence(
            "attention_merge8", "L5.5", 0.00000864267, 357_614.802998,
            "component_CLN22UL_DC", "attention_sfu",
        ),
        ComponentEvidence(
            "silu_one_lane", "L5.4", 0.0000177622, 10_551.632033,
            "component_CLN22UL_DC", "mlp_sfu",
        ),
        ComponentEvidence(
            "refined_rsqrt", "L5.6", 0.000101328, 4_136.31403,
            "component_CLN22UL_DC", "norm_sfu",
        ),
    )


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def analyze_ppa(
    components: Iterable[ComponentEvidence],
    scenarios: Sequence[RouteScenario] = DEFAULT_SCENARIOS,
) -> dict[str, object]:
    items = tuple(components)
    if not items:
        raise ValueError("at least one component is required")
    for item in items:
        item.validate()

    records: list[dict[str, object]] = []
    for item in items:
        record = asdict(item)
        record.update(
            margin_ps=item.margin_ps,
            risk_class=risk_class(item.wns_ns),
            structural_clean=(item.unmapped == item.unresolved == item.blackboxes == 0),
        )
        records.append(record)

    additive_groups: dict[str, float] = {}
    for item in items:
        additive_groups[item.additive_group] = additive_groups.get(item.additive_group, 0.0) + item.area * item.instances

    scenario_results: dict[str, object] = {}
    for scenario in scenarios:
        failures = [item.name for item in items if item.margin_ps < scenario.degradation_ps]
        scenario_results[scenario.label] = {
            "degradation_ps": scenario.degradation_ps,
            "failing_components": failures,
            "failing_count": len(failures),
        }

    min_item = min(items, key=lambda item: item.wns_ns)
    critical = [item.name for item in items if item.margin_ps < 1.0]
    required_local_gates = [
        {
            "id": "L10.1_hierarchical_synthesis",
            "acceptance": [
                "integrated owner hierarchy is explicit",
                "no duplicate counting of precompiled subblocks",
                "WNS >= 0 ns at 1.0 ns clock",
                "unmapped/unresolved/blackbox = 0",
            ],
        },
        {
            "id": "L10.2_SRAM_macro_replacement",
            "acceptance": [
                "all inferred memories replaced or intentionally retained",
                "total macro capacity <= 4 MiB",
                "port/bank conflicts measured",
                "macro timing arcs included",
            ],
        },
        {
            "id": "L10.3_post_route_STA",
            "acceptance": [
                "setup and hold close across approved PVT/OCV corners",
                "clock-tree and extracted interconnect included",
                "transition/capacitance violations = 0",
                "non-reset data false paths = 0",
            ],
        },
        {
            "id": "L10.4_power",
            "acceptance": [
                "SAIF/VCD activity is workload-derived",
                "dynamic and leakage power reported separately",
                "vectorless DC power is not used as signoff evidence",
            ],
        },
    ]

    result: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS_EARLY_PPA_PREFLIGHT_WITH_CRITICAL_MARGIN_RISK",
        "evidence_class": "sandbox_manifest_and_sensitivity_not_local_synthesis_or_post_route",
        "components": records,
        "minimum_margin": {
            "component": min_item.name,
            "wns_ns": min_item.wns_ns,
            "margin_ps": min_item.margin_ps,
        },
        "critical_sub_1ps": critical,
        "additive_group_screening_area": additive_groups,
        "area_warning": "Group sums are screening estimates; they are not a top-level area claim.",
        "route_scenarios": scenario_results,
        "required_local_gates": required_local_gates,
        "decision": (
            "Proceed to bounded L10 hierarchical synthesis, but do not claim 1 GHz signoff. "
            "The accepted pre-layout margins are too small to absorb normal route/OCV degradation."
        ),
        "non_claims": [
            "not integrated-top area",
            "not post-route timing",
            "not PVT/OCV signoff",
            "not SAIF power",
        ],
    }
    result["sha256"] = _sha256_json(result)
    return result


def load_component_overrides(payload: Mapping[str, object]) -> tuple[ComponentEvidence, ...]:
    values = payload.get("components")
    if not isinstance(values, list):
        raise ValueError("components must be a list")
    return tuple(ComponentEvidence(**value) for value in values if isinstance(value, dict))
