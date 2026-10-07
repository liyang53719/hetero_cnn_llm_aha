#!/usr/bin/env python3
"""Fresh actual K1024 Matrix/Norm/RoPE selected-head chain; source-only evidence.

The existing projection controller's opt-in branch executes real Revision8B-B
Matrix hardware and communicates through a delayed-ACK SharedL2 test fabric.
This runner never supplies a projected/native output to a hardware stage.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from heteronpu.model_geometry import require

RTL_SOURCES = (
 'rtl/fabric/shared_l2_fabric.sv',
 'rtl/matrix/bf16_outer_product_array_glue512.sv',
 'rtl/matrix/candidates/rev8b_a/bf16_operand_distribution512_rev8b_a_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_tag_pipeline5_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_lane_cluster16_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_cluster_flags_glue32_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_context_front_control5_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_front_to_cluster_broadcast32_rev8b_b_candidate.sv',
 'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv',
 'rtl/integration/qwen2_matrix_command_endpoint.sv',
 'rtl/integration/qwen2_projection_descriptor_context.sv',
 'rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv',
 'rtl/integration/qwen2_projection_tile16_controller.sv',
 'rtl/integration/qwen2_projection_qk_norm_rope_candidate.sv',
 'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
 'rtl/sfu/fp32_reduce16.sv', 'rtl/sfu/fp32_rsqrt_nr.sv',
 'rtl/sfu/fp32_rmsnorm256_chunked.sv', 'rtl/sfu/qk_norm256_bf16_candidate.sv',
 'rtl/sfu/fp32_rope_pair_bf16_candidate.sv',
 'rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',
 'rtl/integration/rope_bf16_l2_candidate.sv',
 'rtl/integration/qwen2_shared_l2_rope_payload.sv',
 'tb/tb_qwen35_matrix_norm_rope_chain.sv',
)
EMISSION_SOURCES = (
 'integration/gemmini/EmitHeteroBF16Fma.scala',
 'integration/gemmini/EmitHeteroFP32Alu.scala',
 'integration/gemmini/EmitHeteroFP32Pipelines.scala',
 'chisel/matrix_norm_rope_hardware/src/main/scala/EmitMatrixNormRoPEHardwarePrimitives.scala',
 'chisel/matrix_norm_rope_hardware/build.sbt', 'chisel/matrix_norm_rope_hardware/manifest.py',
 'chisel/rope_hardware_oracle/maven-lock.json',
 'scripts/generate_matrix_norm_rope_primitives.sh',
)
EXTRA_SOURCES = (
 'scripts/run_matrix_norm_rope_candidate.py',
 'scripts/verify_matrix_norm_rope_trace.py',
 'scripts/materialize_matrix_norm_rope_vectors.py',
 'src/heteronpu/matrix_norm_rope_candidate.py',
 'scripts/matrix_norm_rope_reference.c',
 'src/heteronpu/qk_norm256_candidate.py',
 'src/heteronpu/rope_bf16_candidate.py',
 'rtl/sfu/fp32_rsqrt_coeffs.svh',
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_logged(command, path, timeout=1200, env=None):
    with path.open('w') as log:
        subprocess.run([str(x) for x in command], cwd=ROOT, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=timeout, env=env)


def build(verilator, generated, output, jobs=2):
    obj = output/'obj_chain'
    command = [verilator, '--binary', '--timing', '-Wno-fatal', '-j', str(jobs),
               '--output-split', '12000', '--output-split-cfuncs', '300',
               '--top-module', 'tb_qwen35_matrix_norm_rope_chain',
               '--Mdir', obj, '-o', 'tb', generated/'HeteroMatrixNormRoPEHardwarePrimitives.sv']
    command.extend(ROOT/p for p in RTL_SOURCES)
    run_logged(command, output/'build.log', timeout=1800)
    return obj/'tb', [str(x) for x in command]


def verify_log(text, suite):
    markers = re.findall(r'QWEN35_MATRIX_NORM_ROPE_CHAIN_PASS ([^\n]+)', text)
    require(len(markers)==1, 'missing/duplicate chain PASS marker')
    require(re.search(r'\bsuite='+re.escape(suite)+r'\b',markers[0]) is not None,
            'chain suite mismatch')
    metrics = {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',markers[0])}
    expected = {'main': (4,0,0,0), 'all': (7,21,10,7)}
    require(suite in expected, 'unsupported acceptance suite')
    require(tuple(metrics.get(k) for k in ('successes','rejects','faults','resets')) == expected[suite],
            'chain transaction inventory mismatch')
    require(metrics.get('capacity_bytes') == 1572864 and metrics.get('source_injection') == 0,
            'chain capacity or source-injection claim mismatch')
    for k in ('actual_matrix_inputs','actual_matrix_outputs','explicit_write_acks',
              'read_stall_cycles','write_stall_cycles','dma_stall_cycles','delayed_ACK_cycles'):
        require(metrics.get(k,0)>0, 'missing real handshake/ACK/stall evidence: '+k)
    if suite == 'main':
        require(metrics['actual_matrix_inputs'] == 49152 and metrics['actual_matrix_outputs'] == 49152,
                'main accepted Matrix coverage mismatch')
    return metrics


def run(args):
    from heteronpu.matrix_norm_rope_candidate import materialize, verify_materialized, MATERIALIZER_SOURCES
    require(not args.output.exists() or not any(args.output.iterdir()), 'output must be new/empty')
    args.output.mkdir(parents=True, exist_ok=True)
    source_names = sorted(set(RTL_SOURCES+EMISSION_SOURCES+EXTRA_SOURCES+tuple(MATERIALIZER_SOURCES)))
    hashes = {p:sha256(ROOT/p) for p in source_names}
    fixture_dir = args.output/'vectors'
    fixture = materialize(ROOT,args.payload_layer0,args.payload_layer3,args.payload_extra,fixture_dir)
    require(fixture['native_gate_pass'], 'selected-head native numerical thresholds failed')
    fixture_hash = sha256(fixture_dir/'summary.json')
    print('Fresh raw inputs and independent pipeline oracle materialized',flush=True)
    env = os.environ.copy()
    env.update(OUT=str(args.generated), PYTHON_BIN=sys.executable)
    if args.verilator:env['VERILATOR_BIN']=str(args.verilator)
    else:env.pop('VERILATOR_BIN',None)
    verilator = args.verilator or ROOT/'work/rope_hardware_oracle/bin/verilator'
    run_logged(['bash', ROOT/'scripts/generate_matrix_norm_rope_primitives.sh'],
               args.output/'emission.log',env=env)
    manifest_verify = [sys.executable, ROOT/'chisel/matrix_norm_rope_hardware/manifest.py',
                       'verify',ROOT,args.generated]
    subprocess.run([str(x) for x in manifest_verify],check=True,timeout=90)
    binary, command = build(verilator,args.generated,args.output,args.jobs)
    print('Actual 512-lane Matrix and Norm/RoPE RTL built',flush=True)
    from verify_matrix_norm_rope_trace import verify_trace
    suites=[]
    for source,suite,root in [('baseline','all',fixture_dir),('avx2','main',fixture_dir/'avx2')]:
        prefix=f'{source}_{suite}'
        log=args.output/(prefix+'.log');trace=args.output/(prefix+'.jsonl')
        run_logged([binary,f'+vectors={root}',f'+suite={suite}',f'+trace={trace}'],log,timeout=1800)
        metrics=verify_log(log.read_text(),suite)
        suites.append({'source':source,'suite':suite,'metrics':metrics,
                       'trace_sha256':sha256(trace),'log_sha256':sha256(log),
                       'independent_trace':verify_trace(trace,root,suite=suite)})
        print(f'{source} {suite} actual RTL passed',flush=True)
    # Materializer, traces and source hashes are rechecked after all simulations.
    verify_materialized(fixture_dir,trusted_summary_sha256=fixture_hash)
    subprocess.run([str(x) for x in manifest_verify],check=True,timeout=90)
    require(hashes=={p:sha256(ROOT/p) for p in source_names},'source changed during verification')
    hardware=json.loads((args.generated/'manifest.json').read_text())
    summary={'schema_version':1,'status':'PASS_BOUNDED_MATRIX_NORM_ROPE_RTL_CHAIN',
             'hardware_manifest_sha256':sha256(args.generated/'manifest.json'),
             'generated_rtl_sha256':hardware['emitted_sha256'],
             'tool_versions':hardware['tool_versions'],
             'build_command':command,
             'native_selected_head_gate_pass':fixture['native_gate_pass'],
             'native_full_block_gate_pass':fixture['native_full_block_gate_pass'],
             'source_sha256':hashes,'fixture_summary_sha256':fixture_hash,
             'fixture_summary':fixture,'rtl_suites':suites,
             'production_policy_changed':False,'matrix_producer_injected':False,
             'Matrix_Norm_RoPE_selected_head_integrated':True,
             'all_Q8_K2_tensor_owner_complete':False,'Command128_complete':False,
             'full_block_numerical_complete':False,'PPA_measured':False,
             'mac_utilization_measured':False,'U00_2_complete':False,'U01_complete':False}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--generated',type=Path,default=ROOT/'work/generated/matrix_norm_rope_candidate')
    p.add_argument('--verilator',type=Path)
    p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--payload-layer0',type=Path,default=ROOT/'work/qwen35_layer0_payload')
    p.add_argument('--payload-layer3',type=Path,default=ROOT/'work/qwen35_layer3_payload')
    p.add_argument('--payload-extra',type=Path,default=ROOT/'work/qwen35_prefix_payload')
    a=p.parse_args()
    for k,v in vars(a).items():
        if isinstance(v,Path):setattr(a,k,v.resolve())
    try:
        require(1<=a.jobs<=4,'jobs must be1..4')
        r=run(a)
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as e:
        print('MATRIX_NORM_ROPE_REJECTED: '+str(e),file=sys.stderr)
        raise SystemExit(3)
    print(r['status'])
