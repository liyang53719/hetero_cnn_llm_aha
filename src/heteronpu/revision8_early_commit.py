from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import re
from pathlib import Path
from typing import Optional

MASK32 = (1 << 32) - 1


@dataclass(frozen=True)
class Request:
    context: int
    clear: bool
    last: bool
    delta: int


@dataclass(frozen=True)
class Item:
    context: int
    last: bool
    value: int


@dataclass(frozen=True)
class PublicView:
    in_ready: bool
    out_valid: bool
    out_context: int
    out_last: bool
    out_value: int
    busy: tuple[bool, ...]
    valid: tuple[bool, ...]
    accepted: int
    completed: int


class Model:
    """Elastic four-stage context accumulator model.

    early_commit=False models Revision 7 completion-handshake bank update and
    same-cycle data bypass.  early_commit=True models Revision 8A: the four
    context banks are the output-stage registers and are written when post
    advances into output.  Architectural busy/valid/completion remain tied to
    the external output handshake.
    """

    def __init__(self, *, early_commit: bool, contexts: int = 4, latency: int = 4):
        if contexts != 4 or latency != 4:
            raise ValueError("frozen geometry")
        self.early_commit = early_commit
        self.contexts = contexts
        self.latency = latency
        self.pipe: list[Optional[Item]] = [None] * latency
        self.busy = [False] * contexts
        self.valid = [False] * contexts
        self.bank = [0] * contexts
        self.local_valid = [False] * contexts
        self.accepted = 0
        self.completed = 0
        self.early_writes = 0
        self.same_cycle_reuses = 0

    def _ready_chain(self, out_ready: bool) -> list[bool]:
        ready = [False] * self.latency
        ready[-1] = self.pipe[-1] is None or out_ready
        for stage in range(self.latency - 2, -1, -1):
            ready[stage] = self.pipe[stage] is None or ready[stage + 1]
        return ready

    def observe(self, request: Optional[Request], out_ready: bool) -> tuple[PublicView, bool, bool, list[bool]]:
        output = self.pipe[-1]
        completion = output is not None and out_ready
        same = bool(request is not None and completion and output.context == request.context)
        context_available = bool(request is not None and (not self.busy[request.context] or same))
        ready = self._ready_chain(out_ready)
        in_ready = bool(request is not None and context_available and ready[0])
        view = PublicView(
            in_ready=in_ready,
            out_valid=output is not None,
            out_context=output.context if output is not None else 0,
            out_last=output.last if output is not None else False,
            out_value=output.value if output is not None else 0,
            busy=tuple(self.busy),
            valid=tuple(self.valid),
            accepted=self.accepted,
            completed=self.completed,
        )
        return view, completion, same, ready

    def step(self, request: Optional[Request], out_ready: bool) -> tuple[PublicView, bool]:
        view, completion, same, ready = self.observe(request, out_ready)
        issue = bool(request is not None and view.in_ready)
        output = self.pipe[-1]

        if issue:
            assert request is not None
            if request.clear:
                base = 0
            elif self.early_commit:
                base = self.bank[request.context] if self.local_valid[request.context] else 0
            elif same:
                assert output is not None
                base = output.value
                self.same_cycle_reuses += 1
            elif self.valid[request.context]:
                base = self.bank[request.context]
            else:
                base = 0
            issued_item = Item(request.context, request.last, (base + request.delta) & MASK32)
        else:
            issued_item = None

        output_write_item = self.pipe[-2] if ready[-1] else None

        new_pipe = list(self.pipe)
        if ready[-1]:
            new_pipe[-1] = self.pipe[-2]
        for stage in range(self.latency - 2, 0, -1):
            if ready[stage]:
                new_pipe[stage] = self.pipe[stage - 1]
        if ready[0]:
            new_pipe[0] = issued_item

        if self.early_commit and output_write_item is not None:
            self.bank[output_write_item.context] = output_write_item.value
            self.local_valid[output_write_item.context] = True
            self.early_writes += 1

        if completion:
            assert output is not None
            if not self.early_commit:
                self.bank[output.context] = output.value
                self.local_valid[output.context] = True
            self.valid[output.context] = True
            self.busy[output.context] = False
            self.completed += 1

        if issue:
            assert request is not None
            self.busy[request.context] = True
            self.accepted += 1
            if same:
                self.same_cycle_reuses += int(self.early_commit)

        self.pipe = new_pipe
        return view, issue


