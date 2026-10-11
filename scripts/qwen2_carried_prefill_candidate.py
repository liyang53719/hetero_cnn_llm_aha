#!/usr/bin/env python3
"""Bounded Qwen2 L0 cold-to-carried software diagnostic. Never hardware admission.

Cold evidence is reused only after execution-output binding is revalidated.
The new C++ phase reads that candidate's actual K/V and raw embedding rows M:2M.
Official self-cache and candidate-cache-conditioned comparisons are distinct.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qwen2_bf16_materialization_candidate as C

R, N = C.R, C.N
BASE_GENERATOR_SHA256 = '357a74dd10b69fb78e2aff34410d1a01c881edbebbcf5d422bed2ee8acb47dbd'
POLICY_ID = 'qwen2-carried-bf16-materialization-v1-diagnostic'
METHODS = ('official_self_cache', 'independent_self_cache',
           'official_candidate_cache', 'independent_candidate_cache')
EXTRAS = ('scores', 'logits', 'softmax_fp32', 'prob', 'silu', 'cache_k', 'cache_v')


def replace_once(source: str, old: str, new: str) -> str:
    R.require(source.count(old) == 1, 'carried patch boundary absent/ambiguous')
    return source.replace(old, new)


def carried_source(root: Path) -> tuple[str, dict]:
    R.require(R.file_sha(root / 'scripts/qwen2_bf16_materialization_candidate.py') == BASE_GENERATOR_SHA256,
              'base candidate generator changed')
    source, identity = C.candidate_source(root)
    source = replace_once(source, 'unsigned tokens;', 'unsigned tokens; unsigned past=0;\n  std::vector<float> cacheK,cacheV;')
    begin, end = source.index('  void attention(){'), source.index('  void computeReference(){')
    attention = source[begin:end]
    # Only address geometry changes; all arithmetic statements retain the base recipe.
    attention = attention.replace('void attention(){', 'void attention(){unsigned total=past+tokens;')
    attention = attention.replace('tokens*tokens', 'tokens*total').replace('p(tokens)', 'p(total)')
    attention = attention.replace('k<tokens', 'k<total').replace('*tokens+k', '*total+k')
    attention = attention.replace('k<=t', 'k<=past+t')
    attention = replace_once(attention, 'get(OFF_K,size_t(k)*KV+kh*HD+j)', 'cacheK.at(size_t(k)*KV+kh*HD+j)')
    attention = replace_once(attention, 'get(OFF_V,size_t(k)*KV+kh*HD+j)', 'cacheV.at(size_t(k)*KV+kh*HD+j)')
    source = source[:begin] + attention + source[end:]
    source = replace_once(source, 'rope(OFF_KR,OFF_K,KVHEADS);attention();', '''rope(OFF_KR,OFF_K,KVHEADS);
    for(size_t i=0;i<size_t(tokens)*KV;i++){cacheK.push_back(get(OFF_K,i));cacheV.push_back(get(OFF_V,i));}
    attention();''')
    source = replace_once(source, 'need(argc==4,"usage: software_recipe readonly_arena tokens output_directory");',
        'need(argc==7,"usage: carried_recipe readonly_arena tokens output_directory past_tokens past_k past_v");')
    source = replace_once(source, '  model.computeReference();', '''  model.past=std::stoul(argv[4]);need(model.past==0||model.past==t,"past must be zero or one complete prior phase");
  auto loadCache=[&](const char* path,std::vector<float>& cache){
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    need(bool(f)&&uint64_t(f.tellg())==size_t(model.past)*KV*4,"previous cache length mismatch");
    cache.resize(size_t(model.past)*KV);f.seekg(0);f.read(reinterpret_cast<char*>(cache.data()),cache.size()*4);
    need(bool(f),"previous cache read failed");
    for(float v:cache)need(std::isfinite(v)&&(bits(v)&0xffff)==0,"previous cache nonfinite or non-BF16");
  };
  loadCache(argv[5],model.cacheK);loadCache(argv[6],model.cacheV);
  auto beforeK=model.cacheK,beforeV=model.cacheV;
  std::vector<float> immutable(model.reference.begin(),model.reference.begin()+WRITABLE_START/4);
  model.computeReference();
  need(std::memcmp(immutable.data(),model.reference.data(),WRITABLE_START)==0,"readonly arena mutated");
  need(std::memcmp(beforeK.data(),model.cacheK.data(),beforeK.size()*4)==0 &&
       std::memcmp(beforeV.data(),model.cacheV.data(),beforeV.size()*4)==0,"previous cache prefix mutated");
  for(const auto& stage:STAGES)for(size_t i=size_t(t)*stage.width;i<size_t(MAX_TOKENS)*stage.width;i++)
    need(bits(model.get(stage.off,i))==0x7fc00001u,"unused writable sentinel changed");
  std::cout<<"CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1"<<std::endl;''')
    source = replace_once(source, '  dump("scores",model.candidateScores);',
                          '  dump("cache_k",model.cacheK);dump("cache_v",model.cacheV);\n  dump("scores",model.candidateScores);')
    return '// DIAGNOSTIC_NOT_ACCEPTED: cold evidence reused; new carried execution.\n' + source, identity


def validate_layout(layout: dict) -> None:
    R.require(layout == R.make_layout({k: layout[k] for k in R.SHAPE}),
              'layout alias/offset/shape differs from guarded recipe')
    regions = sorted(layout['regions'], key=lambda r: r['offset'])
    R.require(all(a['offset'] + a['words'] * 4 <= b['offset'] for a, b in zip(regions, regions[1:])),
              'layout regions alias')


def prepare(root: Path, out: Path, shape: dict | None = None) -> dict:
    R.require(not out.exists(), 'refuse existing carried directory')
    source, identity = carried_source(root)
    layout = R.make_layout(shape); validate_layout(layout)
    out.mkdir(parents=True)
    (out / 'candidate.cpp').write_text(source)
    (out / 'block_layout.h').write_text(R.header(layout))
    compiler = shutil.which('g++'); R.require(compiler is not None, 'ordinary g++ required')
    command = [compiler, *R.FLAGS, str(out / 'candidate.cpp'), '-o', str(out / 'candidate')]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (out / 'build.log').write_text(completed.stdout + completed.stderr)
    R.require(completed.returncode == 0, 'carried compile failed')
    return dict(layout=layout, source_identity=identity, compile_command=command,
                cpp_sha256=R.file_sha(out / 'candidate.cpp'), binary_sha256=R.file_sha(out / 'candidate'),
                header_sha256=R.file_sha(out / 'block_layout.h'))


def load_cold(root: Path, directory: Path, tokens: int, expected_sha256: str) -> tuple[dict, dict, dict, dict]:
    R.require(len(expected_sha256)==64 and not (directory/'RESULT.json').is_symlink()
              and R.file_sha(directory/'RESULT.json')==expected_sha256, 'cold launch receipt hash mismatch')
    report = json.loads((directory / 'RESULT.json').read_text())
    R.require(report['status'] == 'DIAGNOSTIC_NOT_ACCEPTED' and report['policy'] == C.POLICY
              and report['tokens'] == tokens and report['generator_sha256'] == BASE_GENERATOR_SHA256
              and report['candidate_cpp_sha256'] == C.CPP_SHA256, 'cold source/policy/token mismatch')
    R.require(report['compile_command'][1:5] == R.FLAGS and
              R.file_sha(directory / 'candidate.cpp') == C.CPP_SHA256 and
              R.file_sha(directory / 'candidate') == report['candidate_binary_sha256'] and
              R.file_sha(directory / 'block_layout.h') == report['header_sha256'], 'cold compiled artifact changed')
    recipe_dir, native_dir = Path(report['recipe_directory']), Path(report['native_directory'])
    R.require(R.file_sha(recipe_dir / 'RESULT.json') == report['recipe_result_sha256'] and
              R.file_sha(native_dir / 'RESULT.json') == report['native_result_sha256'], 'cold source receipt changed')
    recipe = R.validate_recipe_receipt(root, recipe_dir)
    native = R.validate_native_receipt(root, native_dir, recipe)
    actual = C.load_exports(directory / 'tensors', report['tensors'], tokens)
    actual = C.validate_raw_evidence(report, directory, recipe_dir, R.make_layout(), tokens, actual)
    R.require(C.compare_nodes(root, actual, native_dir, native, tokens) == report['evaluation'], 'cold numerical evidence changed')
    old = json.loads((recipe_dir / 'REFERENCE_COMPARISON.json').read_text())
    R.require(old == R.build_comparison(root, recipe_dir, native_dir), 'original v0 comparison stale')
    R.require(old['final_fp32_budget_status'] == 'FAIL_EXISTING_FP32_FINAL_BUDGET', 'original v0 FAIL must be preserved')
    return report, actual, recipe, native


def config_for(layout: dict) -> dict:
    return dict(hidden_size=layout['hidden'], intermediate_size=layout['ffn'],
                num_attention_heads=layout['heads'], num_key_value_heads=layout['kv_heads'],
                rms_norm_eps=1e-6, rope_theta=1e6)


def write_arena(layout: dict, payload: dict, tokens: int, directory: Path) -> dict:
    """Raw embeddings and weights only. Absolute RoPE tables use the base recipe."""
    ids = list(range(tokens, 2 * tokens)); arena = directory / 'readonly_arena.f32le'
    R.pack_readonly(layout, payload, ids, arena)
    values = np.memmap(arena, dtype='<f4', mode='r+')
    for name, fn in (('cos', math.cos), ('sin', math.sin)):
        entry = next(r for r in layout['regions'] if r['name'] == name)
        table = np.array([[fn(t / math.pow(1e6, 2.0 * j / layout['head_dim']))
                           for j in range(layout['head_dim'] // 2)] for t in ids], dtype='<f4')
        values[entry['offset']//4:entry['offset']//4+table.size] = table.reshape(-1)
    values.flush(); del values
    return dict(token_ids=ids, position_ids=ids, readonly_sha256=R.file_sha(arena),
                input_x_sha256=R.file_sha(directory / 'input_x.f32le'), intermediate_preloads=0,
                rope_table_recipe='canonical_double_libm_absolute_position_then_FP32')


def cache_binding(cold_dir: Path, cold_report: dict, cold: dict, directory: Path, tokens: int,
                  write_files: bool = True) -> dict:
    records = []
    for name in ('cache_k', 'cache_v'):
        a = cold[name].transpose(0, 2, 1, 3).copy().reshape(tokens, -1)
        path = directory / ('previous_' + name + '.f32le')
        if write_files: a.tofile(path)
        records.append(dict(role=name, path=path.name, sha256=R.sha(a.tobytes()), bytes=a.nbytes,
                            source_export_sha256=next(e['sha256'] for e in cold_report['tensors'] if e['name'] == name)))
    return dict(cold_directory=str(cold_dir.resolve()), cold_result_sha256=R.file_sha(cold_dir / 'RESULT.json'),
                source_policy=C.POLICY_ID, source_cpp_sha256=C.CPP_SHA256,
                source_binary_sha256=cold_report['candidate_binary_sha256'],
                source_raw_outputs=cold_report['raw_outputs'], past_tokens=tokens,
                prior_position_ids=list(range(tokens)), position_ids=list(range(tokens, 2 * tokens)),
                token_ids=list(range(tokens, 2 * tokens)), records=records,
                cold_numerical_execution_repeated=False, same_binary_pair_claim=False)


def validate_binding(binding: dict, expected: dict, directory: Path, cold: dict, tokens: int) -> None:
    R.require(binding == expected, 'carry source/hash/length/position metadata mismatch')
    R.require(binding['past_tokens'] == tokens and binding['prior_position_ids'] == list(range(tokens))
              and binding['position_ids'] == binding['token_ids'] == list(range(tokens, 2*tokens)), 'carry absolute position mismatch')
    R.require([r['role'] for r in binding['records']] == ['cache_k', 'cache_v'], 'cache role swap')
    paths = []
    for entry in binding['records']:
        path = directory / entry['path']; paths.append(path)
        expected_bytes = cold[entry['role']].transpose(0, 2, 1, 3).copy().tobytes()
        R.require(entry['path'] == 'previous_' + entry['role'] + '.f32le' and not path.is_symlink()
                  and path.resolve().parent == directory.resolve()
                  and path.stat().st_size == entry['bytes'] == len(expected_bytes)
                  and R.file_sha(path) == entry['sha256'] and path.read_bytes() == expected_bytes,
                  'cache bytes/hash/source/role mismatch')
    R.require(not os.path.samefile(*paths), 'K/V cache file alias')


def read_tensor(path: Path, shape) -> np.ndarray:
    R.require(not path.is_symlink() and path.stat().st_size == math.prod(shape)*4, 'raw tensor length/alias mismatch')
    a = np.fromfile(path, dtype='<f4').reshape(shape)
    R.require(bool(np.isfinite(a).all()), 'nonfinite raw tensor')
    return a


def read_bound_tensor(path: Path, shape, expected_sha256: str) -> np.ndarray:
    """Hash the exact bytes consumed, including cache reads after C++ execution."""
    R.require(not path.is_symlink(), 'bound tensor alias')
    raw=path.read_bytes()
    R.require(len(raw)==math.prod(shape)*4 and R.sha(raw)==expected_sha256,
              'bound tensor bytes/hash changed at consumption')
    a=np.frombuffer(raw,dtype='<f4').reshape(shape).copy()
    R.require(bool(np.isfinite(a).all()), 'nonfinite bound tensor')
    return a


def load_actual(directory: Path, layout: dict, tokens: int, cold: dict) -> dict:
    stages = directory / 'raw_stages'; h, d, heads, kv = (layout[k] for k in ('hidden','head_dim','heads','kv_heads'))
    shapes = N.expected_shapes(config_for(layout), tokens, tokens); actual = {}
    for name in R.STAGE_NAMES:
        shape = shapes[name]
        if name in N.EXPORT_TOKEN_MAJOR:
            _, n, t, hd = shape
            a = read_tensor(stages / f'phase_{R.STAGE_NAMES.index(name)}_{name}_recipe.f32le', (1,t,n*hd))
            a = a.reshape(1,t,n,hd).transpose(0,2,1,3).copy()
        else:
            a = read_tensor(stages / f'phase_{R.STAGE_NAMES.index(name)}_{name}_recipe.f32le', shape)
        actual[name] = a
    for name in EXTRAS:
        shape = shapes[name]
        if name.startswith('cache_'):
            a = read_tensor(stages / (name+'.f32le'), (1,2*tokens,kv*d))
            a = a.reshape(1,2*tokens,kv,d).transpose(0,2,1,3).copy()
        else: a = read_tensor(stages / (name+'.f32le'), shape)
        actual[name] = a
    actual['x'] = read_tensor(directory / 'input_x.f32le', shapes['x'])
    arena = np.memmap(directory / 'readonly_arena.f32le', dtype='<f4', mode='r')
    for name in ('cos','sin'):
        offset = next(r['offset']//4 for r in layout['regions'] if r['name'] == name)
        half = N.bf16(arena[offset:offset+tokens*d//2].reshape(tokens,d//2).copy())
        actual[name] = np.concatenate((cold[name], np.concatenate((half,half),axis=1)),axis=0)
    actual['mask'] = N.causal_mask(tokens,tokens,'bf16')
    actual['repeat_k'] = np.repeat(actual['cache_k'],heads//kv,axis=1)
    actual['repeat_v'] = np.repeat(actual['cache_v'],heads//kv,axis=1)
    actual['pv'] = actual['att'].reshape(1,tokens,heads,d).transpose(0,2,1,3).copy()
    C.validate_dtypes(actual)
    R.require(all(list(actual[k].shape)==v for k,v in shapes.items()), 'carried 29-node geometry mismatch')
    return actual


def comparisons(actual: dict, references: dict, config: dict, cold: dict, root: Path) -> dict:
    policy = N.load_policy(root); result = {}
    for method in METHODS:
        rows=[]
        for name in sorted(N.REQUIRED_STAGES):
            a, b = N.export_value(actual[name],name), N.export_value(references[method][name],name)
            metrics = N.compare(a,b); error=np.abs(a.astype(np.float64)-b.astype(np.float64))
            ix=np.unravel_index(np.argmax(error),error.shape)
            rows.append(dict(name=name,metrics=metrics,verdict=N.stage_verdict(name,metrics,'bf16',policy),
                             max_abs_coordinate=list(map(int,ix)),candidate_at_max=float(a[ix]),reference_at_max=float(b[ix])))
        result[method]=dict(stages=rows,failed_stages=[r['name'] for r in rows if r['verdict']['passed'] is False])
    semantics=N.audit_semantics(actual,cold,config,'bf16')
    return dict(methods=result,semantics=semantics,policy=policy,
                all_semantics_exact=all(semantics.values()),
                expected_shape=[1,config['num_attention_heads'],actual['x'].shape[1],2*actual['x'].shape[1]],
                softmax_fp32_elementwise_gate='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE')


def native_references(root: Path, payload: dict, manifest: dict, cold_report: dict, native_report: dict,
                      cold: dict, x: np.ndarray) -> tuple[dict, dict]:
    import torch
    torch.set_num_threads(4); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    module,identity=N.runtime_identity(root)
    config_dict=json.loads((root/N.SOURCE/'config.json').read_text()); config=module.Qwen2Config(**config_dict)
    config._attn_implementation='eager'
    records={r['local_name']:r for r in manifest['tensors']}
    weights={name:(np.frombuffer(raw,dtype='<u2').astype('<u4')<<16).view('<f4').reshape(records[name]['shape'])
             for name,raw in payload.items() if name!='embed_tokens.rows_0_255'}
    layer=module.Qwen2DecoderLayer(config,layer_idx=0)
    layer.load_state_dict({k:torch.from_numpy(v).to(torch.bfloat16) for k,v in weights.items()},strict=True,assign=True)
    layer=layer.to(dtype=torch.bfloat16).eval(); refs={}; native_dir=Path(cold_report['native_directory'])
    for source in ('self_cache','candidate_cache'):
        caches={}
        for kind in ('native','independent'):
            if source=='candidate_cache': values=tuple(cold[n].copy() for n in ('cache_k','cache_v'))
            else:
                values=[]
                for name in ('cache_k','cache_v'):
                    entry=native_report['modes']['bf16']['phases'][0]['stages'][name]
                    values.append(read_bound_tensor(native_dir/entry[kind+'_file'],entry['shape'],
                                                    entry[kind+'_file_sha256']))
                values=tuple(values)
            caches[kind]=values
        cache=module.DynamicCache(); cache.update(*(torch.from_numpy(a).to(torch.bfloat16) for a in caches['native']),0)
        native,_=N.native_forward(module,layer,torch.from_numpy(x).to(torch.bfloat16),'bf16',cache)
        refs['official_'+source]={k:v.float().numpy() for k,v in native.items()}
        independent,_=N.independent_forward(weights,x,config_dict,'bf16',caches['independent'])
        refs['independent_'+source]=independent
        for prefix,kind in (('official','native'),('independent','independent')):
            old=dict(zip(('cache_k','cache_v'),caches[kind]))
            R.require(all(N.audit_semantics(refs[prefix+'_'+source],old,config_dict,'bf16').values()), 'reference semantic failure')
    return refs,identity


def inventory(directory: Path) -> list[dict]:
    return [dict(path=str(p.relative_to(directory)),bytes=p.stat().st_size,sha256=R.file_sha(p))
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name not in ('RESULT.json','FROZEN.json')]


def validate_frozen(directory: Path, report: dict, root: Path) -> dict:
    raw=(directory/'FROZEN.json').read_bytes()
    R.require(R.sha(raw)==report['frozen_sha256'],'carried freeze changed')
    frozen=json.loads(raw)
    pairs={'generator_sha256':'generator_sha256','build':'build','inputs':'inputs','carry_binding':'carry_binding',
           'payload_manifest_sha256':'payload_manifest_sha256','payload_pin_sha256':'payload_pin_sha256',
           'official_reference_identity':'official_reference_identity','resource_preflight':'resource_preflight',
           'launch_small_result_sha256':'small_result_sha256'}
    R.require(all(frozen.get(a)==report.get(b) for a,b in pairs.items())
              and frozen.get('launch_cold_result_sha256')==report['cold']['result_sha256']
              and frozen.get('threshold_policy')==report['evaluation']['policy']==N.load_policy(root)
              and frozen.get('payload_pin_sha256')==R.file_sha(root/'config/payload_pins/qwen2_layer0.json'),
              'carried freeze/result identity mismatch')
    for entry in frozen['files']:
        path=directory/entry['path']
        R.require(path.resolve().is_relative_to(directory.resolve()) and not path.is_symlink()
                  and path.stat().st_size==entry['bytes'] and R.file_sha(path)==entry['sha256'],
                  'carried frozen artifact changed')
    return frozen


def validate_small(path: Path, root: Path, cpp_sha: str, payload_sha: str) -> dict:
    report=json.loads((path/'RESULT.json').read_text())
    R.require(report['tokens']==16 and report['status']=='DIAGNOSTIC_NOT_ACCEPTED'
              and report['generator_sha256']==R.file_sha(Path(__file__)) and report['build']['cpp_sha256']==cpp_sha
              and report['payload_manifest_sha256']==payload_sha, 'M16 carried source/payload mismatch')
    R.require(report['artifacts']==inventory(path),'M16 carried artifact changed')
    cold_report,cold,_,_=load_cold(root,Path(report['cold']['directory']),16,report['cold']['result_sha256'])
    R.require(report['cold']['result_sha256']==R.file_sha(Path(report['cold']['directory'])/'RESULT.json'),'M16 cold receipt changed')
    binding=report['carry_binding']
    expected_binding=cache_binding(Path(report['cold']['directory']),cold_report,cold,path,16,write_files=False)
    validate_binding(binding,expected_binding,path,cold,16)
    validate_frozen(path,report,root)
    actual=load_actual(path,report['build']['layout'],16,cold)
    refs={method:{name:read_tensor(path/'references'/method/(name+'.f32le'),actual[name].shape)
                  for name in N.REQUIRED_STAGES} for method in METHODS}
    evaluation=comparisons(actual,refs,config_for(report['build']['layout']),cold,root)
    R.require(evaluation==report['evaluation'] and evaluation['all_semantics_exact'],'M16 carried comparison/semantics changed')
    R.require(all(set(v['failed_stages'])<={'scores','logits'} for v in evaluation['methods'].values()),
              'M16 carried principal stage failure; do not escalate')
    return report


def preflight(out: Path) -> dict:
    meminfo={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()}
    disk=shutil.disk_usage(out.parent)
    R.require(meminfo['MemAvailable']>=2*(1<<30) and disk.free>=2*(1<<30),'insufficient bounded model resources')
    R.require(all(os.environ.get(k)=='4' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')),
              'set OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=4')
    return dict(available_memory_bytes=meminfo['MemAvailable'],free_disk_bytes=disk.free,threads=4,
                maximum_query_tokens=128,maximum_key_tokens=256,maximum_execution_seconds=120)


def run(root: Path, cold_dir: Path, payload_dir: Path, out: Path, tokens: int, cold_sha256: str,
        small: Path | None=None, small_sha256: str | None=None) -> dict:
    R.require(tokens in (16,128),'only bounded M16/M128 carried production diagnostics')
    resource=preflight(out)
    cold_report,cold,recipe,native=load_cold(root,cold_dir,tokens,cold_sha256)
    payload_module=R.load_module(root/'scripts/qwen2_layer0_payload.py','carried_payload')
    manifest,payload=payload_module.load_payload(root,payload_dir)
    payload_sha=R.file_sha(payload_dir/'manifest.json')
    R.require(payload_sha==recipe['checkpoint_manifest_sha256'],'carried/cold payload mismatch')
    source,_=carried_source(root)
    if tokens==128:
        R.require(small is not None,'M128 requires checked complete M16 carried evidence')
        R.require(small_sha256 is not None and R.file_sha(small/'RESULT.json')==small_sha256,
                  'M16 carried launch receipt hash mismatch')
        validate_small(small,root,R.sha(source.encode()),payload_sha)
    build=prepare(root,out);inputs=write_arena(build['layout'],payload,tokens,out)
    binding=cache_binding(cold_dir,cold_report,cold,out,tokens)
    (out/'carry_binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    validate_binding(json.loads((out/'carry_binding.json').read_text()),binding,out,cold,tokens)
    _,runtime=N.runtime_identity(root)
    frozen=dict(generator_sha256=R.file_sha(Path(__file__)),build=build,inputs=inputs,carry_binding=binding,
                launch_cold_result_sha256=cold_sha256,launch_small_result_sha256=small_sha256,
                official_reference_identity=runtime,
                payload_manifest_sha256=payload_sha,payload_pin_sha256=R.file_sha(root/'config/payload_pins/qwen2_layer0.json'),
                threshold_policy=N.load_policy(root),resource_preflight=resource,
                files=inventory(out),small_result_sha256=R.file_sha(small/'RESULT.json') if small else None)
    (out/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
    frozen_sha256=R.file_sha(out/'FROZEN.json')
    for name in ('readonly_arena.f32le','input_x.f32le','previous_cache_k.f32le','previous_cache_v.f32le'):
        (out/name).chmod(0o444)
    stages=out/'raw_stages';stages.mkdir()
    command=[str(out/'candidate'),str(out/'readonly_arena.f32le'),str(tokens),str(stages),str(tokens),
             str(out/'previous_cache_k.f32le'),str(out/'previous_cache_v.f32le')]
    start=time.monotonic();execution=subprocess.run(command,capture_output=True,text=True,timeout=120)
    elapsed=time.monotonic()-start;(out/'run.log').write_text(execution.stdout+execution.stderr)
    R.require(execution.returncode==0 and execution.stdout.count('SOFTWARE_RECIPE_STAGE ')==15
              and 'CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1' in execution.stdout,
              'carried execution/lifetime incomplete')
    for entry in frozen['files']:
        p=out/entry['path'];R.require(p.stat().st_size==entry['bytes'] and R.file_sha(p)==entry['sha256'],'frozen input/source changed')
    R.require(R.file_sha(Path(__file__))==frozen['generator_sha256'],'generator changed during execution')
    R.require(R.file_sha(cold_dir/'RESULT.json')==cold_sha256,'cold receipt changed after freeze')
    validate_binding(json.loads((out/'carry_binding.json').read_text()),binding,out,cold,tokens)
    actual=load_actual(out,build['layout'],tokens,cold)
    refs,identity=native_references(root,payload,manifest,cold_report,native,cold,actual['x'])
    R.require(identity==frozen['official_reference_identity'],'official runtime changed after freeze')
    for method,values in refs.items():
        destination=out/'references'/method;destination.mkdir(parents=True)
        for name,value in values.items(): np.ascontiguousarray(value,dtype='<f4').tofile(destination/(name+'.f32le'))
    tensors=out/'tensors';tensors.mkdir();records=C.export_actual(actual,tensors)
    evaluation=comparisons(actual,refs,config_for(build['layout']),cold,root)
    R.require(evaluation['all_semantics_exact'],'carried semantic failure')
    old=json.loads((Path(cold_report['recipe_directory'])/'REFERENCE_COMPARISON.json').read_text())
    result=dict(schema=1,status='DIAGNOSTIC_NOT_ACCEPTED',policy_id=POLICY_ID,tokens=tokens,
        generator_sha256=frozen['generator_sha256'],frozen_sha256=frozen_sha256,build=build,
        payload_manifest_sha256=payload_sha,payload_pin_sha256=frozen['payload_pin_sha256'],
        small_result_sha256=small_sha256,carry_binding=binding,inputs=inputs,
        cold=dict(directory=str(cold_dir.resolve()),result_sha256=R.file_sha(cold_dir/'RESULT.json'),
                  evidence_reused=True,numerical_execution_repeated=False,same_binary_pair=False,
                  original_evaluation=cold_report['evaluation']),
        retained_v0=dict(result=old,report_sha256=R.file_sha(Path(cold_report['recipe_directory'])/'REFERENCE_COMPARISON.json')),
        official_reference_identity=identity,reference_methods={
            'official_self_cache':'Frozen official BF16 cold forward cache reused; unchanged official forward computes carried phase.',
            'independent_self_cache':'Frozen NumPy BF16 cold cache reused; independent equations compute carried phase.',
            'official_candidate_cache':'Official forward conditioned on actual prior candidate K/V; never injected into candidate.',
            'independent_candidate_cache':'Independent equations conditioned on actual prior candidate K/V.'},
        evaluation=evaluation,artifacts=inventory(out),tensors=records,resource_preflight=resource,
        carried_wall_seconds=elapsed,hardware_v0_conformant=False,rtl_executed=False,hardware_cycles=None,
        scope='One Qwen2-1.5B L0 complete block, two M-token phases; not all 28 layers or model logits/quality.')
    validate_frozen(out,result,root)
    (out/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--cold',type=Path,required=True)
    p.add_argument('--cold-sha256',required=True)
    p.add_argument('--payload',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tokens',type=int,choices=(16,128),default=16);p.add_argument('--small',type=Path)
    p.add_argument('--small-sha256')
    a=p.parse_args();r=run(a.root.resolve(),a.cold.resolve(),a.payload.resolve(),a.out.resolve(),a.tokens,
                         a.cold_sha256,a.small.resolve() if a.small else None,a.small_sha256)
    print(json.dumps(dict(status=r['status'],tokens=r['tokens'],seconds=r['carried_wall_seconds'],
                         failures={k:v['failed_stages'] for k,v in r['evaluation']['methods'].items()},
                         result=str(a.out/'RESULT.json')),indent=2))
    return 1


if __name__=='__main__':raise SystemExit(main())
