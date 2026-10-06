#!/usr/bin/env python3
"""Check a Chinese block-closure plan. A pass is NOT an RTL or model pass.

Usage: python3 scripts/validate_typical_block_plan.py PLAN.yaml [--output NEW.json]
Requires PyYAML. Does not execute any task/command embedded in the plan.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

BLOCKS = {
    "B2_DENSE": "Q2", "B35_ATTN_MOE": "Q35", "B35_GDN_MOE": "Q35",
    "B38_GDN_MOE": "Q38", "B38_QSA_MOE": "Q38", "B38_PLE_GDN_MOE": "Q38",
}
MODELS = {
    "Q2": "Qwen/Qwen2-1.5B-Instruct",
    "Q35": "Qwen/Qwen3.5-35B-A3B",
    "Q38": "Qwen/Qwen3.8-Flash-Next",
}
TASK_FIELDS = {
    "编号", "名称", "优先级", "依赖", "状态", "执行侧", "来源",
    "修改落点", "执行动作", "验收", "门禁", "产物",
}
CORE_GATES = {f"G{i}" for i in range(9)}


class PlanError(ValueError):
    """A malformed, incomplete or unsafe plan contract."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate keys, including keys introduced by YAML merge."""


def _mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise PlanError("YAML mapping key must be scalar/hashable") from exc
        if duplicate:
            raise PlanError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def need(ok: bool, message: str) -> None:
    if not ok:
        raise PlanError(message)


def nonempty_list(value: Any, name: str) -> None:
    need(isinstance(value, list) and len(value) > 0, f"empty/invalid list: {name}")
    need(all(isinstance(v, str) and v.strip() for v in value), f"non-text entry: {name}")


CURRENT_MODELS = ["Qwen2-1.5B", "Qwen3.5-0.8B", "Qwen3.5-35B-A3B"]
WORKLOAD_FIELDS = {"model_id", "model_revision", "config_sha256", "forward_sha256",
    "block_type", "layer_id", "batch", "query_tokens", "kv_tokens", "precision_policy_sha256",
    "weights_sha256", "input_sha256", "initial_state_sha256", "generated_rtl_sha256",
    "rtl_source_git_sha", "tool_versions_sha256", "memory_cache_policy_sha256",
    "configured_matrix_macs_per_cycle", "configured_vector_units", "start_event", "end_event",
    "expert_route_histogram_sha256", "matrix_tile_mapping_sha256"}


def validate_current_goal(doc: dict, tasks: dict) -> bool:
    # Historical plan snapshots remain readable; a dated goal revision cannot
    # silently lose its stricter current-target contract.
    if "目标修订日期" not in doc and "当前统一验收目标" not in doc:
        return False
    goal = doc.get("当前统一验收目标")
    need(isinstance(goal, dict) and goal.get("版本") == 1, "missing current acceptance goal")
    need(goal.get("模型") == CURRENT_MODELS, "wrong current acceptance models")
    entries = goal.get("模型入口")
    need(isinstance(entries, dict) and set(entries) == set(CURRENT_MODELS)
         and all(isinstance(v, dict) for v in entries.values()), "current model entries incomplete")
    need(entries["Qwen2-1.5B"].get("既有身份") == MODELS["Q2"]
         and entries["Qwen2-1.5B"].get("所需block") == ["B2_DENSE"], "current Q2 block scope changed")
    need(entries["Qwen3.5-35B-A3B"].get("既有身份") == MODELS["Q35"]
         and entries["Qwen3.5-35B-A3B"].get("所需block") == ["B35_ATTN_MOE", "B35_GDN_MOE"],
         "current Q35 block scope changed")
    # U00 must introduce a pinned, tested profile before a later plan revision
    # can replace this explicit unresolved state with model-support claims.
    small = entries["Qwen3.5-0.8B"]
    need(all(k in small and small[k] is None for k in
             ("既有身份", "revision", "config_sha256", "shape", "所需block")),
         "0.8B requires a separately validated provenance update")
    need(goal.get("验收证据") == "actual_generated_rtl_replay", "current goal requires actual RTL replay")
    need(type(goal.get("最低MAC利用率")) in (int, float) and goal["最低MAC利用率"] == 0.9,
         "current utilization threshold must be 90 percent")
    need(goal.get("性能主口径") == "matrix_useful_macs/(configured_matrix_macs_per_cycle*block_wall_cycles)",
         "current utilization denominator changed")
    for key in ("每模型数值通过", "固定配置资源分母", "包含block内停顿与阶段间隙", "Matrix与Vector分报",
                "源码HLS不替代RTL", "每项目独立验收", "C03.3仅E0"):
        need(goal.get(key) is True, "current acceptance safeguard missing: " + key)
    fields = goal.get("workload必填", [])
    need(isinstance(fields, list) and WORKLOAD_FIELDS <= set(fields), "current workload identity incomplete")
    need(goal.get("最终完成任务") == "U01" and {"U00", "U01"} <= tasks.keys(), "current goal tasks missing")
    historical = goal.get("历史后续任务", [])
    need(isinstance(historical, list) and len(set(historical)) == len(historical)
         and set(historical) <= tasks.keys(), "invalid historical task exclusions")
    need({key for key in tasks if key.startswith("Q38")} | {"R00", "F00", "F01"} <= set(historical),
         "historical Q38 scope reenabled in current goal")
    # Current final acceptance must not inherit the old Q38 closure by accident.
    pending = ["U01"]; ancestors = set()
    while pending:
        item = pending.pop()
        if item not in ancestors:
            ancestors.add(item); pending.extend(tasks[item]["依赖"])
    need("U00" in ancestors, "current final goal bypasses workload/source freezing")
    need("current_three_model_acceptance.json" in doc["门禁"]["G11"]["必需工件"],
         "current release artifact missing")
    need(not ancestors.intersection(historical), "current goal depends on historical Q38/release scope")
    return True


