"""Candidate-only wire/topology/resource checks. No RTL or numeric claims."""
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').exists())
CANDIDATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import heteronpu
if CANDIDATE != ROOT:
    # Read unchanged dependencies from the source tree and load only our overlay.
    # This isolated test invocation must not import the old descriptor module first.
    assert 'heteronpu.descriptor_chain' not in sys.modules, 'run the candidate suite in a fresh Python process'
    heteronpu.__path__.insert(0, str(CANDIDATE / 'src/heteronpu'))
sys.path.insert(0, str(ROOT / 'chisel/continuous_prefill/scripts'))
sys.path.insert(0, str(CANDIDATE / 'chisel/continuous_prefill/scripts'))
from heteronpu.command import Command128, Engine, Opcode
from heteronpu.descriptor_chain import DescriptorRecord, MatrixAux, NULL_INDEX, RecordType, SfuProgram
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import HostQkNormBinding, HostPartialRopeBinding
from host_bf16_attention_core_descriptor import (
    ATTENTION_RECIPE, AttentionContext, AttentionOperation as Op, AttentionTensor,
    CHAIN_RECORDS, DENSE_MATRIX_AUX, HostAttentionCoreBinding,
    build_host_attention_core_commands, build_host_attention_core_descriptor,
    parse_host_attention_core_descriptor, validate_carried_attention_launch, validate_carried_attention_commands,
    validate_host_attention_core_commands,
)


def fixture(*, base=0, count=4, length=0, generation=0, capacity=256, rows=128, offset=0, parameter_offset=0):
    projections = [HostQkvBinding(role, rows, base, count, offset + 0x1000000,
                                 parameter_offset + 0x2000000 + role * 0x1000000,
                                 offset + 0x8000000 + role * 0x200000) for role in range(3)]
    norms = [HostQkNormBinding(role, rows, base, count, projections[role].output_ddr,
                              parameter_offset + 0x5000000 + role * 0x1000,
                              offset + 0xA000000 + role * 0x200000,
                              offset + 0xB000000 if role == 0 else 0) for role in range(2)]
    ropes = [HostPartialRopeBinding(role, rows, base, count, norms[role].output_ddr,
                                   parameter_offset + 0x5200000, offset + 0xC000000 + role * 0x200000,
                                   256, length) for role in range(2)]
    core = HostAttentionCoreBinding(rows, base, count, capacity, length, length, generation,
                                    length == 0, ropes[0].output_ddr, ropes[1].output_ddr,
                                    projections[2].output_ddr, 0x10000000,
                                    offset + 0x11000000, offset + 0x12000000, offset + 0x13000000)
    return projections, norms, ropes, core


@pytest.mark.parametrize('base,count,length,generation', [
    (0, 1, 0, 0), (0, 128, 0, 0), (0, 128, 128, 1), (127, 1, 255, 9),
    (125, 3, 17, 23), (0, 8, 120, 0xFFFFFFFE),
])
def test_complete_actual_chain_roundtrip_and_owner_inventory(base, count, length, generation):
    args = fixture(base=base, count=count, length=length, generation=generation)
    commands, records = build_host_attention_core_commands(*args)
    core = args[-1]
    assert len(commands) == 12 and len(records) == CHAIN_RECORDS == 172
    assert set(records) == set(range(172))
    assert [c.src0 for c in commands] == [0, 21, 42, 63, 78, 90, 102, 114, 125, 138, 147, 160]
    assert [c.opcode for c in commands[7:]] == [0x41, 0x23, 0x33, 0x24, 0x30]
    assert [c.engine for c in commands[7:]] == [4, 2, 3, 2, 3]
    assert [(c.event_wait, c.event_signal) for c in commands] == [(i, i + 1) for i in range(12)]
    assert commands[9].src1 == NULL_INDEX
    assert validate_host_attention_core_commands([c.pack() for c in commands], {i: r.pack() for i, r in records.items()}) == core
    assert len(args[0]) + len(args[1]) + len(args[2]) + len(core.jobs) == 9
    assert core.jobs[0]['writeBytes'] == count * 2048
    assert core.jobs[1]['writeBytes'] == count * 4096
    assert core.jobs[1]['q'] == core.q_ddr + base * 4096
    assert core.jobs[1]['expectedCacheLength'] == length
    assert core.jobs[1]['cacheLength'] == length + count
    assert core.cache_v_ddr == core.cache_ddr + core.capacity * 1024
    assert all(job[f] for job in core.jobs for f in ('activationBf16', 'weightBf16', 'outputBf16'))
    assert core.jobs[0]['cacheLength'] == core.jobs[0]['expectedCacheLength'] == length
    assert all(job['currentGeneration'] == job['expectedGeneration'] == generation for job in core.jobs)


