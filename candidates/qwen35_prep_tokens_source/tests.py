#!/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python
"""Pinned source and synthetic contract checks. This does NOT execute Scala/RTL.

Run only after review, with the exact isolated CPython command in TEST_SCOPE.md.
Only this proposal's four text inputs are read. No payloads, models, active run,
network, subprocesses, threads, compilation, or external packages are used.
"""
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import argparse
import difflib
import json
import os
import resource
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
BASELINE = None
OVERLAY = None
BASELINE_SPEC = (13048, "86fa350cd87bc140b762db2deb5650c25e3b30bae4fb12cef7fe407e6b4faffe")
OVERLAY_SPEC = (15119, "863801ca0ea2d33ef767bc70061ffa62e9cc83dff2cc2d4f18ba2bb71398181d")
CONTRACT = HERE / "CONTRACT.md"
PATCH = HERE / "GdnInputPrepOwner.patch"
PINS = {
    CONTRACT: (5455, "e4ac02b4410d65d4bc3954787c4e15ae1fcb2e4fcbaf7ff88d98c0ac95f34db7"),
}
LIMIT = 1 << 56
U64 = 1 << 64
CONV_STRIDE = 12288
PREP_STRIDE = 25600
DEADLINE = None


def budget():
    if DEADLINE is not None and time.monotonic() >= DEADLINE:
        raise RuntimeError("The bounded source/synthetic check exceeded its 4.5-second wall budget")


