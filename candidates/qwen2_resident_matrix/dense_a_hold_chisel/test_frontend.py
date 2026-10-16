"""Negative audits and mocked runner only; no JVM, network, lowering or RTL."""
import json
import hashlib
from pathlib import Path
import subprocess

import pytest

from candidates.qwen2_resident_matrix.dense_a_hold_chisel import check_frontend as gate
from candidates.qwen2_resident_matrix.raw_kv_parent.test_unit_prepare import synthetic_chirrtl


def fixture(enabled):
    text=synthetic_chirrtl()
    text=text.replace('  module Queue4_MatrixStreamStep :',
        '    reg selected : {'+('readActivation:UInt<1>,' if enabled else '')+
        'k:UInt<12>,context:UInt<3>,half:UInt<1>}, clock\n  module Queue4_MatrixStreamStep :')
    if enabled:
        text=text.replace('}[4]','}[3]').replace('Queue4_MatrixStreamStep','Queue3_MatrixStreamStep')
        text+=''.join('    reg '+name+' : '+shape+', clock\n' for name,shape in (
            ('heldA','UInt<16>[128]'),('heldAK','UInt<12>'),
            ('heldAGeneration','UInt<32>'),('pendingAGeneration','UInt<32>'),('heldAValid','UInt<1>')))
    return text


@pytest.mark.parametrize('enabled',[False,True])
def test_synthetic_inventory_accepts_only_expected_shape(enabled):
    result=gate.memory_audit(fixture(enabled),enabled)
    assert result['sram_memories']==32 and result['total_memory_declarations']==33
    assert result['operand_fifo']['depth']==(3 if enabled else 4)
    assert result['hold_payload_bits']==(2048 if enabled else 0)
    assert not result['physical_area_or_timing_measured']


@pytest.mark.parametrize('bad',[
    lambda s:s.replace('}[3]','}[4]'),
    lambda s:s.replace('UInt<16>[128]','UInt<16>[129]'),
    lambda s:s.replace('heldAK : UInt<12>','heldAK : UInt<13>'),
    lambda s:s.replace('readActivation:UInt<1>','readActivation:UInt<2>'),
    lambda s:s.replace('read mport r0','write mport r0'),
    lambda s:s+'    cmem shadow : UInt<512>[128]\n',
])
def test_synthetic_inventory_rejects_resource_drift(bad):
    with pytest.raises(ValueError):gate.memory_audit(bad(fixture(True)),True)


def test_register_delta_catches_hidden_registers():
    result=gate.register_delta(fixture(False),fixture(True))
    assert result['added_payload_bits']==2048 and result['added_control_bits']==78
    with pytest.raises(ValueError):gate.register_delta(fixture(False),fixture(True)+'    reg extra : UInt<512>, clock\n')


def test_same_pinned_dependency_set_and_budget():
    assert len(gate.dependencies())==87
    assert gate.JAVA==['java','-Xmx1024m','-XX:ActiveProcessorCount=1']
    assert gate.TOTAL_SECONDS==420 and sum(gate.STAGES.values())==390
    assert not any('chiseltest' in path or 'scalatest' in path for path in gate.dependencies())


def test_mocked_runner_only_compiles_real_closure_and_four_frontends(tmp_path,monkeypatch):
    commands=[]
    payload=b'not a jar; mocked runner fixture only'
    monkeypatch.setattr(gate,'dependencies',lambda:{'fixture.jar':hashlib.sha256(payload).hexdigest()})
    def fake(argv,**kwargs):
        commands.append(argv)
        assert kwargs['timeout']<=180
        if '--fetch-only' in argv:
            cache=Path(argv[-1]);cache.mkdir();(cache/'fixture.jar').write_bytes(payload)
        if 'heteronpu.continuous.AHoldElaborate' in argv:
            out=Path(argv[-1]);out.mkdir()
            for name in gate.EXPECTED:
                (out/name).write_text(fixture(bool(int(name[len('owner_hold')]))))
        return 0
    monkeypatch.setattr(gate,'run_group',fake)
    result=gate.run(tmp_path/'result',tmp_path/'cache')
    assert result['status']=='PASS_FRONTEND_ONLY'
    assert result['scala_compiled'] and result['chirrtl_generated']
    assert not result['rtl_generated'] and not result['hardware_protocol_executed']
    assert not result['arithmetic_executed'] and not result['full_business_block_acceptance']
    assert result['precompile_and_postflight_hashes_equal']
    assert len(commands)==3
    compile_command=commands[1]
    assert 'scala.tools.nsc.Main' in compile_command
    sources=[x for x in compile_command if x.endswith('.scala')]
    assert len(sources)==14 and sources[-1].endswith('/AHoldElaborate.scala')
    assert not any('AHoldUnit.scala' in x for x in sources)
    receipt=json.loads((tmp_path/'result/source-sha256.json').read_text())
    assert len(receipt['generated'])==14 and len(receipt['inputs'])>=56