@pytest.mark.parametrize('op', list(Op))
def test_step_wire_layout_and_exact_headers(op):
    core = fixture(base=127, count=1, length=255, generation=3)[-1]
    binding = core.command_binding(op)
    command, records = build_host_attention_core_descriptor(binding, first_index=41, event_wait=17, event_signal=18)
    assert parse_host_attention_core_descriptor(command, records) == binding
    policy = next(r for r in records.values() if r.record_type == 0x24)
    context = next(r for r in records.values() if r.record_type == 0x26)
    word = policy.pack()
    assert word & 255 == 0x24 and (word >> 8) & 0xFFFFFF == 0
    assert (word >> 56) & 255 == 2
    assert (word >> 64) & 15 == op
    assert (word >> 68) & 0xFFFFFFFF == 127
    assert (word >> 100) & 255 == 1
    assert (word >> 108) & 255 == (0 if op in (Op.APPEND, Op.FENCE) else 0xA1)
    assert word >> 116 == 0
    word = context.pack()
    assert word & 255 == RecordType.ATTENTION_CONTEXT == 0x26
    assert (word >> 32) & 0xFFFFFF == NULL_INDEX
    assert (word >> 56) & 255 == 2
    assert (word >> 64) & 511 == 256
    assert (word >> 73) & 511 == 255
    assert (word >> 82) & 511 == 255
    assert (word >> 91) & 0xFFFFFFFF == 3
    assert (word >> 123) & 1 == 0 and (word >> 124) & 1 == 1
    assert word >> 125 == 0
    assert len(records) == binding.record_count
    if op in (Op.QK, Op.PV):
        mat, aux = records[44], records[45]
        assert aux.payload == MatrixAux().payload() == DENSE_MATRIX_AUX
        assert mat.payload & 0xFFFF == 1
        assert (mat.payload >> 16) & 0xFFFF == (256 if op == Op.QK else 256)
        assert (mat.payload >> 32) & 0xFFFFFF == 256
        assert (mat.payload >> 59) & 1 == (op == Op.QK)
    elif op in (Op.SOFTMAX, Op.FENCE):
        assert records[44].payload == SfuProgram(command.opcode, 1 if op == Op.SOFTMAX else 2).payload()


def test_rectangular_carried_attention_and_absolute_query_start():
    core = fixture(base=125, count=3, length=17, generation=2)[-1]
    assert core.tensors[4].shape == core.tensors[5].shape == (8, 3, 20)
    assert core.tensors[4].strides == (60, 20, 1)
    assert core.tensors[3].shape == (2, 256, 512)
    assert core.tensors[3].strides == (131072, 512, 1)
    for op, expected in ((Op.QK, (3, 20, 256, True)), (Op.PV, (3, 256, 20, False))):
        _, records = build_host_attention_core_descriptor(core.command_binding(op))
        p = records[3].payload
        assert (p & 65535, (p >> 16) & 65535, (p >> 32) & 0xFFFFFF, bool((p >> 59) & 1)) == expected
    assert core.jobs[1]['queryStart'] == 17


def test_scratch_logical_rw_reservations_are_padded_and_internal_only():
    core = fixture(count=1)[-1]
    score, probability = core.reservations[1:3]
    assert score['payloadBytes'] == probability['payloadBytes'] == 16
    assert score['bytes'] == probability['bytes'] == 64
    assert all(r['internalOnly'] and r['read'] and r['write'] for r in (score, probability))
    assert not core.reservations[0]['internalOnly'] and not core.reservations[3]['internalOnly']
    assert 'score' not in core.jobs[1] and 'probability' not in core.jobs[1]
    args = fixture(rows=1, count=1, capacity=1)
    commands, records = build_host_attention_core_commands(*args)
    assert validate_host_attention_core_commands(commands, records) == args[-1]


