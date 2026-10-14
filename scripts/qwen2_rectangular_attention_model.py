#!/usr/bin/env python3
"""Pre-RTL, source-bound Qwen2 cold-prefill Attention event/traffic model.

This is a candidate schedule, NOT an implemented owner or a cycle predictor.
Only the already instantiated 16x256 Matrix, five contexts, existing scalar /
16-lane Vector and the original Dense A/B SRAM instances are available.
The event order supports one context or five interleaved QK stripe contexts.
PV keeps one live query tile and one context; no latency is assumed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
# Reviewed 3cd847d -> f16df50: the Qwen2 Host keeps both H2048 borrower
# switches false. Existing geometry, arithmetic and owner serialization
# are unchanged; these models do not cover the enabled borrower path.
SOURCE_PINS = {
    BASE + 'Protocol.scala': '5c94def481dede0195f989608c1827ded32f2d83c752617945695f7d82f64783',
    BASE + 'BlockFloat.scala': '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
    BASE + 'Qwen2Block.scala': '9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4',
    BASE + 'MatrixPipeline.scala': 'dd1f3859ac65fa4d4839105cf166cb5d3a1f4d2d786991eb0f22749ad4ceca3d',
    BASE + 'RetainedMatrix.scala': '80dc285af2208b3f3aa3d811a561cfe729e2c764b45c1da62de360f9578321bb',
    BASE + 'QwenOwnerProtocol.scala': '7f2b4a623b61b6e68478b2310d441ed04ccde1cd5490cb22205113f907b7974d',
    BASE + 'DenseReadPlanner.scala': '0f4c981b32170344c316e0b8dfe6296f2f497d4901365e05e0b9d730d1fd1886',
    BASE + 'StreamingDense.scala': '18d99633b57e5f394f99c242231a5ee009dcf125c03c8940674a01a7965ee789',
    BASE + 'BurstProtocol.scala': '0f2720e741af302952854b7787f63b4df55b9437048f818319f2cecf16034aac',
    'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv':
        'a4c37b485f1e7eeed3012372024e8e7207bc33af6ff97bc307a5572aced6890e',
    'integration/gemmini/EmitHeteroBF16Fma.scala':
        '9df0c5c2b499783dbf471cdf9bed3f1373a34c6713626a1c93d059e70e7a460f',
    'integration/gemmini/EmitHeteroFP32Alu.scala':
        '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1',
    'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv':
        'ad985950e9129c524f685385dac75db9f3bd4ca632e125f7e1b54103271fb418',
    'rtl/integration/qwen2_matrix_command_endpoint.sv':
        '057ce15d3b9fd5153c8873498f9cf1b3f17d7eea64e8928c1208496b3d0bd53a',
}
HEADS, KV_HEADS, HD = 12, 2, 128
ROWS, COLS, STRIPES, CONTEXTS = 16, 256, 16, 5
A_BYTES, B_BYTES = 704512, 81920


def _tokens(tokens):
    if type(tokens) is not int or not 1 <= tokens <= 1024:
        raise ValueError('cold-prefill tokens must be an integer in 1..1024')


def kv_head(head):
    if type(head) is not int or not 0 <= head < HEADS:
        raise ValueError('Q head must be in 0..11')
    return head // 6


def qk_tiles(tokens, head=0):
    """Each physical row is a query; each physical column is one key.

    The causal mask is write/reduce validity, not an available MAC lane gate.
    Columns are enabled at the real 32-column slice granularity.
    """
    _tokens(tokens)
    for qbase in range(0, tokens, ROWS):
        rows = min(ROWS, tokens - qbase)
        for kbase in range(0, qbase + rows, COLS):
            needed = min(COLS, qbase + rows - kbase)
            cols = (needed + 31) // 32 * 32
            masks = [max(0, min(cols, qbase + r - kbase + 1))
                     if r < rows else 0 for r in range(ROWS)]
            yield dict(head=head, kv_head=kv_head(head), qbase=qbase,
                       kbase=kbase, rows=rows, columns=cols,
                       slice_mask=(1 << (cols // 32)) - 1,
                       causal_valid_columns=masks, useful_pairs=sum(masks))


def pv_tiles(tokens, head=0):
    _tokens(tokens)
    for qbase in range(0, tokens, ROWS):
        rows = min(ROWS, tokens - qbase)
        yield dict(head=head, kv_head=kv_head(head), qbase=qbase, rows=rows,
                   keys=qbase + rows, columns=HD, slice_mask=0x0f,
                   useful_pairs=sum(qbase + r + 1 for r in range(rows)))


def scratch_layout(tokens, contexts=1):
    """Retain the actual 1376/160 word bank depths; no flat SRAM fiction.

    All objects use row modulo 16 as bank, and contiguous words within that
    row. K/V remain token-major, so K column gathering costs multiple bank
    accesses. QK C and PV final captures are disjoint in time and alias B.
    """
    _tokens(tokens)
    if contexts not in (1, 5):
        raise ValueError('supported QK context counts are 1 and 5')
    objects = []
    next_word = 0
    for name, rows, columns, size in (
        ('q', 16, 128, 2), ('k', tokens, 128, 2),
        ('v', tokens, 128, 2), ('score', 16, tokens, 4),
        ('prob', 16, tokens, 4),
    ):
        row_words = (columns * size + 31) // 32
        bank_words = (rows + 15) // 16 * row_words
        objects.append(dict(name=name, bank_group='A', base_word=next_word,
                            words_per_bank=bank_words, rows=rows,
                            columns=columns, bytes_per_element=size,
                            row_words=row_words, allocated_bytes=bank_words*512))
        next_word += bank_words
    objects.append(dict(name='partial_or_pv_capture', bank_group='B', base_word=0,
                        words_per_bank=32*contexts, rows=16*contexts, columns=256,
                        bytes_per_element=4, row_words=32, allocated_bytes=16384*contexts))
    if next_word > 1376:
        raise ValueError('candidate exceeds existing A SRAM bank depth')
    return dict(objects=objects, used_a_bytes=next_word*512,
                used_b_bytes=16384*contexts, used_total_bytes=next_word*512+16384*contexts,
                allocated_a_bytes=A_BYTES, allocated_b_bytes=B_BYTES,
                allocated_total_bytes=A_BYTES+B_BYTES,
                separate_core_sram_bytes=573440, separate_elementwise_sram_bytes=12288,
                separate_legacy_score_prob_bytes=8192,
                borrow_separate_core_or_elementwise_sram=False,
                existing_accumulator_bytes=5*16*256*4,
                existing_matrix_result_fifo_bytes=2*16*256*4,
                additional_data_sram_bytes=0, additional_matrix_or_sfu=0,
                extra_control_state_and_routing_area='not synthesized or costed')


def scratch_address(layout, name, row, column):
    obj = next(o for o in layout['objects'] if o['name'] == name)
    if not (0 <= row < obj['rows'] and 0 <= column < obj['columns']):
        raise ValueError('scratch tensor index outside allocation')
    byte = column * obj['bytes_per_element']
    return (obj['bank_group'], row % 16,
            obj['base_word'] + row//16 * obj['row_words'] + byte//32, byte % 32)


def iter_events(tokens, contexts=1):
    """A dependency sequence, with NO cycle timestamps or free overlap.

    Group clear/last/finish and returning metadata follow MatrixPipeline.
    Scratch read/gather, issue, return, capture/store and ACK are ordered.
    A context has to return before it can be issued again. No accumulator
    seed exists or is needed: QK stripes start at +0, PV runs without splitting.
    """
    _tokens(tokens)
    scratch_layout(tokens, contexts)
    yield dict(event='owner_acquire', requires='Dense idle, Matrix drained, prior write ACKs')
    group = 0
    for kv in range(KV_HEADS):
        yield dict(event='load_kv', kv_head=kv, external_fp32_bytes=2*tokens*HD*4,
                   scratch_bf16_bytes=2*tokens*HD*2, requires='load ACK before reuse')
        for head in range(kv*6, (kv+1)*6):
            tiles = list(qk_tiles(tokens, head))
            for pv in pv_tiles(tokens, head):
                qbase, rows = pv['qbase'], pv['rows']
                yield dict(event='load_q', head=head, qbase=qbase,
                           external_fp32_bytes=rows*HD*4, scratch_bf16_bytes=rows*HD*2)
                for tile in (t for t in tiles if t['qbase'] == qbase):
                    for stripe_base in range(0, STRIPES, contexts):
                        stripes = list(range(stripe_base, min(16, stripe_base+contexts)))
                        group += 1
                        common = dict(phase='QK', group=group, head=head,
                                      qbase=qbase, kbase=tile['kbase'])
                        yield dict(common, event='group_start', opcode=0x23,
                                   slice_mask=tile['slice_mask'])
                        for step in range(HD//STRIPES):
                            # Distinct contexts can be pending together. Return
                            # each before its next step; no guessed latency.
                            for context, stripe in enumerate(stripes):
                                detail = dict(common, context=context, stripe=stripe)
                                depth = stripe + step*STRIPES
                                yield dict(detail, event='operand_gather', depth=depth,
                                           q_bank_word_reads=rows,
                                           k_bank_word_reads=min(tile['columns'], tokens-tile['kbase']),
                                           same_a_bank_reads_serialized=True)
                                yield dict(detail, event='matrix_issue', depth=depth,
                                           clear=step == 0, last=step == 7,
                                           finish=step == 7 and context == len(stripes)-1,
                                           emit=step == 7, useful_macs=tile['useful_pairs'],
                                           executed_macs=ROWS*tile['columns'])
                            for context, stripe in enumerate(stripes):
                                detail = dict(common, context=context, stripe=stripe)
                                yield dict(detail, event='matrix_return', emit=step == 7,
                                           returned_value_finite_check='causal stripe partials' if step == 7 else None)
                                if step == 7:
                                    yield dict(detail, event='partial_store',
                                               bytes=ROWS*tile['columns']*4, slot=context,
                                               uses='existing result FIFO; drain before next emitted return')
                        for context, stripe in enumerate(stripes):
                            detail = dict(common, context=context, stripe=stripe)
                            yield dict(detail, event='ordered_stripe_add',
                                       fp32_adds=tile['useful_pairs'], initial_positive_zero=stripe == 0,
                                       causal_valid_columns=tile['causal_valid_columns'])
                            yield dict(detail, event='partial_release', slot=context)
                        yield dict(common, event='group_done')
                yield dict(event='scale_and_softmax', head=head, qbase=qbase,
                           rows=rows, useful_pairs=pv['useful_pairs'],
                           key_order='ascending', arithmetic='existing FP32 scalar recipe',
                           masked_keys='not read, reduced, exponentiated or normalized')
                group += 1
                common = dict(phase='PV', group=group, context=0, head=head, qbase=qbase)
                yield dict(common, event='group_start', opcode=0x24, slice_mask=0x0f)
                for key in range(pv['keys']):
                    valid = [r for r in range(rows) if key <= qbase+r]
                    final = [r for r in valid if key == qbase+r]
                    yield dict(common, event='operand_gather', key=key,
                               probability_bank_word_reads=len(valid), v_bank_word_reads=8,
                               same_a_bank_reads_serialized=True)
                    yield dict(common, event='matrix_issue', key=key,
                               clear=key == 0, last=key == pv['keys']-1,
                               finish=key == pv['keys']-1, emit=bool(final),
                               valid_rows=valid, row_final=final,
                               useful_macs=len(valid)*HD, executed_macs=ROWS*HD)
                    yield dict(common, event='matrix_return', key=key, emit=bool(final),
                               returned_value_finite_check_rows=final)
                    if final:
                        yield dict(common, event='capture_final_row', key=key, rows=final,
                                   bytes=len(final)*HD*4,
                                   requires='returning key tag; never capture padded suffix')
                yield dict(common, event='group_done')
                yield dict(event='output_write', head=head, qbase=qbase, bytes=rows*HD*4)
                yield dict(event='output_ack', head=head, qbase=qbase)
    yield dict(event='owner_release', requires='all output writes acknowledged, Matrix drained')


def calculate(tokens, contexts=1):
    if type(tokens) is not int or tokens not in (128, 1024):
        raise ValueError('public reports support M128 and M1024 cold prefill only')
    qk, pv = list(qk_tiles(tokens)), list(pv_tiles(tokens))
    pairs = HEADS * sum(t['useful_pairs'] for t in qk)
    qk_steps = HEADS*len(qk)*HD
    pv_steps = HEADS*sum(t['keys'] for t in pv)
    qk_executed = HEADS*sum(ROWS*t['columns']*HD for t in qk)
    pv_executed = pv_steps*ROWS*HD
    wide_steps = qk_steps+pv_steps
    scalar_requests = 21*pairs+HEADS*tokens
    partial_store = HEADS*sum(16*ROWS*t['columns']*4 for t in qk)
    # Conservative element-at-a-time RMW below deliberately does not count
    # a 32 B bank access as 32 B of useful FP32 or BF16 payload.
    traffic = dict(
        external_q_fp32_read_bytes=HEADS*tokens*HD*4,
        external_kv_fp32_read_bytes=2*KV_HEADS*tokens*HD*4,
        external_output_fp32_write_bytes=HEADS*tokens*HD*4,
        external_partial_or_score_bytes=0,
        scratch_qkv_bf16_load_payload_bytes=(HEADS+2*KV_HEADS)*tokens*HD*2,
        qk_q_read_payload_bytes=qk_steps*ROWS*2,
        qk_q_read_bank_bytes=qk_steps*ROWS*32,
        qk_k_read_payload_bytes=HEADS*HD*sum(t['columns']*2 for t in qk),
        qk_k_read_bank_bytes=HEADS*HD*sum(t['columns']*32 for t in qk),
        partial_store_payload_bytes=partial_store,
        partial_store_bank_bytes=partial_store,
        partial_reduce_read_payload_bytes=pairs*16*4,
        partial_reduce_read_bank_bytes=pairs*16*32,
        score_reduction_read_payload_bytes=pairs*15*4,
        score_reduction_write_payload_bytes=pairs*16*4,
        score_scale_read_write_payload_bytes=pairs*8,
        score_softmax_read_payload_bytes=pairs*4,
        probability_exp_write_payload_bytes=pairs*4,
        probability_normalize_read_write_payload_bytes=pairs*8,
        pv_probability_read_payload_bytes=pairs*4,
        pv_probability_read_bank_bytes=pairs*32,
        pv_v_read_payload_bytes=pv_steps*HD*2,
        pv_v_read_bank_bytes=pv_steps*HD*2,
        pv_final_capture_write_payload_bytes=HEADS*tokens*HD*4,
        pv_final_capture_read_payload_bytes=HEADS*tokens*HD*4,
    )
    # Score/prob accesses are scalar RMW transactions on the same bank ports.
    # Each FP32 write reads then writes its containing 32 B word; do not assume
    # new byte-write SRAM support. Full-word C/load stores need no RMW.
    score_reads = pairs*(15+1+1+1)  # reduction, scaling, softmax, normalization
    score_writes = pairs*(16+1+1+1)  # reduction, scaling, exp, normalization
    traffic['score_prob_scalar_bank_read_bytes'] = (score_reads+score_writes)*32
    traffic['score_prob_scalar_bank_write_bytes'] = score_writes*32
    traffic['a_bank_read_total_bytes'] = sum(traffic[n] for n in (
        'qk_q_read_bank_bytes', 'qk_k_read_bank_bytes', 'score_prob_scalar_bank_read_bytes',
        'pv_probability_read_bank_bytes', 'pv_v_read_bank_bytes'))
    traffic['a_bank_write_total_bytes'] = (traffic['scratch_qkv_bf16_load_payload_bytes']
                                          + traffic['score_prob_scalar_bank_write_bytes'])
    traffic['b_bank_read_total_bytes'] = (traffic['partial_reduce_read_bank_bytes']
                                         + traffic['pv_final_capture_read_payload_bytes'])
    traffic['b_bank_write_total_bytes'] = (traffic['partial_store_bank_bytes']
                                          + traffic['pv_final_capture_write_payload_bytes'])
    traffic['external_total_bytes'] = sum(traffic[n] for n in (
        'external_q_fp32_read_bytes', 'external_kv_fp32_read_bytes',
        'external_output_fp32_write_bytes'))
    return dict(
        schema_version=1, status='PRE_RTL_CANDIDATE_EVENT_MODEL_NOT_CYCLE_PREDICTION',
        operation_scope='Attention QK/PV and its softmax only; excludes all seven Dense and other block owners',
        workload=dict(model='Qwen2-1.5B', tokens=tokens, past_tokens=0, heads=12,
                      kv_heads=2, head_dim=128, causal=True, batch=1),
        scope=dict(candidate_hardware_implemented=False, actual_model_run=False,
                   actual_rtl_run=False, hardware_acceptance=False,
                   scalar_error_status_policy_validated=False,
                   threshold_or_acceptance_semantics_changed=False),
        arithmetic=dict(ingress='FP32 containers -> RNE BF16',
                        qk='16 stripes; stripe s receives s,s+16,...,s+112; FP32 FMA; ordered FP32 add from +0',
                        pv='ascending causal key BF16 x BF16 -> FP32 FMA; capture at key=query',
                        output='FP32', softmax='unchanged FP32 scale/exp recipe and ascending sum; no substitute exp',
                        matrix_error='MatrixStreamResult.error is protocol-only, not FP exception flags',
                        matrix_numerical_check='check causal final stripe partials / PV row-final returned FP32 values for finite before clear or capture; ignore irrelevant lanes',
                        scalar_status='preserve BlockScalarFloat error returns, including legacy Add/Mul/Div underflow rejection; synthetic bit helpers do not model this status'),
        scratch=scratch_layout(tokens, contexts),
        schedule=dict(qk_rectangles=HEADS*len(qk), pv_rectangles=HEADS*len(pv),
                      qk_groups=HEADS*len(qk)*((16+contexts-1)//contexts), pv_groups=HEADS*len(pv),
                      existing_contexts=5, qk_used_contexts=contexts, pv_used_contexts=1,
                      max_pending_steps=contexts,
                      existing_metadata_fifo_entries=8, seed_restore_count=0,
                      result_fifo_capacity_entries=2, result_consumer_live_entries=1,
                      qk_wide_steps=qk_steps, pv_wide_steps=pv_steps,
                      physical_512_mac_slice_issues=(qk_executed+pv_executed)//512,
                      row_final_captures=HEADS*tokens,
                      qk_stripe_reduction_fp32_adds=16*pairs,
                      qk_scale_fp32_multiplies=pairs,
                      softmax_diff_exp_sum_scalar_requests=3*pairs,
                      softmax_reciprocal_scalar_requests=HEADS*tokens,
                      probability_scale_fp32_multiplies=pairs),
        macs=dict(scope='Attention QK+PV only, not full decoder block',
                  causal_head_query_key_pairs=pairs, qk_useful=pairs*HD,
                  pv_useful=pairs*HD, useful_total=2*pairs*HD,
                  qk_issued_executed=qk_executed, pv_issued_executed=pv_executed,
                  issued_executed_total=qk_executed+pv_executed,
                  causal_or_padded_waste=qk_executed+pv_executed-2*pairs*HD,
                  useful_fraction_of_executed=(2*pairs*HD)/(qk_executed+pv_executed),
                  full_4096_issue_capacity_slots=(qk_steps+pv_steps)*4096,
                  inactive_slice_slots=(qk_steps+pv_steps)*4096-qk_executed-pv_executed,
                  fractions_are_not_cycle_utilization=True),
        traffic=traffic,
        attention_bounds=dict(
            scope='Attention only; conditional source/geometry bounds, never measured cycles',
            wide_issue_count=wide_steps,
            wide_issue_cycles_lower_bound=wide_steps,
            useful_utilization_issue_geometry_upper_bound=(2*pairs*HD)/(4096*wide_steps),
            issue_geometry_excludes_80_percent=True,
            context_count_changes_issue_geometry_bound=False,
            required_scalar_requests_lower_bound=scalar_requests,
            scalar_requests_formula='16P reduction + P scale + 3P diff/exp/sum + P probability scale + 12M reciprocal = 21P+12M',
            scalar_single_port_cycles_lower_bound=scalar_requests,
            useful_utilization_scalar_port_upper_bound=(2*pairs*HD)/(4096*scalar_requests),
            matrix_scalar_serialized_cycles_lower_bound=wide_steps+scalar_requests,
            useful_utilization_serialized_upper_bound=(2*pairs*HD)/(4096*(wide_steps+scalar_requests)),
            assumptions=[
                'At most one accepted Matrix wide issue and one accepted scalar request per cycle; no primitive latency is assumed.',
                'All ordered reduction and softmax operations retain the existing scalar route, including its error policy; no vectorized reduction credit.',
                'The scalar-port bound holds even with perfect Matrix overlap; the stronger sum applies only to this serialized candidate event order.',
                'DMA, bank gathering/RMW, protocol, drain and output ACK costs can only increase complete Attention cycles.',
            ]),
        candidate_requirements=[
            'Explicit exclusive Dense SRAM lease, owner routing and release after write ACKs; existing interfaces expose no lease.',
            'Keep A 16x1376x32 B and B 16x160x32 B; new address/gather and result-store routing, no added SRAM port.',
            'K token-major column gather serializes bank accesses; Q/P and K/V compete for the same A read ports.',
            'Reuse bounded existing operand/result storage with credit reservation; partial fill/gather controls require design and validation.',
            'QK one/five stripe contexts with one/five C slots; ordered scalar FP32 additions, slot release after reduction, causal writes and returned-value finite checks.',
            'PV four active slices only: 128 useful columns. Common A broadcast cannot independently feed a second head to other slices.',
            'PV returning-key metadata and row-final capture into B C before padded suffix; check only relevant returned FP32 values for finite, not unavailable Matrix FP flags.',
            'Keep scalar error handling, including legacy underflow rejection; no vectorized reduction is implemented or credited. Latency, SRAM arbitration, setup, drain and ACK costs remain unmeasured.',
            'No accumulator seed port, split-K reduction, new contexts, online-softmax reorder, prefix cache or new acceptance threshold.',
        ],
        attention_80_percent_excluded_by_issue_geometry=True,
        can_assess_full_block_80_percent_target=False,
        predicted_attention_cycles=None, predicted_full_block_cycles=None,
        rtl_measured_cycles=None, rtl_measured_utilization=None,
        numerical_gate_status='UNCHANGED; synthetic bit tests are not model acceptance',
    )


def report(root, tokens, contexts=1):
    for name, expected in SOURCE_PINS.items():
        path = Path(root)/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('source changed; re-audit rectangular model before use: '+name)
    result = calculate(tokens, contexts)
    result['source_sha256'] = dict(SOURCE_PINS)
    return result


def _finite_parts(bits):
    if type(bits) is not int or not 0 <= bits <= 0xffffffff:
        raise ValueError('expected raw FP32 uint32 bits')
    sign, exp, fraction = bits >> 31, (bits >> 23) & 255, bits & 0x7fffff
    if exp == 255:
        raise ValueError('synthetic arithmetic supports finite values only')
    n = fraction if exp == 0 else (1 << 23) | fraction
    return (-n if sign else n), (-149 if exp == 0 else exp-150)


def _round_shift(n, shift):
    if shift <= 0:
        return n << -shift
    q, r = divmod(n, 1 << shift)
    half = 1 << (shift-1)
    return q + (r > half or (r == half and q & 1))


def _round_fp32(n, exponent, zero_sign=0):
    if not n:
        return zero_sign << 31
    sign, magnitude = int(n < 0), abs(n)
    highest = magnitude.bit_length()-1+exponent
    quantum = max(-149, highest-23)
    mantissa = _round_shift(magnitude, quantum-exponent)
    if mantissa >= 1 << 24:
        mantissa >>= 1
        quantum += 1
    if mantissa < 1 << 23:
        return (sign << 31) | mantissa
    biased = quantum+23+127
    if biased >= 255:
        raise ValueError('FP32 overflow; no finite-output acceptance claimed')
    return (sign << 31) | (biased << 23) | (mantissa & 0x7fffff)


def fp32_fma_bits(a, b, c):
    """Exact integer product/sum followed by one IEEE RNE FP32 rounding."""
    na, ea = _finite_parts(a)
    nb, eb = _finite_parts(b)
    nc, ec = _finite_parts(c)
    product, ep = na*nb, ea+eb
    exponent = min(ep, ec)
    total = (product << (ep-exponent)) + (nc << (ec-exponent))
    same_negative_zeros = not product and not nc and ((a ^ b) >> 31) and (c >> 31)
    return _round_fp32(total, exponent, int(same_negative_zeros))


def fp32_add_bits(a, b):
    """Rounded result bits only; NOT BlockScalarFloat exception/status policy."""
    return fp32_fma_bits(a, 0x3f800000, b)


def returned_values_finite(values, valid):
    """Model the candidate returned-value check, not unavailable Matrix flags."""
    if len(values) != len(valid):
        raise ValueError('returned values and validity mask must have equal lengths')
    return all((bits & 0x7f800000) != 0x7f800000
               for bits, keep in zip(values, valid) if keep)


def bf16_rne_bits(fp32):
    _finite_parts(fp32)
    value = (fp32 + 0x7fff + ((fp32 >> 16) & 1)) >> 16
    if value & 0x7f80 == 0x7f80:
        raise ValueError('BF16 overflow; no finite-output acceptance claimed')
    return value


def fp16_to_fp32_bits(fp16):
    if type(fp16) is not int or not 0 <= fp16 <= 0xffff:
        raise ValueError('expected raw FP16 uint16 bits')
    sign, exp, frac = fp16 >> 15, (fp16 >> 10) & 31, fp16 & 1023
    if exp == 31:
        raise ValueError('synthetic arithmetic supports finite FP16 only')
    n, power = (frac, -24) if not exp else (1024+frac, exp-25)
    return _round_fp32(-n if sign else n, power, sign)


def legacy_qk_bits(q_fp32, k_fp32):
    """Legacy ordering's result bits; scalar error/status checks are not modeled."""
    if len(q_fp32) != HD or len(k_fp32) != HD:
        raise ValueError('Qwen2 head dimension is fixed at 128')
    sums = [0]*16
    for depth in range(0, HD, 16):
        for lane in range(16):
            d = depth+lane
            sums[lane] = fp32_fma_bits(bf16_rne_bits(q_fp32[d]) << 16,
                                      bf16_rne_bits(k_fp32[d]) << 16, sums[lane])
    result = 0
    for partial in sums:
        result = fp32_add_bits(result, partial)
    return result


