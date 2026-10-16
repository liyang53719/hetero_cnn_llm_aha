"""Cold source, parser, resource and mocked process checks. Never starts Java."""
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_interpreter import run as gate
from candidates.qwen2_resident_matrix.dense_a_hold_interpreter.prepare import prepare
from candidates.qwen2_resident_matrix.dense_a_hold_chisel.test_frontend import fixture


def good_log(cycles=1200):
    lines=['AHOLD_CASE_BEGIN reuse=true k=32','AHOLD_SIM_READY reuse=true k=32']
    lines += [f'AHOLD_CYCLE reuse=true k=32 cycle={c}' for c in range(1024,cycles+1,1024)]
    lines += [f'AHOLD_CASE_PASS reuse=true k=32 accepted=352 returned=352 gathered=160 a_reads=32 steps=160 cycles={cycles}',
        '- '+gate.CASE,'Total number of tests run: 1','All tests passed.']
    return '\n'.join(lines)+'\n'


def test_exact_one_case_receipt():
    r=gate.result_audit(good_log())
    assert (r['m'],r['k'],r['n'])==(16,32,160)
    assert r['matrix_packets']==160 and r['a_bank_gathers']==32
    assert r['accepted_dma_requests']==r['retired_dma_responses']==352


@pytest.mark.parametrize('old,new',[
    ('tests run: 1','tests run: 0'),('tests run: 1','tests run: 3'),
    ('All tests passed.','*** FAILED ***'),
    ('AHOLD_SIM_READY reuse=true k=32','AHOLD_SIM_READY reuse=false k=32'),
    ('accepted=352','accepted=353'),('returned=352','returned=0'),
    ('gathered=160','gathered=159'),('a_reads=32','a_reads=160'),
    ('steps=160','steps=159'),('cycles=1200','cycles=20001'),
    ('AHOLD_CYCLE reuse=true k=32 cycle=1024','AHOLD_CYCLE reuse=true k=32 cycle=1025'),
    ('k=32','k=256'),
])
def test_missing_or_wrong_actual_case_cannot_pass(old,new):
    with pytest.raises(ValueError):gate.result_audit(good_log().replace(old,new))


def test_missing_duplicate_or_foreign_marker_cannot_pass():
    for line in ['AHOLD_CASE_BEGIN reuse=true k=32','AHOLD_SIM_READY reuse=true k=32','AHOLD_CYCLE reuse=true k=32 cycle=1024']:
        with pytest.raises(ValueError):gate.result_audit(good_log().replace(line+'\n',''))
        with pytest.raises(ValueError):gate.result_audit(good_log().replace(line,line+'\n'+line))
    with pytest.raises(ValueError):gate.result_audit(good_log()+'AHOLD_CASE_PASS reuse=true k=256\n')
    for field in ('failed','canceled','ignored','pending','aborted'):
        with pytest.raises(ValueError):gate.result_audit(good_log()+field+' 1\n')


def test_cycle_ceiling_is_inclusive():
    assert gate.result_audit(good_log(20000))['clock_cycles']==20000


def origin_log(cache):
    return ''.join(f'AHOLD_CLASS_ORIGIN {name} {(cache/path).as_uri()}\n' for name,path in gate.CLASS_ORIGINS.items())


def test_actual_loaded_class_origins_are_exact_selected_jars(tmp_path):
    selected={path:'1'*64 for path in gate.CLASS_ORIGINS.values()}
    found=gate.origin_audit(origin_log(tmp_path),tmp_path,selected)
    assert set(found)==set(gate.CLASS_ORIGINS) and len(found)==7


@pytest.mark.parametrize('bad',['wrong_jar','missing','duplicate','foreign_class','http','fragment'])
def test_reject_wrong_or_missing_runtime_code_source(tmp_path,bad):
    selected={path:'1'*64 for path in gate.CLASS_ORIGINS.values()}
    log=origin_log(tmp_path);first=log.splitlines()[0]
    if bad=='wrong_jar':log=log.replace('chiseltest_2.13-6.0.0.jar','chiseltest_2.13-5.0.0.jar')
    if bad=='missing':log=log.replace(first+'\n','')
    if bad=='duplicate':log+=first+'\n'
    if bad=='foreign_class':log=log.replace('treadle2.TreadleTester','foreign.Mock')
    if bad=='http':log=log.replace('file:','http:')
    if bad=='fragment':log=log.replace(first,first+'#other')
    with pytest.raises(ValueError):gate.origin_audit(log,tmp_path,selected)


