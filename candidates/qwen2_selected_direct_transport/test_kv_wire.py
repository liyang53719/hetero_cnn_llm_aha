#!/usr/bin/env python3
"""Source-bound, bounded raw-KV wire and bank-port tests; stdlib only.

Run from any cwd, including with Python -I -B or -I -B -O:
  python -I -B test_kv_wire.py --source-root /path/to/pinned/source

This executes unchanged extracted definitions and the exact public-delivery
response_fire body, not a replacement decoder or cache. All input pins are
checked before any source AST is parsed. Original assertions are preserved by
explicit optimize=0 compilation, even under an optimized test launcher.

Scope: bit patterns, byte addresses, bank mapping, and raw-port debt. The
512-bit integer is a wire container, never an FP32/BF16 numerical value. Raw
cache fill/read/ACK/release lifecycle is NOT architecture-equivalent to a new
direct memory route. There is no arithmetic, native, RTL, full-block, or M128
prefill result here. Testing all 4096 raw lines proves address coverage only.
"""
import argparse
import ast
import copy
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import struct
import sys
import types
import unittest


BASE = 'candidates/qwen2_resident_matrix/'
RAW = BASE + 'raw_kv/model.py'
SUPPLY = BASE + 'raw_kv_attention/model.py'
BRIDGE = BASE + 'raw_kv_attention/numeric_bridge.py'
PUBLIC = BASE + 'raw_kv_public/model.py'
PREFIX = BASE + 'ffn_public/prefix_owners.py'
BANKS = BASE + 'transposed_down/model.py'
SOURCE_BYTES = {}
SOURCE_ROOT = None
EXTRACTIONS = {}
RAW_MODULE = SUPPLY_MODULE = BRIDGE_MODULE = PREFIX_MODULE = BANKS_MODULE = None
DELIVERY_NODES = None


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def bound_resources():
    """Fail closed rather than running a purportedly bounded unbounded test."""
    for kind, limit in ((resource.RLIMIT_CPU, 20),
                        (resource.RLIMIT_AS, 256 * 1024 * 1024)):
        soft, hard = resource.getrlimit(kind)
        cap = limit if hard == resource.RLIM_INFINITY else min(limit, hard)
        resource.setrlimit(kind, (cap, cap))
    if not hasattr(os, 'sched_getaffinity') or not hasattr(os, 'sched_setaffinity'):
        raise RuntimeError('one-CPU affinity enforcement is unavailable')
    available = os.sched_getaffinity(0)
    need(bool(available), 'no allowed CPU')
    os.sched_setaffinity(0, {min(available)})
    need(len(os.sched_getaffinity(0)) == 1, 'one-CPU bound not applied')


def validate_bytes(relative, payload, pin):
    need(type(pin.get('bytes')) is int and len(payload) == pin['bytes'],
         'source byte-count mismatch: ' + relative)
    need(hashlib.sha256(payload).hexdigest() == pin.get('sha256'),
         'source SHA256 mismatch: ' + relative)


def verify_sources(root, manifest):
    """Snapshot verified bytes; extraction cannot reopen a changed source."""
    need(manifest.get('schema') == 1, 'unsupported pin schema')
    pins = manifest['sources']
    need(all(path in pins for path in (RAW, SUPPLY, BRIDGE, PUBLIC, PREFIX, BANKS)),
         'required source pin missing (including original Banks)')
    verified = {}
    for relative, pin in pins.items():
        path = root / relative
        need(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
             'non-relative source pin')
        need(path.resolve(strict=True).is_relative_to(root), 'source escaped root')
        payload = path.read_bytes()
        validate_bytes(relative, payload, pin)
        verified[relative] = payload
    return verified


def source_tree(relative):
    need(relative in SOURCE_BYTES, 'AST extraction before source verification')
    return ast.parse(SOURCE_BYTES[relative], filename=str(SOURCE_ROOT / relative))