@pytest.mark.parametrize('op', list(Op))
def test_every_reserved_header_and_tail_cycle_rejected(op):
    command, records = build_host_attention_core_descriptor(fixture()[-1].command_binding(op))
    for index in records:
        for bit in (8, 16, 31):
            words = {i: r.pack() for i, r in records.items()}
            words[index] ^= 1 << bit
            with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, words)
    for index, record in records.items():
        corrupted = records | {index: replace(record, next_index=command.src0)}
        with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, corrupted)


@pytest.mark.parametrize('op', list(Op))
@pytest.mark.parametrize('kind,bits', [
    (0x24, (56, 60, 64, 67, 108, 115, 116, 127)),
    (0x26, (56, 63, 73, 82, 91, 123, 124, 125, 127)),
])
def test_policy_context_reserved_and_mismatched_fields_rejected(op, kind, bits):
    command, records = build_host_attention_core_descriptor(fixture()[-1].command_binding(op))
    index = next(i for i, r in records.items() if r.record_type == kind)
    for bit in bits:
        words = {i: r.pack() for i, r in records.items()}
        words[index] ^= 1 << bit
        with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, words)


@pytest.mark.parametrize('op', list(Op))
def test_tensor_rank_dtype_stride_shape_and_alias_corruptions(op):
    command, records = build_host_attention_core_descriptor(fixture()[-1].command_binding(op))
    roots = [r for r in (command.src0, command.src1, command.dst) if r != NULL_INDEX]
    for root in roots:
        for offset, bit in ((0, 104), (0, 108), (0, 112), (0, 116),
                            (1, 56), (1, 74), (1, 92), (1, 110),
                            (2, 56), (2, 80), (2, 104)):
            words = {i: r.pack() for i, r in records.items()}
            words[root + offset] ^= 1 << bit
            # A changed full row count may remain a legal larger allocation;
            # whole-chain validation below checks agreement with the producer.
            if offset == 1 and bit == 56 and root != command.dst and op in (Op.APPEND, Op.QK, Op.FENCE):
                continue
            with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, words)
    for root in roots[:-1]:
        bad = records | {command.dst: replace(records[command.dst], payload=records[root].payload)}
        with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, bad)


@pytest.mark.parametrize('op', [Op.QK, Op.SOFTMAX, Op.PV, Op.FENCE])
def test_numerical_recipe_rejects_every_program_field_change(op):
    command, records = build_host_attention_core_descriptor(fixture()[-1].command_binding(op))
    for index in range(3, 5 if op in (Op.QK, Op.PV) else 4):
        for bit in range(56, 128):
            words = {i: r.pack() for i, r in records.items()}
            words[index] ^= 1 << bit
            with pytest.raises(ValueError): parse_host_attention_core_descriptor(command, words)


@pytest.mark.parametrize('updates', [
    dict(rows=0), dict(rows=129), dict(token_count=0), dict(token_count=129),
    dict(token_base=128), dict(token_base=0xFFFFFFFF), dict(token_count=True),
    dict(capacity=0), dict(capacity=257), dict(capacity=3),
    dict(expected_length=1), dict(query_start=1), dict(expected_generation=1),
    dict(expected_generation=0xFFFFFFFF), dict(expected_generation=1 << 32),
    dict(cold=False), dict(cold=2), dict(q_ddr=1), dict(cache_ddr=(1 << 56) - 64),
    dict(score_ddr=0x10000000), dict(probability_ddr=0x11000000),
    dict(output_ddr=0xC000000 + 8192), dict(k_ddr=0xC000000 + 8192),
])
def test_core_resource_and_policy_preflight_rejects_invalid_inputs(updates):
    with pytest.raises(ValueError): replace(fixture()[-1], **updates)


