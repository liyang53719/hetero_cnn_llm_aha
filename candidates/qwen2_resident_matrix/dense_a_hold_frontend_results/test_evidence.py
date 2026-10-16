"""Immutable frontend archive and negative scope tests; no Scala/RTL run."""
import json
import shutil

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_frontend_results import validate as evidence


def test_original_safe_archive():
    result=evidence.validate()
    assert result['scala_compiled'] and result['chirrtl_generated']
    assert not result['rtl_generated'] and not result['hardware_protocol_executed']
    assert not result['arithmetic_executed'] and not result['full_business_block_acceptance']


@pytest.mark.parametrize('field,value',[
    ('commit','0'*40),('run_id',38973350758),('run_attempt',2),
    ('artifact_id',12076709706),('artifact_zip_bytes',10607),
    ('rtl_generated',True),('hardware_protocol_executed',True),
    ('arithmetic_executed',True),('full_business_block_acceptance',True),
    ('timing_or_utilization_measured',True),('repository_input_hashes_compared',62),
])
def test_reject_manifest_identity_or_claim_drift(tmp_path,field,value):
    for path in evidence.HERE.glob('*.json'):shutil.copyfile(path,tmp_path/path.name)
    m=json.loads((tmp_path/'manifest.json').read_text());m[field]=value
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError):evidence.validate(tmp_path)


@pytest.mark.parametrize('name',list(evidence.FILES))
def test_reject_even_whitespace_receipt_mutation(tmp_path,name):
    for path in evidence.HERE.glob('*.json'):shutil.copyfile(path,tmp_path/path.name)
    path=tmp_path/name;path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='member drift'):evidence.validate(tmp_path)


def test_reject_extra_archive_member(tmp_path):
    for path in evidence.HERE.glob('*.json'):shutil.copyfile(path,tmp_path/path.name)
    (tmp_path/'unreviewed.json').write_text('{}')
    with pytest.raises(ValueError,match='allowlist'):evidence.validate(tmp_path)


def test_reject_duplicate_json_identity(tmp_path):
    path=tmp_path/'bad.json';path.write_text('{"run_attempt":1,"run_attempt":2}')
    with pytest.raises(ValueError,match='duplicate JSON key'):evidence.read(path)


@pytest.mark.parametrize('case',[
    'protocol_claim','failed_stage','missing_configuration','extra_bank_port',
    'wrong_queue','wrong_hold','extra_register','wrong_source_pins','missing_dependency',
])
def test_semantics_fail_closed_before_hashes_are_considered(case):
    s=evidence.read(evidence.HERE/'summary.json')
    source=evidence.read(evidence.HERE/'source-sha256.json')
    dep=evidence.read(evidence.HERE/'dependency-sha256.json')
    r=s['configurations']['owner_hold1_full1.fir']['resources']
    if case=='protocol_claim':s['hardware_protocol_executed']=True
    if case=='failed_stage':s['stages'][1]['exit_code']=1
    if case=='missing_configuration':s['configurations'].pop('owner_hold0_full0.fir')
    if case=='extra_bank_port':r['read_ports_per_bank']=2
    if case=='wrong_queue':r['operand_fifo']['depth']=4
    if case=='wrong_hold':r['hold_payload_bits']=4096
    if case=='extra_register':s['register_delta']['1']['added_owner_registers']['free_cache']='UInt<512>[128]'
    if case=='wrong_source_pins':source['source_pins_sha256']='0'*64
    if case=='missing_dependency':dep['jars'].pop(next(iter(dep['jars'])))
    with pytest.raises(ValueError):evidence.validate_payloads(s,source,dep)
