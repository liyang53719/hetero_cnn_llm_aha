"""Discrete-event preflight model for the L5.5 Matrix/SFU/DMA/DDR join.

The model schedules a dependency graph onto bounded Matrix, SFU, control,
read-DMA and write-DMA resources with shared-SRAM bank masks. It produces the
local E3 test matrix and catches impossible overlap plans before RTL
integration. It is not measured E3 evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import heapq
import math
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SystemConfig:
    clock_hz: int = 1_000_000_000
    matrix_macs_per_cycle: int = 512
    sfu_lanes: int = 16
    ddr_read_bytes_per_cycle: float = 100.0
    ddr_write_bytes_per_cycle: float = 40.0
    read_dma_channels: int = 2
    write_dma_channels: int = 1
    sram_banks: int = 16
    command_overhead_cycles: int = 4

    def __post_init__(self) -> None:
        if min(
            self.clock_hz,
            self.matrix_macs_per_cycle,
            self.sfu_lanes,
            self.read_dma_channels,
            self.write_dma_channels,
            self.sram_banks,
        ) <= 0:
            raise ValueError("positive system geometry required")
        if self.ddr_read_bytes_per_cycle <= 0 or self.ddr_write_bytes_per_cycle <= 0:
            raise ValueError("positive DDR bandwidth required")


@dataclass(frozen=True)
class Task:
    name: str
    resource: str
    dependencies: tuple[str, ...] = ()
    compute_cycles: int = 0
    read_bytes: int = 0
    write_bytes: int = 0
    bank_mask: int = 0
    metadata: tuple[tuple[str, int | float | str], ...] = ()

    def __post_init__(self) -> None:
        if not self.name or self.resource not in {
            "matrix",
            "sfu",
            "control",
            "dma_read",
            "dma_write",
        }:
            raise ValueError(f"invalid task {self.name}")
        if min(
            self.compute_cycles,
            self.read_bytes,
            self.write_bytes,
            self.bank_mask,
        ) < 0:
            raise ValueError("negative task cost")


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    resource: str
    start: int
    finish: int
    duration: int
    bank_mask: int


@dataclass(frozen=True)
class ScheduleResult:
    cycles: int
    tasks: tuple[ScheduledTask, ...]
    resource_busy: Mapping[str, int]
    max_concurrent_banks: int
    critical_chain: tuple[str, ...]
    status: str = "PASS"


class TaskGraph:
    def __init__(self, tasks: Iterable[Task]) -> None:
        self.tasks = tuple(tasks)
        self.by_name = {task.name: task for task in self.tasks}
        if len(self.by_name) != len(self.tasks):
            raise ValueError("duplicate task")
        self.index = {task.name: index for index, task in enumerate(self.tasks)}
        for task in self.tasks:
            missing = set(task.dependencies) - set(self.by_name)
            if missing:
                raise ValueError(
                    f"missing dependencies for {task.name}: {sorted(missing)}"
                )
            if any(
                self.index[dependency] >= self.index[task.name]
                for dependency in task.dependencies
            ):
                raise ValueError(f"non-topological task order at {task.name}")


class SystemScheduler:
    def __init__(self, config: SystemConfig) -> None:
        self.config = config

    def duration(self, task: Task) -> int:
        if task.resource == "dma_read":
            bandwidth = (
                self.config.ddr_read_bytes_per_cycle
                / self.config.read_dma_channels
            )
            return self.config.command_overhead_cycles + math.ceil(
                task.read_bytes / bandwidth
            )
        if task.resource == "dma_write":
            bandwidth = (
                self.config.ddr_write_bytes_per_cycle
                / self.config.write_dma_channels
            )
            return self.config.command_overhead_cycles + math.ceil(
                task.write_bytes / bandwidth
            )
        return max(1, task.compute_cycles + self.config.command_overhead_cycles)

    def schedule(self, graph: TaskGraph) -> ScheduleResult:
        capacity = {
            "matrix": 1,
            "sfu": 1,
            "control": 1,
            "dma_read": self.config.read_dma_channels,
            "dma_write": self.config.write_dma_channels,
        }
        active: list[tuple[int, int, Task]] = []
        running_by_resource = {name: 0 for name in capacity}
        running_bank_mask = 0
        completed: dict[str, int] = {}
        scheduled: list[ScheduledTask] = []
        resource_busy = {name: 0 for name in capacity}
        unscheduled = list(graph.tasks)
        cycle = 0
        serial = 0
        max_concurrent_banks = 0
        predecessor: dict[str, str | None] = {}

        while unscheduled or active:
            while active and active[0][0] <= cycle:
                finish, _, task = heapq.heappop(active)
                running_by_resource[task.resource] -= 1
                completed[task.name] = finish
                running_bank_mask = 0
                for _, _, other in active:
                    running_bank_mask |= other.bank_mask

            launched = True
            while launched:
                launched = False
                for index, task in enumerate(unscheduled):
                    if any(dependency not in completed for dependency in task.dependencies):
                        continue
                    if running_by_resource[task.resource] >= capacity[task.resource]:
                        continue
                    if task.bank_mask & running_bank_mask:
                        continue
                    duration = self.duration(task)
                    finish = cycle + duration
                    serial += 1
                    heapq.heappush(active, (finish, serial, task))
                    running_by_resource[task.resource] += 1
                    running_bank_mask |= task.bank_mask
                    resource_busy[task.resource] += duration
                    scheduled.append(
                        ScheduledTask(
                            task.name,
                            task.resource,
                            cycle,
                            finish,
                            duration,
                            task.bank_mask,
                        )
                    )
                    predecessor[task.name] = max(
                        task.dependencies,
                        key=lambda name: completed[name],
                        default=None,
                    )
                    unscheduled.pop(index)
                    max_concurrent_banks = max(
                        max_concurrent_banks,
                        running_bank_mask.bit_count(),
                    )
                    launched = True
                    break

            if unscheduled and not active:
                raise RuntimeError("scheduler deadlock")
            if active:
                cycle = min(finish for finish, _, _ in active)

        total_cycles = max(completed.values(), default=0)
        end_task = max(scheduled, key=lambda item: item.finish).name if scheduled else None
        critical_chain: list[str] = []
        while end_task is not None:
            critical_chain.append(end_task)
            end_task = predecessor[end_task]
        return ScheduleResult(
            total_cycles,
            tuple(scheduled),
            resource_busy,
            max_concurrent_banks,
            tuple(reversed(critical_chain)),
        )


HIDDEN = 1536
INTERMEDIATE = 8960
Q_OUTPUT = 1536
KV_OUTPUT = 256


def _matrix_cycles(macs: int, config: SystemConfig) -> int:
    return math.ceil(macs / config.matrix_macs_per_cycle)


def build_qwen2_block(sequence: int, config: SystemConfig) -> TaskGraph:
    if sequence <= 0:
        raise ValueError("sequence")
    qkv_macs = sequence * HIDDEN * (Q_OUTPUT + 2 * KV_OUTPUT)
    output_projection_macs = sequence * HIDDEN * HIDDEN
    gate_up_macs = sequence * HIDDEN * (2 * INTERMEDIATE)
    down_macs = sequence * INTERMEDIATE * HIDDEN
    query_tiles = math.ceil(sequence / 16)
    query_key_pairs = sum(
        math.ceil(min(sequence, (tile + 1) * 16) / 32)
        for tile in range(query_tiles)
    )
    head_microtiles = query_key_pairs * 12
    qk_pv_each = head_microtiles * 128
    softmax_cycles = (
        head_microtiles * 16
        + 12 * sum(token // 128 for token in range(sequence)) * 32
    )
    weight_bytes = {
        "qkv": HIDDEN * (Q_OUTPUT + 2 * KV_OUTPUT) * 2,
        "oproj": HIDDEN * HIDDEN * 2,
        "gate_up": HIDDEN * (2 * INTERMEDIATE) * 2,
        "down": INTERMEDIATE * HIDDEN * 2,
    }
    bank_mask = lambda *indices: sum(1 << index for index in indices)
    return TaskGraph(
        (
            Task(
                "input_norm",
                "sfu",
                compute_cycles=math.ceil(sequence * HIDDEN / config.sfu_lanes),
                bank_mask=bank_mask(0, 1),
            ),
            Task(
                "qkv_weight",
                "dma_read",
                read_bytes=weight_bytes["qkv"],
                bank_mask=bank_mask(4, 5),
            ),
            Task(
                "qkv_matrix",
                "matrix",
                ("input_norm", "qkv_weight"),
                _matrix_cycles(qkv_macs, config),
                bank_mask=bank_mask(0, 1, 4, 5),
            ),
            Task(
                "rope",
                "sfu",
                ("qkv_matrix",),
                math.ceil(sequence * (Q_OUTPUT + KV_OUTPUT) / config.sfu_lanes),
                bank_mask=bank_mask(2, 3),
            ),
            Task(
                "kv_append",
                "dma_write",
                ("rope",),
                write_bytes=sequence * 2 * KV_OUTPUT * 2,
                bank_mask=bank_mask(2, 3),
            ),
            Task(
                "attention_qk",
                "matrix",
                ("rope",),
                qk_pv_each,
                bank_mask=bank_mask(0, 6, 7),
            ),
            Task(
                "attention_softmax",
                "sfu",
                ("attention_qk",),
                softmax_cycles,
                bank_mask=bank_mask(6, 7),
            ),
            Task(
                "attention_pv",
                "matrix",
                ("attention_softmax",),
                qk_pv_each,
                bank_mask=bank_mask(0, 6, 7),
            ),
            Task(
                "oproj_weight",
                "dma_read",
                ("qkv_weight",),
                read_bytes=weight_bytes["oproj"],
                bank_mask=bank_mask(4, 5),
            ),
            Task(
                "oproj_matrix",
                "matrix",
                ("attention_pv", "oproj_weight"),
                _matrix_cycles(output_projection_macs, config),
                bank_mask=bank_mask(0, 4, 5),
            ),
            Task(
                "residual_1",
                "sfu",
                ("oproj_matrix",),
                math.ceil(sequence * HIDDEN / config.sfu_lanes),
                bank_mask=bank_mask(0, 1),
            ),
            Task(
                "ffn_norm",
                "sfu",
                ("residual_1",),
                math.ceil(sequence * HIDDEN / config.sfu_lanes),
                bank_mask=bank_mask(0, 1),
            ),
            Task(
                "gateup_weight",
                "dma_read",
                ("oproj_weight",),
                read_bytes=weight_bytes["gate_up"],
                bank_mask=bank_mask(4, 5),
            ),
            Task(
                "gateup_matrix",
                "matrix",
                ("ffn_norm", "gateup_weight"),
                _matrix_cycles(gate_up_macs, config),
                bank_mask=bank_mask(0, 1, 4, 5),
            ),
            Task(
                "silu_product",
                "sfu",
                ("gateup_matrix",),
                sequence * INTERMEDIATE,
                bank_mask=bank_mask(2, 3),
            ),
            Task(
                "down_weight",
                "dma_read",
                ("gateup_weight",),
                read_bytes=weight_bytes["down"],
                bank_mask=bank_mask(4, 5),
            ),
            Task(
                "down_matrix",
                "matrix",
                ("silu_product", "down_weight"),
                _matrix_cycles(down_macs, config),
                bank_mask=bank_mask(0, 2, 3, 4, 5),
            ),
            Task(
                "residual_2",
                "sfu",
                ("down_matrix",),
                math.ceil(sequence * HIDDEN / config.sfu_lanes),
                bank_mask=bank_mask(0, 1),
            ),
        )
    )


def system_preflight_report(sequence: int = 1024) -> dict[str, object]:
    sweep: dict[str, object] = {}
    for read_bandwidth in (50.0, 75.0, 100.0):
        for banks in (8, 16, 32):
            config = SystemConfig(
                ddr_read_bytes_per_cycle=read_bandwidth,
                sram_banks=banks,
            )
            result = SystemScheduler(config).schedule(
                build_qwen2_block(sequence, config)
            )
            full_model_cycles = result.cycles * 28
            key = f"r{int(read_bandwidth)}_b{banks}"
            sweep[key] = {
                "block_cycles": result.cycles,
                "full_28_layer_cycles": full_model_cycles,
                "analytical_tokens_per_second": (
                    sequence * config.clock_hz / full_model_cycles
                ),
                "matrix_duty_cycle": (
                    result.resource_busy["matrix"] / result.cycles
                ),
                "resource_busy_cycles": dict(result.resource_busy),
                "max_concurrent_banks": result.max_concurrent_banks,
                "critical_chain": list(result.critical_chain),
                "schedule_sha256": hashlib.sha256(
                    repr(tuple(asdict(item) for item in result.tasks)).encode()
                ).hexdigest(),
            }
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_class": "discrete_event_E3_preflight_not_integrated_RTL_E3",
        "workload": {
            "model": "Qwen2-1.5B",
            "layers": 28,
            "sequence": sequence,
            "batch": 1,
        },
        "sweep": sweep,
        "selected_preflight": sweep["r100_b16"],
        "frozen_local_E3_instrumentation": [
            "per-engine queue occupancy",
            "per-task accepted/start/finish cycles",
            "DDR bytes and effective bandwidth",
            "SRAM bank conflict cycles",
            "Matrix active utilization and wall duty cycle",
            "event wait/signal latency",
            "score/probability DDR writes must remain zero",
        ],
        "remaining_local_gates": [
            "replace analytical task durations with measured L5.3/L5.4 service curves",
            "connect real iDMA and DDR latency model",
            "execute the same command trace in integrated RTL",
            "close 28-layer numerical E2 and cycle E3",
        ],
    }