def test_producer_bindings_cross_command_aliases_and_absolute_position():
    p, n, r, core = fixture(base=127, count=1, length=255, generation=3)
    for changes in (dict(q_ddr=0x20000000), dict(k_ddr=0x21000000), dict(v_ddr=0x22000000),
                    dict(token_base=126), dict(rows=127), dict(score_ddr=p[0].activation_ddr),
                    dict(cache_ddr=p[0].weight_ddr), dict(output_ddr=n[0].gate_output_ddr),
                    dict(expected_length=254, query_start=254)):
        with pytest.raises(ValueError): build_host_attention_core_commands(p, n, r, replace(core, **changes))
    # Existing read-only inputs also receive complete-allocation alias checks.
    with pytest.raises(ValueError):
        build_host_attention_core_commands(p, [n[0], replace(n[1], weight_ddr=n[0].weight_ddr)], r, core)


def test_untrusted_stream_requires_strict_events_order_and_same_cache():
    commands, records = build_host_attention_core_commands(*fixture())
    for index in range(12):
        changed = list(commands)
        changed[index] = replace(changed[index], event_wait=0 if index else 2)
        with pytest.raises(ValueError): validate_host_attention_core_commands(changed, records)
    for a, b in ((0, 1), (3, 4), (5, 6), (7, 8), (8, 10), (9, 11)):
        changed = list(commands)
        changed[a], changed[b] = replace(commands[b], event_wait=a, event_signal=a + 1), replace(commands[a], event_wait=b, event_signal=b + 1)
        with pytest.raises(ValueError): validate_host_attention_core_commands(changed, records)
    for step in range(7, 12):
        command = commands[step]
        for root in (command.src0, command.src1, command.dst):
            if root != NULL_INDEX:
                words = {i: r.pack() for i, r in records.items()}
                words[root] ^= 1 << (56 + 23)
                with pytest.raises(ValueError): validate_host_attention_core_commands(commands, words)


def test_chain_context_and_rectangles_cannot_drift_between_phases():
    commands, records = build_host_attention_core_commands(*fixture(count=3, length=17, generation=2))
    for step in range(7, 12):
        root = commands[step].src0
        chain_indices = []
        while root != NULL_INDEX:
            chain_indices.append(root)
            root = records[root].next_index
        policy_index, context_index = chain_indices[-2:]
        for index, bit in ((policy_index, 68), (policy_index, 100), (context_index, 64), (context_index, 91)):
            words = {i: r.pack() for i, r in records.items()}
            words[index] ^= 1 << bit
            with pytest.raises(ValueError): validate_host_attention_core_commands(commands, words)


def test_noncontiguous_descriptor_indices_follow_real_links():
    commands, records = build_host_attention_core_commands(*fixture())
    remap = {i: 11 + i * 19 for i in records}
    moved = {remap[i]: replace(r, next_index=remap.get(r.next_index, NULL_INDEX)) for i, r in records.items()}
    moved[remap[68]] = replace(moved[remap[68]], payload=remap[75])
    moved_commands = [replace(c, src0=remap[c.src0], src1=remap.get(c.src1, NULL_INDEX), dst=remap[c.dst]) for c in commands]
    assert validate_host_attention_core_commands(moved_commands, moved) == fixture()[-1]


def test_high_address_and_descriptor_event_boundaries():
    core = fixture(offset=1 << 48)[-1]
    core = replace(core, cache_ddr=(1 << 48) + core.cache_ddr)
    for op in Op:
        binding = core.command_binding(op)
        command, records = build_host_attention_core_descriptor(binding, first_index=NULL_INDEX - binding.record_count)
        assert parse_host_attention_core_descriptor(command.pack(), {i: r.pack() for i, r in records.items()}) == binding
        for kwargs in (dict(first_index=NULL_INDEX - binding.record_count + 1), dict(event_signal=0),
                       dict(event_signal=256), dict(event_wait=256), dict(event_wait=1), dict(event_wait=True)):
            with pytest.raises(ValueError): build_host_attention_core_descriptor(binding, **kwargs)


