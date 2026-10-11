#!/usr/bin/env python3
"""Fixed-bank fullgraph software model: small, summary, prepare, or guarded run.

No downloads, RTL execution, hardware-cycle claims, or native acceptance.
Preparation compiles but does not execute actual-shaped arithmetic. M128 requires
this preparation's complete, independently compared M16 result. Old work-only
receipts are provenance, never a prerequisite for this newly packaged driver.
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

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fullgraph_dataflow_source', HERE / 'dataflow_source.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
FC, C, D, R, ROOT = B.FC, B.C, B.D, B.R, B.ROOT
R.require(__debug__, 'optimized Python (-O) is unsupported; validation assertions are required')
SCHEMA = 'qwen2-transposed-fullgraph-dataflow-v1'
SMALL_SHAPE = dict(hidden=32, ffn=224, heads=1, kv_heads=1, head_dim=32, max_tokens=128)
PARAMETERS = dict(shape=R.SHAPE, rmw=True, a_chunk=2560, down_chunk=2560,
                  a_bank_words=1376, b_bank_words=160, run_order=[16, 128], timeout_seconds=180)
LIMITS = dict(software_only=True, hardware_cycles=None, hardware_acceptance=False,
              actual_idma=False, actual_leaf_pipeline=False, rtl_executed=False,
              official_framework_forward=False, native_accuracy_acceptance=False,
              native_m128_gate='FAIL_BF16_STAGE_BUDGET_UNCHANGED',
              fp32_final_gate='FAIL_UNCHANGED', numerical_policy='OPEN_UNCHANGED',
              historical_work_full_runs_rebound=False)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def stable_identity(value):
    """HEAD is bookkeeping; all source and artifact hashes remain binding."""
    if isinstance(value, dict):
        return {k: stable_identity(v) for k, v in value.items() if k != 'git_head'}
    if isinstance(value, list):
        return [stable_identity(v) for v in value]
    return value


def source_pins():
    files = [Path(__file__), HERE / 'dataflow_source.py', HERE / 'compare.py',
             HERE / 'full_chain.py', HERE / 'transposed_dense.inc.cpp', HERE / 'small_tests.inc.cpp']
    files += [B.HERE / name for name in B.INCLUDE_SHA256]
    files += [ROOT / 'scripts' / (name + '.py') for name in (
        'qwen2_dense_residency_numeric', 'qwen2_block_recipe_model',
        'qwen2_prefill_resource_schedule', 'qwen2_prefill_traffic_bound',
        'qwen2_rectangular_attention_model', 'qwen2_rectangular_attention_numeric')]
    return {str(p.relative_to(ROOT)): C.sha(p) for p in files}


def summary():
    source, _, _, identity = B.generated()
    traffic = B.traffic()
    return dict(schema=SCHEMA, status='SOURCE_IDENTITY_ONLY_NOT_EXECUTED', **LIMITS,
                generated_cpp_sha256=R.sha(source.encode()), source_sha256=source_pins(),
                source_identity=stable_identity(identity), historical_work=B.HISTORICAL_WORK,
                packaged_driver_actual_m16_executed=False, packaged_driver_actual_m128_executed=False,
                fixed_scratch_bytes=786432, ffn_a_reserved_bytes=638976, prefix_ddr_bytes=786432,
                logical_math_owners=19, public_host_commands=21,
                modeled_m128_traffic={k: traffic[k] for k in
                    ('read_bytes', 'write_bytes', 'total_bytes', 'transfers_64b')},
                counter_scope='Software transfers plus reused source event ledger; not measured hardware cycles.')


def rows(log, marker):
    result = []
    for line in log.splitlines():
        if line.startswith(marker + ' '):
            fields = line.split()[1:]
            pairs = [word.split('=', 1) for word in fields]
            R.require(all(len(pair) == 2 for pair in pairs), 'malformed log fields')
            R.require(len({pair[0] for pair in pairs}) == len(pairs), 'duplicate log fields')
            result.append({key: int(value) if re.fullmatch(r'\d+', value) else value
                           for key, value in pairs})
    return result


def stage_rows(shape, tokens, *, synthetic=False):
    layout = R.make_layout(shape)
    result = []
    for phase, name in enumerate(R.STAGE_NAMES):
        width = next(r['words'] // shape['max_tokens'] for r in layout['regions'] if r['name'] == name)
        row = dict(phase=phase, name=name, values=tokens * width)
        if synthetic:
            row = dict(tokens=tokens, **row)
        result.append(row)
    return result


def verify_float_environment(log):
    probes = rows(log, 'SOFTWARE_FLOAT_ENV')
    R.require(len(probes) == 1 and probes[0]['rounding'] == 'FE_TONEAREST' and probes[0]['probes'] == 10 and
              probes[0]['ftz'] == probes[0]['daz'] == 0, 'floating-point environment differs')


def parse_run_log(log, tokens):
    R.require(type(tokens) is int and tokens in (16, 128), 'only M16/M128 supported')
    expected_order = (['SOFTWARE_FLOAT_ENV'] + ['TRANSPOSED_CASE'] * 3 +
                      ['RESIDENT_ATTENTION', 'TRANSPOSED_CASE', 'DATAFLOW_FFN', 'DATAFLOW_DOWN'] +
                      ['SOFTWARE_RECIPE_STAGE'] * 15 + ['SOFTWARE_RECIPE_COMPLETE'])
    R.require([line.split()[0] for line in log.splitlines() if line.strip()] == expected_order,
              'fullgraph log owner/stage order differs')
    verify_float_environment(log)
    dense = rows(log, 'TRANSPOSED_CASE')
    for row, (_, k, n) in zip(dense, C.S.BOUND.MATRICES[:4]):
        issues = k * ((n + 31) // 32)
        expected = dict(m=tokens, k=k, n=n, rmw=1, a_chunk=2560, a_values=tokens*k,
                        w_values=k*n, issues=issues, swapped_fmas=issues*4096,
                        captures=(n+31)//32, a_read_words=tokens*k, a_write_words=tokens*k,
                        refill_phases=tokens*k//16*3, context_peak=5, meta_peak=1, fifo_peak=1, final_peak=1)
        R.require(row == expected, 'Dense log shape/counters differ')
    attention = D.parse_attention_log(log, R.make_layout(), tokens, True)
    ffn = dict(m=tokens, k=1536, n=8960, input_values=tokens*1536, weight_values=2*1536*8960,
               act_values=tokens*8960, tile_read_bytes=3*tokens*8960*4,
               tile_write_bytes=3*tokens*8960*4, gate_up_arithmetic_ddr_reads=0,
               a_reserved_bytes=638976, b_bytes=81920)
    down = dict(m=tokens, k=8960, n=1536, chunk=2560, a_values=tokens*8960,
                w_values=8960*1536, prefix_read_bytes=2359296, prefix_write_bytes=2359296,
                prefix_acks=144, final_acks=48, issues=8960*48, published=1)
    R.require(rows(log, 'DATAFLOW_FFN') == [ffn] and rows(log, 'DATAFLOW_DOWN') == [down],
              'FFN/down log shape/recipe/counters differ')
    R.require(rows(log, 'SOFTWARE_RECIPE_STAGE') == stage_rows(R.SHAPE, tokens),
              'stage log shape/order differs')
    R.require(rows(log, 'SOFTWARE_RECIPE_COMPLETE') == [dict(tokens=tokens, stages=15)],
              'completion log differs')
    return dict(dense=dense, attention=attention, ffn=ffn, down=down)


def small_sources(tiny):
    source, down, full, identity = B.generated()
    if tiny:
        full = full[:full.index('int main(')] + '''int main(){try{verifyFloatEnvironment();fullCase(16);
std::cout<<"DATAFLOW_TINY_PASS runs=1 stages=15 official_shape=0 official_forward=0"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}}
'''
    return source, ({'small_fullgraph': full} if tiny else {'small_down': down, 'small_fullgraph': full}), identity


def parse_small_logs(logs, tiny):
    tokens = (16,) if tiny else (16, 32, 128)
    full = logs['small_fullgraph']
    verify_float_environment(full)
    marker = ('DATAFLOW_TINY_PASS runs=1 stages=15 official_shape=0 official_forward=0' if tiny else
              'DATAFLOW_FULLGRAPH_SMALL_PASS runs=3 stages=45 official_shape=0 official_forward=0')
    R.require(full.splitlines()[-1] == marker, 'small completion marker differs')
    expected = [s for t in tokens for s in stage_rows(SMALL_SHAPE, t, synthetic=True)]
    R.require(rows(full, 'SYNTHETIC_STAGE_EXACT') == expected, 'small stage shape/order differs')
    cases = rows(full, 'SYNTHETIC_FULLGRAPH_EXACT')
    R.require(len(cases) == len(tokens), 'small fullgraph run count differs')
    for case, t in zip(cases, tokens):
        R.require(case['tokens'] == t and case['stages'] == 15 and case['values'] == t*1056 and
                  case['eliminated_ddr_guard_rejections'] == 6 and case['gate_up_external_bytes'] == 0,
                  'small fullgraph receipt differs')
    down = []
    if not tiny:
        log = logs['small_down']
        verify_float_environment(log)
        R.require(log.splitlines()[-1] == 'DATAFLOW_SMALL_PASS cases=10 official_forward=0 official_m16=0 official_m128=0',
                  'small down completion marker differs')
        down = rows(log, 'DOWN_BIT_EXACT')
        recipe = [(16,16,16,16,0,0), (32,32,32,16,0,1), (16,272,160,80,0,1),
                  (32,272,192,80,0,1), (128,272,192,80,0,1), (16,8960,32,2560,0,0)]
        recipe += [(16 if p&1 else 32,64,48,16,p,1) for p in range(1,5)]
        R.require([tuple(row[k] for k in ('m','k','n','chunk','pattern','bias')) for row in down] == recipe,
                  'small down shape/recipe/order differs')
        R.require(all(row['values'] == row['m']*row['n'] for row in down), 'small down value count differs')
        records = {
            'PREFIX_LAYOUT': dict(exact_addresses=8192, external_mutation_observed=1, seed_payload_bytes=64),
            'PROTOCOL_FAULTS': dict(rejected=42, sticky_poison=1, job_generation=1, rtl_fault_drain=0),
            'PREFIX_ALL_CONTEXTS': dict(contexts=48, beat_addresses=12288, values=196608,
                                        high_bitmap_bits=16, missing_last_ack_rejected=1),
            'FFN_CONSUMER': dict(physical_mutation_observed=1, physical_values=61440, retained_a_halfwords=196608),
            'FFN_LIFECYCLE_FAULTS': dict(rejected=10, sticky_poison=1),
            'DOMAIN_ERRORS': dict(rejected=9, unpublished=1, per_step_hardware_flags=0),
        }
        for name, expected_record in records.items():
            R.require(rows(log, name) == [expected_record], 'small protocol/address/consumer evidence differs: ' + name)
    return dict(coverage='packaging_tiny_only' if tiny else 'bounded_full_small_suite',
                fullgraph_runs=len(tokens), fullgraph_stages=15*len(tokens),
                fullgraph_checked_values=sum(row['values'] for row in cases), down_cases=len(down),
                down_checked_values=sum(row['values'] for row in down), bit_mismatches=0,
                gate_up_guard_rejections=6*len(tokens))


def compile_source(path, binary, cpu):
    compiler = shutil.which('g++')
    R.require(compiler is not None, 'ordinary C++ compiler unavailable')
    command = [compiler, *R.FLAGS, str(path), '-o', str(binary)]
    build = subprocess.run(['taskset', '-c', str(cpu), *command], capture_output=True, text=True, timeout=90)
    binary.with_suffix('.build.log').write_text(build.stdout + build.stderr)
    R.require(build.returncode == 0, 'C++ build failed: ' + build.stderr)
    return command


def small(out, *, tiny=False):
    out = C.output_directory(out)
    source, sources, identity = small_sources(tiny)
    out.mkdir(parents=True)
    (out/'block_layout.h').write_text(R.header(R.make_layout(SMALL_SHAPE)))
    (out/'frozen_fullgraph.cpp').write_text(source)
    cpu = min(os.sched_getaffinity(0))
    commands, logs = {}, {}
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               DATAFLOW_EVIDENCE_DIR=str(out))
    for name, text in sources.items():
        (out/(name+'.cpp')).write_text(text)
        commands[name] = compile_source(out/(name+'.cpp'), out/name, cpu)
        run = subprocess.run(['taskset', '-c', str(cpu), str(out/name)], env=env,
                             capture_output=True, text=True, timeout=90)
        logs[name] = run.stdout + run.stderr
        (out/(name+'.run.log')).write_text(logs[name])
        R.require(run.returncode == 0, 'synthetic C++ run failed: ' + logs[name])
    numeric = parse_small_logs(logs, tiny)
    result = dict(schema=SCHEMA, status='SMALL_SYNTHETIC_ONLY', **LIMITS, tiny=tiny,
                  synthetic_shape=SMALL_SHAPE, source_sha256=source_pins(),
                  source_identity=stable_identity(identity), generated_cpp_sha256=B.CPP_SHA256,
                  compiler_commands=commands, strict_flags=R.FLAGS, single_cpu=cpu, numeric=numeric,
                  historical_work=B.HISTORICAL_WORK,
                  artifact_sha256={p.name: C.sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    write_json(out/'SUMMARY.json', result)
    return result


def verify_small(path):
    path = Path(path).resolve()
    receipt = json.loads(path.read_text())
    R.require(receipt.get('schema') == SCHEMA and receipt.get('tiny') is False and
              receipt.get('status') == 'SMALL_SYNTHETIC_ONLY',
              'complete packaged small prerequisite required; tiny/historical receipt is insufficient')
    R.require(all(receipt.get(k) == v for k, v in LIMITS.items()), 'small receipt scope changed')
    source, sources, identity = small_sources(False)
    R.require(receipt['source_sha256'] == source_pins() and
              receipt['source_identity'] == stable_identity(identity), 'small source identity changed')
    R.require(receipt['strict_flags'] == R.FLAGS and receipt['synthetic_shape'] == SMALL_SHAPE,
              'small shape/compiler recipe changed')
    artifacts = receipt['artifact_sha256']
    required = {'frozen_fullgraph.cpp', 'block_layout.h'}
    required.update(name+suffix for name in sources for suffix in ('', '.cpp', '.build.log', '.run.log'))
    R.require(required <= artifacts.keys(), 'small prerequisite artifacts incomplete')
    for file, digest in artifacts.items():
        R.require(Path(file).name == file and file != 'SUMMARY.json', 'invalid small artifact path')
        FC.checked_hash(path.parent/file, digest)
    R.require((path.parent/'frozen_fullgraph.cpp').read_text() == source and
              receipt['generated_cpp_sha256'] == B.CPP_SHA256, 'small frozen recipe changed')
    R.require((path.parent/'block_layout.h').read_text() == R.header(R.make_layout(SMALL_SHAPE)),
              'small header shape changed')
    logs = {}
    for name, text in sources.items():
        R.require((path.parent/(name+'.cpp')).read_text() == text, 'small harness changed')
        command = receipt['compiler_commands'][name]
        R.require(command[1:] == [*R.FLAGS, str(path.parent/(name+'.cpp')), '-o', str(path.parent/name)],
                  'small compiler recipe changed')
        logs[name] = (path.parent/(name+'.run.log')).read_text()
    R.require(parse_small_logs(logs, False) == receipt['numeric'], 'small numeric receipt changed')
    # Every saved input and stage is part of the prerequisite, not just its log.
    evidence_sizes = {}
    for tokens in (16, 32, 128):
        evidence_sizes[f'input_fullgraph_m{tokens}.f32le'] = R.make_layout(SMALL_SHAPE)['writable_start']
        for row in stage_rows(SMALL_SHAPE, tokens):
            evidence_sizes[f"synthetic_m{tokens}_phase_{row['phase']}_{row['name']}.f32le"] = row['values']*4
    for case in rows(logs['small_down'], 'DOWN_BIT_EXACT'):
        m, k, n = (case[key] for key in ('m', 'k', 'n'))
        evidence_sizes[f"input_down_m{m}_k{k}_n{n}_pattern{case['pattern']}.f32le"] = (m*k+k*n+n)*4
    R.require(set(artifacts) == required | evidence_sizes.keys(), 'small artifact inventory differs')
    for file, size in evidence_sizes.items():
        data = path.parent/file
        R.require(data.stat().st_size == size, 'small evidence byte count differs')
        R.require(bool(R.np.isfinite(R.np.fromfile(data, dtype='<f4')).all()), 'nonfinite small evidence')
    return dict(path=str(path), sha256=C.sha(path), source_sha256=receipt['source_sha256'],
                coverage='bounded_full_small_suite')


def verify_baselines(root, identity):
    baselines = FC.verify_baselines(root, identity['fullchain_identity'])
    # A self-consistent altered baseline source is still not the frozen recipe.
    expected, _ = D.resident_source(ROOT, rectangular_attention=True)
    FC.checked_hash(Path(root)/'generated/software_recipe.cpp', R.sha(expected.encode()))
    FC.checked_hash(Path(root)/'generated/block_layout.h', R.sha(R.header(R.make_layout()).encode()))
    return baselines


def verify_arena(path):
    path = Path(path).resolve()
    R.require(path.is_file() and path.stat().st_size == 188043264 == R.make_layout()['writable_start'],
              'sealed arena size differs')
    FC.checked_hash(path, FC.ARENA_SHA)
    return dict(path=str(path), bytes=188043264, sha256=FC.ARENA_SHA)


def prepare(out, baseline_root, arena, small_receipt):
    out = C.output_directory(out)
    arena = verify_arena(arena)
    prerequisite = verify_small(small_receipt)
    source, _, _, identity = B.generated()
    baselines = verify_baselines(baseline_root, identity)
    generated = out/'generated'
    generated.mkdir(parents=True)
    (generated/'software_recipe.cpp').write_text(source)
    (generated/'block_layout.h').write_text(R.header(R.make_layout()))
    write_json(generated/'layout.json', R.make_layout())
    cpu = min(os.sched_getaffinity(0))
    command = compile_source(generated/'software_recipe.cpp', generated/'software_recipe', cpu)
    result = dict(schema=SCHEMA, status='PREPARED_NOT_EXECUTED', **LIMITS, parameters=PARAMETERS,
                  arena=arena, source_identity=stable_identity(identity), source_sha256=source_pins(),
                  generated_cpp_sha256=B.CPP_SHA256, small_prerequisite=prerequisite,
                  baseline_root=str(Path(baseline_root).resolve()), baselines=baselines,
                  compiler_command=command, strict_flags=R.FLAGS, single_cpu=cpu,
                  historical_work=B.HISTORICAL_WORK,
                  generated_sha256={p.name: C.sha(p) for p in sorted(generated.iterdir())})
    write_json(out/'PREPARED.json', result)
    return dict(status=result['status'], manifest=str(out/'PREPARED.json'), sha256=C.sha(out/'PREPARED.json'))


def verify_generated_artifacts(generated, prepared):
    expected_files = {'software_recipe.cpp', 'software_recipe', 'software_recipe.build.log', 'block_layout.h', 'layout.json'}
    R.require(prepared['generated_sha256'].keys() == expected_files, 'prepared artifact receipt differs')
    for name, digest in prepared['generated_sha256'].items():
        FC.checked_hash(Path(generated)/name, digest)


def validate(out):
    out = Path(out).resolve()
    FC.configure(out)  # Shared source-adjacent output guard.
    p = json.loads((out/'PREPARED.json').read_text())
    R.require(p['schema'] == SCHEMA and p['status'] == 'PREPARED_NOT_EXECUTED', 'prepared receipt type changed')
    R.require(p['parameters'] == PARAMETERS and p['strict_flags'] == R.FLAGS, 'prepared shape/recipe changed')
    R.require(all(p.get(k) == v for k, v in LIMITS.items()), 'prepared scope changed')
    source, _, _, identity = B.generated()
    R.require(p['source_sha256'] == source_pins() and p['source_identity'] == stable_identity(identity),
              'prepared source identity changed')
    R.require(p['generated_cpp_sha256'] == B.CPP_SHA256, 'prepared frozen recipe changed')
    generated = out/'generated'
    verify_generated_artifacts(generated, p)
    R.require((generated/'software_recipe.cpp').read_text() == source, 'prepared generated C++ differs')
    R.require((generated/'block_layout.h').read_text() == R.header(R.make_layout()) and
              json.loads((generated/'layout.json').read_text()) == R.make_layout(), 'prepared header/layout shape differs')
    R.require(p['compiler_command'][1:] == [*R.FLAGS, str(generated/'software_recipe.cpp'), '-o', str(generated/'software_recipe')],
              'prepared compiler recipe differs')
    R.require(verify_small(p['small_prerequisite']['path']) == p['small_prerequisite'], 'small prerequisite changed')
    R.require(verify_baselines(p['baseline_root'], identity) == p['baselines'], 'baseline evidence changed')
    R.require(verify_arena(p['arena']['path']) == p['arena'], 'prepared arena changed')
    return p


def verify_m16(out, p):
    out = Path(out).resolve()
    directory = out/'m16'
    # Shared stage verification binds the result to independent baseline bytes.
    FC.verify_m16(out, C.sha(out/'PREPARED.json'), p['baselines']['16']['stages'])
    result = json.loads((directory/'RESULT.json').read_text())
    R.require(result.get('schema') == SCHEMA and result.get('status') == 'MODEL_ONLY_DIAGNOSTIC_NOT_ACCEPTED' and
              result['all_15_stages_bit_exact'] is True and result['generated_cpp_sha256'] == B.CPP_SHA256 and
              result['source_sha256'] == p['source_sha256'] and
              result['binary_sha256'] == p['generated_sha256']['software_recipe'] and
              result['baseline_result_sha256'] == p['baselines']['16']['result_sha256'],
              'M16 source/binary/baseline identity differs')
    R.require(all(result.get(k) == v for k, v in LIMITS.items()), 'M16 scope differs')
    R.require(parse_run_log((directory/'run.log').read_text(), 16) == result['counters'], 'M16 log receipt differs')


def execute(out, tokens):
    R.require(type(tokens) is int and tokens in (16, 128), 'only M16/M128 supported')
    out = Path(out).resolve()
    FC.configure(out)
    output = out/f'm{tokens}'
    R.require(not output.exists(), 'refuse duplicate actual-shaped run or retry')
    p = validate(out)
    if tokens == 128:
        verify_m16(out, p)
    output.mkdir()
    prepared_sha = C.sha(out/'PREPARED.json')
    affinity = os.sched_getaffinity(0)
    keys = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')
    old_env = {key: os.environ.get(key) for key in keys}
    try:
        R.require(p['single_cpu'] in affinity, 'prepared single CPU is no longer available')
        os.sched_setaffinity(0, {p['single_cpu']})
        os.environ.update({key: '1' for key in keys})
        elapsed = R.execute(out/'generated', Path(p['arena']['path']), tokens, output, timeout_seconds=180)
        R.require(verify_arena(p['arena']['path']) == p['arena'], 'arena changed during execution')
        R.require(C.sha(out/'PREPARED.json') == prepared_sha and source_pins() == p['source_sha256'],
                  'prepared source changed during execution')
        verify_generated_artifacts(out/'generated', p)
        counters = parse_run_log((output/'run.log').read_text(), tokens)
        baseline = p['baselines'][str(tokens)]
        FC.checked_hash(Path(baseline['directory'])/'RESULT.json', baseline['result_sha256'])
        FC.verify_stages(baseline['directory'], baseline['stages'], tokens)
        FC.verify_stages(output, baseline['stages'], tokens)
        for stage in baseline['stages']:
            R.require((output/stage['path']).read_bytes() == (Path(baseline['directory'])/stage['path']).read_bytes(),
                      'independent baseline stage differs: ' + stage['name'])
        result = dict(schema=SCHEMA, status='MODEL_ONLY_DIAGNOSTIC_NOT_ACCEPTED', **LIMITS,
                      tokens=tokens, shape=dict(R.SHAPE, tokens=tokens),
                      completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE', all_15_stages_bit_exact=True,
                      prepared_sha256=prepared_sha, arena_sha256=FC.ARENA_SHA,
                      generated_cpp_sha256=B.CPP_SHA256, source_sha256=p['source_sha256'],
                      binary_sha256=p['generated_sha256']['software_recipe'],
                      baseline_result_sha256=baseline['result_sha256'], stages=baseline['stages'],
                      run_log_sha256=C.sha(output/'run.log'), counters=counters, cpu_wall_seconds=elapsed,
                      single_cpu=p['single_cpu'], reference_use='Post-run comparison only; computation starts from the sealed raw arena.')
        write_json(output/'RESULT.json', result)
        return dict(status=result['status'], tokens=tokens, all_15_stages_bit_exact=True, result=str(output/'RESULT.json'))
    except Exception as error:
        cause = error.__cause__
        if isinstance(cause, subprocess.TimeoutExpired):
            with (output/'run.log').open('a') as log:
                for part in (cause.stdout, cause.stderr):
                    log.write(part.decode(errors='replace') if isinstance(part, bytes) else (part or ''))
        write_json(output/'FAILED.json', dict(status='FAILED_NO_RETRY', tokens=tokens,
                                             prepared_sha256=prepared_sha, reason=str(error)))
        raise
    finally:
        os.sched_setaffinity(0, affinity)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('summary', 'small', 'prepare', 'run'):
        command = commands.add_parser(name)
        command.add_argument('--out', type=Path, required=True)
        if name == 'small':
            command.add_argument('--tiny', action='store_true', help='one synthetic 15-stage packaging check; cannot qualify prepare')
        if name == 'prepare':
            for arg in ('baseline-root', 'arena', 'small-receipt'):
                command.add_argument('--'+arg, type=Path, required=True)
        if name == 'run':
            command.add_argument('--tokens', type=int, choices=(16, 128), required=True)
    args = parser.parse_args()
    if args.command == 'summary':
        out = C.output_directory(args.out)
        result = summary()
        out.mkdir(parents=True)
        write_json(out/'SUMMARY.json', result)
    elif args.command == 'small':
        result = small(args.out, tiny=args.tiny)
        result = dict(status=result['status'], numeric=result['numeric'], summary=str(args.out/'SUMMARY.json'))
    elif args.command == 'prepare':
        result = prepare(args.out, args.baseline_root, args.arena, args.small_receipt)
    else:
        result = execute(args.out, args.tokens)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