def rectangular_qk_bits(q_rows, k_rows, query_base=0):
    """One small synthetic tile, before the unchanged score-scale/softmax."""
    if not 1 <= len(q_rows) <= 16 or any(len(r) != HD for r in q_rows+k_rows):
        raise ValueError('expected 1..16 query rows and head dimension 128')
    score = [[None]*len(k_rows) for _ in q_rows]
    for stripe in range(16):
        for r, q in enumerate(q_rows):
            for key, k in enumerate(k_rows):
                if key > query_base+r:
                    continue
                partial = 0
                for depth in range(stripe, HD, 16):
                    partial = fp32_fma_bits(bf16_rne_bits(q[depth]) << 16,
                                           bf16_rne_bits(k[depth]) << 16, partial)
                score[r][key] = fp32_add_bits(0 if stripe == 0 else score[r][key], partial)
    return score


def rectangular_pv_bits(probability_rows, v_rows, query_base=0):
    """Return causal capture and padded final accumulators, exposing zero risk.

    Probabilities are independent supplied synthetic FP32 values, not a new
    softmax implementation or claims about upstream numerical acceptance.
    """
    if not 1 <= len(probability_rows) <= 16 or any(len(v) != HD for v in v_rows):
        raise ValueError('expected 1..16 rows and head dimension 128')
    keys = query_base+len(probability_rows)
    if len(v_rows) < keys or any(len(p) < keys for p in probability_rows):
        raise ValueError('incomplete causal inputs')
    accum = [[0]*HD for _ in probability_rows]
    captured = [None]*len(probability_rows)
    for key in range(keys):
        for row, probs in enumerate(probability_rows):
            p = bf16_rne_bits(probs[key]) << 16 if key <= query_base+row else 0
            for column in range(HD):
                accum[row][column] = fp32_fma_bits(p, bf16_rne_bits(v_rows[key][column]) << 16,
                                                  accum[row][column])
            if key == query_base+row:
                captured[row] = list(accum[row])
    return captured, accum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tokens', type=int, choices=(128, 1024), default=128)
    parser.add_argument('--contexts', type=int, choices=(1, 5), default=1)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, help='save report JSON, creating parent directories')
    parser.add_argument('--events-jsonl', type=Path,
                        help='optional potentially large dependency trace; events are not cycles')
    args = parser.parse_args()
    result = report(args.root, args.tokens, args.contexts)
    if args.events_jsonl:
        with args.events_jsonl.open('w') as stream:
            for ordinal, event in enumerate(iter_events(args.tokens, args.contexts)):
                stream.write(json.dumps(dict(ordinal=ordinal, **event), sort_keys=True)+'\n')
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
