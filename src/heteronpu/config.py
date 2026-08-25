from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


@dataclass(frozen=True)
class ArchitectureConfig:
    """Thin validated wrapper around the YAML architecture contract."""

    raw: Mapping[str, Any]

    @property
    def name(self) -> str:
        return str(self.raw["name"])

    @property
    def clock_hz(self) -> int:
        return int(self.raw["clock_hz"])

    @property
    def matrix(self) -> Mapping[str, Any]:
        return self.raw["matrix_engine"]

    @property
    def sfu(self) -> Mapping[str, Any]:
        return self.raw["cgra_sfu"]

    @property
    def kv(self) -> Mapping[str, Any]:
        return self.raw["kv_engine"]

    @property
    def memory(self) -> Mapping[str, Any]:
        return self.raw["external_memory"]

    def validate(self) -> None:
        required = {
            "name",
            "clock_hz",
            "command_bits",
            "event_bits",
            "matrix_engine",
            "cgra_sfu",
            "kv_engine",
            "external_memory",
            "on_chip_sram",
        }
        missing = required.difference(self.raw)
        if missing:
            raise ValueError(f"architecture config missing keys: {sorted(missing)}")
        if int(self.raw["command_bits"]) != 128:
            raise ValueError("v0 integration contract requires 128-bit commands")
        if int(self.raw["event_bits"]) != 16:
            raise ValueError("v0 integration contract requires 16-bit events")
        if self.clock_hz <= 0:
            raise ValueError("clock_hz must be positive")
        rows = int(self.matrix["array_rows"])
        cols = int(self.matrix["array_cols"])
        if rows <= 0 or cols <= 0:
            raise ValueError("matrix dimensions must be positive")
        if int(self.kv["page_tokens"]) <= 0:
            raise ValueError("KV page_tokens must be positive")


def load_architecture(path: str | Path) -> ArchitectureConfig:
    p = Path(path)
    with p.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"expected a YAML mapping in {p}")
    config = ArchitectureConfig(raw=raw)
    config.validate()
    return config


def load_config(path: str | Path) -> ArchitectureConfig:
    """Compatibility alias used by scripts and tests."""

    return load_architecture(path)
