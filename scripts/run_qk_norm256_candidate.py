#!/usr/bin/env python3
"""Regenerate actual HardFloat and replay the opt-in Q/K head256 component.

Default operands are rebuilt from pinned official sources with fresh provenance.
Optional historical replay uses locally supplied, immutable original corpora.
Neither mode tests Matrix producer arithmetic, memory transport, or a tensor owner.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.model_geometry import require
from heteronpu import qk_norm256_candidate as oracle

CONTRACT = 'config/upstream/qwen3_5_0p8b/qk_norm256_candidate_contract.json'
CONTRACT_HASH = '484fe09b1def2b48d6abfe4f9076749db5d15cd51b453caec5cccb05b092aae6'
LEGACY = 'tests/fixtures/qk_norm256_legacy/fp32_rmsnorm256_chunked.sv'
LEGACY_HASH = 'e866318664e96dcf1eb9f1a7bf6e544ead95096ec1114e4373077a7ba3e3df12'
SOURCES = (CONTRACT, LEGACY, 'scripts/run_qk_norm256_candidate.py',
 'scripts/qk_norm256_reference.c', 'src/heteronpu/qk_norm256_candidate.py',
 'src/heteronpu/qk_norm256_materialization.py', 'scripts/rebuild_qk_norm256_corpora.py',
 'rtl/sfu/fp32_rmsnorm256_chunked.sv', 'rtl/sfu/qk_norm256_bf16_candidate.sv',
 'rtl/sfu/fp32_reduce16.sv', 'rtl/sfu/fp32_rsqrt_nr.sv',
 'rtl/sfu/fp32_rsqrt_coeffs.svh', 'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
 'tb/tb_qk_norm256_bf16_candidate.sv', 'tb/tb_qk_norm256_legacy_default.sv',
 'tb/tb_fp32_rmsnorm256_chunked.sv', 'tb/tb_l5_hidden256_block.sv',
 'src/heteronpu/rope_bf16_candidate.py', 'spec/numerical_contract.md')


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


component = load_script('run_rope_bf16_candidate')


def record(path):
    return {'file': path.name, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def packed(words, width=16):
    return sum(int(x) << (width*i) for i, x in enumerate(words))


def wide(words):
    return packed(words, 32)


def make_records(corpora=None):
    if corpora is None:
        corpora = {name: oracle.load_corpus(name) for name in ('local', 'remote')}
    require(len(corpora) == 2, 'requires two fully collected source corpora')
    records, provenance = [], {}
    for name, (data, origin) in corpora.items():
        provenance[name] = origin
        order = sorted(range(len(data['role'])), key=lambda i: tuple(int(data[k][i]) for k in ('phase','token','role','head')))
        for i in order:
            role = int(data['role'][i]); gate_idx = int(data['gate_index'][i])
            x = data['input_bf16_u32'][i]; weight = data['weight_bf16_u32'][role]
            gate = data['gate_bf16_u32'][gate_idx] if role == 0 else np.zeros(256, dtype=np.uint32)
            trace = oracle.head_trace(x, weight)
            records.append({'source': name, 'phase': int(data['phase'][i]), 'token': int(data['token'][i]),
                'head': int(data['head'][i]), 'role': role, 'source_index': i,
                'input': x, 'weight': weight, 'gate': gate,
                'native': data['native_bf16_u32'][i], 'norm': np.asarray(trace['output_bf16'], dtype=np.uint32),
                'fp32': np.asarray(trace['output_fp32'], dtype=np.uint32),
                'mean_eps': int(trace['mean_eps']), 'inverse': int(trace['inverse']),
                'flags': int(trace['aggregate_flags']), 'synthetic': False})
        print(f'{name}: verified projected Q/K and native norms loaded', flush=True)
    require(len(records) == 5120, 'incomplete real head corpus')
    rng = np.random.default_rng(0x256c1)
    # Finite arithmetic-domain boundaries and opaque all-encoding gate payloads.
    for n in range(32):
        if n < 2:
            x = np.full(256, 0x80000000 if n else 0, dtype=np.uint32)
        elif n == 2:
            x = np.array([0x2f800000, 0xcf7f0000] * 128, dtype=np.uint32)
        else:
            x = ((rng.integers(95,159,256,dtype=np.uint32) << 23) |
                 (rng.integers(0,128,256,dtype=np.uint32) << 16) |
                 (rng.integers(0,2,256,dtype=np.uint32) << 31))
        weight = np.zeros(256,dtype=np.uint32) if n < 3 else (
            np.full(256,0xbf800000,dtype=np.uint32) if n == 3 else
            ((rng.integers(95,159,256,dtype=np.uint32) << 23) |
             (rng.integers(0,128,256,dtype=np.uint32) << 16) |
             (rng.integers(0,2,256,dtype=np.uint32) << 31)))
        gate = ((np.arange(256,dtype=np.uint32) * 257 + n*2053) & 65535) << 16
        gate[:8] = [0,0x80000000,0x7f800000,0xff800000,0x7fc10000,0x7f810000,0x00010000,0xffff0000]
        role = n % 2
        trace = oracle.head_trace(x, weight)
        records.append({'source':'synthetic', 'phase':0,'token':n,'head':0,'role':role,'source_index':n,
            'input':x,'weight':weight,'gate':gate if role==0 else np.zeros(256,dtype=np.uint32),
            'padding':gate, 'native':None,'norm':np.asarray(trace['output_bf16'],dtype=np.uint32),
            'fp32':np.asarray(trace['output_fp32'],dtype=np.uint32),
            'mean_eps':int(trace['mean_eps']),'inverse':int(trace['inverse']),
            'flags':int(trace['aggregate_flags']),'synthetic':True})
    return records, provenance


def write_vectors(path, records):
    with path.open('w') as f:
        for i,r in enumerate(records):
            rawgate = r.get('padding',r['gate'])
            p = packed(r['input'] >> 16) | (packed(rawgate >> 16) << 4096)
            metadata = (i | r['role'] << 32 | 256 << 34 | 0xc1 << 50 | 0x358637bd << 58 |
                        r['flags'] << 94 | r['mean_eps'] << 99 | r['inverse'] << 131)
            for value in (p,packed(r['weight'] >> 16),packed(r['norm'] >> 16),packed(r['gate'] >> 16),metadata):
                f.write(f'{value:02048x}\n')


def verify_results(path, records):
    rows = []
    with path.open() as f:
        for line in f:
            fields = line.strip().split()
            require(fields and fields[0] in ('R','N','P'), 'malformed result record')
            if fields[0] != 'R':
                continue  # Supplemental directed cases are separately checked in SV.
            require(len(fields)==10 and fields[1].isdigit(), 'result field count')
            idx = int(fields[1]); require(idx == len(rows) and idx < len(records), 'duplicate/reordered/extra result')
            require([len(x) for x in fields[2:]] == [8,1,1,2,8,8,1024,1024], 'result width mismatch')
            require(all(re.fullmatch('[0-9a-f]+',s) for s in fields[2:]), 'result hex malformed')
            actual = tuple(int(x,16) for x in fields[2:]); r=records[idx]
            expected = (idx,r['role'],0,r['flags'],r['mean_eps'],r['inverse'],packed(r['norm']>>16),packed(r['gate']>>16))
            require(actual==expected, f'actual RTL result mismatch at head {idx}')
            rows.append([(actual[-2] >> (16*j)) & 65535 for j in range(256)])
    require(len(rows)==len(records), 'missing RTL result')
    return np.asarray(rows,dtype=np.uint16)


def compare_native(records, actual):
    groups=[]; witnesses=[]
    for source in dict.fromkeys(r['source'] for r in records if r.get('native') is not None):
        for phase in (0,1):
            for role in (0,1):
                ids=[i for i,r in enumerate(records) if r['source']==source and r['phase']==phase and r['role']==role]
                native=np.stack([records[i]['native'] for i in ids]).astype(np.uint32)
                got=actual[ids].astype(np.uint32)<<16
                diff=np.abs(got.view(np.float32).astype(np.float64)-native.view(np.float32).astype(np.float64))
                different=np.argwhere(got!=native)
                maximum=float(diff.max());mean=float(diff.mean())
                groups.append({'source':source,'phase':phase,'role':role,'heads':len(ids),'values':int(diff.size),
                    'max_abs':maximum,'mean_abs':mean,'different_bitpatterns':len(different),
                    'thresholds':{'max_abs':0.03125,'mean_abs':0.005},'pass':maximum<=0.03125 and mean<=0.005})
                for row,col in different:
                    r=records[ids[int(row)]]
                    witnesses.append({'source':source,'phase':phase,'role':role,'token':r['token'],'head':r['head'],
                       'channel':int(col),'native_bits':f'{int(native[row,col]):08x}','rtl_bits':f'{int(got[row,col]):08x}',
                       'abs_error':float(diff[row,col])})
    require(all(x['pass'] for x in groups),'source-native unchanged operator threshold failure')
    return {'groups':groups,'different_values':len(witnesses),'all_differences':witnesses}


# The exact debug and independent-C schemas are defined by the paired oracle
# and testbench. Their validators below reject incomplete/reordered traces.
def verify_debug(path, records):
    from heteronpu.rope_bf16_candidate import add_rne, mul_rne
    idx = 0; step = 0; trace = None; counts = {'C':0,'S':0,'O':0,'Y':0}
    expected_types = ['C']*16 + ['S'] + ['O']*16 + ['Y']
    widths = {'C':[8,8,8,8,8,20,2,2,2,2,128],
              'S':[8,8,8,2,8,8,8,8,8,8,8,8,8,8,10],
              'O':[128,20,128,128,40], 'Y':[8,8,2,2048]}
    with path.open() as f:
        for line in f:
            words=line.strip().split();require(len(words)>=4 and words[0] in counts and words[1] in ('R','N','P'),'bad debug record')
            if words[1]!='R':continue
            require(words[2].isdigit() and int(words[2])==idx and idx<len(records),'debug missing/extra/reordered head')
            require(re.fullmatch('[0-9a-f]{8}',words[3]) and int(words[3],16)==idx,'debug tag mismatch')
            kind=words[0];require(kind==expected_types[step],'debug node order/count mismatch')
            if trace is None:trace=oracle.head_trace(records[idx]['input'],records[idx]['weight'])
            start=4
            if kind in ('C','O'):
                chunk=step if kind=='C' else step-17
                require(words[4].isdigit() and int(words[4])==chunk,'debug chunk mismatch');start=5
            values=words[start:]
            require([len(w) for w in values]==widths[kind] and all(re.fullmatch('[0-9a-f]+',w) for w in values),'debug width/encoding mismatch')
            actual=tuple(int(w,16) for w in values)
            if kind=='C':
                sl=slice(chunk*16,(chunk+1)*16)
                mean,mf=mul_rne(trace['running'][chunk],0x3b800000)
                me,ef=add_rne(mean,0x358637bd)
                redflags=0
                for flag in trace['tree_flags'][chunk*15:(chunk+1)*15]:redflags|=flag
                expected=(trace['partials'][chunk],0 if chunk==0 else trace['running'][chunk-1],
                    trace['running'][chunk],mean,me,packed(trace['square_flags'][sl],5),redflags,
                    trace['running_flags'][chunk],mf,ef,wide(trace['squares'][sl]))
            elif kind=='S':
                coeff=oracle.RSQRT_COEFFICIENTS[trace['rsqrt_index']]
                expected=(trace['mean_eps'],trace['rsqrt_norm'],trace['rsqrt_scale'],trace['rsqrt_index'],
                    coeff>>32,coeff&0xffffffff,*trace['rsqrt_values'],packed(trace['rsqrt_flags'],5))
            elif kind=='O':
                sl=slice(chunk*16,(chunk+1)*16)
                flags=[v for pair in zip(trace['scaled_flags'][sl],trace['output_fp32_flags'][sl]) for v in pair]
                expected=(wide(trace['gamma'][sl]),packed(trace['gamma_flags'][sl],5),wide(trace['scaled'][sl]),
                    wide(trace['output_fp32'][sl]),packed(flags,5))
            else:
                expected=(trace['mean_eps'],trace['inverse'],trace['arithmetic_flags'],wide(trace['output_fp32']))
            require(actual==expected,f'actual RTL intermediate mismatch at {idx} {kind} step{step}')
            counts[kind]+=1;step+=1
            if step==34:idx+=1;step=0;trace=None
    require(idx==len(records) and step==0,'incomplete arithmetic trace')
    return {'heads':idx,'nodes':counts,'exact_value_and_flag_mismatches':0}


def run_c_reference(output, records, compiler):
    exe=output/'c_reference'
    command=[compiler,'-std=c11','-O2','-frounding-math','-ffp-contract=off','-fno-fast-math',
             str(ROOT/'scripts/qk_norm256_reference.c'),'-lm','-o',str(exe)]
    with (output/'c_build.log').open('w') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
    inp=output/'c_inputs.bin'; out=output/'c_traces.bin'
    inputs=np.stack([np.concatenate((r['input'],r['weight'])) for r in records]).astype('<u4')
    inputs.tofile(inp)
    with (output/'c_run.log').open('w') as err:
        subprocess.run([str(exe),str(inp),str(out)],stdout=err,stderr=subprocess.STDOUT,check=True,timeout=300)
    require(out.stat().st_size==len(records)*oracle.TRACE_WORDS*4,'missing/extra independent C trace bytes')
    actual=np.memmap(out,dtype='<u4',mode='r',shape=(len(records),oracle.TRACE_WORDS))
    for count,r in enumerate(records):
        expected=oracle.trace_words(oracle.head_trace(r['input'],r['weight']))
        require(np.array_equal(actual[count],expected),f'independent C node value/flag mismatch {count}')
    return {'heads':len(records),'words_per_head':oracle.TRACE_WORDS,'exact_value_and_flag_mismatches':0,
            'command':command,'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
            'trace':record(out),'inputs':record(inp)}


def verify_protocol_metrics(metrics, count):
    exact={'replay':count,'directed':60,'rejected':48,'accepted':count+56,'completed':count+56,
           'reset_reduction':1,'reset_rsqrt':1,'reset_output':1,'reset_blocked':1}
    require(all(metrics.get(k)==v for k,v in exact.items()),'protocol coverage/count mismatch')
    require(metrics.get('stalls',0)>=count*2 and metrics.get('mutations',0)>=count and
            metrics.get('busy_valid',0)>0 and metrics.get('cycles',0)>0,'missing protocol stress coverage')


def verify_supplemental(path):
    observed={}
    for line in path.read_text().splitlines():
        f=line.split()
        if f and f[0]=='R':continue
        require(len(f)==10 and f[0]=='N' and f[1].isdigit(),'malformed supplemental result')
        require([len(w) for w in f[2:]]==[8,1,1,2,8,8,1024,1024] and
                all(re.fullmatch('[0-9a-f]+',w) for w in f[2:]),'supplemental encoding mismatch')
        key=int(f[1]);require(key not in observed,'duplicate supplemental result')
        values=tuple(int(w,16) for w in f[2:]);observed[key]=values
        if key<48:
            require(values[0]==0xe0000000+key and values[2] in (1,2,3) and not any(values[3:]),
                    'rejection leaked data/flags/debug or wrong identity/status')
        else:require(values[2]==0,'supplemental valid request rejected')
    require(set(observed)==set(range(48))|set(range(1000,1008))|{902,904,905,999},
            'missing/extra supplemental coverage')
    return {'results':len(observed),'zero_data_rejections':48,'reset_recoveries':4,'Q_K_raw_gate_cases':8}


def verify_legacy_log(text):
    marker=re.findall(r'QK_NORM256_LEGACY_DEFAULT_PASS ([^\n]+)',text)
    require(len(marker)==1,'missing/duplicate legacy PASS marker')
    metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',marker[0])}
    require(metrics.get('vectors')==64 and metrics.get('random')==54 and
            metrics.get('default_equals_explicit_zero')==1 and metrics.get('original_rtl_bitexact')==1 and
            metrics.get('stalls',0)>=128 and metrics.get('cycles',0)>0,'legacy default coverage incomplete')
    return metrics


def run(args):
    require(not args.output.exists() or not any(args.output.iterdir()),'output must be fresh or empty')
    hashes={p:record(ROOT/p)['sha256'] for p in SOURCES}
    require(hashes[LEGACY]==LEGACY_HASH,'legacy source drift')
    require(hashes[CONTRACT]==CONTRACT_HASH,'candidate contract drift')
    contract=json.loads((ROOT/CONTRACT).read_text())
    require(contract['policy']==193 and contract['schema_version']==1,'candidate contract drift')
    args.output.mkdir(parents=True,exist_ok=True)
    historical = getattr(args, 'historical_corpus', False)
    materialized_digest = None
    if historical:
        corpora = {name: oracle.load_corpus(name) for name in ('local', 'remote')}
        records, provenance = make_records(corpora)
    else:
        from heteronpu.qk_norm256_materialization import rebuild, load_materialized
        corpora, materialized_digest = rebuild(ROOT, args.payload_layer0, args.payload_layer3,
            args.payload_extra, args.output / 'official_corpora')
        records, provenance = make_records(corpora)
    first, second = [entry[0] for entry in corpora.values()]
    cross_input_equal = bool(np.array_equal(first['input_bf16_u32'], second['input_bf16_u32']))
    cross_native_equal = bool(np.array_equal(first['native_bf16_u32'], second['native_bf16_u32']))
    write_vectors(args.output/'vectors.memh',records)
    metadata=[{k:v for k,v in r.items() if k not in ('input','weight','gate','padding','native','norm','fp32')} for r in records]
    (args.output/'transactions.json').write_text(json.dumps(metadata,indent=2)+'\n')
    np.savez_compressed(args.output/'tensors.npz',
        input=np.stack([r['input'] for r in records]),weight=np.stack([r['weight'] for r in records]),
        gate=np.stack([r['gate'] for r in records]),expected_norm=np.stack([r['norm'] for r in records]),
        expected_fp32=np.stack([r['fp32'] for r in records]),
        native_norm=np.stack([r['native'] for r in records if not r['synthetic']]))
    c_result=run_c_reference(args.output,records,args.compiler)
    print('Independent C/fenv agrees with every integer arithmetic node and flag',flush=True)
    env,verilator=component.old.emission_environment(args.generated,args.verilator)
    with (args.output/'emission.log').open('w') as log:
        subprocess.run(['bash',str(ROOT/'scripts/generate_rope_hardware_primitives.sh')],cwd=ROOT,env=env,
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    verify=[sys.executable,str(ROOT/'chisel/rope_hardware_oracle/manifest.py'),'verify',str(ROOT),str(args.generated)]
    subprocess.run(verify,check=True,timeout=60)
    common=[args.generated/'HeteroRoPEHardwarePrimitives.sv']+[ROOT/p for p in (
        'rtl/sfu/fp32_reduce16.sv','rtl/sfu/fp32_rsqrt_nr.sv','rtl/sfu/fp32_rmsnorm256_chunked.sv')]
    sources=common+[ROOT/p for p in ('rtl/sfu/fp32_to_bf16_rne_candidate.sv','rtl/sfu/qk_norm256_bf16_candidate.sv','tb/tb_qk_norm256_bf16_candidate.sv')]
    obj=args.output/'obj_candidate'
    command=component.sim_build(verilator,sources,'tb_qk_norm256_bf16_candidate',obj,{},args.output/'candidate_build.log')
    with (args.output/'candidate_run.log').open('w') as log:
        subprocess.run([str(obj/'tb'),'+VECTORS='+str(args.output/'vectors.memh'),f'+RECORDS={len(records)}',
            '+TRACE='+str(args.output/'candidate_results.txt'),'+DEBUG='+str(args.output/'candidate_debug.txt')],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    actual=verify_results(args.output/'candidate_results.txt',records)
    np.save(args.output/'actual_norm_bf16.npy',actual,allow_pickle=False)
    debug=verify_debug(args.output/'candidate_debug.txt',records)
    native=compare_native(records,actual)
    marker=re.findall(r'QK_NORM256_BF16_CANDIDATE_PASS ([^\n]+)',(args.output/'candidate_run.log').read_text())
    require(len(marker)==1,'missing/duplicate candidate PASS marker')
    metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',marker[0])}
    verify_protocol_metrics(metrics,len(records))
    supplemental=verify_supplemental(args.output/'candidate_results.txt')
    legacy_text=(ROOT/LEGACY).read_text()
    require(legacy_text.count('module fp32_rmsnorm256_chunked(')==1,'legacy rename anchor mismatch')
    legacy_src=args.output/'fp32_rmsnorm256_chunked_legacy_reference.sv'
    legacy_src.write_text(legacy_text.replace('module fp32_rmsnorm256_chunked(', 'module fp32_rmsnorm256_chunked_legacy_reference('))
    legacy_obj=args.output/'obj_legacy'
    legacy_command=component.sim_build(verilator,common+[legacy_src,ROOT/'tb/tb_qk_norm256_legacy_default.sv'],
        'tb_qk_norm256_legacy_default',legacy_obj,{},args.output/'legacy_build.log')
    with (args.output/'legacy_run.log').open('w') as log:
        subprocess.run([str(legacy_obj/'tb')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    legacy_metrics=verify_legacy_log((args.output/'legacy_run.log').read_text())
    subprocess.run(verify,check=True,timeout=60)
    if historical:
        oracle.verify_fixtures()
    else:
        load_materialized(ROOT, args.output / 'official_corpora', trusted_manifest_sha256=materialized_digest)
    require(hashes=={p:record(ROOT/p)['sha256'] for p in SOURCES},'source changed during execution')
    result={'schema_version':1,'status':'PASS_EXPERIMENTAL_QK_NORM256_BF16_COMPONENT_AND_LAYOUT',
        'real_heads':5120,'real_normalized_values':1310720,'real_raw_gate_values':1048576,'synthetic_heads':32,
        'native_expectations_regenerated':not historical,
        'corpus_mode':'historical_local_cache' if historical else 'fresh_pinned_official_CPU_dispatch_variants',
        'historical_byte_identity_claimed':historical,
        'unique_input_count_claimed':False,
        'official_executions_this_run':0 if historical else 2,
        'cross_variant_input_arrays_identical':cross_input_equal,
        'cross_variant_native_arrays_identical':cross_native_equal,
        'materialized_manifest_sha256':materialized_digest,
        'same_native_projected_input_component_gate':True,
        'production_policy_changed':False,'Matrix_producer_integrated':False,'SharedL2_integrated':False,
        'RoPE_chain_integrated':False,'whole_tensor_owner_integrated':False,'Command128_integrated':False,
        'full_block_numerical_complete':False,'PPA_measured':False,'mac_utilization_measured':False,
        'U00_2_complete':False,'U01_complete':False,'source_sha256':hashes,
        'fixture_provenance':provenance,'independent_C':c_result,'arithmetic_debug':debug,
        'source_native_comparison':native,'rtl_metrics':metrics,'supplemental_results':supplemental,'command':command,
        'legacy_default':{'exact_old_source_sha256':LEGACY_HASH,'command':legacy_command,'metrics':legacy_metrics,
                          'log':record(args.output/'legacy_run.log')},
        'emission_manifest':json.loads((args.generated/'manifest.json').read_text())}
    result['artifacts']={p.name:record(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps(public_summary(result),indent=2)+'\n')
    return result


def public_summary(result):
    """Allowlisted publication view: no raw tensors, logs, commands or host paths."""
    fields = ('schema_version','status','real_heads','real_normalized_values','real_raw_gate_values',
        'synthetic_heads','native_expectations_regenerated','corpus_mode','historical_byte_identity_claimed',
        'unique_input_count_claimed','official_executions_this_run','cross_variant_input_arrays_identical',
        'cross_variant_native_arrays_identical','materialized_manifest_sha256','same_native_projected_input_component_gate','production_policy_changed',
        'Matrix_producer_integrated','SharedL2_integrated','RoPE_chain_integrated','whole_tensor_owner_integrated',
        'Command128_integrated','full_block_numerical_complete','PPA_measured','mac_utilization_measured',
        'U00_2_complete','U01_complete','source_sha256','arithmetic_debug','source_native_comparison',
        'rtl_metrics','supplemental_results')
    summary = {key:result[key] for key in fields}
    summary['independent_C'] = {k:result['independent_C'][k] for k in
        ('heads','words_per_head','exact_value_and_flag_mismatches')}
    summary['legacy_default'] = {k:result['legacy_default'][k] for k in
        ('exact_old_source_sha256','metrics')}
    summary['corpora'] = {}
    for name, origin in result['fixture_provenance'].items():
        summary['corpora'][name] = {k:origin[k] for k in
            ('model_id','revision','framework_revision','layer_id','policy','array_sha256',
             'requested_aten_cpu_capability','actual_torch_cpu_capability','native_audit_status',
             'native_audit_gate_pass','native_failed_comparisons') if k in origin}
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--generated',type=Path,default=ROOT/'work/generated/qk_norm256_candidate')
    parser.add_argument('--verilator',type=Path)
    parser.add_argument('--compiler',default='gcc')
    parser.add_argument('--historical-corpus',action='store_true',help='Replay optional local historical archives; never download unpublished blobs')
    parser.add_argument('--payload-layer0',type=Path,default=ROOT/'work/qwen35_layer0_payload')
    parser.add_argument('--payload-layer3',type=Path,default=ROOT/'work/qwen35_layer3_payload')
    parser.add_argument('--payload-extra',type=Path,default=ROOT/'work/qwen35_prefix_payload')
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    try:result=run(args)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
        print('QK_NORM256_REJECTED: '+str(error),file=sys.stderr);raise SystemExit(3)
    print(result['status'])
