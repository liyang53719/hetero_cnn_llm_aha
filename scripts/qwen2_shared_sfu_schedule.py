#!/usr/bin/env python3
"""Small, pre-RTL shared-SFU reservation model; no hardware prediction.

The existing sixteen SiLU ALU/divider pairs are rescheduled, not replicated.
One or two vector contexts retain the exact exp7/SiLU expression order. The
current RTL has no such controller. Divider timing is unbound by default;
explicit source mode binds the pinned primitive's control and bounded integer
division model. Options16 is a model-only candidate, not a hardware setting.
Numeric results are diagnostic: full HardFloat flags are not generated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
HARDFLOAT_COMMIT = 'c1105e6ac6a0dd90fc80893efc4830ab609005d3'
HARDFLOAT_RECEIPT = 'reports/execution/QWEN2_REAL16_B91BBE3/hardfloat.sha256.json'
HARDFLOAT_SOURCE_PINS = {
    'hardfloat/src/main/scala/common.scala': 'ea83cdfac50db84f372d624ce4e0d45188207164a6a1eae5d42d8174241925cb',
    'hardfloat/src/main/scala/DivSqrtRecFN_small.scala': '905b3c0b4b47286d56b7f7d37a2886add7fd662336f5864df454680021e92da9',
    'hardfloat/src/main/scala/rawFloatFromFN.scala': '39fb14ae28318821906f68ad63803ca24eecb1115bf24aa4f3df497392357dce',
    'hardfloat/src/main/scala/rawFloatFromRecFN.scala': 'bf7e4b0e453569c91f6a9d8c414feb3a5fed6dc7354ba31cdc8c7c0f1ffd8317',
    'hardfloat/src/main/scala/recFNFromFN.scala': '90060c571a38718330f8781ecc4f555096ac45a0c75abb3fe5219e06dacdbd2d',
    'hardfloat/src/main/scala/AddRecFN.scala': '2746fea3b3291a8db97999a45303878fdeabc0a0c8acb318f4da4f52dda54a85',
    'hardfloat/src/main/scala/MulRecFN.scala': 'cf42850379c249a97a073ac436ff6b4c564b56177e868c3e912be2f246243e1d',
    'hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala': '31cdb3be147471d52e721f14914031c19b915bd7aaffe5c0e333393a0c7fb67d',
}
SOURCE_PINS = {
    'scripts/qwen2_rectangular_attention_model.py': 'fbf1c610be695256f487e1df971c266575dc8d722195cd919f06f1209034fbe8',
    'scripts/qwen2_block_recipe_model.py': '2b7a4384bc619d39546714b251f286708646029eea172de8c28fb4946b69a2f6',
    BASE+'BlockFloat.scala': '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
    BASE+'VectorSilu.scala': '758f48c6f945fe78fafeb9d4086c43d4041ece5ead9a90b947379f7f522c32f9',
    BASE+'OverlappedSilu.scala': 'd15173c8105c6d9139623c890a4b6488edac3027e06cef61ca6af06440684dea',
    BASE+'QwenOwnerProtocol.scala': 'c8d6cfd95901bc9f2cae3f248d542cb532b1b66aec1be98942a9a7533d3ca542',
    'integration/gemmini/EmitHeteroFP32Alu.scala': '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1',
    'chisel/continuous_prefill/tests/qwen2_block.cpp': 'd757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5',
    'chisel/continuous_prefill/scripts/prepare_hardfloat.sh': '218ffbf5e7f96a03187938772b655c43c7589e526553d596aca1a46eab694c68',
    HARDFLOAT_RECEIPT: 'b2c54cf1f12987744b8cabe4de6aed6c6fa393dfb0d82ff6ccc4c0d4f2c1d4e6',
}
LANES, MAX_GROUPS = 16, 64


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_bits = _load('shared_sfu_existing_bit_helpers', 'scripts/qwen2_rectangular_attention_model.py')


def verify_sources(root=ROOT):
    for name, expected in SOURCE_PINS.items():
        if hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() != expected:
            raise ValueError('source identity changed; explicit review required: '+name)
    return dict(SOURCE_PINS)


def _divider_options(options):
    if type(options) is not int or options not in (0, 16):
        raise ValueError('only reviewed divider options 0 or candidate 16 are supported')
    return options


def timing_binding(root=ROOT, *, options=0):
    """Reviewed source-FSM formulas, not runtime RTL calibration or a fetch.

    The upstream bytes were read at the pinned commit and checked against the
    existing capture receipt. Local pins/receipt are rechecked on every call.
    """
    options = _divider_options(options)
    pins = verify_sources(root)
    receipt = json.loads((Path(root)/HARDFLOAT_RECEIPT).read_text())
    if any(receipt.get(p) != digest for p, digest in HARDFLOAT_SOURCE_PINS.items()):
        raise ValueError('HardFloat receipt differs from reviewed upstream source')
    return dict(local_source_sha256=pins,
        model_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        upstream=dict(commit=HARDFLOAT_COMMIT, source_sha256=dict(HARDFLOAT_SOURCE_PINS),
            receipt_path=HARDFLOAT_RECEIPT, runtime_upstream_fetch=False,
            source_locations={
                'common.scala': [59],
                'DivSqrtRecFN_small.scala': [224, 275, 298, 304, 317, 369, 393, 504],
                'rawFloatFromFN.scala': [45, 53, 55, 70],
                'rawFloatFromRecFN.scala': [48, 61, 62],
                'RoundAnyRawFNToRecFN.scala': [47, 55, 294, 326]},
            url='https://github.com/ucb-bar/berkeley-hardfloat/tree/'+HARDFLOAT_COMMIT),
        edge_convention='Request fires at edge 0. A registered result visible after edge k can first be sampled/fired at edge k+1. Ready is continuous unless stated.',
        primitive_divider=dict(parameters=[8, 24, options], current_hardware_options=0,
            candidate_options_only=options == 16,
            domain='Only IEEE FP32 normal finite nonzero a and b; either sign. Zero, subnormal, nonfinite and malformed inputs fail closed in this binding.',
            classification=('D=14 for candidate options16; process two quotient bits when cycleNum>=3.' if options else
                'D=25 if normalized significand(a)>=normalized significand(b), else D=26; exponent magnitudes and signs do not select D.'),
            output_visible_after_edge='D-1', first_sample_edge='D', earliest_next_accept_edge='D',
            same_edge_output_sample_and_next_input=True, output_backpressure_supported=False,
            recurrence=('After accept: cycleNum 26,24,...,2,1; output visible after edge13, sample/next accept at edge14.' if options else
                'On accept cycleNum=26; decrement each edge; if cycleNum==3 and first quotient bit is 1, skip to 1. inReady and outValid are true together at cycleNum==1.')),
        scalar_wrapper=dict(
            instantiated_options=0,
            columns=['result_visible_after_edge', 'first_result_fire_edge', 'earliest_next_request_edge'],
            add_mul=[1, 2, 3], exp_saturated=[1, 2, 3], exp_nonsaturated=[18, 19, 20],
            div=['D+1', 'D+2', 'D+3'],
            sqrt_positive_finite='Same wrapper formula; primitive D=24 for odd recoded exponent, 25 for even. Not implemented by the divider classifier.',
            rejected_before_arithmetic=[0, 1, 2], held_result=True),
        silu_wrapper=dict(instantiated_options=0, group_ii_formula='45+17*B+Q',
            variables='B=1 if any gate lane is nonsaturated; Q=1 if any lane reciprocal takes D26. All six phases must finish without an error.',
            first_result_fire_edge='group_ii-1',
            edge_span_formula='45*N+17*L+Qsum-1',
            same_edge_output_fire_and_next_input=False),
        normal_division_model=dict(
            domain='Normal finite nonzero inputs, exact quotient normal, and rounded quotient normal finite; IEEE RNE only.',
            modeled_flags='Only NX is modeled; NV/DZ/OF/UF cases are excluded by the domain, not covered by full flag equivalence.',
            method='Pinned one-bit/two-bit integer remainder/quotient/sticky recurrence followed by guard/sticky/LSB RNE.',
            validation='Deterministic directed/random samples against an independent exact rational oracle; not exhaustive equivalence.'),
        candidate_datapath=(dict(enabled_second_trial_path=True,
            description='Each divider enables a second dependent trial subtraction/comparison and remainder/quotient/sticky selection.',
            added_fp_operator_instances=0, added_physical_integer_adders=None,
            combinational_gate_delta=None, area_delta=None, critical_path_delta=None,
            same_frequency_proved=False) if options else None),
        scope=dict(source_fsm_timing=True, rtl_calibrated=False, hardfloat_flags_generated=False,
                   numerical_acceptance=False, full_block_prediction=False),
        limitations=[
            'The candidate bypasses BlockScalarFloat control; options16 additionally changes the primitive datapath. Neither candidate controller nor option change is implemented RTL.',
            'Scalar core occupancy excludes Qwen2Block calc/resume states and all owner/memory/ACK costs.',
            'Return capture must be reserved: HardFloat has a pulse output with no result-ready input.',
            'Fatal flags can terminate a wrapper phase early; success formulas do not prove numerical acceptance.',
            'An output stall retains the context and extends the schedule; source timing does not remove backpressure.'])


def _normal_operand(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError('source divider requires raw uint32 FP32 normal operands')
    exponent = (value >> 23) & 0xff
    if not 1 <= exponent <= 254:
        raise ValueError('source divider supports only normal finite nonzero operands')
    return value >> 31, exponent-127, 0x800000 | (value & 0x7fffff)


def source_divider_timing(a, b, *, options=0):
    """Pure integer classification for the reviewed normal-input division path."""
    options = _divider_options(options)
    sa, sb = _normal_operand(a)[2], _normal_operand(b)[2]
    latency = 14 if options else 25 if sa >= sb else 26
    return dict(latency_cycles=latency, initiation_interval_cycles=latency,
                options=options, current_hardware_options=0, candidate_options_only=options == 16,
                skip_cycle_2=options == 0 and sa >= sb, normalized_significand_a=sa,
                normalized_significand_b=sb,
                binding='candidate_options16_source_fsm' if options else 'pinned_source_fsm')


def source_division_model(a, b, *, options=0, trace=False):
    """Pinned integer division recurrence, with RNE and NX in a strict domain.

    Both operands, the exact quotient, and the rounded result must be normal
    finite. In particular an exact subnormal rounding to min-normal is rejected.
    The other four exception flags are excluded, not independently modeled.
    Options16 is only a candidate. No claim of exhaustive/RTL equivalence.
    """
    options = _divider_options(options)
    if type(trace) is not bool:
        raise ValueError('trace must be a boolean')
    sign_a, ea, sa = _normal_operand(a)
    sign_b, eb, sb = _normal_operand(b)
    exponent = ea-eb-int(sa < sb)
    if not -126 <= exponent <= 127:
        raise ValueError('division model requires an exact normal quotient')
    mask26 = (1 << 26)-1
    # For division: fractB_Z | (1<<24) = 2*normalized_significand(b).
    divisor = sb << 1
    trial = (sa << 1)-divisor
    first_bit = trial >= 0
    rem_z = (trial if first_bit else sa << 1) & mask26
    not_zero_rem_z = trial != 0
    sig_x = int(first_bit) << 25
    cycle_num, edge = 26, 0
    history = [dict(edge=0, cycle_num=26, rem=rem_z, sig=sig_x, sticky=not_zero_rem_z)] if trace else []
    while cycle_num > 1:
        process_two = options == 16 and cycle_num >= 3
        skip_cycle_2 = options == 0 and cycle_num == 3 and bool(sig_x & (1 << 25))
        trial = (rem_z << 1)-divisor
        bit = trial >= 0
        next_rem = (trial if bit else rem_z << 1) & mask26
        next_not_zero = trial != 0 if bit else not_zero_rem_z
        # Preserve the source's 27-bit truncation and second dependent trial.
        trial2 = (trial << 1)-divisor if bit else ((rem_z << 2) & ((1 << 27)-1))-divisor
        bit2 = trial2 >= 0
        not_zero_rem_z = ((process_two and bit and trial2 > 0) or
                         (process_two and not bit and trial2 > 0) or
                         (not (process_two and bit2) and next_not_zero))
        rem_z = ((trial2 if bit2 else next_rem << 1) & mask26) if process_two else next_rem
        if bit:
            sig_x |= 1 << (cycle_num-2)
        if process_two and bit2:
            sig_x |= 1 << (cycle_num-3)
        cycle_num = 1 if skip_cycle_2 else cycle_num-(2 if process_two else 1)
        edge += 1
        if trace:
            history.append(dict(edge=edge, cycle_num=cycle_num, rem=rem_z, sig=sig_x,
                                sticky=not_zero_rem_z, bit=int(bit),
                                bit2=int(bit2) if process_two else None))
    # rawOut.sig = sigX<<1 | notZeroRem. Option0 may omit the final low
    # quotient bit: compare rounded output/NX, not terminal raw-register equality.
    shift = sig_x.bit_length()-24
    assert shift in (1, 2)
    retained = sig_x >> shift
    guard = (sig_x >> (shift-1)) & 1
    sticky = bool(sig_x & ((1 << (shift-1))-1)) or not_zero_rem_z
    increment = bool(guard and (sticky or retained & 1))
    inexact = bool(guard or sticky)
    retained += increment
    if retained == 1 << 24:
        retained >>= 1
        exponent += 1
    if exponent > 127:
        raise ValueError('division model requires a rounded normal finite quotient')
    bits = ((sign_a ^ sign_b) << 31) | ((exponent+127) << 23) | (retained & 0x7fffff)
    return dict(result_bits=bits, modeled_flags=int(inexact), quotient_bits=sig_x,
                remainder_nonzero=not_zero_rem_z, guard=guard, sticky=sticky,
                increment=increment, output_visible_after_edge=edge,
                result_sample_edge=edge+1, next_accept_edge=edge+1, trace=history,
                options=options, candidate_options_only=options == 16)


def f32_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def f32_value(value):
    return struct.unpack('<f', struct.pack('<I', value))[0]


ONE = f32_bits(1.0)
INV_LN2 = f32_bits(1/math.log(2.0))
COEFFICIENTS = tuple(f32_bits(math.pow(-math.log(2.0), i)/math.factorial(i)) for i in range(8))


def _mul(a, b):
    # Reuse the existing exact-integer RNE backend; signed zero is explicit.
    na, ea = _bits._finite_parts(a)
    nb, eb = _bits._finite_parts(b)
    return _bits._round_fp32(na*nb, ea+eb, (a ^ b) >> 31)


def _div(a, b):
    # Ordinary IEEE FP32 numeric oracle only; never a HardFloat flag model.
    with np.errstate(all='raise'):
        result = np.divide(np.float32(f32_value(a)), np.float32(f32_value(b)), dtype=np.float32)
    bits = f32_bits(float(result))
    _bits._finite_parts(bits)
    return bits


def _groups(values, name):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= MAX_GROUPS:
        raise ValueError(f'{name} requires 1..{MAX_GROUPS} small synthetic groups')
    result = []
    for group in values:
        if not isinstance(group, (list, tuple)) or len(group) != LANES:
            raise ValueError(name+' requires exactly sixteen raw FP32 uint32 values per group')
        for value in group:
            _bits._finite_parts(value)
        result.append(list(group))
    return result


def program(gate):
    """Same rounding nodes and dependencies; register lifetimes are explicit."""
    _bits._finite_parts(gate)
    nodes = []
    def node(name, resource, op, a, b, dest, policy):
        nodes.append(dict(name=name, resource=resource, op=op, a=a, b=b,
                          dest=dest, policy=policy,
                          predecessor=nodes[-1]['name'] if nodes else None))
    if (gate & 0x7fffffff) >= f32_bits(80.0):
        node('exp_saturated', 'control', 'zero', 0, 0, 'work1', 'exp_internal')
    else:
        node('exp_scale', 'alu', 'mul', 'abs_gate', INV_LN2, 'work1', 'exp_internal')
        node('exp_floor', 'converter', 'floor', 'work1', 0, 'k', 'exp_internal')
        node('exp_fraction', 'alu', 'add', 'work1', 'negative_k', 'fraction', 'exp_internal')
        for index in range(6, -1, -1):
            node(f'exp_mul_{index}', 'alu', 'mul', 'work0', 'fraction', 'work1', 'exp_internal')
            node(f'exp_add_{index}', 'alu', 'add', 'work1', COEFFICIENTS[index], 'work0', 'exp_internal')
        node('exp_finish', 'alu', 'mul', 'work0', 'power_of_two', 'work1', 'exp_internal')
    node('denominator', 'alu', 'add', ONE, 'work1', 'work0', 'legacy_add')
    node('reciprocal', 'divider', 'div', ONE, 'work0', 'work0', 'legacy_div')
    node('sign_multiply', 'alu', 'mul', 'work0', 'sign_factor', 'work0', 'legacy_mul')
    node('gate_multiply', 'alu', 'mul', 'work0', 'gate', 'work0', 'legacy_mul')
    node('up_multiply', 'alu', 'mul', 'work0', 'up', 'work0', 'legacy_mul')
    return nodes


def _operand(ref, registers):
    if isinstance(ref, int):
        return ref
    if ref == 'abs_gate':
        return registers['gate'] & 0x7fffffff
    if ref == 'negative_k':
        return f32_bits(float(registers['k'])) ^ 0x80000000
    if ref == 'power_of_two':
        return (127-registers['k']) << 23
    if ref == 'sign_factor':
        return registers['work1'] if registers['gate'] >> 31 else ONE
    return registers[ref]


def _evaluate(node, registers):
    a, b = _operand(node['a'], registers), _operand(node['b'], registers)
    op = node['op']
    if op == 'add': value = _bits.fp32_add_bits(a, b)
    elif op == 'mul': value = _mul(a, b)
    elif op == 'div': value = _div(a, b)
    elif op == 'floor': value = int(f32_value(a))
    elif op == 'zero': value = 0
    else: raise AssertionError('unknown micro-op')
    return a, b, value


def _write(node, registers, value):
    registers[node['dest']] = value
    if node['op'] == 'floor':
        registers['work0'] = COEFFICIENTS[7]


def ordered_reference(gate, up):
    """Diagnostic bits for one lane; no exception flags or acceptance claim."""
    _bits._finite_parts(up)
    registers = dict(gate=gate, up=up)
    trace = []
    for node in program(gate):
        a, b, value = _evaluate(node, registers)
        _write(node, registers, value)
        trace.append(dict(node=node['name'], value=value, a=a, b=b))
    return dict(value=registers['work0'], nodes=trace)


def saved_gate_timing(result_path, root=ROOT):
    """Bounded branch census of a hash-bound saved BF16 gate, not a forward.

    Scan at most one M128 gate and evaluate at most 8192 distinct absolute
    values, stopping each existing exact-integer recipe at the denominator.
    No reciprocal, complete SiLU, flags, or hardware execution is performed.
    """
    verify_sources(root)
    result_path = Path(result_path)
    result_bytes = result_path.read_bytes()
    receipt = json.loads(result_bytes)
    names = ('raw_stages/phase_10_gate_recipe.f32le', 'phase_10_gate_recipe.f32le')
    entries = [x for x in receipt['artifacts'] if x.get('path') in names]
    if len(entries) != 1:
        raise ValueError('saved result must identify exactly one gate artifact')
    entry = entries[0]
    name = entry['path']
    path = result_path.parent/name
    size = path.stat().st_size
    if not 0 < size <= 128*8960*4 or size % 64:
        raise ValueError('saved gate must contain complete groups and be no larger than M128')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if size != entry['bytes'] or digest != entry['sha256']:
        raise ValueError('saved gate artifact bytes or hash differ from RESULT')
    bits = np.frombuffer(data, dtype='<u4')
    absolute = bits & 0x7fffffff
    if np.any((bits & 0xffff) != 0) or np.any(absolute >= 0x7f800000):
        raise ValueError('saved gate requires finite BF16-representable FP32 values')
    unique, inverse, counts = np.unique(absolute, return_inverse=True, return_counts=True)
    if len(unique) > 8192:
        raise ValueError('saved gate exceeds bounded distinct-pattern evaluation limit')
    denominators, timings = [], []
    for gate in unique:
        registers = dict(gate=int(gate), up=ONE)
        for node in program(int(gate)):
            _, _, value = _evaluate(node, registers)
            _write(node, registers, value)
            if node['name'] == 'denominator':
                denominators.append(value)
                timings.append(source_divider_timing(ONE, value)['latency_cycles'])
                break
    classes = np.asarray(timings, dtype=np.int64)
    lane_timing = classes[inverse].reshape(-1, LANES)
    groups = len(lane_timing)
    long_group = (absolute.reshape(-1, LANES) < f32_bits(80)).any(axis=1)
    slow_group = (lane_timing == 26).any(axis=1)
    ii = 45 + 17*long_group.astype(np.int64) + slow_group.astype(np.int64)
    per_lane = lane_timing.sum(axis=0)
    return dict(result_path=str(result_path), result_sha256=hashlib.sha256(result_bytes).hexdigest(),
        gate_path=str(path), gate_bytes=size, gate_sha256=digest, elements=len(bits), groups=groups,
        gate_abs_min=f32_value(int(absolute.min())), gate_abs_max=f32_value(int(absolute.max())),
        distinct_absolute_patterns=len(unique), exact_exp_denominator_evaluations=len(unique),
        denominator_min=f32_value(min(denominators)), denominator_max=f32_value(max(denominators)),
        divider_requests_d25=int(counts[classes == 25].sum()),
        divider_requests_d26=int(counts[classes == 26].sum()),
        nonsaturated_groups=int(long_group.sum()), d26_groups=int(slow_group.sum()),
        wrapper_group_ii_min=int(ii.min()), wrapper_group_ii_max=int(ii.max()),
        arithmetic_only_first_request_to_final_result_fire_edges=int(ii.sum())-1,
        per_divider_lane_service_cycles=per_lane.tolist(), divider_service_floor=int(per_lane.max()),
        evidence_kind='source control timing plus saved-input denominator branch census',
        scope=dict(complete_silu_evaluated=False, hardfloat_flags_generated=False,
                   numerical_acceptance=False, rtl_measured=False, full_block_prediction=False),
        assumptions=['All six wrapper phases finish without fatal flags.',
                     'Continuous inputs and ready outputs; no owner/memory/ACK costs.',
                     'Existing frozen exp7 and FP32-RNE denominator arithmetic.'])


def resource_budget(contexts, *, divider_options=0):
    if type(contexts) is not int or contexts not in (1, 2):
        raise ValueError('only one or two vector contexts are supported')
    divider_options = _divider_options(divider_options)
    tag_bits = (contexts-1).bit_length()
    return dict(alu_lanes=16, alu_issue_ports_per_lane=1, divider_lanes=16,
                converter_lanes=16, added_arithmetic_units=None if divider_options else 0,
                added_fp_operator_instances=0, added_sram_bytes=0,
                divider_options=divider_options, current_hardware_divider_options=0,
                candidate_divider_reconfiguration=divider_options == 16,
                per_divider_enabled_second_trial_path=(
                    'Second dependent trial subtraction/comparison and remainder/quotient/sticky selection.'
                    if divider_options else None),
                added_physical_integer_adders=None if divider_options else 0,
                combinational_gate_delta=None if divider_options else 0,
                area_delta=None, critical_path_delta=None, same_frequency_proved=False,
                contexts=contexts, write_ports_per_lane=1, divider_result_queue_entries=0,
                extra_context_bits=(contexts-1)*16*181,
                extra_batch_ordinal_bits=(contexts-1)*20,
                divider_owner_bits=16*(tag_bits+1),
                output_offer_valid_bits=1,
                output_offer_context_bits=tag_bits,
                added_logical_register_bits=(contexts-1)*(16*181+20)+16*(tag_bits+1)+1+tag_bits,
                context_fields_bits=dict(gate=32,up=32,fraction=32,work0=32,work1=32,
                                         k=8,micro_pc=5,valid=1,error=1,primitive_flags=5,flags_valid=1),
                physical_divider_tag='context index + valid; context cannot recycle while a return is outstanding',
                software_only_assertion_tags=['batch','generation','lane'],
                derived_control='waiting_divider is derived from the divider owner valid/context tag and context PC',
                output_offer_storage='uses existing context result registers plus explicit held-offer valid/context bits',
                allocation='new explicit logical state; existing memory-overlap queues are NOT also borrowed',
                reused_context0='outer gate/up; existing fraction/Horner/product/k/PC/flags fields',
                routing='ALU operand select, divider context tags, exclusive return/writeback mux',
                synthesis_or_area_proof=False)


def summarize_work(gates, ups, contexts=1, *, divider_options=0):
    gates, ups = _groups(gates, 'gate'), _groups(ups, 'up')
    if len(gates) != len(ups):
        raise ValueError('gate/up group counts differ')
    counts = {key: [0]*LANES for key in ('alu', 'converter', 'divider', 'control')}
    long_elements = 0
    for group in gates:
        for lane, gate in enumerate(group):
            ops = program(gate)
            long_elements += len(ops) > 6
            for op in ops:
                counts[op['resource']][lane] += 1
    return dict(groups=len(gates), elements=len(gates)*16,
                nonsaturated_elements=long_elements,
                nonsaturated_groups=sum(any((x & 0x7fffffff) < f32_bits(80) for x in g) for g in gates),
                operations_per_lane=counts,
                single_issue_alu_service_cycles_lower_bound=max(counts['alu']),
                resource_budget=resource_budget(contexts, divider_options=divider_options))


def schedule_silu(gates, ups, *, contexts=1, divider_timing=None, source_divider=False,
                  divider_options=0,
                  output_ready=None, injected_flags=None, injected_errors=None,
                  corrupt_divider_tags=None, max_cycles=100000, root=ROOT):
    """Return a candidate calendar, optionally using source-bound primitive timing.

    output_ready is a cycle->bool callable (default always ready). Fault keys
    are (batch,lane,node). Status flags are supplied externally; the source
    divider also reports diagnostic NX in its exact-normal/rounded-normal domain.
    A corrupt-tag key is (batch,lane) for that lane's sole reciprocal return.
    Cycle t issues and writes a combinational ALU/converter op at its end; the
    next micro-op and output handshake can use it in cycle t+1.
    Divider returns at t own that lane's write port and block ALU that cycle.
    """
    pins = verify_sources(root)
    if type(source_divider) is not bool:
        raise ValueError('source_divider must be a boolean')
    if source_divider and divider_timing is not None:
        raise ValueError('source divider timing and synthetic timing are mutually exclusive')
    divider_options = _divider_options(divider_options)
    if divider_options and not source_divider:
        raise ValueError('candidate divider options require explicit source_divider mode')
    gates, ups = _groups(gates, 'gate'), _groups(ups, 'up')
    work = summarize_work(gates, ups, contexts, divider_options=divider_options)
    result = dict(schema_version=1, component='qwen2_shared_sfu',
                  profile=f'candidate_single_issue_sfu_contexts_{contexts}',
                  profile_kind='candidate_context_schedule',
                  source_sha256=pins, work=work, scenario_cycles=None,
                  predicted_full_block_cycles=None, rtl_measured_cycles=None,
                  measured_cycles=None, events=[], reservations=[], outputs=[], output_drains=[],
                  scope=dict(candidate_hardware_implemented=False,
                    full_block_prediction=False, hardfloat_flags_generated=False,
                    scalar_error_status_policy_validated=False,
                    numerical_acceptance=False, numeric_result_bits_only=not source_divider,
                    normal_domain_divider_nx_modeled=source_divider,
                    memory_traffic_or_ack_modeled=False,
                    scalar_fsm_rewritten_in_candidate=True,
                    current_rtl_wrapper_timing=False),
                  status='TIMING_UNBOUND', divider_timing=divider_timing,
                  divider_timing_kind=('candidate_options16_source_fsm' if divider_options else
                                       'pinned_source_fsm' if source_divider else
                                       'synthetic' if divider_timing is not None else 'unbound'),
                  divider_options=divider_options, current_hardware_divider_options=0,
                  peak_contexts=0, output_count=0, all_outputs_acknowledged=None,
                  cycle_convention='cycle t issue/write commits at its end; next micro-op/output uses it at t+1; final drain cycle is included')
    if source_divider:
        result['timing_binding'] = timing_binding(root, options=divider_options)
        result['divider_bit_model'] = 'integer source recurrence; normal inputs, exact-normal and rounded-normal quotient; diagnostic NX only'
    elif divider_timing is None:
        return result
    else:
        if set(divider_timing) != {'latency_cycles', 'initiation_interval_cycles'}:
            raise ValueError('explicit divider latency_cycles and initiation_interval_cycles required')
        latency, interval = (divider_timing[k] for k in ('latency_cycles', 'initiation_interval_cycles'))
        if any(type(x) is not int or x < 1 for x in (latency, interval)) or interval < latency:
            raise ValueError('single-outstanding divider requires positive interval >= latency')
    if type(max_cycles) is not int or not 1 <= max_cycles <= 1000000:
        raise ValueError('max_cycles must be an integer in 1..1000000')
    ready = output_ready if output_ready is not None else lambda _: True
    flags = dict(injected_flags or {})
    errors = set(injected_errors or ())
    corrupt = set(corrupt_divider_tags or ())
    for value in flags.values():
        if type(value) is not int or not 0 <= value < 32:
            raise ValueError('injected flags must be raw five-bit integers')
    slots, generations = [None]*contexts, [0]*contexts
    dividers, div_available = [None]*16, [0]*16
    next_input = next_output = 0
    poison = None
    held_offer = None
    events, reservations, outputs = result['events'], result['reservations'], result['outputs']

    def event(cycle, event_name, **fields):
        events.append(dict(cycle=cycle, event=event_name, **fields))

    def fail(cycle, kind, **fields):
        nonlocal poison
        if poison is None:
            poison = dict(cycle=cycle, kind=kind, **fields)
            event(cycle, 'poison', kind=kind, **fields)

    def write(cycle, context, lane, node, value, **fields):
        state = context['lanes'][lane]
        key = (context['batch'], lane, node['name'])
        supplied_flags = flags.get(key, 0)
        fatal_flags = bool(supplied_flags & 0x1e) and node['policy'].startswith('legacy_')
        _write(node, state['registers'], value)
        state['pc'] += 1
        event(cycle, 'writeback', batch=context['batch'], lane=lane,
              slot=context['slot'], generation=context['generation'],
              node=node['name'], value=value, flags=flags.get(key),
              policy=node['policy'], injected_flag_source=key in flags,
              automatic_numerical_status_validated=False, **fields)
        if key in errors or fatal_flags:
            fail(cycle, 'numerical_injected', batch=context['batch'], lane=lane, node=node['name'])

    def evaluate(cycle, ctx, lane, node):
        try:
            registers = ctx['lanes'][lane]['registers']
            if source_divider and node['op'] == 'div':
                a, b = _operand(node['a'], registers), _operand(node['b'], registers)
                arithmetic = source_division_model(a, b, options=divider_options)
                return a, b, arithmetic['result_bits'], arithmetic['modeled_flags']
            return (*_evaluate(node, registers), None)
        except (ValueError, FloatingPointError, OverflowError) as exc:
            # The bit oracle has a deliberately limited domain. Its failure is
            # neither an IEEE flag nor permission to drop accepted transfers.
            fail(cycle, 'numeric_oracle_domain', batch=ctx['batch'],lane=lane,
                 node=node['name'],reason=str(exc))
            return None

    for cycle in range(max_cycles):
        blocked_write = set()
        # Return ownership is checked before any output publication at this edge.
        for lane, pending in enumerate(dividers):
            if pending is not None and pending['return_cycle'] == cycle:
                dividers[lane] = None
                blocked_write.add(lane)
                tag = pending['tag']
                observed = (tag[0], tag[1] ^ 1, tag[2], lane) if (tag[0], lane) in corrupt else tag
                ctx = slots[tag[1]]
                valid = ctx is not None and (ctx['batch'], ctx['slot'], ctx['generation'], lane) == observed
                event(cycle, 'divider_return', lane=lane, tag=list(observed), expected_tag=list(tag))
                if not valid:
                    fail(cycle, 'divider_tag', lane=lane, expected=list(tag), observed=list(observed))
                elif poison is None:
                    assert ctx['lanes'][lane]['waiting_divider']
                    ctx['lanes'][lane]['waiting_divider'] = False
                    write(cycle, ctx, lane, pending['node'], pending['value'], resource=f'silu.divider.{lane:02d}',
                          modeled_divider_flags=pending['modeled_flags'])
                else:
                    event(cycle, 'divider_discard', lane=lane, tag=list(tag))

        # Once offered, payload/valid cannot be withdrawn on a later fault.
        # Drain that transport handshake without publishing a successful job.
        if held_offer is None and poison is None:
            ctx = next((c for c in slots if c is not None and c['batch'] == next_output), None)
            if ctx is not None and all(s['pc'] == len(s['program']) for s in ctx['lanes']):
                held_offer = dict(batch=ctx['batch'],slot=ctx['slot'],
                                  value=[s['registers']['work0'] for s in ctx['lanes']])
        if held_offer is not None:
            packet = held_offer
            event(cycle,'output_offer',batch=packet['batch'],slot=packet['slot'],value=list(packet['value']))
            if ready(cycle):
                destination = outputs if poison is None else result['output_drains']
                destination.append(dict(batch=packet['batch'],value=list(packet['value']),cycle=cycle))
                event(cycle,'output_fire',batch=packet['batch'],slot=packet['slot'],poisoned_drain=poison is not None)
                event(cycle,'context_release',batch=packet['batch'],slot=packet['slot'],reason='output_fire')
                slots[packet['slot']] = None
                held_offer = None
                next_output += 1
        if poison is None:
            if next_input < len(gates) and None in slots:
                slot = slots.index(None)
                generations[slot] += 1
                ctx = dict(slot=slot, generation=generations[slot], batch=next_input, accepted_cycle=cycle,
                           lanes=[dict(registers=dict(gate=gates[next_input][lane], up=ups[next_input][lane]),
                                       program=program(gates[next_input][lane]), pc=0, waiting_divider=False)
                                  for lane in range(16)])
                slots[slot] = ctx
                result['peak_contexts'] = max(result['peak_contexts'], sum(c is not None for c in slots))
                event(cycle, 'input_fire', batch=next_input, slot=slot, generation=generations[slot])
                next_input += 1

        if poison is None:
            for lane in range(16):
                candidates = sorted((c for c in slots if c is not None and c['accepted_cycle'] < cycle), key=lambda c:c['batch'])
                # Issue at most one divider per lane; no return/write at issue.
                for ctx in candidates:
                    state = ctx['lanes'][lane]
                    if state['waiting_divider'] or state['pc'] == len(state['program']):
                        continue
                    node = state['program'][state['pc']]
                    if node['resource'] == 'divider' and dividers[lane] is None and cycle >= div_available[lane]:
                        computed = evaluate(cycle,ctx,lane,node)
                        if computed is None:
                            break
                        a, b, value, modeled_flags = computed
                        timing = source_divider_timing(a, b, options=divider_options) if source_divider else divider_timing
                        latency = timing['latency_cycles']
                        interval = timing['initiation_interval_cycles']
                        tag = (ctx['batch'],ctx['slot'],ctx['generation'],lane)
                        dividers[lane] = dict(tag=tag, node=node, value=value, return_cycle=cycle+latency,
                                             modeled_flags=modeled_flags)
                        div_available[lane] = cycle+interval
                        state['waiting_divider'] = True
                        event(cycle, 'issue', batch=ctx['batch'], lane=lane, slot=ctx['slot'],
                              generation=ctx['generation'], node=node['name'], resource=f'silu.divider.{lane:02d}', a=a,b=b,
                              latency_cycles=latency, initiation_interval_cycles=interval,
                              timing_binding=result['divider_timing_kind'], modeled_divider_flags=modeled_flags)
                        reservations.append(dict(resource=f'silu.divider.{lane:02d}',start=cycle,end=cycle+interval,
                                                 batch=ctx['batch'],slot=ctx['slot'],node=node['name']))
                        break
                if poison is not None:
                    break
                # The physical write port is reserved for an arriving divider.
                if lane in blocked_write:
                    event(cycle, 'alu_blocked_by_divider', lane=lane)
                    continue
                for ctx in candidates:
                    state = ctx['lanes'][lane]
                    if state['waiting_divider'] or state['pc'] == len(state['program']):
                        continue
                    node = state['program'][state['pc']]
                    if node['resource'] == 'divider':
                        continue
                    computed = evaluate(cycle,ctx,lane,node)
                    if computed is None:
                        break
                    a,b,value,_ = computed
                    resource = f"silu.{node['resource']}.{lane:02d}"
                    event(cycle, 'issue', batch=ctx['batch'], lane=lane, slot=ctx['slot'],
                          generation=ctx['generation'], node=node['name'], resource=resource,a=a,b=b)
                    reservations.append(dict(resource=resource,start=cycle,end=cycle+1,
                                             batch=ctx['batch'],slot=ctx['slot'],node=node['name']))
                    # End-of-cycle write; output evaluation already happened,
                    # and this lane cannot issue another micro-op this cycle.
                    write(cycle,ctx,lane,node,value,resource=resource)
                    break
                if poison is not None:
                    break

        drained = all(p is None for p in dividers) and all(t <= cycle for t in div_available)
        if poison is not None and drained and held_offer is None:
            for ctx in slots:
                if ctx is not None:
                    event(cycle, 'context_release', batch=ctx['batch'], slot=ctx['slot'], reason='poison_drain')
            slots = [None]*contexts
        if drained and all(c is None for c in slots) and (poison is not None or next_output == len(gates)):
            event(cycle, 'terminal', error=poison is not None)
            terminal_status = ('DIAGNOSTIC_DOMAIN_REJECTED_DRAINED' if poison and poison['kind']=='numeric_oracle_domain'
                               else 'POISON_DRAINED' if poison else 'SCENARIO_DRAINED')
            result.update(status=terminal_status,
                          scenario_cycles=cycle+1, poison=poison, resources_drained=True,
                          accepted_groups=next_input, retired_groups=next_output,
                          output_count=len(outputs)+len(result['output_drains']), successful_output_count=len(outputs),
                          all_output_handshakes_completed=next_output == len(gates),
                          numerical_acceptance=False)
            return result
    result.update(status='SCENARIO_LIMIT_REACHED', scenario_cycles=None,
                  elapsed_scenario_cycles=max_cycles, resources_drained=False,
                  accepted_groups=next_input, retired_groups=next_output, poison=poison,
                  output_count=len(outputs)+len(result['output_drains']),successful_output_count=len(outputs),
                  pending_output_offer=held_offer,
                  all_output_handshakes_completed=next_output == len(gates))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contexts', type=int, choices=(1,2), default=1)
    parser.add_argument('--groups', type=int, default=2)
    parser.add_argument('--divider-latency', type=int)
    parser.add_argument('--divider-ii', type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--source-divider-timing', action='store_true')
    mode.add_argument('--source-timing-audit', action='store_true')
    parser.add_argument('--source-divider-options', type=int, choices=(0, 16), default=0,
                        help='0 is current source; 16 is an explicit model-only datapath candidate, not a hardware configuration change')
    mode.add_argument('--gate-result', type=Path, nargs='+',
                      help='Hash-check and classify at most two saved gate artifacts; no full forward')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if not 1 <= args.groups <= MAX_GROUPS:
        parser.error(f'--groups must be 1..{MAX_GROUPS}; no full M128 microstep runs')
    if (args.divider_latency is None) != (args.divider_ii is None):
        parser.error('both divider latency and II must be supplied explicitly')
    if args.divider_latency is not None and (args.source_divider_timing or args.source_timing_audit or args.gate_result):
        parser.error('source timing/audit and synthetic timing are mutually exclusive')
    if args.gate_result and len(args.gate_result) > 2:
        parser.error('--gate-result accepts at most two saved result files')
    if args.source_divider_options and not (args.source_divider_timing or args.source_timing_audit):
        parser.error('candidate options16 requires --source-divider-timing or --source-timing-audit; saved gate census stays on actual options0')
    timing = None if args.divider_latency is None else dict(latency_cycles=args.divider_latency,
                                                         initiation_interval_cycles=args.divider_ii)
    gates = [[f32_bits((lane-8)/4) for lane in range(16)] for _ in range(args.groups)]
    ups = [[ONE]*16 for _ in gates]
    if args.source_timing_audit:
        report = timing_binding(options=args.source_divider_options)
    elif args.gate_result:
        report = dict(timing_binding=timing_binding(),
                      saved_gate_timing=[saved_gate_timing(path) for path in args.gate_result])
    else:
        report = schedule_silu(gates,ups,contexts=args.contexts,divider_timing=timing,
                               source_divider=args.source_divider_timing,
                               divider_options=args.source_divider_options)
    text = json.dumps(report,indent=2,allow_nan=False)+'\n'
    if args.out:
        with args.out.open('x') as stream: stream.write(text)
    else: print(text,end='')


if __name__ == '__main__':
    main()
