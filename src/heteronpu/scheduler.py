from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Dict, Iterable, Mapping

from .config import ArchitectureConfig


@dataclass(frozen=True)
class Task:
    name: str
    engine: str
    cycles: int
    dependencies: tuple[str, ...] = ()
    bytes_moved: int = 0
    macs: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduledTask:
    task: Task
    start: int
    end: int


class CycleModel:
    """Deterministic resource-constrained task scheduler and roofline model."""

    def __init__(self, config: ArchitectureConfig) -> None:
        self.config = config
        self.rows = int(config.matrix["array_rows"])
        self.cols = int(config.matrix["array_cols"])
        self.bus_bytes = int(config.memory["axi_data_bits"]) // 8

    def matrix_cycles(self, m: int, n: int, k: int, dtype: str = "int8") -> int:
        if min(m, n, k) <= 0:
            return 0
        if dtype == "bf16":
            rows, cols, pack = max(1, self.rows // 2), max(1, self.cols // 2), 1
        elif dtype == "w4a8":
            rows, cols, pack = self.rows, self.cols, 2
        else:
            rows, cols, pack = self.rows, self.cols, 1
        mt = ceil(m / rows)
        nt = ceil(n / cols)
        effective_k = ceil(k / pack)
        fill = rows + cols + 6
        return mt * nt * (effective_k + fill)

    def dma_cycles(self, byte_count: int, *, efficiency: float = 0.82, ports: int = 1) -> int:
        if byte_count <= 0:
            return 0
        payload = self.bus_bytes * max(1, ports) * efficiency
        return 12 + ceil(byte_count / payload)

    def sfu_cycles(self, elements: int, op: str) -> int:
        tiles = int(self.config.sfu["tiles_x"]) * int(self.config.sfu["tiles_y"])
        lanes = int(self.config.sfu["vector_lanes_per_tile"])
        base = ceil(max(0, elements) / max(1, tiles * lanes))
        latency = {
            "relu": 2,
            "rope": 8,
            "silu": 12,
            "gelu": 14,
            "rmsnorm": 18,
            "softmax": 24,
            "pool": 5,
            "quantize": 6,
        }.get(op, 4)
        return base + latency

    def kv_cycles(self, tokens: int, kv_heads: int, head_dim: int, dtype: str, op: str) -> int:
        bytes_per_element = 1 if dtype == "int8" else 2
        byte_count = max(0, tokens) * kv_heads * head_dim * 2 * bytes_per_element
        translation = int(self.config.kv["translation_pipeline_cycles"])
        page_tokens = int(self.config.kv["page_tokens"])
        pages = ceil(max(0, tokens) / page_tokens)
        fixed = {"append": 4, "gather": 6, "share": 10, "free": 4}.get(op, 4)
        return fixed + pages * translation + self.dma_cycles(byte_count, efficiency=0.88)

    @staticmethod
    def schedule(tasks: Iterable[Task]) -> list[ScheduledTask]:
        pending: Dict[str, Task] = {}
        for task in tasks:
            if task.name in pending:
                raise ValueError(f"duplicate task name: {task.name}")
            if task.cycles < 0:
                raise ValueError(f"negative cycles for {task.name}")
            pending[task.name] = task
        unknown = {
            dep for task in pending.values() for dep in task.dependencies if dep not in pending
        }
        if unknown:
            raise ValueError(f"unknown dependencies: {sorted(unknown)}")
        completed: Dict[str, ScheduledTask] = {}
        engine_free: Dict[str, int] = {}
        while pending:
            ready = [
                task
                for task in pending.values()
                if all(dep in completed for dep in task.dependencies)
            ]
            if not ready:
                raise ValueError("task graph has a dependency cycle")
            ready.sort(key=lambda t: (max((completed[d].end for d in t.dependencies), default=0), t.name))
            task = ready[0]
            dep_end = max((completed[d].end for d in task.dependencies), default=0)
            start = max(dep_end, engine_free.get(task.engine, 0))
            scheduled = ScheduledTask(task=task, start=start, end=start + task.cycles)
            completed[task.name] = scheduled
            engine_free[task.engine] = scheduled.end
            del pending[task.name]
        return sorted(completed.values(), key=lambda item: (item.start, item.task.name))

    @staticmethod
    def summarize(schedule: Iterable[ScheduledTask], clock_hz: int) -> dict[str, object]:
        entries = list(schedule)
        makespan = max((entry.end for entry in entries), default=0)
        busy: Dict[str, int] = {}
        for entry in entries:
            busy[entry.task.engine] = busy.get(entry.task.engine, 0) + entry.task.cycles
        return {
            "cycles": makespan,
            "latency_us": makespan / clock_hz * 1e6,
            "engine_busy_cycles": busy,
            "engine_utilization": {
                engine: (cycles / makespan if makespan else 0.0) for engine, cycles in busy.items()
            },
            "tasks": [
                {
                    "name": e.task.name,
                    "engine": e.task.engine,
                    "start": e.start,
                    "end": e.end,
                    "cycles": e.task.cycles,
                    "bytes": e.task.bytes_moved,
                    "macs": e.task.macs,
                }
                for e in entries
            ],
        }

    def cnn_layer_tasks(
        self,
        *,
        batch: int,
        out_h: int,
        out_w: int,
        in_channels: int,
        out_channels: int,
        kernel_h: int,
        kernel_w: int,
        dtype: str = "int8",
        prefix: str = "conv",
    ) -> list[Task]:
        m = batch * out_h * out_w
        k = kernel_h * kernel_w * in_channels
        n = out_channels
        elem_bytes = 2 if dtype == "bf16" else 1
        input_bytes = m * k * elem_bytes
        weight_bytes = k * n * (0.5 if dtype == "w4a8" else elem_bytes)
        output_bytes = m * n * 4
        load_name = f"{prefix}.load"
        compute_name = f"{prefix}.matrix"
        act_name = f"{prefix}.activation"
        return [
            Task(load_name, "dma", self.dma_cycles(int(input_bytes + weight_bytes)), bytes_moved=int(input_bytes + weight_bytes)),
            Task(
                compute_name,
                "matrix",
                self.matrix_cycles(m, n, k, dtype),
                (load_name,),
                macs=m * n * k,
            ),
            Task(act_name, "sfu", self.sfu_cycles(m * n, "relu"), (compute_name,)),
            Task(
                f"{prefix}.store",
                "dma",
                self.dma_cycles(output_bytes),
                (act_name,),
                bytes_moved=output_bytes,
            ),
        ]

    def llm_block_tasks(
        self,
        *,
        tokens: int,
        hidden: int,
        heads: int,
        kv_heads: int,
        head_dim: int,
        ffn: int,
        dtype: str = "w4a8",
        decode: bool = False,
    ) -> list[Task]:
        weight_bytes_per = 0.5 if dtype == "w4a8" else (2 if dtype == "bf16" else 1)
        tasks: list[Task] = []
        tasks.append(Task("norm1", "sfu", self.sfu_cycles(tokens * hidden, "rmsnorm")))
        qkv_weight = hidden * (hidden + 2 * kv_heads * head_dim) * weight_bytes_per
        tasks.append(Task("qkv.load", "dma", self.dma_cycles(int(qkv_weight), ports=2), bytes_moved=int(qkv_weight)))
        qkv_n = hidden + 2 * kv_heads * head_dim
        tasks.append(
            Task(
                "qkv.matrix",
                "matrix",
                self.matrix_cycles(tokens, qkv_n, hidden, dtype),
                ("norm1", "qkv.load"),
                macs=tokens * qkv_n * hidden,
            )
        )
        tasks.append(Task("rope", "sfu", self.sfu_cycles(tokens * heads * head_dim, "rope"), ("qkv.matrix",)))
        tasks.append(
            Task(
                "kv.append",
                "kv",
                self.kv_cycles(tokens, kv_heads, head_dim, "int8" if dtype != "bf16" else "bf16", "append"),
                ("rope",),
            )
        )
        context = 4096 if decode else tokens
        tasks.append(
            Task(
                "kv.gather",
                "kv",
                self.kv_cycles(context, kv_heads, head_dim, "int8" if dtype != "bf16" else "bf16", "gather"),
                ("kv.append",),
            )
        )
        tasks.append(
            Task(
                "qk.matrix",
                "matrix",
                self.matrix_cycles(tokens * heads, context, head_dim, dtype if dtype != "w4a8" else "int8"),
                ("rope", "kv.gather"),
                macs=tokens * heads * context * head_dim,
            )
        )
        tasks.append(Task("softmax", "sfu", self.sfu_cycles(tokens * heads * context, "softmax"), ("qk.matrix",)))
        tasks.append(
            Task(
                "pv.matrix",
                "matrix",
                self.matrix_cycles(tokens * heads, head_dim, context, dtype if dtype != "w4a8" else "int8"),
                ("softmax", "kv.gather"),
                macs=tokens * heads * context * head_dim,
            )
        )
        o_weight = hidden * hidden * weight_bytes_per
        tasks.append(Task("oproj.load", "dma", self.dma_cycles(int(o_weight), ports=2), bytes_moved=int(o_weight)))
        tasks.append(
            Task(
                "oproj.matrix",
                "matrix",
                self.matrix_cycles(tokens, hidden, hidden, dtype),
                ("pv.matrix", "oproj.load"),
                macs=tokens * hidden * hidden,
            )
        )
        tasks.append(Task("norm2", "sfu", self.sfu_cycles(tokens * hidden, "rmsnorm"), ("oproj.matrix",)))
        gu_weight = hidden * (2 * ffn) * weight_bytes_per
        tasks.append(Task("mlp.gu.load", "dma", self.dma_cycles(int(gu_weight), ports=2), bytes_moved=int(gu_weight)))
        tasks.append(
            Task(
                "mlp.gu.matrix",
                "matrix",
                self.matrix_cycles(tokens, 2 * ffn, hidden, dtype),
                ("norm2", "mlp.gu.load"),
                macs=tokens * hidden * 2 * ffn,
            )
        )
        tasks.append(Task("mlp.silu", "sfu", self.sfu_cycles(tokens * ffn, "silu"), ("mlp.gu.matrix",)))
        down_weight = ffn * hidden * weight_bytes_per
        tasks.append(Task("mlp.down.load", "dma", self.dma_cycles(int(down_weight), ports=2), bytes_moved=int(down_weight)))
        tasks.append(
            Task(
                "mlp.down.matrix",
                "matrix",
                self.matrix_cycles(tokens, hidden, ffn, dtype),
                ("mlp.silu", "mlp.down.load"),
                macs=tokens * ffn * hidden,
            )
        )
        tasks.append(Task("block.store", "dma", self.dma_cycles(tokens * hidden * 2), ("mlp.down.matrix",), bytes_moved=tokens * hidden * 2))
        return tasks

# Public name used in the execution plan; retained as an alias so older scripts
# that imported CycleModel continue to work.
CycleEstimator = CycleModel
