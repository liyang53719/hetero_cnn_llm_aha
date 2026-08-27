import json
from pathlib import Path
import pytest
from heteronpu.planning_v6 import audit_control,arch_collateral,build_qwen38_program,compile_mock,load_arch,SequenceMemory
ROOT=Path(__file__).resolve().parents[1]
PROFILE=json.loads((ROOT/'config/model_profiles/qwen3_8_flash_next.json').read_text())
def test_arch_and_control():
    a=load_arch('configs/arch_v2_qwen38_candidate.yaml',ROOT);c=arch_collateral(a)
    assert c['total_sram_bytes']==4096*1024 and len(c['sram_map'])==7
    assert 'grouped_expert_gemm' in c['matrix_modes']
    assert audit_control(ROOT)['status']=='PASS'
def test_program_and_mock():
    p=build_qwen38_program(PROFILE,'prefill',1024,weight_bits=4);d=build_qwen38_program(PROFILE,'decode',1,262144,4)
    assert p['operation_count']==d['operation_count']==500
    assert p['total_macs']==6373421613056 and d['total_macs']==6852331520
    assert compile_mock(p)['analytical_total_cycles']>0
    assert p['program_sha256']==build_qwen38_program(PROFILE,'prefill',1024,weight_bits=4)['program_sha256']
def test_sequence_memory():
    m=SequenceMemory();m.create(1,2,3,4);m.map_page(1,2,3,4,0,9);m.map_page(1,2,3,4,1,10)
    assert m.translate(1,2,3,4,0)['path']=='page_walk'
    assert m.translate(1,2,3,4,1)['path']=='tlb_hit'
    assert m.translate(1,2,3,4,16)['path']=='leaf_cache_hit'
    with pytest.raises(ValueError):m.translate(1,2,3,5,0)