# Reviewed literal edit recipe. Full-file equality against this recipe constrains
# every other byte, not merely a few searched snippets. A changed overlay must be
# reviewed and repinned here, not silently accepted by learning from the file.
REPLACEMENTS = [
    ("/** Internal M1 producer bridge, not a public Host descriptor. The three inputs",
     "/** Internal producer bridge, not a public Host descriptor. The three inputs"),
    ("  * M1 uses the chunk path. This owner does not implement an M128 prefill path.",
     "  * M1 uses the chunk scaling path. maxTokens defaults to 1: public instances\n"
     "  * remain M1. Explicit internal multi-token instances require 16 heads and\n"
     "  * packed Conv/core rows (12288/25600 bytes), AB rows of 64 bytes, and chunk\n"
     "  * scaling. This serial InputPrep loop is not a chunk64 or full prefill core."),
    ("class GdnInputPrepOwner(heads: Int = 16) extends Module {\n"
     "  require(heads > 0 && heads <= 16)",
     "class GdnInputPrepOwner(heads: Int = 16, maxTokens: Int = 1) extends Module {\n"
     "  require(heads > 0 && heads <= 16)\n"
     "  require(maxTokens > 0 && maxTokens <= 128)"),
    ("  val job = Reg(new GdnInputPrepJob)\n",
     "  val job = Reg(new GdnInputPrepJob)\n  val token = RegInit(0.U(16.W))\n"),
    ("  val paramBase = MuxLookup(param, job.ab)(Seq(1.U -> job.aLog, 2.U -> job.dtBias))",
     "  val inputTokenOffset = token.pad(64) * 12288.U\n"
     "  val outputTokenOffset = token.pad(64) * 25600.U\n"
     "  val paramBase = MuxLookup(param, job.ab + (token.pad(64) << 6))(Seq(1.U -> job.aLog, 2.U -> job.dtBias))"),
    ("  io.memory.bits.address := MuxLookup(state, inputBase + (head.pad(64) << 8) + (beat.pad(64) << 6))(Seq(\n"
     "    readParam -> paramBase,\n"
     "    writeVector -> (outputBase + (head.pad(64) << 9) + (beat.pad(64) << 6)),\n"
     "    writeGate -> (job.gates + (head.pad(64) << 6))))",
     "  io.memory.bits.address := MuxLookup(state, inputBase + inputTokenOffset + (head.pad(64) << 8) + (beat.pad(64) << 6))(Seq(\n"
     "    readParam -> paramBase,\n"
     "    writeVector -> (outputBase + outputTokenOffset + (head.pad(64) << 9) + (beat.pad(64) << 6)),\n"
     "    writeGate -> (job.gates + outputTokenOffset + (head.pad(64) << 6))))"),
    ("    job := io.job.bits; param := 0.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U",
     "    job := io.job.bits; token := 0.U; param := 0.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U"),
    ("    when(j.tokens =/= 1.U || j.heads =/= heads.U || badAddress || badOverlap) { fail(Status.Bounds.U) }",
     "    // Multiple tokens share one packed allocation, not four overlapping role\n"
     "    // envelopes. Preserve the original separated-pointer checks for M1.\n"
     "    val multi = j.tokens > 1.U\n"
     "    val packedReads = Seq((j.queryIn, j.tokens.pad(66) * 12288.U),\n"
     "      (j.ab, j.tokens.pad(66) * 64.U), (j.aLog, 64.U), (j.dtBias, 64.U))\n"
     "    val packedWrite = (j.query, j.tokens.pad(66) * 25600.U)\n"
     "    val packedBadAddress = (packedReads :+ packedWrite).map { case (base, size) =>\n"
     "      base(5, 0) =/= 0.U || base.pad(82) + size.pad(82) > (BigInt(1) << 56).U }.reduce(_ || _)\n"
     "    val packedOverlap = packedReads.map { case (base, size) =>\n"
     "      packedWrite._1.pad(82) < base.pad(82) + size.pad(82) &&\n"
     "        base.pad(82) < packedWrite._1.pad(82) + packedWrite._2.pad(82) }.reduce(_ || _)\n"
     "    val packedPointers = j.keyIn.pad(66) === j.queryIn.pad(66) + 4096.U &&\n"
     "      j.valueIn.pad(66) === j.queryIn.pad(66) + 8192.U &&\n"
     "      j.key.pad(66) === j.query.pad(66) + 8192.U &&\n"
     "      j.value.pad(66) === j.query.pad(66) + 16384.U &&\n"
     "      j.gates.pad(66) === j.query.pad(66) + 24576.U\n"
     "    val badTokens = j.tokens === 0.U || j.tokens > maxTokens.U ||\n"
     "      (multi && ((heads != 16).B || j.recurrentMode))\n"
     "    val badLayout = Mux(multi, !packedPointers || packedBadAddress || packedOverlap, badAddress || badOverlap)\n"
     "    when(badTokens || j.heads =/= heads.U || badLayout) { fail(Status.Bounds.U) }"),
    ("          when(head === (heads - 1).U) { state := finish }",
     "          when(head === (heads - 1).U) {\n"
     "            when(token.pad(17) + 1.U === job.tokens.pad(17)) { state := finish }\n"
     "              .otherwise {\n"
     "                token := token + 1.U; param := 0.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U\n"
     "                accumulator := 0.U; state := readParam\n"
     "              }\n"
     "          }"),
]


def expected_overlay(baseline):
    result = baseline
    for old, new in REPLACEMENTS:
        if result.count(old) != 1:
            raise AssertionError("Literal edit anchor is missing or ambiguous: " + old[:100])
        result = result.replace(old, new, 1)
    return result


def between(text, start, end):
    if text.count(start) != 1:
        raise AssertionError("Source block start is missing or ambiguous")
    first = text.index(start)
    return text[first:text.index(end, first + len(start))]


@dataclass(frozen=True)
class Job:
    tokens: int = 1
    heads: int = 16
    queryIn: int = 0x100000
    keyIn: int = 0x101000
    valueIn: int = 0x102000
    ab: int = 0x400000
    aLog: int = 0x500000
    dtBias: int = 0x600000
    query: int = 0x1000000
    key: int = 0x1002000
    value: int = 0x1004000
    gates: int = 0x1006000
    recurrentMode: bool = False


def packed_job(tokens, *, conv=0x100000, prep=0x1000000, **kwargs):
    return Job(tokens=tokens, queryIn=conv, keyIn=conv + 4096, valueIn=conv + 8192,
               query=prep, key=prep + 8192, value=prep + 16384, gates=prep + 24576, **kwargs)


