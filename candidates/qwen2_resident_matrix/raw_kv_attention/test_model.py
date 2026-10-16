"""Bit-preserving transport checks, not Attention arithmetic or RTL evidence."""
from collections import Counter
from dataclasses import replace
import unittest

from candidates.qwen2_resident_matrix.raw_kv_attention import model as m
from candidates.qwen2_resident_matrix.raw_kv import model as raw
from candidates.qwen2_resident_matrix.raw_kv_parent import model as parent


# Raw FP32 encodings include signed zero, infinities, quiet/signaling NaNs and
# subnormals. They are opaque integers; these tests never execute FP arithmetic.
WORDS = (0x00000000, 0x80000000, 0x7f800000, 0xff800000,
         0x7fc00001, 0x7fa00001, 0xffc12345, 0x00000001,
         0x80000001, 0x3f800000, 0xbf800000, 0x7f7fffff,
         0xff7fffff, 0x00800000, 0x80800000, 0x3f000000)
BITS = sum(word << (32 * index) for index, word in enumerate(WORDS))


def binding(tokens=128):
    return m.Binding(7, 11, 0x100000, 0x200000, tokens,
                     0x300000, tokens * 6144)


def payload(address):
    return BITS ^ (address << 128)


class Harness:
    """A one-command DDR responder, observing real shared-bank touches."""
    def __init__(self, tokens=128):
        self.supply = m.KvSupply(parent.ParentLoan(enabled=True), enabled=True)
        self.supply.bind(binding(tokens))
        self.banks = self.supply.parent.owner.a_banks
        self.bank_words = self.banks.words
        self.counts = Counter()
        self.ddr_addresses = []
        self.read_lines = []
        self.write_lines = []
        self.max_wait = 100

    def tick(self, **inputs):
        e = self.supply.tick(**inputs)
        if e['response_fire'] != (e['response'] is not None and inputs.get('response_ready', False)):
            raise AssertionError('core response valid/ready handshake was not honored')
        for name in ('request_fire', 'ddr_fire', 'ddr_response_fire',
                     'response_fire', 'released'):
            self.counts[name] += bool(e[name])
        if e['ddr_fire']:
            self.ddr_addresses.append(e['ddr_request'].address)
        r = e['parent']['raw']
        if r['accepted']:
            key = self.supply.raw_key
            (self.write_lines if key.write else self.read_lines).append(key.line)
        if self.banks.reads and self.banks.writes:
            raise AssertionError('simultaneous shared-bank read/write')
        if self.banks.words is not self.bank_words:
            raise AssertionError('shared bank allocation replaced')
        return e

    def until(self, predicate, **inputs):
        for _ in range(self.max_wait):
            e = self.tick(**inputs)
            if predicate(e):
                return e
        raise AssertionError(('no progress', self.supply.state,
                              self.supply.error_reason))

    def accept(self, request):
        return self.until(lambda e: e['request_fire'], request=request)

    def issue_miss(self, address=None, tag=0):
        b = self.supply.binding
        request = m.Read(tag, b.k_base if address is None else address)
        self.accept(request)
        e = self.until(lambda e: e['ddr_fire'], ddr_ready=True)
        if e['ddr_request'] != request:
            raise AssertionError('DDR command differs from accepted core request')
        return request

    def hold_reply(self, address, tag=0):
        request = m.Read(tag, address)
        accepted = False
        pending = None
        for _ in range(self.max_wait):
            e = self.tick(request=None if accepted else request,
                          ddr_ready=True, ddr_response=pending)
            if e['request_fire']:
                accepted = True
            if e['ddr_response_fire']:
                pending = None
            if e['ddr_fire']:
                if pending is not None:
                    raise AssertionError('multiple accepted DDR commands')
                pending = m.Reply(e['ddr_request'].tag,
                                  payload(e['ddr_request'].address))
            if e['response'] is not None:
                if not accepted or pending is not None:
                    raise AssertionError('response before accepted debt retired')
                return e['response']
        raise AssertionError(('no reply', self.supply.state))

    def read(self, address, tag=0):
        reply = self.hold_reply(address, tag)
        e = self.tick(response_ready=True)
        if not e['response_fire'] or e['response'] != reply:
            raise AssertionError('held reply was not consumed unchanged')
        return reply

    def finish(self):
        return self.until(lambda e: e['done_ready'], terminal=True)


