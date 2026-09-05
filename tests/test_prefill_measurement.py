import pytest
from heteronpu.prefill_measurement import measured_metrics


def receipt():
    return dict(evidence_class='full_request_integrated_rtl', batch=1, tokens=1024,
                clock_hz=800_000_000, macs_per_cycle=512, numerical_pass=True,
                cross_layer_memory_continuity=True, final_norm_complete=True,
                last_token_lm_head_complete=True, synthetic_memory_services=False,
                rtl_sha256='a'*64, source_sha='b'*40, model_revision='c'*40,
                numerical_receipt_sha256='d'*64, counter_log_sha256='e'*64,
                expected_layers=28, completed_layers=28, wall_cycles=1000,
                useful_matrix_macs=256000, executed_matrix_macs=512000,
                ddr_read_bytes=0, ddr_write_bytes=0)


def test_metrics():
    assert measured_metrics(receipt())['useful_wall_mac_utilization'] == .5


@pytest.mark.parametrize('key,value', [
    ('evidence_class', 'composed_real_RTL_E3'), ('clock_hz', 1_000_000_000),
    ('completed_layers', 1), ('synthetic_memory_services', True),
    ('cross_layer_memory_continuity', False), ('wall_cycles', 0),
    ('executed_matrix_macs', 512001), ('useful_matrix_macs', 512001),
    ('numerical_pass', 1), ('rtl_sha256', ''), ('ddr_read_bytes', 1000000000),
])
def test_reject_incomplete_or_inconsistent(key, value):
    item = receipt(); item[key] = value
    with pytest.raises(ValueError):
        measured_metrics(item)
