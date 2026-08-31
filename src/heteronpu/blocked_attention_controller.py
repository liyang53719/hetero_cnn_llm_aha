"""Executable protocol reference for the L5.3 blocked-Attention stream controller.

This model is deliberately narrower than the numerical Attention Golden. It
freezes command ordering and ready/valid behaviour for the shared Matrix path
(QK and PV), the score FIFO, the SFU path and the probability FIFO. The model
never materializes score or probability tensors in DDR.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random


@dataclass(frozen=True)
class Geometry:
    sequence_tokens: int
    query_tile: int = 16
    kv_tile: int = 32
    q_heads: int = 12
    kv_heads: int = 2
    block_tokens: int = 128
    score_fifo_depth: int = 2
    probability_fifo_depth: int = 2

    def __post_init__(self) -> None:
        if self.sequence_tokens <= 0:
            raise ValueError("sequence_tokens")
        if self.q_heads % self.kv_heads:
            raise ValueError("GQA head ratio")
        if self.block_tokens % self.kv_tile:
            raise ValueError("block must contain an integer number of KV tiles")
        if min(self.score_fifo_depth, self.probability_fifo_depth) < 2:
            raise ValueError("first RTL contract requires at least two FIFO entries")

    @property
    def query_tiles(self) -> int:
        return math.ceil(self.sequence_tokens / self.query_tile)

    @property
    def gqa_ratio(self) -> int:
        return self.q_heads // self.kv_heads


@dataclass(frozen=True)
class Microtask:
    task_id: int
    query_tile_index: int
    kv_tile_index: int
    q_head: int
    kv_head: int
    valid_query_rows: int
    close_summary_block: bool
    merge_with_global: bool
    last_kv_tile_for_q_head: bool

    @property
    def summary_merge_rows(self) -> int:
        return self.valid_query_rows if self.merge_with_global else 0


def build_microtasks(geometry: Geometry) -> tuple[Microtask, ...]:
    tasks: list[Microtask] = []
    task_id = 0
    tiles_per_block = geometry.block_tokens // geometry.kv_tile
    for query_tile_index in range(geometry.query_tiles):
        query_base = query_tile_index * geometry.query_tile
        valid_rows = min(geometry.query_tile, geometry.sequence_tokens - query_base)
        causal_limit = min(geometry.sequence_tokens, (query_tile_index + 1) * geometry.query_tile)
        kv_tiles = math.ceil(causal_limit / geometry.kv_tile)
        for q_head in range(geometry.q_heads):
            for kv_tile_index in range(kv_tiles):
                last = kv_tile_index + 1 == kv_tiles
                closes = ((kv_tile_index + 1) % tiles_per_block == 0) or last
                block_index = kv_tile_index // tiles_per_block
                tasks.append(Microtask(task_id, query_tile_index, kv_tile_index, q_head,
                    q_head // geometry.gqa_ratio, valid_rows, closes,
                    closes and block_index > 0, last))
                task_id += 1
    return tuple(tasks)


@dataclass(frozen=True)
class ServiceConfig:
    matrix_cycles: int = 128
    sfu_base_cycles: int = 16
    sfu_merge_cycles_per_row: int = 2
    matrix_stall_probability: float = 0.0
    sfu_stall_probability: float = 0.0
    matrix_command_block_probability: float = 0.0
    sfu_command_block_probability: float = 0.0

    def __post_init__(self) -> None:
        if min(self.matrix_cycles, self.sfu_base_cycles) <= 0:
            raise ValueError("service cycles")
        for probability in (self.matrix_stall_probability, self.sfu_stall_probability,
                            self.matrix_command_block_probability, self.sfu_command_block_probability):
            if not 0.0 <= probability < 1.0:
                raise ValueError("probability")


@dataclass
class _EngineJob:
    kind: str
    task: Microtask
    remaining: int
    output_pending: bool = False


@dataclass(frozen=True)
class ProtocolResult:
    status: str
    cycles: int
    total_tasks: int
    qk_issued: int
    qk_completed: int
    sfu_issued: int
    sfu_completed: int
    pv_issued: int
    pv_completed: int
    summary_merge_rows: int
    max_score_fifo: int
    max_probability_fifo: int
    matrix_qk_commands: int
    matrix_pv_commands: int
    matrix_switches: int
    matrix_idle_cycles: int
    protocol_errors: int
    score_ddr_bytes: int
    probability_ddr_bytes: int
    completion_sha256: str


class ControllerModel:
    def __init__(self, geometry: Geometry, service: ServiceConfig = ServiceConfig(), *, seed: int = 0xA77E) -> None:
        self.geometry = geometry
        self.service = service
        self.rng = random.Random(seed)
        self.tasks = build_microtasks(geometry)

    def run(self, max_cycles_factor: float = 8.0) -> ProtocolResult:
        score_fifo: deque[Microtask] = deque()
        probability_fifo: deque[Microtask] = deque()
        next_qk = 0
        matrix_job: _EngineJob | None = None
        sfu_job: _EngineJob | None = None
        cycles = 0
        qk_completed = sfu_issued = sfu_completed = pv_issued = pv_completed = 0
        merge_rows = protocol_errors = matrix_switches = matrix_idle = 0
        last_matrix_kind: str | None = None
        max_score = max_probability = 0
        completion_ids: list[int] = []
        deadline = max(10_000, int(len(self.tasks) * (2 * self.service.matrix_cycles + self.service.sfu_base_cycles) * max_cycles_factor))

        while pv_completed < len(self.tasks):
            cycles += 1
            if cycles > deadline:
                raise RuntimeError("blocked-Attention controller deadlock")
            if matrix_job is not None and not matrix_job.output_pending:
                if self.rng.random() >= self.service.matrix_stall_probability:
                    matrix_job.remaining -= 1
                    if matrix_job.remaining == 0:
                        matrix_job.output_pending = True
            if matrix_job is not None and matrix_job.output_pending:
                if matrix_job.kind == "qk":
                    if len(score_fifo) < self.geometry.score_fifo_depth:
                        score_fifo.append(matrix_job.task); qk_completed += 1; matrix_job = None
                elif matrix_job.kind == "pv":
                    completion_ids.append(matrix_job.task.task_id); pv_completed += 1; matrix_job = None
                else:
                    raise AssertionError(matrix_job.kind)
            if sfu_job is not None and not sfu_job.output_pending:
                if self.rng.random() >= self.service.sfu_stall_probability:
                    sfu_job.remaining -= 1
                    if sfu_job.remaining == 0:
                        sfu_job.output_pending = True
            if sfu_job is not None and sfu_job.output_pending:
                if len(probability_fifo) < self.geometry.probability_fifo_depth:
                    probability_fifo.append(sfu_job.task); sfu_completed += 1
                    merge_rows += sfu_job.task.summary_merge_rows; sfu_job = None
            if sfu_job is None and score_fifo and self.rng.random() >= self.service.sfu_command_block_probability:
                task = score_fifo.popleft()
                duration = self.service.sfu_base_cycles + (task.valid_query_rows * self.service.sfu_merge_cycles_per_row if task.merge_with_global else 0)
                sfu_job = _EngineJob("sfu", task, duration); sfu_issued += 1
            if matrix_job is None:
                generator_done = next_qk >= len(self.tasks)
                score_pressure = len(score_fifo) >= self.geometry.score_fifo_depth - 1
                select_pv = bool(probability_fifo) and (score_pressure or generator_done)
                issued = False
                if select_pv and self.rng.random() >= self.service.matrix_command_block_probability:
                    task = probability_fifo.popleft(); matrix_job = _EngineJob("pv", task, self.service.matrix_cycles); pv_issued += 1; issued = True
                elif not generator_done and len(score_fifo) < self.geometry.score_fifo_depth and self.rng.random() >= self.service.matrix_command_block_probability:
                    task = self.tasks[next_qk]; next_qk += 1; matrix_job = _EngineJob("qk", task, self.service.matrix_cycles); issued = True
                elif probability_fifo and self.rng.random() >= self.service.matrix_command_block_probability:
                    task = probability_fifo.popleft(); matrix_job = _EngineJob("pv", task, self.service.matrix_cycles); pv_issued += 1; issued = True
                if issued and matrix_job is not None:
                    if last_matrix_kind is not None and last_matrix_kind != matrix_job.kind:
                        matrix_switches += 1
                    last_matrix_kind = matrix_job.kind
                else:
                    matrix_idle += 1
            max_score = max(max_score, len(score_fifo)); max_probability = max(max_probability, len(probability_fifo))

        if completion_ids != list(range(len(self.tasks))): protocol_errors += 1
        if qk_completed != len(self.tasks) or sfu_issued != len(self.tasks) or sfu_completed != len(self.tasks) or pv_issued != len(self.tasks): protocol_errors += 1
        if merge_rows != self.expected_summary_merge_rows(): protocol_errors += 1
        digest = hashlib.sha256(b"".join(task_id.to_bytes(4, "little") for task_id in completion_ids)).hexdigest()
        return ProtocolResult("PASS" if protocol_errors == 0 else "FAIL", cycles, len(self.tasks), len(self.tasks), qk_completed,
            sfu_issued, sfu_completed, pv_issued, pv_completed, merge_rows, max_score, max_probability,
            len(self.tasks), len(self.tasks), matrix_switches, matrix_idle, protocol_errors, 0, 0, digest)

    def expected_summary_merge_rows(self) -> int:
        return self.geometry.q_heads * sum(token // self.geometry.block_tokens for token in range(self.geometry.sequence_tokens))


def protocol_report() -> dict[str, object]:
    cases: dict[str, object] = {}
    for sequence in (128, 384, 1024):
        geometry = Geometry(sequence)
        nominal = ControllerModel(geometry).run()
        stressed = ControllerModel(geometry, ServiceConfig(matrix_cycles=16, sfu_base_cycles=4,
            sfu_merge_cycles_per_row=1, matrix_stall_probability=0.02, sfu_stall_probability=0.05,
            matrix_command_block_probability=0.03, sfu_command_block_probability=0.04), seed=sequence * 17).run(max_cycles_factor=16)
        cases[str(sequence)] = {"nominal": asdict(nominal), "stressed": asdict(stressed),
            "expected_summary_merge_rows": ControllerModel(geometry).expected_summary_merge_rows()}
    payload = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    return {"schema_version": 1,
        "status": "PASS" if all(case[mode]["status"] == "PASS" for case in cases.values() for mode in ("nominal", "stressed")) else "FAIL",
        "evidence_class": "controller_protocol_E0_not_RTL_E1",
        "frozen": {"query_tile": 16, "kv_tile": 32, "block_tokens": 128, "q_heads": 12, "kv_heads": 2,
            "score_fifo_depth": 2, "probability_fifo_depth": 2, "shared_matrix_QK_PV": True,
            "score_DDR_bytes": 0, "probability_DDR_bytes": 0},
        "cases": cases, "sha256": hashlib.sha256(payload).hexdigest(),
        "remaining_local_gates": ["SystemVerilog_elaboration", "RTL_ready_valid_E1", "RTL_vs_numeric_Golden_E2", "Revision8B_B_measured_service_curve"]}