def write_structure(path):
    path.mkdir();original=fixture(True)
    (path/'owner.fir').write_text(original)
    (path/'probe.fir').write_text(original.replace('TransposedDenseDownOwner','AHoldProbe'))


def test_probe_structure_keeps_actual_resource_inventory(tmp_path):
    write_structure(tmp_path/'fir');r=gate.structural_audit(tmp_path/'fir')
    assert r['resources']['sram_memories']==32 and r['resources']['operand_fifo']['depth']==3
    assert r['resources']['hold_payload_bits']==2048 and not r['probe_changes_registers']


@pytest.mark.parametrize('change',[
    lambda s:s+'    reg hidden : UInt<512>, clock\n',
    lambda s:s.replace('}[3]','}[4]'),
    lambda s:s.replace('UInt<16>[128]','UInt<16>[129]'),
    lambda s:s.replace('read mport r0','write mport r0'),
    lambda s:s.replace('module AHoldProbe :','module MockOwner :'),
])
def test_probe_cannot_hide_extra_resource_or_wrong_top(tmp_path,change):
    write_structure(tmp_path/'fir');p=tmp_path/'fir/probe.fir';p.write_text(change(p.read_text()))
    with pytest.raises(ValueError):gate.structural_audit(tmp_path/'fir')


def test_prepared_harness_only_uses_actual_owner_and_explicit_interpreter(tmp_path):
    generated=prepare(tmp_path/'source');assert len(generated)==15
    unit=(tmp_path/'source/AHoldUnit.scala').read_text()
    assert unit.count('withAnnotations(Seq(TreadleBackendAnnotation))')==2
    assert 'class AHoldProbe(reuse:Boolean) extends TransposedDenseDownOwner' in unit
    assert 'while(!done && cycle<20000)' in unit
    assert 'if(fault)assert(!readFire' in unit and 'accepted==returned' in unit
    assert 'VerilatorBackendAnnotation' not in unit and 'peekMemory' not in unit


def test_frozen_dependency_delta_is_explicit_and_original_unchanged():
    selected=gate.dependencies();lock=json.loads((gate.HERE/'dependency-lock.json').read_text())
    assert len(selected)==106 and len(lock['added'])==25 and len(lock['removed'])==6
    assert not (set(lock['removed']) & set(selected))
    assert lock['new_jars_executed_during_freeze'] is False
    assert gate.sha(gate.ROOT/lock['base_lock'])==lock['base_lock_sha256']
    assert gate.TOTAL_SECONDS==600 and sum(gate.STAGES.values())==570
    assert gate.JAVA_FLAGS==['-showversion','-Xmx2048m','-Xss4m','-XX:ActiveProcessorCount=1']


def mock_processes(tmp_path,monkeypatch,drift=None):
    commands=[];payload=b'cold fixture, not an executable jar'
    selected={path:hashlib.sha256(payload).hexdigest() for path in gate.CLASS_ORIGINS.values()}
    monkeypatch.setattr(gate,'dependencies',lambda:selected)
    java=tmp_path/'java';java.write_text('cold fixture, not executable')
    monkeypatch.setattr(gate.shutil,'which',lambda _:str(java))
    def fake(argv,**kw):
        commands.append(argv)
        assert kw['timeout']<=240
        if '--fetch-only' in argv:
            cache=Path(argv[-1]);cache.mkdir()
            for path in selected:
                p=cache/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'wrong' if drift=='precompile_jar' else payload)
        else:
            assert kw['env']['PATH'].endswith('/no-external-tools')
            assert '-Xmx2048m' in argv and '-XX:ActiveProcessorCount=1' in argv
        if 'scala.tools.nsc.Main' in argv:
            kw['log'].write('openjdk version "21.0.8"\n')
            (Path(kw['cwd'])/'classes/Fixture.class').write_bytes(b'cold fixture, not JVM bytecode')
        if 'heteronpu.continuous.ProbeElaborate' in argv:
            write_structure(Path(argv[-1]))
            if drift=='preinterpret_class':(Path(kw['cwd'])/'classes/Fixture.class').write_bytes(b'drift')
        if 'org.scalatest.tools.Runner' in argv:
            kw['log'].write(good_log()+origin_log(tmp_path/'cache'))
            out=Path(kw['cwd'])
            if drift=='generated':(out/'source/TransposedDenseOwner.scala').write_text('drift')
            if drift=='extra_source':(out/'source/Unreviewed.scala').write_text('drift')
            if drift=='postflight_jar':(tmp_path/'cache'/next(iter(selected))).write_bytes(b'drift')
            if drift=='java':java.write_text('drift')
            if drift=='native_artifact':(out/'hidden.sv').write_text('unexpected emitted RTL')
            if drift=='postflight_class':(out/'classes/Fixture.class').write_bytes(b'drift')
            if drift=='extra_class':(out/'classes/Unexpected.class').write_bytes(b'drift')
        return 0
    monkeypatch.setattr(gate,'run_group',fake)
    return commands


