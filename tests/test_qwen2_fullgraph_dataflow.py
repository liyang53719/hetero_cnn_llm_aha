"""Bounded fullgraph packaging checks; never execute actual-shaped arithmetic."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'candidates/qwen2_transposed_dense'
spec = importlib.util.spec_from_file_location('dataflow_test', SOURCE/'fullgraph_dataflow.py')
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)


def save(path, value):
    path.write_text(json.dumps(value))


def line(marker, values):
    return marker + ' ' + ' '.join(f'{k}={v}' for k, v in values.items())


def full_log(tokens=16):
    """Independent official-shape log fixture; no arithmetic or work files."""
    lines = ['SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10 arch=x86 ftz=0 daz=0']
    for index, n in enumerate((1536, 256, 256, 1536)):
        if index == 3:
            lines.append(line('RESIDENT_ATTENTION', F.D.expected_attention(tokens, F.R.make_layout())))
        lines.append(line('TRANSPOSED_CASE', dict(m=tokens, k=1536, n=n, rmw=1, a_chunk=2560,
            a_values=tokens*1536, w_values=1536*n, issues=48*n, swapped_fmas=48*n*4096,
            captures=n//32, a_read_words=tokens*1536, a_write_words=tokens*1536,
            refill_phases=tokens*288, context_peak=5, meta_peak=1, fifo_peak=1, final_peak=1)))
    lines.append(line('DATAFLOW_FFN', dict(m=tokens, k=1536, n=8960, input_values=tokens*1536,
        weight_values=27525120, act_values=tokens*8960, tile_read_bytes=tokens*107520,
        tile_write_bytes=tokens*107520, gate_up_arithmetic_ddr_reads=0, a_reserved_bytes=638976, b_bytes=81920)))
    lines.append(line('DATAFLOW_DOWN', dict(m=tokens, k=8960, n=1536, chunk=2560,
        a_values=tokens*8960, w_values=13762560, prefix_read_bytes=2359296, prefix_write_bytes=2359296,
        prefix_acks=144, final_acks=48, issues=430080, published=1)))
    for phase, name in enumerate(F.R.STAGE_NAMES):
        width = 8960 if name in ('gate','up','act') else 256 if name in ('kr','v','k') else 1536
        lines.append(line('SOFTWARE_RECIPE_STAGE', dict(phase=phase, name=name, values=tokens*width)))
    lines.append(line('SOFTWARE_RECIPE_COMPLETE', dict(tokens=tokens, stages=15)))
    return '\n'.join(lines) + '\n'


def test_frozen_sources_reproduce_exact_cpp_outside_work_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source, down, full, _ = F.B.generated()
    assert F.R.sha(source.encode()) == '38a3a0169cf584d3aa7f6a6e8ad9766cbd2b150d8568c4ba5f600151dab66d39'
    assert 'gate/up DDR arithmetic access' in source and 'tiledFFN();' in source
    assert 'PREFIX_ALL_CONTEXTS' in down and 'SYNTHETIC_FULLGRAPH_EXACT' in full
    assert source.count(F.D.NUMERIC_ATT.ATTENTION_BODY) == 1
    assert F.B.HISTORICAL_WORK['old_driver_pass_rebound'] is False


@pytest.mark.parametrize('name', list(F.B.INCLUDE_SHA256))
def test_each_frozen_include_tamper_is_rejected(tmp_path, monkeypatch, name):
    for file in F.B.INCLUDE_SHA256:
        shutil.copyfile(SOURCE/'dataflow'/file, tmp_path/file)
    (tmp_path/name).write_bytes((tmp_path/name).read_bytes() + b'\n')
    monkeypatch.setattr(F.B, 'HERE', tmp_path)
    with pytest.raises(ValueError, match='changed evidence'):
        F.B.generated()


def test_summary_is_compact_source_identity_only(monkeypatch):
    def prohibited(*args, **kwargs):
        pytest.fail('summary must not compile or execute C++')
    monkeypatch.setattr(F, 'compile_source', prohibited)
    monkeypatch.setattr(F.R, 'execute', prohibited)
    result = F.summary()
    assert result['status'] == 'SOURCE_IDENTITY_ONLY_NOT_EXECUTED'
    assert result['generated_cpp_sha256'] == F.B.CPP_SHA256
    assert result['modeled_m128_traffic'] == dict(read_bytes=115998720, write_bytes=15728640,
        total_bytes=131727360, transfers_64b=2058240)
    assert all(not Path(path).is_absolute() and not path.startswith('work/') for path in result['source_sha256'])
    assert result['hardware_cycles'] is None and not result['native_accuracy_acceptance']
    assert result['fp32_final_gate'] == 'FAIL_UNCHANGED' and result['numerical_policy'] == 'OPEN_UNCHANGED'
    assert not result['packaged_driver_actual_m16_executed'] and not result['packaged_driver_actual_m128_executed']
    assert not result['historical_work_full_runs_rebound']
    assert 'all_15_stages_bit_exact' not in result


def test_fixed_resource_addresses():
    addresses, resources = F.B.address_checks(), F.B.resources()
    assert addresses['alias_free'] and addresses['ffn_reserved_bytes'] == 638976
    assert addresses['prefix_unique_beats'] == 12288
    assert resources['scratch']['total_bytes'] == 786432
    assert resources['prefix']['ddr_bytes'] == 786432
    assert resources['observers']['arithmetic_read_allowed'] is False


@pytest.mark.parametrize('tokens', [16,128])
def test_exact_full_run_log_recipe(tokens):
    counters = F.parse_run_log(full_log(tokens), tokens)
    assert counters['down']['prefix_acks'] == 144
    assert len(counters['dense']) == 4 and counters['ffn']['gate_up_arithmetic_ddr_reads'] == 0


@pytest.mark.parametrize('old,new', [
    ('m=16 k=8960', 'm=128 k=8960'), ('chunk=2560', 'chunk=1280'),
    ('prefix_acks=144', 'prefix_acks=143'), ('published=1', 'published=0'),
    ('a_values=24576', 'a_values=24575'), ('gate_up_arithmetic_ddr_reads=0', 'gate_up_arithmetic_ddr_reads=1'),
    ('phase=0 name=n0 values=24576', 'phase=0 name=n0 values=24575'),
    ('SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15', 'SOFTWARE_RECIPE_COMPLETE tokens=128 stages=15'),
    ('ftz=0', 'ftz=1'), ('prefix_acks=144', 'prefix_acks=144 prefix_acks=144'),
])
def test_log_shape_recipe_completion_and_duplicate_field_guards(old, new):
    with pytest.raises(ValueError):
        F.parse_run_log(full_log().replace(old, new), 16)


def test_owner_and_stage_log_order_rejected():
    original = full_log().splitlines()
    for a,b in [(1,2), (7,8), (8,9)]:
        altered = original[:]
        altered[a],altered[b] = altered[b],altered[a]
        with pytest.raises(ValueError):
            F.parse_run_log('\n'.join(altered),16)


@pytest.fixture
def m16_receipt(tmp_path):
    out = tmp_path/'prepared'
    directory = out/'m16'
    directory.mkdir(parents=True)
    (out/'PREPARED.json').write_text('independent preparation identity')
    stages = []
    for row in F.stage_rows(F.R.SHAPE, 16):
        file = f"phase_{row['phase']}_{row['name']}_recipe.f32le"
        path = directory/file
        path.write_bytes(bytes(row['values']*4))
        stages.append(dict(phase=row['phase'], name=row['name'], path=file,
                           width=row['values']//16, sha256=F.C.sha(path)))
    (directory/'run.log').write_text(full_log())
    baseline = dict(stages=copy.deepcopy(stages), result_sha256='independent-baseline-receipt')
    prepared = dict(baselines={'16':baseline}, source_sha256=F.source_pins(),
                    generated_sha256={'software_recipe':'prepared-binary'})
    result = dict(schema=F.SCHEMA, status='MODEL_ONLY_DIAGNOSTIC_NOT_ACCEPTED', **F.LIMITS,
        tokens=16, shape=dict(F.R.SHAPE,tokens=16), completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',
        all_15_stages_bit_exact=True, prepared_sha256=F.C.sha(out/'PREPARED.json'), arena_sha256=F.FC.ARENA_SHA,
        generated_cpp_sha256=F.B.CPP_SHA256, source_sha256=prepared['source_sha256'], binary_sha256='prepared-binary',
        baseline_result_sha256='independent-baseline-receipt', stages=stages,
        run_log_sha256=F.C.sha(directory/'run.log'), counters=F.parse_run_log(full_log(),16))
    save(directory/'RESULT.json',result)
    return out,prepared,result


def test_m16_receipt_independently_bound(m16_receipt):
    out,prepared,_ = m16_receipt
    F.verify_m16(out,prepared)
    prepared['baselines']['16']['stages'][0]['sha256'] = 'f'*64
    with pytest.raises(ValueError, match='frozen baseline'):
        F.verify_m16(out,prepared)


@pytest.mark.parametrize('key,value', [
    ('schema','work-only'), ('prepared_sha256','other preparation'), ('tokens',128),
    ('arena_sha256','wrong input'), ('binary_sha256','different binary'),
    ('source_sha256',{}), ('generated_cpp_sha256','different recipe'),
    ('baseline_result_sha256','other baseline'), ('all_15_stages_bit_exact',False),
    ('all_15_stages_bit_exact','yes'), ('status','OLD_WHOLE_CASE_PASS'),
    ('completion_status','INCOMPLETE'), ('native_accuracy_acceptance',True),
])
def test_m16_receipt_identity_guards(m16_receipt,key,value):
    out,prepared,result = m16_receipt
    result[key] = value
    save(out/'m16/RESULT.json',result)
    with pytest.raises(ValueError):
        F.verify_m16(out,prepared)


def test_m16_log_cannot_be_rebound_by_updating_hash(m16_receipt):
    out,prepared,result = m16_receipt
    log = out/'m16/run.log'
    log.write_text(log.read_text().replace('published=1','published=0'))
    result['run_log_sha256'] = F.C.sha(log)
    save(out/'m16/RESULT.json',result)
    with pytest.raises(ValueError,match='recipe/counters'):
        F.verify_m16(out,prepared)


def test_baseline_generated_recipe_checked_independently(tmp_path,monkeypatch):
    source,_,_,identity = F.B.generated()
    generated = tmp_path/'generated'
    generated.mkdir()
    # Even if a receipt is self-consistent, this candidate is not the baseline.
    (generated/'software_recipe.cpp').write_text(source)
    monkeypatch.setattr(F.FC,'verify_baselines',lambda *a: {'self_consistent':'insufficient'})
    with pytest.raises(ValueError,match='changed evidence'):
        F.verify_baselines(tmp_path,identity)


@pytest.mark.parametrize('kind',['shape','arena','recipe'])
def test_shared_baseline_guards_reject_before_stage_reads(tmp_path,kind):
    _,_,_,identity = F.B.generated()
    old = dict(identity['fullchain_identity']['base_recipe_identity'])
    old.update(resident_attention_body_sha256=identity['unchanged_attention_body_sha256'],
               rectangular_attention=True,compile_command=['g++',*F.R.FLAGS])
    receipt = dict(shape=dict(F.R.SHAPE,tokens=16),readonly_sha256=F.FC.ARENA_SHA,
                   completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',source_identity=old)
    if kind == 'shape': receipt['shape']['hidden'] = 32
    if kind == 'arena': receipt['readonly_sha256'] = 'wrong'
    if kind == 'recipe': old['source_pass_cpp_sha256'] = 'wrong'
    (tmp_path/'m16').mkdir()
    save(tmp_path/'m16/RESULT.json',receipt)
    with pytest.raises(ValueError): F.verify_baselines(tmp_path,identity)


@pytest.mark.parametrize('kind',['shape','recipe','source','scope'])
def test_prepared_manifest_guards(tmp_path,kind):
    _,_,_,identity = F.B.generated()
    p = dict(schema=F.SCHEMA,status='PREPARED_NOT_EXECUTED',**F.LIMITS,
        parameters=copy.deepcopy(F.PARAMETERS),strict_flags=F.R.FLAGS,
        source_sha256=F.source_pins(),source_identity=F.stable_identity(identity))
    if kind == 'shape': p['parameters']['shape']['hidden'] = 32
    if kind == 'recipe': p['strict_flags'] = ['-ffast-math']
    if kind == 'source': p['source_sha256'] = {}
    if kind == 'scope': p['historical_work_full_runs_rebound'] = True
    save(tmp_path/'PREPARED.json',p)
    with pytest.raises(ValueError): F.validate(tmp_path)


def test_prepare_bad_arena_makes_no_output(tmp_path):
    arena = tmp_path/'raw'
    arena.write_bytes(b'invalid')
    with pytest.raises(ValueError,match='arena size'):
        F.prepare(tmp_path/'new',tmp_path/'baseline',arena,tmp_path/'small.json')
    assert not (tmp_path/'new').exists()


def test_m128_requires_m16_before_launch_or_output(tmp_path,monkeypatch):
    def prohibited(*args,**kwargs): pytest.fail('actual-shaped arithmetic is forbidden in packaging tests')
    monkeypatch.setattr(F.R,'execute',prohibited)
    monkeypatch.setattr(F,'validate',lambda out: {'baselines':{'16':{'stages':[]}}})
    (tmp_path/'PREPARED.json').write_text('prepared')
    with pytest.raises(FileNotFoundError): F.execute(tmp_path,128)
    assert not (tmp_path/'m128').exists()


def test_existing_run_refuses_before_validation(tmp_path,monkeypatch):
    (tmp_path/'m16').mkdir()
    evidence = tmp_path/'m16/preserved'
    evidence.write_bytes(b'exact existing evidence')
    monkeypatch.setattr(F,'validate',lambda *a: pytest.fail('must refuse existing evidence first'))
    with pytest.raises(ValueError,match='duplicate'): F.execute(tmp_path,16)
    assert evidence.read_bytes() == b'exact existing evidence'


@pytest.mark.parametrize('name',['software_recipe.cpp','software_recipe','block_layout.h','layout.json','software_recipe.build.log'])
def test_artifact_changed_during_stub_execution_cannot_publish(tmp_path,monkeypatch,name):
    generated = tmp_path/'generated'
    generated.mkdir()
    files = ['software_recipe.cpp','software_recipe','block_layout.h','layout.json','software_recipe.build.log']
    for file in files: (generated/file).write_text(file)
    p = dict(generated_sha256={file:F.C.sha(generated/file) for file in files},
             source_sha256=F.source_pins(),single_cpu=min(os.sched_getaffinity(0)),
             arena={'path':str(tmp_path/'arena'),'sha256':F.FC.ARENA_SHA,'bytes':188043264})
    (tmp_path/'PREPARED.json').write_text('stub control-flow test; no arithmetic')
    monkeypatch.setattr(F,'validate',lambda *args:p)
    monkeypatch.setattr(F,'verify_arena',lambda *args:p['arena'])
    def stub_execute(generated,arena,tokens,output,**kwargs):
        (output/'run.log').write_text(full_log(tokens))
        (generated/name).write_text('changed during the stub execution')
        return 0.0
    monkeypatch.setattr(F.R,'execute',stub_execute)
    with pytest.raises(ValueError,match='changed evidence'): F.execute(tmp_path,16)
    assert not (tmp_path/'m16/RESULT.json').exists()
    assert json.loads((tmp_path/'m16/FAILED.json').read_text())['status'] == 'FAILED_NO_RETRY'
    for file in files:
        if file != name: assert F.C.sha(generated/file) == p['generated_sha256'][file]


def test_output_and_optimized_python_guards(tmp_path):
    for output in (SOURCE, SOURCE/'dataflow/result'):
        with pytest.raises(ValueError,match='outside candidate'): F.C.output_directory(output)
    with pytest.raises(ValueError,match='overwrite'): F.small(tmp_path,tiny=True)
    out = tmp_path/'optimized'
    result = subprocess.run([sys.executable,'-O',str(SOURCE/'fullgraph_dataflow.py'),'summary','--out',str(out)],
                            text=True,capture_output=True,timeout=30)
    assert result.returncode != 0 and 'optimized Python' in result.stderr
    assert not out.exists()


@pytest.fixture(scope='module')
def tiny_cpp(tmp_path_factory):
    if shutil.which('g++') is None:
        pytest.skip('ordinary C++ compiler unavailable')
    out = tmp_path_factory.mktemp('dataflow')/'tiny'
    before = {str(p.relative_to(SOURCE)):F.C.sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    result = F.small(out,tiny=True)
    after = {str(p.relative_to(SOURCE)):F.C.sha(p) for p in SOURCE.rglob('*') if p.is_file()}
    assert before == after
    return out,result


def test_one_tiny_actual_cpp_fullgraph(tiny_cpp):
    out,result = tiny_cpp
    assert result['numeric'] == dict(coverage='packaging_tiny_only',fullgraph_runs=1,fullgraph_stages=15,
        fullgraph_checked_values=16896,down_cases=0,down_checked_values=0,bit_mismatches=0,gate_up_guard_rejections=6)
    assert F.C.sha(out/'frozen_fullgraph.cpp') == F.B.CPP_SHA256
    assert result['strict_flags'] == ['-O2','-std=c++17','-ffp-contract=off','-fno-fast-math']
    assert len(list(out.glob('synthetic_m16_phase_*.f32le'))) == 15
    assert 'prefix_read_bytes=49152' in (out/'small_fullgraph.run.log').read_text()
    assert result['native_accuracy_acceptance'] is False


def test_tiny_receipt_never_qualifies_actual_prepare(tiny_cpp):
    out,_ = tiny_cpp
    with pytest.raises(ValueError,match='tiny/historical receipt'):
        F.verify_small(out/'SUMMARY.json')


@pytest.mark.parametrize('kind',['source','shape','flags','scope','incomplete'])
def test_tiny_receipt_cannot_be_relabelled_as_full(tiny_cpp,tmp_path,kind):
    _, original = tiny_cpp
    receipt = copy.deepcopy(original)
    receipt['tiny'] = False
    if kind == 'source': receipt['source_sha256'] = {}
    if kind == 'shape': receipt['synthetic_shape']['hidden'] = 1536
    if kind == 'flags': receipt['strict_flags'] = ['-ffast-math']
    if kind == 'scope': receipt['native_accuracy_acceptance'] = True
    save(tmp_path/'SUMMARY.json',receipt)
    with pytest.raises(ValueError): F.verify_small(tmp_path/'SUMMARY.json')


def test_small_log_stage_order_and_receipt_guards(tiny_cpp):
    out,_ = tiny_cpp
    original = (out/'small_fullgraph.run.log').read_text()
    for old,new in [('tokens=16 phase=0','tokens=16 phase=1'),
                    ('stages=15 values=16896','stages=15 values=1'),
                    ('eliminated_ddr_guard_rejections=6','eliminated_ddr_guard_rejections=5')]:
        with pytest.raises(ValueError):
            F.parse_small_logs({'small_fullgraph':original.replace(old,new)},True)


def bounded_log_fixture():
    """Parser-only receipt fixture, not an execution receipt."""
    env = 'SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10 ftz=0 daz=0'
    full = [env]
    for tokens in (16,32,128):
        full += [line('SYNTHETIC_STAGE_EXACT',row) for row in F.stage_rows(F.SMALL_SHAPE,tokens,synthetic=True)]
        full.append(line('SYNTHETIC_FULLGRAPH_EXACT',dict(tokens=tokens,stages=15,values=tokens*1056,
            input_fnv64=0,eliminated_ddr_guard_rejections=6,gate_up_external_bytes=0)))
    full.append('DATAFLOW_FULLGRAPH_SMALL_PASS runs=3 stages=45 official_shape=0 official_forward=0')
    down = [env,
        'PREFIX_LAYOUT exact_addresses=8192 external_mutation_observed=1 seed_payload_bytes=64',
        'PROTOCOL_FAULTS rejected=42 sticky_poison=1 job_generation=1 rtl_fault_drain=0',
        'PREFIX_ALL_CONTEXTS contexts=48 beat_addresses=12288 values=196608 high_bitmap_bits=16 missing_last_ack_rejected=1',
        'FFN_CONSUMER physical_mutation_observed=1 physical_values=61440 retained_a_halfwords=196608',
        'FFN_LIFECYCLE_FAULTS rejected=10 sticky_poison=1',
        'DOMAIN_ERRORS rejected=9 unpublished=1 per_step_hardware_flags=0']
    recipe = [(16,16,16,16,0,0),(32,32,32,16,0,1),(16,272,160,80,0,1),
              (32,272,192,80,0,1),(128,272,192,80,0,1),(16,8960,32,2560,0,0)]
    recipe += [(16 if p&1 else 32,64,48,16,p,1) for p in range(1,5)]
    for m,k,n,chunk,pattern,bias in recipe:
        down.append(line('DOWN_BIT_EXACT',dict(m=m,k=k,n=n,chunk=chunk,pattern=pattern,bias=bias,values=m*n)))
    down.append('DATAFLOW_SMALL_PASS cases=10 official_forward=0 official_m16=0 official_m128=0')
    return {'small_fullgraph':'\n'.join(full),'small_down':'\n'.join(down)}


@pytest.mark.parametrize('marker',['PREFIX_LAYOUT','PROTOCOL_FAULTS','PREFIX_ALL_CONTEXTS',
                                 'FFN_CONSUMER','FFN_LIFECYCLE_FAULTS','DOMAIN_ERRORS'])
def test_small_address_consumer_fault_records_mandatory(marker):
    logs = bounded_log_fixture()
    assert F.parse_small_logs(logs,False)['fullgraph_checked_values'] == 185856
    logs['small_down'] = '\n'.join(row for row in logs['small_down'].splitlines() if not row.startswith(marker+' '))
    with pytest.raises(ValueError,match='protocol/address/consumer evidence'):
        F.parse_small_logs(logs,False)