def definitions(relative, names, environment=None):
    tree = source_tree(relative)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    need(len(nodes) == len(names) and {node.name for node in nodes} == set(names),
         'missing or duplicate source definitions: ' + relative)
    name = '_kv_wire_' + relative.replace('/', '_').replace('.', '_')
    module = types.ModuleType(name)
    module.__file__ = str(SOURCE_ROOT / relative)
    module.__dict__.update(dataclass=dataclass, struct=struct)
    module.__dict__.update(environment or {})
    sys.modules[name] = module
    exec(compile(ast.Module(body=nodes, type_ignores=[]), module.__file__, 'exec',
                 dont_inherit=True, optimize=0), module.__dict__)
    EXTRACTIONS[relative] = dict(definitions=list(names),
        sha256=hashlib.sha256(SOURCE_BYTES[relative]).hexdigest(), unchanged_ast=True)
    return module


def delivery_nodes():
    """Extract the exact guarded body, with no copied implementation."""
    public = next(node for node in source_tree(PUBLIC).body
                  if isinstance(node, ast.ClassDef) and node.name == 'PublicKvTransport')
    tick = next(node for node in public.body
                if isinstance(node, ast.FunctionDef) and node.name == 'tick')
    matches = [node for node in tick.body if isinstance(node, ast.If)
               and ast.unparse(node.test) == "se['response_fire']"
               and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                       and child.func.attr == 'to_bytes' for child in ast.walk(node))]
    need(len(matches) == 1, 'unique actual PublicKvTransport delivery block required')
    nodes = matches[0].body
    need(any(isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == 'core_response'
        for target in node.targets) for node in nodes), 'public delivery assignment absent')
    EXTRACTIONS[PUBLIC] = dict(method='PublicKvTransport.tick',
        lines=[matches[0].lineno, matches[0].end_lineno],
        scope='unchanged guarded response_fire body only',
        sha256=hashlib.sha256(SOURCE_BYTES[PUBLIC]).hexdigest(), unchanged_ast=True)
    return nodes


def deliver(reply, accepted_tag=None, admitted=True, nodes=None):
    if accepted_tag is None:
        accepted_tag = reply.tag
    environment = dict(self=types.SimpleNamespace(kv_admitted=admitted),
        accepted=types.SimpleNamespace(tag=accepted_tag), se={'response': reply},
        require=BRIDGE_MODULE.require, MemoryResponse=PREFIX_MODULE.MemoryResponse)
    code = compile(ast.Module(body=DELIVERY_NODES if nodes is None else nodes,
                              type_ignores=[]), str(SOURCE_ROOT / PUBLIC), 'exec',
                   dont_inherit=True, optimize=0)
    exec(code, environment)
    return environment['core_response']


def load_sources(root, manifest):
    global SOURCE_ROOT, SOURCE_BYTES, RAW_MODULE, SUPPLY_MODULE
    global BRIDGE_MODULE, PREFIX_MODULE, BANKS_MODULE, DELIVERY_NODES
    SOURCE_ROOT = root
    SOURCE_BYTES = verify_sources(root, manifest)
    RAW_MODULE = definitions(RAW, ('uint', 'location', 'Key', 'Request', 'Response',
                                    'Obligations', 'valid_key', 'RawKvPort'))
    PREFIX_MODULE = definitions(PREFIX, ('MemoryResponse',), {'BEAT_BYTES': 64})
    SUPPLY_MODULE = definitions(SUPPLY, ('Binding', 'Read', 'Reply', 'KvSupply'),
        {'uint': RAW_MODULE.uint, 'Key': RAW_MODULE.Key, 'Request': RAW_MODULE.Request})
    BRIDGE_MODULE = definitions(BRIDGE, ('require', 'decode_ddr_response'),
        {'uint': RAW_MODULE.uint, 'Reply': SUPPLY_MODULE.Reply})
    BANKS_MODULE = definitions(BANKS, ('Banks',))
    DELIVERY_NODES = delivery_nodes()


