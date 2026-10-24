#!/usr/bin/env python3
"""Bounded pure-stdlib controls, NOT Scala/Chisel/RTL/AXI execution.

Run only after independent source review and separate execution admission:
  python3 -B tests.py --base FIXED_REPOSITORY --contract CONTRACT_1245_PACKAGE

The Python state machine consumes explicit, synthetic request/response events.
Source-literal checks are correspondence witnesses, not a compiler or a proof
of equivalent Chisel handshake behavior. Full-beat transport, trusted receipt
provenance, stable source/root, and joint transport reset remain integration
obligations. No new publication, arithmetic, DMA, SRAM, or Host claim is made.

Both external inputs and this source package are verified before/after controls.
The harness imports only stdlib and the verified local transfer_model.py. It
does not import or run the original numerical models. No fixtures are written.
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
PROTO_PATH = "chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Protocol.scala"
CONTRACT_PROTOCOL = "source/GdnChunkProtocol.scala"
CONTRACT_PLAN = "source/GdnChunkAddressPlan.scala"
OWNER_SOURCE = "source/GdnChunkStateTransferOwner.scala"
MODEL = PINS = None
FULL_TRANSFERS = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def readonly_audit(event, args):
    """Fail closed on file writes, external execution, or network/native loads."""
    if event in ("ctypes.dlopen", "subprocess.Popen", "os.system", "os.posix_spawn",
                 "os.fork", "os.exec", "os.remove", "os.rename", "os.rmdir",
                 "os.mkdir", "os.unlink", "os.symlink", "os.link", "os.truncate"):
        raise RuntimeError("contract controls forbid native/process/filesystem changes")
    if event.startswith("socket."):
        raise RuntimeError("contract controls forbid network")
    if event == "open":
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if ((isinstance(mode, str) and any(char in mode for char in "wax+"))
                or (isinstance(flags, int) and flags & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))):
            raise RuntimeError("contract controls are read-only")


def safe_path(root, relative):
    require(isinstance(relative, str) and relative, "missing pin relative path")
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "unsafe pin path")
    path = root / rel
    require(path.is_file() and not path.is_symlink(), "pin must be a regular file")
    require(path.resolve().is_relative_to(root.resolve()), "pin escapes its root")
    return path


def read_small(path, expected=None):
    before = path.stat()
    require(before.st_size <= 2 * 1024 * 1024, "input exceeds small-control file bound")
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size,
                             stat.st_mtime_ns, stat.st_ctime_ns)
    require(identity(before) == identity(after), "file changed during read")
    digest = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if expected is not None:
        require(digest == {"bytes": expected["bytes"], "sha256": expected["sha256"]},
                f"pin mismatch: {path.name}")
    return raw, digest


class PinSet:
    """Pins are read-only evidence, never refreshed to fit current contents."""

    def __init__(self, base, contract):
        self.roots = {"base": base.resolve(), "contract": contract.resolve()}
        pins_raw, pins_digest = read_small(HERE / "INPUT_PINS.json")
        manifest_raw, manifest_digest = read_small(HERE / "SOURCE_MANIFEST.json")
        external = json.loads(pins_raw)
        manifest = json.loads(manifest_raw)
        require(isinstance(external.get("files"), dict) and external["files"],
                "INPUT_PINS files mapping is required")
        require(isinstance(manifest.get("files"), dict) and manifest["files"],
                "SOURCE_MANIFEST files mapping is required")
        own = manifest["files"]
        require({"transfer_model.py", "tests.py", OWNER_SOURCE,
                 "INTERFACE_PROPOSAL.md", "INPUT_PINS.json"} <= set(own),
                "source manifest omits a required implementation/input file")
        require("SOURCE_MANIFEST.json" not in own, "self-referential manifest")
        self.entries = []
        self.cache = {}
        self.descriptors = [
            (HERE / "INPUT_PINS.json", pins_digest),
            (HERE / "SOURCE_MANIFEST.json", manifest_digest),
        ]
        for label, spec in external["files"].items():
            require(spec.get("role") in self.roots, f"unknown role: {label}")
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
                "input set exceeds small-control total bound")
        required = {( "base", PROTO_PATH), ("contract", CONTRACT_PROTOCOL),
                    ("contract", CONTRACT_PLAN)}
        require(required <= set(self.cache), "missing required source correspondence pin")

    def text(self, role, relative):
        return self.cache[(role, relative)].decode("utf-8")

    def verify_after(self):
        for path, digest in self.descriptors + self.entries:
            read_small(path, digest)


def strip_comments(source):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


def compact(source):
    return re.sub(r"\s+", "", strip_comments(source))


def bundle_fields(source, name):
    body = source.split(f"class {name} extends Bundle {{", 1)[1].split("}", 1)[0]
    return re.findall(r"\bval\s+(\w+)\s*=", strip_comments(body))


@lru_cache(maxsize=1)
def shape_rows():
    source = PINS.text("contract", CONTRACT_PLAN)
    vector = source.split("val Shapes: Vector[Shape] = Vector(", 1)[1].split(
        "require(Shapes", 1)[0]
    return tuple((name, int(rows), int(cols)) for name, rows, cols in re.findall(
        r'Shape\("([a-z_]+)",\s*(\d+),\s*(\d+)\)', vector))


def make_job(tokens=16, head=0, path="warm", tag=0x87654321):
    m = MODEL
    cold = path == "cold"
    context = m.Context(tag, tokens, cold, 0 if cold else 7, 0,
                        0x100000, 0x800000, 0xA00000, 0xC00000, 0x1000000)
    committed = m.Committed(not cold, context.expected_generation,
                            context.state_in if not cold else 0)
    operation = m.Operation.EXPORT_FINAL if path == "export" else m.Operation.INITIALIZE
    chunk = 0 if tokens == 16 else 1
    next_ready = m.Receipt(tag, context.expected_generation, head, chunk, 16,
                           m.Status.OK, 65536, 0, 0, True)
    output_ready = m.Receipt(tag, context.expected_generation, head, chunk, 17,
                             m.Status.OK, 0, 4096 if tokens == 16 else 16384, 0, True)
    return m.Job(context, head, operation, next_ready, output_ready), committed


def payload(beat, head=0, tokens=16):
    # Explicit NaNs, infinities, signed zeros, subnormals, and ordinary FP32 bits.
    # No conversion to float is performed; payload equality is bitwise.
    special = (0x00000000, 0x80000000, 0x7F800000, 0xFF800000,
               0x7FC12345, 0x7F800001, 0xFFC54321, 0x00000001,
               0x80000001, 0x007FFFFF, 0x3F800000, 0xBF800000)
    words = [special[(lane + beat) % len(special)] for lane in range(12)]
    words += [((beat * 0x1020305) ^ (head << 24) ^ (tokens << 8)
               ^ (lane * 0x9E3779B9)) & 0xFFFFFFFF for lane in range(4)]
    return sum(word << (32 * lane) for lane, word in enumerate(words))


def oracle_addresses(job, beat):
    """Formula from PINNED declarative Scala shapes, not model constants."""
    shapes = shape_rows()
    chunk_bytes = sum(rows * cols * 4 for _, rows, cols in shapes)
    next_index = [name for name, _, _ in shapes].index("next_state")
    next_offset = sum(rows * cols * 4 for _, rows, cols in shapes[:next_index])
    chunks = (job.context.tokens + 63) // 64
    initial = job.context.scratch + job.head * (128 * 128 * 4 + chunks * chunk_bytes)
    last = initial + 128 * 128 * 4 + (chunks - 1) * chunk_bytes + next_offset
    offset = beat * 64
    if job.operation == MODEL.Operation.EXPORT_FINAL:
        return last + offset, job.context.state_out + job.head * 128 * 128 * 4 + offset
    return job.context.state_in + job.head * 128 * 128 * 4 + offset, initial + offset


class SourceCorrespondence(unittest.TestCase):
    def test_01_original_memory_abi_and_status_ids(self):
        source = PINS.text("base", PROTO_PATH)
        self.assertEqual(bundle_fields(source, "MemoryRequest"),
                         ["write", "address", "data", "mask", "tag"])
        self.assertEqual(bundle_fields(source, "MemoryResponse"), ["data", "tag", "error"])
        body = compact(source)
        for literal in ("valdata=UInt(512.W)", "valaddress=UInt(64.W)",
                        "valmask=UInt(64.W)", "valtag=UInt(64.W)"):
            self.assertIn(literal, body)
        for name, code in (("Ok", 0), ("Memory", 3), ("Unsupported", 4),
                           ("Bounds", 5), ("Dependency", 6), ("Protocol", 7)):
            self.assertRegex(source, rf"\bval\s+{name}\s*=\s*{code}\b")
        self.assertEqual([field.name for field in fields(MODEL.Response)],
                         ["tag", "data", "error"])

    def test_02_geometry_and_address_formulas(self):
        protocol = PINS.text("contract", CONTRACT_PROTOCOL)
        constants = {name: int(value) for name, value in re.findall(
            r"val (\w+) = (\d+)\b", protocol)}
        expected = dict(ChunkRows=64, Heads=16, KeyDim=128, ValueDim=128,
                        BeatBytes=64, PreparedRowBytes=25600, StateBytes=1048576,
                        OutputRowBytes=4096, AddressBits=56)
        self.assertEqual({key: constants[key] for key in expected}, expected)
        self.assertIn("Set(16, 128)", protocol)
        shapes = shape_rows()
        self.assertEqual(len(shapes), 24)
        self.assertEqual(shapes[-1], ("next_state", 128, 128))
        per_chunk = sum(rows * cols * 4 for _, rows, cols in shapes)
        self.assertEqual(per_chunk, 806912)
        self.assertEqual(sum(rows * cols * 4 for _, rows, cols in shapes[:-1]), 741376)
        for tokens, chunks in ((16, 1), (128, 2)):
            self.assertEqual(MODEL.HEAD_STRIDE[tokens], 65536 + chunks * per_chunk)
            self.assertEqual(MODEL.FINAL_NEXT_OFFSET[tokens], chunks * per_chunk)
        source = compact(PINS.text("contract", CONTRACT_PLAN))
        for literal in (
            "base+bytes<=AddressLimit", "spans(i).disjoint(spans(j))",
            "committed.generation==expectedGeneration",
            "committed.state.contains(bases.stateIn)", "expectedGeneration<LastGeneration",
            "bases.scratch+head*headScratchBytes",
            "initial(head).span.end+chunk*PerHeadChunkBytes+offset",
        ):
            self.assertIn(literal, source)

    def test_03_private_types_and_no_added_compute_or_publication(self):
        source = PINS.text("own", OWNER_SOURCE)
        self.assertEqual(bundle_fields(source, "GdnChunkStateTransferJob"),
                         ["context", "head", "operation", "nextStateReady", "outputReady"])
        self.assertEqual(bundle_fields(source, "GdnChunkStateTransferResult"), [
            "tag", "expectedGeneration", "head", "operation", "status", "readBytes",
            "writeBytes", "cycles", "transferComplete", "localDrained"])
        self.assertEqual(bundle_fields(source, "GdnChunkStateTransferPort"),
                         ["job", "committed", "memory", "response", "done", "resetRequired"])
        code = strip_comments(source)
        self.assertEqual(len(re.findall(r"extends\s+Module\b", code)), 1)
        self.assertNotRegex(code, r"\b(?:Module|Mem|SyncReadMem)\s*\(")
        self.assertEqual(len(re.findall(r"RegInit\(0\.U\(512\.W\)\)", code)), 1)
        self.assertNotRegex(code, r"\b(?:stateCommitted|historyCommitted|generationAdvanced|newGeneration)\b")
        self.assertEqual(MODEL.RESULT_FIELDS, (
            "tag", "expected_generation", "head", "operation", "status", "read_bytes",
            "write_bytes", "cycles", "transfer_complete", "local_drained"))

    def test_04_source_admission_and_receipt_guards(self):
        source = compact(PINS.text("own", OWNER_SOURCE))
        for literal in (
            "require(nextIndex==23&&stateBytes==65536&&chunkBytes==806912)",
            "require(nextOffset==741376&&stride16==872448&&stride128==1679360)",
            "require(next16==806912&&next128==1613824)",
            "base(5,0)=/=0.U||size===0.U||base.pad(66)+size>(BigInt(1)<<AddressBits).U",
            "spans.indices.flatMap(i=>(0untili).map(k=>",
            "c.expectedGeneration=/=io.committed.generation",
            "c.expectedGeneration===\"hffffffff\".U",
            "r.tag===c.tag&&r.expectedGeneration===c.expectedGeneration",
            "r.head.pad(16)===j.head&&r.chunk===Mux(is128,1.U,0.U)",
            "r.phase===phase.U&&r.status===Status.Ok.U&&r.drained",
            "sameReceipt(j.nextStateReady,16)", "sameReceipt(j.outputReady,17)",
            "j.nextStateReady.scratchAckBytes===stateBytes.U",
            "j.nextStateReady.outputAckBytes===0.U&&j.nextStateReady.stateAckBytes===0.U",
            "j.outputReady.outputAckBytes===Mux(is128,16384.U,4096.U)",
            "j.outputReady.scratchAckBytes===0.U&&j.outputReady.stateAckBytes===0.U",
        ):
            self.assertIn(literal, source)
        root = source.index("when(rootBad)")
        bounds = source.index("fail(Status.Bounds.U)", root)
        unsupported = source.index("fail(Status.Unsupported.U)", bounds)
        dependency = source.index("!nextReady||!outputReady", unsupported)
        self.assertLess(root, bounds)
        self.assertLess(bounds, unsupported)
        self.assertLess(unsupported, dependency)

    def test_05_source_handshake_and_terminal_guards(self):
        source = compact(PINS.text("own", OWNER_SOURCE))
        for literal in (
            "idle::issueRead::waitRead::issueWrite::waitWrite::finish::locked::Nil=Enum(7)",
            "io.job.ready:=state===idle",
            "io.memory.valid:=state===issueRead||state===issueWrite",
            "io.response.ready:=state===waitRead||state===waitWrite",
            "io.memory.bits.tag:=Cat(tag,sequence)",
            "io.memory.bits.mask:=Mux(state===issueWrite,Fill(64,1.U(1.W)),0.U(64.W))",
            "when(io.memory.fire){outstanding:=true.Bstate:=Mux(state===issueRead,waitRead,waitWrite)}",
            "when(r.tag=/=Cat(tag,sequence)){fail(Status.Protocol.U)}",
            ".elsewhen(r.error){outstanding:=false.B;fail(Status.Memory.U)}",
            "when(state===waitRead){payload:=r.datareadBytes:=readBytes+BeatBytes.Ustate:=issueWrite}",
            "writeBytes:=writeBytes+BeatBytes.U",
            "when(beat===(stateBytes/BeatBytes-1).U){state:=finish}",
            "when(state=/=idle&&state=/=finish&&state=/=locked){cycles:=cycles+1.U}",
            "io.done.bits.transferComplete:=state===finish&&status===Status.Ok.U&&writeBytes===stateBytes.U&&!outstanding",
            "io.done.bits.localDrained:=state===finish&&status===Status.Ok.U&&!outstanding",
            "when(io.done.fire){state:=Mux(status===Status.Ok.U,idle,locked)}",
        ):
            self.assertIn(literal, source)
        response = source.split("when(io.response.fire)", 1)[1]
        self.assertLess(response.index("r.tag=/="), response.index("r.error"))


class ModelControls(unittest.TestCase):
    def admit(self, job, committed):
        owner = MODEL.Owner()
        event = owner.tick(job=job, committed=committed, memory_ready=True)
        self.assertTrue(event.job_fire)
        self.assertFalse(event.memory_fire)
        self.assertFalse(event.response_fire)
        self.assertEqual(owner.cycles, 0)
        self.assertIsNone(owner.signals().done)
        return owner

    def counter_snapshot(self, owner):
        return (owner.beat, owner.sequence, owner.read_bytes, owner.write_bytes,
                owner.outstanding, owner.buffer)

    def issue(self, owner, request, stalls=0, offered_data=0):
        before = self.counter_snapshot(owner)
        self.assertEqual(owner.signals().memory_request, request)
        self.assertFalse(owner.outstanding)
        for _ in range(stalls):
            event = owner.tick(response=MODEL.Response(request.tag, offered_data))
            self.assertFalse(event.memory_fire)
            self.assertFalse(event.response_fire)
            self.assertEqual(owner.signals().memory_request, request)
            self.assertEqual(self.counter_snapshot(owner), before)
        event = owner.tick(memory_ready=True, response=MODEL.Response(request.tag, offered_data))
        self.assertTrue(event.memory_fire)
        self.assertFalse(event.response_fire, "cannot consume response on issue cycle")
        self.assertTrue(owner.outstanding)
        self.assertIsNone(owner.signals().memory_request)
        self.assertTrue(owner.signals().response_ready)
        self.assertEqual(owner.read_bytes, before[2])
        self.assertEqual(owner.write_bytes, before[3])
        self.assertEqual(owner.beat, before[0])
        return request

    def wait_response(self, owner, count):
        before = self.counter_snapshot(owner)
        for _ in range(count):
            event = owner.tick(memory_ready=True, done_ready=True)
            self.assertFalse(event.memory_fire)
            self.assertFalse(event.done_fire)
            self.assertIsNone(owner.signals().done)
            self.assertEqual(self.counter_snapshot(owner), before)

    def one_beat(self, owner, job, beat, *, stalls=0, waits=0, final_waits=0):
        m = MODEL
        source, target = oracle_addresses(job, beat)
        cold = job.context.cold and job.operation == m.Operation.INITIALIZE
        data = 0 if cold else payload(beat, job.head, job.context.tokens)
        self.assertEqual(owner.beat, beat)
        self.assertEqual(owner.write_bytes, beat * 64)
        if not cold:
            sequence = beat * 2
            request = m.Request(source, 0, 0, (job.context.tag << 32) | sequence, False)
            self.issue(owner, request, stalls, data ^ 0xABCD)
            self.wait_response(owner, waits)
            old_write = owner.write_bytes
            event = owner.tick(response=m.Response(request.tag, data), memory_ready=True)
            self.assertTrue(event.response_fire)
            self.assertFalse(event.memory_fire)
            self.assertEqual(owner.sequence, sequence + 1)
            self.assertEqual(owner.read_bytes, (beat + 1) * 64)
            self.assertEqual(owner.write_bytes, old_write)
            self.assertEqual(owner.beat, beat, "read success cannot advance destination beat")
            self.assertEqual(owner.buffer, data)
        sequence = beat if cold else beat * 2 + 1
        request = m.Request(target, data, m.FULL_MASK, (job.context.tag << 32) | sequence, True)
        self.issue(owner, request, stalls, data ^ 0xFACE)
        self.wait_response(owner, waits + final_waits)
        self.assertIsNone(owner.signals().done)
        self.assertEqual(owner.write_bytes, beat * 64)
        event = owner.tick(response=m.Response(request.tag, data ^ 1), done_ready=True)
        self.assertTrue(event.response_fire)
        self.assertFalse(event.done_fire, "result does not exist before final ACK edge")
        self.assertEqual(owner.write_bytes, (beat + 1) * 64)
        self.assertEqual(owner.sequence, sequence + 1)
        self.assertFalse(owner.outstanding)
        if beat == 1023:
            self.assertEqual(owner.beat, 1023)
        else:
            self.assertEqual(owner.beat, beat + 1)
            self.assertIsNone(owner.signals().done)

    def held_and_consume(self, owner, job, committed, successful):
        result = owner.signals().done
        self.assertIsNotNone(result)
        snapshot = self.counter_snapshot(owner)
        for _ in range(5):
            event = owner.tick(job=job, committed=committed, memory_ready=True,
                               response=MODEL.Response(0, (1 << 512) - 1, True))
            self.assertFalse(event.job_fire)
            self.assertFalse(event.memory_fire)
            self.assertFalse(event.response_fire)
            self.assertFalse(event.done_fire)
            self.assertEqual(owner.signals().done, result)
            self.assertEqual(self.counter_snapshot(owner), snapshot)
            self.assertEqual(owner.cycles, result.cycles)
        event = owner.tick(job=job, committed=committed, done_ready=True)
        self.assertTrue(event.done_fire)
        self.assertFalse(event.job_fire)
        self.assertEqual(owner.signals().job_ready, successful)
        self.assertEqual(owner.signals().reset_required, not successful)
        self.assertIsNone(owner.signals().done)
        if not successful:
            for _ in range(3):
                event = owner.tick(job=job, committed=committed, memory_ready=True,
                                   done_ready=True, response=MODEL.Response(owner.expected_tag))
                self.assertFalse(any((event.job_fire, event.memory_fire,
                                      event.response_fire, event.done_fire)))
                self.assertEqual(owner.state, owner.LOCKED)
                self.assertEqual(owner.cycles, result.cycles)
                self.assertEqual(self.counter_snapshot(owner), snapshot)
        return result

    def reject(self, job, committed, status):
        owner = MODEL.Owner()
        self.assertEqual(MODEL.admission_status(job, committed), status)
        event = owner.tick(job=job, committed=committed, memory_ready=True,
                           response=MODEL.Response(0))
        self.assertTrue(event.job_fire)
        self.assertFalse(event.memory_fire)
        self.assertFalse(event.response_fire)
        result = owner.signals().done
        self.assertEqual(result.status, status)
        self.assertEqual((result.read_bytes, result.write_bytes, result.cycles), (0, 0, 0))
        self.assertFalse(result.transfer_complete)
        self.assertFalse(result.local_drained)
        self.assertTrue(owner.signals().reset_required)
        self.held_and_consume(owner, job, committed, False)

    def test_10_twelve_full_bitwise_transfers(self):
        m = MODEL
        for tokens in (16, 128):
            for head in (0, 15):
                for path in ("cold", "warm", "export"):
                    with self.subTest(tokens=tokens, head=head, path=path):
                        job, committed = make_job(tokens, head, path)
                        committed_before = committed
                        owner = self.admit(job, committed)
                        for beat in range(1024):
                            stressed = beat in (0, 511, 1023)
                            self.one_beat(owner, job, beat, stalls=3 if stressed else 0,
                                          waits=2 if stressed else 0,
                                          final_waits=7 if beat == 1023 else 0)
                        result = owner.signals().done
                        cold = path == "cold"
                        self.assertEqual(result.status, m.Status.OK)
                        self.assertEqual(result.read_bytes, 0 if cold else 65536)
                        self.assertEqual(result.write_bytes, 65536)
                        self.assertEqual(result.cycles, (2048 + 15 if cold else 4096 + 30) + 7)
                        self.assertTrue(result.transfer_complete)
                        self.assertTrue(result.local_drained)
                        self.assertFalse(owner.signals().reset_required)
                        self.assertEqual(result.expected_generation, committed.generation)
                        self.assertEqual(committed, committed_before)
                        self.held_and_consume(owner, job, committed, True)
                        # Reuse only after successful held result acceptance.
                        event = owner.tick(job=job, committed=committed)
                        self.assertTrue(event.job_fire)
                        self.assertEqual((owner.sequence, owner.beat, owner.cycles), (0, 0, 0))
                        self.assertEqual((owner.read_bytes, owner.write_bytes), (0, 0))
                        FULL_TRANSFERS.append(dict(tokens=tokens, head=head, path=path,
                                                   beats=1024, read_bytes=result.read_bytes,
                                                   write_bytes=result.write_bytes))
        self.assertEqual(len(FULL_TRANSFERS), 12)

    def test_11_unsolicited_response_and_busy_job_are_not_accepted(self):
        m = MODEL
        owner = m.Owner()
        initial = owner.signals()
        event = owner.tick(response=m.Response(0xFF, 123, True), memory_ready=True)
        self.assertFalse(event.response_fire)
        self.assertEqual(owner.signals(), initial)
        job, committed = make_job()
        owner = self.admit(job, committed)
        request = owner.signals().memory_request
        different, different_root = make_job(128, 15, "export", tag=1)
        event = owner.tick(job=different, committed=different_root,
                           response=m.Response(request.tag, 123))
        self.assertFalse(event.job_fire)
        self.assertFalse(event.response_fire)
        self.assertEqual(owner.job, job)
        self.assertEqual(owner.signals().memory_request, request)
        self.issue(owner, request)
        event = owner.tick(job=different, committed=different_root,
                           response=m.Response(request.tag, 456), memory_ready=True)
        self.assertTrue(event.response_fire)
        self.assertFalse(event.job_fire)
        self.assertFalse(event.memory_fire)
        self.assertEqual(owner.job, job)
        self.assertEqual(owner.buffer, 456)

    def test_12_scope_values_and_status_precedence(self):
        m = MODEL
        job, committed = make_job(path="cold")
        for tokens in (0, 1, 15, 17, 63, 64, 65, 127, 129, 256, 65535):
            with self.subTest(tokens=tokens):
                self.reject(replace(job, context=replace(job.context, tokens=tokens)), committed, m.Status.BOUNDS)
        for head in (16, 17, 65535):
            self.reject(replace(job, head=head), committed, m.Status.BOUNDS)
        for operation in (2, 3):
            self.reject(replace(job, operation=operation), committed, m.Status.UNSUPPORTED)
        for policy in (0, 1):
            self.assertTrue(m.admissible(replace(job, context=replace(job.context, vector_policy=policy)), committed))
        # Root mismatch dominates bounds/op; bounds dominates op/receipts;
        # operation dominates receipts, exactly as the Scala elsewhen order.
        invalid = replace(job, head=16, operation=3,
                          context=replace(job.context, tokens=64, input=1))
        self.reject(invalid, replace(committed, generation=1), m.Status.DEPENDENCY)
        self.reject(invalid, committed, m.Status.BOUNDS)
        self.reject(replace(job, operation=3), committed, m.Status.UNSUPPORTED)

    def test_13_exact_cold_warm_root_and_generation_rules(self):
        m = MODEL
        cold, empty = make_job(path="cold")
        warm, carried = make_job(path="warm")
        for job, root in (
            (cold, replace(empty, valid=True)),
            (cold, replace(empty, generation=1)),
            (replace(cold, context=replace(cold.context, expected_generation=1)),
             replace(empty, generation=1)),
            (warm, replace(carried, valid=False)),
            (warm, replace(carried, generation=6)),
            (warm, replace(carried, state=carried.state + 64)),
            (replace(warm, context=replace(warm.context, expected_generation=0)),
             replace(carried, generation=0)),
        ):
            self.reject(job, root, m.Status.DEPENDENCY)
        self.assertTrue(m.admissible(cold, replace(empty, state=(1 << 64) - 1)))
        for generation in (1, 0xFFFFFFFE):
            self.assertTrue(m.admissible(
                replace(warm, context=replace(warm.context, expected_generation=generation)),
                replace(carried, generation=generation)))
        self.reject(replace(warm, context=replace(warm.context, expected_generation=0xFFFFFFFF)),
                    replace(carried, generation=0xFFFFFFFF), m.Status.BOUNDS)

    def test_14_full_spans_alignment_and_wide_end(self):
        m = MODEL
        names = ("input", "state_in", "state_out", "output", "scratch")
        for tokens in (16, 128):
            job, committed = make_job(tokens, 0, "cold")
            full_spans = m.spans(job.context)
            self.assertEqual([size for _, size in full_spans],
                             [tokens * 25600, 1048576, 1048576, tokens * 4096,
                              13959168 if tokens == 16 else 26869760])
            for name, (_, size) in zip(names, full_spans):
                with self.subTest(tokens=tokens, span=name):
                    self.reject(replace(job, context=replace(job.context,
                                **{name: getattr(job.context, name) + 1})), committed, m.Status.BOUNDS)
                    at_limit = replace(job, context=replace(job.context,
                                       **{name: (1 << 56) - size}))
                    self.assertTrue(m.admissible(at_limit, committed), "exclusive end == 2^56 is valid")
                    self.reject(replace(at_limit, context=replace(at_limit.context,
                                **{name: (1 << 56) - size + 64})), committed, m.Status.BOUNDS)
                    self.reject(replace(job, context=replace(job.context,
                                **{name: (1 << 64) - 64})), committed, m.Status.BOUNDS)
                    self.reject(replace(job, context=replace(job.context,
                                **{name: 1 << 56})), committed, m.Status.BOUNDS)
            # Even head 0 cold initialization validates unaccessed stateIn and
            # the complete 16-head scratch allocation, not only its own 64 KiB.
            bad_scratch = replace(job, context=replace(job.context, scratch=(1 << 56) - 65536))
            self.reject(bad_scratch, committed, m.Status.BOUNDS)

    def test_15_all_ten_full_span_alias_pairs_and_touching(self):
        m = MODEL
        names = ("input", "state_in", "state_out", "output", "scratch")
        for tokens in (16, 128):
            job, root = make_job(tokens, 0, "cold")
            context = replace(job.context, **{name: (index + 1) * 0x10000000
                                              for index, name in enumerate(names)})
            job = replace(job, context=context)
            sizes = [size for _, size in m.spans(context)]
            pair_count = 0
            for second in range(5):
                for first in range(second):
                    pair_count += 1
                    with self.subTest(tokens=tokens, pair=(names[first], names[second])):
                        first_end = getattr(context, names[first]) + sizes[first]
                        touching = replace(job, context=replace(context, **{names[second]: first_end}))
                        self.assertTrue(m.admissible(touching, root), "adjacent full spans do not alias")
                        overlapping = replace(job, context=replace(context,
                                              **{names[second]: first_end - 64}))
                        self.reject(overlapping, root, m.Status.BOUNDS)
            self.assertEqual(pair_count, 10)

    def test_16_every_receipt_field_and_final_chunk_are_bound(self):
        m = MODEL
        for tokens in (16, 128):
            job, root = make_job(tokens, 15, "export")
            self.assertTrue(m.admissible(job, root))
            for name in ("next_state_ready", "output_ready"):
                receipt = getattr(job, name)
                changes = dict(tag=receipt.tag ^ 1,
                               expected_generation=receipt.expected_generation + 1,
                               head=receipt.head ^ 1, chunk=receipt.chunk ^ 1,
                               phase=receipt.phase - 1, status=m.Status.MEMORY,
                               scratch_ack_bytes=receipt.scratch_ack_bytes + 64,
                               output_ack_bytes=receipt.output_ack_bytes + 64,
                               state_ack_bytes=64, drained=False)
                self.assertEqual(set(changes), {field.name for field in fields(m.Receipt)})
                for field, value in changes.items():
                    with self.subTest(tokens=tokens, receipt=name, field=field):
                        invalid = replace(job, **{name: replace(receipt, **{field: value})})
                        self.reject(invalid, root, m.Status.DEPENDENCY)
            self.reject(replace(job, output_ready=m.Receipt()), root, m.Status.DEPENDENCY)
            self.reject(replace(job, next_state_ready=job.output_ready,
                                output_ready=job.next_state_ready), root, m.Status.DEPENDENCY)
            # Initializers do not consume either receipt; root is still checked.
            for path in ("cold", "warm"):
                initial, initial_root = make_job(tokens, 15, path)
                initial = replace(initial, next_state_ready=m.Receipt(status=255),
                                  output_ready=m.Receipt(status=255))
                self.assertTrue(m.admissible(initial, initial_root))
            # Export may belong to a cold job, but must still read next_state,
            # not zero-fill, with the generation-0 receipts and empty root.
            cold, cold_root = make_job(tokens, 15, "cold")
            cold_export = replace(cold, operation=m.Operation.EXPORT_FINAL)
            owner = self.admit(cold_export, cold_root)
            self.assertFalse(owner.signals().memory_request.write)
            self.assertEqual(owner.signals().memory_request.address,
                             oracle_addresses(cold_export, 0)[0])

    def test_17_tag_error_precedence_failure_counters_and_lock(self):
        m = MODEL
        for path in ("cold", "warm", "export"):
            directions = ("write",) if path == "cold" else ("read", "write")
            for direction in directions:
                for wrong_tag, error in ((False, True), (True, False), (True, True)):
                    with self.subTest(path=path, direction=direction, wrong_tag=wrong_tag, error=error):
                        job, root = make_job(128, 15, path)
                        owner = self.admit(job, root)
                        for beat in range(3):
                            self.one_beat(owner, job, beat)
                        if direction == "write" and path != "cold":
                            request = owner.signals().memory_request
                            self.issue(owner, request)
                            owner.tick(response=m.Response(request.tag, payload(3)))
                        request = owner.signals().memory_request
                        self.assertEqual(request.write, direction == "write")
                        self.issue(owner, request)
                        before = self.counter_snapshot(owner)
                        tag = request.tag ^ 1 if wrong_tag else request.tag
                        event = owner.tick(response=m.Response(tag, (1 << 512) - 1, error))
                        self.assertTrue(event.response_fire)
                        result = owner.signals().done
                        self.assertEqual(result.status, m.Status.PROTOCOL if wrong_tag else m.Status.MEMORY)
                        self.assertEqual((owner.beat, owner.sequence, owner.read_bytes, owner.write_bytes), before[:4])
                        self.assertEqual(owner.buffer, before[5])
                        self.assertEqual(owner.outstanding, wrong_tag)
                        self.assertFalse(result.transfer_complete)
                        self.assertFalse(result.local_drained)
                        self.held_and_consume(owner, job, root, False)
                        owner.reset()
                        self.assertTrue(owner.signals().job_ready)
                        self.assertFalse(owner.signals().reset_required)
                        self.assertTrue(owner.tick(job=job, committed=root).job_fire)

    def test_18_failed_final_write_never_completes(self):
        m = MODEL
        job, root = make_job(16, 0, "warm")
        owner = self.admit(job, root)
        for beat in range(1023):
            self.one_beat(owner, job, beat)
        read = owner.signals().memory_request
        self.issue(owner, read)
        owner.tick(response=m.Response(read.tag, payload(1023)))
        write = owner.signals().memory_request
        self.issue(owner, write)
        self.wait_response(owner, 7)
        owner.tick(response=m.Response(write.tag, error=True))
        result = owner.signals().done
        self.assertEqual((result.read_bytes, result.write_bytes), (65536, 65472))
        self.assertEqual((owner.beat, owner.sequence), (1023, 2047))
        self.assertEqual(result.status, m.Status.MEMORY)
        self.assertFalse(result.transfer_complete)
        self.assertFalse(result.local_drained)
        self.held_and_consume(owner, job, root, False)

    def test_19_stale_read_response_not_a_write_ack(self):
        m = MODEL
        job, root = make_job()
        owner = self.admit(job, root)
        read = owner.signals().memory_request
        self.issue(owner, read)
        owner.tick(response=m.Response(read.tag, payload(0)))
        write = owner.signals().memory_request
        event = owner.tick(response=m.Response(read.tag))
        self.assertFalse(event.response_fire)
        self.issue(owner, write)
        owner.tick(response=m.Response(read.tag))
        self.assertEqual(owner.signals().done.status, m.Status.PROTOCOL)
        self.assertEqual((owner.read_bytes, owner.write_bytes), (64, 0))
        self.assertTrue(owner.outstanding)

    def test_20_python_wire_width_checks_are_not_extra_hardware_admission(self):
        m = MODEL
        job, _ = make_job()
        for field, value in (("tag", 1 << 32), ("tokens", 1 << 16),
                             ("expected_generation", -1), ("vector_policy", 2),
                             ("scratch", 1 << 64)):
            with self.assertRaises(ValueError):
                replace(job.context, **{field: value})
        with self.assertRaises(ValueError):
            replace(job, head=-1)
        with self.assertRaises(ValueError):
            m.Response(0, 1 << 512)
        with self.assertRaises(ValueError):
            m.Response(1 << 64)
        self.assertEqual(m.Response((1 << 64) - 1, (1 << 512) - 1).data, (1 << 512) - 1)


def main():
    global MODEL, PINS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="fixed repository source root")
    parser.add_argument("--contract", type=Path, required=True, help="pinned 1245 source package root")
    args = parser.parse_args()
    sys.addaudithook(readonly_audit)
    started = time.monotonic()
    try:
        PINS = PinSet(args.base, args.contract)
    except Exception as error:
        print(json.dumps({"status": "INPUT_PIN_FAILURE", "error": str(error)}), flush=True)
        return 2
    result = None
    problem = None
    try:
        # Works under -I without using sys.path or any bytecode/cache loader.
        # Execute only the exact already-verified source bytes. Registration is
        # required by dataclasses; this does not import repository model code.
        module = types.ModuleType("pinned_chunk_state_transfer_model")
        module.__file__ = str(HERE / "transfer_model.py")
        sys.modules[module.__name__] = module
        model_code = compile(PINS.cache[("own", "transfer_model.py")], module.__file__, "exec")
        exec(model_code, module.__dict__)
        MODEL = module
        suite = unittest.TestSuite((
            unittest.defaultTestLoader.loadTestsFromTestCase(SourceCorrespondence),
            unittest.defaultTestLoader.loadTestsFromTestCase(ModelControls),
        ))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    except Exception as error:
        problem = str(error)
    finally:
        try:
            PINS.verify_after()
        except Exception as error:
            problem = f"AFTER_PIN_FAILURE: {error}"
    success = problem is None and result is not None and result.wasSuccessful()
    print(json.dumps({
        "status": "PASS_PYTHON_MODEL_AND_SOURCE_CONTROLS_ONLY" if success else "FAIL",
        "executed_chisel": False, "executed_rtl": False, "executed_native_model": False,
        "tests": 0 if result is None else result.testsRun,
        "full_transfer_cases": FULL_TRANSFERS,
        "pins_before_and_after": problem is None,
        "pinned_files": len(PINS.entries),
        "seconds": round(time.monotonic() - started, 6),
        "error": problem,
        "limits": "No compile, elaboration, transport-byte-count, real receipt, arithmetic, or publication proof.",
    }, sort_keys=True), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