def _public_tuple(view: PublicView) -> tuple[object, ...]:
    return (
        view.in_ready,
        view.out_valid,
        view.out_context,
        view.out_last,
        view.out_value,
        view.busy,
        view.valid,
        view.accepted,
        view.completed,
    )


def differential_stress(
    accepted_operations: int = 1_000_000,
    *,
    seed: int = 0x8A17C0DE,
    output_stall_probability: float = 0.27,
    input_bubble_probability: float = 0.19,
) -> dict[str, object]:
    if accepted_operations <= 0:
        raise ValueError("accepted_operations")
    rng = random.Random(seed)
    old = Model(early_commit=False)
    new = Model(early_commit=True)
    pending: Optional[Request] = None
    produced = 0
    cycles = 0
    compared_outputs = 0
    max_cycles = accepted_operations * 20 + 1000
    trace_hash = hashlib.sha256()

    while old.completed < accepted_operations:
        if cycles >= max_cycles:
            raise AssertionError("deadlock")
        cycles += 1
        if pending is None and produced < accepted_operations and rng.random() >= input_bubble_probability:
            context = rng.randrange(4)
            clear = (produced < 4) or (rng.random() < 0.015)
            pending = Request(
                context=context,
                clear=clear,
                last=(produced >= accepted_operations - 4),
                delta=(rng.getrandbits(16) + 1) & MASK32,
            )
        out_ready = rng.random() >= output_stall_probability

        old_view, old_issue = old.step(pending, out_ready)
        new_view, new_issue = new.step(pending, out_ready)
        if _public_tuple(old_view) != _public_tuple(new_view):
            raise AssertionError(
                f"public divergence cycle={cycles}\nold={old_view}\nnew={new_view}\npending={pending} out_ready={out_ready}"
            )
        if old_issue != new_issue:
            raise AssertionError("issue divergence")
        if old_view.out_valid and out_ready:
            compared_outputs += 1
            trace_hash.update(old_view.out_context.to_bytes(1, "little"))
            trace_hash.update(old_view.out_value.to_bytes(4, "little"))
            trace_hash.update(bytes([old_view.out_last]))
        if old_issue:
            produced += 1
            pending = None

    if old.bank != new.bank or old.valid != new.valid or old.busy != new.busy:
        raise AssertionError((old.bank, new.bank, old.valid, new.valid, old.busy, new.busy))
    if old.accepted != accepted_operations or new.accepted != accepted_operations:
        raise AssertionError("accepted count")
    if compared_outputs != accepted_operations:
        raise AssertionError("output count")

    return {
        "schema_version": 1,
        "status": "PASS",
        "candidate": "revision8A_early_context_bank_commit",
        "accepted_operations": accepted_operations,
        "compared_outputs": compared_outputs,
        "cycles": cycles,
        "contexts": 4,
        "feedback_latency_cycles": 4,
        "same_cycle_reuses": old.same_cycle_reuses,
        "early_bank_writes": new.early_writes,
        "public_cycle_exact": True,
        "final_state_equal": True,
        "output_trace_sha256": trace_hash.hexdigest(),
        "seed": seed,
        "output_stall_probability": output_stall_probability,
        "input_bubble_probability": input_bubble_probability,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(differential_stress(), indent=2, sort_keys=True))


