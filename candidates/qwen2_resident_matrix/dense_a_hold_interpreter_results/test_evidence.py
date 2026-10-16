"""Original failure identity and fail-closed scope checks; no JVM or EDA."""
import json
import shutil

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_interpreter_results import validate as evidence


def copied(tmp_path):
    for name in ('manifest.json',*evidence.FILES):
        shutil.copyfile(evidence.HERE/name,tmp_path/name)
    return tmp_path


def test_original_timeout_is_preserved():
    result=evidence.validate()
    assert result['status']=='PASS_IMMUTABLE_FAILURE_ARCHIVE'
    assert result['original_run_conclusion']=='failure'
    assert result['scala_compiled'] and result['chirrtl_generated']
    assert not result['interpreted_hardware_protocol']
    assert result['actual_clock_cycles_observed'] is None


@pytest.mark.parametrize('field,value',[
    ('commit','0'*40),('run_id',38976754471),('run_attempt',2),
    ('job_id',117227926194),('artifact_id',12079995426),
    ('artifact_zip_bytes',17525),('run_conclusion','success'),
    ('actual_clock_cycles_observed',0),('specific_startup_subphase','FIRRTL lowering'),
    ('startup_timeout_is_inference',False),('test_callback_observed',True),
    ('runtime_class_origins_retained',True),('postflight_hash_equality_claimed',True),
    ('compiled_class_bytes_downloaded',True),('interpreted_hardware_protocol',True),
    ('emitted_rtl_simulation',True),('matrix_arithmetic',True),
    ('full_business_block_acceptance',True),('hardware_timing_or_utilization',True),
    ('repository_input_hashes_verified',74),('generated_sources_recomposed',14),
    ('locked_dependency_identities_matched',105),('recorded_compiled_class_hashes',111),
])
def test_reject_identity_or_invented_runtime_claim(tmp_path,field,value):
    copied(tmp_path)
    manifest=evidence.read(tmp_path/'manifest.json');manifest[field]=value
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):evidence.validate(tmp_path)


@pytest.mark.parametrize('name',list(evidence.FILES))
def test_reject_even_whitespace_original_mutation(tmp_path,name):
    copied(tmp_path);path=tmp_path/name
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='original receipt changed'):evidence.validate(tmp_path)


@pytest.mark.parametrize('name',['invented.json','owner.fir','classes.jar','full.log'])
def test_no_unreviewed_or_large_artifacts(tmp_path,name):
    copied(tmp_path);(tmp_path/name).write_text('unreviewed')
    with pytest.raises(ValueError,match='allowlist'):evidence.validate(tmp_path)


def test_reject_linked_artifact(tmp_path):
    copied(tmp_path);path=tmp_path/'diagnostic.txt';path.unlink()
    path.symlink_to(evidence.HERE/'diagnostic.txt')
    with pytest.raises(ValueError,match='allowlist'):evidence.validate(tmp_path)


def test_reject_duplicate_json_identity(tmp_path):
    path=tmp_path/'bad.json';path.write_text('{"run_attempt":1,"run_attempt":2}')
    with pytest.raises(ValueError,match='duplicate JSON key'):evidence.read(path)


@pytest.mark.parametrize('case',[
    'success','runtime_acceptance','invented_postflight','sim_ready','invented_cycle',
    'invented_case','invented_origins','raised_budget','successful_interpret',
    'zero_exit_after_timeout','compile_failure','extra_bank_port','extra_hold',
    'different_queue','numeric_endpoint','wrong_workflow','wrong_lock','missing_jar',
    'missing_input','unsafe_class_path',
])
def test_semantics_reject_false_claim_even_before_original_byte_check(case):
    s=evidence.read(evidence.HERE/'summary.json')
    src=evidence.read(evidence.HERE/'source-sha256.json')
    deps=evidence.read(evidence.HERE/'dependency-sha256.json')
    r=s['structure']['resources']
    if case=='success':s['status']='PASS'
    if case=='runtime_acceptance':s['interpreted_hardware_protocol']=True
    if case=='invented_postflight':s['precompile_and_postflight_hashes_equal']=True
    if case=='sim_ready':s['interpret_progress']['sim_ready_seen']=True
    if case=='invented_cycle':s['interpret_progress']['last_reported_cycle']=0
    if case=='invented_case':s['case']={}
    if case=='invented_origins':s['loaded_class_origins']={}
    if case=='raised_budget':s['budget']['stages_seconds']['interpret']=600
    if case=='successful_interpret':s['stages'][-1]['status']='PASS'
    if case=='zero_exit_after_timeout':s['stages'][-1]['exit_code']=0
    if case=='compile_failure':s['stages'][1]['exit_code']=1
    if case=='extra_bank_port':r['read_ports_per_bank']=2
    if case=='extra_hold':r['hold_payload_bits']=4096
    if case=='different_queue':r['operand_fifo']['depth']=4
    if case=='numeric_endpoint':r['matrix_or_hardfloat_instantiated']=True
    if case=='wrong_workflow':src['workflow_sha256']='0'*64
    if case=='wrong_lock':deps['lock_sha256']='0'*64
    if case=='missing_jar':deps['jars'].pop(next(iter(deps['jars'])))
    if case=='missing_input':src['inputs'].pop(next(iter(src['inputs'])))
    if case=='unsafe_class_path':
        value=src['compiled_classes'].pop(next(iter(src['compiled_classes'])))
        src['compiled_classes']['../outside.class']=value
    with pytest.raises(ValueError):evidence.validate_payloads(s,src,deps)
