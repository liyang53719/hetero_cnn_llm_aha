import json
from collections import Counter
import pytest
from candidates.qwen2_resident_matrix.attention_panel_audit.constraints import (
    HERE, BorrowLedger, check_sources, head_recipe, location, panel_slot, report,
    scratch_line, transfers, v_slot)


def borrowed():
    loan = BorrowLedger()
    loan.acquire(native_idle=True, dense_drained=True, matrix_drained=True,
                 scalar_drained=True, bank_drained=True)
    return loan


def test_sources_and_saved_report():
    assert check_sources() >= 10
    assert json.loads((HERE / 'M128_COUNTS.json').read_text()) == report()


def test_exact_allocation_and_no_pv_alias():
    panel = {panel_slot(h, k) for h in range(6) for k in range(16)}
    values = {v_slot(c) for c in range(128)}
    assert panel == set(range(128, 224))
    assert values == set(range(128))
    assert not panel & values
    assert len(panel | values) == 224


@pytest.mark.parametrize('keys', [1, 2, 16, 17, 127, 128])
def test_complete_line_transactions_and_order(keys):
    trace = tuple(transfers(keys))
    count = 6 * ((keys + 15) // 16)
    assert Counter(op for op, _ in trace) == dict.fromkeys(
        ('score_write', 'score_read', 'weight_write', 'weight_read'), count)
    written = set()
    for op, line in trace:
        if op.endswith('write'):
            assert line not in written
            written.add(line)
        else:
            assert line in written
        low, high, word = location(line)
        assert high == low + 1 and 512 <= word <= 523
    events = tuple(head_recipe(keys))
    for op in ('ordered_max', 'ordered_sum_fp32', 'normalize_fp32', 'pv_fma_fp32'):
        assert [k for name, k in events if name == op] == list(range(keys))
    reciprocal = events.index(('reciprocal_fp32', -1))
    assert events.index(('ordered_sum_fp32', keys - 1)) < reciprocal
    for key in range(keys):
        assert reciprocal < events.index(('normalize_fp32', key)) < events.index(('matrix_ingress_bf16', key)) < events.index(('pv_fma_fp32', key))


def test_head_lines_collide_so_six_reads_must_serialize():
    for first in range(0, 128, 16):
        cells = [location(scratch_line('weight', head, first)) for head in range(6)]
        assert len({cell[:2] for cell in cells}) == 1
        assert len({cell[2] for cell in cells}) == 6


def test_exclusive_lease_and_clear_hazard():
    loan = borrowed()
    for index in range(256):
        loan.touch('qk', index)
    with pytest.raises(ValueError): loan.touch('panel', 128)
    with pytest.raises(ValueError): loan.legacy_clear()
    with pytest.raises(ValueError): loan.begin_softmax(qk_drained=False, score_acks_complete=True)
    loan.begin_softmax(qk_drained=True, score_acks_complete=True)
    with pytest.raises(ValueError): loan.touch('qk', 0)
    with pytest.raises(ValueError): loan.touch('v', 0)
    with pytest.raises(ValueError): loan.begin_pv(raw_weights_committed=True, reciprocal_acked=False)
    loan.begin_pv(raw_weights_committed=True, reciprocal_acked=True)
    for h in range(6):
        for k in range(16): loan.touch('panel', panel_slot(h, k))
    for c in range(128): loan.touch('v', v_slot(c))
    with pytest.raises(ValueError): loan.touch('v', 128)
    with pytest.raises(ValueError): loan.touch('panel', 224)
    with pytest.raises(ValueError): loan.release(matrix_drained=False, scalar_drained=True, bank_drained=True, outputs_acked=True)
    loan.release(matrix_drained=True, scalar_drained=True, bank_drained=True, outputs_acked=True)
    loan.legacy_clear()


def test_m128_counts_enumerated_and_bound_is_not_acceptance():
    trace_count = sum(2 * len(tuple(transfers(n))) for n in range(1, 129))
    r = report()
    assert trace_count == r['scratch_transactions'] == 27648
    assert r['scratch_service_edge_floor'] == 82944
    assert r['serial_plus_vector_fold_scale']['conditional_minimum_edges'] == 1852032
    assert r['serial_plus_vector_fold_scale']['useful_mac_utilization_ceiling_percent'] < 80
    assert r['physical_stage_retention_verified'] is False
    assert r['actual_hardware_cycles'] is None
    assert r['accepted_80'] is r['accepted_90'] is False


def test_noncanonical_or_unleased_use_fails_closed():
    for h, k in ((True, 0), (6, 0), (0, 16), (-1, 0)):
        with pytest.raises(ValueError): panel_slot(h, k)
    with pytest.raises(ValueError): tuple(transfers(True))
    with pytest.raises(ValueError): scratch_line('weight', 0, 1)
    with pytest.raises(ValueError): BorrowLedger().touch('qk', 0)
    with pytest.raises(ValueError): BorrowLedger().acquire(native_idle=True, dense_drained=True, matrix_drained=True, scalar_drained=True, bank_drained=1)