def separated_job(heads=16, recurrent=False):
    return Job(heads=heads, queryIn=0x100000, keyIn=0x300000, valueIn=0x500000,
               ab=0x700000, aLog=0x710000, dtBias=0x720000,
               query=0x1000000, key=0x1400000, value=0x1800000, gates=0x1C00000,
               recurrentMode=recurrent)


def overlap(a, b):
    return a[0] < b[0] + b[1] and b[0] < a[0] + a[1]


def valid_span(span):
    base, size = span
    return 0 <= base < U64 and base % 64 == 0 and size > 0 and base + size <= LIMIT


def old_spans(j, heads):
    reads = [(j.queryIn, heads * 256), (j.keyIn, heads * 256), (j.valueIn, heads * 256),
             (j.ab, 64), (j.aLog, 64), (j.dtBias, 64)]
    writes = [(j.query, heads * 512), (j.key, heads * 512), (j.value, heads * 512), (j.gates, heads * 64)]
    return reads, writes


def old_admit(j, heads=16):
    reads, writes = old_spans(j, heads)
    return (j.tokens == 1 and j.heads == heads
            and all(valid_span(s) for s in reads + writes)
            and not any(overlap(w, r) for w in writes for r in reads)
            and not any(overlap(writes[i], writes[k]) for i in range(4) for k in range(i)))


def admit(j, heads=16, max_tokens=1):
    """Unbounded-integer specification, NOT an interpreter of the Scala owner."""
    if not (1 <= heads <= 16 and 1 <= max_tokens <= 128):
        raise ValueError("Invalid constructor domain")
    if not 1 <= j.tokens <= max_tokens or j.heads != heads:
        return False
    if j.tokens == 1:
        return old_admit(j, heads)
    if heads != 16 or j.recurrentMode:
        return False
    pointers = ((j.keyIn, j.queryIn + 4096), (j.valueIn, j.queryIn + 8192),
                (j.key, j.query + 8192), (j.value, j.query + 16384), (j.gates, j.query + 24576))
    if any(actual != expected for actual, expected in pointers):
        return False
    reads = [(j.queryIn, j.tokens * CONV_STRIDE), (j.ab, j.tokens * 64), (j.aLog, 64), (j.dtBias, 64)]
    write = (j.query, j.tokens * PREP_STRIDE)
    return all(valid_span(s) for s in reads + [write]) and not any(overlap(write, r) for r in reads)


@dataclass(frozen=True)
class Tx:
    kind: str
    token: int
    head: int
    role: int
    beat: int
    address: int


def transactions(j):
    """Synthetic Head -> Role -> Beat schedule. Scalar operations are not simulated."""
    in_bases = (j.queryIn, j.keyIn, j.valueIn)
    out_bases = (j.query, j.key, j.value)
    for token in range(j.tokens):
        budget()
        for param, address in enumerate((j.ab + token * 64, j.aLog, j.dtBias)):
            yield Tx("param", token, -1, param, 0, address)
        for head in range(j.heads):
            for role in range(3):
                for beat in range(4):
                    yield Tx("read", token, head, role, beat, in_bases[role] + token * CONV_STRIDE + head * 256 + beat * 64)
                for beat in range(8):
                    yield Tx("write", token, head, role, beat, out_bases[role] + token * PREP_STRIDE + head * 512 + beat * 64)
            yield Tx("gate", token, head, -1, 0, j.gates + token * PREP_STRIDE + head * 64)


