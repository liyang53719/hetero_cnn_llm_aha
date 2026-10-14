#!/usr/bin/env python3
"""Real initialized dependencies and audit hook; no input/oracle/model arithmetic.

Only the original Scalar constructor's five fixed environment checks execute.
Matrix/selected SiLU reset and source checking are initialization, not FMAs.
Metadata-only Host decode may offer pc0; no owner request is accepted.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_live_fullblock_model_m128 import gates,runner,statistics


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialized-only',action='store_true')
    args=parser.parse_args(argv)
    if not args.initialized_only:
        print(json.dumps(dict(status='NOT_EXECUTED')));return 0
    dependencies=runner.dependencies()
    r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=dependencies
    from candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory import FullGraphMemory
    from candidates.qwen2_resident_matrix.official_bf16.execution import ObservedSiluLibrary,validate_job
    from candidates.qwen2_live_attention_model_m128.public_binding import PV32PublicExecution
    from candidates.qwen2_live_attention_model_m128.pv32_owner import OfficialPV32AttentionOwner
    from candidates.qwen2_live_fullblock_model_m128 import tail
    gates.OUTPUT_ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cold_initialized_',dir=gates.OUTPUT_ROOT) as directory:
        out=Path(directory);(out/'tmp').mkdir();tempfile.tempdir=str(out/'tmp')
        gate=gates.OracleGate(gates.DATA,out,gates.REFERENCE)
        sys.addaudithook(gate.audit)
        lib,built,reuse=runner.native_artifact.load(dense)
        selected=dense.selected_library(lib)
        gates.require(lib.td_reset()==0 and selected.sf_reset()==0,'initial resets')
        service=binding.ProfiledMatrixService(lib,profiles.QWEN2_QKV_PROFILE)
        shared=scalar.ScalarService()
        f=fixtures.make_qwen2_21_fixture(128,7)
        def no_input_read(offset):
            raise ValueError('cold probe cannot read any executable model operand')
        physical=prefix.PhysicalMemory(f,{n:no_input_read for n in gates.ROLES})
        memory=FullGraphMemory(physical)
        region=f.config.regions[3]
        owner=owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(
            region.base,region.limit-region.base,8,2560),enable_dense_drain=True,enable_k_window=True,
            enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
        x=PV32PublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),owner,
            original.numeric.CappedTrace(),time.monotonic()+30,fixture=f,
            host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
            prefix_owner=execution.OfficialPrefixOwner(shared),
            attention_owner=OfficialPV32AttentionOwner(service,shared),matrix_service=service)
        silu=ObservedSiluLibrary(selected,128)
        before=statistics.identity(x,physical,memory)
        ledger=statistics.StageLedger(x,physical,memory,silu)
        ledger.transition('metadata_decode_only')
        failures=[]
        def reject(name,fn):
            try:fn()
            except ValueError as error:failures.append(dict(name=name,error=str(error)))
            else:raise ValueError('negative control admitted: '+name)
        reject('duplicate_workspace',lambda:FullGraphMemory(physical))
        reject('tail_before_live_pc12',lambda:tail.execute_tail(x,physical,silu,out,memory=memory,
            attention_job=None,stage=lambda name:None))
        reject('workspace_seed_ack_without_begin',lambda:memory.workspace.finish())
        ports=x.advance_to_request();job=ports['ordinary_request']
        gates.require(job.kind=='Norm' and job.tag&0xffff==0,'real metadata-only pc0')
        reject('copied_public_job',lambda:x.prefix_edge(job=replace(job)))
        reject('wrong_public_shape',lambda:validate_job(f,replace(job,m=16)))
        reject('prefix_read_before_publication',lambda:physical.read_bytes64(f.allocations['n0'].address))
        reject('early_pc0_completion',lambda:x.publish_completions((0,)))
        for name in gates.REFERENCES:
            reject('preseal_'+name,lambda name=name:gate.audit('open',(str(gates.REFERENCE/(name+'.f32le')),'rb',0)))
        # Exercise the exact post-seal source/runtime/metadata read surface without
        # opening any actual reference payload or claiming an actual live seal.
        gates.require_final_reference()
        for path,digest in gates.pins()['runtime_read_sha256'].items():
            gates.require(gates.sha(path)==digest,'preseal exact runtime read drift')
        reject('pc12_seal_not_whole',lambda:gate.open_after_seal(dict(actual_outputs_sealed=True,
            public_completions=12,actual_owner_jobs=11,accepted_launch_results=0,finalfence=False,
            same_live_identity=True,outstanding_debts={})))
        # Independent gate instance only exercises the postseal permission branch.
        # The installed gate remains closed, so real payload reads still fail.
        other=gates.OracleGate(gates.DATA,out,gates.REFERENCE)
        other.open_after_seal(dict(actual_outputs_sealed=True,public_completions=21,actual_owner_jobs=17,
            accepted_launch_results=1,finalfence=True,same_live_identity=True,outstanding_debts={}))
        for name in gates.REFERENCES:
            other.audit('open',(str(gates.REFERENCE/(name+'.f32le')),'rb',0))
        for path in other.raw_paths:other.audit('open',(str(path),'rb',0))
        reject('historical_artifact_postseal',lambda:other.audit('open',(str(ROOT/'work/old/actual_att.u32le'),'rb',0)))
        gates.require(before==statistics.identity(x,physical,memory),'cold controls changed resource identity')
        gates.require(x.host.jobs==x.host.completed==0 and x.counts['request_fire']==x.counts['owner_result_fire']==0,
            'cold probe accepted model owner work')
        gates.require(lib.matrix_dense_fmas()==lib.matrix_normal_fmas()==silu.calls==silu.sf_calls()==silu.sf_failures()==0,
            'cold probe executed native arithmetic')
        gates.require(dict(shared.calls)=={} and not gate.opened and gate.reference_reads==[] and gate.input_reads==[],
            'cold probe executed Scalar operations or read payloads')
        stats=ledger.finish();x.trace.close()
        print(json.dumps(dict(status='PASS_REAL_INITIALIZED_FULLBLOCK_CONTROL_ONLY',real_audit_hook=True,
            native_code_loaded=True,matrix_fma_executed=False,silu_vectors_executed=False,
            model_inputs_loaded=False,reference_payloads_read=False,model_owner_jobs=0,
            scalar_fixed_environment_probes=5,scalar_service_calls=dict(shared.calls),
            software_host_metadata_ticks=stats['host_model_ticks'],resources=before,
            environment_events=gate.environment_events,negative_controls=failures,
            postseal_permission_branch_simulated_only=True,same_live_resource_identity=True),sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
