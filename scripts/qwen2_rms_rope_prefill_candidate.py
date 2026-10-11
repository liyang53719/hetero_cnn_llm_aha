#!/usr/bin/env python3
"""Versioned RMS1536/FP32-trig cold-to-carried software diagnostic.

Only RMS and table generation differ from the guarded carried v1 arithmetic.
Each phase actually executes the same newly built ELF. The carried process reads
raw cache files written by the cold process. This is not hardware ACK evidence,
policy approval, RTL, timing, or whole-model quality acceptance.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qwen2_carried_prefill_candidate as G
import qwen2_rms_rope_policy_diagnostic as D
C, R, N = G.C, G.R, G.N
STATUS = 'DIAGNOSTIC_NOT_ACCEPTED'
POLICY_ID = 'qwen2-rms1536-fp32-rope-prefill-v2-diagnostic'
PINS = {
    'scripts/qwen2_bf16_materialization_candidate.py': '357a74dd10b69fb78e2aff34410d1a01c881edbebbcf5d422bed2ee8acb47dbd',
    'scripts/qwen2_carried_prefill_candidate.py': '9df9ad51f98c7273ce8847a47a090093edd23c48289cf9e964f44a8ac3cd41b6',
    'scripts/qwen2_rms_rope_policy_diagnostic.py': '9117f240243357786bd538908343fcfb3a791769f2061d585524594b96b76ef6',
    'tests/test_qwen2_rms_rope_policy_diagnostic.py': 'b2a6766d85adc4df422f2b4319de0ceb9e95613f8357c8c1053cfa4f9b5027a2',
}
EVIDENCE_ROOT = 'reports/execution/QWEN2_RMS_ROPE_POLICY_20261011'
EVIDENCE_PINS = {
    'RESULT.json':'060bbb4e55fa0abba8ee7f253c68297630b90b2db778dec7dbceafc701e0eae5',
    'FROZEN.json':'500c4a52e8572bdcf9c295483dab5b533bae4a940ef9bc2df06f3ab216dd50c1',
    'BACKEND_VERIFIED.json':'c533e3f8d4e035e0c324bf15f4f98fce13fe6b38fdaa2793d56b2b6953a3620c',
    'source_manifest.json':'52555a6d4b7b307e7e87bb2cb6bfcaf4b20d27fa58046ef50ea78427a38dcbf9',
}
TABLE_DIGESTS = {
    'cos':'b2c04b80563e33961a310e59ae5e631849947230f5a119500cb91a66b698ee9e',
    'sin':'f18f7ead36a7657df0baa5e3f549b35b9bcb8703633026bb9767ff40398cfc69',
}
POLICY = dict(id=POLICY_ID, status=STATUS, policy_approval=False,
    hardware_v0_conformant=False, diagnostic_only=True,
    rms='RMS1536 V8/ILP4/three blocks of16, divide1536, epsilon, FP32 sqrt then reciprocal, BF16 before direct gamma and final BF16',
    rope='FP32 exponent/powf/reciprocal/phase multiply/sinf/cosf then BF16; positions0..255 only',
    preserved='Dense BF16 operands/FP32 increasing-K FMA; original bias order; 16-stripe QK; exp7; all other RNE boundaries',
    fp32_trig_bit_exact_claim=False, cross_host_equivalence_claim=False)
# Reuse the reviewed ordinary C implementation verbatim except symbol names.
# The complete ten-node function is also the exact helper used by full-block norm.
HELPERS = D.C_SOURCE
for _old, _new in (('bf', 'prefill_bf'), ('environment', 'prefill_environment'),
                   ('rms', 'prefill_rms'), ('rope', 'prefill_rope')):
    HELPERS = re.sub(r'\b' + _old + r'\b', _new, HELPERS)

NORM = '''  void norm(uint64_t in,uint64_t gamma,uint64_t out){
    need(H==1536,"reviewed RMS requires width1536");
    std::vector<float> nodes(5+5*1536);
    for(unsigned t=0;t<tokens;t++){
      need(prefill_rms(reference.data()+in/4+size_t(t)*H,reference.data()+gamma/4,1,nodes.data())==1,"RMS1536 failed");
      for(int i=0;i<H;i++)put(out,size_t(t)*H+i,nodes[5+4*1536+i]);
    }
  }
'''
MODES = '''  if(argc==3 && std::string(argv[1])=="--tables"){
    verifyFloatEnvironment();std::vector<float> data(192+5*16384);
    need(prefill_rope(data.data())==1,"table generation failed");
    need(!std::filesystem::exists(argv[2]),"refuse table overwrite");
    std::ofstream f(argv[2],std::ios::binary);f.write(reinterpret_cast<char*>(data.data()),data.size()*4);
    need(bool(f),"table output failed");return 0;
  }
  if(argc==6 && std::string(argv[1])=="--rms-nodes"){
    verifyFloatEnvironment();unsigned rows=std::stoul(argv[2]);need(rows>=1&&rows<=128,"RMS rows");
    auto read=[&](const char* path,size_t count){std::vector<float> a(count);std::ifstream f(path,std::ios::binary|std::ios::ate);
      need(bool(f)&&uint64_t(f.tellg())==count*4,"RMS input length");f.seekg(0);f.read(reinterpret_cast<char*>(a.data()),count*4);
      need(bool(f),"RMS input read");for(float v:a)need(std::isfinite(v)&&(bits(v)&0xffff)==0,"RMS finite BF16 required");return a;};
    auto x=read(argv[3],rows*1536),g=read(argv[4],1536);std::vector<float> data(5*rows+5*rows*1536);
    need(prefill_rms(x.data(),g.data(),rows,data.data())==1,"RMS failed");
    need(!std::filesystem::exists(argv[5]),"refuse RMS overwrite");std::ofstream f(argv[5],std::ios::binary);
    f.write(reinterpret_cast<char*>(data.data()),data.size()*4);need(bool(f),"RMS output failed");return 0;
  }
'''


def verify_pins(root=ROOT):
    for name, digest in PINS.items():
        R.require(R.file_sha(root / name) == digest, 'reviewed dependency changed: ' + name)
    return dict(PINS)


def candidate_source(root=ROOT):
    verify_pins(root)
    source, identity = G.carried_source(root)
    # Remove the old driver's descriptive reuse claim; never rename its policy.
    prefix = '// DIAGNOSTIC_NOT_ACCEPTED: cold evidence reused; new carried execution.\n'
    R.require(source.startswith(prefix), 'guarded carried prefix changed')
    source = source[len(prefix):]
    begin, end = source.index('  void norm('), source.index('  void dense(')
    original_norm = source[begin:end]
    source = source[:begin] + NORM + source[end:]
    source = G.replace_once(source, 'class SoftwareRecipe {', HELPERS + '\nclass SoftwareRecipe {')
    source = G.replace_once(source, 'int main(int argc,char** argv){try{', 'int main(int argc,char** argv){try{\n' + MODES)
    source = '// ' + POLICY_ID + ': ' + STATUS + '; both phases newly executed.\n' + source
    identity.update(parent_carried_cpp_sha256=R.sha(G.carried_source(root)[0].encode()),
                    replaced_norm_sha256=R.sha(original_norm.encode()),
                    reviewed_helper_sha256=R.sha(D.C_SOURCE.encode()),
                    integrated_helper_sha256=R.sha(HELPERS.encode()), policy_id=POLICY_ID)
    return source, identity


def prepare(out, shape=None):
    R.require(not out.exists(), 'refuse existing candidate directory')
    source, identity = candidate_source()
    layout = R.make_layout(shape)
    G.validate_layout(layout)
    R.require(layout['hidden'] == 1536 and layout['head_dim'] == 128, 'fixed RMS1536/RoPE128 geometry')
    out.mkdir(parents=True)
    (out / 'candidate.cpp').write_text(source)
    (out / 'block_layout.h').write_text(R.header(layout))
    compiler = shutil.which('g++')
    R.require(compiler is not None, 'ordinary g++ required')
    command = [compiler, *R.FLAGS, str(out / 'candidate.cpp'), '-o', str(out / 'candidate')]
    done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / 'build.log').write_text(done.stdout + done.stderr)
    R.require(done.returncode == 0, 'candidate compile failed')
    return dict(layout=layout, source_identity=identity, compile_command=command,
                cpp_sha256=R.file_sha(out / 'candidate.cpp'), binary_sha256=R.file_sha(out / 'candidate'),
                header_sha256=R.file_sha(out / 'block_layout.h'),
                compiler_path=str(Path(compiler).resolve()), compiler_sha256=R.file_sha(Path(compiler).resolve()),
                compiler_version=subprocess.check_output([compiler, '--version'], text=True).splitlines()[0])


def table_values(path):
    a = G.read_tensor(path, (192 + 5 * 16384,))
    return {name: a[192+i*16384:192+(i+1)*16384].reshape(256,64)
            for i,name in enumerate(('angle','cos','sin','cos_bf16','sin_bf16'))}


def generate_tables(binary, path):
    done = subprocess.run([str(binary), '--tables', str(path)], capture_output=True, text=True, timeout=10)
    R.require(done.returncode == 0, 'new-binary table generation failed')
    arrays = table_values(path)
    checks = {}
    for trig in ('cos','sin'):
        doubled = np.concatenate((arrays[trig + '_bf16'], arrays[trig + '_bf16']), axis=1)
        R.require(R.sha(doubled.tobytes()) == TABLE_DIGESTS[trig], 'BF16 trig table identity mismatch')
        R.require(np.array_equal(D.bf16(arrays[trig]).view('<u4'), arrays[trig+'_bf16'].view('<u4')), 'BF16 table rounding')
        checks[trig] = dict(full_fp32_half_sha256=R.sha(arrays[trig].tobytes()),
            full_bf16_half_sha256=R.sha(arrays[trig+'_bf16'].tobytes()),
            reviewed_and_official_bf16_exact=True)
    return dict(raw_sha256=R.file_sha(path), positions=[0,255], tables=checks,
                produced_by_binary_sha256=R.file_sha(binary), fp32_bit_exact_claim=False)


def write_arena(layout, payload, tokens, past, directory, tables):
    R.require(tokens in (1,2,16,128) and past in (0,tokens), 'phase geometry')
    ids = list(range(past,past+tokens))
    R.pack_readonly(layout, payload, ids, directory/'readonly_arena.f32le')
    values = np.memmap(directory/'readonly_arena.f32le', dtype='<f4', mode='r+')
    arrays = table_values(tables)
    for name in ('cos','sin'):
        offset = next(r['offset']//4 for r in layout['regions'] if r['name']==name)
        values[offset:offset+tokens*64] = arrays[name][ids].reshape(-1)
    values.flush(); del values
    return dict(token_ids=ids, position_ids=ids, past_tokens=past,
                readonly_sha256=R.file_sha(directory/'readonly_arena.f32le'),
                input_x_sha256=R.file_sha(directory/'input_x.f32le'), intermediate_preloads=0,
                rope_table_sha256=R.file_sha(tables), rope_recipe=POLICY['rope'])


def runtime_tools(binary):
    import torch
    R.require(torch.__version__=='2.10.0+cpu' and torch.version.git_version==D.TORCH_COMMIT,
              'reviewed Torch build changed')
    R.require(torch.backends.cpu.get_cpu_capability()=='AVX512' and os.getenv('ATEN_CPU_CAPABILITY') is None,
              'reviewed CPU dispatch context changed')
    linkage=subprocess.check_output(['ldd',str(binary)],text=True)
    paths=[Path(sys.executable).resolve(),Path(torch.__file__).parent/'lib/libtorch_cpu.so']
    for line in linkage.splitlines():
        fields=line.strip().split()
        if len(fields)>2 and fields[1]=='=>' and fields[2].startswith('/'):paths.append(Path(fields[2]).resolve())
    return dict(python_executable=str(Path(sys.executable).resolve()),torch_commit=D.TORCH_COMMIT,
        reported_cpu_capability=torch.backends.cpu.get_cpu_capability(),ldd=linkage,
        runtime_files=[file_record(path) for path in paths],
        reference_settings=dict(threads=4,interop_threads=1,deterministic_algorithms=True,
                                configured_by='guarded carried v1 native_references before forwards'),
        actual_execution_threads=1,maximum_phase_threads=4)


def audit_actual_rms(actual,payload,module):
    checks={}
    for output,input_,gamma in (('n0','x','input_layernorm.weight'),('n1','r','post_attention_layernorm.weight')):
        weight=(np.frombuffer(payload[gamma],dtype='<u2').astype('<u4')<<16).view('<f4')
        stages=D.rms_recipe(actual[input_],weight)
        comparison=D.compare(actual[output],stages['output'])
        official,native_nodes=D.torch_rms(module,actual[input_],weight)
        official_output=D.compare(actual[output],official)
        official_nodes={name:D.compare(stages[name],value) for name,value in native_nodes.items()}
        R.require(official_output['bit_exact'] and all(v['bit_exact'] for v in official_nodes.values()),
                  'same-input official RMS mismatch: '+output)
        R.require(comparison['bit_exact'], 'full-block RMS differs from reviewed helper: '+output)
        checks[output]=dict(same_input_reviewed_recipe=comparison,same_input_official_output=official_output,
            same_input_official_nodes=official_nodes,scope='same actual input only; end-to-end gates remain separate',
            input_sha256=R.sha(actual[input_].tobytes()),gamma_sha256=R.sha(weight.tobytes()),
            scalar_rne=D.check_scalar_rne(*(stages[n] for n in ('variance','root','sum','mean','inverse'))),
            reviewed_node_sha256={name:R.sha(value.tobytes()) for name,value in stages.items()})
    return checks


def source_files():
    names = list(PINS) + [str(Path(__file__).relative_to(ROOT)),
        'tests/test_qwen2_rms_rope_prefill_candidate.py', 'scripts/qwen2_block_recipe_model.py',
        'scripts/qwen2_layer0_model_gate.py', 'scripts/qwen2_layer0_payload.py',
        'spec/numerical_contract.md', 'config/payload_pins/qwen2_layer0.json']
    records = {name:R.file_sha(ROOT/name) for name in names}
    for name,digest in EVIDENCE_PINS.items():
        relative=EVIDENCE_ROOT+'/'+name
        R.require(R.file_sha(ROOT/relative)==digest, 'published reviewed evidence changed: '+name)
        records[relative]=digest
    return records


def verify_sources(records):
    for name,digest in records.items():
        R.require(R.file_sha(ROOT/name)==digest, 'frozen source changed: '+name)


def cache_binding(cold_dir, cold_report, cold, tokens):
    records=[]
    for name in ('cache_k','cache_v'):
        path=cold_dir/'raw_stages'/(name+'.f32le')
        raw=cold[name].transpose(0,2,1,3).copy().tobytes()
        R.require(not path.is_symlink() and path.read_bytes()==raw, 'raw actual cache differs from cold export')
        records.append(dict(role=name,path=str(path.resolve()),sha256=R.sha(raw),bytes=len(raw)))
    return dict(cold_directory=str(cold_dir.resolve()),cold_result_sha256=R.file_sha(cold_dir/'RESULT.json'),
                source_policy=POLICY_ID,source_cpp_sha256=cold_report['build']['cpp_sha256'],
                source_binary_sha256=cold_report['build']['binary_sha256'],records=records,past_tokens=tokens,
                prior_position_ids=list(range(tokens)),position_ids=list(range(tokens,2*tokens)),
                token_ids=list(range(tokens,2*tokens)),same_binary_pair=True,
                direct_raw_previous_actual_cache_files=True,official_cache_injected=False)


def validate_binding(binding, expected, cold, tokens):
    R.require(binding==expected, 'carry source/hash/position metadata mismatch')
    R.require(binding['source_policy']==POLICY_ID and binding['past_tokens']==tokens
              and binding['prior_position_ids']==list(range(tokens))
              and binding['position_ids']==binding['token_ids']==list(range(tokens,2*tokens)), 'carry position mismatch')
    paths=[]
    R.require([r['role'] for r in binding['records']]==['cache_k','cache_v'], 'cache role mismatch')
    for record in binding['records']:
        path=Path(record['path']);paths.append(path)
        raw=cold[record['role']].transpose(0,2,1,3).copy().tobytes()
        expected_path=Path(binding['cold_directory'])/'raw_stages'/(record['role']+'.f32le')
        R.require(path==expected_path and not path.is_symlink() and path.read_bytes()==raw
                  and len(raw)==record['bytes'] and R.sha(raw)==record['sha256'], 'raw previous cache bytes/hash/source mismatch')
    R.require(not os.path.samefile(*paths), 'cache file alias')


def software_ack(stdout, tokens, returncode):
    """Software phase receipts only. No bus, stall, or hardware ACK claim."""
    entries=re.findall(r'^SOFTWARE_RECIPE_STAGE phase=(\d+) name=(\w+) values=(\d+)$',stdout,re.M)
    layout=R.make_layout()
    widths={r['name']:r['words']//layout['max_tokens'] for r in layout['regions']}
    expected=[(str(i),name,str(tokens*widths[name])) for i,name in enumerate(R.STAGE_NAMES)]
    R.require(returncode==0 and entries==expected
        and stdout.count('SOFTWARE_RECIPE_COMPLETE tokens='+str(tokens)+' stages=15')==1
        and stdout.count('SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10')==1
        and stdout.count('CARRIED_LIFETIME readonly_exact=1 cache_prefix_exact=1 unused_sentinels_exact=1')==1,
        'software completion/phase ACK missing, duplicate, reordered, or failed')
    return dict(phase_receipts_exactly_once_in_order=True,process_completion_ack=True,
                scope='software file/process contract only',hardware_ack_verified=False)


def compare(actual, refs, previous):
    policy=N.load_policy(ROOT);methods={}
    for method,reference in refs.items():
        rows=[]
        for name in sorted(N.REQUIRED_STAGES):
            a,b=N.export_value(actual[name],name),N.export_value(reference[name],name)
            metrics=N.compare(a,b);error=np.abs(a.astype(np.float64)-b.astype(np.float64));ix=np.unravel_index(np.argmax(error),error.shape)
            rows.append(dict(name=name,metrics=metrics,verdict=N.stage_verdict(name,metrics,'bf16',policy),
                max_abs_coordinate=list(map(int,ix)),candidate_at_max=float(a[ix]),reference_at_max=float(b[ix])))
        failures=[r['name'] for r in rows if r['verdict']['passed'] is False]
        methods[method]=dict(stages=rows,failed_stages=failures,numerical_status='FAIL' if failures else 'PASS')
    semantic=N.audit_semantics(actual,previous,G.config_for(R.make_layout()),'bf16')
    return dict(methods=methods,semantics=semantic,all_semantics_exact=all(semantic.values()),policy=policy,
        softmax_fp32_elementwise_gate='DIAGNOSTIC_NO_APPROVED_FP32_TOLERANCE',
        softmax_row_sum_limit=2e-5,max_softmax_row_sum_error=float(np.max(np.abs(actual['softmax_fp32'].sum(-1,dtype=np.float32)-1))))


def read_cold_refs(old_report, native_report):
    refs={};directory=Path(old_report['native_directory'])
    for method,kind in (('official_self_cache','native'),('independent_self_cache','independent')):
        refs[method]={}
        for name,entry in native_report['modes']['bf16']['phases'][0]['stages'].items():
            value=G.read_bound_tensor(directory/entry[kind+'_file'],entry[kind+'_export_shape'],entry[kind+'_file_sha256'])
            if name in N.EXPORT_TOKEN_MAJOR:
                batch,heads,tokens,dim=entry['shape']
                R.require(list(value.shape)==[batch,tokens,heads*dim], 'cold reference export layout mismatch')
                value=value.reshape(batch,tokens,heads,dim).transpose(0,2,1,3).copy()
            R.require(list(value.shape)==entry['shape'], 'cold reference logical shape mismatch')
            refs[method][name]=value
    return refs


def frozen_verify(directory, frozen, freeze_sha):
    R.require(R.file_sha(directory/'FROZEN.json')==freeze_sha, 'phase freeze changed')
    verify_sources(frozen['source_files'])
    for record in frozen['files'] + frozen['tools']['runtime_files']:
        path=Path(record['path'])
        R.require(not path.is_symlink() and path.stat().st_size==record['bytes']
                  and R.file_sha(path)==record['sha256'], 'frozen launch file changed: '+str(path))


def file_record(path):
    R.require(not path.is_symlink(), 'cannot freeze symlink')
    return dict(path=str(path.resolve()),bytes=path.stat().st_size,sha256=R.file_sha(path))


def execute_phase(pair, build, payload, tokens, past, table_identity, shared, cold=None, cold_report=None):
    directory=pair/('cold' if past==0 else 'carried');directory.mkdir()
    inputs=write_arena(build['layout'],payload,tokens,past,directory,pair/'rope_full.f32le')
    binding=None
    if past:
        binding=cache_binding(pair/'cold',cold_report,cold,tokens)
        validate_binding(binding,binding,cold,tokens)
        R.require(binding['source_binary_sha256']==build['binary_sha256'],'same binary pair mismatch')
        paths=[Path(r['path']) for r in binding['records']]
    else:
        paths=[directory/'empty_k.f32le',directory/'empty_v.f32le']
        for path in paths:path.write_bytes(b'')
    command=[str(pair/'build/candidate'),str(directory/'readonly_arena.f32le'),str(tokens),
             str(directory/'raw_stages'),str(past),*(str(p) for p in paths)]
    frozen=dict(policy=POLICY,build=build,inputs=inputs,carry_binding=binding,table_identity=table_identity,
        **shared,resource_preflight=dict(G.preflight(directory),maximum_execution_seconds=60),command=command,timeout_seconds=60,
        files=[file_record(p) for p in [pair/'build/candidate',pair/'build/candidate.cpp',pair/'build/block_layout.h',
            pair/'rope_full.f32le',directory/'readonly_arena.f32le',directory/'input_x.f32le',*paths]])
    (directory/'FROZEN.json').write_text(json.dumps(frozen,indent=2)+'\n')
    freeze_sha=R.file_sha(directory/'FROZEN.json')
    for p in [directory/'readonly_arena.f32le',directory/'input_x.f32le',*paths]:p.chmod(0o444)
    frozen_verify(directory,frozen,freeze_sha)
    (directory/'raw_stages').mkdir()
    start=time.monotonic();done=subprocess.run(command,capture_output=True,text=True,timeout=60)
    elapsed=time.monotonic()-start
    (directory/'run.log').write_text(done.stdout+done.stderr)
    ack=software_ack(done.stdout,tokens,done.returncode)
    frozen_verify(directory,frozen,freeze_sha)
    if past:validate_binding(binding,binding,cold,tokens)
    if past:actual=G.load_actual(directory,build['layout'],tokens,cold)
    else:
        actual=C.load_actual(directory/'raw_stages',directory/'readonly_arena.f32le',directory/'input_x.f32le',build['layout'],tokens)
        for name in ('cache_k','cache_v'):
            R.require(actual[name].transpose(0,2,1,3).copy().tobytes()==(directory/'raw_stages'/(name+'.f32le')).read_bytes(), 'cold raw cache mismatch')
    R.require(all(N.audit_semantics(actual,cold,G.config_for(build['layout']),'bf16').values()), 'actual semantic failure')
    return directory,actual,dict(status=STATUS,policy=POLICY,tokens=tokens,past_tokens=past,build=build,
        inputs=inputs,carry_binding=binding,frozen_sha256=freeze_sha,wall_seconds=elapsed,software_ack=ack,
        hardware_v0_conformant=False,policy_approval=False,rtl_executed=False,hardware_cycles=None)


def finish_phase(directory,actual,refs,previous,report):
    report['evaluation']=compare(actual,refs,previous)
    R.require(report['evaluation']['all_semantics_exact'], 'phase semantics failed')
    for method,values in refs.items():
        target=directory/'references'/method;target.mkdir(parents=True)
        for name,value in values.items():np.ascontiguousarray(value,dtype='<f4').tofile(target/(name+'.f32le'))
    target=directory/'tensors';target.mkdir()
    report['tensors']=C.export_actual(actual,target)
    report['artifacts']=G.inventory(directory)
    (directory/'RESULT.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


def validate_pair(path, expected_sha, tokens=16):
    R.require(R.file_sha(path/'RESULT.json')==expected_sha, 'pair receipt hash mismatch')
    report=json.loads((path/'RESULT.json').read_text())
    source,_=candidate_source()
    R.require(report['tokens']==tokens and report['policy']==POLICY
              and report['build']['cpp_sha256']==R.sha(source.encode()), 'pair source/policy mismatch')
    verify_sources(report['source_files'])
    actuals={}
    for phase in ('cold','carried'):
        directory=path/phase
        R.require(R.file_sha(directory/'RESULT.json')==report['phase_result_sha256'][phase], 'phase result changed')
        receipt=json.loads((directory/'RESULT.json').read_text())
        R.require(receipt['artifacts']==G.inventory(directory), 'phase artifact changed')
        frozen=json.loads((directory/'FROZEN.json').read_text())
        frozen_verify(directory,frozen,receipt['frozen_sha256'])
        R.require(frozen['build']==receipt['build']==report['build'] and frozen['policy']==receipt['policy']==POLICY
                  and frozen['inputs']==receipt['inputs'] and frozen['carry_binding']==receipt['carry_binding'], 'freeze/result mismatch')
        if phase=='cold':
            actual=C.load_actual(directory/'raw_stages',directory/'readonly_arena.f32le',directory/'input_x.f32le',report['build']['layout'],tokens)
            previous=None
        else:
            previous=actuals['cold'];actual=G.load_actual(directory,report['build']['layout'],tokens,previous)
            cold_report=json.loads((path/'cold/RESULT.json').read_text())
            expected=cache_binding(path/'cold',cold_report,previous,tokens)
            validate_binding(receipt['carry_binding'],expected,previous,tokens)
        refs={method:{name:G.read_tensor(directory/'references'/method/(name+'.f32le'),actual[name].shape)
                      for name in N.REQUIRED_STAGES} for method in receipt['evaluation']['methods']}
        R.require(compare(actual,refs,previous)==receipt['evaluation'] and receipt['evaluation']['all_semantics_exact'], 'phase comparison/semantics changed')
        software_ack((directory/'run.log').read_text(),tokens,0)
        actuals[phase]=actual
    return report


def run(out,payload_dir,tokens,small=None,small_sha=None):
    R.require(tokens in (16,128) and not out.exists() and out.is_relative_to(ROOT/'work'), 'fresh bounded work output required')
    resource=G.preflight(out);verify_pins()
    if tokens==128:
        R.require(small is not None and small_sha is not None,'M128 requires reviewed complete new M16 pair')
        validate_pair(small,small_sha)
    old_name,old_sha=D.RUNS['cold_m'+str(tokens)]
    old_report,_,recipe,native=G.load_cold(ROOT,ROOT/'work'/old_name,tokens,old_sha)
    module,identity=N.runtime_identity(ROOT)
    R.require(identity==native['identity'], 'cached official cold runtime changed')
    payload_module=R.load_module(ROOT/'scripts/qwen2_layer0_payload.py','rms_prefill_payload')
    manifest,payload=payload_module.load_payload(ROOT,payload_dir)
    R.require(R.file_sha(payload_dir/'manifest.json')==recipe['checkpoint_manifest_sha256'], 'payload differs from original cold')
    policy=N.load_policy(ROOT)
    R.require(policy['operator']==dict(max_abs=.03125,mean_abs=.005) and policy['block']==dict(max_abs=.05,mean_abs=.01), 'original numerical gates changed')
    out.mkdir();build=prepare(out/'build')
    table_identity=generate_tables(out/'build/candidate',out/'rope_full.f32le')
    cold_refs=read_cold_refs(old_report,native)
    shared=dict(source_files=source_files(),official_reference_identity=identity,tools=runtime_tools(out/'build/candidate'),
        payload_manifest_sha256=R.file_sha(payload_dir/'manifest.json'),threshold_policy=policy,
        old_cold_result_sha256=old_sha,small_result_sha256=small_sha,
        reference_reuse=dict(cached_cold_official_forward=1,cached_cold_independent_forward=1,
            native_directory=old_report['native_directory'],native_result_sha256=old_report['native_result_sha256'],
            actual_candidate_cold_reused=False))
    directory,cold,cold_report=execute_phase(out,build,payload,tokens,0,table_identity,shared)
    # Prepare carried references from the real cold output and fixed next raw IDs.
    # This guarded helper configures four intra-op / one inter-op threads before
    # all official same-input RMS audits. No reference tensor enters the candidate.
    embeddings=(np.frombuffer(payload['embed_tokens.rows_0_255'],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(256,1536)
    next_x=embeddings[tokens:2*tokens][None].copy()
    refs,current=G.native_references(ROOT,payload,manifest,old_report,native,cold,next_x)
    R.require(current==identity,'reference runtime changed')
    cold_report['rms_same_input_audit']=audit_actual_rms(cold,payload,module)
    finish_phase(directory,cold,cold_refs,None,cold_report)
    print(json.dumps(dict(phase='cold',tokens=tokens,seconds=cold_report['wall_seconds'],
        failures={k:v['failed_stages'] for k,v in cold_report['evaluation']['methods'].items()})),flush=True)
    directory,carried,carried_report=execute_phase(out,build,payload,tokens,tokens,table_identity,shared,cold,cold_report)
    R.require(carried['x'].tobytes()==next_x.tobytes(),'carried raw input/reference identity changed')
    carried_report['rms_same_input_audit']=audit_actual_rms(carried,payload,module)
    finish_phase(directory,carried,refs,cold,carried_report)
    old_carried_name,old_carried_sha=D.RUNS['carried_m'+str(tokens)]
    old_carried_path=ROOT/'work'/old_carried_name/'RESULT.json'
    R.require(R.file_sha(old_carried_path)==old_carried_sha,'prior carried receipt changed')
    old_carried=json.loads(old_carried_path.read_text())
    result=dict(status=STATUS,policy=POLICY,tokens=tokens,build=build,**shared,table_identity=table_identity,
        phase_result_sha256={phase:R.file_sha(out/phase/'RESULT.json') for phase in ('cold','carried')},
        executions=dict(actual_cold=1,actual_carried=1,same_binary=True,separate_software_processes=True,
            carried_official_self_cache=1,carried_independent_self_cache=1,
            carried_official_actual_cache=1,carried_independent_actual_cache=1),
        prior_v1=dict(cold=dict(result_sha256=old_sha,evaluation=old_report['evaluation']),
                      carried=dict(result_sha256=old_carried_sha,evaluation=old_carried['evaluation'])),
        hardware_v0_conformant=False,policy_approval=False,rtl_executed=False,hardware_cycles=None,
        scope='One Qwen2-1.5B layer0, fixed raw IDs0..2M-1; software-only; numerical PASS/FAIL never policy acceptance')
    verify_sources(shared['source_files'])
    (out/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    validate_pair(out,R.file_sha(out/'RESULT.json'),tokens)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--tokens',type=int,choices=(16,128),required=True)
    p.add_argument('--payload',type=Path,default=ROOT/'work/qwen2_layer0_payload_20261011')
    p.add_argument('--small',type=Path);p.add_argument('--small-sha256')
    a=p.parse_args();result=run(a.out.resolve(),a.payload.resolve(),a.tokens,a.small.resolve() if a.small else None,a.small_sha256)
    print(json.dumps(dict(status=STATUS,policy_approval=False,tokens=a.tokens,result=str(a.out/'RESULT.json'))),flush=True)
    return 1


if __name__=='__main__':raise SystemExit(main())