class ControlContract:
    """Synthetic ACK/event oracle only; it is not Scala or a real handshake trace."""
    def __init__(self, tokens, heads=16):
        self.tokens, self.heads = tokens, heads
        self.token = self.sequence = self.bytes = self.cycles = 0
        self.param = self.head = self.role = self.beat = self.lane = self.accumulator = 0
        self.state, self.status, self.pending = "readParam", "Ok", None

    def tick(self):
        if self.state not in ("idle", "finish", "locked"):
            self.cycles += 1

    def request(self, tx, ready=True):
        self.tick()
        if self.pending is not None or self.state in ("finish", "locked", "idle"):
            raise AssertionError("Contract request outside its active single-outstanding domain")
        if tx.token != self.token:
            raise AssertionError("Wrong synthetic token")
        if not ready:
            return False
        self.pending = tx
        self.state = {"param": "waitParam", "read": "waitVector", "write": "waitWrite", "gate": "waitGate"}[tx.kind]
        return True

    def response(self, valid=True, ready=True, tag_match=True, error=False):
        self.tick()
        if not valid or not ready or self.pending is None:
            return False
        tx, self.pending = self.pending, None
        if not tag_match or error:
            self.status = "Protocol" if not tag_match else "Memory"
            self.state = "finish"
            return True
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        if tx.kind in ("write", "gate"):
            self.bytes += 64
        self.state = "active"
        if tx.kind == "gate" and tx.head == self.heads - 1:
            if self.token + 1 == self.tokens:
                self.state = "finish"
            else:
                self.token += 1
                self.param = self.head = self.role = self.beat = self.lane = self.accumulator = 0
                self.state = "readParam"
        return True

    @property
    def committed(self):
        return self.state == "finish" and self.status == "Ok"

    def done(self, ready):
        if self.state == "finish" and ready:
            self.state = "idle" if self.status == "Ok" else "locked"

    def snapshot(self):
        # Cycles intentionally advance during active stalls; control/counters do not.
        return (self.token, self.sequence, self.bytes, self.state, self.status, self.pending)


class SourceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_inputs = {}
        for path, (size, digest) in PINS.items():
            if path.stat().st_size != size:
                raise AssertionError("pinned source size mismatch before read")
            with path.open("rb") as stream:
                raw = stream.read(size + 1)
            if len(raw) != size or sha256(raw).hexdigest() != digest:
                raise AssertionError("pinned source byte identity mismatch")
            raw_inputs[path] = raw
        cls.base = raw_inputs[BASELINE].decode("utf-8")
        cls.source = raw_inputs[OVERLAY].decode("utf-8")

    def test_exact_input_pins(self):
        for path, (size, digest) in PINS.items():
            with self.subTest(name=path.name):
                raw = path.read_bytes()
                self.assertEqual(len(raw), size)
                self.assertEqual(sha256(raw).hexdigest(), digest)

    def test_only_reviewed_literal_edits(self):
        self.assertEqual(self.source, expected_overlay(self.base))

    def test_uniform_patch_matches_sources(self):
        name = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnInputPrepOwner.scala"
        expected = "".join(difflib.unified_diff(self.base.splitlines(keepends=True), self.source.splitlines(keepends=True),
                                               fromfile="a/" + name, tofile="b/" + name))
        self.assertEqual(PATCH.read_text(encoding="utf-8"), expected)

    def test_bundle_enums_arithmetic_failures_and_terminal_preserved(self):
        blocks = [
            ("class GdnInputPrepJob", "/** No arithmetic service"),
            ("  val idle ::", "  val job = Reg"),
            ("  val outputBeats =", "  when(io.job.fire)"),
            ("  when(io.memory.fire)", "        when(state === waitGate)"),
            ("  when(io.scalar.request.fire)", "\n}\n"),
        ]
        for start, end in blocks:
            with self.subTest(block=start):
                self.assertEqual(between(self.base, start, end), between(self.source, start, end))
        self.assertIn("Cat(0.U(448.W), beta, g)", self.source)
        self.assertIn("when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }", self.source)

    def test_m1_spans_are_byte_preserved(self):
        old = between(self.base, "    val reads =", "    when(j.tokens =/= 1.U")
        new = between(self.source, "    val reads =", "    // Multiple tokens")
        self.assertEqual(old, new)

    def test_counter_resets_and_ack_nesting_are_pinned(self):
        # Full-file equality establishes nesting; these counts make obligations explicit.
        self.assertEqual(self.source.count("token := 0.U"), 1)
        self.assertEqual(self.source.count("token := token + 1.U"), 1)
        for name in ("sequence", "bytes", "cycles"):
            self.assertEqual(self.source.count(name + " := 0.U"), 1)
        self.assertEqual(self.source.count("val token = RegInit(0.U(16.W))"), 1)
        self.assertEqual(self.source.count("token.pad(17) + 1.U === job.tokens.pad(17)"), 1)
        self.assertEqual(self.source.count("val idle ::"), 1)
        self.assertIn("Enum(13)", self.source)
        self.assertIn("Enum(16)", self.source)


