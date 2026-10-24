#!/usr/bin/env python3
"""Bounded stdlib phase-1 contract controls, NOT a Scala/RTL or FP32 DUT test.

Root-only, separately admitted command: Python 3.12 -I -S -B tests.py --base
FIXED_SOURCE_ROOT --contract CONTRACT_ROOT. Outer limits: 10 s, one CPU,
256 MiB. No candidate execution is authorized merely by possessing this file.

The scalar service below is SIMULATED with exact integer binary32 RNE Add.
It supplies responses to a Python protocol model. Hand-derived vectors check
that helper, but neither helper nor Python owner is independent hardware DUT
validation. Injected service errors are explicitly synthetic, not naturally
occurring finite same-format Add underflow. Full-source pins are checked before
and after; the verified raw model bytes are compiled/exec'd without pyc/import.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import unittest
from dataclasses import fields, replace
from functools import lru_cache

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREFIX = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/"
PROTO_PATH = PREFIX + "Protocol.scala"
SCALAR_SOURCE = PREFIX + "BlockFloat.scala"
SCALAR_ABI = PREFIX + "GdnOwnerProtocol.scala"
CONTRACT_PROTOCOL = "source/GdnChunkProtocol.scala"
CONTRACT_PLAN = "source/GdnChunkAddressPlan.scala"
OWNER_SOURCE = "source/GdnChunkLoadPrepOwner.scala"
MODEL = PINS = None
FULL_CASES = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def readonly_audit(event, args):
    """Fail closed on writes, subprocesses, network, and dynamic native loads."""
    denied = ("ctypes.dlopen", "subprocess.Popen", "os.system", "os.posix_spawn",
              "os.fork", "os.exec", "os.remove", "os.rename", "os.rmdir",
              "os.mkdir", "os.unlink", "os.symlink", "os.link", "os.truncate",
              "os.chmod", "os.chown", "os.utime", "os.setxattr", "os.removexattr")
    if event in denied or event.startswith("socket."):
        raise RuntimeError("read-only controls forbid this operation")
    if event == "open":
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if ((isinstance(mode, str) and any(char in mode for char in "wax+"))
                or (isinstance(flags, int) and flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
            raise RuntimeError("read-only controls forbid file writes")


def safe_path(root, relative):
    require(isinstance(relative, str) and relative, "missing relative pin path")
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "unsafe pin path")
    path = root / rel
    require(path.is_file() and not path.is_symlink(), "pin must be a regular file")
    require(path.resolve().is_relative_to(root.resolve()), "pin escapes root")
    return path


def read_small(path, expected=None):
    before = path.stat()
    require(before.st_size <= 2 * 1024 * 1024, "file exceeds small-control bound")
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    require(identity(before) == identity(after), "file changed during read")
    digest = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        require(digest == {"bytes": expected["bytes"], "sha256": expected["sha256"]},
                f"pin mismatch: {path.name}")
    return raw, digest


class PinSet:
    def __init__(self, base, contract):
        self.roots = {"base": base.resolve(), "contract": contract.resolve()}
        pins_raw, pins_digest = read_small(HERE / "INPUT_PINS.json")
        manifest_raw, manifest_digest = read_small(HERE / "SOURCE_MANIFEST.json")
        external, manifest = json.loads(pins_raw), json.loads(manifest_raw)
        require(isinstance(external.get("files"), dict) and external["files"], "missing input pins")
        require(isinstance(manifest.get("files"), dict) and manifest["files"], "missing source pins")
        own = manifest["files"]
        require({"loadprep_model.py", "tests.py", OWNER_SOURCE, "README.md", "SCOPE.json",
                 "INPUT_PINS.json", "TEST_COMMAND.json"} <= set(own), "omitted own required file")
        require("SOURCE_MANIFEST.json" not in own, "self-referential manifest")
        self.entries, self.cache = [], {}
        self.descriptors = [(HERE / "INPUT_PINS.json", pins_digest),
                            (HERE / "SOURCE_MANIFEST.json", manifest_digest)]
        for label, spec in external["files"].items():
            require(spec.get("role") in self.roots, f"unknown pin role: {label}")
            key = (spec["role"], spec["path"])
            require(key not in self.cache, "duplicate external pin")
            path = safe_path(self.roots[spec["role"]], spec["path"])
            raw, digest = read_small(path, spec)
            self.cache[key] = raw
            self.entries.append((path, digest))
        for relative, spec in own.items():
            path = safe_path(HERE, relative)
            raw, digest = read_small(path, spec)
            self.cache[("own", relative)] = raw
            self.entries.append((path, digest))
        require(sum(spec["bytes"] for _, spec in self.entries) <= 20 * 1024 * 1024,
                "input set exceeds total small-control bound")
        required = {("base", PROTO_PATH), ("base", SCALAR_SOURCE), ("base", SCALAR_ABI),
                    ("contract", CONTRACT_PROTOCOL), ("contract", CONTRACT_PLAN)}
        require(required <= set(self.cache), "missing source correspondence input")

    def text(self, role, relative):
        return self.cache[(role, relative)].decode("utf-8")

    def verify_after(self):
        for path, digest in self.descriptors + self.entries:
            read_small(path, digest)


def compact(source):
    return re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S))


def bundle_fields(source, name):
    body = source.split(f"class {name} extends Bundle {{", 1)[1].split("}", 1)[0]
    return re.findall(r"\bval\s+(\w+)\s*=", body)


@lru_cache(maxsize=1)
def shapes():
    source = PINS.text("contract", CONTRACT_PLAN)
    body = source.split("val Shapes: Vector[Shape] = Vector(", 1)[1].split("require(Shapes", 1)[0]
    return tuple((name, int(rows), int(cols)) for name, rows, cols in re.findall(
        r'Shape\("([a-z_]+)",\s*(\d+),\s*(\d+)\)', body))


def make_job(tokens=16, head=0, chunk=0, cold=False):
    m = MODEL
    c = m.Context(0x87654321, tokens, cold, 0 if cold else 7, 0,
                  0x100000, 0x800000, 0xA00000, 0xC00000, 0x1000000)
    root = m.Committed(not cold, c.expected_generation, c.state_in if not cold else 0)
    prep = m.PreparedReceipt(c.tag, c.expected_generation, tokens, c.input, 0,
                             tokens * 25600, True, True, False)
    initial = m.Receipt(c.tag, c.expected_generation, head, 0, 0, 0, 65536, 0, 0, True)
    previous = replace(initial, phase=16)
    output = replace(initial, phase=17, scratch_ack_bytes=0, output_ack_bytes=16384)
    return m.Job(c, head, chunk, prep, initial, previous, output), root


def repack_context(job, **changes):
    """Keep receipts consistent when testing only an allocation/root change."""
    c = replace(job.context, **changes)
    common = {"tag": c.tag, "expected_generation": c.expected_generation}
    return replace(job, context=c,
                   prep_ready=replace(job.prep_ready, **common, tokens=c.tokens,
                                      input=c.input, write_bytes=c.tokens * 25600),
                   initial_ready=replace(job.initial_ready, **common),
                   previous_state_ready=replace(job.previous_state_ready, **common),
                   previous_output_ready=replace(job.previous_output_ready, **common))


def pack(words):
    return sum(word << (lane * 32) for lane, word in enumerate(words))


def simulated_add_rne(a, b):
    """SIMULATED scalar response service, not independent FP32 DUT evidence.

    Exact integers in units of 2**-149, followed by binary32 nearest-even.
    Finite same-format Add cannot have an inexact tiny result: if its exact
    magnitude is subnormal it is already an integral multiple of 2**-149.
    """
    def decode(word):
        exp, frac = (word >> 23) & 255, word & 0x7FFFFF
        if exp == 255:
            raise ValueError("simulated finite Add expects finite operands")
        n = frac if exp == 0 else (frac | 0x800000) << (exp - 1)
        return -n if word >> 31 else n
    total = decode(a) + decode(b)
    if total == 0:
        return (0x80000000 if a == b == 0x80000000 else 0), False
    sign = 0x80000000 if total < 0 else 0
    magnitude = abs(total)
    if magnitude < 0x800000:
        return sign | magnitude, False
    shift = max(0, magnitude.bit_length() - 24)
    mantissa = magnitude >> shift
    if shift:
        remainder = magnitude - (mantissa << shift)
        halfway = 1 << (shift - 1)
        if remainder > halfway or (remainder == halfway and mantissa & 1):
            mantissa += 1
    if mantissa == 0x1000000:
        mantissa >>= 1
        shift += 1
    exponent = shift + 1
    if exponent >= 255:
        return sign | 0x7F800000, True
    return sign | (exponent << 23) | (mantissa & 0x7FFFFF), False


def gate_words(row):
    # -1, -2**-24, -2**-24 round separately to -1 at every prefix.
    g = (0xBF800000, 0xB3800000, 0xB3800000, 0x80000001)[row] if row < 4 else (0x80000000 if row & 1 else 0)
    beta = (0, 0x80000000, 0x3F800000, 0x3F000000)[row % 4]
    return g, beta


def input_payload(job, row, role, beat):
    if role == 0:
        return pack(gate_words(row))
    # Finite, lane-distinct, reproducible opaque QKV, including signed zeros,
    # exact subnormals and maximal finite values. No float conversion occurs.
    specials = (0, 0x80000000, 1, 0x80000001, 0x007FFFFF, 0x7F7FFFFF)
    words = list(specials)
    for lane in range(6, 16):
        bits = ((row * 1009 + role * 103 + beat * 17 + lane + job.head * 4099
                 + job.chunk * 65537) & 0x7FFFFF)
        words.append(0x3F000000 | bits | ((lane & 1) << 31))
    return pack(words)


def expected_addresses(job, row, role, beat):
    """Independent indexing formulas from pinned declarative shape rows."""
    c = job.context
    sizes = [r * cols * 4 for _, r, cols in shapes()]
    chunk_bytes = sum(sizes)
    chunk_base = c.scratch + job.head * (128 * 128 * 4 + ((c.tokens + 63) // 64) * chunk_bytes)
    chunk_base += 128 * 128 * 4 + job.chunk * chunk_bytes
    source = c.input + (job.chunk * 64 + row) * (3 * 16 * 128 * 4 + 16 * 16 * 4)
    if role == 0:
        return source + 3 * 16 * 128 * 4 + job.head * 64, chunk_base + row * 64
    return (source + ((role - 1) * 16 + job.head) * 128 * 4 + beat * 64,
            chunk_base + sum(sizes[:role]) + row * 128 * 4 + beat * 64)


def full_run(test, job, root, stalls=False):
    """Explicit bounded fire events; fake services never execute model code."""
    m, owner = MODEL, MODEL.Owner()
    accepted = owner.tick(job=job, committed=root)
    test.assertTrue(accepted.job_fire)
    requests, scalar_requests, gate_writes = [], [], []
    memory_pending = scalar_pending = None
    steps = 0
    while owner.signals().done is None:
        steps += 1
        test.assertLess(steps, 10000)
        s = owner.signals()
        test.assertFalse(owner.outstanding and owner.scalar_outstanding)
        test.assertFalse(s.memory_request is not None and s.scalar_request is not None)
        if s.memory_request is not None:
            r = s.memory_request
            test.assertIsNone(memory_pending)
            test.assertIsNone(scalar_pending)
            test.assertEqual(r.tag, (job.context.tag << 32) | len(requests))
            test.assertEqual(r.mask, (1 << 64) - 1 if r.write else 0)
            read_address, write_address = expected_addresses(job, owner.row, owner.role, owner.beat)
            test.assertEqual(r.address, write_address if r.write else read_address)
            valid = job.chunk * 64 + owner.row < job.context.tokens
            if r.write:
                if owner.role == 0:
                    expected = pack((0xBF800000, gate_words(owner.row)[1] if valid else 0))
                    gate_writes.append(r.data)
                else:
                    expected = input_payload(job, owner.row, owner.role, owner.beat) if valid else 0
                test.assertEqual(r.data, expected)
            else:
                test.assertTrue(valid, "padded row must not read input")
                test.assertEqual(r.data, 0)
            for _ in range((len(requests) % 3) if stalls else 0):
                stalled = owner.tick(memory_ready=False)
                test.assertFalse(stalled.memory_fire)
                test.assertEqual(owner.signals().memory_request, r)
            data = 0 if r.write else input_payload(job, owner.row, owner.role, owner.beat)
            # Response offered on the same edge is NOT yet accepted.
            e = owner.tick(memory_ready=True, response=m.Response(r.tag, data),
                           scalar_result=m.ScalarResult(0x7FC00000))
            test.assertTrue(e.memory_fire)
            test.assertFalse(e.response_fire or e.scalar_result_fire)
            memory_pending = m.Response(r.tag, data)
            requests.append(r)
        elif s.response_ready:
            test.assertIsNotNone(memory_pending)
            for _ in range(2 if stalls else 0):
                previous = (owner.read_bytes, owner.write_bytes, owner.row, owner.role, owner.beat)
                owner.tick()
                test.assertEqual(previous, (owner.read_bytes, owner.write_bytes, owner.row, owner.role, owner.beat))
            previous_writes = owner.write_bytes
            e = owner.tick(response=memory_pending)
            test.assertTrue(e.response_fire)
            expected_increment = 64 if requests[-1].write else 0
            test.assertEqual(owner.write_bytes, previous_writes + expected_increment)
            memory_pending = None
        elif s.scalar_request is not None:
            r = s.scalar_request
            test.assertIsNone(memory_pending)
            test.assertIsNone(scalar_pending)
            test.assertEqual(r.op, 0)
            test.assertEqual(r.a, 0 if owner.row == 0 else 0xBF800000)
            valid = job.chunk * 64 + owner.row < job.context.tokens
            test.assertEqual(r.b, gate_words(owner.row)[0] if valid else 0)
            for _ in range(2 if stalls else 0):
                owner.tick(scalar_result=m.ScalarResult(0x7FC00000))
                test.assertEqual(owner.signals().scalar_request, r)
            value, error = simulated_add_rne(r.a, r.b)
            scalar_pending = m.ScalarResult(value, error)
            e = owner.tick(scalar_ready=True, scalar_result=scalar_pending)
            test.assertTrue(e.scalar_fire)
            test.assertFalse(e.scalar_result_fire)
            scalar_requests.append(r)
        elif s.scalar_result_ready:
            test.assertIsNotNone(scalar_pending)
            for _ in range(2 if stalls else 1):
                previous = (owner.add_results, owner.cumulative, owner.buffer)
                owner.tick()
                test.assertEqual(previous, (owner.add_results, owner.cumulative, owner.buffer))
            e = owner.tick(scalar_result=scalar_pending)
            test.assertTrue(e.scalar_result_fire)
            scalar_pending = None
        else:
            test.fail(f"unexpected active state {owner.state}")
        if owner.signals().done is not None:
            test.assertTrue(e.response_fire)
            test.assertTrue(requests[-1].write)
            test.assertEqual(owner.write_bytes, 102400)
    result = owner.signals().done
    test.assertIsNone(memory_pending)
    test.assertIsNone(scalar_pending)
    test.assertEqual(len(gate_writes), 64)
    test.assertEqual(len(scalar_requests), 64)
    test.assertEqual(sum(r.write for r in requests), 1600)
    expected_reads = 400 if job.context.tokens == 16 else 1600
    test.assertEqual(sum(not r.write for r in requests), expected_reads)
    test.assertEqual(result.read_bytes, expected_reads * 64)
    test.assertEqual((result.write_bytes, result.add_issues, result.add_results), (102400, 64, 64))
    test.assertEqual((result.receipt.tag, result.receipt.expected_generation,
                      result.receipt.head, result.receipt.chunk),
                     (job.context.tag, job.context.expected_generation, job.head, job.chunk))
    test.assertEqual((result.receipt.phase, result.receipt.output_ack_bytes,
                      result.receipt.state_ack_bytes), (1, 0, 0))
    test.assertTrue(result.stage_complete and result.local_drained and result.receipt.drained)
    test.assertEqual(result.status, 0)
    if not stalls:
        # This is the Python schedule's count, not a measured hardware bound.
        test.assertEqual(result.cycles, 2 * (expected_reads + 1600) + 3 * 64)
    test.assertEqual(len({r.address for r in requests if r.write}), 1600)
    # Holding done freezes cycles and every result field, and accepts no job,
    # memory or scalar event. Successful done.fire returns to idle next edge.
    for _ in range(3):
        e = owner.tick(job=job, committed=root, memory_ready=True, response=m.Response(0),
                       scalar_ready=True, scalar_result=m.ScalarResult(0), done_ready=False)
        test.assertEqual(owner.signals().done, result)
        test.assertFalse(any((e.job_fire, e.memory_fire, e.response_fire, e.scalar_fire, e.scalar_result_fire, e.done_fire)))
    e = owner.tick(job=job, committed=root, done_ready=True)
    test.assertTrue(e.done_fire)
    test.assertFalse(e.job_fire)
    test.assertTrue(owner.signals().job_ready)
    test.assertEqual(root, m.Committed(root.valid, root.generation, root.state))
    FULL_CASES.append({"tokens": job.context.tokens, "head": job.head, "chunk": job.chunk,
                       "read_beats": expected_reads, "write_ack_beats": 1600,
                       "simulated_add_results": 64, "stalls": stalls, "model_cycles": result.cycles})
    return owner, result


class SourceCorrespondence(unittest.TestCase):
    def test_01_existing_abis_and_policy(self):
        source = PINS.text("base", PROTO_PATH)
        self.assertEqual(bundle_fields(source, "MemoryRequest"), ["write", "address", "data", "mask", "tag"])
        self.assertEqual(bundle_fields(source, "MemoryResponse"), ["data", "tag", "error"])
        self.assertEqual([f.name for f in fields(MODEL.Response)], ["tag", "data", "error"])
        for name, code in (("Ok", 0), ("Memory", 3), ("Unsupported", 4), ("Bounds", 5),
                           ("Dependency", 6), ("Protocol", 7), ("Numerical", 8)):
            self.assertRegex(source, rf"\bval\s+{name}\s*=\s*{code}\b")
        self.assertEqual(bundle_fields(PINS.text("base", SCALAR_ABI), "GdnScalarClient"), ["request", "result", "error"])
        scalar = compact(PINS.text("base", SCALAR_SOURCE))
        for literal in ("valop=UInt(3.W)", "valAdd=0", "io.request.ready:=state===idle",
                        "io.result.valid:=state===done", "exceptionFlags(4,2).orR",
                        "exceptionFlags(1)&&op=/=ScalarOp.MulIeeeRne.U", "tininess_afterRounding"):
            self.assertIn(literal, scalar)

    def test_02_geometry_and_private_owner_source(self):
        self.assertEqual(shapes()[:4], (("gates", 64, 16), ("q", 64, 128), ("k", 64, 128), ("v", 64, 128)))
        self.assertEqual(sum(r * c * 4 for _, r, c in shapes()), 806912)
        self.assertEqual(sum(r * c * 4 for _, r, c in shapes()[:4]), 102400)
        source = PINS.text("own", OWNER_SOURCE)
        self.assertEqual(bundle_fields(source, "GdnChunkPreparedReceipt"),
                         ["tag", "expectedGeneration", "tokens", "input", "status", "writeBytes", "preparedComplete", "drained", "recurrentMode"])
        self.assertEqual(bundle_fields(source, "GdnChunkLoadPrepJob"),
                         ["context", "head", "chunk", "prepReady", "initialReady", "previousStateReady", "previousOutputReady"])
        body = compact(source)
        for literal in (
            "idle::issueRead::waitRead::issueAdd::waitAdd::issueWrite::waitWrite::finish::locked::Nil=Enum(9)",
            "io.scalar.request.bits.op:=ScalarOp.Add.U", "io.scalar.request.bits.a:=cumulative",
            "io.scalar.request.bits.b:=payload(31,0)", "io.scalar.result.ready:=state===waitAdd",
            "io.response.ready:=state===waitRead||state===waitWrite", "io.done.bits.receipt.phase:=1.U",
            "io.done.bits.receipt.outputAckBytes:=0.U", "io.done.bits.receipt.stateAckBytes:=0.U",
            "writeBytes===phaseBytes.U&&addRequests===64.U&&addResults===64.U",
            "valfiniteBeat=(0until16).map", "r.data(511,64)===0.U",
            "payload:=Cat(0.U(448.W),payload(63,32),io.scalar.result.bits)",
            "when(io.scalar.error||!finite(io.scalar.result.bits))", "fail(Status.Numerical.U)",
            "state:=Mux(status===Status.Ok.U,idle,locked)", "base.pad(66)+size>(BigInt(1)<<AddressBits).U",
            "p.preparedComplete&&p.drained&&!p.recurrentMode", "previousStateReady&&previousOutputReady",
            "j.previousOutputReady.outputAckBytes===16384.U"):
            self.assertIn(literal, body)
        self.assertLess(body.index("when(r.tag=/=Cat(tag,sequence))"), body.index(".elsewhen(r.error)"))
        self.assertNotIn("Module(new", body)
        for forbidden in ("SyncReadMem", "Mem(", "stateCommitted", "generationAdvanced", "newGeneration"):
            self.assertNotIn(forbidden, body)

    def test_03_no_original_model_import_or_native_execution(self):
        source = PINS.text("own", "loadprep_model.py")
        self.assertNotIn("import transfer_model", source)
        self.assertNotIn("simulated_add_rne", source)
        for pattern in (r"\bsubprocess\b", r"\bctypes\b", r"\bfloat\(", r"\bstruct\b", r"\bsocket\b"):
            self.assertIsNone(re.search(pattern, source))
        self.assertNotIn("state_committed", MODEL.RESULT_FIELDS)
        for event, args in (("subprocess.Popen", ()), ("ctypes.dlopen", ()),
                            ("socket.connect", ()), ("open", ("x", "wb", 0)),
                            ("open", ("x", None, os.O_CREAT)), ("os.remove", ())):
            with self.assertRaises(RuntimeError):
                readonly_audit(event, args)
        readonly_audit("open", ("x", "rb", 0))


class SimulatedScalarControls(unittest.TestCase):
    def test_hand_derived_binary32_vectors_only(self):
        vectors = (
            (0, 0, 0), (0x80000000, 0, 0), (0x80000000, 0x80000000, 0x80000000),
            (0x3F800000, 0xBF800000, 0), (0, 0x80000001, 0x80000001),
            (1, 1, 2), (0x80000001, 0x80000001, 0x80000002),
            (0x007FFFFF, 1, 0x00800000), (0x00800000, 0x807FFFFF, 1),
            (0x3F800000, 0x33800000, 0x3F800000),
            (0x3F800001, 0x33800000, 0x3F800002),
            (0xBF800000, 0xB3800000, 0xBF800000),
            (0xBF800000, 0xB4000000, 0xBF800001),
        )
        for a, b, result in vectors:
            self.assertEqual(simulated_add_rne(a, b), (result, False))
        self.assertEqual(simulated_add_rne(0xFF7FFFFF, 0xFF7FFFFF), (0xFF800000, True))
        cumulative = 0
        prefixes = []
        for g in (0xBF800000, 0xB3800000, 0xB3800000):
            cumulative, error = simulated_add_rne(cumulative, g)
            self.assertFalse(error)
            prefixes.append(cumulative)
        self.assertEqual(prefixes, [0xBF800000] * 3)
        tiny_pair, _ = simulated_add_rne(0xB3800000, 0xB3800000)
        self.assertEqual(simulated_add_rne(0xBF800000, tiny_pair), (0xBF800001, False))
        with self.assertRaises(ValueError):
            simulated_add_rne(0x7F800000, 0)


class ModelControls(unittest.TestCase):
    def begin(self, job=None, root=None):
        if job is None:
            job, root = make_job()
        owner = MODEL.Owner()
        event = owner.tick(job=job, committed=root)
        self.assertTrue(event.job_fire)
        return owner

    def read_gate(self, data=pack((0xBF800000, 0))):
        owner = self.begin()
        request = owner.signals().memory_request
        owner.tick(memory_ready=True)
        owner.tick(response=MODEL.Response(request.tag, data))
        return owner

    def assert_failure(self, owner, status, read_bytes=0, write_bytes=0, outstanding=False):
        m = MODEL
        result = owner.signals().done
        self.assertIsNotNone(result)
        self.assertEqual((result.status, result.read_bytes, result.write_bytes), (status, read_bytes, write_bytes))
        self.assertFalse(result.stage_complete or result.local_drained or result.receipt.drained)
        self.assertEqual(owner.outstanding, outstanding)
        self.assertTrue(owner.signals().reset_required)
        for _ in range(3):
            owner.tick(response=m.Response(0), scalar_result=m.ScalarResult(0), memory_ready=True, scalar_ready=True)
            self.assertEqual(owner.signals().done, result)
        owner.tick(done_ready=True)
        self.assertEqual(owner.state, owner.LOCKED)
        job, root = make_job()
        e = owner.tick(job=job, committed=root)
        self.assertFalse(e.job_fire)
        self.assertIsNone(owner.signals().memory_request)
        owner.reset()
        self.assertTrue(owner.signals().job_ready)
        self.assertFalse(owner.signals().reset_required)

    def test_full_m16_heads_and_m128_both_chunks(self):
        for tokens, head, chunk in ((16, 0, 0), (16, 15, 0), (128, 0, 0), (128, 15, 1)):
            with self.subTest(tokens=tokens, head=head, chunk=chunk):
                job, root = make_job(tokens, head, chunk, cold=(tokens == 16 and head == 0))
                owner, _ = full_run(self, job, root, stalls=(head == 15))
                e = owner.tick(job=job, committed=root)
                self.assertTrue(e.job_fire)
                self.assertEqual((owner.row, owner.cumulative, owner.add_issues, owner.write_bytes), (0, 0, 0, 0))
                self.assertFalse(owner.outstanding or owner.scalar_outstanding)

    def test_admission_root_geometry_policy_and_no_pending(self):
        m = MODEL
        job, root = make_job()
        cases = [
            (job, replace(root, generation=6), m.Status.DEPENDENCY),
            (job, replace(root, valid=False), m.Status.DEPENDENCY),
            (job, replace(root, state=root.state + 64), m.Status.DEPENDENCY),
            (repack_context(job, expected_generation=0), m.Committed(True, 0, root.state), m.Status.DEPENDENCY),
            (repack_context(job, cold=True), root, m.Status.DEPENDENCY),
            (replace(job, head=16), root, m.Status.BOUNDS),
            (replace(job, head=65535), root, m.Status.BOUNDS),
            (replace(job, chunk=1), root, m.Status.BOUNDS),
            (replace(job, chunk=65535), root, m.Status.BOUNDS),
            (repack_context(job, tokens=1), root, m.Status.BOUNDS),
            (repack_context(job, tokens=64), root, m.Status.BOUNDS),
            (repack_context(job, tokens=0), root, m.Status.BOUNDS),
            (repack_context(job, expected_generation=0xFFFFFFFF), replace(root, generation=0xFFFFFFFF), m.Status.BOUNDS),
            (repack_context(job, vector_policy=1), root, m.Status.UNSUPPORTED),
        ]
        cold, cold_root = make_job(cold=True)
        cases += [(cold, replace(cold_root, valid=True), m.Status.DEPENDENCY)]
        for bad_job, bad_root, status in cases:
            with self.subTest(status=status, job=bad_job):
                owner = m.Owner()
                e = owner.tick(job=bad_job, committed=bad_root, memory_ready=True,
                               response=m.Response(0), scalar_ready=True, scalar_result=m.ScalarResult(0))
                self.assertTrue(e.job_fire)
                self.assertFalse(e.memory_fire or e.response_fire or e.scalar_fire or e.scalar_result_fire)
                self.assertFalse(owner.outstanding or owner.scalar_outstanding)
                self.assert_failure(owner, status)
        # Root mismatch has priority over every lower gate.
        owner = self.begin(repack_context(job, vector_policy=1, input=1), replace(root, generation=6))
        self.assert_failure(owner, m.Status.DEPENDENCY)
        # Valid admission also cannot consume pre-existing unsolicited returns.
        owner = m.Owner()
        e = owner.tick(job=job, committed=root, response=m.Response(0), scalar_result=m.ScalarResult(0))
        self.assertFalse(e.response_fire or e.scalar_result_fire)
        self.assertEqual((owner.read_bytes, owner.add_results), (0, 0))
        self.assertFalse(owner.outstanding or owner.scalar_outstanding)

    def test_all_prepared_receipt_fields(self):
        job, root = make_job()
        changes = {"tag": 1, "expected_generation": 8, "tokens": 128, "input": job.context.input + 64,
                   "status": 3, "write_bytes": job.prep_ready.write_bytes - 64,
                   "prepared_complete": False, "drained": False, "recurrent_mode": True}
        for field, value in changes.items():
            with self.subTest(field=field):
                bad = replace(job, prep_ready=replace(job.prep_ready, **{field: value}))
                self.assert_failure(self.begin(bad, root), MODEL.Status.DEPENDENCY)
        # Overcounting is not accepted either.
        bad = replace(job, prep_ready=replace(job.prep_ready, write_bytes=job.prep_ready.write_bytes + 64))
        self.assert_failure(self.begin(bad, root), MODEL.Status.DEPENDENCY)

    def test_predecessors_exact_and_chunk_specific(self):
        m = MODEL
        for chunk, names in ((0, ("initial_ready",)), (1, ("previous_state_ready", "previous_output_ready"))):
            job, root = make_job(128, 15, chunk)
            for name in names:
                receipt = getattr(job, name)
                changes = {"tag": 1, "expected_generation": 6, "head": 0, "chunk": 1,
                           "phase": 3, "status": 3, "scratch_ack_bytes": receipt.scratch_ack_bytes + 64,
                           "output_ack_bytes": receipt.output_ack_bytes + 64,
                           "state_ack_bytes": 64, "drained": False}
                for field, value in changes.items():
                    bad = replace(job, **{name: replace(receipt, **{field: value})})
                    self.assert_failure(self.begin(bad, root), m.Status.DEPENDENCY)
            # Inactive predecessor fields are not spuriously required.
            if chunk == 0:
                good = replace(job, previous_state_ready=m.Receipt(), previous_output_ready=m.Receipt())
            else:
                good = replace(job, initial_ready=m.Receipt())
            self.assertEqual(m.admission_status(good, root), m.Status.OK)
        job, root = make_job(128, 0, 1)
        fake_state_out = replace(job.previous_state_ready, scratch_ack_bytes=0, state_ack_bytes=65536)
        self.assert_failure(self.begin(replace(job, previous_state_ready=fake_state_out), root), m.Status.DEPENDENCY)

    def test_all_full_spans_alignment_alias_end56_and_wrap(self):
        m = MODEL
        job, root = make_job(128, 15, 1)
        names = ("input", "state_in", "state_out", "output", "scratch")
        for index, name in enumerate(names):
            for base in (getattr(job.context, name) + 1, (1 << 56), (1 << 64) - 64):
                bad = repack_context(job, **{name: base})
                use_root = replace(root, state=base) if name == "state_in" else root
                self.assert_failure(self.begin(bad, use_root), m.Status.BOUNDS)
            # Exact end == 2**56 is valid; crossing it by one beat is not.
            size = m.spans(job.context)[index][1]
            end_base = (1 << 56) - size
            good = repack_context(job, **{name: end_base})
            use_root = replace(root, state=end_base) if name == "state_in" else root
            self.assertEqual(m.admission_status(good, use_root), m.Status.OK)
            bad = repack_context(job, **{name: end_base + 64})
            use_root = replace(root, state=end_base + 64) if name == "state_in" else root
            self.assert_failure(self.begin(bad, use_root), m.Status.BOUNDS)
        # Every pair of full allocations, including untouched state/output.
        for i, name in enumerate(names):
            for other in names[:i]:
                base = getattr(job.context, other)
                bad = repack_context(job, **{name: base})
                use_root = replace(root, state=base) if name == "state_in" else root
                self.assert_failure(self.begin(bad, use_root), m.Status.BOUNDS)
        # Touching ends are disjoint; overlap only at the far end still fails.
        good = repack_context(job, state_out=job.context.state_in + 1048576)
        self.assertEqual(m.admission_status(good, root), m.Status.OK)
        bad = repack_context(job, state_out=job.context.state_in + 1048576 - 64)
        self.assert_failure(self.begin(bad, root), m.Status.BOUNDS)

    def test_gate_finiteness_domain_padding_and_signed_zero(self):
        m = MODEL
        for lane in range(16):
            for word in (0x7F800000, 0xFF800000, 0x7FC12345, 0x7F800001):
                words = [0] * 16
                words[lane] = word
                self.assert_failure(self.read_gate(pack(words)), m.Status.NUMERICAL, read_bytes=64)
        for g, beta, lane, word in ((1, 0, 2, 0), (0x3F800000, 0, 2, 0),
                                    (0, 0x80000001, 2, 0), (0, 0x3F800001, 2, 0),
                                    (0, 0, 2, 1), (0, 0, 15, 0x80000000)):
            words = [g, beta] + [0] * 14
            words[lane] = word
            self.assert_failure(self.read_gate(pack(words)), m.Status.NUMERICAL, read_bytes=64)
        for g in (0, 0x80000000, 0x80000001, 0xFF7FFFFF):
            for beta in (0, 0x80000000, 1, 0x3F800000):
                owner = self.read_gate(pack((g, beta)))
                self.assertEqual(owner.state, owner.ISSUE_ADD)
                self.assertEqual(owner.signals().scalar_request.b, g)

    def test_every_qkv_lane_finite_validation(self):
        m = MODEL
        for lane in range(16):
            owner = self.read_gate()
            owner.tick(scalar_ready=True)
            owner.tick(scalar_result=m.ScalarResult(0xBF800000))
            gate = owner.signals().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.Response(gate.tag))
            q = owner.signals().memory_request
            self.assertEqual(owner.role, 1)
            owner.tick(memory_ready=True)
            owner.tick(response=m.Response(q.tag, 0x7FC00000 << (32 * lane)))
            self.assert_failure(owner, m.Status.NUMERICAL, read_bytes=128, write_bytes=64)

    def test_memory_wrong_tag_error_precedence_and_partial_writes(self):
        m = MODEL
        for wrong, error, status in ((True, False, m.Status.PROTOCOL), (True, True, m.Status.PROTOCOL),
                                     (False, True, m.Status.MEMORY)):
            owner = self.begin()
            request = owner.signals().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.Response(request.tag ^ int(wrong), error=error))
            self.assert_failure(owner, status, outstanding=wrong)
        # Fail second write after gate ACK: byte count remains exactly one
        # acknowledged beat, never sent-write count and never rolled back.
        for wrong, error, status in ((True, True, m.Status.PROTOCOL), (False, True, m.Status.MEMORY)):
            owner = self.read_gate()
            owner.tick(scalar_ready=True)
            owner.tick(scalar_result=m.ScalarResult(0xBF800000))
            gate = owner.signals().memory_request
            owner.tick(memory_ready=True)
            self.assertEqual(owner.write_bytes, 0)
            owner.tick(response=m.Response(gate.tag))
            q = owner.signals().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.Response(q.tag, 1))
            write = owner.signals().memory_request
            owner.tick(memory_ready=True)
            self.assertEqual(owner.write_bytes, 64)
            owner.tick(response=m.Response(write.tag ^ int(wrong), error=error))
            self.assert_failure(owner, status, read_bytes=128, write_bytes=64, outstanding=wrong)

    def test_scalar_injected_error_nonfinite_exact_subnormal_and_overflow(self):
        m = MODEL
        # This finite error is an INJECTED service error. It is NOT a natural
        # underflow example for binary32 Add, which cannot produce tiny-inexact.
        for result in (m.ScalarResult(1, True), m.ScalarResult(0x7F800000),
                       m.ScalarResult(0xFF800000), m.ScalarResult(0x7FC00000)):
            owner = self.read_gate()
            owner.tick(scalar_ready=True)
            owner.tick(scalar_result=result)
            self.assertEqual((owner.add_issues, owner.add_results), (1, 0))
            self.assertFalse(owner.scalar_outstanding)
            self.assert_failure(owner, m.Status.NUMERICAL, read_bytes=64)
        for g, result in ((0x80000001, 0x80000001), (0x80000000, 0), (0, 0)):
            owner = self.read_gate(pack((g, 0x80000000)))
            request = owner.signals().scalar_request
            self.assertEqual(simulated_add_rne(request.a, request.b), (result, False))
            owner.tick(scalar_ready=True)
            owner.tick(scalar_result=m.ScalarResult(result))
            self.assertEqual(owner.signals().memory_request.data, pack((result, 0x80000000)))
            self.assertEqual(owner.add_results, 1)
        # The service can return -0 (e.g. an injected opaque finite response);
        # owner must preserve it, not reinterpret exponent zero as underflow.
        owner = self.read_gate(pack((0x80000000, 0)))
        owner.tick(scalar_ready=True)
        owner.tick(scalar_result=m.ScalarResult(0x80000000))
        self.assertEqual(owner.signals().memory_request.data, 0x80000000)
        # Genuine simulated finite Add overflow: -max + -max. Feed through
        # a two-row transaction sequence, with all intervening Q/K/V ACKs.
        owner = self.read_gate(pack((0xFF7FFFFF, 0)))
        owner.tick(scalar_ready=True)
        owner.tick(scalar_result=m.ScalarResult(0xFF7FFFFF))
        count = 0
        while not (owner.row == 1 and owner.state == owner.ISSUE_ADD):
            count += 1
            self.assertLess(count, 110)
            s = owner.signals()
            if s.memory_request is not None:
                request = s.memory_request
                data = pack((0xFF7FFFFF, 0)) if owner.row == 1 else 0
                owner.tick(memory_ready=True)
                owner.tick(response=m.Response(request.tag, data))
            else:
                self.fail(f"unexpected overflow preparation state {owner.state}")
        request = owner.signals().scalar_request
        result, error = simulated_add_rne(request.a, request.b)
        self.assertEqual((result, error), (0xFF800000, True))
        owner.tick(scalar_ready=True)
        owner.tick(scalar_result=m.ScalarResult(result, error))
        self.assert_failure(owner, m.Status.NUMERICAL, read_bytes=26 * 64, write_bytes=25 * 64)

    def test_unsigned_abi_and_types(self):
        m = MODEL
        job, _ = make_job()
        for field, value in (("tag", -1), ("tokens", 65536), ("expected_generation", 1 << 32),
                             ("vector_policy", 2), ("input", 1 << 64), ("cold", 1)):
            with self.assertRaises(ValueError):
                replace(job.context, **{field: value})
        for factory in (lambda: replace(job, head=-1), lambda: replace(job, chunk=65536),
                        lambda: m.Response(1 << 64), lambda: m.Response(0, 1 << 512),
                        lambda: m.ScalarRequest(8, 0, 0), lambda: m.ScalarResult(1 << 32),
                        lambda: m.ScalarResult(0, 1)):
            with self.assertRaises(ValueError):
                factory()


def main():
    global MODEL, PINS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 12), "only the separately reviewed Python 3.12 scope is admitted")
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
            "invoke with -I -S -B")
    sys.addaudithook(readonly_audit)
    started = time.monotonic()
    try:
        PINS = PinSet(args.base, args.contract)
    except Exception as error:
        print(json.dumps({"status": "INPUT_PIN_FAILURE", "error": str(error)}), flush=True)
        return 2
    result, problem, after_ok = None, None, False
    try:
        module = types.ModuleType("pinned_chunk_loadprep_model")
        module.__file__ = str(HERE / "loadprep_model.py")
        sys.modules[module.__name__] = module
        # Exact verified raw source bytes, not a path import or cached pyc.
        code = compile(PINS.cache[("own", "loadprep_model.py")], module.__file__, "exec")
        exec(code, module.__dict__)
        MODEL = module
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                                   for cls in (SourceCorrespondence, SimulatedScalarControls, ModelControls))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    except Exception as error:
        problem = str(error)
    finally:
        try:
            PINS.verify_after()
            after_ok = True
        except Exception as error:
            problem = f"AFTER_PIN_FAILURE: {error}"
    success = problem is None and result is not None and result.wasSuccessful()
    print(json.dumps({
        "status": "PASS_PYTHON_PROTOCOL_AND_SIMULATED_SCALAR_ONLY" if success else "FAIL",
        "executed_scala": False, "executed_chisel": False, "executed_rtl": False,
        "executed_native_model": False, "independent_fp32_dut_validation": False,
        "scalar_response_service": "SIMULATED_EXACT_INTEGER_BINARY32_RNE_ADD",
        "tests": 0 if result is None else result.testsRun,
        "full_cases": FULL_CASES, "pins_before_and_after": after_ok,
        "pinned_files": len(PINS.entries), "seconds": round(time.monotonic() - started, 6),
        "error": problem,
        "limits": "No compile/elaboration, real transport/receipt provenance, FP32 DUT, publication, complete chunk/block, or utilization proof.",
    }, sort_keys=True), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
