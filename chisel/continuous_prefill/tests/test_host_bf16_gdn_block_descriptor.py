"""CONTROL_ONLY: tensor-free tests of the production full-block v3 ABI."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from host_bf16_gdn_block_descriptor import (
    GdnBlockOperation as Op, HostGdnBlockBinding as Binding, HostGdnBlockTensor as Tensor,
    TensorDType as DType, RecordType, NULL_INDEX, BLOCK_SEQUENCE, PARAMETER_BINDINGS,
    build_host_gdn_block_commands, build_host_gdn_block_descriptor,
    parse_host_gdn_block_commands, parse_host_gdn_block_descriptor,
    validate_host_gdn_block_transaction, validate_host_gdn_block_continuation,
)


def transaction(*, cold=True, generation=0):
    """Symbolic DDR allocations only; no hidden values, weights, or payloads."""
    address = 0x10000

    def tensor(rows, columns, dtype=DType.BF16):
        nonlocal address
        result = Tensor(address, dtype, (rows, columns))
        address += result.span_bytes + 64
        return result

    raw, ig, pg = (tensor(1, 1024) for _ in range(3))
    qw, zw, abw = (tensor(1024, n) for n in (6144, 2048, 32))
    cw, hin, hout = (tensor(6144, 4) for _ in range(3))
    sin, sout = (tensor(2048, 128, DType.FP32) for _ in range(2))
    alog, dt, gamma = tensor(1, 16, DType.FP32), tensor(1, 16), tensor(1, 128, DType.FP32)
    ow, gw, uw, dw = tensor(2048, 1024), tensor(1024, 3584), tensor(1024, 3584), tensor(3584, 1024)
    inp, qkv, z, ab = (tensor(1, n) for n in (1024, 6144, 2048, 32))
    conv, prep = tensor(1, 6144), tensor(1, 6400, DType.FP32)
    core, norm, out, r1, post = (tensor(1, n) for n in (2048, 2048, 1024, 1024, 1024))
    gate, up, silu, down, r2 = (tensor(1, n) for n in (3584, 3584, 3584, 1024, 1024))
    context = dict(cold=cold, expected_generation=generation)
    return [
        Binding(Op.RMS_NORM, raw, ig, inp, role=0, **context),
        Binding(Op.DENSE, inp, qw, qkv, role=0, **context),
        Binding(Op.DENSE, inp, zw, z, role=1, **context),
        Binding(Op.DENSE, inp, abw, ab, role=2, **context),
        Binding(Op.CONV4, qkv, cw, conv, hin, hout, **context),
        Binding(Op.INPUT_PREP, conv, ab, prep, alog, dt, **context),
        Binding(Op.RECURRENT, prep, sin, core, sout, **context),
        Binding(Op.GATED_NORM, core, z, norm, gamma, **context),
        Binding(Op.DENSE, norm, ow, out, role=3, **context),
        Binding(Op.ELEMENTWISE, raw, out, r1, role=0, **context),
        Binding(Op.RMS_NORM, r1, pg, post, role=1, **context),
        Binding(Op.DENSE, post, gw, gate, role=4, **context),
        Binding(Op.DENSE, post, uw, up, role=5, **context),
        Binding(Op.ELEMENTWISE, gate, up, silu, role=1, **context),
        Binding(Op.DENSE, silu, dw, down, role=6, **context),
        Binding(Op.ELEMENTWISE, r1, down, r2, role=2, **context),
        Binding(Op.FENCE, hout, sout, r2, **context),
    ]


def carry(previous):
    current = [replace(b, cold=False, recurrent_mode=True,
                       expected_generation=b.expected_generation + 1) for b in previous]
    current[4] = replace(current[4], aux0=previous[16].a, aux1=previous[4].aux0)
    current[6] = replace(current[6], b=previous[16].b, aux0=previous[6].b)
    current[16] = replace(current[16], a=current[4].aux1, b=current[6].aux0)
    return current


class HostGdnBlockDescriptorTests(unittest.TestCase):
    def test_single_and_complete_roundtrip(self):
        for bindings in (transaction(), transaction(cold=False, generation=92)):
            for binding in bindings:
                command, records = build_host_gdn_block_descriptor(binding, first_index=37, event_wait=2, event_signal=9)
                self.assertEqual(len(records), binding.record_count)
                self.assertEqual(binding, parse_host_gdn_block_descriptor(command.pack(), {i: r.pack() for i, r in records.items()}))
            commands, records = build_host_gdn_block_commands(bindings, first_index=11)
            self.assertEqual(len(commands), 17)
            self.assertEqual(len(records), 216)
            self.assertEqual([(c.event_wait, c.event_signal) for c in commands], list(zip(range(17), range(1, 18))))
            self.assertEqual(tuple(bindings), parse_host_gdn_block_commands([c.pack() for c in commands], {i: r.pack() for i, r in records.items()}))

    def test_public_roles_programs_and_record_counts(self):
        for b in transaction():
            c, records = build_host_gdn_block_descriptor(b)
            dense = b.operation == Op.DENSE
            policy = records[5 if dense else 4]
            self.assertEqual(policy.payload, 3 | int(b.operation) << 8 | 1 << 24 | b.role << 26)
            self.assertEqual(policy.record_type, RecordType.GDN_POLICY)
            self.assertEqual((c.opcode, c.engine), (0x20, 2) if dense else (0x30, 3))
            if dense:
                self.assertEqual(records[3].payload, 1 | b.d.shape[1] << 16 | b.a.shape[1] << 32)
            else:
                pair = (7, 5) if b.operation == Op.RECURRENT else (5, 7) if b.operation == Op.INPUT_PREP else (5, 5)
                self.assertEqual(records[3].payload, 0x30 | 2 << 16 | 1 << 24 | pair[0] << 32 | pair[1] << 36 | 16 << 40 | 1 << 48)
            if b.operation in (Op.FENCE, Op.RMS_NORM, Op.ELEMENTWISE):
                self.assertEqual((len(records), policy.next_index, c.src1, c.dst), (11, NULL_INDEX, 5, 8))
            elif not dense:
                self.assertEqual(records[5].payload, 12 | (15 if b.aux1 is not None else NULL_INDEX) << 24)

    def test_preserves_core_tensor_and_padding(self):
        from host_bf16_gdn_core_descriptor import HostGdnCoreTensor
        self.assertIs(Tensor, HostGdnCoreTensor)
        b = transaction()
        self.assertEqual((b[5].aux1.logical_bytes, b[5].aux1.span_bytes), (32, 64))
        self.assertEqual(b[6].b.logical_bytes, 1048576)
        self.assertEqual(b[13].d.logical_bytes, 7168)
        high = replace(b[0], a=replace(b[0].a, address=0xAB << 48))
        self.assertEqual(high, parse_host_gdn_block_descriptor(*build_host_gdn_block_descriptor(high)))

    def test_invalid_roles_types_and_shapes(self):
        for b in transaction():
            for role in (-1, 7, True):
                with self.subTest(op=b.operation, role=role), self.assertRaises(ValueError):
                    replace(b, role=role)
            for field in ("a", "b", "d"):
                tensor = getattr(b, field)
                dtype = DType.FP32 if tensor.dtype == DType.BF16 else DType.BF16
                with self.subTest(op=b.operation, field=field), self.assertRaises(ValueError):
                    replace(b, **{field: replace(tensor, dtype=dtype)})
        for pc, value in ((0, (2, 1024)), (8, (1, 1024)), (13, (1, 1024)), (14, (1, 2048))):
            b = transaction()[pc]
            with self.assertRaises(ValueError):
                replace(b, a=replace(b.a, shape=value))
        with self.assertRaises(ValueError):
            replace(transaction()[0], operation=7)

    def test_context_validation(self):
        for kwargs in (dict(cold=True, expected_generation=1), dict(expected_generation=0xFFFFFFFF),
                       dict(cold=True, recurrent_mode=True), dict(cold=False, expected_generation=0),
                       dict(expected_generation=True)):
            with self.assertRaises(ValueError):
                replace(transaction()[0], **kwargs)
        for pc in range(17):
            b = transaction()
            b[pc] = replace(b[pc], cold=False, recurrent_mode=True, expected_generation=1)
            with self.assertRaisesRegex(ValueError, "must match"):
                validate_host_gdn_block_transaction(b)

    def test_actual_producers_and_original_raw_hidden(self):
        fields = ((1, "a"), (2, "a"), (3, "a"), (4, "a"), (5, "a"), (5, "b"),
                  (6, "a"), (7, "a"), (7, "b"), (8, "a"), (9, "a"), (9, "b"),
                  (10, "a"), (11, "a"), (12, "a"), (13, "a"), (13, "b"),
                  (14, "a"), (15, "a"), (15, "b"), (16, "a"), (16, "b"), (16, "d"))
        for pc, field in fields:
            b = transaction()
            b[pc] = replace(b[pc], **{field: replace(getattr(b[pc], field), address=0x6000000)})
            with self.subTest(pc=pc, field=field), self.assertRaisesRegex(ValueError, "producer/source"):
                build_host_gdn_block_commands(b)
        b = transaction()
        b[1] = replace(b[1], a=b[0].a)
        with self.assertRaisesRegex(ValueError, "producer/source"):
            build_host_gdn_block_commands(b)

    def test_all_thirteen_parameters_stay_bound_across_carry(self):
        first = transaction()
        second, third = carry(first), carry(carry(first))
        validate_host_gdn_block_continuation(first, second)
        validate_host_gdn_block_continuation(second, third)
        self.assertEqual((third[16].a, third[16].b), (first[16].a, first[16].b))
        self.assertEqual(len(PARAMETER_BINDINGS), 13)
        for pc, field in PARAMETER_BINDINGS:
            changed = second.copy()
            changed[pc] = replace(changed[pc], **{field: replace(getattr(changed[pc], field), address=0x6000000)})
            with self.subTest(pc=pc, field=field), self.assertRaisesRegex(ValueError, "checkpoint weight"):
                validate_host_gdn_block_continuation(first, changed)
        with self.assertRaisesRegex(ValueError, "fence bindings"):
            validate_host_gdn_block_continuation(first, transaction(cold=False, generation=1))
        with self.assertRaisesRegex(ValueError, "generation"):
            validate_host_gdn_block_continuation(first, [replace(b, expected_generation=2) for b in second])

    def test_next_raw_hidden_can_change_after_fence(self):
        first = transaction()
        second = carry(first)
        raw = replace(second[0].a, address=0x6000000)
        second[0], second[9] = replace(second[0], a=raw), replace(second[9], a=raw)
        validate_host_gdn_block_continuation(first, second)

    def test_readonly_source_alias_and_output_recycling_rejected(self):
        for pc, field, target in ((2, "b", (1, "b")), (10, "b", (0, "b")),
                                  (12, "b", (11, "b")), (14, "b", (12, "b")),
                                  (6, "b", (1, "b"))):
            b = transaction()
            b[pc] = replace(b[pc], **{field: replace(getattr(b[pc], field), address=getattr(b[target[0]], target[1]).address)})
            with self.assertRaisesRegex(ValueError, "physical tensor alias"):
                validate_host_gdn_block_transaction(b)
        b = transaction()
        late = replace(b[15].d, address=b[1].d.address)
        b[15], b[16] = replace(b[15], d=late), replace(b[16], d=late)
        with self.assertRaisesRegex(ValueError, "physical tensor alias"):
            validate_host_gdn_block_transaction(b)

    def test_reserved_policy_and_wrong_program_or_matrix(self):
        for b in transaction():
            c, records = build_host_gdn_block_descriptor(b)
            pi = 5 if b.operation == Op.DENSE else 4
            for bit_index in (0, 16, 23, 25, 29, 31, 32, 64, 71):
                bad = records | {pi: replace(records[pi], payload=records[pi].payload ^ 1 << bit_index)}
                with self.subTest(op=b.operation, bit=bit_index), self.assertRaises(ValueError):
                    parse_host_gdn_block_descriptor(c, bad)
            for policy in ((records[pi].payload & ~255) | 2,
                           (records[pi].payload & ~(255 << 8)) | 7 << 8,
                           (records[pi].payload & ~(7 << 26)) | 7 << 26):
                with self.assertRaises(ValueError):
                    parse_host_gdn_block_descriptor(c, records | {pi: replace(records[pi], payload=policy)})
            for slot in ((3, 4) if b.operation == Op.DENSE else (3,)):
                for bit_index in (0, 16, 24, 32, 36, 40, 48, 56, 64, 71):
                    bad = records | {slot: replace(records[slot], payload=records[slot].payload ^ 1 << bit_index)}
                    with self.assertRaises(ValueError):
                        parse_host_gdn_block_descriptor(c, bad)

    def test_auxiliary_reserved_missing_duplicate_and_extra_roots(self):
        for pc in (4, 5, 6, 7):
            b = transaction()[pc]
            c, records = build_host_gdn_block_descriptor(b)
            for payload in (records[5].payload | 1 << 48, NULL_INDEX | NULL_INDEX << 24,
                            12 | 12 << 24, 0 | 15 << 24, 0x1234 | NULL_INDEX << 24):
                with self.assertRaises(ValueError):
                    parse_host_gdn_block_descriptor(c, records | {5: replace(records[5], payload=payload)})
        for pc in (0, 9, 10, 13, 15, 16):
            with self.assertRaises(ValueError):
                replace(transaction()[pc], aux0=transaction()[5].aux0)

    def test_tensor_chain_layout_stride_tail_and_command_flags(self):
        c, records = build_host_gdn_block_descriptor(transaction()[0])
        for slot, bit_index in ((0, 48), (0, 56), (0, 60), (1, 36), (2, 24)):
            with self.assertRaises(ValueError):
                parse_host_gdn_block_descriptor(c, records | {slot: replace(records[slot], payload=records[slot].payload ^ 1 << bit_index)})
        for slot, target in ((7, 8), (2, 0), (4, 4)):
            with self.assertRaises(ValueError):
                parse_host_gdn_block_descriptor(c, records | {slot: replace(records[slot], next_index=target)})
        with self.assertRaises(ValueError):
            parse_host_gdn_block_descriptor(replace(c, flags=1), records)

    def test_order_count_role_and_shared_descriptor_rejections(self):
        b = transaction()
        for changed in (b[:-1], b + b[-1:], [b[1], b[0], *b[2:]]):
            with self.assertRaises(ValueError):
                build_host_gdn_block_commands(changed)
        bad = b.copy()
        bad[12] = replace(bad[12], role=4)
        with self.assertRaisesRegex(ValueError, "explicit roles"):
            build_host_gdn_block_commands(bad)
        c, records = build_host_gdn_block_commands(b)
        c[-1] = replace(c[-1], dst=c[-2].dst)
        self.assertEqual(b[-1], parse_host_gdn_block_descriptor(c[-1], records))
        with self.assertRaisesRegex(ValueError, "indices must be distinct"):
            parse_host_gdn_block_commands(c, records)

    def test_event_aperture_and_launch_zero(self):
        b = transaction()
        for kwargs in (dict(first_signal=0), dict(first_signal=240), dict(event_wait=200),
                       dict(event_wait=256), dict(first_index=NULL_INDEX - 215)):
            with self.assertRaises(ValueError):
                build_host_gdn_block_commands(b, **kwargs)
        c, records = build_host_gdn_block_commands(b, first_index=NULL_INDEX - 216, first_signal=239)
        self.assertEqual(tuple(b), parse_host_gdn_block_commands(c, records))
        for pc, wait in ((0, 238), (4, 0)):
            changed = c.copy()
            changed[pc] = replace(changed[pc], event_wait=wait)
            with self.assertRaisesRegex(ValueError, "event dependency"):
                parse_host_gdn_block_commands(changed, records)

    def test_contract_matches_encoder(self):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result)
                result[key] = value
            return result
        path = Path(__file__).resolve().parents[1] / "config/host_bf16_gdn_block_descriptor_contract.json"
        contract = json.loads(path.read_text(), object_pairs_hook=unique)
        self.assertEqual(contract["record_counts"], [b.record_count for b in transaction()])
        self.assertEqual(contract["transaction_record_count"], 216)
        self.assertEqual(contract["command_count"], 17)
        self.assertEqual(contract["owner_job_count"], 16)
        self.assertEqual(contract["policy"]["operations"], {op.name: int(op) for op in Op})
        self.assertEqual(contract["operation_roles"], [list(x) for x in BLOCK_SEQUENCE])
        self.assertEqual(contract["continuation"]["parameter_binding_count"], 13)


if __name__ == "__main__":
    unittest.main()
