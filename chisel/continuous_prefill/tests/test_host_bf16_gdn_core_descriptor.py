"""Small, tensor-free tests for the production GDN core v2 command contract."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from host_bf16_gdn_core_descriptor import (
    GdnCoreOperation as Op, HostGdnCoreBinding as Binding, HostGdnCoreTensor as Tensor,
    TensorDType as DType, RecordType, NULL_INDEX, build_host_gdn_core_commands,
    build_host_gdn_core_descriptor, parse_host_gdn_core_commands,
    parse_host_gdn_core_descriptor, validate_host_gdn_core_transaction,
    validate_host_gdn_core_continuation,
)


def transaction(*, cold=True, generation=0):
    """Allocate only symbolic DDR addresses, never data or weight fixtures."""
    address = 0x10000

    def tensor(dtype, rows, columns):
        nonlocal address
        result = Tensor(address, dtype, (rows, columns))
        address += result.span_bytes + 64
        return result

    bf, fp = DType.BF16, DType.FP32
    hidden = tensor(bf, 1, 1024)
    qkv_w, z_w, ab_w = (tensor(bf, 1024, n) for n in (6144, 2048, 32))
    conv_w, hist_in, hist_out = (tensor(bf, 6144, 4) for _ in range(3))
    state_in, state_out = (tensor(fp, 2048, 128) for _ in range(2))
    a_log, dt_bias, gamma = tensor(fp, 1, 16), tensor(bf, 1, 16), tensor(fp, 1, 128)
    qkv, z, ab = (tensor(bf, 1, n) for n in (6144, 2048, 32))
    conv, prep = tensor(bf, 1, 6144), tensor(fp, 1, 6400)
    core, norm = tensor(bf, 1, 2048), tensor(bf, 1, 2048)
    policy = dict(cold=cold, expected_generation=generation)
    return [
        Binding(Op.DENSE, hidden, qkv_w, qkv, **policy),
        Binding(Op.DENSE, hidden, z_w, z, **policy),
        Binding(Op.DENSE, hidden, ab_w, ab, **policy),
        Binding(Op.CONV4, qkv, conv_w, conv, hist_in, hist_out, **policy),
        Binding(Op.INPUT_PREP, conv, ab, prep, a_log, dt_bias, **policy),
        Binding(Op.RECURRENT, prep, state_in, core, state_out, **policy),
        Binding(Op.GATED_NORM, core, z, norm, gamma, **policy),
        Binding(Op.FENCE, hist_out, state_out, norm, **policy),
    ]


class HostGdnCoreDescriptorTests(unittest.TestCase):
    def test_single_descriptor_roundtrip_cold_and_carried(self):
        for bindings in (transaction(), transaction(cold=False, generation=19)):
            for binding in bindings:
                with self.subTest(operation=binding.operation, cold=binding.cold):
                    command, records = build_host_gdn_core_descriptor(binding, first_index=37, event_wait=2, event_signal=9)
                    self.assertEqual(len(records), binding.record_count)
                    self.assertEqual(binding, parse_host_gdn_core_descriptor(
                        command.pack(), {i: record.pack() for i, record in records.items()}))

    def test_complete_eight_command_roundtrip_and_envelopes(self):
        for bindings in (transaction(), transaction(cold=False, generation=1)):
            commands, records = build_host_gdn_core_commands(bindings, first_index=11)
            self.assertEqual(len(records), 113)
            self.assertEqual([command.src0 for command in commands], [11, 23, 35, 47, 65, 83, 98, 113])
            self.assertEqual([(command.opcode, command.engine) for command in commands], [(0x20, 2)] * 3 + [(0x30, 3)] * 5)
            self.assertEqual([(command.event_wait, command.event_signal) for command in commands], list(zip(range(8), range(1, 9))))
            self.assertEqual(tuple(bindings), parse_host_gdn_core_commands(
                [command.pack() for command in commands], {i: record.pack() for i, record in records.items()}))

    def test_public_policy_dtype_and_extra_root_encoding(self):
        bindings = transaction()
        for binding in bindings:
            command, records = build_host_gdn_core_descriptor(binding)
            dense = binding.operation == Op.DENSE
            policy = records[5 if dense else 4]
            self.assertEqual(policy.payload, 2 | int(binding.operation) << 8 | 1 << 24)
            self.assertEqual(policy.record_type, RecordType.GDN_POLICY)
            if not dense:
                program = records[3].payload
                pair = ((7, 5) if binding.operation == Op.RECURRENT else
                        (5, 7) if binding.operation == Op.INPUT_PREP else (5, 5))
                self.assertEqual(program, 0x30 | 2 << 16 | 1 << 24 | pair[0] << 32 | pair[1] << 36 | 16 << 40 | 1 << 48)
            if binding.operation == Op.FENCE:
                self.assertEqual(len(records), 11)
                self.assertEqual(policy.next_index, NULL_INDEX)
                self.assertEqual((command.src1, command.dst), (5, 8))
            elif not dense:
                self.assertEqual(records[5].record_type, 0x22 if binding.operation == Op.CONV4 else 0x23)
                self.assertEqual(records[5].payload, 12 | (15 if binding.aux1 is not None else NULL_INDEX) << 24)

    def test_native_geometry_and_padding(self):
        bindings = transaction()
        prep = bindings[4]
        self.assertEqual(prep.d.logical_bytes, 3 * 8192 + 1024)
        self.assertEqual((prep.aux1.logical_bytes, prep.aux1.span_bytes), (32, 64))
        self.assertEqual(bindings[2].d.span_bytes, 64)
        self.assertEqual(bindings[5].b.logical_bytes, 1048576)
        high = 0xAB << 48
        tensor = replace(bindings[0].a, address=high)
        binding = replace(bindings[0], a=tensor)
        command, records = build_host_gdn_core_descriptor(binding)
        self.assertEqual(parse_host_gdn_core_descriptor(command, records).a.address, high)

    def test_tensor_address_type_and_shape_rejections(self):
        for args in ((1, 5, (1, 16)), ((1 << 56) - 64, 7, (1, 32)),
                     (0, 6, (1, 16)), (0, 5, (0, 16)), (0, 5, (1, 2, 3)),
                     (True, 5, (1, 16)), (0, 5, (1.0, 16))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Tensor(*args)
        for index, field, value in ((0, "a", Tensor(0x3000000, 5, (2, 1024))),
                                    (4, "b", Tensor(0x3000000, 5, (1, 16))),
                                    (4, "d", Tensor(0x3000000, 5, (1, 6400))),
                                    (6, "aux0", Tensor(0x3000000, 5, (1, 128)))):
            with self.assertRaises(ValueError):
                replace(transaction()[index], **{field: value})

    def test_policy_generation_mode_validation(self):
        for kwargs in (dict(cold=True, expected_generation=1), dict(expected_generation=0xFFFFFFFF),
                       dict(cold=True, recurrent_mode=True), dict(cold=False, recurrent_mode=False),
                       dict(expected_generation=-1), dict(expected_generation=True),
                       dict(cold=False, recurrent_mode=True, expected_generation=0)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(transaction()[0], **kwargs)
        bindings = transaction()
        bindings[4] = replace(bindings[4], cold=False, recurrent_mode=True, expected_generation=1)
        with self.assertRaisesRegex(ValueError, "must match"):
            validate_host_gdn_core_transaction(bindings)

    def test_continuation_requires_committed_pair_and_generation(self):
        previous = transaction()

        def carry(bindings):
            current = [replace(binding, cold=False, recurrent_mode=True,
                               expected_generation=binding.expected_generation + 1) for binding in bindings]
            current[3] = replace(current[3], aux0=bindings[7].a, aux1=bindings[3].aux0)
            current[5] = replace(current[5], b=bindings[7].b, aux0=bindings[5].b)
            current[7] = replace(current[7], a=current[3].aux1, b=current[5].aux0)
            return current

        second = carry(previous)
        third = carry(second)
        validate_host_gdn_core_continuation(previous, second)
        validate_host_gdn_core_continuation(second, third)
        self.assertEqual(third[7].a, previous[7].a)
        self.assertEqual(third[7].b, previous[7].b)
        self.assertEqual(third[0].d, previous[0].d)
        # Fresh-looking external tensors alone do not establish continuation.
        with self.assertRaisesRegex(ValueError, "fence bindings"):
            validate_host_gdn_core_continuation(previous, transaction(cold=False, generation=1))
        for invalid in (transaction(), [replace(binding, expected_generation=2) for binding in second]):
            with self.assertRaisesRegex(ValueError, "generation"):
                validate_host_gdn_core_continuation(previous, invalid)
        changed = second.copy()
        changed[0] = replace(changed[0], b=replace(changed[0].b, address=0x6000000))
        with self.assertRaisesRegex(ValueError, "checkpoint weight"):
            validate_host_gdn_core_continuation(previous, changed)

    def test_malformed_policy_program_and_matrix_bits(self):
        for binding in transaction():
            command, records = build_host_gdn_core_descriptor(binding)
            policy_index = 5 if binding.operation == Op.DENSE else 4
            for bit_index in (0, 8, 16, 23, 25, 26, 31, 32, 64, 71):
                changed = records | {policy_index: replace(records[policy_index], payload=records[policy_index].payload ^ (1 << bit_index))}
                with self.subTest(op=binding.operation, bit=bit_index), self.assertRaises(ValueError):
                    parse_host_gdn_core_descriptor(command, changed)
            for slot in ((3, 4) if binding.operation == Op.DENSE else (3,)):
                for bit_index in (0, 16, 24, 32, 36, 40, 48, 56, 64, 71):
                    changed = records | {slot: replace(records[slot], payload=records[slot].payload ^ (1 << bit_index))}
                    with self.subTest(op=binding.operation, slot=slot, bit=bit_index), self.assertRaises(ValueError):
                        parse_host_gdn_core_descriptor(command, changed)

    def test_reject_v1_and_operation_opcode_mismatch(self):
        command, records = build_host_gdn_core_descriptor(transaction()[0])
        for policy in (0x201, 0x202, 0x1000002, 0x1000702, 0x1000102):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                parse_host_gdn_core_descriptor(command, records | {5: replace(records[5], payload=policy)})

    def test_missing_duplicate_wrong_and_reserved_auxiliary_roots(self):
        for index in (3, 4, 5, 6):
            binding = transaction()[index]
            command, records = build_host_gdn_core_descriptor(binding)
            for payload in (records[5].payload | 1 << 48, NULL_INDEX | NULL_INDEX << 24,
                            12 | 12 << 24, 0 | 15 << 24, 0x1234 | NULL_INDEX << 24):
                with self.subTest(op=binding.operation, payload=payload), self.assertRaises(ValueError):
                    parse_host_gdn_core_descriptor(command, records | {5: replace(records[5], payload=payload)})
            wrong_type = RecordType.GDN_AUX_ROOTS if index == 3 else RecordType.GDN_STATE_ROOTS
            with self.assertRaises(ValueError):
                parse_host_gdn_core_descriptor(command, records | {5: replace(records[5], record_type=wrong_type)})
        binding = transaction()[5]
        with self.assertRaises(ValueError):
            replace(binding, aux1=transaction()[4].aux1)

    def test_tensor_chain_reserved_layout_stride_and_tail_rejections(self):
        command, records = build_host_gdn_core_descriptor(transaction()[4])
        for slot, bit_index in ((0, 48), (0, 56), (0, 60), (1, 36), (2, 24)):
            with self.subTest(slot=slot, bit=bit_index), self.assertRaises(ValueError):
                parse_host_gdn_core_descriptor(command, records | {slot: replace(records[slot], payload=records[slot].payload ^ (1 << bit_index))})
        for slot, target in ((8, 9), (2, 0), (5, 5), (17, 3)):
            with self.subTest(slot=slot, target=target), self.assertRaises(ValueError):
                parse_host_gdn_core_descriptor(command, records | {slot: replace(records[slot], next_index=target)})
        with self.assertRaises(ValueError):
            parse_host_gdn_core_descriptor(command, {i: r for i, r in records.items() if i != 16})

    def test_requires_each_actual_producer_and_shared_hidden(self):
        for index, field in ((1, "a"), (2, "a"), (3, "a"), (4, "a"), (4, "b"),
                             (5, "a"), (6, "a"), (6, "b"), (7, "a"), (7, "b"), (7, "d")):
            bindings = transaction()
            tensor = replace(getattr(bindings[index], field), address=0x4000000)
            bindings[index] = replace(bindings[index], **{field: tensor})
            with self.subTest(index=index, field=field), self.assertRaisesRegex(ValueError, "producer/source"):
                build_host_gdn_core_commands(bindings)

    def test_rejects_different_readonly_sources_overlapping_across_commands(self):
        bindings = transaction()
        bindings[1] = replace(bindings[1], b=replace(bindings[1].b, address=bindings[0].b.address + 64))
        with self.assertRaisesRegex(ValueError, "physical tensor alias"):
            validate_host_gdn_core_transaction(bindings)
        bindings = transaction()
        bindings[6] = replace(bindings[6], aux0=replace(bindings[6].aux0, address=bindings[4].aux0.address))
        with self.assertRaisesRegex(ValueError, "physical tensor alias"):
            validate_host_gdn_core_transaction(bindings)

    def test_output_cannot_overwrite_later_source_or_old_producer(self):
        bindings = transaction()
        changed = replace(bindings[0].d, address=bindings[6].aux0.address)
        bindings[0], bindings[3] = replace(bindings[0], d=changed), replace(bindings[3], a=changed)
        with self.assertRaisesRegex(ValueError, "physical tensor alias"):
            validate_host_gdn_core_transaction(bindings)
        bindings = transaction()
        changed = replace(bindings[6].d, address=bindings[0].d.address)
        bindings[6], bindings[7] = replace(bindings[6], d=changed), replace(bindings[7], d=changed)
        with self.assertRaisesRegex(ValueError, "physical tensor alias"):
            validate_host_gdn_core_transaction(bindings)

    def test_per_command_alias_includes_readonly_and_state_pingpong(self):
        for index, field, address_field in ((0, "b", "a"), (3, "aux1", "aux0"),
                                            (5, "aux0", "b"), (7, "d", "a")):
            binding = transaction()[index]
            value = replace(getattr(binding, field), address=getattr(binding, address_field).address)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "physical tensor alias"):
                replace(binding, **{field: value})

    def test_transaction_order_count_and_shared_descriptor_rejections(self):
        bindings = transaction()
        for changed in (bindings[:-1], bindings + bindings[-1:], [bindings[1], bindings[0], *bindings[2:]],
                        [*bindings[:6], bindings[7], bindings[6]]):
            with self.assertRaises(ValueError):
                build_host_gdn_core_commands(changed)
        commands, records = build_host_gdn_core_commands(bindings)
        commands[-1] = replace(commands[-1], dst=commands[-2].dst)
        self.assertEqual(bindings[-1], parse_host_gdn_core_descriptor(commands[-1], records))
        with self.assertRaisesRegex(ValueError, "indices must be distinct"):
            parse_host_gdn_core_commands(commands, records)

    def test_event_dependency_flags_and_aperture_rejections(self):
        bindings = transaction()
        for kwargs in (dict(first_signal=0), dict(first_signal=249), dict(event_wait=4),
                       dict(event_wait=256), dict(first_index=NULL_INDEX - 112)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_host_gdn_core_commands(bindings, **kwargs)
        commands, records = build_host_gdn_core_commands(bindings, first_index=NULL_INDEX - 113, event_wait=200, first_signal=248)
        self.assertEqual(tuple(bindings), parse_host_gdn_core_commands(commands, records))
        commands[3] = replace(commands[3], event_wait=1)
        with self.assertRaisesRegex(ValueError, "event dependency"):
            parse_host_gdn_core_commands(commands, records)
        command, records = build_host_gdn_core_descriptor(bindings[0])
        with self.assertRaises(ValueError):
            parse_host_gdn_core_descriptor(replace(command, flags=1), records)

    def test_contract_matches_public_enum_and_builder(self):
        directory = Path(__file__).resolve().parents[1]

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result, f"duplicate JSON key: {key}")
                result[key] = value
            return result

        contract = json.loads((directory / "config/host_bf16_gdn_core_descriptor_contract.json").read_text(), object_pairs_hook=unique_pairs)
        public = json.loads((directory.parents[1] / "config/descriptor_public_encoding.json").read_text(), object_pairs_hook=unique_pairs)
        self.assertEqual(contract["record_counts"], [binding.record_count for binding in transaction()])
        self.assertEqual(contract["transaction_record_count"], 113)
        self.assertEqual(public["gdn_aux_roots"]["record_type"], RecordType.GDN_AUX_ROOTS)
        self.assertEqual(public["gdn_policy"]["version"], 1)
        self.assertEqual(public["gdn_policy_v2"]["version"], 2)


if __name__ == "__main__":
    unittest.main()
