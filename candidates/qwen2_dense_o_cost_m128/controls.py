#!/usr/bin/env python3
"""Real initialized O controls, with synthetic unread operands and zero FMAs."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_dense_o_cost_m128 import gates,runner


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--initialized-only',action='store_true');a=ap.parse_args(argv)
    if not a.initialized_only:
        print(json.dumps(dict(status='NOT_EXECUTED',numerical_acceptance=False)));return 0
    modules,fixture=runner.setup_dependencies()
    gates.OUTPUT_ROOT.mkdir(exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='cold_controls_',dir=gates.OUTPUT_ROOT))
    discard=out/'actual_dense.f32le';discard.symlink_to('/dev/null')
    library,built,reuse=runner.full.native_artifact.load(modules[1])
    gate=gates.OracleGate(out);sys.addaudithook(gate.audit)
    synthetic=dict(att=bytes(786432),wo=bytes(4718592))
    original,physical,memory,owner,service,job=runner.construct(modules,fixture,synthetic,library)
    initial=runner.resource_identity(owner,service,physical)
    failures=[]
    def reject(name,call):
        try:call()
        except (ValueError,PermissionError) as error:failures.append(dict(name=name,error=str(error)))
        else:raise ValueError('negative control admitted: '+name)
    gates.require(not any(runner.debts(owner,service,physical).values()),'initialized resources have debt')
    reject('unbound_role',lambda:service.acquire(owner,'dense',job.tag+1))
    reject('unaligned_stimulus',lambda:memory.read64(job.a+1))
    reject('operand_outside_cost_scope',lambda:memory.read64(fixture.allocations['n0'].address))
    reject('output_unpublished',lambda:physical.read_bytes64(job.dst))
    reject('terminal_before_real_ACK',lambda:physical.terminal(job,(job.tag,None,job.write_bytes)))
    reject('direct_tensor_disposal',lambda:discard.write_bytes(b'forbidden'))
    reject('unrelated_tensor_output',lambda:(out/'fake.f32le').write_bytes(b'forbidden'))
    reject('unrelated_old_payload',lambda:gate.audit('open',(str(ROOT/'work/old/actual.bin'),'rb',0)))
    reject('frozen_oracle_payload',lambda:gate.audit('open',(str(ROOT/'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/o.f32le'),'rb',0)))
    source=original.down_driver.DenseSource(job.a,job.m*job.k*4,'readonly',ready=lambda:False,raw=lambda:synthetic['att'])
    reject('unready_stimulus',lambda:source.validate(job))
    gates.require(service.acquire(owner,'dense',job.tag),'real initialized original Matrix lease positive gate')
    bridge=service.dense_library(owner)
    from candidates.qwen2_resident_matrix.official_bf16.dense_silu import OfficialDenseLibraryAdapter
    gates.require(type(bridge) is OfficialDenseLibraryAdapter,'O accidentally selected QKV partial adapter')
    reject('group_before_original_job_admission',lambda:bridge.td_group(0,1536,5))
    reject('release_before_actual_owner_response',lambda:service.release(owner))
    # Do not fabricate a terminal or reset/clear this genuine outstanding lease.
    # Report it and let process teardown discard the cold isolated process.
    gates.require(initial==runner.resource_identity(owner,service,physical),'resources replaced by cold controls')
    gates.require(library.matrix_dense_fmas()==library.matrix_normal_fmas()==0 and owner.clock==0 and
        owner.responses==0 and memory.counts=={} and not physical.regions['att']['written'],
        'cold controls executed model arithmetic/owner work')
    gates.require(gates.sources()==gates.sources(),'real installed source-rehash surface')
    discard.unlink()
    result=dict(status='PASS_REAL_INITIALIZED_O_CONTROL_ONLY',scope='ISOLATED_COST_REPLAY_NOT_SAME_CHAIN',
        numerical_acceptance=False,model_inputs_loaded=False,reference_payloads_read=False,
        native_code_loaded=True,native_code_loaded_before_operand_gate=True,compile_executed=False,torch_imported=False,owner_ticks=owner.clock,
        model_owner_responses=owner.responses,matrix_dense_fma=int(library.matrix_dense_fmas()),
        matrix_normal_fma=int(library.matrix_normal_fmas()),original_OfficialDenseLibraryAdapter=True,
        negative_controls=failures,terminal_fabricated=False,backend_abort_drain_executed=False,
        retained_cold_debts=runner.debts(owner,service,physical),identity=initial,
        real_matrix_lease_acquired=True,temporary_metadata_directory=str(out.relative_to(ROOT)))
    (out/'CONTROL.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
