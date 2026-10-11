#!/usr/bin/env python3
"""Small, pre-RTL shared-SFU reservation model; no hardware prediction.

The existing sixteen SiLU ALU/divider pairs are rescheduled, not replicated.
One or two vector contexts retain the exact exp7/SiLU expression order. The
current RTL has no such controller. Divider timing is deliberately unbound by
default. Numeric result bits are diagnostic: HardFloat flags are not generated.
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
SOURCE_PINS = {
    'scripts/qwen2_rectangular_attention_model.py': 'fbf1c610be695256f487e1df971c266575dc8d722195cd919f06f1209034fbe8',
    'scripts/qwen2_block_recipe_model.py': '2b7a4384bc619d39546714b251f286708646029eea172de8c28fb4946b69a2f6',
    BASE+'BlockFloat.scala': '9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5',
    BASE+'VectorSilu.scala': '758f48c6f945fe78fafeb9d4086c43d4041ece5ead9a90b947379f7f522c32f9',
    BASE+'OverlappedSilu.scala': 'd15173c8105c6d9139623c890a4b6488edac3027e06cef61ca6af06440684dea',
    BASE+'QwenOwnerProtocol.scala': 'c8d6cfd95901bc9f2cae3f248d542cb532b1b66aec1be98942a9a7533d3ca542',
    'integration/gemmini/EmitHeteroFP32Alu.scala': '83fb6b55fe4362b58ddf740f7bfccd16f86779bda68e2e6e879052749cad88b1',
    'chisel/continuous_prefill/tests/qwen2_block.cpp': 'd757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5',
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


def resource_budget(contexts):
    if type(contexts) is not int or contexts not in (1, 2):
        raise ValueError('only one or two vector contexts are supported')
    tag_bits = (contexts-1).bit_length()
    return dict(alu_lanes=16, alu_issue_ports_per_lane=1, divider_lanes=16,
                converter_lanes=16, added_arithmetic_units=0, added_sram_bytes=0,
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


def summarize_work(gates, ups, contexts=1):
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
                resource_budget=resource_budget(contexts))


def schedule_silu(gates, ups, *, contexts=1, divider_timing=None,
                  output_ready=None, injected_flags=None, injected_errors=None,
                  corrupt_divider_tags=None, max_cycles=100000, root=ROOT):
    """Return a calendar component. Explicit timing is a hypothetical scenario.

    output_ready is a cycle->bool callable (default always ready). Fault keys
    are (batch,lane,node). Flags are supplied externally, never calculated.
    A corrupt-tag key is (batch,lane) for that lane's sole reciprocal return.
    Cycle t issues and writes a combinational ALU/converter op at its end; the
    next micro-op and output handshake can use it in cycle t+1.
    Divider returns at t own that lane's write port and block ALU that cycle.
    """
    pins = verify_sources(root)
    gates, ups = _groups(gates, 'gate'), _groups(ups, 'up')
    work = summarize_work(gates, ups, contexts)
    result = dict(schema_version=1, component='qwen2_shared_sfu',
                  profile=f'candidate_single_issue_sfu_contexts_{contexts}',
                  profile_kind='candidate_context_schedule',
                  source_sha256=pins, work=work, scenario_cycles=None,
                  predicted_full_block_cycles=None, rtl_measured_cycles=None,
                  measured_cycles=None, events=[], reservations=[], outputs=[], output_drains=[],
                  scope=dict(candidate_hardware_implemented=False,
                    full_block_prediction=False, hardfloat_flags_generated=False,
                    scalar_error_status_policy_validated=False,
                    numerical_acceptance=False, numeric_result_bits_only=True,
                    memory_traffic_or_ack_modeled=False,
                    scalar_fsm_rewritten_in_candidate=True,
                    current_rtl_wrapper_timing=False),
                  status='TIMING_UNBOUND', divider_timing=divider_timing,
                  peak_contexts=0, output_count=0, all_outputs_acknowledged=None,
                  cycle_convention='cycle t issue/write commits at its end; next micro-op/output uses it at t+1; final drain cycle is included')
    if divider_timing is None:
        return result
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
            return _evaluate(node,ctx['lanes'][lane]['registers'])
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
                    write(cycle, ctx, lane, pending['node'], pending['value'], resource=f'silu.divider.{lane:02d}')
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
                        a, b, value = computed
                        tag = (ctx['batch'],ctx['slot'],ctx['generation'],lane)
                        dividers[lane] = dict(tag=tag, node=node, value=value, return_cycle=cycle+latency)
                        div_available[lane] = cycle+interval
                        state['waiting_divider'] = True
                        event(cycle, 'issue', batch=ctx['batch'], lane=lane, slot=ctx['slot'],
                              generation=ctx['generation'], node=node['name'], resource=f'silu.divider.{lane:02d}', a=a,b=b)
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
                    a,b,value = computed
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
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if not 1 <= args.groups <= MAX_GROUPS:
        parser.error(f'--groups must be 1..{MAX_GROUPS}; no full M128 microstep runs')
    if (args.divider_latency is None) != (args.divider_ii is None):
        parser.error('both divider latency and II must be supplied explicitly')
    timing = None if args.divider_latency is None else dict(latency_cycles=args.divider_latency,
                                                         initiation_interval_cycles=args.divider_ii)
    gates = [[f32_bits((lane-8)/4) for lane in range(16)] for _ in range(args.groups)]
    ups = [[ONE]*16 for _ in gates]
    report = schedule_silu(gates,ups,contexts=args.contexts,divider_timing=timing)
    text = json.dumps(report,indent=2,allow_nan=False)+'\n'
    if args.out:
        with args.out.open('x') as stream: stream.write(text)
    else: print(text,end='')


if __name__ == '__main__':
    main()
