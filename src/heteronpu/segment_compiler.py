from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .command import Command128, Engine, Opcode, NULL_INDEX


@dataclass(frozen=True)
class BarrierDescriptor:
    index: int
    wait_events: tuple[int, ...]


@dataclass(frozen=True)
class CompiledCommand:
    name: str
    command: Command128
    dependencies: tuple[str, ...]
    synthetic: bool = False


@dataclass(frozen=True)
class CompiledSegment:
    name: str
    commands: tuple[CompiledCommand, ...]
    barriers: tuple[BarrierDescriptor, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "commands": [
                {
                    "name": item.name,
                    "dependencies": list(item.dependencies),
                    "synthetic": item.synthetic,
                    "word_hex": f"0x{item.command.pack():032x}",
                    "bytes_le_hex": item.command.to_bytes().hex(),
                    "fields": {
                        **asdict(item.command),
                        "opcode": item.command.opcode.name,
                        "engine": item.command.engine.name,
                    },
                }
                for item in self.commands
            ],
            "barrier_descriptors": [
                {"index": barrier.index, "wait_events": list(barrier.wait_events)}
                for barrier in self.barriers
            ],
        }


_ENGINE_BY_NAME = {
    "control": Engine.CONTROL,
    "dma": Engine.DMA,
    "matrix": Engine.MATRIX,
    "sfu_cgra": Engine.SFU_CGRA,
    "sfu": Engine.SFU_CGRA,
    "kv": Engine.KV,
    "collective": Engine.COLLECTIVE,
}
_OPCODE_BY_NAME = {op.name.lower(): op for op in Opcode}


def compile_segment(spec: dict[str, Any]) -> CompiledSegment:
    name = str(spec.get("name", "unnamed_segment"))
    operations = spec.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("segment must contain a non-empty operations list")

    ids = [str(op["id"]) for op in operations]
    if len(set(ids)) != len(ids):
        raise ValueError("operation IDs must be unique")
    id_set = set(ids)

    next_event = 1
    next_barrier_desc = int(spec.get("barrier_descriptor_base", 0xF00000))
    event_by_op: dict[str, int] = {}
    barriers: list[BarrierDescriptor] = []
    compiled: list[CompiledCommand] = []

    for raw in operations:
        op_id = str(raw["id"])
        deps = tuple(str(dep) for dep in raw.get("depends_on", []))
        unknown = set(deps).difference(id_set)
        if unknown:
            raise ValueError(f"operation {op_id} has unknown dependencies: {sorted(unknown)}")
        not_yet_defined = [dep for dep in deps if dep not in event_by_op]
        if not_yet_defined:
            raise ValueError(
                f"operations must be topologically ordered; {op_id} precedes {not_yet_defined}"
            )

        wait_event = 0
        if len(deps) == 1:
            wait_event = event_by_op[deps[0]]
        elif len(deps) > 1:
            barrier_event = next_event
            next_event += 1
            barrier_desc = BarrierDescriptor(
                index=next_barrier_desc,
                wait_events=tuple(event_by_op[dep] for dep in deps),
            )
            next_barrier_desc += 1
            barriers.append(barrier_desc)
            barrier_cmd = Command128(
                opcode=Opcode.BARRIER,
                engine=Engine.CONTROL,
                event_signal=barrier_event,
                src0=barrier_desc.index,
            )
            compiled.append(
                CompiledCommand(
                    name=f"__join__{op_id}",
                    command=barrier_cmd,
                    dependencies=deps,
                    synthetic=True,
                )
            )
            wait_event = barrier_event

        engine_name = str(raw["engine"]).lower()
        opcode_name = str(raw["opcode"]).lower()
        try:
            engine = _ENGINE_BY_NAME[engine_name]
            opcode = _OPCODE_BY_NAME[opcode_name]
        except KeyError as exc:
            raise ValueError(f"unknown engine/opcode in {op_id}: {exc}") from exc

        signal_event = next_event
        next_event += 1
        command = Command128(
            opcode=opcode,
            engine=engine,
            flags=int(raw.get("flags", 0)),
            event_wait=wait_event,
            event_signal=signal_event,
            src0=int(raw.get("src0", NULL_INDEX)),
            src1=int(raw.get("src1", NULL_INDEX)),
            dst=int(raw.get("dst", NULL_INDEX)),
        )
        compiled.append(
            CompiledCommand(name=op_id, command=command, dependencies=deps)
        )
        event_by_op[op_id] = signal_event

    return CompiledSegment(name=name, commands=tuple(compiled), barriers=tuple(barriers))


def load_and_compile(path: str | Path) -> CompiledSegment:
    with Path(path).open("r", encoding="utf-8") as handle:
        spec = yaml.safe_load(handle)
    if not isinstance(spec, dict):
        raise ValueError("segment YAML must contain a mapping")
    return compile_segment(spec)
