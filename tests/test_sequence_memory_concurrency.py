from heteronpu.sequence_memory_concurrency import (
    MemoryRequest,
    ModelConfig,
    SequenceMemoryModel,
    coalesced_trace,
    sequence_memory_concurrency_report,
)


def test_mshr_coalescing_issues_fewer_walks():
    model = SequenceMemoryModel(ModelConfig(mshr_entries=8, max_outstanding_walks=8, max_outstanding_data=16), seed=1)
    for seq in range(4):
        model.set_generation(seq, 1)
    result = model.run(coalesced_trace(groups=32, requests_per_page=8))
    assert result["status"] == "PASS"
    assert result["counters"]["walks_issued"] < result["requests"]
    assert result["counters"]["mshr_coalesced"] > 0


def test_stale_generation_rejected_before_data():
    model = SequenceMemoryModel(ModelConfig(), seed=2)
    model.set_generation(3, 9)
    result = model.run(tuple(MemoryRequest(i, 3, i, 8) for i in range(32)))
    assert result["counters"]["stale_rejected"] == 32
    assert result["counters"]["walks_issued"] == 0


def test_out_of_order_arrival_in_order_retirement():
    model = SequenceMemoryModel(ModelConfig(data_latency_min=1, data_latency_max=100, max_outstanding_data=32), seed=3)
    model.set_generation(0, 1)
    requests = tuple(MemoryRequest(i, 0, i, 1) for i in range(128))
    result = model.run(requests)
    assert result["counters"]["out_of_order_arrivals"] > 0
    assert result["counters"]["retired"] == 128


def test_report():
    report = sequence_memory_concurrency_report()
    assert report["status"] == "PASS"
    assert report["coalescing_case"]["counters"]["mshr_coalesced"] > 0
    assert report["stale_generation_case"]["counters"]["stale_rejected"] == 64