def test_mocked_runner_never_launches_a_real_jvm(tmp_path,monkeypatch):
    commands=mock_processes(tmp_path,monkeypatch)
    r=gate.run(tmp_path/'out',tmp_path/'cache')
    assert len(commands)==4 and r['status']=='PASS_ONE_CASE_INTERPRETED_PROTOCOL'
    assert r['interpreted_hardware_protocol'] and r['precompile_and_postflight_hashes_equal']
    for field in ('rtl_generated','emitted_rtl_simulation','matrix_arithmetic','full_business_block_acceptance','hardware_timing_or_utilization'):assert r[field] is False
    assert len([s for s in commands[1] if s.endswith('.scala')])==15
    assert commands[-1][-2:]==['-z','reuse=true'] and '-oW' in commands[-1]


@pytest.mark.parametrize('drift',['precompile_jar','postflight_jar','generated','extra_source','java','native_artifact','preinterpret_class','postflight_class','extra_class'])
def test_mocked_provenance_or_scope_drift_preserves_failed_result(tmp_path,monkeypatch,drift):
    mock_processes(tmp_path,monkeypatch,drift)
    with pytest.raises(ValueError):gate.run(tmp_path/'out',tmp_path/'cache')
    r=json.loads((tmp_path/'out/summary.json').read_text())
    assert r['status']=='FAILED' and not r['interpreted_hardware_protocol']
    assert not r.get('precompile_and_postflight_hashes_equal',False)
    if drift=='precompile_jar':assert not r['scala_compiled']


def test_mocked_timeout_is_failure_with_small_diagnostics(tmp_path,monkeypatch):
    mock_processes(tmp_path,monkeypatch)
    def timeout(argv,**kw):raise subprocess.TimeoutExpired(argv,kw['timeout'])
    monkeypatch.setattr(gate,'run_group',timeout)
    with pytest.raises(subprocess.TimeoutExpired):gate.run(tmp_path/'out',tmp_path/'cache')
    r=json.loads((tmp_path/'out/summary.json').read_text())
    assert r['status']=='FAILED' and r['stages'][0]['status']=='TIMEOUT'
    assert not r['scala_compiled'] and not r['interpreted_hardware_protocol']
    assert (tmp_path/'out/diagnostic.txt').stat().st_size<=4096


def test_direct_compiler_and_scalatest_diagnostics_are_preserved_safely(tmp_path):
    log=tmp_path/'failure.log'
    log.write_text('/private/build/AHoldUnit.scala:6: error: not found: object chiseltest\n'
        '  println("source echo must stay private")\n'
        '- packet case *** FAILED ***\n'
        'chiseltest.FailedExpectException: actual did not equal expected\n'
        'java.lang.OutOfMemoryError: Java heap space\n'
        'error: token=ghp_12345678901234567890 payload: secret-array\n'
        'error: password=private-value\n')
    text=gate.failure_diagnostics(log,stage='compile',error='stage failed')
    for expected in ('AHoldUnit.scala:6: error:','*** FAILED ***','FailedExpectException','OutOfMemoryError'):assert expected in text
    for forbidden in ('source echo','/private/build','ghp_123','secret-array','private-value'):assert forbidden not in text
    assert len(text.encode())<=4096


