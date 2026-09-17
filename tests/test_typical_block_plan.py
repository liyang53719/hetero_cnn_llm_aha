"""Plan validation only. No synthetic log in this test represents an RTL run."""
import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("plan_validator", ROOT / "scripts/validate_typical_block_plan.py")
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)
PLAN = ROOT / "plans/three_model_typical_block_closure_20260917_zh.yaml"


def base():
    return yaml.load(PLAN.read_text(encoding="utf-8"), Loader=V.UniqueKeyLoader)


def test_actual_plan():
    result = V.validate(base())
    assert result["status"] == "PASS_PLAN_CONSISTENCY_ONLY"
    assert result["tasks"] == 44 and result["blocks"] == 6 and result["gates"] == 12
    assert result["hardware_tests_executed"] is False
    doc = base()
    pos = {task: i for i, task in enumerate(result["topological_order"])}
    for task in doc["任务"]:
        assert all(pos[d] < pos[task["编号"]] for d in task["依赖"])


def corrupt(doc, kind):
    if kind == "repo": doc["仓库"] = "liyang53719/voyager_vmap"
    elif kind == "branch": doc["继承约束"]["分支"] = "work"
    elif kind == "force": doc["继承约束"]["允许强制推送"] = True
    elif kind == "clock": doc["继承约束"]["目标时钟_Hz"] = 1000000000
    elif kind == "baseline": doc["审查基线"] = "main"
    elif kind == "revision": doc["模型合同"]["Q38"]["revision"] = "main"
    elif kind == "model": doc["模型合同"]["Q38"]["checkpoint"] = "Qwen/Qwen3-8B"
    elif kind == "geometry": doc["模型合同"]["Q35"]["q_width"] = 2048
    elif kind == "routing": doc["模型合同"]["Q38"]["top_k"] = 8
    elif kind == "state": doc["资源与性能边界"]["GDN状态_计算而非测量"]["Q35_每层_FP32字节"] = 1024
    elif kind == "duplicate_task": doc["任务"].append(copy.deepcopy(doc["任务"][0]))
    elif kind == "self": doc["任务"][0]["依赖"] = ["C00"]
    elif kind == "unknown": doc["任务"][0]["依赖"] = ["MISSING"]
    elif kind == "cycle": doc["任务"][0]["依赖"] = ["C01"]
    elif kind == "priority": doc["任务"][0]["优先级"] = "P7"
    elif kind == "fake_pass": doc["任务"][0]["状态"] = "通过"
    elif kind == "source": doc["任务"][0]["来源"] = ["MISSING"]
    elif kind == "empty_exit": doc["任务"][0]["验收"] = []
    elif kind == "task_gate": doc["任务"][0]["门禁"] = ["G99"]
    elif kind == "missing_field": del doc["任务"][0]["执行侧"]
    elif kind == "block": del doc["典型block"]["B38_PLE_GDN_MOE"]
    elif kind == "block_model": doc["典型block"]["B35_GDN_MOE"]["模型"] = "Q38"
    elif kind == "block_task": doc["典型block"]["B2_DENSE"]["完成任务"] = ["MISSING"]
    elif kind == "official_gate": doc["典型block"]["B2_DENSE"]["发布门禁"].remove("G6")
    elif kind == "qsa": doc["测试矩阵"]["QSA额外"]["候选微块数"] = [0, 1, 512]
    elif kind == "tokens": doc["测试矩阵"]["完整block官方必测"] = [16]
    elif kind == "milestone": doc["里程碑"]["M0"].pop()
    elif kind == "duplicate_milestone": doc["里程碑"]["M0"].append("C00")
    elif kind == "physical": doc["门禁"]["G10"]["功能block发布前置"] = True
    elif kind == "gate_inventory": del doc["门禁"]["G6"]
    else: raise AssertionError(kind)


@pytest.mark.parametrize("kind", [
    "repo", "branch", "force", "clock", "baseline", "revision", "model", "geometry",
    "routing", "state", "duplicate_task", "self", "unknown", "cycle", "priority",
    "fake_pass", "source", "empty_exit", "task_gate", "missing_field", "block", "block_model",
    "block_task", "official_gate", "qsa", "tokens", "milestone", "duplicate_milestone",
    "physical", "gate_inventory",
])
def test_reject_mutation(kind):
    doc = base()
    corrupt(doc, kind)
    with pytest.raises(V.PlanError):
        V.validate(doc)


@pytest.mark.parametrize("text", ["版本: 1\n版本: 2\n", "a: &x {x: 1}\nb: {<<: *x, x: 2}\n"])
def test_reject_duplicate_yaml_keys(text):
    with pytest.raises(V.PlanError):
        yaml.load(text, Loader=V.UniqueKeyLoader)


def test_safe_yaml_rejects_python_objects():
    with pytest.raises(yaml.YAMLError):
        yaml.load("!!python/object/apply:os.system ['exit 0']", Loader=V.UniqueKeyLoader)