class AdmissionContractChecks(unittest.TestCase):
    def test_default_m1_separated_pointers_and_recurrent_preserved(self):
        for heads in (1, 2, 8, 16):
            for recurrent in (False, True):
                j = separated_job(heads, recurrent)
                self.assertTrue(old_admit(j, heads))
                self.assertEqual(admit(j, heads), old_admit(j, heads))
                self.assertEqual(admit(j, heads, 128), old_admit(j, heads))
                # Original contract permits read/read overlap.
                alias = replace(j, keyIn=j.queryIn, valueIn=j.queryIn, aLog=j.ab, dtBias=j.ab)
                self.assertTrue(admit(alias, heads))
                for field in ("queryIn", "keyIn", "valueIn", "ab", "aLog", "dtBias", "query", "key", "value", "gates"):
                    bad = replace(j, **{field: getattr(j, field) + 1})
                    self.assertFalse(admit(bad, heads))
                    self.assertEqual(admit(bad, heads), old_admit(bad, heads))
                self.assertFalse(admit(replace(j, key=j.query), heads))
                self.assertFalse(admit(replace(j, query=j.queryIn), heads))
        self.assertFalse(admit(packed_job(2)))
        self.assertTrue(admit(packed_job(1, recurrentMode=True), max_tokens=128))

    def test_tokens_heads_recurrent_and_constructor_negative_cases(self):
        for tokens in (0, 129, 65535):
            self.assertFalse(admit(packed_job(tokens), max_tokens=128))
        self.assertFalse(admit(packed_job(16), max_tokens=2))
        for tokens in (2, 16, 128):
            self.assertTrue(admit(packed_job(tokens), max_tokens=128))
            self.assertFalse(admit(packed_job(tokens, recurrentMode=True), max_tokens=128))
            self.assertFalse(admit(replace(packed_job(tokens), heads=8), heads=8, max_tokens=128))
            self.assertFalse(admit(replace(packed_job(tokens), heads=8), heads=16, max_tokens=128))
        for heads, maximum in ((0, 1), (17, 1), (16, 0), (16, 129)):
            with self.assertRaises(ValueError):
                admit(Job(), heads, maximum)

    def test_all_packed_role_relations_and_no_wrap(self):
        j = packed_job(2)
        for field in ("keyIn", "valueIn", "key", "value", "gates"):
            for delta in (-64, 64):
                with self.subTest(field=field, delta=delta):
                    self.assertFalse(admit(replace(j, **{field: getattr(j, field) + delta}), max_tokens=128))
        # These satisfy selected modulo-2^64 additions, never wide exact relations.
        wrapped_input = replace(j, queryIn=U64 - 4096, keyIn=0, valueIn=4096)
        wrapped_output = replace(j, query=U64 - 8192, key=0, value=8192, gates=16384)
        self.assertFalse(admit(wrapped_input, max_tokens=128))
        self.assertFalse(admit(wrapped_output, max_tokens=128))

    def test_full_bounds_and_alignment_for_each_allocation(self):
        for m in (2, 16, 128):
            for role, size in (("conv", m * CONV_STRIDE), ("prep", m * PREP_STRIDE),
                               ("ab", m * 64), ("aLog", 64), ("dtBias", 64)):
                if role == "conv":
                    good = packed_job(m, conv=LIMIT - size)
                    bad = packed_job(m, conv=LIMIT - size + 64)
                    unaligned = packed_job(m, conv=0x100001)
                elif role == "prep":
                    good = packed_job(m, prep=LIMIT - size)
                    bad = packed_job(m, prep=LIMIT - size + 64)
                    unaligned = packed_job(m, prep=0x1000001)
                else:
                    good = replace(packed_job(m), **{role: LIMIT - size})
                    bad = replace(packed_job(m), **{role: LIMIT - size + 64})
                    unaligned = replace(packed_job(m), **{role: 0x800001})
                with self.subTest(tokens=m, allocation=role):
                    self.assertTrue(admit(good, max_tokens=128))
                    self.assertFalse(admit(bad, max_tokens=128))
                    self.assertFalse(admit(unaligned, max_tokens=128))

    def test_complete_read_allocation_aliases_and_later_token_destruction(self):
        for m in (2, 16, 128):
            j = packed_job(m)
            # Last output beat versus each parameter read span.
            last = j.query + m * PREP_STRIDE - 64
            for field in ("ab", "aLog", "dtBias"):
                self.assertFalse(admit(replace(j, **{field: last}), max_tokens=128))
            # First output would destroy a later token's Conv row, although the
            # complete first Conv row and first output row are mutually disjoint.
            destructive = packed_job(m, prep=j.queryIn + (m - 1) * CONV_STRIDE)
            self.assertFalse(overlap((destructive.queryIn, CONV_STRIDE), (destructive.query, PREP_STRIDE)))
            self.assertTrue(overlap((destructive.queryIn, m * CONV_STRIDE), (destructive.query, m * PREP_STRIDE)))
            self.assertFalse(admit(destructive, max_tokens=128))
            # AB token 0 lies immediately before output; AB token 1 is overwritten.
            late_ab = replace(j, ab=j.query - 64)
            self.assertFalse(overlap((late_ab.ab, 64), (late_ab.query, PREP_STRIDE)))
            self.assertFalse(admit(late_ab, max_tokens=128))
            # Prep's later row, not its first row, aliases Conv input.
            late_prep = packed_job(m, conv=j.query + (m - 1) * PREP_STRIDE)
            self.assertFalse(overlap((late_prep.query, PREP_STRIDE), (late_prep.queryIn, CONV_STRIDE)))
            self.assertFalse(admit(late_prep, max_tokens=128))
            # Half-open endpoints may touch; read/read aliases remain permitted.
            touching = packed_job(m, prep=j.queryIn + m * CONV_STRIDE,
                                  ab=0x4000000, aLog=0x5000000, dtBias=0x6000000)
            self.assertTrue(admit(touching, max_tokens=128))
            read_alias = replace(j, ab=j.queryIn, aLog=j.queryIn, dtBias=j.queryIn)
            self.assertTrue(admit(read_alias, max_tokens=128))


