# SPDX-License-Identifier: Apache-2.0
"""Tiny synthetic tests only; these do not run weights or any actual model gate."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('resident_numeric', ROOT/'scripts/qwen2_dense_residency_numeric.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
R = m.R


def test_only_dense_body_changes_and_fixed_physical_storage():
    text, identity = m.resident_source(ROOT)
    helpers, maths, _ = R.extract_sources(ROOT)
    dense = R.section(maths, '  void dense(', '  void rope(')
    resident = R.section(text, '  void dense(', '  void rope(')
    original = '// Ordinary C++ software numerical model; not a hardware simulator.\n'
    original += helpers+R.HOST_PROBES+R.DRIVER+maths+R.MAIN
    assert text.replace(resident, dense) == original
    assert resident[:resident.index('{')+1] == dense[:dense.index('{')+1]
    assert identity['base_runner_sha256'] == m.BASE_SHA256
    assert identity['section_sha256']['math'] == '4507a74bffa481584038713e2bc7de4c675d291176fc22a5c4c2a10fba732ee8'
    assert 'uint16_t ac[16][1024][16], b[16][512][16]' in resident
    assert 'accumulator[5][16][256], resultFIFO[2][16][256], finalValue[16][256]' in resident
    assert 'std::vector' not in resident
    assert not any(symbol in text for symbol in ('verilated', 'BlockDut', 'VQwen', 'd.eval'))


def test_actual_counters_match_reviewed_resource_plan():
    spec = importlib.util.spec_from_file_location('resident_resource_plan', ROOT/'scripts/qwen2_prefill_resource_schedule.py')
    schedule = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schedule)
    for _, k, n in schedule.BOUND.MATRICES:
        plan = schedule.resident_dense_plan(128, k, n)
        expected = m.expected_dense(128, k, n)
        assert expected['external_a_fp32_bytes'] == plan['external_a_fp32_read_bytes']
        assert expected['logical_weight_bf16_bytes'] == plan['external_weight_bf16_read_bytes']
        assert expected['external_d_fp32_bytes'] == plan['external_d_fp32_write_bytes']
        assert expected['prefix_restore_fp32_bytes'] == plan['partial_restore_bytes']
        assert expected['prefix_store_fp32_bytes'] == plan['partial_store_bytes']
        assert expected['wide_issues'] == plan['matrix_wide_issues']
        assert expected['useful_macs'] == plan['useful_macs']
        assert expected['c_base_word'] == plan['a_operand_bf16_bytes']//512
        assert expected['c_slots'] == plan['n_tiles_retained']


def bf16(values):
    array = np.asarray(values, dtype='<f4').copy()
    words = array.view('<u4')
    words[...] = (words+np.uint32(0x7fff)+((words>>16)&1)) & np.uint32(0xffff0000)
    return array


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    if shutil.which('g++') is None:
        pytest.skip('ordinary C++ compiler unavailable')
    directory = tmp_path_factory.mktemp('resident_numeric')
    # Small H, but F crosses six KC boundaries; MAX_TOKENS stays 128.
    shape = dict(hidden=32, ffn=1792, heads=1, kv_heads=1, head_dim=32, max_tokens=128)
    layout, provenance = m.generate_and_compile(ROOT, directory/'resident', shape)
    baseline, _ = R.generate_and_compile(ROOT, directory/'baseline', shape)
    assert layout == baseline
    assert provenance['compile_command'][1:5] == R.FLAGS
    arena = np.zeros(layout['writable_start']//4, dtype='<f4')
    regions = {region['name']: region for region in layout['regions']}

    def put(name, values):
        values = np.asarray(values, dtype='<f4').reshape(-1)
        start = regions[name]['offset']//4
        assert len(values) <= regions[name]['words']
        arena[start:start+len(values)] = values

    for number, name in enumerate(R.WEIGHTS):
        words = regions[name]['words']
        put(name, bf16(((np.arange(words)*(2*number+3))%29-14)/1024))
    put('gamma0', bf16(1+np.arange(32)/128))
    put('gamma1', bf16(1-np.arange(32)/256))
    for name in ('bq','bk','bv'):
        put(name, (np.arange(32)%7-3)/64)
    put('x', ((np.arange(128*32)*7)%31-15)/16)
    angles = np.arange(128)[:,None]/(1000000.0**(np.arange(16)[None,:]/16))
    put('cos', np.cos(angles))
    put('sin', np.sin(angles))
    arena.tofile(directory/'arena')
    return directory, layout, provenance


def test_full_block_small_then_m16_bit_exact_and_reuses_same_binary(compiled):
    directory, layout, provenance = compiled
    for tokens in (2, 16):
        before = R.file_sha(directory/'resident/software_recipe')
        result = m.execute(ROOT, directory/'resident', directory/'arena', tokens, directory/f'resident_m{tokens}',
                           expected_arena_sha256=R.file_sha(directory/'arena'), timeout_seconds=30)
        baseline = directory/f'baseline_m{tokens}'
        baseline.mkdir()
        R.execute(directory/'baseline', directory/'arena', tokens, baseline, timeout_seconds=30)
        for phase, name in enumerate(R.STAGE_NAMES):
            path = f'phase_{phase}_{name}_recipe.f32le'
            assert (directory/f'resident_m{tokens}'/path).read_bytes() == (baseline/path).read_bytes(), name
        assert R.file_sha(directory/'resident/software_recipe') == before == provenance['binary_sha256']
        assert result['status'] == m.STATUS
        assert result['scope']['consumes_own_previous_stages']
        assert result['scope']['checkpoint_accuracy_signoff'] is False
        assert result['scope']['hardware_acceptance'] is False
        assert result['dense'][-1]['prefix_restore_fp32_bytes'] > 0
        assert result['dense'][-1]['c_slots'] == 3
    assert layout['max_tokens'] == 128


def test_reuse_and_receipts_reject_changed_artifacts(compiled, tmp_path):
    directory, _, _ = compiled
    copied = tmp_path/'copied'
    shutil.copytree(directory/'resident', copied)
    binary = copied/'software_recipe'
    binary.write_bytes(binary.read_bytes()+b'changed')
    with pytest.raises(ValueError, match='binary changed'):
        m.validate_generated(ROOT, copied)
    with pytest.raises(ValueError, match='sealed readonly arena SHA mismatch'):
        m.execute(ROOT, directory/'resident', directory/'arena', 2, tmp_path/'bad', expected_arena_sha256='wrong')
    with pytest.raises(ValueError, match='timeout'):
        m.execute(ROOT, directory/'resident', directory/'arena', 2, tmp_path/'bad',
                  expected_arena_sha256=R.file_sha(directory/'arena'), timeout_seconds=601)
    with pytest.raises(ValueError, match='existing generated'):
        m.generate_and_compile(ROOT, directory/'resident')


@pytest.mark.skipif(shutil.which('g++') is None, reason='ordinary C++ compiler unavailable')
def test_direct_dense_cohorts_three_slots_restarts_bias_and_rne(tmp_path):
    """Use the original extracted Dense as comparator, not a new oracle.

    Full M128 bank geometry on tiny synthetic tensors exercises all eight M
    tiles, three live C slots, a second N supergroup, seven K chunks, and a
    partial N tile. Cancellation distinguishes prefix continuation from K-block
    sums, and input tie bits exercise the unchanged BF16 RNE rule.
    """
    source, _ = m.resident_source(ROOT)
    _, maths, _ = R.extract_sources(ROOT)
    source = source[:source.index('int main(int argc,char** argv)')]
    source += R.DRIVER.replace('SoftwareRecipe', 'CanonicalRecipe')+maths+'\n};\n'
    source += r'''
int main(){try{
  verifyFloatEnvironment();
  auto run=[](unsigned tokens,int K,int N,bool biased){
    SoftwareRecipe actual(tokens);CanonicalRecipe expected(tokens);
    const uint64_t a=0,w=uint64_t(tokens)*K*4,bias=w+uint64_t(K)*N*4,out=bias+N*4;
    actual.reference.assign(out/4+size_t(tokens)*N,fp(0x7fc00001u));
    for(unsigned row=0;row<tokens;row++)for(int k=0;k<K;k++){
      float v=row==0?1.0f:float(int((row*19+k*7)%17)-8)/8;
      if(row==1 && k%4==0)v=fp(k%8?0x3f808000u:0x3f818000u);
      actual.put(a,size_t(row)*K+k,v);
    }
    for(int k=0;k<K;k++)for(int n=0;n<N;n++){
      float v=float(int((k*31+n*17)%29)-14)/128;
      if(n==0)v=k==0?16777216.0f:k==K-1?-16777216.0f:1.0f;
      actual.put(w,size_t(k)*N+n,bf(v));
    }
    for(int n=0;n<N;n++)actual.put(bias,n,float(n%7-3)/64);
    expected.reference=actual.reference;
    actual.dense(a,w,out,K,N,biased?int64_t(bias):-1);
    expected.dense(a,w,out,K,N,biased?int64_t(bias):-1);
    for(size_t i=0;i<size_t(tokens)*N;i++)
      need(bits(actual.get(out,i))==bits(expected.get(out,i)),"synthetic resident Dense differs from v0");
    need(bits(actual.get(out,0))==bits(biased?actual.get(bias,0):0.0f),"prefix cancellation/bias order changed");
    std::cout<<"TINY_DENSE_EXACT tokens="<<tokens<<" k="<<K<<" n="<<N<<std::endl;
  };
  run(3,512,32,true);
  run(16,1536,256,true);
  run(128,1792,800,false);
  SoftwareRecipe bad(1);bad.reference.assign(16*16+32,0.0f);
  bad.reference[16]=fp(0x3f800001u);
  bool rejected=false;
  try{bad.dense(0,16*4,(16+256)*4,16,16);}catch(const std::exception& e){
    rejected=std::string(e.what()).find("weight not exact BF16")!=std::string::npos;
  }
  need(rejected,"non-BF16 fixture weight accepted");
  std::cout<<"TINY_DENSE_ALL_EXACT"<<std::endl;
  return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
'''
    layout = R.make_layout(dict(hidden=32, ffn=32, heads=1, kv_heads=1, head_dim=32, max_tokens=128))
    (tmp_path/'block_layout.h').write_text(R.header(layout))
    (tmp_path/'tiny.cpp').write_text(source)
    command = [shutil.which('g++'), *R.FLAGS, str(tmp_path/'tiny.cpp'), '-o', str(tmp_path/'tiny')]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    run = subprocess.run([str(tmp_path/'tiny')], check=True, capture_output=True, text=True, timeout=30)
    assert 'TINY_DENSE_ALL_EXACT' in run.stdout
    line = next(line for line in run.stdout.splitlines() if line.startswith('RESIDENT_DENSE tokens=128'))
    for fragment in ('contexts_peak=5', 'fifo_peak=1', 'c_slots=3', 'c_base_word=128',
                     'scratch_bytes=786432', 'seed_contexts=192', 'snapshot_contexts=192'):
        assert fragment in line


def test_actual_m128_prerequisite_is_checked_before_running(monkeypatch, tmp_path):
    # No actual compilation, arena, or model weights are needed for this guard.
    monkeypatch.setattr(m, 'validate_generated', lambda *_: (R.make_layout(), {}))
    with pytest.raises(ValueError, match='completed resident M16 prerequisite'):
        m.execute(ROOT, tmp_path/'generated', tmp_path/'no_arena', 128, tmp_path/'out',
                  expected_arena_sha256='unused')


def test_synthetic_m16_cannot_unlock_actual_m128(compiled, tmp_path):
    directory, _, provenance = compiled
    # The prerequisite verifier deliberately only accepts the actual max128
    # shape; synthetic receipts cannot unlock an actual M128 run.
    receipt = tmp_path/'m16'
    receipt.mkdir()
    data = dict(status=m.STATUS, shape=dict(hidden=32, ffn=1792, heads=1, kv_heads=1,
        head_dim=32, max_tokens=128, tokens=16), completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE')
    (receipt/'RESULT.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='completed resident M16 prerequisite'):
        m._verify_m16(receipt, directory/'resident', provenance, 'unused')


def test_m16_receipt_requires_same_binary_arena_and_intact_outputs(tmp_path):
    # Zero-filled files exercise receipt validation only. No actual forward,
    # checkpoint acquisition, or acceptance claim is made by this fixture.
    receipt = tmp_path/'m16'
    receipt.mkdir()
    layout = R.make_layout()
    provenance = {'binary_sha256': 'fixture-binary', 'generated_header_sha256': 'fixture-layout'}
    stages = []
    for phase, name in enumerate(R.STAGE_NAMES):
        width = next(r['words']//128 for r in layout['regions'] if r['name'] == name)
        path = receipt/f'phase_{phase}_{name}_recipe.f32le'
        path.write_bytes(bytes(16*width*4))
        stages.append(dict(phase=phase, name=name, width=width, path=path.name, sha256=R.file_sha(path)))
    dimensions = ((1536,1536),(1536,256),(1536,256),(1536,1536),(1536,8960),(1536,8960),(8960,1536))
    log = 'SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10\n'
    log += ''.join('RESIDENT_DENSE '+' '.join(f'{key}={value}' for key,value in m.expected_dense(16,k,n).items())+'\n'
                   for k,n in dimensions)
    log += ''.join(f'SOFTWARE_RECIPE_STAGE phase={phase} name={name}\n' for phase,name in enumerate(R.STAGE_NAMES))
    log += 'SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15\n'
    (receipt/'run.log').write_text(log)
    data = dict(status=m.STATUS, shape=dict(R.SHAPE, tokens=16),
        completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE', source_identity=provenance,
        generated_directory=str(tmp_path/'generated'), readonly_sha256='fixture-arena',
        run_log_sha256=R.file_sha(receipt/'run.log'), stages=stages)
    (receipt/'RESULT.json').write_text(json.dumps(data))
    assert m._verify_m16(receipt, tmp_path/'generated', provenance, 'fixture-arena')['status'] == m.STATUS
    with pytest.raises(ValueError, match='same generated binary/layout'):
        m._verify_m16(receipt, tmp_path/'generated', {'binary_sha256': 'changed'}, 'fixture-arena')
    with pytest.raises(ValueError, match='same sealed arena'):
        m._verify_m16(receipt, tmp_path/'generated', provenance, 'changed')
    data['stages'][0]['width'] = 1
    (receipt/'RESULT.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='stage identity changed'):
        m._verify_m16(receipt, tmp_path/'generated', provenance, 'fixture-arena')
    data['stages'][0]['width'] = 1536
    (receipt/'RESULT.json').write_text(json.dumps(data))
    path = receipt/stages[-1]['path']
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='stage changed'):
        m._verify_m16(receipt, tmp_path/'generated', provenance, 'fixture-arena')
