"""Read-only report/source tests. Native execution is a separate opt-in run."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_numeric import check_numeric as n


def stored():
    return json.loads(Path(__file__).with_name('NUMERIC_RESULT.json').read_text())


def test_source_closure_and_saved_execution():
    assert len(n.sources()['sources'])==20
    assert len(n.snapshot())==22
    assert n.validate_report(stored())==stored()


@pytest.mark.parametrize('field',['complete_business_block_acceptance','rtl_execution',
    'timing_or_utilization_claim','independent_framework_reference','real_checkpoint_weights','recompiled'])
def test_report_rejects_expanded_claims(field):
    r=stored();r[field]=True
    with pytest.raises(ValueError):n.validate_report(r)


@pytest.mark.parametrize('field,value',[('actual_fma_calls',1),('output_words',1),
    ('max_joined_payload_slots',3),('max_reserved_operands',4),('accumulator_bytes',163840),
    ('accepted_debt_retired',False),('a_gathers',1),('returned_full_4096_cell_payloads',1),
    ('restored_seed_contexts',1),('packets_sha256','0'*64)])
def test_report_rejects_missing_work_storage_or_retirement(field,value):
    r=deepcopy(stored());r['cases'][3]['candidate'][field]=value
    with pytest.raises(ValueError):n.validate_report(r)


def test_rejects_unpinned_compile_receipt_before_loading(tmp_path):
    receipt=tmp_path/'compile.json';receipt.write_text('{}')
    with pytest.raises(ValueError,match='receipt drift'):n.verify_library(receipt)


def test_inputs_include_finite_rne_boundary_words():
    for kind in ('a','b'):
        for index in range(64):
            bits=n.synthetic_bits(kind,index)
            assert bits&0x7f80 != 0x7f80
            lo=bits<<16
            assert n.model.down.bf16_rne(lo|0x7fff)==bits
            assert n.model.down.bf16_rne(lo|0x8000)==bits+(bits&1)
            assert n.model.down.bf16_rne(lo|0x8001)==bits+1
