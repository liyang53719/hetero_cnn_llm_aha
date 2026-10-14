"""One-memory/one-Scalar real RMS, full QKV/Conv, A/B packing and Prep.

Software transactions and arithmetic only; state history remains unpublished.
Explicit35B gate-output policy preserves finite nonpositive FP32 g without
clipping. It does not admit downstream chunk/exp or an official Prep tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time

from ..qwen35_35b_rms import owner as rms
from ..qwen35_gdn_prefill import typed_dense as dense
from ..qwen35_gdn_prefill.conv import model as conv
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
from ..qwen35_35b_prefill.projection_owner import LargeKProjectionOwner, PrefixWorkspace
from ..qwen35_35b_prefill.projection_driver import TypedLargeKProjectionDriver

from ..qwen35_gdn_prefill.prep import model as prep
from ..qwen35_gdn_prefill.prep.scalar import PrepScalar
from ..qwen35_35b_payload.packer import raw_nk_to_kn
from .pack import TypedABPackDriver
from . import chunk_stage
from ..qwen35_gdn_prefill.gated_norm import model as gated_norm
from ..qwen35_35b_gated_norm.core_publication import publish_core_intermediate
from ..qwen35_35b_output import stage as output_stage
from ..qwen35_35b_output.driver import TypedStreamingUpstreamDriver
from ..qwen35_35b_postnorm import stage as postnorm_stage

WIDTH, OUTPUTS = 2048, 8192


def require(condition, detail):
    if not condition:
        raise ValueError('35B RMS/projection prefix: ' + detail)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PrefixExecutionError(RuntimeError):
    """Interrupted invocation retains actual state; this does not retire DMA."""
    def __init__(self, error, report, snapshot, raw, history_raw=None):
        super().__init__(str(error))
        self.execution_report, self.snapshot, self.partial_output = report, snapshot, raw
        self.partial_history = history_raw


@dataclass(frozen=True)
class ColumnWindow:
    start: int
    columns: int

    def validate(self):
        require(type(self.start) is int and type(self.columns) is int and
                self.start >= 0 and self.start % 32 == 0 and
                self.columns > 0 and self.columns % 32 == 0 and
                self.start + self.columns <= OUTPUTS, 'original NK column window extent')


def pack_window(raw_nk, window):
    """Only bitwise BF16 NK→KN packing; no arithmetic or oracle values."""
    import numpy as np
    require(type(raw_nk) is bytes and len(raw_nk) == OUTPUTS * WIDTH * 2,
            'complete original BF16[8192,2048] weight required')
    require(type(window) is ColumnWindow, 'exact immutable column selection')
    window.validate()
    nk = np.frombuffer(raw_nk, '<u2').reshape(OUTPUTS, WIDTH)
    return nk[window.start:window.start + window.columns].T.copy().tobytes()


def execute_prep_prefix(hidden, norm_weight, qkv_nk, *, tokens, windows, profile,
                   matrix, vector, deadline, memory=None, controls=None, observe=None,
                   conv_weights=None, conv_observe=None, ab_weights=None, ab_profiles=None, a_log=None, dt_bias=None, reduction_policy=prep.ASCENDING,gate_policy=prep.FINITE_GATE_35B, run_chunk=False, chunk_progress=None, on_chunk_interrupt=None, z_weight=None, z_profile=None, gated_weight=None, o_weight=None, o_profile=None, postnorm_weight=None, postnorm_observe=None, chunk_matmul_policy=chunk_stage.c.LEGACY_MATMUL):
    """Run original owners to terminal; callback observes only real publication.

    controls(stage,index,driver) may provide existing driver handshake/fault
    controls. No result injection interface exists. A failed or aborted owner
    stops the prefix and prevents admission of all later consumers. Already
    published stateless intermediates remain valid; this is not a stateful
    complete-block commit/fence or public Command128 program decoder.
    """
    require(type(tokens) is int and tokens in (16, 128), 'current Dense M16/M128')
    require(type(hidden) is bytes and len(hidden) == tokens * WIDTH * 2 and
            type(norm_weight) is bytes and len(norm_weight) == WIDTH * 2,
            'raw BF16 hidden/norm weight extents')
    require(type(qkv_nk) is bytes and len(qkv_nk) == WIDTH * OUTPUTS * 2,
            'complete original NK projection weight extent')
    require(type(windows) is tuple and windows and all(type(w) is ColumnWindow for w in windows),
            'explicit immutable original output columns')
    for window in windows:
        window.validate()
    spans = sorted((w.start, w.start + w.columns) for w in windows)
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'overlapping output windows')
    require(type(profile) is ReductionProfile and profile.ranges == ((0, 1024), (1024, 2048)) and
            profile.pair_reverse is True, 'explicit two-K1024 pair profile required')
    profile.validate(WIDTH)
    require(type(matrix) is dense.MatrixService and matrix.owner is None and
            type(vector) is Vector16 and vector.client is None and vector.exception_policy == IEEE_POLICY,
            'same drained actual Matrix and finite-IEEE Vector16 required')
    memory = dense.TypedMemory() if memory is None else memory
    require(type(memory) is dense.TypedMemory and memory.pending is None and not memory.regions,
            'fresh shared physical memory map for this prefix')
    require(controls is None or callable(controls), 'optional handshake/fault controls')
    require(observe is None or callable(observe), 'optional terminal observer')
    require(type(deadline) in (int, float) and deadline > time.monotonic(), 'bounded wall deadline')
    require(conv_weights is None or type(conv_weights) is bytes and len(conv_weights) == OUTPUTS * 8,
            'complete BF16 Conv4 weight required')
    require(conv_weights is None or windows == (ColumnWindow(0, OUTPUTS),),
            'Conv requires actual complete original QKV')
    require(conv_observe is None or callable(conv_observe), 'optional immutable Conv observer')
    require(conv_weights is not None, 'complete Conv producer required')
    require(type(ab_weights) is dict and set(ab_weights)=={'a','b'} and all(type(v) is bytes and len(v)==131072 for v in ab_weights.values()), 'complete A/B weights')
    require(type(ab_profiles) is dict and set(ab_profiles)=={'a','b'}, 'separate N32 profiles')
    for policy in ab_profiles.values():
        require(type(policy) is ReductionProfile and policy.ranges==((0,1024),(1024,2048)) and policy.pair_reverse, 'N32 pair policy')
        policy.validate(WIDTH)
    require(type(a_log) is bytes and len(a_log)==128 and type(dt_bias) is bytes and len(dt_bias)==64, 'original parameter extents')
    require(type(run_chunk) is bool and (not run_chunk or gate_policy==prep.DUAL_EXP_GATE_35B), 'chunk requires explicit shared IEEE GateScalar')
    require(chunk_matmul_policy in chunk_stage.c.MATMUL_POLICIES and (run_chunk or chunk_matmul_policy==chunk_stage.c.LEGACY_MATMUL), 'explicit chunk matmul policy')
    require(chunk_progress is None or callable(chunk_progress), 'optional progress observer')
    run_norm = z_weight is not None or gated_weight is not None or z_profile is not None
    require(not run_norm or (run_chunk and type(z_weight) is bytes and len(z_weight)==4096*2048*2 and
        type(gated_weight) is bytes and len(gated_weight)==512 and type(z_profile) is ReductionProfile), 'complete Z/norm inputs and chunk required')
    run_o=o_weight is not None or o_profile is not None
    require(not run_o or (run_norm and type(o_weight) is bytes and len(o_weight)==2048*4096*2 and type(o_profile) is output_stage.FourProfile), 'O requires complete weight/profile and actual norm stage')
    if run_o:o_profile.validate(4096)
    if run_norm:
        require(z_profile.ranges==((0,1024),(1024,2048)) and z_profile.pair_reverse, 'explicit independently calibrated N4096 profile')
        z_profile.validate(WIDTH)
    scalar = prep.GateScalar(enable_softplus=True,enable_ieee_exp=True,enable_gate_softplus=True) if gate_policy==prep.DUAL_EXP_GATE_35B else PrepScalar(enable_softplus=True)
    require(postnorm_observe is None or callable(postnorm_observe), "postnorm observer callback")
    def rms_observe(stage,token,words):
        if rms_owner.job.tag==35602:
            postnorm_observe(stage,token,words)
    rms_owner = rms.RmsOwner(scalar, rms_observe if postnorm_observe is not None else None)
    # This K2048 job uses resident partials. The legacy prefix spill condition
    # must not advertise split_k=128 and accidentally require N-dependent DDR.
    projection_owner = (output_stage.StreamingProjectionOwner(output_stage.NoPrefixWorkspace(0x100000000,16384,1)) if run_o else LargeKProjectionOwner(PrefixWorkspace(0x100000000,16384,1,split_k=2048)))
    projection_driver_type=TypedStreamingUpstreamDriver if run_o else TypedLargeKProjectionDriver
    resources = (id(memory), id(scalar), id(rms_owner), id(projection_owner),
                 id(projection_owner.a_banks), id(projection_owner.b_banks),
                 matrix.resource_address, vector.resource_address)
    cursor = 0x100000

    def region(raw=None, size=None):
        nonlocal cursor
        extent = len(raw) if raw is not None else size
        address = cursor
        cursor += (extent + 63) // 64 * 64 + 64
        require(cursor < 0x100000000, 'prefix tensor overlaps workspace')
        if raw is not None:
            memory.add_readonly(address, raw)
        else:
            memory.allocate_output(address, extent)
        return address

    input_base, weight_base = region(hidden), region(norm_weight)
    rms_base = region(size=len(hidden))
    packed = [(window, region(pack_window(qkv_nk, window)), region(size=tokens * window.columns * 2))
              for window in windows]
    require(postnorm_weight is None or (run_o and type(postnorm_weight) is bytes and len(postnorm_weight)==4096),
            'postnorm requires full O chain and original H2048 weight')
    report = dict(scope='ACTUAL_TYPED_RMS_QKV_CONV_AB_PACK_PREP_SOFTWARE', status='RUNNING',
                  tokens=tokens, conv4_requested=conv_weights is not None, full_qkv=windows == (ColumnWindow(0, OUTPUTS),),
                  full_block=False, official_model_profile_admitted=False,
                  command128_executed=False, rtl_executed=False, hardware_cycles=None,
                  source_hashes=dict(hidden=sha(hidden), norm_weight=sha(norm_weight), qkv_nk=sha(qkv_nk)),
                  numerical_profile=vars(profile),
                  fixed_resources=dict(matrix_macs=4096, vector_lanes=16, scalar_units=1),
                  terminals=[], stages=[], output_columns=[vars(w) for w in windows])
    published = []

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
        status = driver.response.status if stage in ('input_norm', 'conv4_silu', 'ab_pack', 'prep','gated_norm','attention_residual','post_attention_norm') else driver.response[1]
        details = driver.report()
        report['stages'].append(dict(stage=stage, host_seconds=time.monotonic() - started, report=details))
        report['terminals'].append(dict(stage=stage, status=status))
        require(memory.pending is None, 'terminal before shared memory drain')
        require(all(part.published and sha(part.raw()) == digest for part, digest in published),
                'old public tensor overwritten or publication revoked')
        if status is not None:
            require(not driver.output.published, 'failed owner published output')
            report.update(status='FAILED', failed_stage=stage)
            if stage in ('conv4_silu','gated_norm','attention_residual','post_attention_norm'):
                error = RuntimeError(stage+' owner returned '+str(status))
                raise PrefixExecutionError(error, report, dict(stage=stage, owner_report=details,
                    terminal_accepted=True, output_published=False, history_published=False,
                    automatically_drained=False, resumable_checkpoint=False),
                    driver.output.raw(), driver.history_out.raw() if hasattr(driver,'history_out') else None)
            return False
        require(driver.output.published, 'successful terminal without actual output publication')
        published.append((driver.output, sha(driver.output.raw())))
        if observe is not None:
            observe(stage, details, driver.output.raw())
        return True

    initial = rms.TypedRmsDriver(rms_owner, memory, rms.RmsJob(35001, input_base, weight_base, rms_base, tokens))
    if not run('input_norm', initial):
        return report, memory
    report['actual_rms_output_sha256'] = sha(initial.output.raw())
    for index, (window, b_base, d_base) in enumerate(packed):
        require(memory.exact(rms_base, len(hidden), readable=True) is initial.output,
                'projection did not consume actual published RMS region')
        job = dense.down.Job(m=tokens, k=WIDTH, n=window.columns, tag=35002 + index,
                             a=rms_base, b=b_base, dst=d_base, activation_bf16=True,
                             weight_bf16=True, output_bf16=True, write_bytes=tokens * window.columns * 2)
        driver = projection_driver_type(projection_owner, matrix, memory, job,
                    vector=vector, profile=profile, sum_identity=36002 + index)
        if not run('qkv_columns_' + str(window.start), driver):
            return report, memory
    if conv_weights is not None:
        qkv_base = packed[0][2]
        qkv_region = memory.exact(qkv_base, tokens * OUTPUTS * 2, readable=True)
        require(qkv_region is driver.output and qkv_region.published,
                'Conv did not receive actual complete QKV producer region')
        conv_weight_base = region(conv_weights)
        conv_out = region(size=tokens * OUTPUTS * 2)
        history_in = region(bytes(OUTPUTS * 8))
        history_out = region(size=OUTPUTS * 8)
        conv_owner = conv.ConvOwner(scalar, channels=OUTPUTS, observe=conv_observe)
        job = conv.ConvJob(35090, qkv_base, conv_weight_base, conv_out,
                          history_in, history_out, tokens, True, 0, channels=OUTPUTS)
        conv_driver = conv.TypedConvDriver(conv_owner, memory, job, current_generation=0)
        require(conv_driver.input is qkv_region and conv_owner.scalar is rms_owner.scalar,
                'Conv producer/scalar identity changed')
        if not run('conv4_silu', conv_driver):
            return report, memory
        require(not conv_driver.history_out.published and conv_driver.response.generation == 0 and not conv_driver.response.history_committed,
                'Conv local completion must not commit block state')
        report['conv_history_staging'] = dict(sha256=sha(conv_driver.history_out.raw()),
            bytes=OUTPUTS*8, address=history_out, published=False, generation_advanced=False)
        report['actual_qkv_region_consumed'] = True
        if observe is not None:
            observe('conv_history_staging', dict(published=False, generation_advanced=False),
                    conv_driver.history_out.raw())
    ab_producers={}
    for i,name in enumerate(('a','b')):
        b_base=region(raw_nk_to_kn(ab_weights[name],32,WIDTH));d_base=region(size=tokens*64)
        require(memory.exact(rms_base,len(hidden),readable=True) is initial.output, 'A/B actual RMS identity')
        job=dense.down.Job(m=tokens,k=WIDTH,n=32,tag=35102+i,a=rms_base,b=b_base,dst=d_base,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=tokens*64)
        ab_driver=projection_driver_type(projection_owner,matrix,memory,job,vector=vector,
            profile=ab_profiles[name],sum_identity=36102+i)
        if not run(name,ab_driver):return report,memory
        ab_producers[name]=ab_driver.output
    packed_ab_base=region(size=tokens*128)
    pack_driver=TypedABPackDriver(memory,ab_producers['a'].base,ab_producers['b'].base,packed_ab_base,tokens)
    require(pack_driver.sources[0] is ab_producers['a'] and pack_driver.sources[1] is ab_producers['b'], 'pack actual A/B identity')
    if not run('ab_pack',pack_driver):return report,memory
    log_base,bias_base=region(a_log),region(dt_bias)
    core_base=region(size=tokens*prep.GROUPED_35B.core_row_bytes)
    prep_owner=prep.InputPrepOwner(scalar,heads=32,layout=prep.GROUPED_35B,gate_policy=gate_policy,reduction_policy=reduction_policy)
    prep_job=prep.InputPrepJob(35201,conv_out,packed_ab_base,log_base,bias_base,core_base,tokens,32,prep.GROUPED_35B,gate_policy,reduction_policy)
    prep_driver=prep.TypedInputPrepDriver(prep_owner,memory,prep_job)
    require(prep_driver.conv is conv_driver.output and prep_driver.ab is pack_driver.output and
        prep_owner.scalar is conv_owner.scalar is rms_owner.scalar,'Prep actual producers/one Scalar identity')
    if not run('prep',prep_driver):return report,memory
    require(not conv_driver.history_out.published and conv_driver.response.generation==0,'history must remain staging')
    report.update(actual_ab_producers_consumed=True,actual_conv_producer_consumed=True,
        actual_packed_ab_producer_consumed=True,history_published=False,prep_native_acceptance=False,
        ab_profiles={k:vars(v) for k,v in ab_profiles.items()},
        added_parameter_sha256={k:sha(v) for k,v in dict(ab_weights,a_log=a_log,dt_bias=dt_bias).items()})
    if run_norm:
        z_b=region(raw_nk_to_kn(z_weight,4096,WIDTH));z_d=region(size=tokens*4096*2)
        require(memory.exact(rms_base,len(hidden),readable=True) is initial.output, 'Z actual RMS identity')
        z_job=dense.down.Job(m=tokens,k=WIDTH,n=4096,tag=35251,a=rms_base,b=z_b,dst=z_d,
            activation_bf16=True,weight_bf16=True,output_bf16=True,write_bytes=tokens*4096*2)
        z_driver=projection_driver_type(projection_owner,matrix,memory,z_job,vector=vector,
            profile=z_profile,sum_identity=36251)
        if not run('z',z_driver):return report,memory
        report['z_profile']=vars(z_profile)
        report['z_weight_sha256']=sha(z_weight)
    if run_chunk:
        try:
            chunk_driver, chunk_details = chunk_stage.execute_chunk(memory,scalar,vector,prep_driver.output,region,
                tokens=tokens,deadline=deadline,controls=controls,progress=chunk_progress,on_interrupt=on_chunk_interrupt,matmul_policy=chunk_matmul_policy)
        except chunk_stage.ChunkInterrupted as error:
            report.update(status='INTERRUPTED',active_stage='chunk')
            error.execution_report=report
            raise
        report['stages'].append(dict(stage='chunk',host_seconds=chunk_details['host_seconds'],report=chunk_details))
        report['terminals'].append(dict(stage='chunk',status=chunk_driver.response.status))
        report['chunk_staging']=chunk_details
        require(all(part.published and sha(part.raw())==digest for part,digest in published), 'chunk changed prior public output')
        require(not conv_driver.history_out.published and conv_driver.response.generation==0,'chunk committed history')
        if observe is not None:
            observe('chunk',chunk_details,chunk_driver.output.raw())
            observe('chunk_state_staging',dict(published=False,generation_advanced=False),chunk_driver.state_out.raw())
            observe('chunk_scratch_staging',dict(published=False,base=chunk_driver.job.scratch,bytes=chunk_driver.job.scratch_bytes),chunk_driver.scratch.raw())
        if chunk_driver.response.status is not None:
            report.update(status='FAILED',failed_stage='chunk')
            return report,memory
    if run_norm:
        publication=publish_core_intermediate(chunk_driver,conv_driver.history_out,scalar,vector,tokens=tokens)
        core_digest=publication['core_sha256'];state_digest=publication['state_sha256']
        published.append((chunk_driver.output,core_digest))
        gamma=region(gated_weight);norm_out=region(size=tokens*8192)
        norm_owner=gated_norm.GatedNormOwner(scalar,heads=32,layout=prep.GROUPED_35B)
        norm_job=gated_norm.GatedNormJob(35401,chunk_driver.job.output,z_d,gamma,norm_out,tokens,32,prep.GROUPED_35B)
        norm_driver=gated_norm.TypedGatedNormDriver(norm_owner,memory,norm_job)
        require(norm_driver.core is chunk_driver.output and norm_driver.gate is z_driver.output and
            norm_owner.scalar is rms_owner.scalar,'norm actual core/Z and shared Scalar')
        report['core_intermediate_publication']=publication
        try:
            completed=run('gated_norm',norm_driver)
        finally:
            require(sha(chunk_driver.state_out.raw())==state_digest and not chunk_driver.state_out.published and
                sha(conv_driver.history_out.raw())==publication['history_sha256'] and not conv_driver.history_out.published and
                not chunk_driver.scratch.published and conv_driver.response.generation==0,
                'norm changed or committed block state/history')
        if not completed:return report,memory
        report['gated_weight_sha256']=sha(gated_weight)
    if run_o:
        o_b=region(raw_nk_to_kn(o_weight,2048,4096));o_out=region(size=tokens*2048*2)
        o_driver=output_stage.prepare_output_projection(norm_driver,projection_owner,matrix,memory,
            weight_base=o_b,output_base=o_out,tokens=tokens,scalar=scalar,vector=vector,profile=o_profile)
        try:
            completed=run('output_projection',o_driver)
        finally:
            require(sha(chunk_driver.state_out.raw())==state_digest and not chunk_driver.state_out.published and
                sha(conv_driver.history_out.raw())==publication['history_sha256'] and not conv_driver.history_out.published and
                not chunk_driver.scratch.published and conv_driver.response.generation==0,
                'O changed or committed block state/history')
        if not completed:return report,memory
        report['o_weight_sha256']=sha(o_weight)
        report['o_profile']=vars(o_profile)
        report['actual_norm_region_consumed']=True
    if postnorm_weight is not None:
        post_weight_base=region(postnorm_weight)
        residual_out=region(size=len(hidden));postnorm_out=region(size=len(hidden))
        preserved_banks=(id(rms_owner.row_bank),id(rms_owner.weight_bank),id(rms_owner.output_bank))
        matrix_before=matrix.report();vector_before=(dict(vector.calls),dict(vector.lane_ops))
        try:
            residual_driver=postnorm_stage.prepare_residual(o_driver,initial,memory,scalar,residual_out)
            require(residual_driver.a is memory.regions[input_base] and sha(residual_driver.a.raw())==sha(hidden),
                    'residual must consume unchanged original input before input RMS')
            if not run('attention_residual',residual_driver):return report,memory
            post_driver=postnorm_stage.prepare_postnorm(residual_driver,rms_owner,memory,scalar,
                post_weight_base,postnorm_out)
            if not run('post_attention_norm',post_driver):return report,memory
        finally:
            require(preserved_banks==(id(rms_owner.row_bank),id(rms_owner.weight_bank),id(rms_owner.output_bank)) and
                matrix.report()==matrix_before and (dict(vector.calls),dict(vector.lane_ops))==vector_before,
                'residual/postnorm changed RMS banks or used extra Matrix/Vector work')
            require(sha(chunk_driver.state_out.raw())==state_digest and not chunk_driver.state_out.published and
                sha(conv_driver.history_out.raw())==publication['history_sha256'] and not conv_driver.history_out.published and
                not chunk_driver.scratch.published and conv_driver.response.generation==0,
                'residual/postnorm changed or committed block state/history')
        report['postnorm_weight_sha256']=sha(postnorm_weight)
        report['same_rms_owner_and_banks_reused']=True
        report['residual_original_input_sha256']=sha(hidden)
        report['postnorm_matrix_vector_unchanged']=True
    require(resources == (id(memory), id(scalar), id(rms_owner), id(projection_owner),
                 id(projection_owner.a_banks), id(projection_owner.b_banks),
                 matrix.resource_address, vector.resource_address), 'execution resource replaced')
    require(matrix.owner is None and vector.client is None and scalar.client is None and
            memory.pending is None and not projection_owner.tiles.leased, 'prefix resource not retired')
    report.update(status='PASS_TYPED_POSTNORM_PREFIX_EXECUTION_ONLY' if postnorm_weight is not None else 'PASS_TYPED_OUTPUT_PREFIX_EXECUTION_ONLY' if run_o else 'PASS_TYPED_GATED_NORM_PREFIX_EXECUTION_ONLY' if run_norm else 'PASS_TYPED_CHUNK_STAGING_EXECUTION_ONLY' if run_chunk else 'PASS_TYPED_PREP_PREFIX_EXECUTION_ONLY', shared_resources_unchanged=True,
                  actual_rms_region_consumed=True, all_old_outputs_unchanged=True,
                  matrix_service=matrix.report(), scalar_operations=dict(scalar.calls),
                  hardware_utilization=None, busy_duty=None, active_lane_duty=None,
                  stall_breakdown=None, overlap_timeline=None)
    return report, memory