def test_carried_launch_protects_checkpoint_and_allows_expired_scratch_reuse():
    previous = fixture(count=128)[-1]
    current = fixture(count=128, length=128, generation=1, offset=0x20000000)[-1]
    assert validate_carried_attention_launch(previous, current) == current
    for changes in (dict(cache_ddr=0x15000000), dict(capacity=255, token_count=127),
                    dict(expected_length=127, query_start=127), dict(expected_generation=2),
                    dict(q_ddr=previous.output_ddr), dict(score_ddr=previous.output_ddr)):
        with pytest.raises(ValueError): validate_carried_attention_launch(previous, replace(current, **changes))
    for changes in (dict(q_ddr=previous.q_ddr), dict(score_ddr=previous.score_ddr)):
        reused = replace(current, **changes)
        assert validate_carried_attention_launch(previous, reused) == reused


def test_carried_full_stream_preserves_parameter_identities_and_committed_context():
    previous = fixture(count=1)
    current = fixture(base=127, count=1, length=1, generation=1, offset=0x20000000)
    old_commands, old_records = build_host_attention_core_commands(*previous)
    new_commands, new_records = build_host_attention_core_commands(*current)
    assert validate_carried_attention_commands(old_commands, old_records, new_commands, new_records) == current[-1]
    # Mutate all three Matrix weights, both Norm weights, and the shared trig table.
    for index in range(6):
        projections, norms, ropes, core = fixture(base=127, count=1, length=1, generation=1, offset=0x20000000)
        if index < 3:
            projections[index] = replace(projections[index], weight_ddr=0x50000000)
        elif index < 5:
            norms[index - 3] = replace(norms[index - 3], weight_ddr=0x50000000)
        else:
            ropes = [replace(r, trig_ddr=0x50000000) for r in ropes]
        commands, records = build_host_attention_core_commands(projections, norms, ropes, core)
        with pytest.raises(ValueError, match='identities'):
            validate_carried_attention_commands(old_commands, old_records, commands, records)
    # A new hidden tensor cannot consume the protected previous context buffer.
    projections = [replace(p, activation_ddr=previous[-1].output_ddr) for p in current[0]]
    commands, records = build_host_attention_core_commands(projections, *current[1:])
    with pytest.raises(ValueError, match='overlap'):
        validate_carried_attention_commands(old_commands, old_records, commands, records)


def test_carried_scratch_lifetime_matches_scala_control_sequence():
    # Match HostAttentionCoreCommandsSpec.program: all scratch is identical;
    # only the committed context alternates after an accepted fence.
    def scala_layout(length, generation, context):
        p, n, r, core = fixture(base=127, count=1, length=length, generation=generation)
        core = replace(core, cache_ddr=0x14000000, score_ddr=0x10000000,
                       probability_ddr=0x11000000, output_ddr=context)
        return build_host_attention_core_commands(p, n, r, core)
    cold = scala_layout(0, 0, 0x12000000)
    carried = scala_layout(1, 1, 0x13000000)
    third = scala_layout(2, 2, 0x12000000)
    validate_carried_attention_commands(*cold, *carried)
    validate_carried_attention_commands(*carried, *third)
    # The immediately committed context cannot be overwritten before its fence.
    with pytest.raises(ValueError, match='overlap'):
        validate_carried_attention_commands(*cold, *scala_layout(1, 1, 0x12000000))


def export_wire_fixtures(destination):
    """Hand the Scala candidate exact independently parsed raw command fixtures."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    cold1 = build_host_attention_core_commands(*fixture(count=1))
    carry1 = build_host_attention_core_commands(*fixture(base=127, count=1, length=1, generation=1, offset=0x20000000))
    validate_carried_attention_commands(*cold1, *carry1)
    for name, kwargs in [('realcold1', dict(count=1)),
                         ('carry1', dict(base=127, count=1, length=1, generation=1, offset=0x20000000)),
                         ('cold', dict(count=4)), ('carried', dict(base=125, count=3, length=17, generation=2)),
                         ('cold128', dict(count=128)), ('carried128', dict(count=128, length=128, generation=1))]:
        args = fixture(**kwargs)
        commands, records = build_host_attention_core_commands(*args)
        validate_host_attention_core_commands(commands, records)
        (destination / f'{name}.json').write_text(json.dumps({
            'name': name, 'commands': [f'{c.pack():032x}' for c in commands],
            'records': {str(i): f'{r.pack():032x}' for i, r in records.items()},
            'jobs': args[-1].jobs, 'reservations': args[-1].reservations,
        }, indent=2) + '\n')