def wire_patterns():
    yield 'zero', bytes(64)
    yield 'ones', bytes([255]) * 64
    for bit in range(512):
        yield 'walking_%03d' % bit, (1 << bit).to_bytes(64, 'little')
    # Encodings only: no floating-point unpack, arithmetic, or canonicalization.
    words = (0, 0x80000000, 0x7f800000, 0xff800000, 0x7fc00001, 0x7f800001,
             0xffc12345, 0xff800001, 1, 0x80000001, 0x007fffff, 0x807fffff,
             0x00800000, 0x80800000, 0x3f800000, 0xbf800000)
    yield 'special_encodings', struct.pack('<16I', *words)
    rng = random.Random(0x64_16_512)
    for index in range(128):
        yield 'random_%03d' % index, rng.getrandbits(512).to_bytes(64, 'little')
    for index in range(64):
        # Both quiet/signaling NaN payloads and both signs; never converted to float.
        words = tuple((rng.getrandbits(1) << 31) | 0x7f800000 |
                      rng.randrange(1, 1 << 23) for _ in range(16))
        yield 'nan_payloads_%02d' % index, struct.pack('<16I', *words)
        words = tuple((rng.getrandbits(1) << 31) | rng.randrange(1, 1 << 23)
                      for _ in range(16))
        yield 'subnormal_payloads_%02d' % index, struct.pack('<16I', *words)


class WireTests(unittest.TestCase):
    def setUp(self):
        self.decode = BRIDGE_MODULE.decode_ddr_response
        self.Response = PREFIX_MODULE.MemoryResponse
        self.Reply = SUPPLY_MODULE.Reply

    def test_actual_bytes_and_16u32_roundtrip_all_512_bits(self):
        count = 0
        for label, raw in wire_patterns():
            with self.subTest(pattern=label):
                words = struct.unpack('<16I', raw)
                for representation in (raw, words):
                    decoded = self.decode(self.Response((1 << 64) - 1, representation),
                                          self.Response)
                    self.assertIs(type(decoded), self.Reply)
                    self.assertFalse(decoded.error)
                    self.assertEqual(decoded.tag, (1 << 64) - 1)
                    self.assertEqual(decoded.data, int.from_bytes(raw, 'little'))
                    result = deliver(decoded)
                    self.assertIs(type(result.data), bytes)
                    self.assertEqual(result.nbytes, 64)
                    self.assertEqual(result.data, raw)
                    self.assertEqual(struct.unpack('<16I', result.data), words)
                    self.assertFalse(result.error)
                count += 1
        self.assertEqual(count, 771)

    def test_malformed_matching_beats_are_errors_not_successful_fabricated_payloads(self):
        raw = bytes(range(64))
        good = self.Response(99, raw)
        bad = [replace(good, nbytes=n) for n in (0, 4, 16, 63, 65, 128, True, 64.0, '64', None)]
        bad += [replace(good, error=e) for e in (True, 0, 1, None, 'false')]
        bad += [replace(good, data=data) for data in
                (None, 0, raw[:-1], raw + b'\0', bytearray(raw), memoryview(raw),
                 list(range(16)), tuple(range(15)), tuple(range(17)), 'x' * 64)]
        class IntSubclass(int):
            pass
        class BytesSubclass(bytes):
            pass
        class TupleSubclass(tuple):
            pass
        bad += [replace(good, data=BytesSubclass(raw)),
                replace(good, data=TupleSubclass(range(16)))]
        for value in (-1, 1 << 32, True, 1.0, '1', None, IntSubclass(1)):
            for lane in (0, 7, 15):
                words = list(range(16)); words[lane] = value
                bad.append(replace(good, data=tuple(words)))
        for response in bad:
            with self.subTest(response=repr(response)):
                decoded = self.decode(response, self.Response)
                self.assertIs(type(decoded), self.Reply)
                self.assertEqual(decoded.tag, good.tag)
                self.assertIs(decoded.error, True)
                self.assertEqual(decoded.data, 0)  # Explicit error sentinel, not a fill.

    def test_noncanonical_identity_never_becomes_a_reply(self):
        class ResponseSubclass(self.Response):
            pass
        class IntSubclass(int):
            pass
        values = [self.Response(tag, bytes(64)) for tag in
                  (-1, 1 << 64, True, 1.0, '1', None, IntSubclass(1))]
        values += [None, object(), types.SimpleNamespace(tag=7, data=bytes(64)),
                   ResponseSubclass(7, bytes(64))]
        for response in values:
            with self.subTest(response=repr(response)):
                decoded = self.decode(response, self.Response)
                self.assertIsNot(type(decoded), self.Reply)
                self.assertFalse(hasattr(decoded, 'data'))
        # A canonical foreign tag is preserved, not silently rewritten to match.
        foreign = self.decode(self.Response(100, bytes(range(64))), self.Response)
        self.assertEqual(foreign.tag, 100)
        with self.assertRaisesRegex(ValueError, 'KV response identity'):
            deliver(foreign, accepted_tag=99)
        with self.assertRaisesRegex(ValueError, 'unowned KV reply'):
            deliver(foreign, admitted=False)

    def test_public_conversion_refuses_unrepresentable_512bit_payload(self):
        for value in (-1, 1 << 512):
            with self.assertRaises(OverflowError):
                deliver(self.Reply(9, value))
        for value in (1.0, bytes(64), None):
            with self.assertRaises(AttributeError):
                deliver(self.Reply(9, value))

    def test_endian_mutations_are_detected_by_exact_wire_oracle(self):
        raw = bytes(range(64))
        original = self.decode(self.Response(7, raw), self.Response)
        self.assertEqual(deliver(original).data, raw)
        mutated = copy.deepcopy(DELIVERY_NODES)
        changed = 0
        for node in ast.walk(ast.Module(body=mutated, type_ignores=[])):
            if isinstance(node, ast.Constant) and node.value == 'little':
                node.value = 'big'; changed += 1
        self.assertEqual(changed, 1)
        with self.assertRaises(AssertionError):
            self.assertEqual(deliver(original, nodes=mutated).data, raw)
        for old, new, representation in (
            ('little', 'big', raw), ('<16I', '>16I', struct.unpack('<16I', raw))):
            tree = source_tree(BRIDGE)
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'decode_ddr_response')
            changed = 0
            for node in ast.walk(fn):
                if isinstance(node, ast.Constant) and node.value == old:
                    node.value = new; changed += 1
            self.assertGreater(changed, 0)
            env = dict(uint=RAW_MODULE.uint, Reply=self.Reply, struct=struct)
            exec(compile(ast.Module(body=[fn], type_ignores=[]), '<negative-endian-mutant>',
                         'exec', dont_inherit=True, optimize=0), env)
            corrupted = env['decode_ddr_response'](self.Response(7, representation), self.Response)
            with self.assertRaises(AssertionError):
                self.assertEqual(deliver(corrupted).data, raw)

    def test_pin_mutations_fail_before_extraction(self):
        raw = SOURCE_BYTES[BRIDGE]
        pin = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        validate_bytes(BRIDGE, raw, pin)
        for changed in (raw + b'\n', bytes([raw[0] ^ 1]) + raw[1:]):
            with self.assertRaisesRegex(AssertionError, 'source (byte-count|SHA256) mismatch'):
                validate_bytes(BRIDGE, changed, pin)


