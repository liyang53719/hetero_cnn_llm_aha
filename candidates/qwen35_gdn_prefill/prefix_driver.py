"""Raw checkpoint input → typed RMS → real shared-Matrix QKV/Z/AB prefix.

Only this four-command owner chain is implemented. It has no public Command128
decoder yet; no Conv, input prep, chunk GDN, state, O or FFN is executed here.
Carried input names identify tokens128..255, not a stateful completed block.
"""
from __future__ import annotations

import argparse
import ctypes as C
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import signal
import time

import numpy as np

from .input_fixture import ROOT, load_fixture, gdn, SOURCE_FILES as INPUT_SOURCES
from . import typed_dense as d
from . import rms_owner as r
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library, SOURCE_HASHES as MATRIX_SOURCES

MODEL_SOURCES = (
    'candidates/qwen35_gdn_prefill/input_fixture.py',
    'candidates/qwen35_gdn_prefill/typed_dense.py',
    'candidates/qwen35_gdn_prefill/rms_owner.py',
    'candidates/qwen35_gdn_prefill/prefix_driver.py',
    'candidates/qwen35_gdn_prefill/prefix_reference.py',
    'candidates/qwen35_gdn_prefill/projection_reference.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/model.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala',
    'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py',
    'config/upstream/qwen3_5_0p8b/layer0_payload_pin.json',
    'chisel/continuous_prefill/config/host_bf16_gdn_descriptor_contract.json',
)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def persist(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def run(fixture, output, *, rows=16, budget_seconds=600,
        policy=r.ReductionPolicy.Torch210CpuDefault1024):
    d.require(type(rows) is int and rows in (16, 128), 'M16 or M128 prefix only')
    d.require(type(budget_seconds) is int and 0 < budget_seconds <= 3600, 'bounded software wall budget')
    output = Path(output)
    d.require(not output.exists(), 'fresh output required')
    manifest, inputs = load_fixture(ROOT, fixture)
    _, weights = gdn.load_payload(ROOT, Path(manifest['sources']['layer0_directory']))
    library = d.library_from_environment(ROOT)
    source_names=sorted(set(MODEL_SOURCES) | set(INPUT_SOURCES) | set(MATRIX_SOURCES))
    sources = {name: sha((ROOT/name).read_bytes()) for name in source_names}
    output.mkdir(parents=True)
    for name in source_names:
        target=output/'source_snapshot'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    start, current, sequence = time.monotonic(), None, []
    deadline = start + budget_seconds
    report = dict(schema_version=1, scope='QWEN35_L0_TYPED_OWNER_RMS_QKV_Z_AB_PREFIX_ONLY',
        rows=rows, status='RUNNING', input_fixture_sha256=sha((Path(fixture)/'manifest.json').read_bytes()),
        token_fixture_slices={'cold128':[0,rows],'carried128':[128,128+rows]},
        carried_label_means_input_window_only=True,
        source_sha256=sources, library_sha256=sha(library.read_bytes()),library=str(library),
        compile_receipt=str(Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']).resolve()),
        compile_receipt_sha256=sha(Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']).read_bytes()),
        rms_policy=r.ReductionPolicy(policy).value, commands=sequence,
        public_command128_executed=False, full_block_executed=False,
        chunk_gdn_executed=False, history_or_state_committed=False,
        hardware_cycles=None, hardware_mac_utilization=None, rtl_executed=False)
    persist(output/'identity.json', report)
    try:
        memory = d.TypedMemory()
        lib = configure_library(C.CDLL(str(library)))
        d.require(lib.td_reset() == 0, 'single initial Matrix reset')
        matrix = d.MatrixService(lib)
        dense = d.down.DenseOwnerModel(d.down.PrefixWorkspace(0x90000000, 64, 1))
        scalar = r.SharedScalar()
        rms = r.RmsOwner(scalar)
        resources = (id(memory), id(dense), id(dense.a_banks), id(dense.b_banks), matrix.resource_address, id(scalar))
        memory.add_readonly(0x1000000, weights['input_layernorm.weight'])
        original_weights = {role: weights['linear_attn.in_proj_'+role+'.weight'] for role in ('qkv','z')}
        original_weights['ab'] = weights['linear_attn.in_proj_a.weight'] + weights['linear_attn.in_proj_b.weight']
        weight_bases = {'qkv': 0x2000000, 'z': 0x4000000, 'ab': 0x6000000}
        for role, raw in original_weights.items():
            packed = np.frombuffer(raw, '<u2').reshape(-1, 1024).T.copy().tobytes()
            memory.add_readonly(weight_bases[role], packed)
        actual, tag = {}, 1
    except BaseException as error:
        report.update(status="FAILED",error=dict(type=type(error).__name__,message=str(error)),
                      elapsed_seconds=time.monotonic()-start)
        persist(output/"summary.json",report)
        raise

    def execute(driver, phase, role):
        nonlocal current
        current = driver
        command_start = time.monotonic()
        ticks = 0
        while driver.response is None:
            if ticks % 128 == 0:
                d.require(time.monotonic() < deadline, 'software prefix wall budget exceeded')
            driver.tick()
            ticks += 1
        d.require(driver.output.published, 'owner failed before actual output publication')
        command = dict(phase=phase, role=role, seconds=time.monotonic()-command_start, **driver.report())
        sequence.append(command)
        raw = driver.output.raw()
        (output/f'{phase}.{role}.actual.bf16le').write_bytes(raw)
        actual[phase][role] = raw
        persist(output/'progress.json', dict(commands=sequence, elapsed_seconds=time.monotonic()-start))
        print(json.dumps(dict(phase=phase, role=role, seconds=command['seconds'],
                              output_bytes=len(raw), sha256=sha(raw))), flush=True)

    try:
        for case, phase in enumerate(('cold128', 'carried128')):
            hidden = inputs[phase+'.hidden.bf16le'][:rows*2048]
            input_base, base = 0x100000+case*0x100000, 0x10000000+case*0x1000000
            memory.add_readonly(input_base, hidden)
            (output/f'{phase}.input.bf16le').write_bytes(hidden)
            actual[phase] = {}
            memory.allocate_output(base, rows*2048)
            execute(r.TypedRmsDriver(rms, memory, r.RmsJob(tag,input_base,0x1000000,base,rows,policy)),phase,'input_norm')
            tag += 1
            for role, width, offset in (('qkv',6144,0x100000), ('z',2048,0x400000), ('ab',32,0x600000)):
                destination = base+offset
                memory.allocate_output(destination,rows*width*2)
                job = d.down.Job(m=rows,k=1024,n=width,tag=tag,a=base,b=weight_bases[role],dst=destination,
                    activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=rows*width*2)
                execute(d.TypedDenseDriver(dense,matrix,memory,job),phase,role)
                tag += 1
            d.require(resources == (id(memory),id(dense),id(dense.a_banks),id(dense.b_banks),matrix.resource_address,id(scalar)),
                      'resource identity changed between actual prefix commands')
        report['actual_terminal_reached'] = True
        report['actual_elapsed_seconds'] = time.monotonic()-start
        report['matrix'] = matrix.report()
        report['scalar_calls'] = dict(scalar.calls)
        report['outputs'] = {phase:{name:dict(bytes=len(raw),sha256=sha(raw)) for name,raw in data.items()}
                             for phase,data in actual.items()}
        persist(output/'actual_terminal.json',report)
        # No reference code is imported or invoked until every actual output is sealed.
        from . import prefix_reference as reference
        reference_build = reference.build_projection_reference(output/'reference')
        report['reference_build'] = reference_build
        report['comparisons'] = {}
        for phase in actual:
            d.require(time.monotonic() < deadline, 'reference phase software wall budget exceeded')
            hidden = inputs[phase+'.hidden.bf16le'][:rows*2048]
            expected_norm = reference.rms_recipe(hidden,weights['input_layernorm.weight'],r.ReductionPolicy(policy).value)
            fixed = {'input_norm': reference.compare_bf16(actual[phase]['input_norm'],expected_norm)}
            for role,width in (('qkv',6144),('z',2048),('ab',32)):
                expected = reference.projection_reference(reference_build,actual[phase]['input_norm'],original_weights[role],rows,width)
                fixed[role] = reference.compare_bf16(actual[phase][role],expected)
                (output/f'{phase}.{role}.fixed.bf16le').write_bytes(expected)
            native, native_receipt = reference.native_prefix(hidden,weights)
            official = {role:reference.original_prefix_gate(raw,native[role]) for role,raw in actual[phase].items()}
            ab=np.frombuffer(actual[phase]['ab'],'<u2').reshape(rows,32)
            for role,part in (('a',ab[:,:16]),('b',ab[:,16:])):
                official[role]=reference.original_prefix_gate(part.copy().tobytes(),native[role])
            for role,raw in native.items(): (output/f'{phase}.{role}.official.bf16le').write_bytes(raw)
            report['comparisons'][phase] = dict(fixed_arithmetic=fixed,official=official,official_identity=native_receipt)
            d.require(all(v['bit_mismatches'] == 0 for v in fixed.values()),'actual prefix differs from independent fixed arithmetic')
        report['fixed_arithmetic_pass']=True
        report['official_prefix_gate_pass']=all(v['passed'] for case in report['comparisons'].values()
                                                for v in case['official'].values())
        report['status'] = ('PASS_PREFIX_GATES_ONLY' if report['official_prefix_gate_pass']
                            else 'FAIL_OFFICIAL_PREFIX_GATES')
        report['official_stage_acceptance'] = 'ORIGINAL_GDN_PER_NODE_THRESHOLDS_ONLY_FULL_BLOCK_OPEN'
    except BaseException as error:
        report['status'] = 'FAILED'
        report['error'] = dict(type=type(error).__name__,message=str(error))
        if current is not None:
            report['interrupted_owner'] = current.report()
            raw=current.output.raw()
            name='interrupted_output.unpublished_or_partial.bf16le'
            (output/name).write_bytes(raw)
            report['interrupted_staging']=dict(file=name,bytes=len(raw),sha256=sha(raw),
                published=current.output.published,written_offsets=sorted(current.output.written),
                acknowledged_offsets=sorted(current.output.acknowledged))
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic()-start
        report['source_unchanged'] = sources == {name:sha((ROOT/name).read_bytes()) for name in source_names}
        report['library_unchanged'] = (sha(library.read_bytes())==report['library_sha256'] and
            sha(Path(report['compile_receipt']).read_bytes())==report['compile_receipt_sha256'])
        report['fixture_unchanged'] = sha((Path(fixture)/'manifest.json').read_bytes())==report['input_fixture_sha256']
        if not all(report[name] for name in ('source_unchanged','library_unchanged','fixture_unchanged')):
            report['status']='FAILED'
            report['error']=dict(type='IdentityDrift',message='source/library/fixture changed during actual prefix')
        persist(output/'summary.json',report)
    d.require(all(report[name] for name in ('source_unchanged','library_unchanged','fixture_unchanged')),
              'source/library/fixture changed during actual prefix')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--rows',type=int,choices=(16,128),default=16)
    parser.add_argument('--budget-seconds',type=int,default=600)
    parser.add_argument('--policy',choices=[p.value for p in r.ReductionPolicy],default=r.ReductionPolicy.Torch210CpuDefault1024.value)
    args=parser.parse_args()
    def timed_out(signum, frame):
        raise TimeoutError('external/software prefix wall budget exhausted')
    # The invoking workflow also uses GNU timeout with a five-second kill
    # grace. Python signals preserve the last owner receipt where possible;
    # the external process exit is authoritative if a native call cannot yield.
    signal.signal(signal.SIGTERM,timed_out)
    signal.signal(signal.SIGALRM,timed_out)
    signal.setitimer(signal.ITIMER_REAL,args.budget_seconds)
    try:
        result=run(args.fixture,args.out,rows=args.rows,budget_seconds=args.budget_seconds,policy=args.policy)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps(dict(status=result['status'],seconds=result['elapsed_seconds'])))
    if not result['official_prefix_gate_pass']: raise SystemExit(2)


if __name__ == '__main__': main()