def validate(doc: Any) -> dict:
    need(isinstance(doc, dict), "plan must be a mapping")
    need(doc.get("版本") == 1, "unsupported plan version")
    need(doc.get("仓库") == "liyang53719/hetero_cnn_llm_aha", "wrong repository")
    need(re.fullmatch(r"[0-9a-f]{40}", str(doc.get("审查基线", ""))) is not None, "unfrozen baseline")
    policy = doc.get("继承约束", {})
    need(policy.get("分支") == "main", "not main-only")
    need(policy.get("允许创建分支") is False and policy.get("允许强制推送") is False, "unsafe branch policy")
    need(policy.get("目标时钟_Hz") == 800000000 and policy.get("目标周期_ns") == 1.25, "wrong clock target")
    gates = doc.get("门禁", {})
    need(isinstance(gates, dict) and set(gates) == {f"G{i}" for i in range(12)}, "incomplete gates")
    for name, gate in gates.items():
        need(isinstance(gate, dict) and bool(gate.get("名称")) and bool(gate.get("判据")), f"undefined gate: {name}")
        nonempty_list(gate.get("必需工件"), name)
    need(gates["G10"].get("功能block发布前置") is False, "physical signoff must be separate")
    sources = doc.get("来源", {})
    need(isinstance(sources, dict) and bool(sources), "no provenance")
    models = doc.get("模型合同", {})
    need(isinstance(models, dict) and set(models) == set(MODELS), "incomplete models")
    for model, checkpoint in MODELS.items():
        m = models[model]
        need(m.get("checkpoint") == checkpoint, f"wrong checkpoint: {model}")
        need(re.fullmatch(r"[0-9a-f]{40}", str(m.get("revision", ""))) is not None, f"unfrozen model: {model}")
        need(m.get("q_width") == m.get("q_heads", 0) * m.get("head_dim", 0), f"Q geometry: {model}")
        need(m.get("kv_width") == m.get("kv_heads", 0) * m.get("head_dim", 0), f"KV geometry: {model}")
    need(models["Q35"]["hidden"] != models["Q35"]["q_width"], "Q35 must decouple Q/hidden")
    need(models["Q38"]["hidden"] != models["Q38"]["q_width"], "Q38 must decouple Q/hidden")
    need((models["Q35"].get("experts"), models["Q35"].get("top_k")) == (256, 8), "Q35 routing geometry")
    need((models["Q38"].get("experts"), models["Q38"].get("top_k")) == (512, 10), "Q38 routing geometry")
    rows = doc.get("任务", [])
    need(isinstance(rows, list) and bool(rows), "no tasks")
    tasks = {}
    for row in rows:
        need(isinstance(row, dict) and TASK_FIELDS <= row.keys(), "incomplete task fields")
        ident = row["编号"]
        need(isinstance(ident, str) and ident not in tasks, f"duplicate/invalid task: {ident}")
        need(row["优先级"] in {"P0", "P1", "P2", "P3"}, f"bad priority: {ident}")
        need(row["状态"] == "待执行", f"planning task falsely marked executed: {ident}")
        need(isinstance(row["依赖"], list) and len(set(row["依赖"])) == len(row["依赖"]), f"bad dependencies: {ident}")
        for field in ("来源", "执行动作", "验收", "门禁", "产物"):
            nonempty_list(row[field], f"{ident}.{field}")
        need(set(row["来源"]) <= sources.keys(), f"undefined source: {ident}")
        need(set(row["门禁"]) <= gates.keys(), f"undefined gate: {ident}")
        tasks[ident] = row
    for ident, row in tasks.items():
        need(set(row["依赖"]) <= tasks.keys() and ident not in row["依赖"], f"unknown/self dependency: {ident}")
    pending = set(tasks)
    order = []
    while pending:
        ready = sorted((i for i in pending if set(tasks[i]["依赖"]) <= set(order)),
                       key=lambda i: (tasks[i]["优先级"], i in {"P01", "P02", "P03", "P04"}, i))
        need(bool(ready), "dependency cycle")
        chosen = ready[0]
        order.append(chosen)
        pending.remove(chosen)
    blocks = doc.get("典型block", {})
    need(isinstance(blocks, dict) and set(blocks) == set(BLOCKS), "incomplete six-block inventory")
    for block, model in BLOCKS.items():
        entry = blocks[block]
        need(entry.get("模型") == model, f"wrong model for block: {block}")
        for field in ("完整范围", "输入", "输出"):
            need(isinstance(entry.get(field), str) and bool(entry[field].strip()), f"missing block boundary: {block}")
        nonempty_list(entry.get("完成任务"), block)
        need(set(entry["完成任务"]) <= tasks.keys(), f"unknown completion task: {block}")
        need(set(entry.get("发布门禁", [])) == CORE_GATES, f"block bypasses core gate: {block}")
    milestones = doc.get("里程碑", {})
    need(isinstance(milestones, dict), "invalid milestones")
    named = [task for items in milestones.values() for task in items]
    need(len(named) == len(tasks) and set(named) == set(tasks), "milestones omit/duplicate tasks")
    matrix = doc.get("测试矩阵", {})
    need(set(matrix.get("完整block官方必测", [])) >= {16, 33, 128, 1024}, "missing official full-shape test")
    qsa = matrix.get("QSA额外", {}).get("候选微块数", [])
    need(513 in qsa and 1024 in qsa, "QSA never exceeds Top512 capacity")
    budget = doc.get("资源与性能边界", {}).get("GDN状态_计算而非测量", {})
    for model, field in (("Q35", "Q35_每层_FP32字节"), ("Q38", "Q38_每层_FP32字节")):
        m = models[model]
        count = m["gdn_value_heads"] * m["gdn_key_dim"] * m["gdn_value_dim"] * 4
        need(budget.get(field) == count, f"bad state budget: {model}")
    current_goal = validate_current_goal(doc, tasks)
    return {
        "current_goal_contract_checked": current_goal,
        "current_models": len(CURRENT_MODELS) if current_goal else None,
        "status": "PASS_PLAN_CONSISTENCY_ONLY", "hardware_tests_executed": False,
        "tasks": len(tasks), "blocks": len(blocks), "gates": len(gates),
        "priorities": dict(sorted(Counter(r["优先级"] for r in rows).items())),
        "topological_order": order,
        "scope": "Schema, references, dependencies, model geometry and required gates only; not hardware acceptance.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = args.plan.read_bytes()
        result = validate(yaml.load(data.decode("utf-8"), Loader=UniqueKeyLoader))
        result["plan_sha256"] = hashlib.sha256(data).hexdigest()
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                output.write(text)
        print(text, end="")
        return 0
    except (PlanError, yaml.YAMLError, OSError, UnicodeError, TypeError, KeyError) as exc:
        print(f"FAIL_PLAN: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