@pytest.mark.parametrize('drift',['generated_source','jar','precompile_jar','extra_emitter'])
def test_mocked_source_or_jar_drift_never_returns_pass(tmp_path,monkeypatch,drift):
    payload=b'not a jar; mutation test fixture only'
    monkeypatch.setattr(gate,'dependencies',lambda:{'fixture.jar':hashlib.sha256(payload).hexdigest()})
    def fake(argv,**kwargs):
        if '--fetch-only' in argv:
            cache=Path(argv[-1]);cache.mkdir()
            (cache/'fixture.jar').write_bytes(b'wrong' if drift=='precompile_jar' else payload)
        if 'heteronpu.continuous.AHoldElaborate' in argv:
            out=Path(argv[-1]);out.mkdir()
            for name in gate.EXPECTED:(out/name).write_text(fixture(bool(int(name[len('owner_hold')]))))
            if drift=='generated_source':(out.parent/'source/TransposedDenseBanks.scala').write_text('changed generated source')
            if drift=='extra_emitter':(out.parent/'source/AHoldElaborate.scala').write_text('unattested extra source')
            if drift=='jar':(tmp_path/'cache/fixture.jar').write_bytes(b'changed jar')
        return 0
    monkeypatch.setattr(gate,'run_group',fake)
    with pytest.raises(ValueError,match='changed during frontend'):
        gate.run(tmp_path/'result',tmp_path/'cache')
    result=json.loads((tmp_path/'result/summary.json').read_text())
    assert result['status']=='FAILED' and not result.get('precompile_and_postflight_hashes_equal',False)
    if drift=='precompile_jar':assert not result['scala_compiled']


def test_mocked_timeout_has_failed_receipt_and_no_false_elaboration(tmp_path,monkeypatch):
    def timeout(argv,**kwargs):raise subprocess.TimeoutExpired(argv,kwargs['timeout'])
    monkeypatch.setattr(gate,'run_group',timeout)
    with pytest.raises(subprocess.TimeoutExpired):gate.run(tmp_path/'result',tmp_path/'cache')
    result=json.loads((tmp_path/'result/summary.json').read_text())
    assert result['status']=='FAILED' and result['stages'][0]['status']=='TIMEOUT'
    assert not result['scala_compiled'] and not result['chirrtl_generated'] and not result['rtl_generated']
    assert (tmp_path/'result/diagnostic.txt').stat().st_size<=4096


def test_workflow_is_single_launch_revision_with_safe_artifacts():
    workflow=(gate.ROOT/'.github/workflows/qwen2-dense-a-hold-frontend.yml').read_text()
    assert "paths: ['.github/workflows/qwen2-dense-a-hold-frontend.yml']" in workflow
    assert 'if: github.run_attempt == 1' in workflow and 'timeout-minutes: 9' in workflow
    assert "java-version: '21'" in workflow
    uploaded=workflow.split('          path: |',1)[1]
    assert [line.strip().rsplit('/',1)[-1] for line in uploaded.splitlines() if line.strip()]==[
        'summary.json','source-sha256.json','dependency-sha256.json','diagnostic.txt']
    assert 'sbt/setup' not in workflow and 'apt-get' not in workflow
    assert 'check_frontend.py' in workflow and 'run_unit.py' not in workflow