class KvSupplyTests(unittest.TestCase):
    def test_all_4096_m128_fills_then_hits_use_only_original_banks(self):
        h = Harness()
        s, b = h.supply, h.supply.binding
        self.assertIsInstance(s.parent.owner, parent.DenseReductionOwner)
        self.assertIs(s.parent.raw.banks, h.banks)
        self.assertIs(s.parent.owner.tiles.banks, h.banks)
        self.assertIsNone(s.parent.raw.owner)  # bind is metadata-only, lazy loan
        self.assertEqual(len(s.valid), 512)
        self.assertFalse(any(s.valid))
        addresses = [b.k_base + line * 64 for line in range(2048)]
        addresses += [b.v_base + line * 64 for line in range(2048)]
        for line, address in enumerate(addresses):
            with self.subTest(fill=line):
                self.assertEqual(s.line(address), line)
                reply = h.read(address, line)
                self.assertEqual(reply, m.Reply(line, payload(address)))
                self.assertTrue(s.present(line))
                lo, hi, word = raw.location(line)
                self.assertEqual(h.banks.words[lo][word], payload(address) & ((1 << 256) - 1))
                self.assertEqual(h.banks.words[hi][word], payload(address) >> 256)
        self.assertEqual(h.ddr_addresses, addresses)
        self.assertEqual(h.write_lines, list(range(4096)))
        self.assertEqual(h.read_lines, list(range(4096)))
        self.assertEqual(s.valid, bytearray(b'\xff' * 512))
        for line, address in enumerate(addresses):
            self.assertEqual(h.read(address, (1 << 64) - 1 - line),
                             m.Reply((1 << 64) - 1 - line, payload(address)))
        self.assertEqual(h.ddr_addresses, addresses)
        self.assertEqual(h.write_lines, list(range(4096)))
        self.assertEqual(h.read_lines, list(range(4096)) * 2)
        self.assertEqual(s.counts['fills'], 4096)
        self.assertEqual(s.counts['hits'], 4096)
        self.assertEqual(s.counts['core_responses'], 8192)
        self.assertTrue(all(word == 0 for bank in h.banks.words for word in bank[512:]))
        self.assertTrue(h.finish()['released'])
        self.assertFalse(any(s.valid))
        self.assertIsNone(s.parent.raw.owner)
        self.assertFalse(s.reset_required)

    def test_m1_m2_original_source_kv_trace_uses_cache_without_arithmetic(self):
        from candidates.qwen2_resident_matrix.raw_kv_attention import source_contract
        for tokens, request_count, unique_count in ((1, 192, 32), (2, 576, 64)):
            with self.subTest(tokens=tokens):
                h = Harness(tokens)
                b = h.supply.binding
                trace = list(source_contract.kv_reads(tokens, b.k_base, b.v_base))
                self.assertEqual(len(trace), request_count)
                self.assertEqual(Counter(kind for kind, _ in trace),
                                 {'k': request_count // 2, 'v': request_count // 2})
                self.assertEqual(trace[:16],
                                 [('k', b.k_base + 64 * i) for i in range(8)] +
                                 [('v', b.v_base + 64 * i) for i in range(8)])
                self.assertEqual(trace[96:112],
                                 [('k', b.k_base + 512 + 64 * i) for i in range(8)] +
                                 [('v', b.v_base + 512 + 64 * i) for i in range(8)])
                if tokens == 2:
                    # K depth walks each token, whereas V token walks each col.
                    self.assertEqual(trace[192:208],
                                     [('k', b.k_base + token * 1024 + col * 64)
                                      for token in range(2) for col in range(8)])
                    self.assertEqual(trace[208:224],
                                     [('v', b.v_base + token * 1024 + col * 64)
                                      for col in range(8) for token in range(2)])
                addresses = [address for _, address in trace]
                unique = list(dict.fromkeys(addresses))
                self.assertEqual(len(unique), unique_count)
                for tag, address in enumerate(addresses):
                    self.assertEqual(h.read(address, tag), m.Reply(tag, payload(address)))
                self.assertEqual(h.ddr_addresses, unique)
                self.assertEqual(h.read_lines, [h.supply.line(a) for a in addresses])
                self.assertEqual(h.supply.counts['fills'], unique_count)
                self.assertEqual(h.supply.counts['hits'], request_count - unique_count)
                self.assertEqual(h.supply.counts['core_responses'], request_count)
                self.assertTrue(h.finish()['released'])

    def test_source_contract_pins_original_method_and_chisel_consumer(self):
        from candidates.qwen2_resident_matrix.raw_kv_attention import source_contract
        contract = source_contract.check()
        self.assertEqual(set(contract),
                         {'pv16_method_ast_sha256', 'attention_region_sha256'})
        self.assertTrue(all(len(value) == 64 for value in contract.values()))

    def test_binding_fields_are_strict_and_spans_do_not_alias_or_overflow(self):
        b = binding(1)
        cases = []
        for field in ('owner', 'tag'):
            for value in (0, -1, True, 1.0, 1 << 32, None):
                cases.append((field, value))
        for value in (0, 129, -1, True, 1.0, None):
            cases.append(('tokens', value))
        for field in ('k_base', 'v_base', 'output_base'):
            for value in (-64, 1, True, 1.0, 1 << 64, (1 << 64) - 64, None):
                cases.append((field, value))
        for value in (0, 1, True, 6144.0, 6143, 6145, None):
            cases.append(('output_bytes', value))
        cases += [('v_base', b.k_base), ('v_base', b.k_base + 64),
                  ('k_base', b.v_base + 64), ('output_base', b.k_base),
                  ('output_base', b.v_base), ('output_base', b.k_base - 64)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                s = m.KvSupply(enabled=True)
                with self.assertRaises(ValueError):
                    s.bind(replace(b, **{field: value}))
                self.assertIsNone(s.binding)
                self.assertIsNone(s.parent.raw.owner)
                self.assertFalse(s.parent.owner.a_banks.reads or s.parent.owner.a_banks.writes)
        s = m.KvSupply(enabled=True)
        with self.assertRaises(ValueError):
            s.bind(vars(b))
        # Half-open adjacency and the exact end of the address space are legal.
        s.bind(replace(b, k_base=0, v_base=1024, output_base=(1 << 64) - 6144))

    def test_default_off_and_disabled_parent_preserve_original_route(self):
        for s in (m.KvSupply(), m.KvSupply(parent.ParentLoan(), enabled=True)):
            with self.assertRaises(ValueError):
                s.bind(binding(1))
            e = s.tick(request=m.Read(0, binding(1).k_base))
            self.assertFalse(e['request_fire'] or e['parent']['raw']['acquired'])
            self.assertIsNone(e['ddr_request'])
            self.assertIsNone(e['response'])
        with self.assertRaises(ValueError):
            m.KvSupply(enabled=1)

    def test_read_address_mapping_boundaries_and_invalid_requests(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        self.assertEqual(s.line(b.k_base), 0)
        self.assertEqual(s.line(b.k_base + 15 * 64), 15)
        self.assertEqual(s.line(b.v_base), 2048)
        self.assertEqual(s.line(b.v_base + 15 * 64), 2063)
        for address in (b.k_base - 64, b.k_base + 1024, b.v_base + 1024,
                        b.output_base, b.k_base + 1, -1, True, 1.0, 1 << 64, None):
            with self.subTest(address=address):
                self.assertIsNone(s.line(address))
                with self.assertRaises(ValueError):
                    h.tick(request=m.Read(0, address))
                self.assertFalse(h.banks.reads or h.banks.writes)
        for tag in (-1, True, 0.0, 1 << 64, None):
            with self.assertRaises(ValueError):
                h.tick(request=m.Read(tag, b.k_base))
        for bad in (-1, True, 1.0, 4096, None):
            with self.assertRaises(ValueError):
                s.present(bad)
        self.assertFalse(s.core_pending)
        self.assertEqual(h.read(b.k_base, 0), m.Reply(0, payload(b.k_base)))

    def test_handshake_flags_and_external_raw_controls_are_rejected(self):
        for flag in ('ddr_ready', 'response_ready', 'terminal', 'abort', 'raw_ack_ready'):
            s = Harness(1).supply
            with self.assertRaises(ValueError):
                s.tick(**{flag: 1})
        for control in ('acquire', 'release', 'ack', 'soft_reset'):
            s = Harness(1).supply
            with self.assertRaises(ValueError):
                s.tick(**{control: 7})

    def test_validity_commits_only_on_matching_fill_ack_then_raw_reread(self):
        h = Harness(1)
        s = h.supply
        request = h.issue_miss()
        for _ in range(3):
            e = h.tick()
            self.assertFalse(s.present(0))
            self.assertFalse(h.banks.reads or h.banks.writes)
            self.assertIsNone(e['response'])
        e = h.tick(ddr_response=m.Reply(request.tag, payload(request.address)))
        self.assertTrue(e['ddr_response_fire'])
        self.assertTrue(e['parent']['raw']['accepted'])
        self.assertEqual(h.banks.writes, {0: 0, 1: 0})
        self.assertFalse(s.present(0))
        self.assertIsNone(s.parent.raw.response)
        e = h.tick(raw_ack_ready=False)
        self.assertFalse(e['parent']['raw']['acked'])
        held = s.parent.raw.response
        self.assertTrue(held.key.write)
        for _ in range(4):
            e = h.tick(raw_ack_ready=False, response_ready=True)
            self.assertEqual(s.parent.raw.response, held)
            self.assertFalse(e['parent']['raw']['acked'] or e['response_fire'])
            self.assertFalse(s.present(0))
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick()
        self.assertTrue(e['parent']['raw']['acked'])
        self.assertTrue(s.present(0))
        self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick()
        self.assertTrue(e['parent']['raw']['accepted'])
        self.assertEqual(h.banks.reads, {0: 0, 1: 0})
        self.assertFalse(s.raw_key.write)
        self.assertIsNone(e['response'])
        e = h.until(lambda edge: edge['response'] is not None)
        self.assertEqual(e['response'], m.Reply(request.tag, payload(request.address)))
        self.assertIs(e['response'].data, s.parent.raw.response.data)

    def test_held_response_and_raw_ack_stall_single_outstanding_request(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        reply = h.hold_reply(b.k_base, 44)
        held = s.parent.raw.response
        other = m.Read(45, b.v_base)
        for _ in range(4):
            e = h.tick(request=other, raw_ack_ready=False)
            self.assertFalse(e['request_fire'] or e['response_fire'])
            self.assertEqual(e['response'], reply)
            self.assertIs(s.parent.raw.response, held)
            self.assertFalse(h.banks.reads or h.banks.writes)
        # Core consumption cannot be conditional on an independent raw ACK.
        e = h.tick(request=other, response_ready=True, raw_ack_ready=False)
        self.assertEqual(e['response'], reply)
        self.assertTrue(e['response_fire'])
        self.assertFalse(e['parent']['raw']['acked'])
        self.assertFalse(e['request_fire'])
        self.assertFalse(s.core_pending)
        self.assertIs(s.parent.raw.response, held)
        for _ in range(4):
            e = h.tick(request=other, response_ready=True, raw_ack_ready=False)
            self.assertIsNone(e['response'])
            self.assertFalse(e['request_fire'] or e['response_fire'])
            self.assertIs(s.parent.raw.response, held)
            self.assertFalse(s.parent.raw.drained)
            self.assertEqual(s.counts['core_responses'], 1)
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(request=other, response_ready=True)
        self.assertIsNone(e['response'])
        self.assertFalse(e['response_fire'])
        self.assertTrue(e['parent']['raw']['acked'])
        self.assertFalse(e['request_fire'])
        self.assertIsNone(s.parent.raw.response)
        self.assertEqual(h.read(b.v_base, 45), m.Reply(45, payload(b.v_base)))
        self.assertEqual(s.counts['core_responses'], 2)

    def test_consumed_core_reply_keeps_raw_debt_through_terminal_abort_until_ack(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        reply = h.hold_reply(b.k_base, 46)
        held = s.parent.raw.response
        e = h.tick(response_ready=True, raw_ack_ready=False)
        self.assertEqual(e['response'], reply)
        self.assertTrue(e['response_fire'])
        self.assertFalse(e['parent']['raw']['acked'])
        self.assertFalse(s.core_pending)
        self.assertEqual(s.counts['core_responses'], 1)
        for _ in range(4):
            e = h.tick(terminal=True, abort=True, response_ready=True,
                       raw_ack_ready=False, request=m.Read(47, b.v_base))
            self.assertIsNone(e['response'])
            self.assertFalse(e['response_fire'] or e['request_fire'])
            self.assertFalse(e['released'] or e['done_ready'])
            self.assertFalse(e['parent']['raw']['acked'])
            self.assertIs(s.parent.raw.response, held)
            self.assertFalse(s.parent.raw.drained)
            self.assertEqual(s.parent.raw.owner, b.owner)
            self.assertFalse(any(s.valid))
            self.assertTrue(e['reset_required'])
            self.assertEqual(s.counts['core_responses'], 1)
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(terminal=True, response_ready=True)
        self.assertIsNone(e['response'])
        self.assertFalse(e['response_fire'])
        self.assertTrue(e['parent']['raw']['acked'])
        self.assertTrue(s.parent.raw.drained)
        self.assertFalse(e['released'] or e['done_ready'])
        e = h.finish()
        self.assertTrue(e['released'])
        self.assertTrue(e['done_ready'])
        self.assertEqual(s.counts['core_responses'], 1)
        self.assertEqual(h.counts['response_fire'], 1)
        self.assertTrue(s.reset_required)

    def test_ddr_command_stalls_stably_and_acceptance_cannot_take_new_core_read(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        request = m.Read((1 << 64) - 1, b.k_base)
        h.accept(request)
        h.until(lambda e: e['ddr_request'] is not None)
        for _ in range(4):
            e = h.tick(request=m.Read(2, b.v_base))
            self.assertEqual(e['ddr_request'], request)
            self.assertFalse(e['ddr_fire'] or e['request_fire'])
            self.assertFalse(s.ddr_pending)
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(ddr_ready=True, request=m.Read(2, b.v_base))
        self.assertTrue(e['ddr_fire'])
        self.assertFalse(e['request_fire'])
        self.assertTrue(s.ddr_pending)

    def test_offered_ddr_request_stays_valid_through_abort_until_accepted_and_drained(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        request = m.Read(55, b.k_base)
        h.accept(request)
        e = h.until(lambda edge: edge['ddr_request'] is not None)
        self.assertEqual(e['ddr_request'], request)
        for _ in range(4):
            e = h.tick(abort=True, terminal=True, request=m.Read(56, b.v_base))
            self.assertEqual(e['ddr_request'], request)
            self.assertFalse(e['ddr_fire'] or e['request_fire'])
            self.assertFalse(e['released'] or e['done_ready'])
            self.assertTrue(e['reset_required'])
            self.assertTrue(s.core_pending)
            self.assertFalse(s.ddr_pending)
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(ddr_ready=True, terminal=True)
        self.assertEqual(e['ddr_request'], request)
        self.assertTrue(e['ddr_fire'])
        self.assertTrue(s.ddr_pending)
        self.assertIsNone(e['response'])
        for _ in range(3):
            e = h.tick(response_ready=True, terminal=True)
            self.assertIsNone(e['ddr_request'])
            self.assertFalse(e['ddr_fire'] or e['response_fire'] or e['done_ready'])
            self.assertTrue(s.ddr_pending)
        e = h.tick(ddr_response=m.Reply(request.tag, BITS))
        self.assertTrue(e['ddr_response_fire'])
        self.assertFalse(s.ddr_pending)
        self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(response_ready=True)
        self.assertEqual(e['response'], m.Reply(55, 0, True))
        self.assertTrue(e['response_fire'])
        self.assertFalse(e['released'])
        self.assertTrue(h.finish()['released'])
        self.assertEqual(s.counts['ddr_requests'], 1)
        self.assertEqual(s.counts['ddr_responses'], 1)
        self.assertEqual(s.counts['core_responses'], 1)
        self.assertEqual(h.write_lines, [])

    def test_unsolicited_ddr_reply_poison_preserves_core_and_raw_debts(self):
        for phase in ('idle', 'acquire', 'lookup', 'read_wait', 'ack_wait'):
            with self.subTest(phase=phase):
                h = Harness(1)
                s, b = h.supply, h.supply.binding
                held = reply = None
                if phase in ('acquire', 'lookup'):
                    h.accept(m.Read(57, b.k_base))
                    if phase == 'lookup':
                        self.assertTrue(h.tick()['parent']['raw']['acquired'])
                elif phase in ('read_wait', 'ack_wait'):
                    reply = h.hold_reply(b.k_base, 57)
                    held = s.parent.raw.response
                    if phase == 'ack_wait':
                        self.assertTrue(h.tick(response_ready=True, raw_ack_ready=False)['response_fire'])
                self.assertEqual(s.state, phase)
                self.assertFalse(s.ddr_pending)
                core_pending = s.core_pending
                e = h.tick(ddr_response=m.Reply(999, BITS), raw_ack_ready=False)
                self.assertTrue(e['ddr_response_fire'])
                self.assertTrue(e['reset_required'])
                self.assertFalse(s.ddr_pending)
                self.assertEqual(s.core_pending, core_pending)
                self.assertFalse(e['response_fire'] or e['released'])
                self.assertFalse(any(s.valid))
                self.assertFalse(h.banks.reads or h.banks.writes)
                self.assertEqual(s.counts['foreign_responses'], 1)
                if held is not None:
                    self.assertIs(s.parent.raw.response, held)
                    self.assertFalse(s.parent.raw.drained)
                    if phase == 'read_wait':
                        self.assertEqual(e['response'], reply)
                        e = h.tick(response_ready=True, raw_ack_ready=False)
                        self.assertEqual(e['response'], reply)
                        self.assertTrue(e['response_fire'])
                    else:
                        self.assertIsNone(e['response'])
                    e = h.tick(terminal=True, raw_ack_ready=False, response_ready=True)
                    self.assertIsNone(e['response'])
                    self.assertFalse(e['response_fire'] or e['done_ready'])
                    self.assertIs(s.parent.raw.response, held)
                    e = h.tick()
                    self.assertTrue(e['parent']['raw']['acked'])
                    self.assertFalse(e['response_fire'] or e['released'])
                    self.assertEqual(s.counts['core_responses'], 1)
                elif phase != 'idle':
                    e = h.tick(response_ready=True)
                    self.assertEqual(e['response'], m.Reply(57, 0, True))
                    self.assertTrue(e['response_fire'])
                self.assertTrue(h.finish()['done_ready'])
                self.assertTrue(s.reset_required)
        disabled = m.KvSupply()
        e = disabled.tick(ddr_response=m.Reply(999, BITS))
        self.assertFalse(e['ddr_response_fire'] or e['reset_required'])
        self.assertEqual(disabled.counts['foreign_responses'], 0)

    def test_abort_during_ddr_debt_waits_for_real_reply_without_fill(self):
        h = Harness(1)
        s = h.supply
        request = h.issue_miss()
        for _ in range(4):
            e = h.tick(abort=True, terminal=True, response_ready=True)
            self.assertTrue(s.ddr_pending)
            self.assertFalse(e['released'] or e['done_ready'])
            self.assertFalse(h.banks.reads or h.banks.writes)
        e = h.tick(ddr_response=m.Reply(request.tag, payload(request.address)), terminal=True)
        self.assertTrue(e['ddr_response_fire'])
        self.assertFalse(s.ddr_pending)
        self.assertFalse(h.banks.reads or h.banks.writes)
        self.assertFalse(any(s.valid))
        e = h.tick(terminal=True)
        self.assertEqual(e['response'], m.Reply(request.tag, 0, True))
        self.assertFalse(e['released'])
        e = h.tick(terminal=True, response_ready=True)
        self.assertTrue(e['response_fire'])
        self.assertFalse(e['released'])
        self.assertTrue(h.finish()['released'])
        self.assertTrue(s.reset_required)

    def test_foreign_and_malformed_ddr_replies_poison_without_erasing_debt(self):
        bad_replies = (m.Reply(5, BITS), m.Reply(True, BITS),
                       m.Reply(4, -1), m.Reply(4, 1 << 512),
                       m.Reply(4, BITS, 1), object())
        for bad in bad_replies:
            with self.subTest(reply=bad):
                h = Harness(1)
                s = h.supply
                request = h.issue_miss(tag=4)
                e = h.tick(ddr_response=bad, terminal=True)
                self.assertTrue(e['ddr_response_fire'])
                self.assertTrue(s.reset_required)
                self.assertTrue(s.ddr_pending)
                self.assertFalse(e['released'])
                self.assertFalse(any(s.valid))
                self.assertFalse(h.banks.reads or h.banks.writes)
                for _ in range(3):
                    self.assertFalse(h.tick(terminal=True)['done_ready'])
                    self.assertTrue(s.ddr_pending)
                e = h.tick(ddr_response=m.Reply(request.tag, BITS))
                self.assertTrue(e['ddr_response_fire'])
                self.assertFalse(s.ddr_pending)
                self.assertFalse(h.banks.reads or h.banks.writes)
                e = h.tick(response_ready=True)
                self.assertEqual(e['response'], m.Reply(request.tag, 0, True))
                self.assertTrue(e['response_fire'])
                self.assertTrue(h.finish()['released'])

    def test_raw_sequence_exhaustion_drains_matching_ddr_debt_without_reuse(self):
        for serial, writes in (((1 << 32) - 1, 0), ((1 << 32) - 2, 1)):
            with self.subTest(serial=serial):
                h = Harness(1)
                s = h.supply
                s.serial = serial
                request = h.issue_miss(tag=82)
                e = h.tick(ddr_response=m.Reply(request.tag, BITS))
                self.assertTrue(e['ddr_response_fire'])
                self.assertFalse(s.ddr_pending)
                e = h.until(lambda edge: edge['response'] is not None)
                self.assertEqual(e['response'], m.Reply(82, 0, True))
                self.assertTrue(s.reset_required)
                self.assertFalse(any(s.valid))
                self.assertEqual(len(h.write_lines), writes)
                self.assertEqual(h.read_lines, [])
                self.assertEqual(s.counts['ddr_responses'], 1)
                self.assertTrue(h.tick(response_ready=True)['response_fire'])
                self.assertTrue(h.finish()['released'])

    def test_matching_ddr_error_produces_no_raw_write(self):
        h = Harness(1)
        s = h.supply
        request = h.issue_miss(tag=18)
        e = h.tick(ddr_response=m.Reply(request.tag, BITS, True))
        self.assertTrue(e['ddr_response_fire'])
        self.assertFalse(s.ddr_pending)
        self.assertTrue(s.reset_required)
        self.assertFalse(h.banks.reads or h.banks.writes)
        self.assertFalse(any(s.valid))
        e = h.tick(response_ready=True)
        self.assertEqual(e['response'], m.Reply(18, 0, True))
        self.assertTrue(e['response_fire'])
        self.assertTrue(h.finish()['released'])

    def test_abort_with_matching_fill_ack_drains_without_publication(self):
        for signal in ('abort', 'backend_abort'):
            with self.subTest(signal=signal):
                h = Harness(1)
                s = h.supply
                request = h.issue_miss()
                h.tick(ddr_response=m.Reply(request.tag, BITS))
                h.tick(raw_ack_ready=False)
                self.assertIsNotNone(s.parent.raw.response)
                self.assertFalse(any(s.valid))
                e = h.tick(terminal=True, **{signal: True})
                self.assertTrue(e['parent']['raw']['acked'])
                self.assertFalse(e['released'])
                self.assertFalse(any(s.valid))
                self.assertTrue(s.reset_required)
                self.assertFalse(h.banks.reads or h.banks.writes)
                e = h.tick(response_ready=True)
                self.assertEqual(e['response'], m.Reply(request.tag, 0, True))
                self.assertTrue(e['response_fire'])
                self.assertTrue(h.finish()['released'])
                self.assertEqual(h.read_lines, [])

    def test_abort_preserves_pending_synchronous_raw_fill_and_read(self):
        for phase in ('fill', 'read'):
            with self.subTest(phase=phase):
                h = Harness(1)
                s = h.supply
                request = h.issue_miss(tag=91)
                h.tick(ddr_response=m.Reply(request.tag, BITS))
                if phase == 'read':
                    h.until(lambda e: e['parent']['raw']['accepted'])
                pending = s.parent.raw.pending
                self.assertIsNotNone(pending)
                self.assertEqual(pending.key.write, phase == 'fill')
                self.assertIsNone(s.parent.raw.response)
                e = h.tick(abort=True, terminal=True, raw_ack_ready=False)
                self.assertFalse(e['parent']['raw']['acked'])
                self.assertFalse(e['done_ready'])
                self.assertIs(s.parent.raw.response, pending)
                self.assertIsNone(s.parent.raw.pending)
                self.assertFalse(any(s.valid))
                self.assertFalse(h.banks.reads or h.banks.writes)
                if phase == 'fill':
                    e = h.tick()
                    self.assertTrue(e['parent']['raw']['acked'])
                    e = h.tick(response_ready=True)
                    self.assertEqual(e['response'], m.Reply(91, 0, True))
                else:
                    e = h.tick(response_ready=True)
                    self.assertEqual(e['response'], m.Reply(91, BITS))
                    self.assertTrue(e['parent']['raw']['acked'])
                self.assertTrue(e['response_fire'])
                self.assertFalse(e['released'])
                self.assertTrue(h.finish()['released'])

    def test_abort_holds_accepted_raw_read_and_reply_unchanged_until_consumed(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        reply = h.hold_reply(b.k_base, 90)
        held = s.parent.raw.response
        self.assertTrue(s.present(0))
        for _ in range(4):
            e = h.tick(abort=True, terminal=True)
            self.assertEqual(e['response'], reply)
            self.assertIs(s.parent.raw.response, held)
            self.assertFalse(any(s.valid))
            self.assertTrue(e['reset_required'])
            self.assertFalse(e['response_fire'] or e['released'])
        e = h.tick(response_ready=True)
        self.assertEqual(e['response'], reply)
        self.assertTrue(e['response_fire'])
        self.assertTrue(e['parent']['raw']['acked'])
        self.assertFalse(e['released'])
        self.assertTrue(h.finish()['released'])

    def test_terminal_does_not_discard_accepted_work_or_admit_new_work(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        request = h.issue_miss(tag=8)
        e = h.tick(terminal=True, request=m.Read(9, b.v_base))
        self.assertFalse(e['request_fire'] or e['done_ready'])
        self.assertTrue(s.ddr_pending)
        h.tick(ddr_response=m.Reply(request.tag, payload(request.address)))
        e = h.until(lambda edge: edge['response'] is not None)
        self.assertEqual(e['response'], m.Reply(8, payload(request.address)))
        for _ in range(3):
            self.assertFalse(h.tick()['done_ready'])
        e = h.tick(response_ready=True)
        self.assertTrue(e['response_fire'])
        self.assertFalse(e['released'])
        self.assertTrue(h.finish()['released'])
        h = Harness(1)
        e = h.tick(terminal=True, request=m.Read(0, h.supply.binding.k_base))
        self.assertFalse(e['request_fire'])
        self.assertTrue(e['done_ready'])
        self.assertIsNone(h.supply.parent.raw.owner)

    def test_prior_edge_invalidation_is_required_for_retained_a_lease(self):
        h = Harness(1)
        s, p = h.supply, h.supply.parent
        p.owner.lease = parent.drain.ALease(0x100000, True, 16, 32, 64, 9)
        h.accept(m.Read(0, s.binding.k_base))
        e = h.tick()
        self.assertFalse(e['parent']['drained'])
        self.assertFalse(e['parent']['raw']['acquired'])
        self.assertIsNone(p.owner.lease)
        self.assertIsNone(p.raw.owner)
        e = h.tick()
        self.assertTrue(e['parent']['raw']['acquired'])
        self.assertEqual(p.raw.owner, s.binding.owner)
        self.assertFalse(h.banks.reads or h.banks.writes)

    def test_actual_dense_job_and_actual_tile_lease_exclude_the_raw_loan(self):
        for kind in ('dense', 'tile'):
            with self.subTest(kind=kind):
                p = parent.ParentLoan(enabled=True)
                if kind == 'dense':
                    job = parent.Job(m=16, k=32, n=32, write_bytes=2048)
                    p.tick(job=job)
                    self.assertEqual(p.owner.state, 'clear')
                else:
                    e = p.tick(tile_control=parent.drain.Control(0, 0, 9, 0, 16, 32))
                    self.assertTrue(e['owner']['tile']['ctl_fire'])
                    self.assertTrue(p.owner.tiles.leased)
                s = m.KvSupply(p, enabled=True)
                s.bind(binding(1))
                self.assertTrue(s.tick(request=m.Read(0, s.binding.k_base))['request_fire'])
                for _ in range(20):
                    e = s.tick()
                    self.assertFalse(e['parent']['raw']['acquired'])
                    self.assertFalse(e['parent']['raw']['accepted'])
                    self.assertIsNone(e['ddr_request'])
                    self.assertIsNone(p.raw.owner)
                self.assertTrue(any(p.debts().values()))

    def test_acquisition_and_release_edges_reserve_dense_and_tile_ports(self):
        h = Harness(1)
        s, p = h.supply, h.supply.parent
        job = parent.Job(m=16, k=32, n=32, write_bytes=2048)
        control = parent.drain.Control(0, 0, 9, 0, 16, 32)
        h.accept(m.Read(0, s.binding.k_base))
        e = h.tick(job=job, tile_control=control)
        self.assertTrue(e['parent']['raw']['acquired'])
        self.assertFalse(e['parent']['owner']['job_ready'])
        self.assertFalse(e['parent']['owner']['tile']['ctl_fire'])
        self.assertIsNone(p.owner.job)
        h.until(lambda edge: edge['ddr_fire'], ddr_ready=True)
        h.tick(ddr_response=m.Reply(0, BITS))
        h.until(lambda edge: edge['response'] is not None)
        h.tick(response_ready=True, terminal=True)
        e = h.tick(job=job, tile_control=control)
        self.assertTrue(e['released'])
        self.assertFalse(e['parent']['owner']['job_ready'])
        self.assertFalse(e['parent']['owner']['tile']['ctl_fire'])
        self.assertIsNone(p.owner.job)
        e = h.tick(job=job)
        self.assertTrue(e['parent']['owner']['job_ready'])
        self.assertIs(p.owner.job, job)

    def test_no_payload_shadow_and_fresh_binding_invalidates_old_lines(self):
        h = Harness(1)
        s, b = h.supply, h.supply.binding
        held = h.hold_reply(b.k_base, 0)
        self.assertEqual(held.data, payload(b.k_base))
        # Inspect while a payload is live, not after a shadow could be cleared.
        # Only the existing raw port may own a payload or response register.
        for name, value in vars(s).items():
            if name == 'parent':
                continue
            self.assertNotIsInstance(value, (m.Reply, raw.Request, raw.Response), name)
            self.assertNotIsInstance(value, (list, tuple), name)
            if type(value) is dict:
                self.assertTrue(all(type(v) is int and 0 <= v < (1 << 64)
                                    for v in value.values()), name)
            if type(value) is int:
                self.assertLess(value, 1 << 64, name)
        self.assertEqual(len(s.valid), 512)
        with self.assertRaises(ValueError):
            s.bind(replace(b, tag=12))
        self.assertTrue(h.tick(response_ready=True)['response_fire'])
        h.finish()
        s.bind(replace(b, tag=12))
        self.assertFalse(any(s.valid))
        self.assertIsNone(s.parent.raw.owner)
        self.assertEqual(h.read(b.k_base, 0), m.Reply(0, payload(b.k_base)))
        self.assertEqual(h.ddr_addresses, [b.k_base, b.k_base])

    def test_parent_poison_after_bind_returns_first_tagged_error_without_sram(self):
        h = Harness(1)
        s = h.supply
        h.tick(read_beat=parent.down.ReadBeat(1, (0,) * 32, True))
        self.assertTrue(s.reset_required)
        e = h.tick(request=m.Read(123, s.binding.k_base))
        self.assertTrue(e['request_fire'])
        e = h.tick(response_ready=True)
        self.assertEqual(e['response'], m.Reply(123, 0, True))
        self.assertTrue(e['response_fire'])
        self.assertFalse(h.banks.reads or h.banks.writes)
        self.assertFalse(h.tick(request=m.Read(124, s.binding.v_base))['request_fire'])
        self.assertTrue(h.finish()['done_ready'])
        with self.assertRaises(ValueError):
            s.bind(binding(1))


if __name__ == '__main__':
    unittest.main()
