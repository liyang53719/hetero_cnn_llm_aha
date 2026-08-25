from heteronpu.config import load_config
from heteronpu.scheduler import CycleEstimator, Task


def test_scheduler_respects_dependencies_and_engine_serialization() -> None:
    tasks = [
        Task("a", "dma", 10),
        Task("b", "matrix", 20, ("a",)),
        Task("c", "dma", 7),
        Task("d", "sfu", 4, ("b", "c")),
    ]
    schedule = CycleEstimator.schedule(tasks)
    entries = {entry.task.name: entry for entry in schedule}
    assert entries["a"].start == 0
    assert entries["c"].start == 10
    assert entries["b"].start == 10
    assert entries["d"].start == 30


def test_cycle_models_are_positive_and_prefill_is_matrix_dominated() -> None:
    cfg = load_config("configs/arch_v0.yaml")
    estimator = CycleEstimator(cfg)
    tasks = estimator.llm_block_tasks(
        tokens=384,
        hidden=1536,
        heads=12,
        kv_heads=2,
        head_dim=128,
        ffn=8960,
        dtype="w4a8",
    )
    summary = estimator.summarize(estimator.schedule(tasks), cfg.clock_hz)
    assert summary["cycles"] > 0
    assert summary["engine_utilization"]["matrix"] > 0.8
    assert sum(task.macs for task in tasks) > 0
