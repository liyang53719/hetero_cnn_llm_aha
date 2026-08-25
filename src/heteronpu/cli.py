from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from .config import load_architecture
from .scheduler import CycleModel
from .workloads import run_toy_cnn, run_toy_llm_block


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Heterogeneous CNN/LLM architecture harness")
    parser.add_argument("--config", default="configs/arch_v0.yaml")
    parser.add_argument("--output", default="")
    parser.add_argument("--llm-kv-format", choices=["bf16", "int8"], default="bf16")
    args = parser.parse_args(argv)

    config = load_architecture(args.config)
    cycle = CycleModel(config)
    cnn = run_toy_cnn()
    llm = run_toy_llm_block(storage_format=args.llm_kv_format)
    cnn_tasks = cycle.cnn_layer_tasks(
        batch=1,
        out_h=56,
        out_w=56,
        in_channels=64,
        out_channels=64,
        kernel_h=3,
        kernel_w=3,
        dtype="int8",
        prefix="resnet_stage",
    )
    llm_prefill_tasks = cycle.llm_block_tasks(
        tokens=384,
        hidden=1536,
        heads=12,
        kv_heads=2,
        head_dim=128,
        ffn=8960,
        dtype="w4a8",
        decode=False,
    )
    llm_decode_tasks = cycle.llm_block_tasks(
        tokens=1,
        hidden=1536,
        heads=12,
        kv_heads=2,
        head_dim=128,
        ffn=8960,
        dtype="w4a8",
        decode=True,
    )
    report = {
        "architecture": config.name,
        "clock_hz": config.clock_hz,
        "functional": {
            "cnn": {key: value for key, value in cnn.items() if key not in {"reference", "output"}},
            "llm": {key: value for key, value in llm.items() if key not in {"reference", "output"}},
        },
        "cycle_model": {
            "cnn_layer": cycle.summarize(cycle.schedule(cnn_tasks), config.clock_hz),
            "llm_prefill_block": cycle.summarize(cycle.schedule(llm_prefill_tasks), config.clock_hz),
            "llm_decode_block_context4096": cycle.summarize(cycle.schedule(llm_decode_tasks), config.clock_hz),
        },
    }
    rendered = json.dumps(_jsonable(report), indent=2, sort_keys=True)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0