class LayoutAndControlContractChecks(unittest.TestCase):
    def test_m1_address_trajectory_matches_original_separated_formula(self):
        for heads in (1, 8, 16):
            for recurrent in (False, True):
                j = separated_job(heads, recurrent)
                reads = (j.queryIn, j.keyIn, j.valueIn)
                writes = (j.query, j.key, j.value)
                for tx in transactions(j):
                    self.assertEqual(tx.token, 0)
                    if tx.kind == "param":
                        expected = (j.ab, j.aLog, j.dtBias)[tx.role]
                    elif tx.kind == "gate":
                        expected = j.gates + tx.head * 64
                    elif tx.kind == "read":
                        expected = reads[tx.role] + tx.head * 256 + tx.beat * 64
                    else:
                        expected = writes[tx.role] + tx.head * 512 + tx.beat * 64
                    self.assertEqual(tx.address, expected)

    def test_m2_m16_m128_complete_unique_layout_and_transaction_counts(self):
        for m in (2, 16, 128):
            j = packed_job(m)
            all_writes, all_conv_reads, coordinate_keys = set(), set(), set()
            param_addresses = []
            read_count = write_count = 0
            token_ends = []
            for n, tx in enumerate(transactions(j)):
                if n % 1024 == 0:
                    budget()
                self.assertEqual(tx.address % 64, 0)
                key = (tx.kind, tx.token, tx.head, tx.role, tx.beat)
                self.assertNotIn(key, coordinate_keys)
                coordinate_keys.add(key)
                if tx.kind in ("write", "gate"):
                    self.assertNotIn(tx.address, all_writes)
                    all_writes.add(tx.address)
                    self.assertTrue(j.query <= tx.address and tx.address + 64 <= j.query + m * PREP_STRIDE)
                    write_count += 1
                else:
                    read_count += 1
                    if tx.kind == "param":
                        param_addresses.append((tx.token, tx.role, tx.address))
                    else:
                        self.assertNotIn(tx.address, all_conv_reads)
                        all_conv_reads.add(tx.address)
                        self.assertTrue(j.queryIn <= tx.address and tx.address + 64 <= j.queryIn + m * CONV_STRIDE)
                if tx.kind == "gate" and tx.head == 15:
                    token_ends.append(tx.token)
                    self.assertEqual(n + 1, (tx.token + 1) * 595)
                    self.assertEqual(write_count * 64, (tx.token + 1) * PREP_STRIDE)
            self.assertEqual(all_writes, set(range(j.query, j.query + m * PREP_STRIDE, 64)))
            self.assertEqual(all_conv_reads, set(range(j.queryIn, j.queryIn + m * CONV_STRIDE, 64)))
            self.assertEqual(param_addresses, [(t, p, a) for t in range(m) for p, a in enumerate((j.ab + t * 64, j.aLog, j.dtBias))])
            self.assertEqual((read_count, write_count, read_count + write_count, write_count * 64),
                             (m * 195, m * 400, m * 595, m * PREP_STRIDE))
            self.assertEqual(len(token_ends), m)
            # Explicit first/final allocation addresses, including token 127.
            self.assertEqual(min(all_writes), j.query)
            self.assertEqual(max(all_writes), j.query + m * PREP_STRIDE - 64)
            self.assertEqual(max(all_conv_reads), j.queryIn + m * CONV_STRIDE - 64)
            if m == 128:
                self.assertEqual((read_count, write_count, read_count + write_count, write_count * 64, token_ends[-1]),
                                 (24960, 51200, 76160, 3276800, 127))

    def test_counters_preserved_at_each_synthetic_token_boundary(self):
        # At most 128 boundary events, not a 76k-event simulated handshake run.
        for m in (2, 16, 128):
            ctl = ControlContract(m)
            for token in range(m):
                # Contract counts before the final gate ACK. These are explicit
                # specification inputs, not values obtained from real hardware.
                ctl.sequence = token * 595 + 594
                ctl.bytes = token * PREP_STRIDE + PREP_STRIDE - 64
                before_cycles = ctl.cycles
                ctl.request(Tx("gate", token, 15, -1, 0, 0))
                ctl.response()
                self.assertEqual(ctl.sequence, (token + 1) * 595)
                self.assertEqual(ctl.bytes, (token + 1) * PREP_STRIDE)
                self.assertEqual(ctl.cycles, before_cycles + 2)
                self.assertEqual(ctl.token, min(token + 1, m - 1))
                self.assertEqual(ctl.state, "finish" if token == m - 1 else "readParam")
            self.assertTrue(ctl.committed)

    def test_token_advances_only_after_last_head_gate_ack(self):
        ctl = ControlContract(2)
        for kind, head in (("param", -1), ("read", 15), ("write", 15), ("gate", 14)):
            ctl.request(Tx(kind, 0, head, 0, 0, 0))
            ctl.response()
            self.assertEqual(ctl.token, 0)
            self.assertFalse(ctl.committed)
        gate = Tx("gate", 0, 15, -1, 0, 0)
        before = ctl.snapshot()
        self.assertFalse(ctl.request(gate, ready=False))
        self.assertEqual(ctl.snapshot(), before)
        ctl.request(gate)
        waiting = ctl.snapshot()
        self.assertFalse(ctl.response(valid=False))
        self.assertEqual(ctl.snapshot(), waiting)
        self.assertFalse(ctl.response(ready=False))
        self.assertEqual(ctl.snapshot(), waiting)
        ctl.param = ctl.head = ctl.role = ctl.beat = ctl.lane = ctl.accumulator = 7
        sequence, written, cycles = ctl.sequence, ctl.bytes, ctl.cycles
        ctl.response()
        self.assertEqual((ctl.token, ctl.state), (1, "readParam"))
        self.assertEqual((ctl.param, ctl.head, ctl.role, ctl.beat, ctl.lane, ctl.accumulator), (0,) * 6)
        self.assertEqual((ctl.sequence, ctl.bytes, ctl.cycles), (sequence + 1, written + 64, cycles + 1))
        self.assertFalse(ctl.committed)
        final_gate = Tx("gate", 1, 15, -1, 0, 0)
        ctl.request(final_gate)
        self.assertFalse(ctl.committed)
        ctl.response(valid=False)
        self.assertFalse(ctl.committed)
        ctl.response()
        self.assertTrue(ctl.committed)
        terminal = ctl.snapshot()
        for _ in range(3):
            ctl.done(ready=False)
            ctl.tick()
            self.assertEqual(ctl.snapshot(), terminal)
        ctl.done(ready=True)
        self.assertEqual(ctl.state, "idle")

    def test_bad_tag_or_error_never_advances_success_and_locks(self):
        for token, tokens in ((0, 2), (1, 2), (127, 128)):
            for match, error, status in ((False, False, "Protocol"), (True, True, "Memory"), (False, True, "Protocol")):
                ctl = ControlContract(tokens)
                ctl.token, ctl.sequence, ctl.bytes = token, 100, 6400
                ctl.request(Tx("gate", token, 15, -1, 0, 0))
                ctl.response(tag_match=match, error=error)
                self.assertEqual((ctl.token, ctl.sequence, ctl.bytes, ctl.status, ctl.state), (token, 100, 6400, status, "finish"))
                self.assertFalse(ctl.committed)
                ctl.done(ready=False)
                self.assertEqual(ctl.state, "finish")
                ctl.done(ready=True)
                self.assertEqual(ctl.state, "locked")

    def test_m128_end_comparison_cannot_wrap_at_127(self):
        # A 7-bit add would wrap 127+1 to zero. The pinned source uses a 16-bit
        # token and a 17-bit final comparison, and never increments on completion.
        self.assertEqual((127 + 1) & 0x7F, 0)
        self.assertEqual((127 + 1) & 0x1FFFF, 128)
        ctl = ControlContract(128)
        ctl.token, ctl.sequence, ctl.bytes = 127, 76159, 3276736
        ctl.request(Tx("gate", 127, 15, -1, 0, 0))
        ctl.response()
        self.assertEqual((ctl.token, ctl.sequence, ctl.bytes, ctl.state), (127, 76160, 3276800, "finish"))
        self.assertTrue(ctl.committed)


