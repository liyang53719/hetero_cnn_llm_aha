"""Strict full-request performance admission, not a service-curve estimator."""
from math import isfinite


def measured_metrics(receipt):
    required = {
        'evidence_class': 'full_request_integrated_rtl',
        'batch': 1, 'tokens': 1024, 'clock_hz': 800_000_000,
        'macs_per_cycle': 512, 'numerical_pass': True,
        'cross_layer_memory_continuity': True,
        'final_norm_complete': True, 'last_token_lm_head_complete': True,
        'synthetic_memory_services': False,
    }
    for key, value in required.items():
        if key not in receipt or type(receipt[key]) is not type(value) or receipt[key] != value:
            raise ValueError(f'inadmissible {key}')
    for key in ('rtl_sha256', 'source_sha', 'model_revision', 'numerical_receipt_sha256',
                'counter_log_sha256'):
        if not receipt.get(key):
            raise ValueError(f'missing {key}')
    for key in ('expected_layers', 'completed_layers', 'wall_cycles',
                'useful_matrix_macs', 'executed_matrix_macs', 'ddr_read_bytes',
                'ddr_write_bytes'):
        if type(receipt.get(key)) is not int or receipt[key] < 0:
            raise ValueError(f'invalid {key}')
    if not receipt['expected_layers'] or receipt['completed_layers'] != receipt['expected_layers']:
        raise ValueError('incomplete layer coverage')
    cycles = receipt['wall_cycles']
    useful = receipt['useful_matrix_macs']
    executed = receipt['executed_matrix_macs']
    if cycles <= 0 or not 0 < useful <= executed <= cycles * 512:
        raise ValueError('MAC conservation')
    seconds = cycles / receipt['clock_hz']
    for key, limit in (('ddr_read_bytes', 100e9), ('ddr_write_bytes', 40e9)):
        if receipt[key] / seconds > limit:
            raise ValueError('DDR bandwidth exceeded')
    metrics = {'tokens_per_second': 1024 / seconds,
               'useful_wall_mac_utilization': useful / (512 * cycles),
               'executed_wall_mac_utilization': executed / (512 * cycles)}
    assert all(isfinite(v) for v in metrics.values())
    return metrics
