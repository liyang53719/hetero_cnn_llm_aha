"""Actual H2048 RMS writes consumed by the existing K2048 projection driver.

This is a typed-software prefix using one byte map, Matrix, Vector and Scalar.
Columns may select original Q/K/V windows for bounded debugging or all8192.
A selected window is never presented as a complete QKV/block execution or a
small-shape official operator. Native comparisons belong after real terminals.
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
from .projection_owner import LargeKProjectionOwner, PrefixWorkspace
from .projection_driver import TypedLargeKProjectionDriver

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


def execute_prefix(hidden, norm_weight, qkv_nk, *, tokens, windows, profile,
                   matrix, vector, deadline, memory=None, controls=None, observe=None,
                   conv_weights=None, conv_observe=None):
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
    scalar = rms.SharedScalar() if conv_weights is None else conv.ConvScalar()
    rms_owner = rms.RmsOwner(scalar)
    # This K2048 job uses resident partials. The legacy prefix spill condition
    # must not advertise split_k=128 and accidentally require N-dependent DDR.
    projection_owner = LargeKProjectionOwner(PrefixWorkspace(0x100000000, 16384, 1, split_k=2048))
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
    report = dict(scope='ACTUAL_TYPED_H2048_RMS_TO_K2048_QKV_WINDOWS', status='RUNNING',
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
        status = driver.response.status if stage in ('input_norm', 'conv4_silu') else driver.response[1]
        details = driver.report()
        report['stages'].append(dict(stage=stage, host_seconds=time.monotonic() - started, report=details))
        report['terminals'].append(dict(stage=stage, status=status))
        require(memory.pending is None, 'terminal before shared memory drain')
        require(all(part.published and sha(part.raw()) == digest for part, digest in published),
                'old public tensor overwritten or publication revoked')
        if status is not None:
            require(not driver.output.published, 'failed owner published output')
            report.update(status='FAILED', failed_stage=stage)
            if stage == 'conv4_silu':
                error = RuntimeError('Conv owner returned '+str(status))
                raise PrefixExecutionError(error, report, dict(stage=stage, owner_report=details,
                    terminal_accepted=True, output_published=False, history_published=False,
                    automatically_drained=False, resumable_checkpoint=False),
                    driver.output.raw(), driver.history_out.raw())
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
        driver = TypedLargeKProjectionDriver(projection_owner, matrix, memory, job,
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
    require(resources == (id(memory), id(scalar), id(rms_owner), id(projection_owner),
                 id(projection_owner.a_banks), id(projection_owner.b_banks),
                 matrix.resource_address, vector.resource_address), 'execution resource replaced')
    require(matrix.owner is None and vector.client is None and scalar.client is None and
            memory.pending is None and not projection_owner.tiles.leased, 'prefix resource not retired')
    report.update(status='PASS_TYPED_PREFIX_EXECUTION_ONLY', shared_resources_unchanged=True,
                  actual_rms_region_consumed=True, all_old_outputs_unchanged=True,
                  matrix_service=matrix.report(), scalar_operations=dict(scalar.calls),
                  hardware_utilization=None, busy_duty=None, active_lane_duty=None,
                  stall_breakdown=None, overlap_timeline=None)
    return report, memory
