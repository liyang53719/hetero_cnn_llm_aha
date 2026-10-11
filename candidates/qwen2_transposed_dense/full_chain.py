#!/usr/bin/env python3
"""Prepare or explicitly execute the frozen 15-stage software-only comparison.

Preparation never executes official-shaped arithmetic. Execution refuses M128
without the same prepared binary's complete bit-exact M16 result. No downloads.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('transposed_comparison',HERE/'compare.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
D,R,ROOT=C.D,C.R,C.ROOT
R.require(__debug__,'optimized Python (-O) is unsupported; validation assertions are required')
ARENA_SHA='c34bcef98ca05d3c05087559741152082492b40fa6b74e072a1dec589c964a69'
OUTPUT_ROOT=GENERATED=MANIFEST=None


def configure(out):
    global OUTPUT_ROOT,GENERATED,MANIFEST
    OUTPUT_ROOT=Path(out).resolve()
    R.require(OUTPUT_ROOT!=HERE and HERE not in OUTPUT_ROOT.parents,'outputs must be outside candidate source directory')
    GENERATED=OUTPUT_ROOT/'generated';MANIFEST=GENERATED/'PREPARED.json'


def new_source():
    C.verify_algorithm_sources()
    original,identity=D.resident_source(ROOT,rectangular_attention=True)
    body=(HERE/'transposed_dense.inc.cpp').read_text()
    start=body.index('{',body.index('  void transposed('))+1
    dense='\n    const bool rmw=true; const int aChunk=2560;\n'+body[start:body.rfind('  }')]
    assert original.count(D.DENSE_BODY)==1
    support=D.NUMERIC_ATT.CPP_SUPPORT
    mapped=support
    replacements={
      'uint16_t ac[16][1024][16], b[16][512][16];':'uint16_t ac[16][1376][16], b[16][160][16];',
      'base<=1024 && 5*32<=512':'base<=1376 && 5*32<=160',
      'depth=o.inB?512:1024':'depth=o.inB?160:1376',
      'sizeof(RectangularAttentionStorage::ac)==524288 && sizeof(RectangularAttentionStorage::b)==262144':
      'sizeof(RectangularAttentionStorage::ac)==704512 && sizeof(RectangularAttentionStorage::b)==81920',
    }
    for old,new in replacements.items():
        assert mapped.count(old)==1,old
        mapped=mapped.replace(old,new)
    assert original.count(support)==1
    source=original.replace(D.DENSE_BODY,dense).replace(support,mapped)
    assert source.replace(dense,D.DENSE_BODY).replace(mapped,support)==original
    assert D.NUMERIC_ATT.ATTENTION_BODY in source
    return source,dict(base_recipe_identity=identity,
        actual_mapping='transposed_m128_n32_a688_b80_retained_fullk',
        original_mapping='resident_m128_nc3_with_rectangular_attention',
        transposed_body_sha256=C.sha(HERE/'transposed_dense.inc.cpp'),
        inserted_dense_sha256=R.sha(dense.encode()),original_support_sha256=R.sha(support.encode()),
        mapped_support_sha256=R.sha(mapped.encode()),unchanged_attention_body_sha256=R.sha(D.NUMERIC_ATT.ATTENTION_BODY.encode()),
        support_capacity_replacements=replacements,
        body_only_replacement_plus_support_capacity_patch=True)


def checked_hash(path,expected):
    R.require(Path(path).is_file() and C.sha(Path(path))==expected,'missing/changed evidence: '+str(path))


def verify_stages(directory,stages,tokens):
    layout=R.make_layout()
    R.require(len(stages)==15,'incomplete stage receipt')
    for phase,(name,stage) in enumerate(zip(R.STAGE_NAMES,stages)):
        expected=f'phase_{phase}_{name}_recipe.f32le'
        width=next(r['words']//128 for r in layout['regions'] if r['name']==name)
        R.require(stage['phase']==phase and stage['name']==name and stage['path']==expected and stage['width']==width,
                  'stage shape/order/path changed')
        path=Path(directory)/expected;checked_hash(path,stage['sha256'])
        R.require(path.stat().st_size==tokens*width*4,'stage byte count changed')
        R.require(bool(R.np.isfinite(R.np.fromfile(path,dtype='<f4')).all()),'nonfinite saved stage')


def verify_baselines(root,identity):
    root=Path(root).resolve();baselines={}
    for tokens in (16,128):
        directory=root/f'm{tokens}';path=directory/'RESULT.json';receipt=json.loads(path.read_text())
        R.require(receipt['shape']==dict(R.SHAPE,tokens=tokens),'baseline shape differs')
        R.require(receipt['readonly_sha256']==ARENA_SHA and receipt['completion_status']=='ALL_15_SOFTWARE_STAGES_COMPLETE',
                  'baseline input/completion differs')
        old=receipt['source_identity'];base=identity['base_recipe_identity']
        for key in ('section_sha256','source_pass_reference_commit','source_pass_cpp_sha256'):
            R.require(old[key]==base[key],'baseline canonical source differs: '+key)
        R.require(old['resident_attention_body_sha256']==identity['unchanged_attention_body_sha256'] and old['rectangular_attention'],
                  'baseline Attention differs')
        R.require(old['compile_command'][1:5]==R.FLAGS,'baseline compiler flags differ')
        artifacts={'software_recipe.cpp':old['generated_cpp_sha256'],
                   'block_layout.h':old['generated_header_sha256'],'software_recipe':old['binary_sha256']}
        for file,sha in artifacts.items():checked_hash(root/'generated'/file,sha)
        checked_hash(directory/'run.log',receipt['run_log_sha256']);verify_stages(directory,receipt['stages'],tokens)
        baselines[str(tokens)]=dict(directory=str(directory),result_sha256=C.sha(path),
            source_artifacts=artifacts,run_log_sha256=receipt['run_log_sha256'],stages=receipt['stages'])
    return baselines


def verify_small(path):
    path=Path(path).resolve();small=json.loads(path.read_text());numeric=small['numeric']
    R.require(isinstance(numeric,dict) and numeric['mapped_runs']==20 and numeric['bit_mismatches']==0 and len(numeric['cases'])==10,
              'full bounded small prerequisite required; tiny packaging check is insufficient')
    pins=small['source_sha256']
    R.require([v for k,v in pins.items() if Path(k).name=='transposed_dense.inc.cpp']==[C.ALGORITHM_SHA256] and
              [v for k,v in pins.items() if Path(k).name=='small_tests.inc.cpp']==[C.SMALL_CASES_SHA256],
              'small prerequisite algorithm/cases differ')
    for key,file in [('generated_cpp_sha256','small_comparison.cpp'),('binary_sha256','small_comparison'),('log_sha256','run.log')]:
        checked_hash(path.parent/'generated'/file,numeric[key])
    return dict(path=str(path),sha256=C.sha(path),algorithm_sha256=C.ALGORITHM_SHA256,
                scope='saved exact-algorithm small suite; no refactored-driver full run implied')


def prepare(out,baseline_root,arena,small_receipt):
    out=C.output_directory(out);configure(out);arena=Path(arena).resolve()
    layout=R.make_layout()
    assert arena.stat().st_size==188043264==layout['writable_start']
    assert R.file_sha(arena)==ARENA_SHA,'sealed arena differs'
    small=verify_small(small_receipt)
    source,identity=new_source()
    baselines=verify_baselines(baseline_root,identity)
    GENERATED.mkdir(parents=True)
    (GENERATED/'software_recipe.cpp').write_text(source)
    (GENERATED/'block_layout.h').write_text(R.header(layout))
    (GENERATED/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    command=[shutil.which('g++'),*R.FLAGS,str(GENERATED/'software_recipe.cpp'),'-o',str(GENERATED/'software_recipe')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=90)
    (GENERATED/'build.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stderr
    prepared=dict(status='PREPARED_NOT_EXECUTED',software_only=True,official_framework_forward=False,
        parameters=dict(shape=R.SHAPE,rmw=True,a_chunk=2560,b_chunk=128,a_bank_words=1376,b_bank_words=160),
        arena=str(arena.resolve()),arena_bytes=arena.stat().st_size,arena_sha256=ARENA_SHA,
        source_identity=identity,source_sha256=C.sha(GENERATED/'software_recipe.cpp'),
        header_sha256=C.sha(GENERATED/'block_layout.h'),layout_sha256=C.sha(GENERATED/'layout.json'),
        binary_sha256=C.sha(GENERATED/'software_recipe'),runner_sha256=C.sha(Path(__file__)),
        comparison_driver_sha256=C.sha(HERE/'compare.py'),small_prerequisite=small,
        baseline_root=str(Path(baseline_root).resolve()),historical_work_full_runs_rebound=False,
        compile_command=command,baselines=baselines,
        gates_unchanged='native M128 FAIL_BF16_STAGE_BUDGET and existing FP32 final failure remain',
        run_order=[16,128],hardware_cycles=None,hardware_acceptance=False)
    MANIFEST.write_text(json.dumps(prepared,indent=2)+'\n')
    return dict(status=prepared['status'],manifest=str(MANIFEST),manifest_sha256=C.sha(MANIFEST))


def validate(out):
    configure(out)
    p=json.loads(MANIFEST.read_text())
    source,identity=new_source()
    assert R.sha(source.encode())==p['source_sha256']==C.sha(GENERATED/'software_recipe.cpp')
    # git HEAD is bookkeeping; current guarded sources and all generated files
    # must match even if an unrelated parent commit was published meanwhile.
    current=dict(identity);frozen=dict(p['source_identity'])
    for item in (current,frozen):
        item['base_recipe_identity']={k:v for k,v in item['base_recipe_identity'].items() if k!='git_head'}
    assert current==frozen
    for key,file in [('header_sha256','block_layout.h'),('layout_sha256','layout.json'),('binary_sha256','software_recipe')]:
        assert C.sha(GENERATED/file)==p[key]
    assert C.sha(Path(__file__))==p['runner_sha256'] and C.sha(HERE/'compare.py')==p['comparison_driver_sha256']
    R.require(p['parameters']==dict(shape=R.SHAPE,rmw=True,a_chunk=2560,b_chunk=128,a_bank_words=1376,b_bank_words=160),
              'prepared parameters changed')
    R.require(verify_small(p['small_prerequisite']['path'])==p['small_prerequisite'],'small prerequisite changed')
    R.require(verify_baselines(p['baseline_root'],identity)==p['baselines'],'baseline evidence changed')
    assert C.sha(Path(p['arena']))==p['arena_sha256']==ARENA_SHA
    R.require(Path(p['arena']).stat().st_size==p['arena_bytes']==188043264,'prepared input size changed')
    return p


def verify_m16(out,prepared_sha,baseline_stages):
    directory=Path(out)/'m16';r=json.loads((directory/'RESULT.json').read_text())
    R.require(r['tokens']==16 and r['shape']==dict(R.SHAPE,tokens=16) and
              r['all_15_stages_bit_exact'] and r['completion_status']=='ALL_15_SOFTWARE_STAGES_COMPLETE' and
              r['prepared_sha256']==prepared_sha and r['arena_sha256']==ARENA_SHA,'M16 prerequisite differs')
    R.require(r['stages']==baseline_stages,'M16 stage receipt differs from frozen baseline')
    checked_hash(directory/'run.log',r['run_log_sha256']);verify_stages(directory,r['stages'],16)


def execute(out,tokens):
    R.require(tokens in (16,128),'only M16/M128 supported')
    p=validate(out)
    output=OUTPUT_ROOT/f'm{tokens}'
    assert not output.exists(),'refuse duplicate official-shaped run'
    if tokens==128:
        verify_m16(OUTPUT_ROOT,C.sha(MANIFEST),p['baselines']['16']['stages'])
    baseline=p['baselines'][str(tokens)]
    assert C.sha(Path(baseline['directory'])/'RESULT.json')==baseline['result_sha256']
    # Hash and validate all comparison-only files before any new arithmetic.
    for stage in baseline['stages']:
        path=Path(baseline['directory'])/stage['path']
        assert C.sha(path)==stage['sha256']
    output.mkdir()
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
    try:
        elapsed=R.execute(GENERATED,Path(p['arena']),tokens,output,timeout_seconds=180)
    except RuntimeError as error:
        cause=error.__cause__
        if isinstance(cause,subprocess.TimeoutExpired):
            def text(x):return x.decode(errors='replace') if isinstance(x,bytes) else (x or '')
            with (output/'run.log').open('a') as log:log.write(text(cause.stdout)+text(cause.stderr))
        raise
    assert C.sha(Path(p['arena']))==ARENA_SHA
    log=(output/'run.log').read_text()
    assert 'SOFTWARE_RECIPE_COMPLETE tokens='+str(tokens)+' stages=15' in log
    dense=[dict(re.findall(r'(\w+)=([^ ]+)',line)) for line in log.splitlines() if line.startswith('TRANSPOSED_CASE ')]
    assert len(dense)==7
    for row,(name,k,n) in zip(dense,C.S.BOUND.MATRICES):
        assert int(row['m'])==tokens and int(row['k'])==k and int(row['n'])==n
        assert int(row['rmw'])==1 and int(row['a_chunk'])==2560
        assert int(row['a_values'])==tokens*k*(1 if k<=2560 else (n+159)//160)
        assert int(row['w_values'])==k*n and int(row['issues'])==k*((n+31)//32)
    D.parse_attention_log(log,R.make_layout(),tokens,True)
    stages=[]
    for expected in baseline['stages']:
        path=output/expected['path'];reference=Path(baseline['directory'])/expected['path']
        assert path.stat().st_size==reference.stat().st_size
        assert path.read_bytes()==reference.read_bytes(),'v0-equivalent saved stage mismatch: '+expected['name']
        assert bool(R.np.isfinite(R.np.fromfile(path,dtype='<f4')).all())
        stages.append(dict(expected,sha256=C.sha(path)))
    verify_stages(output,stages,tokens)
    result=dict(status='MODEL_ONLY_DIAGNOSTIC_NOT_ACCEPTED',tokens=tokens,shape=dict(R.SHAPE,tokens=tokens),
        completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',all_15_stages_bit_exact=True,historical_work_full_runs_rebound=False,
        prepared_sha256=C.sha(MANIFEST),arena_sha256=ARENA_SHA,run_log_sha256=C.sha(output/'run.log'),
        stages=stages,dense=dense,cpu_wall_seconds=elapsed,single_cpu=cpu,hardware_cycles=None,
        reference_use='saved v0-equivalent stages read only for post-run comparison; never preloaded into computation',
        native_accuracy_acceptance=False,rtl_executed=False,official_framework_forward=False,
        attention_function_unchanged=True,attention_support_capacity_patch=p['source_identity']['support_capacity_replacements'])
    (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    return dict(status=result['status'],tokens=tokens,all_15_stages_bit_exact=True,result=str(output/'RESULT.json'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare')
    for name in ('out','baseline-root','arena','small-receipt'):prep.add_argument('--'+name,type=Path,required=True)
    run=sub.add_parser('execute');run.add_argument('--out',type=Path,required=True)
    run.add_argument('--tokens',type=int,choices=(16,128),required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.out,args.baseline_root,args.arena,args.small_receipt) if args.command=='prepare' else execute(args.out,args.tokens),indent=2))


if __name__=='__main__':main()