class AddressTests(unittest.TestCase):
    def mapper(self):
        # Only actual byte-address decoding is called. No parent, cache, or data
        # is synthesized; __init__ is intentionally outside this narrow slice.
        supply = SUPPLY_MODULE.KvSupply.__new__(SUPPLY_MODULE.KvSupply)
        supply.binding = SUPPLY_MODULE.Binding(7, 11, 0x100000, 0x200000,
                                              128, 0x400000, 128 * 6144)
        return supply

    def test_all_4096_lines_use_64byte_not_word_addresses(self):
        supply = self.mapper()
        for base, start in ((supply.binding.k_base, 0), (supply.binding.v_base, 2048)):
            for offset in range(2048):
                self.assertEqual(supply.line(base + offset * 64), start + offset)
            for offset in (1, 4, 16, 32, 63):
                self.assertIsNone(supply.line(base + offset))
            for address in (base - 64, base + 128 * 1024, base // 4, base // 16):
                self.assertIsNone(supply.line(address))
        for address in (-1, 1 << 64, True, None, 1.0, '1048576'):
            self.assertIsNone(supply.line(address))
        supply.binding = None
        self.assertIsNone(supply.line(0x100000))

    def test_word_address_divisor_mutation_is_detected(self):
        tree = source_tree(SUPPLY)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'KvSupply')
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'line')
        changed = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.FloorDiv):
                if isinstance(node.right, ast.Constant) and node.right.value == 64:
                    node.right.value = 16; changed += 1
        self.assertEqual(changed, 1)
        env = {'uint': RAW_MODULE.uint}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<negative-address-unit-mutant>',
                     'exec', dont_inherit=True, optimize=0), env)
        supply = self.mapper()
        self.assertEqual(supply.line(supply.binding.k_base + 64), 1)
        with self.assertRaises(AssertionError):
            self.assertEqual(env['line'](supply, supply.binding.k_base + 64), 1)


