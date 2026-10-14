#!/usr/bin/env python3
"""One isolated original O projection cost trace. Never numerical acceptance."""
from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import resource
import signal
import struct
import sys
import time
import traceback
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from candidates.qwen2_dense_o_cost_m128 import gates
from candidates.qwen2_live_fullblock_model_m128 import runner as full


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def setup_dependencies():
    modules=full.dependencies()
    fixtures=modules[5]
    fixture=fixtures.make_qwen2_21_fixture(128,7)
    return modules,fixture


class ReplayOperands:
    """Explicit address-bound cost stimuli; never fabricate public publication.

    att lives only in this isolated readonly replay provider. The original
    PhysicalMemory att allocation remains untouched, unpublished and sentinel.
    wo uses the unchanged original PhysicalMemory readonly beat path.
    """
    def __init__(self,fixture,physical,inputs):
        self.fixture,self.physical,self.inputs=fixture,physical,inputs
        self.att_base=fixture.allocations['att'].address
        self.att_extent=fixture.allocations['att'].storage_bytes
        self.wo_base=fixture.allocations['wo'].address
        self.wo_extent=fixture.allocations['wo'].storage_bytes
        gates.require(set(inputs)=={'att','wo'} and len(inputs['att'])==self.att_extent and
                      len(inputs['wo'])==self.wo_extent,'cost input geometry')
        self.counts=Counter()

    def read64(self,address):
        gates.require(type(address) is int and address%64==0,'cost operand address alignment')
        if self.att_base<=address and address+64<=self.att_base+self.att_extent:
            self.counts['att_read_bytes']+=64
            return 'att',struct.unpack_from('<16I',self.inputs['att'],address-self.att_base)
        if self.wo_base<=address and address+64<=self.wo_base+self.wo_extent:
            self.counts['wo_read_bytes']+=64
            return self.physical.read64(address)
        raise ValueError('isolated O operand escaped exact att/wo address spans')


def construct(modules,fixture,inputs,library):
    r,dense,native,helper,original,fixtures,public,prefix,scalar,owner_module,binding,profiles,execution,suffix,observation=modules
    physical=prefix.PhysicalMemory(fixture,{'wo':r.base.bytes_provider(inputs['wo'])})
    memory=ReplayOperands(fixture,physical,inputs)
    region=fixture.config.regions[3]
    owner=owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(
        region.base,region.limit-region.base,8,2560),enable_dense_drain=True,enable_k_window=True,
        enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
    gates.require(library.td_reset()==0,'fresh Matrix reset')
    service=binding.ProfiledMatrixService(library,profiles.QWEN2_QKV_PROFILE)
    # Isolated original pc13 geometry. No public Host or predecessor completions
    # are created or claimed by this cost-only launch.
    job=original.numeric.model.Job(kind='Dense',tag=(fixture.config.epoch<<16)|13,
        a=fixture.allocations['att'].address,b=fixture.allocations['wo'].address,
        dst=fixture.allocations['o'].address,m=128,n=1536,k=1536,write_bytes=786432,
        weight_bf16=True,activation_bf16=False,output_bf16=False)
    job.validate()
    from candidates.qwen2_resident_matrix.official_bf16.execution import validate_job
    gates.require(validate_job(fixture,job)==13,'original O role/geometry binding')
    service.bind_dense_job(job,'dense_o')
    return original,physical,memory,owner,service,job


def debts(owner,service,physical):
    bridge=service._dense
    return dict(owner_state_not_idle=owner.state!='idle',owner_pending=owner.pending is not None,
        owner_fifo=len(owner.fifo),owner_read=owner.read_active is not None,
        owner_a_hold=owner.a_hold is not None,owner_a_rmw=owner.a_rmw_pending is not None,
        owner_write_state=owner.write_state!='idle',owner_seed=bool(owner.seed_outstanding),
        owner_lease=owner.lease is not None,tile_busy=not owner.tiles.idle,tile_leased=owner.tiles.leased,
        physical_pending=physical.pending is not None,matrix_owned=service.owner is not None,
        matrix_group=service.group is not None,matrix_result=service.result is not None,
        matrix_done=service._done is not None,dense_bridge=bridge is not None,
        bridge_results=len(bridge.pending) if bridge else 0,matrix_c_state=int(service.lib.matrix_state()))


def resource_identity(owner,service,physical):
    return dict(owner=id(owner),a_banks=id(owner.a_banks),b_banks=id(owner.b_banks),
        tiles=id(owner.tiles),tile_banks=id(owner.tiles.banks),physical=id(physical),
        matrix=id(service),accumulator_address=service.resource_address,
        a_bank_shape=[16,1376,256],b_bank_shape=[16,160,256],accumulator_contexts=5,
        accumulator_bytes=81920,resident_tile_slots=3,issued_cells=4096)