def validate_candidate_sources(root: str | Path) -> dict[str, object]:
    root = Path(root)
    candidate = root / "rtl/matrix/candidates/rev8"
    paths = {
        "tag": candidate / "bf16_context_tag_pipeline4_rev8_candidate.sv",
        "lane": candidate / "bf16_context_fma_pipeline_lane4_rev8_candidate.sv",
        "cluster": candidate / "bf16_context_lane_cluster16_rev8_candidate.sv",
        "control": candidate / "bf16_outer_product_array_control_rev8_candidate.sv",
        "front": candidate / "bf16_context_front_control_rev8_candidate.sv",
        "top": candidate / "bf16_outer_product_context_array_rev8_candidate.sv",
    }
    errors: list[str] = []
    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            errors.append(f"missing:{path.relative_to(root)}")
            continue
        payload = path.read_bytes()
        texts[name] = payload.decode("utf-8")
        hashes[str(path.relative_to(root))] = hashlib.sha256(payload).hexdigest()
    if errors:
        return {"schema_version": 1, "status": "FAIL", "errors": errors, "hashes": hashes}

    tag = texts["tag"]
    lane = texts["lane"]
    cluster = texts["cluster"]
    control = texts["control"]
    front = texts["front"]
    top = texts["top"]

    required_tag = (
        "pre_context_q",
        "mul_context_q",
        "post_context_q",
        "output_context_q",
        "if (output_write_i) output_context_q <= post_context_q",
        "if (pre_write_i) pre_context_q <= issue_context_i",
    )
    required_lane = (
        "logic [31:0] accumulator_bank [0:3]",
        "bank_valid_q[issue_context_i]",
        "accumulator_bank[early_commit_context_i] <= round_out",
        "bank_valid_q[early_commit_context_i] <= 1'b1",
        "HeteroBF16FmaPre",
        "HeteroBF16FmaMul",
        "HeteroBF16FmaPost",
        "HeteroBF16FmaRound",
    )
    for needle in required_tag:
        if needle not in tag:
            errors.append(f"tag_missing:{needle}")
    for needle in required_lane:
        if needle not in lane:
            errors.append(f"lane_missing:{needle}")
    for forbidden in ("issue_bypass_i", "completion_fire_i"):
        if forbidden in lane or forbidden in cluster:
            errors.append(f"completion_path_reenters_lane:{forbidden}")
    for stage in ("HeteroBF16FmaPre", "HeteroBF16FmaMul", "HeteroBF16FmaPost", "HeteroBF16FmaRound"):
        if lane.count(stage) != 1:
            errors.append(f"stage_count:{stage}:{lane.count(stage)}")
    if "for (genvar lane = 0; lane < 16; lane++)" not in cluster:
        errors.append("cluster_not_16_lanes")
    if "for (genvar cluster = 0; cluster < 32; cluster++)" not in top:
        errors.append("top_not_32_clusters")
    for needle in ("bf16_context_scheduler4 scheduler", "bf16_outer_product_array_control_rev8_candidate array_control", "bf16_context_tag_pipeline4_rev8_candidate tags", "issue_bypass_unused"):
        if needle not in front:
            errors.append(f"front_missing:{needle}")
    if ".issue_bypass_i(" in top or ".issue_bypass_i(" in cluster or ".issue_bypass_i(" in lane:
        errors.append("bypass_connected_to_candidate_data_path")
    if "bf16_context_front_control_rev8_candidate front_control" not in top:
        errors.append("front_control_not_used")
    for needle in ("pre_valid_q", "mul_valid_q", "post_valid_q", "output_valid_q"):
        if needle not in control:
            errors.append(f"control_missing:{needle}")
    if "output_context_o != context_o" not in front:
        errors.append("tag_fifo_alignment_check_missing")

    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "candidate": "revision8A_early_context_bank_commit",
        "hashes": hashes,
        "contract": {
            "contexts": 4,
            "feedback_latency_cycles": 4,
            "lanes": 512,
            "clusters": 32,
            "lanes_per_cluster": 16,
            "front_control_joint_mapping": True,
            "completion_to_pre_combinational_path_removed": True,
            "generated_hardfloat_modified": False,
        },
        "errors": errors,
    }