class RawBankTests(unittest.TestCase):
    def setUp(self):
        self.banks = BANKS_MODULE.Banks(1376)
        self.port = RAW_MODULE.RawKvPort(self.banks, enabled=True)
        self.assertTrue(self.port.tick(acquire=7)['acquired'])
        self.words_identity = id(self.banks.words)
        self.rows_identity = tuple(map(id, self.banks.words))

    def key(self, line=0, write=False, tag=1):
        return RAW_MODULE.Key(7, tag, line, write)

    def issue(self, key, data=0):
        event = self.port.tick(request=RAW_MODULE.Request(key, data))
        self.assertTrue(event['accepted'])
        self.assertFalse(self.port.drained)
        self.assertIsNone(self.port.response)
        lo, hi, word = RAW_MODULE.location(key.line)
        self.assertEqual(self.banks.writes if key.write else self.banks.reads,
                         {lo: word, hi: word})
        self.assertEqual(self.banks.reads if key.write else self.banks.writes, {})

    def complete(self, key):
        self.port.tick()
        held = self.port.response
        self.assertEqual(held.key, key)
        event = self.port.tick(ack=key)
        self.assertTrue(event['acked'])
        self.assertTrue(self.port.drained)
        self.assertEqual(self.banks.reads, {})
        self.assertEqual(self.banks.writes, {})
        return held.data

    @staticmethod
    def pattern(line):
        words = tuple((0x7f800001 ^ ((line + 1) * (lane + 1) * 0x01010101)) & 0xffffffff
                      for lane in range(16))
        return int.from_bytes(struct.pack('<16I', *words), 'little')

    def test_actual_fixed_backing_and_all4096_two_bank_locations(self):
        self.assertIs(self.port.banks, self.banks)
        self.assertEqual(self.banks.depth, 1376)
        self.assertEqual([len(row) for row in self.banks.words], [1376] * 16)
        occupied = set()
        for line in range(4096):
            expected = (2 * (line % 8), 2 * (line % 8) + 1, line // 8)
            self.assertEqual(RAW_MODULE.location(line), expected)
            lo, hi, word = expected
            self.assertNotIn((lo, word), occupied)
            self.assertNotIn((hi, word), occupied)
            occupied.update(((lo, word), (hi, word)))
            value = self.pattern(line)
            key = self.key(line, True, line + 1)
            self.issue(key, value)
            self.assertEqual(self.banks.words[lo][word], value & ((1 << 256) - 1))
            self.assertEqual(self.banks.words[hi][word], value >> 256)
            self.assertEqual(self.complete(key), 0)
        self.assertEqual(len(occupied), 8192)
        for line in range(4096):
            key = self.key(line, False, line + 1)
            self.issue(key)
            self.assertEqual(self.complete(key), self.pattern(line))
        self.assertEqual(RAW_MODULE.location(4095), (14, 15, 511))
        self.assertEqual(id(self.banks.words), self.words_identity)
        self.assertEqual(tuple(map(id, self.banks.words)), self.rows_identity)
        self.assertTrue(all(value == 0 for row in self.banks.words for value in row[512:]))
        self.assertEqual(set(vars(self.port)),
                         {'banks', 'enabled', 'owner', 'pending', 'response', 'poison'})

    def test_all_wire_encodings_survive_actual_bank_write_and_read(self):
        for index, (label, raw) in enumerate(wire_patterns()):
            with self.subTest(pattern=label):
                line = index % 4096
                value = int.from_bytes(raw, 'little')
                write = self.key(line, True, 2 * index + 1)
                self.issue(write, value)
                self.complete(write)
                read = self.key(line, False, 2 * index + 2)
                self.issue(read)
                returned = self.complete(read)
                self.assertEqual(returned, value)
                self.assertEqual(deliver(SUPPLY_MODULE.Reply(55, returned)).data, raw)

    def test_exact_ack_and_release_are_separate_fences_for_read_and_write(self):
        for write in (True, False):
            with self.subTest(write=write):
                key = self.key(4095, write, 9)
                self.issue(key, 0x1122334455 if write else 0)
                # Early ACK cannot erase the synchronous pending response.
                early = self.port.tick(ack=key, release=7)
                self.assertFalse(early['acked'])
                self.assertFalse(early['released'])
                held = self.port.response
                for bad in (None, replace(key, owner=8), replace(key, tag=10),
                            replace(key, line=4094), replace(key, write=not write),
                            replace(key, owner=True), replace(key, tag=True),
                            replace(key, line=4095.0), replace(key, write=int(write))):
                    event = self.port.tick(ack=bad, release=7,
                        request=RAW_MODULE.Request(self.key(1, False, 10)),
                        dense=True, tile=True, clear=True)
                    self.assertFalse(event['acked'])
                    self.assertFalse(event['released'])
                    self.assertFalse(event['accepted'])
                    self.assertIs(self.port.response, held)
                    self.assertFalse(any(event[k] for k in
                                         ('dense_allowed', 'tile_allowed', 'clear_allowed')))
                    self.assertFalse(self.banks.reads or self.banks.writes)
                event = self.port.tick(ack=key, release=7,
                    request=RAW_MODULE.Request(self.key(1, False, 10)))
                self.assertTrue(event['acked'])
                self.assertFalse(event['released'])
                self.assertFalse(event['accepted'])
                self.assertTrue(self.port.drained)
                self.assertTrue(self.port.blocked)
                event = self.port.tick(release=7, dense=True, tile=True, clear=True)
                self.assertTrue(event['released'])
                self.assertFalse(any(event[k] for k in
                                     ('dense_allowed', 'tile_allowed', 'clear_allowed')))
                self.assertTrue(self.port.tick()['dense_allowed'])
                self.assertTrue(self.port.tick(acquire=7)['acquired'])

    def test_abort_and_soft_reset_preserve_debt_until_exact_ack(self):
        for write in (True, False):
            key = self.key(8, write, 77)
            self.issue(key, 0x87654321 if write else 0)
            event = self.port.tick(ack=key, release=7, abort=True, soft_reset=True)
            self.assertFalse(event['acked'])
            self.assertFalse(event['released'])
            self.assertTrue(self.port.poison)
            held = self.port.response
            for _ in range(3):
                event = self.port.tick(release=7, soft_reset=True)
                self.assertFalse(event['released'])
                self.assertIs(self.port.response, held)
            event = self.port.tick(ack=key, release=7, soft_reset=True)
            self.assertTrue(event['acked'])
            self.assertFalse(event['released'])
            self.assertTrue(self.port.tick(release=7)['released'])
            self.assertFalse(self.port.tick(acquire=8)['acquired'])
            self.assertFalse(self.port.tick()['dense_allowed'])
            self.port.tick(soft_reset=True)
            self.assertFalse(self.port.poison)
            self.assertTrue(self.port.tick(acquire=7)['acquired'])
        self.assertEqual(self.banks.words[0][1], 0x87654321)

    def test_bad_raw_keys_data_and_lines_never_touch_banks(self):
        good = self.key()
        keys = [replace(good, **{field: value}) for field, values in (
            ('owner', (None, 0, 8, True, 1 << 32)),
            ('tag', (0, -1, True, 1 << 32)),
            ('line', (-1, 4096, True, 1.0)), ('write', (0, 1, None)))
                for value in values]
        requests = [RAW_MODULE.Request(key) for key in keys]
        requests += [RAW_MODULE.Request(self.key(write=True), value) for value in
                     (-1, 1 << 512, True, 1.0, None, bytes(64))]
        requests += [object(), types.SimpleNamespace(key=good, data=0)]
        for request in requests:
            self.assertFalse(self.port.tick(request=request)['accepted'])
            self.assertTrue(self.port.drained)
            self.assertFalse(self.banks.reads or self.banks.writes)
        for line in (-1, 4096, True, 1.0, None, '0'):
            with self.assertRaises(ValueError):
                RAW_MODULE.location(line)
        self.assertTrue(all(value == 0 for row in self.banks.words for value in row))

    def test_acquisition_needs_every_obligation_and_canonical_owner(self):
        self.assertTrue(self.port.tick(release=7)['released'])
        for field in RAW_MODULE.Obligations.__dataclass_fields__:
            for value in (True, 0, None):
                event = self.port.tick(acquire=7,
                    obligations=RAW_MODULE.Obligations(**{field: value}))
                self.assertFalse(event['acquired'])
        for field in ('dense', 'tile', 'clear', 'abort', 'soft_reset'):
            self.assertFalse(self.port.tick(acquire=7, **{field: True})['acquired'])
        for owner in (0, False, -1, 1 << 32):
            self.assertFalse(self.port.tick(acquire=owner)['acquired'])
        self.assertTrue(self.port.tick(acquire=7)['acquired'])
        with self.assertRaisesRegex(ValueError, '16x1376x256'):
            RAW_MODULE.RawKvPort(BANKS_MODULE.Banks(1375), enabled=True)

    def test_default_disabled_raw_port_does_not_allocate_or_borrow(self):
        disabled = RAW_MODULE.RawKvPort(self.banks)
        self.assertIs(disabled.banks, self.banks)
        self.assertFalse(disabled.tick(acquire=7)['acquired'])
        event = disabled.tick(request=RAW_MODULE.Request(self.key(write=True), 123))
        self.assertFalse(event['accepted'])
        self.assertTrue(all(event[key] for key in
                            ('dense_allowed', 'tile_allowed', 'clear_allowed')))
        self.assertTrue(disabled.drained)
        self.assertFalse(disabled.blocked)
        self.assertFalse(self.banks.reads or self.banks.writes)
        self.assertEqual(id(self.banks.words), self.words_identity)

    def test_source_banks_port_and_word_guards_remain_live_under_optimized_launcher(self):
        # Guard tests are independent of RawKvPort, whose accepted accesses are legal.
        self.banks.begin_cycle()
        self.banks.read(0, 0)
        with self.assertRaisesRegex(AssertionError, 'second SRAM read port'):
            self.banks.read(0, 1)
        self.banks.begin_cycle()
        self.banks.write(1, 0, 1)
        with self.assertRaisesRegex(AssertionError, 'second SRAM write port'):
            self.banks.write(1, 1, 1)
        for value in (-1, 1 << 256):
            self.banks.begin_cycle()
            with self.assertRaises(AssertionError):
                self.banks.write(0, 0, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    bound_resources()
    manifest = json.loads((Path(__file__).resolve().parent / 'INPUT_PINS.json').read_text())
    load_sources(args.source_root.resolve(strict=True), manifest)
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (WireTests, AddressTests, RawBankTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(status='pass' if result.wasSuccessful() else 'fail',
        tests=result.testsRun, pinned_sources=len(SOURCE_BYTES), patterns=771,
        walking_bits=512, raw_lines=4096, backing='original Banks: 16 x 1376 x 256 bits',
        source_commit=manifest.get('source_commit'), extractions=EXTRACTIONS,
        launcher_optimized=bool(sys.flags.optimize), source_compile_optimize=0,
        limits=dict(cpu_seconds=20, address_space_mib=256, allowed_cpus=len(os.sched_getaffinity(0))),
        scope='wire / bank-port protocol only; not full PublicKvTransport execution',
        exclusions=['arithmetic', 'native', 'RTL', 'full block', 'M128 prefill',
                    'raw-cache/direct-route architecture equivalence'])
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
