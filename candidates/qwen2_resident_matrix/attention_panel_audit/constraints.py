"""Index/order/count audit of a proposed register loan; no datapath implementation."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('canonical bounded integer')
    return value


def panel_slot(head, key):
    return 128 + 16 * integer(head, 0, 5) + integer(key, 0, 15)


def v_slot(column):
    return integer(column, 0, 127)


def scratch_line(plane, head, first):
    if plane not in ('score', 'weight'):
        raise ValueError('plane')
    integer(first, 0, 127)
    if first % 16:
        raise ValueError('aligned panel')
    return (4096 if plane == 'score' else 4144) + 8 * integer(head, 0, 5) + first // 16


def location(line):
    integer(line, 4096, 4191)
    return (2 * (line % 8), 2 * (line % 8) + 1, line // 8)


class BorrowLedger:
    """Metadata-only proposed exclusive lease, not proof that flops survive synthesis."""
    def __init__(self):
        self.phase = 'idle'

    def acquire(self, *, native_idle, dense_drained, matrix_drained, scalar_drained, bank_drained):
        ready = (native_idle, dense_drained, matrix_drained, scalar_drained, bank_drained)
        if self.phase != 'idle' or any(x is not True for x in ready):
            raise ValueError('register loan requires all old obligations drained')
        self.phase = 'qk'

    def touch(self, role, index):
        integer(index, 0, 255)
        allowed = (self.phase == 'qk' and role == 'qk') or (
            self.phase in ('softmax', 'pv') and role == 'panel' and 128 <= index < 224) or (
            self.phase == 'pv' and role == 'v' and index < 128)
        if not allowed:
            raise ValueError('overlapping or out-of-phase register use')
        return index

    def begin_softmax(self, *, qk_drained, score_acks_complete):
        if self.phase != 'qk' or qk_drained is not True or score_acks_complete is not True:
            raise ValueError('QK/score commit fence')
        self.phase = 'softmax'

    def begin_pv(self, *, raw_weights_committed, reciprocal_acked):
        if self.phase != 'softmax' or raw_weights_committed is not True or reciprocal_acked is not True:
            raise ValueError('softmax row fence')
        self.phase = 'pv'

    def legacy_clear(self):
        if self.phase != 'idle':
            raise ValueError('whole-vector clear would destroy the borrowed panel')

    def release(self, *, matrix_drained, scalar_drained, bank_drained, outputs_acked):
        ready = (matrix_drained, scalar_drained, bank_drained, outputs_acked)
        if self.phase != 'pv' or any(x is not True for x in ready):
            raise ValueError('accepted debt remains')
        self.phase = 'idle'


def transfers(keys):
    """Full-line logical transactions for one query/KV-head; no payload cache."""
    integer(keys, 1, 128)
    firsts = range(0, keys, 16)
    # All heads' QK score writes and maximum observations finish first.
    for head in range(6):
        for first in firsts:
            yield ('score_write', scratch_line('score', head, first))
    for first in firsts:
        for head in range(6):
            yield ('score_read', scratch_line('score', head, first))
        # Ordered per-head sums run on this panel before its raw-weight write.
        for head in range(6):
            yield ('weight_write', scratch_line('weight', head, first))
    # Reciprocal is acknowledged after every raw-weight panel is committed.
    for first in firsts:
        for head in range(6):
            yield ('weight_read', scratch_line('weight', head, first))


def head_recipe(keys):
    """Events of one head, excluding other heads; no arithmetic callbacks."""
    integer(keys, 1, 128)
    for key in range(keys):
        yield ('qk8_fma_then16_fold_adds', key)
        yield ('dot_bf16_scale_fp32_score_bf16', key)
        yield ('ordered_max', key)
    for first in range(0, keys, 16):
        for key in range(first, min(first + 16, keys)):
            yield ('subtract_fp32', key)
            yield ('exp_original', key)
            yield ('ordered_sum_fp32', key)
    yield ('reciprocal_fp32', -1)
    for first in range(0, keys, 16):
        for key in range(first, min(first + 16, keys)):
            yield ('normalize_fp32', key)
            yield ('matrix_ingress_bf16', key)
            yield ('pv_fma_fp32', key)
    yield ('output_bf16', -1)


def report(tokens=128):
    integer(tokens, 1, 128)
    pairs = 12 * tokens * (tokens + 1) // 2
    head_panels = 12 * sum((n + 15) // 16 for n in range(1, tokens + 1))
    six_head_key_packets = pairs // 6
    six_head_rows = 2 * tokens
    result = dict(
        scope='CONDITIONAL_REGISTER_LOAN_INDEX_ORDER_AND_COUNT_AUDIT', tokens=tokens,
        causal_head_key_pairs=pairs, head_panels=head_panels,
        six_head_panels=head_panels // 6, scratch_transactions=4 * head_panels,
        scratch_reads=2 * head_panels, scratch_writes=2 * head_panels,
        physical_256bit_bank_reads=4 * head_panels,
        physical_256bit_bank_writes=4 * head_panels,
        scratch_bytes=4 * head_panels * 64,
        scratch_service_edge_floor=12 * head_panels,
        scratch_rmw_reads=0, normalized_weight_bank_writes=0,
        proposed_reused_words=256, pv_lower_words=128, panel_words=96,
        unused_upper_words=32, panel_payload_bits=96 * 32,
        alternative_explicit_panel_delta_bits=96 * 32,
        alternative_operand_staging_delta_bits=None,
        physical_stage_retention_verified=False, rtl_executed=False,
        actual_hardware_cycles=None, accepted_80=False, accepted_90=False,
        qk_fold_packets=16 * head_panels, qk_scale_packets=head_panels,
        proposed_vector_fold_scale_service_edges=34 * head_panels,
        softmax_six_head_key_packets=six_head_key_packets,
        softmax_reciprocal_packets=six_head_rows,
        # Each row has exp(0); at least one full-path packet per six-head row.
        softmax_service_floor_excluding_division=12 * six_head_key_packets + 17 * six_head_rows,
        softmax_all_full_exp_service_excluding_division=29 * six_head_key_packets,
        silu_vectors=tokens * 8960 // 16,
        silu_service_floor_excluding_division=15 * (tokens * 8960 // 16))
    if tokens == 128:
        ideal, matrix = 1468464, 1462272 + 8 * head_panels + six_head_key_packets
        def bound(cycles):
            return dict(conditional_minimum_edges=cycles,
                        useful_mac_utilization_ceiling_percent=float(Fraction(100 * ideal, cycles)))
        bank = result['scratch_service_edge_floor']
        fold = result['proposed_vector_fold_scale_service_edges']
        sm = result['softmax_service_floor_excluding_division']
        result.update(matrix_issue_floor=matrix, useful_macs=6014828544, macs_per_cycle=4096,
            serial_matrix_and_scratch_only=bound(matrix + bank),
            serial_plus_vector_fold_scale=bound(matrix + bank + fold),
            serial_plus_softmax_excluding_division=bound(matrix + bank + fold + sm),
            serial_plus_silu_excluding_divisions=bound(matrix + bank + fold + sm + result['silu_service_floor_excluding_division']))
    return result


def check_sources():
    pins = json.loads((HERE / 'source_pins.json').read_text())
    if set(pins) != {'schema', 'scope', 'sources'} or pins['schema'] != 1 or pins['scope'] != 'ATTENTION_PANEL_SOURCE_AUDIT':
        raise ValueError('pin schema')
    for name, expected in pins['sources'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('pin path')
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError('source changed: ' + name)
    return len(pins['sources'])


if __name__ == '__main__':
    check_sources()
    print(json.dumps(report(), indent=2, sort_keys=True))