def sandbox_approval_report(root: str | Path, *, primary_operations: int = 1_000_000) -> dict[str, object]:
    root = Path(root)
    primary = differential_stress(accepted_operations=primary_operations)
    additional: list[dict[str, object]] = []
    for index in range(20):
        result = differential_stress(
            accepted_operations=25_000,
            seed=0x80000000 + index,
            output_stall_probability=(index % 7) / 10,
            input_bubble_probability=(index % 5) / 12,
        )
        additional.append(
            {
                "seed": result["seed"],
                "cycles": result["cycles"],
                "same_cycle_reuses": result["same_cycle_reuses"],
                "output_trace_sha256": result["output_trace_sha256"],
            }
        )
    source = validate_candidate_sources(root)
    local_flow = validate_local_flow(root)
    status = "PASS" if source["status"] == "PASS" and local_flow["status"] == "PASS" else "FAIL"
    return {
        "schema_version": 1,
        "status": status,
        "decision": "APPROVE_REVISION8A_CANDIDATE_FOR_LOCAL_E1_E4" if status == "PASS" else "REJECT_SOURCE_CONTRACT",
        "candidate": "early_context_bank_commit_with_aligned_tag_pipeline_and_cluster16",
        "primary_differential": primary,
        "multi_seed": {
            "status": "PASS",
            "cases": len(additional),
            "accepted_operations": len(additional) * 25_000,
            "results": additional,
        },
        "rtl_static_contract": source,
        "local_flow_static_contract": local_flow,
        "remaining_local_gates": [
            "candidate_Verilator_1M_plus_random_E1",
            "candidate_RTL_vs_revision7_cycle_compare",
            "candidate_source_to_mapped_gate_compare_or_Formality",
            "candidate_lane_and_cluster_CLN22UL_1GHz_E4",
            "candidate_structural_H3_CLN22UL_1GHz_E4",
            "area_and_power_delta",
        ],
    }


def validate_local_flow(root: str | Path) -> dict[str, object]:
    root = Path(root)
    tcls = {
        "lane": root / "dc/synth_l5_bf16_context_lane_rev8a.tcl",
        "cluster16": root / "dc/synth_l5_bf16_context_cluster16_rev8a.tcl",
        "front": root / "dc/synth_l5_bf16_front_control_rev8a.tcl",
        "top": root / "dc/synth_l5_bf16_context_top_rev8a.tcl",
        "formality": root / "dc/formality_l5_context_lane_rev8a.tcl",
    }
    errors: list[str] = []
    hashes: dict[str, str] = {}
    for name, path in tcls.items():
        if not path.is_file():
            errors.append(f"missing_tcl:{name}")
            continue
        payload = path.read_bytes()
        text = payload.decode("utf-8")
        hashes[str(path.relative_to(root))] = hashlib.sha256(payload).hexdigest()
        for pattern, label in (
            (r"set_multicycle_path", "multicycle"),
            (r"compile_ultra[^\n]*-retime", "retime"),
            (r"optimize_registers", "retime_optimize_registers"),
            (r"set_false_path(?![^\n]*rst_ni)", "non_reset_false_path"),
        ):
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                errors.append(f"{name}:{label}")
        if name != "formality":
            for needle in ("CLOCK_PERIOD_NS", "set_clock_uncertainty 0.08", "set_input_delay 0.10", "set_output_delay 0.10", "set_load 0.02"):
                if needle not in text:
                    errors.append(f"{name}:missing:{needle}")
    if tcls["top"].is_file():
        top = tcls["top"].read_text()
        executable = "\n".join(line for line in top.splitlines() if not line.lstrip().startswith("#"))
        if re.search(r"^\s*compile(?:_ultra)?\b", executable, re.MULTILINE):
            errors.append("top_compile_forbidden")
        for needle in ("CLUSTER16_INSTANCES", "PHYSICAL_LANES", "COMPILE_COMMANDS=0"):
            if needle not in top:
                errors.append(f"top_missing:{needle}")
    scripts = (
        "scripts/run_l5_matrix_context_revision8a.sh",
        "scripts/run_l5_matrix_context_revision8a_compare.sh",
        "scripts/run_l5_matrix_context_revision8a_e1.sh",
        "scripts/run_l5_matrix_context_revision8a_adversarial_e1.sh",
        "scripts/run_l5_revision8a_gate_compare.sh",
        "scripts/summarize_l5_revision8a.py",
    )
    for relative in scripts:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing_script:{relative}")
        else:
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"schema_version": 1, "status": "PASS" if not errors else "FAIL", "errors": errors, "hashes": hashes}
