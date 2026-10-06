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
PLAN = ROOT / "doc/three_model_typical_block_closure_20260917_zh.yaml"


def base():
    return yaml.load(PLAN.read_text(encoding="utf-8"), Loader=V.UniqueKeyLoader)


def test_actual_plan():
    result = V.validate(base())
    assert result["status"] == "PASS_PLAN_CONSISTENCY_ONLY"
    assert result["tasks"] == 46 and result["blocks"] == 6 and result["gates"] == 12
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


def test_current_goal_is_stricter_than_preserved_legacy_inventory():
    doc = base(); result = V.validate(doc)
    assert result["current_goal_contract_checked"] and result["current_models"] == 3
    goal = doc["当前统一验收目标"]
    assert goal["模型"] == ["Qwen2-1.5B", "Qwen3.5-0.8B", "Qwen3.5-35B-A3B"]
    assert goal["模型入口"]["Qwen3.5-0.8B"]["shape"]["hidden"] == 1024
    assert goal["模型入口"]["Qwen3.5-0.8B"]["revision"] == "2fc06364715b967f1860aea9cf38778875588b17"
    assert goal["最低MAC利用率"] == 0.9
    assert next(t for t in doc["任务"] if t["编号"] == "U01")["依赖"] == ["U00"]


@pytest.mark.parametrize("kind", ["missing", "models", "source", "threshold", "denominator", "stalls", "fixed", "vector", "identity", "historical", "freeze_dependency", "entries", "blocks", "invented_08b", "release_artifact"])
def test_reject_current_goal_relaxation(kind):
    doc = base(); goal = doc["当前统一验收目标"]
    if kind == "missing": del doc["当前统一验收目标"]
    elif kind == "models": goal["模型"][1] = "Qwen3.8-Flash-Next"
    elif kind == "source": goal["验收证据"] = "source_hls_only"
    elif kind == "threshold": goal["最低MAC利用率"] = 0.5
    elif kind == "denominator": goal["性能主口径"] = "useful_macs/executed_macs"
    elif kind == "stalls": goal["包含block内停顿与阶段间隙"] = False
    elif kind == "fixed": goal["固定配置资源分母"] = False
    elif kind == "vector": goal["Matrix与Vector分报"] = False
    elif kind == "identity": goal["workload必填"].remove("generated_rtl_sha256")
    elif kind == "historical": next(t for t in doc["任务"] if t["编号"] == "U01")["依赖"].append("Q38I")
    elif kind == "freeze_dependency": next(t for t in doc["任务"] if t["编号"] == "U01")["依赖"] = []
    elif kind == "entries": del goal["模型入口"]
    elif kind == "blocks": goal["模型入口"]["Qwen3.5-35B-A3B"]["所需block"] = []
    elif kind == "invented_08b": goal["模型入口"]["Qwen3.5-0.8B"]["shape"] = {"hidden": 2048}
    elif kind == "release_artifact": doc["门禁"]["G11"]["必需工件"] = ["six_block_release_matrix.json"]
    with pytest.raises(V.PlanError): V.validate(doc)


@pytest.mark.parametrize("field,value", [("revision", "main"), ("forward_sha256", "0" * 64),
    ("阶段", "RTL_PASS"), ("权重数值RTL通过", True), ("性能workload已冻结", True),
    ("典型层索引", {"B35_08_ATTN_DENSE": 0, "B35_08_GDN_DENSE": 3})])
def test_small_model_provenance_cannot_drift_or_claim_hardware(field, value):
    doc = base()
    doc["当前统一验收目标"]["模型入口"]["Qwen3.5-0.8B"][field] = value
    with pytest.raises(V.PlanError): V.validate(doc)