def test_failure_progress_survives_large_log_without_copying_log(tmp_path):
    log=tmp_path/'interpreter.log'
    log.write_text('AHOLD_CASE_BEGIN reuse=true k=32\nAHOLD_SIM_READY reuse=true k=32\n'+
        ('unselected source or data '+('x'*100)+'\n')*4000+
        'AHOLD_CYCLE reuse=true k=32 cycle=2048\njava.lang.OutOfMemoryError: Java heap space\n')
    r=gate.failure_progress(log)
    assert r=={'case_begin_seen':True,'sim_ready_seen':True,'last_reported_cycle':2048,'case_pass_marker_seen':False}
    text=gate.failure_diagnostics(log,stage='interpret',error='timed out')
    assert 'OutOfMemoryError' in text and 'unselected source' not in text


def test_mocked_interpreter_timeout_retains_actual_progress_markers(tmp_path,monkeypatch):
    mock_processes(tmp_path,monkeypatch);original=gate.run_group
    def fake(argv,**kwargs):
        if 'org.scalatest.tools.Runner' in argv:
            kwargs['log'].write('AHOLD_CASE_BEGIN reuse=true k=32\nAHOLD_SIM_READY reuse=true k=32\nAHOLD_CYCLE reuse=true k=32 cycle=1024\n')
            raise subprocess.TimeoutExpired(argv,kwargs['timeout'])
        return original(argv,**kwargs)
    monkeypatch.setattr(gate,'run_group',fake)
    with pytest.raises(subprocess.TimeoutExpired):gate.run(tmp_path/'out',tmp_path/'cache')
    r=json.loads((tmp_path/'out/summary.json').read_text())
    assert r['status']=='FAILED' and r['stages'][-1]['status']=='TIMEOUT'
    assert r['interpret_progress']=={'case_begin_seen':True,'sim_ready_seen':True,'last_reported_cycle':1024,'case_pass_marker_seen':False}
    assert not r['interpreted_hardware_protocol']


@pytest.mark.parametrize('target',['repository','pins','workflow','lock'])
@pytest.mark.parametrize('phase',['precompile','postflight'])
def test_mocked_attestation_input_mutation_never_passes(tmp_path,monkeypatch,target,phase):
    mock_processes(tmp_path,monkeypatch)
    original_process=gate.run_group;original_sha=gate.sha;active=False
    path={'repository':gate.HERE/'run.py','pins':gate.HERE/'source_pins.json',
          'workflow':gate.ROOT/gate.WORKFLOW,'lock':gate.HERE/'dependency-lock.json'}[target]
    def fake(argv,**kwargs):
        nonlocal active
        rc=original_process(argv,**kwargs)
        if (phase=='precompile' and '--fetch-only' in argv) or (phase=='postflight' and 'org.scalatest.tools.Runner' in argv):active=True
        return rc
    monkeypatch.setattr(gate,'run_group',fake)
    monkeypatch.setattr(gate,'sha',lambda p:'0'*64 if active and p==path else original_sha(p))
    with pytest.raises(ValueError):gate.run(tmp_path/'out',tmp_path/'cache')
    r=json.loads((tmp_path/'out/summary.json').read_text())
    assert r['status']=='FAILED' and not r['interpreted_hardware_protocol']
    if phase=='precompile':assert not r['scala_compiled']


def test_workflow_closed_and_only_small_evidence_uploaded():
    workflow=(gate.ROOT/gate.WORKFLOW).read_text()
    if 'if: ${{ false }}' in workflow:assert 'push:' not in workflow
    else:
        assert 'if: github.run_attempt == 1' in workflow
        assert "paths: ['.github/workflows/qwen2-dense-a-hold-interpreter.yml']" in workflow
    assert 'timeout-minutes: 12' in workflow and "java-version: '21'" in workflow
    uploaded=workflow.split('          path: |',1)[1]
    assert [x.strip().rsplit('/',1)[-1] for x in uploaded.splitlines() if x.strip()]==[
        'summary.json','source-sha256.json','dependency-sha256.json','diagnostic.txt']
