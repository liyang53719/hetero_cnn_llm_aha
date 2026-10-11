"""Focused packaging/address tests; no official forward or full swap enumeration."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'candidates/qwen2_transposed_dense'


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,SOURCE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


C=load('transposed_test_compare','compare.py')
F=load('transposed_test_full','full_chain.py')


def test_xor_and_two_half_bijection_real_port_bounds():
    result=C.address_proof()
    assert [x['k'] for x in result['cases']]==[16,256,1536,2048,2560,2752]
    for case in result['cases']:
        assert case['unique_halfwords']==128*case['k']
        assert case['words_per_bank']<=1376
        assert case['compute_max_reads_per_bank']==1
        assert case['fp32_beat_scatter_max_writes_per_bank']==1
    assert result['b_bijection_words']==16*160 and result['b_bytes']==81920
    assert result['b_two_word_compute_and_refill_banks_distinct']
    assert result['native_bf16_beat_min_bank_write_phases']==2
    assert not result['full_down_fits']


@pytest.mark.parametrize('m,k',[(128,0),(-1,0),(0,2752),(0,-1)])
def test_a_capacity_rejects_outside(m,k):
    with pytest.raises(ValueError,match='A address'):C.activation_address(m,k)


@pytest.mark.parametrize('half,k,n',[(2,0,0),(0,128,0),(0,0,160),(-1,0,0)])
def test_b_capacity_rejects_outside(half,k,n):
    with pytest.raises(ValueError,match='B address'):C.weight_address(half,k,n)


@pytest.mark.parametrize('k,reads',[(1536,1),(2048,1),(2560,1),(2576,2)])
def test_new_full_a_boundary_matches_cpp(k,reads):
    plan=C.dense_plan('boundary',k,256)
    assert plan['a_reads']==reads
    assert plan['activation_bytes']==128*k*4*reads
    assert plan['a_full_k_resident']==(k<=2560)
    # The comparison's old baseline retains its original K<=1536 contract.
    assert plan['old_activation_bytes']==C.D.expected_dense(128,k,256)['external_a_fp32_bytes']


def test_fixed_resources_and_full_owner_traffic():
    ledger=C.resource_ledger();traffic=C.traffic()
    assert ledger['scratch']['a_bytes']==704512 and ledger['scratch']['b_bytes']==81920
    assert ledger['payloads']['existing_leaf_result_register_bytes']==81920
    assert ledger['payloads']['fp32_contexts']==5 and ledger['payloads']['result_fifo_entries']==2
    assert len(traffic['owners'])==19 and len(traffic['dense'])==7
    assert traffic['totals']['read_bytes']==164888576
    assert traffic['totals']['write_bytes']==22544384
    assert sum(x['operand_ready_context_hazard_bubbles_without_refills'] for x in traffic['dense'])==30198
    assert traffic['down_ddr_prefix_alternative']['status']=='ANALYTIC_ONLY_NOT_EXECUTED'


def test_frozen_algorithm_and_attention_support_only():
    C.verify_algorithm_sources()
    source,identity=F.new_source()
    assert identity['transposed_body_sha256']==C.ALGORITHM_SHA256
    # The 15-stage C++ text matches the work-directory frozen executable source.
    # This is a source identity check, not a re-execution of that driver.
    assert C.R.sha(source.encode())=='4ce29539e1bd7345d5ccee88c7d70b056ec39bdadae4df416ebb401b9afbdcc1'
    assert len(identity['support_capacity_replacements'])==4
    assert source.count(F.D.NUMERIC_ATT.ATTENTION_BODY)==1
    assert 'uint16_t ac[16][1376][16], b[16][160][16]' in source
    assert 'uint16_t ac[16][1024][16], b[16][512][16]' not in source


def test_algorithm_tamper_rejected_before_generation(tmp_path,monkeypatch):
    altered=tmp_path/'source';altered.mkdir()
    for file in ('transposed_dense.inc.cpp','small_tests.inc.cpp'):shutil.copyfile(SOURCE/file,altered/file)
    path=altered/'transposed_dense.inc.cpp';path.write_text(path.read_text().replace('std::fma(wv,av,','std::fma(av,wv,'))
    monkeypatch.setattr(C,'HERE',altered)
    with pytest.raises(ValueError,match='algorithm changed'):C.verify_algorithm_sources()


def test_evidence_hash_and_stage_path_tamper_rejected(tmp_path):
    path=tmp_path/'receipt';path.write_text('original');identity=C.sha(path)
    path.write_text('changed')
    with pytest.raises(ValueError,match='changed evidence'):F.checked_hash(path,identity)
    stages=[dict(phase=i,name=n,path='../escape',width=1,sha256='0'*64) for i,n in enumerate(C.R.STAGE_NAMES)]
    with pytest.raises(ValueError,match='stage shape/order/path'):F.verify_stages(tmp_path,stages,16)


def test_m128_rejects_wrong_m16_identity_before_outputs(tmp_path):
    directory=tmp_path/'m16';directory.mkdir()
    (directory/'RESULT.json').write_text(json.dumps(dict(tokens=16,shape=dict(C.R.SHAPE,tokens=16),
        all_15_stages_bit_exact=True,completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',
        prepared_sha256='wrong',arena_sha256=F.ARENA_SHA)))
    with pytest.raises(ValueError,match='M16 prerequisite'):F.verify_m16(tmp_path,'expected',[])
    assert not (tmp_path/'m128').exists()


@pytest.mark.parametrize('kind',['shape','input','source','elf'])
def test_baseline_preflight_rejects_changed_identity(tmp_path,kind):
    _,identity=F.new_source();old=dict(identity['base_recipe_identity'])
    old.update(resident_attention_body_sha256=identity['unchanged_attention_body_sha256'],
               rectangular_attention=True,compile_command=['g++',*C.R.FLAGS])
    generated=tmp_path/'generated';generated.mkdir()
    for file,key in [('software_recipe.cpp','generated_cpp_sha256'),('block_layout.h','generated_header_sha256'),('software_recipe','binary_sha256')]:
        (generated/file).write_text(file);old[key]=C.sha(generated/file)
    receipt=dict(shape=dict(C.R.SHAPE,tokens=16),readonly_sha256=F.ARENA_SHA,
                 completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',source_identity=old)
    if kind=='shape':receipt['shape']['tokens']=128
    if kind=='input':receipt['readonly_sha256']='wrong'
    if kind=='source':old['source_pass_cpp_sha256']='wrong'
    if kind=='elf':(generated/'software_recipe').write_text('tampered')
    directory=tmp_path/'m16';directory.mkdir();(directory/'RESULT.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):F.verify_baselines(tmp_path,identity)


def test_prepare_rejects_wrong_arena_before_creating_output(tmp_path):
    arena=tmp_path/'arena';arena.write_bytes(b'invalid')
    out=tmp_path/'new-run'
    with pytest.raises(AssertionError):F.prepare(out,tmp_path/'baselines',arena,tmp_path/'small.json')
    assert not out.exists()


def test_m128_rejects_self_consistent_but_wrong_m16_stage(tmp_path):
    directory=tmp_path/'m16';directory.mkdir();stages=[];layout=C.R.make_layout()
    for phase,name in enumerate(C.R.STAGE_NAMES):
        width=next(r['words']//128 for r in layout['regions'] if r['name']==name)
        path=directory/f'phase_{phase}_{name}_recipe.f32le';path.write_bytes(bytes(16*width*4))
        stages.append(dict(phase=phase,name=name,width=width,path=path.name,sha256=C.sha(path)))
    (directory/'run.log').write_text('saved execution log')
    receipt=dict(tokens=16,shape=dict(C.R.SHAPE,tokens=16),all_15_stages_bit_exact=True,
        completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',prepared_sha256='expected',arena_sha256=F.ARENA_SHA,
        run_log_sha256=C.sha(directory/'run.log'),stages=stages)
    (directory/'RESULT.json').write_text(json.dumps(receipt))
    F.verify_stages(directory,stages,16) # self-consistent finite files alone pass
    frozen=[dict(s) for s in stages];frozen[0]['sha256']='f'*64
    with pytest.raises(ValueError,match='frozen baseline'):F.verify_m16(tmp_path,'expected',frozen)


def test_analytic_only_never_executes_cpp_or_qualifies_small_receipt(tmp_path,monkeypatch):
    def prohibited(*a,**k):raise AssertionError('numeric execution must not run')
    monkeypatch.setattr(C,'numeric',prohibited)
    output=tmp_path/'analytic';result=C.run(output,analytic_only=True)
    assert result['numeric'] is None and not result['numeric_executed']
    assert result['status']=='MODEL_ONLY_ANALYTIC_NOT_EXECUTED'
    assert not (output/'generated').exists()
    with pytest.raises(ValueError,match='small prerequisite'):F.verify_small(output/'SUMMARY.json')


def test_source_adjacent_or_existing_outputs_rejected(tmp_path):
    with pytest.raises(ValueError,match='outside candidate'):C.output_directory(SOURCE/'generated')
    with pytest.raises(ValueError,match='overwrite'):C.output_directory(tmp_path)
    with pytest.raises(ValueError,match='outside candidate'):F.configure(SOURCE/'run')


@pytest.mark.skipif(shutil.which('g++') is None,reason='ordinary C++ compiler unavailable')
def test_one_tiny_cpp_packaging_example(tmp_path):
    before={p.name for p in SOURCE.iterdir()}
    result=C.numeric(tmp_path/'tiny',tiny=True)
    assert result['coverage']=='packaging_tiny_only'
    assert result['mapped_runs']==2 and result['bit_mismatches']==0
    assert result['checked_values']==128*48*2
    assert result['swap_probe_triplets']==0 and not result['official_model_run']
    assert {p.name for p in SOURCE.iterdir()}==before
    log=(tmp_path/'tiny/generated/run.log').read_text()
    assert 'TINY_COMPARISON_PASS' in log and 'OPERAND_SWAP ' not in log