def run(out,*,reviewed_source_manifest=None):
    started,cpu=time.monotonic(),time.process_time()
    sources=gates.require_review(reviewed_source_manifest)
    out=Path(out).absolute();gates.fresh_output(out);out.mkdir()
    discard=out/'actual_dense.f32le';discard.symlink_to('/dev/null')
    report=dict(schema=1,status='STARTED',scope='ISOLATED_COST_REPLAY_NOT_SAME_CHAIN',
        numerical_acceptance=False,fullblock_executed=False,public21_executed=False,
        cost_complete=False,compile_executed=False,torch_imported=False,rtl_executed=False,
        hardware_cycles=None,hardware_utilization=None,software_ticks_are_hardware_cycles=False,
        source_manifest_sha256=reviewed_source_manifest,source_sha256_before=sources,
        input_specs=gates.pins()['inputs'],limits=gates.LIMITS,automatic_retry=False,
        tensor_artifacts_retained=False,previous_terminal_acceptance_inherited=False,
        scalar_sfu_unified_physical_arbiter_proven=False)
    save(out/'RESULT.json',report)
    deadline=started+gates.LIMITS['work_wall_seconds']
    previous={s:signal.getsignal(s) for s in (signal.SIGALRM,signal.SIGTERM)}
    gates.require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'existing timer cannot be replaced')
    def expired(signum,frame):raise TimeoutError('isolated O cost-only wall deadline/termination')
    for s in previous:signal.signal(s,expired)
    signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))
    trace=None
    try:
        modules,fixture=setup_dependencies()
        # Code-only preflight includes original compiler --version verification.
        # No model operands are read and no Matrix FMA/reset occurs here.
        library,built,reuse=full.native_artifact.load(modules[1])
        gate=gates.OracleGate(out)
        sys.addaudithook(gate.audit)
        inputs=gates.load_inputs()
        original,physical,memory,owner,service,job=construct(modules,fixture,inputs,library)
        identity=resource_identity(owner,service,physical)
        report.update(native_artifact_reuse=reuse,job=asdict(job),identity_initial=identity,
            input_identity_before={n:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in inputs.items()},
            current_process_fresh_matrix=True,native_code_loaded_before_operand_gate=True,
            isolated_att_readonly_replay=True,
            physical_att_published=False,physical_att_written_bytes=0,physical_att_ack_bytes=0)
        gates.require(library.matrix_dense_fmas()==library.matrix_normal_fmas()==library.sf_bf16_v1_calls()==0,
                      'native arithmetic not fresh')
        driver=original.down_driver
        source=driver.DenseSource(job.a,job.m*job.k*4,'readonly',ready=lambda:True,raw=lambda:inputs['att'])
        gates.require(service.acquire(owner,'dense',job.tag),'isolated O Matrix acquire')
        bridge=service.dense_library(owner)
        trace=original.numeric.CappedTrace(out/'events_prefix.jsonl')
        report['status']='EXECUTING_COST_ONLY_O';save(out/'RESULT.json',report)
        stage_wall,stage_cpu=time.monotonic(),time.process_time()
        result,actual=driver.execute_dense(original.numeric.model,owner,bridge,memory,job,out,deadline,trace,
            a_source=source,output_event=physical.dense_sink(job),matrix_bridge=bridge)
        gates.require(result['completed'] and result['completion']==[job.tag,None,job.write_bytes] and
            physical.regions['o']['terminal'],'actual accepted O terminal missing')
        service.retire_owner_response(owner);service.release(owner)
        stage_seconds=time.monotonic()-stage_wall;stage_cpu_seconds=time.process_time()-stage_cpu
        report.update(original_driver=result,matrix=service.report(),stage_wall_seconds=stage_seconds,
            stage_cpu_seconds=stage_cpu_seconds,actual_O_owner_terminal_observed=True)
        gates.require(actual.raw()==physical.raw(job.dst,job.write_bytes),'accepted output sinks differ')
        gates.require(result['accepted']['accepted_steps']==73728 and result['accepted']['accepted_results']==48 and
            result['accepted']['groups']==10 and result['accepted']['response_handshakes']==1 and
            result['ddr']['ack_bytes']==786432 and result['prefix']['completed_sweeps']==result['prefix']['ack_bytes']==0,
            'complete isolated O schedule/ACK/zero-prefix mismatch')
        matrix=service.report();c=matrix['counters']
        gates.require(c['dense_steps']==73728 and c['dense_results']==48 and c['dense_groups']==10 and
            c['owner_acquires']==c['owner_responses']==c['owner_releases']==1 and
            matrix['dense_fma_calls']==301989888 and matrix['normal_fma_calls']==0 and library.sf_bf16_v1_calls()==0,
            'isolated O actual Matrix/lease counters mismatch')
        gates.require(identity==resource_identity(owner,service,physical),'isolated O resource replacement')
        remaining=debts(owner,service,physical)
        gates.require(not any(remaining.values()),'isolated O terminal has outstanding obligations')
        att=physical.regions['att']
        gates.require(not att['written'] and not att['acked'] and not att['terminal'] and not att['published'],
            'cost replay fabricated an actual Attention producer/publication')
        physical.check_coexistence()
        trace.close();trace=None
        discard.unlink()
        gates.require(full.native_artifact.identity()==reuse['artifact_identity_before'],'native artifact drift')
        report['source_sha256_after']=gates.sources()
        report['input_identity_after']=gates.input_identity()
        gates.require(report['source_sha256_after']==sources and
            report['input_identity_after']==report['input_identity_before'],'source/stimulus drift')
        result['ddr']['path']=None
        result['scope']='ISOLATED_COST_REPLAY_NOT_SAME_CHAIN'
        result['historical_numeric_label_is_not_verdict']=True
        report.update(status='COST_ONLY_O_COMPLETE',cost_complete=True,numerical_acceptance=False,
            original_driver=result,matrix=matrix,remaining_debts=remaining,identity_final=resource_identity(owner,service,physical),
            observed_operand_bytes=dict(memory.counts),physical_accepted=dict(physical.counts),
            stage_wall_seconds=stage_seconds,stage_cpu_seconds=stage_cpu_seconds,
            accepted_steps_per_wall_second=73728/stage_seconds,
            wall_seconds_per_accepted_step=stage_seconds/73728,
            full_4096_issued_cell_opportunities=301989888,actual_c_fma=matrix['dense_fma_calls'],silu_vector_calls=int(library.sf_bf16_v1_calls()),
            actual_useful_fma=result['useful_macs'],actual_executed_fma=result['executed_macs'],
            fullblock_runtime_bound_established=False,output_disposal=gate.disposal_events,
            prefix_seed_record_bytes=(out/'down_seed_records_prefix.bin').stat().st_size,
            prefix_transaction_record_bytes=(out/'down_prefix_transactions_prefix.jsonl').stat().st_size)
        gates.require(report['prefix_seed_record_bytes']==report['prefix_transaction_record_bytes']==0,
                      'O emitted unexpected prefix/seed records')
        gates.require(time.monotonic()<deadline,'isolated O end-to-end wall deadline')
        report.update(wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save(out/'RESULT.json',report)
        return report
    except BaseException as error:
        report.update(status='FAILED',cost_complete=False,numerical_acceptance=False,error=repr(error),
            failure_kind='TIMEOUT' if full.telemetry.is_budget(error) else 'EXECUTION_FAILURE',
            traceback=traceback.format_exc(),wall_seconds=time.monotonic()-started,
            cpu_seconds=time.process_time()-cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            backend_abort_drain_executed=False,process_cleanup_is_not_backend_drain=True,
            failed_debts_scope='owner/service/physical fields only; original driver local pending/read/result/staged/held queues not enumerated',
            driver_local_queues_enumerated_on_failure=False)
        if 'owner' in locals():
            report.update(failed_owner_state=owner.state,failed_owner_clock=owner.clock,
                failed_matrix=service.report(),failed_debts=debts(owner,service,physical),
                failed_physical_accepted=dict(physical.counts),failed_operand_counts=dict(memory.counts))
        save(out/'RESULT.json',report)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for signum,handler in previous.items():signal.signal(signum,handler)
        if trace is not None:trace.close()
        if discard.is_symlink():discard.unlink()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actual',action='store_true');parser.add_argument('--out');parser.add_argument('--reviewed-source-manifest')
    args=parser.parse_args(argv)
    if not args.actual:
        gates.require(args.out is None and args.reviewed_source_manifest is None,'actual arguments require --actual')
        print(json.dumps(dict(status='NOT_EXECUTED',scope='ISOLATED_COST_REPLAY_NOT_SAME_CHAIN',numerical_acceptance=False,
            actual_execution_authorized=False,input_loading=False,native_initialized=False,
            source_manifest_sha256=gates.manifest(gates.sources()),limits=gates.LIMITS)))
        return 0
    gates.require(args.out is not None and args.reviewed_source_manifest is not None,'actual requires fresh out and reviewed source manifest')
    resource.setrlimit(resource.RLIMIT_AS,(gates.LIMITS['rss_bytes'],gates.LIMITS['rss_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE,(gates.LIMITS['file_bytes'],gates.LIMITS['file_bytes']))
    report=run(args.out,reviewed_source_manifest=args.reviewed_source_manifest)
    print(json.dumps({n:report[n] for n in ('status','cost_complete','numerical_acceptance','stage_wall_seconds')}),flush=True)
    return 0 if report['cost_complete'] else 1


if __name__=='__main__':raise SystemExit(main())
