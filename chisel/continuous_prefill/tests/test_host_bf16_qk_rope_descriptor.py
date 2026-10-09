"""Small Python wire/resource tests; no owner elaboration or numeric claims."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_bf16_qkv_descriptor import HostQkvBinding
from host_bf16_qk_rope_descriptor import (
    HostQkNormBinding, HostPartialRopeBinding, build_host_qk_rope_descriptor,
    parse_host_qk_rope_descriptor, build_host_qkv_rope_commands,
)
from heteronpu.command import Opcode, Engine
from heteronpu.descriptor_chain import NULL_INDEX, RecordType, SfuProgram


def norm(role=0, **updates):
    args = dict(role=role, rows=128, token_base=0, token_count=1,
                input_ddr=0x4000000 + role * 0x200000, weight_ddr=0x3000000 + role * 0x1000,
                output_ddr=0x5000000 + role * 0x200000, gate_output_ddr=0x6000000 if role == 0 else 0)
    return HostQkNormBinding(**(args | updates))


def rope(role=0, **updates):
    args = dict(role=role, rows=128, token_base=0, token_count=1,
                input_ddr=0x5000000 + role * 0x200000, trig_ddr=0x3200000,
                output_ddr=0x7000000 + role * 0x200000, trig_tokens=256, position_base=0)
    return HostPartialRopeBinding(**(args | updates))


@pytest.mark.parametrize('factory', [norm, rope])
@pytest.mark.parametrize('role', [0, 1])
@pytest.mark.parametrize('base,count', [(0, 1), (0, 16), (0, 128), (127, 1)])
def test_roundtrip_public_bf16_roots_and_offsets(factory, role, base, count):
    binding = factory(role, token_base=base, token_count=count)
    command, records = build_host_qk_rope_descriptor(binding, first_index=39, event_wait=7, event_signal=8)
    assert command.flags == 0 and command.engine == Engine.SFU_CGRA
    assert command.opcode == (Opcode.SFU_RMSNORM if factory is norm else Opcode.SFU_ROPE)
    assert (command.src0, command.src1, command.dst) == (39, 45, 48)
    assert len(records) == (15 if factory is norm and role == 0 else 12)
    assert parse_host_qk_rope_descriptor(command.pack(), {i: r.pack() for i, r in records.items()}) == binding
    assert records[42].payload == SfuProgram(command.opcode, 2).payload()
    for root in (39, 45, 48) + ((51,) if factory is norm and role == 0 else ()):
        payload, shape, stride = (records[root + i].payload for i in range(3))
        dims = tuple((shape >> (18 * i)) & 0x3FFFF for i in range(4))
        assert (payload >> 48) & 0xFFFF == 0x2050
        assert dims[2:] == (1, 1) and stride == dims[1] | 1 << 24 | 1 << 48
    assert binding.job['output'] == binding.output_ddr + base * binding.n * 2
    if factory is norm:
        assert binding.job['writeBytes'] == count * binding.n * 2 * (2 if role == 0 else 1)
        assert binding.job['gateOutput'] == (binding.gate_output_ddr + base * 4096 if role == 0 else 0)


@pytest.mark.parametrize('role', [0, 1])
def test_absolute_position_is_not_tensor_window_offset(role):
    cold = rope(role, token_base=0, position_base=0)
    carried = rope(role, token_base=127, position_base=255)
    assert cold.job['positionBase'] == 0
    assert carried.job['positionBase'] == 255
    assert carried.job['trig'] == carried.trig_ddr
    assert carried.job['input'] == carried.input_ddr + 127 * carried.n * 2
    command, records = build_host_qk_rope_descriptor(carried)
    assert records[5].payload == NULL_INDEX | 255 << 24
    assert parse_host_qk_rope_descriptor(command, records).position_base == 255
    with pytest.raises(ValueError, match='positions'):
        rope(role, token_base=126, token_count=2, position_base=255)


def test_exact_versioned_policy_and_enums():
    assert RecordType.ATTENTION_POLICY == 0x24
    assert RecordType.ATTENTION_AUX == 0x25
    for factory in (norm, rope):
        binding = factory(1, token_base=127)
        _, records = build_host_qk_rope_descriptor(binding)
        mode, recipe = (0, 0xC1) if factory is norm else (1, 0xB1)
        assert records[4].payload == 1 | 1 << 8 | mode << 10 | 127 << 12 | 1 << 44 | recipe << 52
        assert records[5].payload == NULL_INDEX


@pytest.mark.parametrize('index,bit', [
    (0, 104), (0, 108), (0, 112), (0, 116), (1, 56), (1, 74), (1, 92), (1, 110),
    (2, 56), (2, 80), (2, 104),
    (3, 56), (3, 72), (3, 80), (3, 88), (3, 92), (3, 96), (3, 104), (3, 112), (3, 120),
    (4, 56), (4, 65), (4, 66), (4, 108), (4, 116), (4, 127),
    (5, 80), (5, 112), (5, 127),
    (6, 108), (7, 56), (7, 74), (8, 56), (9, 108), (10, 56), (10, 74),
    (12, 108), (12, 116), (13, 56), (13, 74), (14, 56),
])
def test_raw_wire_corruptions_are_rejected(index, bit):
    command, records = build_host_qk_rope_descriptor(norm())
    words = {i: r.pack() for i, r in records.items()}
    words[index] ^= 1 << bit
    with pytest.raises(ValueError): parse_host_qk_rope_descriptor(command, words)


def test_reserved_headers_and_cycles_across_every_tensor():
    command, records = build_host_qk_rope_descriptor(norm())
    for index in records:
        for bit in (8, 16):
            words = {i: r.pack() for i, r in records.items()}
            words[index] ^= 1 << bit
            with pytest.raises(ValueError): parse_host_qk_rope_descriptor(command, words)
    for index, target in ((0, 0), (2, NULL_INDEX), (4, 3), (5, 6), (8, 0), (11, 12), (14, 0)):
        with pytest.raises(ValueError):
            parse_host_qk_rope_descriptor(command, records | {index: replace(records[index], next_index=target)})
    for gate_root in (NULL_INDEX, command.src0, command.src1, command.dst, 12345):
        with pytest.raises(ValueError):
            parse_host_qk_rope_descriptor(command, records | {5: replace(records[5], payload=gate_root)})
    with pytest.raises(ValueError): parse_host_qk_rope_descriptor(command, {i: r for i, r in records.items() if i != 14})


@pytest.mark.parametrize('factory,role', [(norm, 1), (rope, 0), (rope, 1)])
def test_non_qnorm_forbids_gate_root(factory, role):
    command, records = build_host_qk_rope_descriptor(factory(role))
    with pytest.raises(ValueError):
        parse_host_qk_rope_descriptor(command, records | {5: replace(records[5], payload=0)})


@pytest.mark.parametrize('updates', [dict(role=2), dict(rows=0), dict(rows=129), dict(token_count=0),
    dict(token_count=129), dict(token_base=128), dict(token_base=0xFFFFFFFF),
    dict(input_ddr=1), dict(weight_ddr=(1 << 56) - 64), dict(output_ddr=0x4000000),
    dict(gate_output_ddr=0x4000000), dict(gate_output_ddr=0x5000000), dict(gate_output_ddr=0x3000000)])
def test_norm_window_range_and_dual_output_alias(updates):
    with pytest.raises(ValueError): norm(**updates)


@pytest.mark.parametrize('updates', [dict(trig_tokens=0), dict(trig_tokens=1 << 18),
    dict(position_base=256), dict(position_base=1 << 32), dict(position_base=0xFFFFFFFF),
    dict(trig_ddr=(1 << 56) - 64), dict(output_ddr=0x3200000), dict(output_ddr=0x5000000)])
def test_rope_geometry_position_and_resource_bounds(updates):
    with pytest.raises(ValueError): rope(**updates)


def test_events_index_aperture_and_high_address_roundtrip():
    binding = norm(input_ddr=(1 << 48) + 0x1000000, output_ddr=(1 << 48) + 0x2000000,
                   gate_output_ddr=(1 << 48) + 0x3000000)
    command, records = build_host_qk_rope_descriptor(binding, first_index=NULL_INDEX - 15)
    assert parse_host_qk_rope_descriptor(command, records) == binding
    for kwargs in ({'first_index': NULL_INDEX - 14}, {'event_signal': 0}, {'event_signal': 256},
                   {'event_wait': 256}, {'event_wait': 1}, {'event_wait': True}):
        with pytest.raises(ValueError): build_host_qk_rope_descriptor(binding, **kwargs)
    for changes in (dict(flags=1), dict(event_signal=0), dict(event_signal=256), dict(event_wait=256),
                    dict(opcode=Opcode.SFU_VECTOR), dict(src1=command.src0)):
        with pytest.raises(ValueError): parse_host_qk_rope_descriptor(replace(command, **changes), records)


@pytest.mark.parametrize('factory', [norm, rope])
def test_inactive_prefix_suffix_cannot_hide_full_tensor_overflow_or_alias(factory):
    with pytest.raises(ValueError):
        factory(token_base=0, token_count=1, input_ddr=(1 << 56) - 8192)
    # Active one-row writes do not overlap this shifted input, but full buffers do.
    with pytest.raises(ValueError):
        factory(token_base=0, token_count=1, output_ddr=0x4000000 + 16384 if factory is norm else 0x5000000 + 16384)


@pytest.mark.parametrize('factory,role', [(norm, 0), (norm, 1), (rope, 0), (rope, 1)])
def test_opcode_mode_recipe_and_auxiliary_tail_cannot_alias(factory, role):
    command, records = build_host_qk_rope_descriptor(factory(role))
    for payload in (records[4].payload ^ (1 << 10), records[4].payload ^ (1 << 52),
                    records[4].payload | (1 << 71)):
        with pytest.raises(ValueError):
            parse_host_qk_rope_descriptor(command, records | {4: replace(records[4], payload=payload)})
    with pytest.raises(ValueError):
        parse_host_qk_rope_descriptor(command, records | {5: replace(records[5], next_index=command.dst)})
    other_opcode = Opcode.SFU_ROPE if factory is norm else Opcode.SFU_RMSNORM
    with pytest.raises(ValueError):
        parse_host_qk_rope_descriptor(replace(command, opcode=other_opcode), records)


def full_bindings(base=127, count=1, position=255):
    projections = [HostQkvBinding(role, 128, base, count, 0x1000000, 0x2000000 + role * 0x1000000,
                                 0x8000000 + role * 0x200000) for role in range(3)]
    norms = [norm(role, token_base=base, token_count=count, input_ddr=projections[role].output_ddr,
                  weight_ddr=0x5000000 + role * 0x1000, output_ddr=0xA000000 + role * 0x200000,
                  gate_output_ddr=0xB000000 if role == 0 else 0) for role in range(2)]
    ropes = [rope(role, token_base=base, token_count=count, input_ddr=norms[role].output_ddr,
                  trig_ddr=0x5200000, output_ddr=0xC000000 + role * 0x200000, position_base=position) for role in range(2)]
    return projections, norms, ropes


@pytest.mark.parametrize('base,count,position', [(0, 128, 0), (0, 128, 128), (127, 1, 127), (127, 1, 255)])
def test_seven_actual_dependencies_events_and_exact_114_records(base, count, position):
    projections, norms, ropes = full_bindings(base, count, position)
    commands, records = build_host_qkv_rope_commands(projections, norms, ropes)
    assert len(commands) == 7 and len(records) == 114 and set(records) == set(range(114))
    assert [c.src0 for c in commands] == [0, 21, 42, 63, 78, 90, 102]
    assert [(c.event_wait, c.event_signal) for c in commands] == [(i, i + 1) for i in range(7)]
    assert [parse_host_qk_rope_descriptor(c, records) for c in commands[3:]] == norms + ropes
    assert records[68].payload & 0xFFFFFF == 75
    assert sum(b.job['writeBytes'] for b in projections + norms + ropes) == count * 24576


def test_full_chain_rejects_false_dependencies_and_cross_output_aliases():
    projections, norms, ropes = full_bindings()
    for bad_norm in (replace(norms[0], input_ddr=0xE000000), replace(norms[0], output_ddr=projections[2].output_ddr),
                     replace(norms[0], gate_output_ddr=projections[1].output_ddr), replace(norms[0], token_base=126)):
        with pytest.raises(ValueError): build_host_qkv_rope_commands(projections, [bad_norm, norms[1]], ropes)
    for bad_rope in (replace(ropes[0], input_ddr=0xE000000), replace(ropes[0], position_base=254),
                     replace(ropes[0], output_ddr=norms[0].gate_output_ddr), replace(ropes[0], output_ddr=projections[0].weight_ddr)):
        with pytest.raises(ValueError): build_host_qkv_rope_commands(projections, norms, [bad_rope, ropes[1]])


def test_noncontiguous_indices_and_gate_root_are_followed():
    command, records = build_host_qk_rope_descriptor(norm())
    remap = {index: 100 + index * 17 for index in records}
    moved = {remap[i]: replace(r, next_index=remap.get(r.next_index, NULL_INDEX)) for i, r in records.items()}
    moved[remap[5]] = replace(moved[remap[5]], payload=remap[12])
    command = replace(command, src0=remap[0], src1=remap[6], dst=remap[9])
    assert parse_host_qk_rope_descriptor(command, moved) == norm()
