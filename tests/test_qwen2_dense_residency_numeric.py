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


def test_attention_opt_in_keeps_frozen_driver_and_actual_event_accounting():
    text, identity = m.resident_source(ROOT, rectangular_attention=True)
    helpers, maths, _ = m.frozen_sources(ROOT)
    for begin, end in (('  void dense(', '  void rope('),
                       ('  void attention(', '  void computeReference(')):
        text = text.replace(R.section(text, begin, end), R.section(maths, begin, end))
    text = text.replace(m.NUMERIC_ATT.CPP_SUPPORT, '')
    assert text == '// Ordinary C++ software numerical model; not a hardware simulator.\n'+helpers+R.HOST_PROBES+R.DRIVER+maths+R.MAIN
    assert identity['source_pass_reference_commit'] == '299949a03876fb561010afb6e1d83097db0ca593'
    assert identity['attention_event_sha256'] == m.ATTENTION_EVENT_SHA256
    assert 'std::vector' not in m.NUMERIC_ATT.ATTENTION_BODY+m.NUMERIC_ATT.CPP_SUPPORT
    expected = m.expected_attention(128, R.make_layout())
    events = list(m.ATT.iter_events(128, 5))
    issue = [e for e in events if e['event'] == 'matrix_issue']
    gather = [e for e in events if e['event'] == 'operand_gather']
    assert expected['wide_issues'] == len(issue)
    assert expected['useful_macs'] == sum(e['useful_macs'] for e in issue)
    assert expected['executed_macs'] == sum(e['executed_macs'] for e in issue)
    assert expected['event_gather_bank_read_bytes'] == 32*sum(
        sum(e.get(key, 0) for key in ('q_bank_word_reads', 'k_bank_word_reads',
            'probability_bank_word_reads', 'v_bank_word_reads')) for e in gather)
    assert expected['groups'] == sum(e['event'] == 'group_start' for e in events)
    assert expected['result_captures'] == sum(e['event'] == 'matrix_return' and e['emit'] for e in events)
    assert expected['partial_stores'] == sum(e['event'] == 'partial_store' for e in events)
    assert expected['pv_row_captures'] == sum(len(e['rows']) for e in events if e['event'] == 'capture_final_row')
    assert expected['scalar_add_requests'] == expected['ordered_stripe_adds']+2*12*128*129//2
    layout = m.ATT.scratch_layout(128, 5)
    assert layout['used_a_bytes'] == 168*512 <= 524288
    assert layout['used_b_bytes'] == 160*512 <= 262144
    addresses = set()
    for obj in layout['objects']:
        for row in range(obj['rows']):
            for col in range(obj['columns']):
                address = m.ATT.scratch_address(layout, obj['name'], row, col)
                assert address not in addresses
                addresses.add(address)
    assert m.ATT.scratch_address(layout, 'partial_or_pv_capture', 0, 0) == ('B', 0, 0, 0)