def main():
    global DEADLINE, BASELINE, OVERLAY, PINS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-source", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    args = parser.parse_args()
    BASELINE = args.base_source.resolve(strict=True)
    OVERLAY = args.overlay.resolve(strict=True)
    if BASELINE == OVERLAY or BASELINE in PINS or OVERLAY in PINS:
        raise SystemExit("Source inputs must be distinct; byte pins remain mandatory")
    PINS = dict(PINS)
    PINS[BASELINE] = BASELINE_SPEC
    PINS[OVERLAY] = OVERLAY_SPEC
    expected_python = "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python"
    if sys.executable != expected_python or sys.version_info[:3] != (3, 12, 14):
        raise SystemExit("Refusing execution: use the pinned CPython 3.12.14 executable, not /usr/bin/python3")
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise SystemExit("Refusing execution: -I -S -B are required")
    # Single process, one allowed CPU, no concurrent workers; 256 MiB address cap.
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    started = time.monotonic()
    DEADLINE = started + 4.5
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    budget()
    elapsed = time.monotonic() - started
    print(json.dumps({
        "scope": "pinned-source + synthetic integer layout and bounded ACK contract only",
        "not_evidence_for": ["Scala", "RTL", "native", "model", "numerical outputs", "real handshakes", "hardware cycles", "fullblock utilization"],
        "source_synthetic_only": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "elapsed_seconds": round(elapsed, 6), "max_cpus": 1, "address_space_limit_mib": 256,
        "interpreter": sys.version, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "cpu_soft_limit_seconds": 4, "cpu_hard_limit_seconds": 5,
        "m128_synthetic": {"reads": 24960, "writes": 51200, "transactions": 76160, "write_bytes": 3276800},
    }, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
