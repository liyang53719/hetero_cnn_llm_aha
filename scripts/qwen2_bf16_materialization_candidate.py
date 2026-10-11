#!/usr/bin/env python3
"""Versioned official-BF16 materialization DIAGNOSTIC, never hardware acceptance.

Preserves the committed mixed recipe and numerical thresholds. This candidate
adds eager BF16 materialization boundaries while retaining BF16 Matrix operands,
FP32 increasing-K FMA, current bias order, 16-part QK reduction and exp polynomial.
Its per-product BF16 RoPE differs from numerical_contract v0's FP32 pair rotation.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
def module(path: Path,name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise ValueError('module unavailable')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
R=module(ROOT/'scripts/qwen2_block_recipe_model.py','candidate_recipe')
N=module(ROOT/'scripts/qwen2_layer0_model_gate.py','candidate_native')
POLICY_ID='qwen2-official-bf16-materialization-v1-diagnostic'
CPP_SHA256='fa8e35755dfd17fb00c911b11b69d55b10cb5cc88002867a7484167d35320f79'
POLICY=dict(id=POLICY_ID,diagnostic_only=True,status='DIAGNOSTIC_NOT_ACCEPTED',hardware_v0_conformant=False,
    rope_difference='Official eager BF16 products round separately before BF16 sum; v0 specifies FP32 pair then BF16 output.',
    matrix='unchanged BF16 operands, FP32 accumulation; no vendor-specific reduction imitation',
    source='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py',
    softmax='Compare official BF16 forward internal FP32 softmax separately from materialized BF16 prob; no FP32 elementwise tolerance invented.')
# Each unique source substitution is reviewed and guarded. Any source drift fails.
PATCHES=[{'label': 'RMS normalized BF16 before gamma',
  'original': 'bf(mul(mul(get(in,size_t(t)*H+i),inv),get(gamma,i)))',
  'replacement': 'bf(mul(bf(mul(get(in,size_t(t)*H+i),inv)),get(gamma,i)))',
  'official_source': 'modeling_qwen2.py:85-90'},
 {'label': 'Dense output BF16 after unchanged bias order',
  'original': 'bias>=0?add(sums[j],get(bias,col+j)):sums[j]',
  'replacement': 'bf(bias>=0?add(sums[j],get(bias,col+j)):sums[j])',
  'official_source': 'modeling_qwen2.py:228-231,255-257,313; BF16 nn.Linear output'},
 {'label': 'RoPE table BF16 materialization',
  'original': 'c=get(OFF_COS,size_t(t)*HD/2+j),s=get(OFF_SIN,size_t(t)*HD/2+j)',
  'replacement': 'c=bf(get(OFF_COS,size_t(t)*HD/2+j)),s=bf(get(OFF_SIN,size_t(t)*HD/2+j))',
  'official_source': 'modeling_qwen2.py:119-126'},
 {'label': 'RoPE BF16 products then BF16 sum',
  'original': 'put(out,ix,add(mul(x,c),-mul(y,s)));put(out,ix+HD/2,add(mul(x,s),mul(y,c)));',
  'replacement': 'put(out,ix,bf(add(bf(mul(x,c)),-bf(mul(y,s)))));put(out,ix+HD/2,bf(add(bf(mul(x,s)),bf(mul(y,c)))));',
  'official_source': 'modeling_qwen2.py:162-163'},
 {'label': 'QK BF16 dot result then BF16 scaled result',
  'original': 'p[k]=mul(sum,float(1.0/std::sqrt(double(HD))));max=std::max(max,p[k]);',
  'replacement': 'p[k]=bf(mul(bf(sum),float(1.0/std::sqrt(double(HD)))));candidateScores[(size_t(h)*tokens+t)*tokens+k]=p[k];candidateLogits[(size_t(h)*tokens+t)*tokens+k]=k<=t?p[k]:fp(0xff7f0000u);if(k<=t)max=std::max(max,p[k]);',
  'official_source': 'modeling_qwen2.py:283'},
 {'label': 'PV output BF16 after unchanged FP32 accumulation',
  'original': 'put(OFF_ATT,size_t(t)*H+h*HD+j,sum);',
  'replacement': 'put(OFF_ATT,size_t(t)*H+h*HD+j,bf(sum));',
  'official_source': 'modeling_qwen2.py:302'},
 {'label': 'Attention residual BF16',
  'original': 'put(OFF_R,i,add(get(OFF_X,i),get(OFF_O,i)))',
  'replacement': 'put(OFF_R,i,bf(add(get(OFF_X,i),get(OFF_O,i))))',
  'official_source': 'modeling_qwen2.py:776'},
 {'label': 'SiLU output BF16 then product BF16',
  'original': 'put(OFF_ACT,i,mul(mul(sig,g),get(OFF_UP,i)))',
  'replacement': 'candidateSilu[i]=bf(mul(sig,g));put(OFF_ACT,i,bf(mul(candidateSilu[i],get(OFF_UP,i))))',
  'official_source': 'modeling_qwen2.py:179-180'},
 {'label': 'Final residual BF16',
  'original': 'put(OFF_Y,i,add(get(OFF_R,i),get(OFF_DOWN,i)))',
  'replacement': 'put(OFF_Y,i,bf(add(get(OFF_R,i),get(OFF_DOWN,i))))',
  'official_source': 'modeling_qwen2.py:782'},
 {'label': 'Additional software diagnostic buffers',
  'original': '  std::vector<float> reference; unsigned tokens;',
  'replacement': '  std::vector<float> reference; unsigned tokens;\n'
                 '  std::vector<float> candidateScores,candidateLogits,candidateSoftmax,candidateProb,candidateSilu;',
  'official_source': 'diagnostic_only_not_hardware'},
 {'label': 'Attention observer allocation',
  'original': 'void attention(){std::vector<float> p(tokens);',
  'replacement': 'void '
                 'attention(){candidateScores.resize(size_t(HEADS)*tokens*tokens);candidateLogits.resize(candidateScores.size());candidateSoftmax.assign(candidateScores.size(),0);candidateProb.assign(candidateScores.size(),0);std::vector<float> '
                 'p(tokens);',
  'official_source': 'diagnostic_only_not_hardware'},
 {'label': 'Observe masked-future score values without consuming them',
  'original': 'for(unsigned k=0;k<=t;k++){float parts[16]={};',
  'replacement': 'for(unsigned k=0;k<tokens;k++){float parts[16]={};',
  'official_source': 'diagnostic_only_not_hardware'},
 {'label': 'Observe FP32 softmax and BF16 probability',
  'original': 'float inv=1.0f/sum;\n    for(int j=0;j<HD;j++)',
  'replacement': 'float inv=1.0f/sum;\n'
                 '    for(unsigned '
                 'k=0;k<=t;k++){candidateSoftmax[(size_t(h)*tokens+t)*tokens+k]=mul(p[k],inv);candidateProb[(size_t(h)*tokens+t)*tokens+k]=bf(mul(p[k],inv));}\n'
                 '    for(int j=0;j<HD;j++)',
  'official_source': 'diagnostic_only_not_hardware'},
 {'label': 'Observe SiLU materialization',
  'original': '  void computeReference(){',
  'replacement': '  void computeReference(){candidateSilu.resize(size_t(tokens)*F);',
  'official_source': 'diagnostic_only_not_hardware'},
 {'label': 'Export diagnostic tensors',
  'original': '  model.computeReference();',
  'replacement': '  model.computeReference();\n'
                 '  auto dump=[&](const char* name,const std::vector<float>& values){std::ofstream '
                 'f(std::filesystem::path(argv[3])/(std::string(name)+".f32le"),std::ios::binary);f.write(reinterpret_cast<const '
                 'char*>(values.data()),values.size()*4);need(bool(f),"candidate diagnostic write failed");};\n'
                 '  '
                 'dump("scores",model.candidateScores);dump("logits",model.candidateLogits);dump("softmax_fp32",model.candidateSoftmax);dump("prob",model.candidateProb);dump("silu",model.candidateSilu);',
  'official_source': 'diagnostic_only_not_hardware'}]


def candidate_source(root: Path) -> tuple[str,dict]:
    helpers,maths,identity=R.extract_sources(root)
    source='// Ordinary C++ software numerical model; not a hardware simulator.\n'+helpers+R.HOST_PROBES+R.DRIVER+maths+R.MAIN
    source=apply_patches(source)
    R.require(R.sha(source.encode())==CPP_SHA256,'candidate source identity changed; versioned review required')
    return source,identity


def apply_patches(source: str) -> str:
    for patch in PATCHES:
        R.require(source.count(patch['original'])==1,'candidate patch boundary absent/ambiguous: '+patch['label'])
        source=source.replace(patch['original'],patch['replacement'])
    return '// WORK-ONLY CANDIDATE. Not the frozen canonical recipe or implemented hardware.\n'+source


def prepare(root: Path,out: Path,shape: dict | None=None,compile_binary: bool=True) -> dict:
    R.require(not out.exists(),'refuse existing candidate directory')
    source,identity=candidate_source(root);layout=R.make_layout(shape)
    out.mkdir(parents=True);(out/'candidate.cpp').write_text(source);(out/'block_layout.h').write_text(R.header(layout))
    (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    compiler=shutil.which('g++');R.require(compiler is not None,'ordinary g++ required')
    command=[compiler,*R.FLAGS,str(out/'candidate.cpp'),'-o',str(out/'candidate')]
    if compile_binary:
        build=subprocess.run(command,capture_output=True,text=True,timeout=120)
        (out/'build.log').write_text(build.stdout+build.stderr);R.require(build.returncode==0,'candidate compile failed')
    return dict(source_identity=identity,layout=layout,compile_command=command,compiled_now=compile_binary,
                candidate_cpp_sha256=R.file_sha(out/'candidate.cpp'),header_sha256=R.file_sha(out/'block_layout.h'))


def load_actual(stages: Path,arena_path: Path,input_path: Path,layout: dict,tokens: int) -> dict:
    h,f,heads,kvheads,d=(layout[k] for k in ('hidden','ffn','heads','kv_heads','head_dim'))
    widths=(h,h,kvheads*d,kvheads*d,h,kvheads*d,h,h,h,h,f,f,f,h,h)
    result={}
    def read(path: Path,shape):
        R.require(path.stat().st_size==int(np.prod(shape))*4,'candidate tensor byte length mismatch')
        a=np.fromfile(path,dtype='<f4').reshape(shape);R.require(bool(np.isfinite(a).all()),'nonfinite candidate tensor');return a
    for i,(name,width) in enumerate(zip(R.STAGE_NAMES,widths)):
        a=read(stages/f'phase_{i}_{name}_recipe.f32le',(1,tokens,width))
        if name in ('q','k'):a=a.reshape(1,tokens,heads if name=='q' else kvheads,d).transpose(0,2,1,3).copy()
        result[name]=a
    for name in ('scores','logits','softmax_fp32','prob','silu'):
        shape=(1,tokens,f) if name=='silu' else (1,heads,tokens,tokens)
        result[name]=read(stages/(name+'.f32le'),shape)
    result['cache_k']=result['k'].copy()
    result['cache_v']=result['v'].reshape(1,tokens,kvheads,d).transpose(0,2,1,3).copy()
    result['repeat_k']=np.repeat(result['cache_k'],heads//kvheads,axis=1)
    result['repeat_v']=np.repeat(result['cache_v'],heads//kvheads,axis=1)
    result['pv']=result['att'].reshape(1,tokens,heads,d).transpose(0,2,1,3).copy()
    result['mask']=N.causal_mask(tokens,0,'bf16');result['x']=read(input_path,(1,tokens,h))
    regions={entry['name']:entry for entry in layout['regions']};arena=np.memmap(arena_path,dtype='<f4',mode='r')
    for name in ('cos','sin'):
        off=regions[name]['offset']//4;a=N.bf16(arena[off:off+tokens*d//2].reshape(tokens,d//2).copy())
        result[name]=np.concatenate((a,a),axis=1)
    validate_dtypes(result)
    return result



def validate_dtypes(actual: dict) -> None:
    R.require(set(actual)==N.REQUIRED_STAGES,'candidate 29-node inventory mismatch')
    for name,value in actual.items():
        R.require(value.dtype==np.dtype('<f4') and bool(np.isfinite(value).all()),'candidate dtype/nonfinite mismatch: '+name)
        if name!='softmax_fp32':
            R.require(not bool(np.any(value.view('<u4') & 0xffff)),'candidate node is not BF16-representable: '+name)

def compare_nodes(root: Path,actual: dict,native_dir: Path,native: dict,tokens: int) -> dict:
    validate_dtypes(actual)
    policy=N.load_policy(root);comparisons={}
    for kind in ('native','independent'):
        entries=[]
        for name in sorted(N.REQUIRED_STAGES):
            entry=native['modes']['bf16']['phases'][0]['stages'][name]
            ref=np.fromfile(native_dir/entry[kind+'_file'],dtype='<f4').reshape(entry[kind+'_export_shape'])
            a=N.export_value(actual[name],name);metrics=N.compare(a,ref)
            error=np.abs(a.astype(np.float64)-ref.astype(np.float64));ix=np.unravel_index(np.argmax(error),error.shape)
            entries.append(dict(name=name,metrics=metrics,verdict=N.stage_verdict(name,metrics,'bf16',policy),
                max_abs_coordinate=list(map(int,ix)),candidate_at_max=float(a[ix]),reference_at_max=float(ref[ix])))
        comparisons[kind]=entries
    config=json.loads((root/N.SOURCE/'config.json').read_text())
    semantics=N.audit_semantics(actual,None,config,'bf16')
    row_error=float(np.max(np.abs(actual['softmax_fp32'].sum(axis=-1,dtype=np.float32)-1)))
    return dict(comparisons=comparisons,semantics=semantics,threshold_policy=policy,
        softmax_fp32=dict(reference='official BF16 eager internal FP32 softmax, not official FP32-mode attention',
            elementwise_tolerance=None,max_row_sum_error=row_error,row_sum_limit=2e-5,passed_row_sum_contract=row_error<=2e-5),
        node_gates_pass={kind:all(e['verdict']['passed'] is not False for e in entries) and all(semantics.values()) and row_error<=2e-5
                        for kind,entries in comparisons.items()})


def export_actual(actual: dict,out: Path) -> list[dict]:
    records=[]
    for name in sorted(N.REQUIRED_STAGES):
        a=N.export_value(actual[name],name);path=out/f'candidate_{name}.f32le';a.tofile(path)
        records.append(dict(name=name,path=path.name,shape=list(actual[name].shape),export_shape=list(a.shape),sha256=R.file_sha(path)))
    return records


def load_exports(directory: Path,records: list[dict],tokens: int) -> dict:
    expected=N.expected_shapes(dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2),tokens,0)
    R.require([r['name'] for r in records]==sorted(N.REQUIRED_STAGES),'candidate artifact inventory/order mismatch')
    result={}
    for entry in records:
        name=entry['name'];path=directory/f'candidate_{name}.f32le'
        R.require(entry['path']==path.name and entry['shape']==expected[name] and not path.is_symlink()
                  and R.file_sha(path)==entry['sha256'],'candidate export identity mismatch')
        a=np.fromfile(path,dtype='<f4');R.require(a.size==int(np.prod(expected[name])),'candidate export size mismatch')
        if name in N.EXPORT_TOKEN_MAJOR:
            b,h,t,d=expected[name];shape=[b,t,h*d];a=a.reshape(b,t,h,d).transpose(0,2,1,3).copy()
        else:shape=expected[name];a=a.reshape(shape)
        R.require(entry['export_shape']==shape and bool(np.isfinite(a).all()),'candidate export layout/nonfinite mismatch')
        result[name]=a
    validate_dtypes(result)
    return result


def validate_small(root: Path,path: Path,recipe: dict,recipe_dir: Path) -> None:
    report=json.loads((path/'RESULT.json').read_text())
    R.require(report['policy']==POLICY and report['tokens']==16 and report['generator_sha256']==R.file_sha(Path(__file__))
              and report['candidate_cpp_sha256']==CPP_SHA256,'candidate M16 source/policy mismatch')
    R.require(R.file_sha(path/'candidate.cpp')==CPP_SHA256 and R.file_sha(path/'candidate')==report['candidate_binary_sha256']
              and R.file_sha(path/'block_layout.h')==report['header_sha256'],'candidate M16 generated artifact changed')
    R.require(R.file_sha(Path(report['recipe_directory'])/'RESULT.json')==report['recipe_result_sha256'],'candidate M16 recipe receipt changed')
    prior_recipe=R.validate_recipe_receipt(root,Path(report['recipe_directory']))
    R.require(prior_recipe['checkpoint_manifest_sha256']==recipe['checkpoint_manifest_sha256'],'candidate M16 payload mismatch')
    native_dir=Path(report['native_directory']);native=R.validate_native_receipt(root,native_dir,prior_recipe)
    R.require(R.file_sha(native_dir/'RESULT.json')==report['native_result_sha256'],'candidate M16 native receipt changed')
    actual=load_exports(path/'tensors',report['tensors'],16)
    actual=validate_raw_evidence(report,path,Path(report['recipe_directory']),R.make_layout(),16,actual)
    R.require(actual['x'].tobytes()==(recipe_dir/'input_x.f32le').read_bytes()[:16*1536*4],'candidate M16 input prefix differs')
    evaluation=compare_nodes(root,actual,native_dir,native,16)
    R.require(evaluation==report['evaluation'] and all(evaluation['node_gates_pass'].values()),'candidate M16 gates stale/failed')



def bind_raw_outputs(primary: dict,stages: Path,recipe_dir: Path,layout: dict,tokens: int,exports: dict) -> dict:
    """Rebuild derived exports from the actual ELF outputs, never trust edits."""
    entries=primary['comparisons']['native'];by_name={e['name']:e for e in entries}
    R.require(len(by_name)==len(entries),'duplicate original observation stage')
    for name in (*R.STAGE_NAMES,'scores','logits','softmax_fp32','prob','silu'):
        R.require(name in by_name,'original raw observation stage missing')
        path=stages/(f'phase_{R.STAGE_NAMES.index(name)}_{name}_recipe.f32le' if name in R.STAGE_NAMES else name+'.f32le')
        expected=by_name[name].get('sha256',by_name[name].get('candidate_sha256'))
        R.require(not path.is_symlink() and R.file_sha(path)==expected,'original raw observation output changed')
    rebuilt=load_actual(stages,recipe_dir/'readonly_arena.f32le',recipe_dir/'input_x.f32le',layout,tokens)
    for name in sorted(N.REQUIRED_STAGES):
        R.require(N.export_value(rebuilt[name],name).tobytes()==N.export_value(exports[name],name).tobytes(),
                  'observation export differs from actual raw candidate output: '+name)
    return rebuilt


def raw_inventory(stages: Path) -> list[dict]:
    records=[]
    for name in (*R.STAGE_NAMES,'scores','logits','softmax_fp32','prob','silu'):
        filename=f'phase_{R.STAGE_NAMES.index(name)}_{name}_recipe.f32le' if name in R.STAGE_NAMES else name+'.f32le'
        records.append(dict(name=name,path=filename,sha256=R.file_sha(stages/filename)))
    return records


def validate_raw_evidence(report: dict,directory: Path,recipe_dir: Path,layout: dict,tokens: int,exports: dict) -> dict:
    """Keep the execution-to-export binding when admitting a later M128 run."""
    adoption=report['adoption']
    if adoption is not None:
        observation=Path(adoption['observation_directory']);primary_path=observation/'RESULT.json'
        R.require(R.file_sha(primary_path)==adoption['primary_report_sha256'],'adopted primary receipt changed')
        complete_path=observation/'FULL_NODE_CHECK.json'
        if adoption['complete_report_sha256'] is not None:
            R.require(R.file_sha(complete_path)==adoption['complete_report_sha256'],'adopted complete receipt changed')
        else:
            R.require(not complete_path.exists(),'unexpected adopted complete receipt')
        primary=json.loads(primary_path.read_text());stages=observation/'stages'
    else:
        stages=directory/'raw_stages'
        primary={'comparisons':{'native':report['raw_outputs']}}
    R.require(raw_inventory(stages)==report['raw_outputs'],'candidate raw evidence changed')
    return bind_raw_outputs(primary,stages,recipe_dir,layout,tokens,exports)

def adopt(root: Path,observation: Path,binary: Path,out: Path,recipe_dir: Path,native_dir: Path,tokens: int) -> dict:
    original_build=json.loads((binary.parent/'RESULT.json').read_text())
    R.require(original_build['compile_command'][1:5]==R.FLAGS and original_build['candidate_cpp_sha256']==CPP_SHA256
              and original_build['candidate_binary_sha256']==R.file_sha(binary),'observation compiler/source identity mismatch')
    primary=json.loads((observation/'RESULT.json').read_text())
    complete_path=observation/'FULL_NODE_CHECK.json'
    report=json.loads(complete_path.read_text()) if complete_path.exists() else primary
    R.require(report['tokens']==tokens and report['candidate_cpp_sha256']==CPP_SHA256
              and report['candidate_binary_sha256']==R.file_sha(binary),'observation candidate source/binary mismatch')
    R.require(R.file_sha(binary.with_suffix('.cpp'))==CPP_SHA256,'observation C++ changed')
    R.require(R.file_sha(binary.parent/'block_layout.h')==R.file_sha(out/'block_layout.h'),'observation layout differs')
    R.require(report['canonical_result_sha256']==R.file_sha(recipe_dir/'RESULT.json')
              and report['native_result_sha256']==R.file_sha(native_dir/'RESULT.json'),'observation source receipt mismatch')
    if complete_path.exists():
        R.require(report['candidate_result_sha256']==R.file_sha(observation/'RESULT.json'),'observation full-node receipt changed')
    R.require(primary.get('retains_dense_increasing_K_FMA') is True and primary.get('retains_original_FP32_bias_order') is True,'observation numerical scope mismatch')
    for kind in ('native','independent'):
        R.require({e['name'] for e in report['comparisons'][kind]}==N.REQUIRED_STAGES,'observation incomplete node inventory')
    records=[]
    for entry in sorted(report['comparisons']['native'],key=lambda e:e['name']):
        name=entry['name'];p=observation/'stages'/f'candidate_{name}.f32le'
        R.require(R.file_sha(p)==entry['candidate_sha256'],'observation tensor changed')
        expected=N.expected_shapes(dict(hidden_size=1536,intermediate_size=8960,num_attention_heads=12,num_key_value_heads=2),tokens,0)[name]
        records.append(dict(name=name,path=p.name,shape=expected,export_shape=entry['metrics']['shape'],sha256=entry['candidate_sha256']))
    actual=load_exports(observation/'stages',records,tokens)
    actual=bind_raw_outputs(primary,observation/'stages',recipe_dir,R.make_layout(),tokens,actual)
    shutil.copyfile(binary,out/'candidate')
    return dict(actual=actual,adoption=dict(observation_directory=str(observation.resolve()),
        primary_report_sha256=R.file_sha(observation/'RESULT.json'),complete_report_sha256=R.file_sha(complete_path) if complete_path.exists() else None,
        candidate_binary_sha256=R.file_sha(binary),numerical_execution_repeated=False))


def run(root: Path,recipe_dir: Path,native_dir: Path,out: Path,small_candidate: Path | None=None,
        observation: Path | None=None,observed_binary: Path | None=None,timeout_seconds: float=120) -> dict:
    root=root.resolve();recipe_dir=recipe_dir.resolve();native_dir=native_dir.resolve();out=out.resolve()
    recipe=R.validate_recipe_receipt(root,recipe_dir);native=R.validate_native_receipt(root,native_dir,recipe)
    tokens=recipe['shape']['tokens'];R.require(tokens in (16,128),'candidate supports cold M16/M128 only')
    R.require(0<timeout_seconds<=600,'candidate timeout outside bounded local budget')
    if tokens==128:
        R.require(small_candidate is not None,'M128 candidate requires complete M16 candidate gate')
        validate_small(root,small_candidate,recipe,recipe_dir)
    R.require((observation is None)==(observed_binary is None),'adoption requires both observation and binary')
    provenance=prepare(root,out,compile_binary=observation is None);adoption=None;elapsed=None
    if observation is not None:
        adopted=adopt(root,observation,observed_binary,out,recipe_dir,native_dir,tokens)
        actual=adopted['actual'];adoption=adopted['adoption'];stages=observation/'stages'
    else:
        stages=out/'raw_stages';stages.mkdir();start=time.monotonic()
        execution=subprocess.run([str(out/'candidate'),str(recipe_dir/'readonly_arena.f32le'),str(tokens),str(stages)],
            capture_output=True,text=True,timeout=timeout_seconds)
        elapsed=time.monotonic()-start;(out/'run.log').write_text(execution.stdout+execution.stderr)
        R.require(execution.returncode==0 and execution.stdout.count('SOFTWARE_RECIPE_STAGE ')==15
                  and 'SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10' in execution.stdout,'candidate execution incomplete')
        R.require(R.file_sha(recipe_dir/'readonly_arena.f32le')==recipe['input']['readonly_sha256'],'candidate readonly arena changed')
        actual=load_actual(stages,recipe_dir/'readonly_arena.f32le',recipe_dir/'input_x.f32le',provenance['layout'],tokens)
    R.require(actual['x'].tobytes()==(recipe_dir/'input_x.f32le').read_bytes(),'candidate input differs from pinned recipe input')
    tensors=out/'tensors';tensors.mkdir();records=export_actual(actual,tensors)
    result=dict(schema=1,status='DIAGNOSTIC_NOT_ACCEPTED',policy=POLICY,tokens=tokens,**provenance,
        generator_sha256=R.file_sha(Path(__file__)),candidate_binary_sha256=R.file_sha(out/'candidate'),
        recipe_directory=str(recipe_dir),recipe_result_sha256=R.file_sha(recipe_dir/'RESULT.json'),
        native_directory=str(native_dir),native_result_sha256=R.file_sha(native_dir/'RESULT.json'),
        small_candidate_result_sha256=R.file_sha(small_candidate/'RESULT.json') if small_candidate else None,
        tensors=records,raw_outputs=raw_inventory(stages),evaluation=compare_nodes(root,actual,native_dir,native,tokens),adoption=adoption,wall_seconds=elapsed,
        derived_nodes=['x','cos','sin','mask','cache_k','cache_v','repeat_k','repeat_v','pv'],
        scope=dict(rtl_executed=False,hardware_implemented=False,hardware_v0_conformant=False,official_framework_forward=False,
                   consumes_own_previous_stages=True,extra_masked_future_scores='software observers only'),
        hardware_cycles=None,hardware_utilization=None)
    (out/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--recipe-run',type=Path,required=True)
    p.add_argument('--native-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--small-candidate',type=Path);p.add_argument('--adopt-observation',type=Path)
    p.add_argument('--observed-binary',type=Path);p.add_argument('--timeout-seconds',type=float,default=120)
    a=p.parse_args();r=run(a.root,a.recipe_run,a.native_run,a.out,a.small_candidate,a.adopt_observation,a.observed_binary,a.timeout_seconds)
    print(json.dumps(dict(status=r['status'],tokens=r['tokens'],node_gates_pass=r['evaluation']['node_gates_pass'],result=str(a.out/'RESULT.json')),indent=2))
    return 1 # Diagnostic policy never signals hardware acceptance.

if __name__=='__main__':raise SystemExit(main())