@pytest.fixture(scope='module')
def compiled_attention(tmp_path_factory):
    if shutil.which('g++') is None:
        pytest.skip('ordinary C++ compiler unavailable')
    directory = tmp_path_factory.mktemp('rectangular_numeric')
    shape = dict(hidden=128, ffn=64, heads=4, kv_heads=2, head_dim=32, max_tokens=128)
    layout, provenance = m.generate_and_compile(ROOT, directory/'mapped', shape, rectangular_attention=True)
    # Compile the exact source pinned at SOURCE_PASS_COMMIT, not a redefined oracle.
    helpers, maths, _ = m.frozen_sources(ROOT)
    baseline = directory/'baseline'
    baseline.mkdir()
    (baseline/'software_recipe.cpp').write_text(helpers+R.HOST_PROBES+R.DRIVER+maths+R.MAIN)
    (baseline/'block_layout.h').write_text(R.header(layout))
    subprocess.run([shutil.which('g++'), *R.FLAGS, str(baseline/'software_recipe.cpp'), '-o', str(baseline/'software_recipe')],
                   check=True, capture_output=True, text=True, timeout=120)
    arena = np.zeros(layout['writable_start']//4, dtype='<f4')
    for region in layout['regions']:
        if region['offset'] >= layout['writable_start']:
            continue
        name, words = region['name'], region['words']
        i = np.arange(words)
        values = bf16(((i*7+len(name)*3)%29-14)/512)
        if name.startswith('gamma'):
            values = bf16(1+(i%7)/128)
        elif name == 'x':
            values = ((i*13)%31-15)/16
        elif name == 'cos':
            values = np.cos(i/37)
        elif name == 'sin':
            values = np.sin(i/37)
        start = region['offset']//4
        arena[start:start+words] = values
    arena.tofile(directory/'arena')
    return directory, layout, provenance


def test_rectangular_full_15_stages_grouped_heads_and_qtile_boundary(compiled_attention):
    directory, layout, provenance = compiled_attention
    for tokens in (3, 17):
        out, baseline = directory/f'mapped_m{tokens}', directory/f'baseline_m{tokens}'
        result = m.execute(ROOT, directory/'mapped', directory/'arena', tokens, out,
            expected_arena_sha256=R.file_sha(directory/'arena'), timeout_seconds=30)
        baseline.mkdir()
        R.execute(directory/'baseline', directory/'arena', tokens, baseline, timeout_seconds=30)
        for phase, name in enumerate(R.STAGE_NAMES):
            path = f'phase_{phase}_{name}_recipe.f32le'
            assert (out/path).read_bytes() == (baseline/path).read_bytes(), name
        assert result['attention'] == [m.expected_attention(tokens, layout)]
        assert result['source_identity']['binary_sha256'] == provenance['binary_sha256']
        assert result['scope']['rectangular_attention_numerical_address_model']
        assert not result['scope']['attention_row_final_capture_route_implemented']
        assert not result['scope']['attention_scratch_gather_route_implemented']
        assert not result['scope']['hardware_acceptance']
        assert result['source_identity']['source_pass_reference_commit'] == m.SOURCE_PASS_COMMIT


@pytest.mark.skipif(shutil.which('g++') is None, reason='ordinary C++ compiler unavailable')
@pytest.mark.parametrize('heads,kvheads,hd', [(4, 2, 32), (12, 2, 128)])
def test_direct_rectangular_attention_bitexact_masks_stripes_and_rejections(tmp_path, heads, kvheads, hd):
    source, _ = m.resident_source(ROOT, rectangular_attention=True)
    _, maths, _ = m.frozen_sources(ROOT)
    source = source[:source.index('int main(int argc,char** argv)')]
    source += R.DRIVER.replace('SoftwareRecipe', 'CanonicalRecipe')+maths+'\n};\n'
    source += r'''
int main(){try{
  verifyFloatEnvironment();
  auto run=[](unsigned tokens,bool underflow){
    SoftwareRecipe actual(tokens);CanonicalRecipe expected(tokens);
    for(unsigned t=0;t<tokens;t++){
      for(int h=0;h<HEADS;h++)for(int j=0;j<HD;j++){
        float q=float(int((t*13+h*7+j*3)%19)-9)/8;
        if(t<=1 && h==0)q=1.0f;
        if(underflow)q=1.0f;
        actual.put(OFF_Q,size_t(t)*H+h*HD+j,q);
      }
      for(int kh=0;kh<KVHEADS;kh++)for(int j=0;j<HD;j++){
        float k=float(int((t*11+kh*23+j*7)%23)-11)/8;
        float v=float(int((t*5+kh*31+j*11)%29)-14)/16;
        // Across j=0,1,16,17 this yields independent-stripe +2, while
        // a single sequential dot loses the ones around the large terms.
        if(t==0 && kh==0)k=j==0?16777216.0f:j==16?-16777216.0f:(j==1||j==17)?1.0f:0.0f;
        if(t==1 && kh==0)k=0.0f;
        if(kh==0 && t<=1)v=t==0?1.0f:0.0f;
        if(underflow){k=t==0?-6.1875f:0.0f;v=t==0?fp(0x80010000u):t==1?fp(0x80000000u):1.0f;}
        actual.put(OFF_K,size_t(t)*KV+kh*HD+j,k);actual.put(OFF_V,size_t(t)*KV+kh*HD+j,v);
      }
    }
    expected.reference=actual.reference;actual.attention();expected.attention();
    for(size_t i=0;i<size_t(tokens)*H;i++)need(bits(actual.get(OFF_ATT,i))==bits(expected.get(OFF_ATT,i)),
         "rectangular Attention differs from frozen v0");
    if(underflow){
      need(bits(actual.get(OFF_ATT,H))==0x80000000u,"causal final negative zero lost to suffix");
      need(bits(std::fma(0.0f,1.0f,actual.get(OFF_ATT,H)))==0u,"inactive suffix sign counterexample absent");
      std::cout<<"CAUSAL_CAPTURE negative_zero=80000000 inactive_suffix=00000000"<<std::endl;
    }
    std::cout<<"TINY_ATTENTION_EXACT tokens="<<tokens<<" heads="<<HEADS<<" hd="<<HD<<std::endl;
  };
  run(1,false);run(17,false);run(128,false);if(HD==32)run(3,true);
  {
    // A real future key is executed in the first tile's padded columns. Its
    // overflowing row-zero partial must never enter that row's causal score.
    SoftwareRecipe actual(17);CanonicalRecipe expected(17);
    for(int t=0;t<17;t++){
      for(int j=0;j<H;j++)actual.put(OFF_Q,size_t(t)*H+j,t==0?fp(0x7f000000u):0.0f);
      for(int j=0;j<KV;j++){
        actual.put(OFF_K,size_t(t)*KV+j,t==16?2.0f:0.0f);
        actual.put(OFF_V,size_t(t)*KV+j,float((t+j)%7-3)/8);
      }
    }
    expected.reference=actual.reference;actual.attention();expected.attention();
    for(int i=0;i<17*H;i++)need(bits(actual.get(OFF_ATT,i))==bits(expected.get(OFF_ATT,i)),
         "masked future overflow entered a causal result");
    std::cout<<"MASKED_FUTURE_OVERFLOW_DISCARDED"<<std::endl;
  }
  // Direct physical identity, poisoned reads, result drainage, and tags.
  auto p=std::make_unique<RectangularAttentionStorage>(17);
  need(p->object[1].base==8 && p->object[2].base==24 && p->object[3].base==40 && p->object[4].base==43,
       "published Attention layout differs");
  p->put32(5,0,0,fp(0x80000000u));need(bits(p->get32(5,0,0))==0x80000000u,"FP32 SRAM zero sign lost");
  need(p->cell(5,0,0)==&p->b[0][0][0],"B capture/partial alias hidden by private slots");
  auto reject=[](auto action,const std::string& message){bool rejected=false;try{action();}
    catch(const std::exception& e){rejected=std::string(e.what()).find(message)!=std::string::npos;}
    need(rejected,"expected rectangular rejection: "+message);};
  reject([&]{p->get16(0,0,0);},"uninitialized BF16");
  reject([&]{p->get32(3,0,0);},"uninitialized or nonfinite FP32");
  reject([&]{p->cell(3,0,17);},"tensor bounds");
  p->begin(0,0,0,0,0,32);p->start(0);p->issue(0,0,0,true);
  reject([&]{p->issue(0,0,0,true);},"issue before return");
  reject([&]{p->returned(0,1,0,true);},"stale return identity");
  p->returned(0,0,0,true);
  reject([&]{p->end();},"before drain");
  reject([&]{p->begin(0,0,0,16,0,32);},"reuse before result drain");
  p->drain(0,0,0);reject([&]{p->end();},"before drain");p->releaseFinal();
  p->partialStripe[0]=0;reject([&]{p->end();},"before partial reduction");p->partialStripe[0]=-1;p->end();
  for(int input=0;input<3;input++){
    SoftwareRecipe bad(1);
    for(int j=0;j<H;j++)bad.put(OFF_Q,j,0.0f);
    for(int j=0;j<KV;j++){bad.put(OFF_K,j,0.0f);bad.put(OFF_V,j,0.0f);}
    bad.put(input==0?OFF_Q:input==1?OFF_K:OFF_V,0,fp(0x7f800000u));
    reject([&]{bad.attention();},"nonfinite BF16 load");
  }
  SoftwareRecipe overflow(1);
  for(int j=0;j<H;j++)overflow.put(OFF_Q,j,fp(0x7f000000u));
  for(int j=0;j<KV;j++){overflow.put(OFF_K,j,2.0f);overflow.put(OFF_V,j,1.0f);}
  reject([&]{overflow.attention();},"nonfinite causal QK partial");
  SoftwareRecipe invalid(129);reject([&]{invalid.attention();},"shape outside bounded storage");
  std::cout<<"TINY_ATTENTION_ALL_EXACT"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
'''
    layout = R.make_layout(dict(hidden=heads*hd, ffn=32, heads=heads, kv_heads=kvheads,
                               head_dim=hd, max_tokens=128))
    (tmp_path/'block_layout.h').write_text(R.header(layout))
    (tmp_path/'tiny.cpp').write_text(source)
    # Freeze the exact synthetic test source before compilation/execution.
    source_sha, header_sha = R.file_sha(tmp_path/'tiny.cpp'), R.file_sha(tmp_path/'block_layout.h')
    subprocess.run([shutil.which('g++'), *R.FLAGS, str(tmp_path/'tiny.cpp'), '-o', str(tmp_path/'tiny')],
                   check=True, capture_output=True, text=True, timeout=120)
    run = subprocess.run([str(tmp_path/'tiny')], check=True, capture_output=True, text=True, timeout=90)
    assert R.file_sha(tmp_path/'tiny.cpp') == source_sha
    assert R.file_sha(tmp_path/'block_layout.h') == header_sha
    assert 'TINY_ATTENTION_ALL_EXACT' in run.stdout
    assert 'MASKED_FUTURE_OVERFLOW_DISCARDED' in run.stdout
    if hd == 32:
        assert 'CAUSAL_CAPTURE negative_zero=80000000 inactive_suffix=00000000' in run.stdout
    for tokens in (1, 17, 128):
        line = next(line for line in run.stdout.splitlines() if line.startswith(f'RESIDENT_ATTENTION tokens={tokens} '))
        assert m.parse_attention_log(line, layout, tokens, True) == [m.expected_attention(tokens, layout)]


def test_rectangular_provenance_and_counter_rejections(compiled_attention, tmp_path):
    directory, layout, _ = compiled_attention
    copied = tmp_path/'copied'
    shutil.copytree(directory/'mapped', copied)
    path = copied/'provenance.json'
    provenance = json.loads(path.read_text())
    provenance['rectangular_attention'] = False
    path.write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match='source identity differs|C\\+\\+ changed'):
        m.validate_generated(ROOT, copied)
    with pytest.raises(ValueError, match='Attention counters'):
        m.parse_attention_log('', layout, 17, True)
    with pytest.raises(ValueError, match='opt-in must be boolean'):
        m.resident_source(ROOT, rectangular_attention='yes')


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
