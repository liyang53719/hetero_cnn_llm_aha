"""Actual one-RMS/two-N32 projection prefix; no oracle injection or full block."""
from ..qwen35_35b_prefill.prefix_driver import (require,sha,PrefixExecutionError,rms,dense,
    Vector16,IEEE_POLICY,ReductionProfile,LargeKProjectionOwner,PrefixWorkspace,TypedLargeKProjectionDriver)
from ..qwen35_35b_payload.packer import raw_nk_to_kn
import time


def execute_ab(hidden,norm_weight,weights,*,tokens,profiles,matrix,vector,deadline,
               memory=None,controls=None,observe=None):
    require(type(tokens) is int and tokens in (16,128),'M16/M128')
    require(type(hidden) is bytes and len(hidden)==tokens*4096 and type(norm_weight) is bytes and len(norm_weight)==4096,'complete H2048 RMS input')
    require(type(weights) is dict and set(weights)=={'a','b'} and all(type(v) is bytes and len(v)==131072 for v in weights.values()),'two complete N32 K2048 NK weights')
    require(type(profiles) is dict and set(profiles)=={'a','b'},'independent A/B profiles')
    for profile in profiles.values():
        require(type(profile) is ReductionProfile and profile.ranges==((0,1024),(1024,2048)) and profile.pair_reverse is True,'explicit independently calibrated N32 pair profile')
        profile.validate(2048)
    require(type(matrix) is dense.MatrixService and matrix.owner is None and type(vector) is Vector16 and vector.client is None and vector.exception_policy==IEEE_POLICY,'drained existing Matrix/Vector')
    memory=dense.TypedMemory() if memory is None else memory
    require(type(memory) is dense.TypedMemory and not memory.regions and memory.pending is None,'fresh shared memory')
    require(controls is None or callable(controls),'optional fault controls')
    require(observe is None or callable(observe),'readonly observer')
    require(type(deadline) in (int,float) and deadline>time.monotonic(),'bounded wall deadline')
    scalar=rms.SharedScalar();rms_owner=rms.RmsOwner(scalar)
    projection_owner=LargeKProjectionOwner(PrefixWorkspace(0x100000000,16384,1,split_k=2048))
    resources=(id(memory),id(scalar),id(rms_owner),id(projection_owner),id(projection_owner.a_banks),
        id(projection_owner.b_banks),matrix.resource_address,vector.resource_address)
    cursor=0x100000
    def region(raw=None,size=None):
        nonlocal cursor
        extent=len(raw) if raw is not None else size
        address=cursor;cursor+=(extent+63)//64*64+64
        require(cursor<0x100000000,'tensors overlap workspace')
        if raw is None:memory.allocate_output(address,extent)
        else:memory.add_readonly(address,raw)
        return address
    input_base,weight_base=region(hidden),region(norm_weight)
    rms_base=region(size=len(hidden))
    packed=[(name,region(raw_nk_to_kn(weights[name],32,2048)),region(size=tokens*64)) for name in ('a','b')]
    report=dict(scope='ACTUAL_TYPED_RMS_TO_TWO_SEPARATE_N32_PROJECTIONS',status='RUNNING',tokens=tokens,
        full_block=False,rtl_executed=False,command128_executed=False,official_model_profile_admitted=False,
        source_hashes=dict(hidden=sha(hidden),norm_weight=sha(norm_weight),**{k:sha(v) for k,v in weights.items()}),
        numerical_profiles={k:vars(v) for k,v in profiles.items()},
        fixed_resources=dict(matrix_macs=4096,vector_lanes=16,scalar_units=1),terminals=[],stages=[],
        hardware_cycles=None,hardware_utilization=None,busy_duty=None,active_lane_duty=None,
        stall_breakdown=None,overlap_timeline=None)
    published=[]
    def run(stage, driver):
        started = time.monotonic()
        try:
            for tick in range(20_000_000):
                require(time.monotonic() < deadline, 'software prefix wall budget')
                options = {} if controls is None else controls(stage, tick, driver)
                driver.tick(**options)
                if driver.response is not None:
                    break
            require(driver.response is not None, 'software prefix transport watchdog')
        except BaseException as error:
            # Preserve the actual interrupted transaction without fabricating
            # ACK, reset, drain, terminal acceptance or resumability.
            raw = driver.output.raw()
            snapshot = dict(stage=stage, owner_report=driver.report(),
                terminal_accepted=driver.response is not None,
                shared_memory_pending=memory.pending is not None,
                pending_read=getattr(driver, 'pending_read', None) is not None,
                pending_ack=getattr(driver, 'pending_ack', None) is not None,
                rms_response_pending=getattr(driver, 'pending', None) is not None,
                partial_output_sha256=sha(raw), partial_output_bytes=len(raw),
                output_published=driver.output.published,
                completed_stages=len(report['terminals']),
                cause=dict(type=type(error).__name__, message=str(error)),
                automatically_drained=False, resumable_checkpoint=False)
            report.update(status='INTERRUPTED', active_stage=stage)
            raise PrefixExecutionError(error, report, snapshot, raw,
                driver.history_out.raw() if hasattr(driver, 'history_out') else None) from error
        status = driver.response.status if stage == 'input_norm' else driver.response[1]
        details = driver.report()
        report['stages'].append(dict(stage=stage, host_seconds=time.monotonic() - started, report=details))
        report['terminals'].append(dict(stage=stage, status=status))
        require(memory.pending is None, 'terminal before shared memory drain')
        require(all(part.published and sha(part.raw()) == digest for part, digest in published),
                'old public tensor overwritten or publication revoked')
        if status is not None:
            require(not driver.output.published, 'failed owner published output')
            report.update(status='FAILED', failed_stage=stage)
            return False
        require(driver.output.published, 'successful terminal without actual output publication')
        published.append((driver.output, sha(driver.output.raw())))
        if observe is not None:
            observe(stage, details, driver.output.raw())
        return True

    initial=rms.TypedRmsDriver(rms_owner,memory,rms.RmsJob(35101,input_base,weight_base,rms_base,tokens))
    if not run('input_norm',initial):return report,memory
    report['actual_rms_output_sha256']=sha(initial.output.raw())
    for index,(name,b_base,d_base) in enumerate(packed):
        require(memory.exact(rms_base,len(hidden),readable=True) is initial.output,'projection must consume same actual RMS producer')
        job=dense.down.Job(m=tokens,k=2048,n=32,tag=35102+index,a=rms_base,b=b_base,dst=d_base,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=tokens*64)
        driver=TypedLargeKProjectionDriver(projection_owner,matrix,memory,job,
            vector=vector,profile=profiles[name],sum_identity=36102+index)
        if not run(name,driver):return report,memory
    require(resources==(id(memory),id(scalar),id(rms_owner),id(projection_owner),id(projection_owner.a_banks),
        id(projection_owner.b_banks),matrix.resource_address,vector.resource_address),'execution resource replaced')
    require(matrix.owner is None and vector.client is None and scalar.client is None and memory.pending is None and not projection_owner.tiles.leased,'resources not retired')
    report.update(status='PASS_TYPED_AB_EXECUTION_ONLY',actual_rms_region_consumed_by_both=True,
        shared_resources_unchanged=True,all_old_outputs_unchanged=True,matrix_service=matrix.report(),
        scalar_operations=dict(scalar.calls),combined_ab_tensor_materialized=False)
    return report,memory
