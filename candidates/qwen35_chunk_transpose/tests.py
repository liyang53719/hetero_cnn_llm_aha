#!/usr/bin/env python3
"""Bounded read-only SOURCE and PYTHON SIMULATED protocol controls only.

Run only by separately authorized root review, Python3.12 -I -S -B, <=10s,
1 CPU, 256MiB. This file grants no execution permission. No Scala, JVM,
Chisel, native candidate, RTL, real transport ACK, or arithmetic service runs.
The independent integer/address/word oracle is a transcription of the pinned
transpose order, not execution of that original model or numerical DUT proof.
"""
import argparse
from dataclasses import fields, replace
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PREFIX = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
OWNER_SOURCE = 'source/GdnChunkTransposeOwner.scala'
PHASE1_SOURCE = 'source/GdnChunkLoadPrepOwner.scala'
PHASE2_SOURCE = 'source/GdnChunkDerivedAndPairOwner.scala'
ORIGINAL = 'candidates/qwen35_gdn_prefill/chunk/model.py'
MODEL = PINS = None
FULL_CASES = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def readonly_audit(event, args):
    denied = ('ctypes.dlopen', 'subprocess.Popen', 'os.system', 'os.posix_spawn',
              'os.fork', 'os.exec', 'os.remove', 'os.rename', 'os.rmdir', 'os.mkdir',
              'os.unlink', 'os.symlink', 'os.link', 'os.truncate', 'os.chmod',
              'os.chown', 'os.utime', 'os.setxattr', 'os.removexattr')
    if event in denied or event.startswith('socket.'):
        raise RuntimeError('read-only controls forbid this operation')
    if event == 'open':
        mode, flags = args[1], args[2]
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            raise RuntimeError('read-only controls forbid file writes')


def safe_path(root, relative):
    require(isinstance(relative, str) and relative, 'missing pin path')
    rel = Path(relative)
    require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe pin path')
    path = root / rel
    require(path.is_file() and not path.is_symlink(), 'pin must be regular file')
    require(path.resolve().is_relative_to(root.resolve()), 'pin escapes root')
    return path


def read_small(path, expected=None):
    before = path.stat()
    require(before.st_size <= 2 * 1024 * 1024, 'small-control file bound')
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after), 'file changed during read')
    digest = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if expected is not None:
        require(digest == dict(bytes=expected['bytes'], sha256=expected['sha256']), f'pin mismatch: {path.name}')
    return raw, digest


class PinSet:
    def __init__(self, base, contract, phase1, phase2):
        roots = {n: p.resolve() for n, p in dict(base=base, contract=contract, phase1=phase1, phase2=phase2).items()}
        pin_raw, pin_digest = read_small(HERE / 'INPUT_PINS.json')
        manifest_raw, manifest_digest = read_small(HERE / 'SOURCE_MANIFEST.json')
        external, manifest = json.loads(pin_raw), json.loads(manifest_raw)
        require(isinstance(external.get('files'), dict) and external['files'], 'missing input pins')
        require(isinstance(manifest.get('files'), dict) and manifest['files'], 'missing own pins')
        own = manifest['files']
        require({'transpose_model.py', 'tests.py', OWNER_SOURCE, 'INTERFACE_CONTRACT.md', 'README.md',
                 'SCOPE.json', 'INPUT_PINS.json', 'TEST_COMMAND.json'} <= set(own), 'omitted own required file')
        require('SOURCE_MANIFEST.json' not in own, 'self-referential manifest')
        self.entries, self.cache = [], {}
        self.manifest_sha256 = manifest_digest['sha256']
        self.descriptors = [(HERE / 'INPUT_PINS.json', pin_digest), (HERE / 'SOURCE_MANIFEST.json', manifest_digest)]
        for label, spec in external['files'].items():
            require(spec.get('role') in roots, f'unknown role: {label}')
            key = spec['role'], spec['path']
            require(key not in self.cache, 'duplicate external pin')
            path = safe_path(roots[spec['role']], spec['path'])
            raw, digest = read_small(path, spec)
            self.cache[key] = raw
            self.entries.append((path, digest))
        for relative, spec in own.items():
            path = safe_path(HERE, relative)
            raw, digest = read_small(path, spec)
            self.cache[('own', relative)] = raw
            self.entries.append((path, digest))
        require(sum(d['bytes'] for _, d in self.entries) <= 20 * 1024 * 1024, 'total pin bound')
        required = {('base', PREFIX + n) for n in ('Protocol.scala', 'BlockFloat.scala',
            'ElementwiseMemoryEngine.scala', 'ElementwiseRegisterLoan.scala', 'GdnInputPrepOwner.scala',
            'GdnOwnerProtocol.scala', 'GdnRecurrentOwner.scala', 'HostBlockTop.scala',
            'QwenOwnerProtocol.scala', 'SharedMemoryArbiter.scala')}
        required |= {('base', ORIGINAL), ('base', 'candidates/qwen35_gdn_prefill/chunk/vector16.cpp'),
            ('base', 'config/upstream/qwen3_5_0p8b/manifest.json'),
            ('contract', 'source/GdnChunkProtocol.scala'), ('contract', 'source/GdnChunkAddressPlan.scala'),
            ('phase1', PHASE1_SOURCE), ('phase2', PHASE2_SOURCE), ('phase2', 'SOURCE_MANIFEST.json')}
        require(required <= set(self.cache), 'missing correspondence input')
        phase2_manifest = json.loads(self.cache[('phase2', 'SOURCE_MANIFEST.json')])
        spec = phase2_manifest['files'][PHASE2_SOURCE]
        raw = self.cache[('phase2', PHASE2_SOURCE)]
        require(spec == dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()), 'phase2 source/manifest mismatch')

    def text(self, role, path):
        return self.cache[(role, path)].decode('utf-8')

    def verify_after(self):
        for path, digest in self.descriptors + self.entries:
            read_small(path, digest)


def compact(source):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S))


def pack(words):
    return int.from_bytes(b''.join(w.to_bytes(4, 'little') for w in words), 'little')


def make_job(tokens=16, head=3, chunk=0, cold=False):
    m = MODEL
    c = m.Context(0x87654321, tokens, cold, 0 if cold else 7, 0,
                  0x100000, 0x800000, 0xA00000, 0xC00000, 0x1000000)
    p = m.Receipt(c.tag, c.expected_generation, head, chunk, 2, 0, 180224, 0, 0, True)
    d = m.PrivateDecay(c, head, chunk, 0x80000001, True)
    r = m.Phase2Result(p, d, 235584, 2209, 2209, 2144, 2144, 2560, 2560, 987, True)
    return m.Job(c, head, chunk, r), m.Committed(not cold, c.expected_generation, 0 if cold else c.state_in)


def repack(job, **changes):
    c = replace(job.context, **changes)
    r = replace(job.phase2_ready, receipt=replace(job.phase2_ready.receipt,
                tag=c.tag, expected_generation=c.expected_generation),
                decay=replace(job.phase2_ready.decay, context=c))
    return replace(job, context=c, phase2_ready=r)


SPECIALS = (0, 0x80000000, 1, 0x80000001, 0x007FFFFF, 0x807FFFFF,
            0x00800000, 0x80800000, 0x7F7FFFFF, 0xFF7FFFFF, 0x3F800000, 0xBF800000)


def source_word(job, phase, row, column):
    """Independent finite test data, including bit-exact signed subnormals.

    M16 padded rows are zero in these fixtures, but still READ and transposed.
    The owner is not authorized to infer padding or omit those rows.
    """
    if job.context.tokens == 16 and row >= 16:
        return 0
    index = row * 128 + column
    if index % 17 < len(SPECIALS):
        return SPECIALS[(index + phase + job.head + job.chunk) % len(SPECIALS)]
    fraction = (row * 1009 + column * 65537 + phase * 4099 + job.head * 131 + job.chunk) & 0x7FFFFF
    return 0x3F000000 | fraction | ((index & 1) << 31)


def independent_events(job):
    """Never calls owner address/transpose/finite helpers or original code."""
    stride = 65536 + ((job.context.tokens + 63) // 64) * 806912
    base = job.context.scratch + job.head * stride + 65536 + job.chunk * 806912
    for phase, src, dst in ((3, 36864, 266240), (4, 233472, 299008)):
        for row_start in range(0, 64, 16):
            for column_start in range(0, 128, 16):
                for row in range(row_start, row_start + 16):
                    data = pack(source_word(job, phase, row, col) for col in range(column_start, column_start + 16))
                    yield False, phase, base + src + (row * 128 + column_start) * 4, data
                for column in range(column_start, column_start + 16):
                    data = pack(source_word(job, phase, row, column) for row in range(row_start, row_start + 16))
                    yield True, phase, base + dst + (column * 64 + row_start) * 4, data


def drive_one(test, owner, expected, *, stalls=False):
    write, phase, address, data = expected
    before = owner.peek()
    req = before.memory_request
    test.assertIsNotNone(req)
    test.assertFalse(before.job_ready or before.reset_required)
    test.assertIsNone(before.done)
    test.assertEqual((req.write, req.address, req.mask, req.data),
                     (write, address, (1 << 64) - 1 if write else 0, data if write else 0))
    test.assertEqual(req.tag, (owner.job.context.tag << 32) | owner.sequence)
    test.assertFalse(owner.outstanding)
    response = MODEL.MemoryResponse(req.tag, 0 if write else data)
    if stalls:
        accepted = owner.job
        for _ in range(2):
            e = owner.tick(job=repack(accepted, tag=1), response=response)
            test.assertFalse(e.job_fire or e.memory_fire or e.response_fire)
            test.assertEqual(owner.peek(), before)
            test.assertEqual(owner.job, accepted)
    reads, writes = owner.read_bytes[:], owner.write_bytes[:]
    e = owner.tick(memory_ready=True, response=response)
    test.assertTrue(e.memory_fire)
    test.assertFalse(e.response_fire)
    test.assertTrue(owner.outstanding)
    test.assertIsNone(owner.peek().memory_request)
    test.assertIsNone(owner.peek().done)
    test.assertEqual((owner.read_bytes, owner.write_bytes), (reads, writes))
    if stalls:
        owner.tick()
        test.assertEqual((owner.read_bytes, owner.write_bytes), (reads, writes))
    e = owner.tick(response=response)
    test.assertTrue(e.response_fire)
    test.assertFalse(owner.outstanding)
    (writes if write else reads)[phase - 3] += 64
    test.assertEqual((owner.read_bytes, owner.write_bytes), (reads, writes))
    test.assertEqual(len(owner.tile), 16)
    test.assertTrue(all(0 <= value < 1 << 512 for value in owner.tile))
    return req


class SourceCorrespondence(unittest.TestCase):
    def test_original_abi_transport_and_unchanged_public_gates(self):
        protocol = compact(PINS.text('base', PREFIX + 'Protocol.scala'))
        self.assertIn('valwrite=Bool();valaddress=UInt(64.W);valdata=UInt(512.W);valmask=UInt(64.W);valtag=UInt(64.W)', protocol)
        self.assertIn('classMemoryResponseextendsBundle{valdata=UInt(512.W);valtag=UInt(64.W);valerror=Bool()}', protocol)
        self.assertEqual([f.name for f in fields(MODEL.MemoryResponse)], ['tag', 'data', 'error'])
        for name, value in (('Ok', 0), ('Memory', 3), ('Unsupported', 4), ('Bounds', 5),
                            ('Dependency', 6), ('Protocol', 7), ('Numerical', 8)):
            self.assertIn(f'val{name}={value}', protocol)
        arb = compact(PINS.text('base', PREFIX + 'SharedMemoryArbiter.scala'))
        self.assertIn('reply.tag:=originalTag', arb)
        self.assertIn('state:=Mux(poison,locked,idle)', arb)
        recurrent = compact(PINS.text('base', PREFIX + 'GdnRecurrentOwner.scala'))
        self.assertIn('j.tokens=/=1.U', recurrent)
        public = compact(PINS.text('base', PREFIX + 'QwenOwnerProtocol.scala'))
        self.assertIn('Some(Module(newGdnRecurrentOwner(maxHeads=16)))', public)
        self.assertNotIn('GdnChunkTransposeOwner', public)
        self.assertNotIn('GdnChunkTransposeOwner', PINS.text('base', PREFIX + 'HostBlockTop.scala'))
        self.assertIn('"max_tokens":1', PINS.text('base', PREFIX + 'HostBlockTop.scala'))

    def test_owner_state_addresses_gate_and_ack_source(self):
        source = compact(PINS.text('own', OWNER_SOURCE))
        self.assertIn('validle::issueRead::waitRead::issueWrite::waitWrite::finish::locked::Nil=Enum(7)', source)
        self.assertEqual(tuple(MODEL.STATES), ('idle', 'issueRead', 'waitRead', 'issueWrite', 'waitWrite', 'finish', 'locked'))
        for literal in ('Seq.fill(16)(0.U(512.W))', 'valphase2Ready=newGdnChunkDerivedAndPairResult',
                'd.context.asUInt===c.asUInt', 'd.head.pad(16)===j.head', 'd.chunk.pad(16)===j.chunk',
                'p.scratchAckBytes===180224.U', 'r.readBytes===235584.U',
                'r.expRequests===2209.U&&r.expResults===2209.U',
                'r.addRequests===2144.U&&r.addResults===2144.U',
                'r.mulRequests===2560.U&&r.mulResults===2560.U',
                'Cat(tileRow,index).pad(66)<<9', 'tileCol.pad(66)<<6',
                'Cat(tileCol,index).pad(66)<<8', 'tileRow.pad(66)<<6',
                'transposed(j):=(tile(j)>>(index<<5))(31,0)',
                'readBytes(second.asUInt)=/=32768.U||writeBytes(second.asUInt)=/=32704.U',
                'phase3Done:=true.B;second:=true.B', 'state:=Mux(status===Status.Ok.U,idle,locked)'):
            self.assertIn(literal, source)
        self.assertLess(source.index('when(r.tag=/=Cat(context.tag,sequence))'), source.index('.elsewhen(r.error)'))
        self.assertLess(source.index('readBytes(second.asUInt):=readBytes(second.asUInt)+BeatBytes.U'), source.index('when(!finiteBeat(r.data))'))
        self.assertNotIn('Module(new', source)
        self.assertNotIn('SyncReadMem', source)
        self.assertNotIn('newGdnScalarClient', source)
        self.assertIn('receipt.outputAckBytes:=0.U;receipt.stateAckBytes:=0.U', source)
        self.assertIn('io.done.bits.decay.value:=Mux(complete,decayValue,0.U)', source)

    def test_original_order_shapes_phase2_types_and_scope(self):
        original = compact(PINS.text('base', ORIGINAL))
        self.assertIn('ifnotall(finite(v)forvinwords)', original)
        self.assertIn('forrinrange(0,source.rows,16):forcinrange(0,source.cols,16):tile=[]', original)
        self.assertIn('tile.append((yieldfromself._read(source.address(r+i,c))))', original)
        self.assertIn('yieldfromself._write(destination.address(c+i,r),[tile[j][i]forjinrange(16)])', original)
        self.assertLess(original.index("self._phase('transpose_k')"), original.index("self._phase('transpose_decayed_k')"))
        plan = compact(PINS.text('contract', 'source/GdnChunkAddressPlan.scala'))
        for literal in ('Shape("k",64,128)', 'Shape("ke",64,128)', 'Shape("kt",128,64)',
                        'Shape("ket",128,64)', 'Phase("TransposeK",Vector("kt"))',
                        'Phase("TransposeDecayedK",Vector("ket"))'):
            self.assertIn(literal, plan)
        phase2 = compact(PINS.text('phase2', PHASE2_SOURCE))
        self.assertIn('classGdnChunkPrivateDecayextendsBundle{valcontext=newGdnChunkJob', phase2)
        self.assertIn('valdecay=newGdnChunkPrivateDecay', phase2)
        self.assertIn('valphase1Ready=newGdnChunkLoadPrepResult', phase2)
        self.assertIn('class GdnChunkLoadPrepResult', PINS.text('phase1', PHASE1_SOURCE))
        scope = json.loads(PINS.text('own', 'SCOPE.json'))
        self.assertEqual((scope['payload_bytes'], scope['combined_transactions'], scope['arithmetic_requests']), (1024, 2048, 0))
        for name in ('scala_compile', 'chirrtl_elaboration', 'rtl_simulation', 'numerical_dut_validation',
                     'whole_chunk_implemented', 'host_publication_changed', 'm1_public_and_recurrent_guards_changed'):
            self.assertFalse(scope[name])
        contract = PINS.text('own', 'INTERFACE_CONTRACT.md')
        for literal in ('TRUSTED SCHEDULER', 'not authenticate receipts', 'phase3Complete', 'no-stale', 'NOT Scala execution'):
            self.assertIn(literal, contract)


class ModelControls(unittest.TestCase):
    def accepted(self, job=None, root=None):
        if job is None:
            job, root = make_job()
        owner = MODEL.Owner()
        e = owner.tick(job=job, committed=root)
        self.assertTrue(e.job_fire)
        self.assertEqual(owner.state, 'issueRead')
        self.assertEqual(owner.cycles, 0)
        return owner

    def advance(self, owner, count):
        events = independent_events(owner.job)
        for _ in range(count):
            drive_one(self, owner, next(events))
        return events

    def failure(self, owner, status, outstanding=False):
        m = MODEL
        held = owner.peek()
        self.assertIsNotNone(held.done)
        self.assertEqual(held.done.status, status)
        self.assertTrue(held.reset_required)
        self.assertFalse(held.job_ready or held.response_ready)
        self.assertIsNone(held.memory_request)
        self.assertFalse(held.done.drained or held.done.stage_complete or held.done.phase4_complete)
        self.assertFalse(held.done.decay.valid)
        self.assertEqual(held.done.decay.value, 0)
        self.assertEqual(owner.outstanding, outstanding)
        for _ in range(2):
            e = owner.tick(job=owner.job, committed=m.Committed(False, 99, 0), memory_ready=True,
                           response=m.MemoryResponse(0))
            self.assertFalse(e.job_fire or e.memory_fire or e.response_fire or e.done_fire)
            self.assertEqual(owner.peek(), held)
        self.assertTrue(owner.tick(done_ready=True, job=owner.job).done_fire)
        self.assertEqual(owner.state, 'locked')
        e = owner.tick(job=owner.job, committed=m.Committed(False, 0, 0), memory_ready=True,
                       response=m.MemoryResponse(0), done_ready=True)
        self.assertFalse(e.job_fire or e.memory_fire or e.response_fire or e.done_fire)

    def test_unsigned_widths_no_response_length_or_external_state_fields(self):
        m = MODEL
        job, _ = make_job()
        for name, value in (('tag', -1), ('tokens', 65536), ('expected_generation', 1 << 32),
                ('vector_policy', 2), ('input', 1 << 64), ('cold', 1)):
            with self.assertRaises(ValueError):
                replace(job.context, **{name: value})
        for factory in (lambda: replace(job, head=65536), lambda: replace(job, chunk=-1),
                lambda: replace(job.phase2_ready, exp_requests=4096),
                lambda: m.MemoryResponse(1 << 64), lambda: m.MemoryResponse(0, 1 << 512),
                lambda: m.MemoryResponse(0, error=1), lambda: m.Owner().tick(memory_ready=1),
                lambda: replace(job.phase2_ready.decay, value=1 << 32)):
            with self.assertRaises(ValueError):
                factory()
        self.assertEqual([f.name for f in fields(m.Job)], ['context', 'head', 'chunk', 'phase2_ready'])
        self.assertFalse({'state_committed', 'generation_advanced', 'new_generation'} & {f.name for f in fields(m.Result)})
        with self.assertRaises(TypeError):
            m.MemoryResponse(0, nbytes=64)

    def test_roots_selectors_policy_and_priority(self):
        m = MODEL
        job, root = make_job()
        for snapshot in (replace(root, generation=6), replace(root, valid=False), replace(root, state=root.state + 64)):
            self.assertEqual(m.admission_status(job, snapshot), m.Status.DEPENDENCY)
        cold, coldroot = make_job(cold=True)
        self.assertEqual(m.admission_status(cold, coldroot), 0)
        self.assertEqual(m.admission_status(cold, replace(coldroot, valid=True)), m.Status.DEPENDENCY)
        self.assertEqual(m.admission_status(repack(job, expected_generation=0), replace(root, generation=0)), m.Status.DEPENDENCY)
        for bad in (repack(job, tokens=0), repack(job, tokens=1), repack(job, tokens=64), repack(job, tokens=129),
                    replace(job, head=16), replace(job, head=65535), replace(job, chunk=1)):
            self.assertEqual(m.admission_status(bad, root), m.Status.BOUNDS)
        j128, r128 = make_job(128, 15, 1)
        self.assertEqual(m.admission_status(j128, r128), 0)
        self.assertEqual(m.admission_status(replace(j128, chunk=2), r128), m.Status.BOUNDS)
        last = repack(job, expected_generation=0xFFFFFFFF)
        self.assertEqual(m.admission_status(last, replace(root, generation=0xFFFFFFFF)), m.Status.BOUNDS)
        self.assertEqual(m.admission_status(repack(job, vector_policy=1), root), m.Status.UNSUPPORTED)
        bad = repack(job, tokens=1, vector_policy=1)
        self.assertEqual(m.admission_status(bad, replace(root, generation=0)), m.Status.DEPENDENCY)
        self.assertEqual(m.admission_status(bad, root), m.Status.BOUNDS)

    def test_all_five_full_spans_endpoints_and_aliases_including_cold(self):
        m = MODEL
        for cold in (False, True):
            job, root = make_job(cold=cold)
            names = ('input', 'state_in', 'state_out', 'output', 'scratch')
            sizes = (16 * 25600, 1048576, 1048576, 16 * 4096, 16 * 872448)
            for name, size in zip(names, sizes):
                for address, expected in ((getattr(job.context, name) + 1, m.Status.BOUNDS),
                        ((1 << 56) - size, m.Status.OK), ((1 << 56) - size + 64, m.Status.BOUNDS)):
                    candidate = repack(job, **{name: address})
                    snapshot = replace(root, state=address) if name == 'state_in' and not cold else root
                    self.assertEqual(m.admission_status(candidate, snapshot), expected)
            for i, name in enumerate(names):
                for other in names[:i]:
                    candidate = repack(job, **{name: getattr(job.context, other)})
                    snapshot = replace(root, state=candidate.context.state_in) if not cold else root
                    self.assertEqual(m.admission_status(candidate, snapshot), m.Status.BOUNDS)

    def test_complete_phase2_receipt_and_each_counter_gate(self):
        m = MODEL
        job, root = make_job()
        p, r = job.phase2_ready.receipt, job.phase2_ready
        mutations = dict(tag=p.tag ^ 1, expected_generation=6, head=2, chunk=1, phase=1,
            status=3, scratch_ack_bytes=180160, output_ack_bytes=64, state_ack_bytes=64, drained=False)
        for name, value in mutations.items():
            bad = replace(job, phase2_ready=replace(r, receipt=replace(p, **{name: value})))
            self.assertEqual(m.admission_status(bad, root), m.Status.DEPENDENCY, name)
        for name in ('read_bytes', 'exp_requests', 'exp_results', 'add_requests', 'add_results', 'mul_requests', 'mul_results'):
            bad = replace(job, phase2_ready=replace(r, **{name: getattr(r, name) - 1}))
            self.assertEqual(m.admission_status(bad, root), m.Status.DEPENDENCY, name)
        self.assertEqual(m.admission_status(replace(job, phase2_ready=replace(r, stage_complete=False)), root), m.Status.DEPENDENCY)

    def test_full_decay_context_and_finite_admission_gate(self):
        m = MODEL
        job, root = make_job()
        r, d = job.phase2_ready, job.phase2_ready.decay
        for f in fields(job.context):
            value = getattr(job.context, f.name)
            value = not value if type(value) is bool else value ^ 1
            bad = replace(d, context=replace(job.context, **{f.name: value}))
            self.assertEqual(m.admission_status(replace(job, phase2_ready=replace(r, decay=bad)), root), m.Status.DEPENDENCY, f.name)
        for change in (dict(valid=False), dict(head=2), dict(chunk=1),
                       *(dict(value=v) for v in (0x7F800000, 0xFF800000, 0x7FC00000, 0xFFC00000, 0x7F800001, 0xFF800001))):
            self.assertEqual(m.admission_status(replace(job, phase2_ready=replace(r, decay=replace(d, **change))), root), m.Status.DEPENDENCY)
        for value in SPECIALS:
            self.assertEqual(m.admission_status(replace(job, phase2_ready=replace(r, decay=replace(d, value=value))), root), 0)

    def test_stale_admission_priority_and_root_snapshot_is_sampled_once(self):
        m = MODEL
        job, root = make_job()
        owner = m.Owner()
        owner.tick(job=job, committed=root, response=m.MemoryResponse(0))
        self.failure(owner, m.Status.PROTOCOL)
        owner = m.Owner()
        owner.tick(job=repack(job, vector_policy=1), committed=root, response=m.MemoryResponse(0))
        self.failure(owner, m.Status.UNSUPPORTED)
        owner = self.accepted(job, root)
        accepted = owner.job
        owner.tick(committed=m.Committed(False, 99, 0), job=repack(job, tag=1))
        self.assertEqual(owner.job, accepted)
        self.assertEqual(owner.state, 'issueRead')
        self.assertEqual(owner.cycles, 1)

    def test_request_backpressure_zero_latency_offer_and_wait_only_response(self):
        m = MODEL
        owner = self.accepted()
        req = owner.peek().memory_request
        response = m.MemoryResponse(req.tag, pack(SPECIALS + (0, 1, 2, 3)))
        for _ in range(3):
            e = owner.tick(response=response)
            self.assertFalse(e.memory_fire or e.response_fire)
            self.assertEqual(owner.peek().memory_request, req)
            self.assertFalse(owner.outstanding)
        e = owner.tick(memory_ready=True, response=response)
        self.assertTrue(e.memory_fire)
        self.assertFalse(e.response_fire)
        self.assertEqual(owner.read_bytes, [0, 0])
        self.assertTrue(owner.peek().response_ready)
        self.assertIsNone(owner.peek().memory_request)
        owner.tick(memory_ready=True)
        self.assertEqual(owner.read_bytes, [0, 0])
        self.assertTrue(owner.tick(response=response).response_fire)
        self.assertEqual(owner.read_bytes, [64, 0])
        self.assertEqual(owner.sequence, 1)

    def test_sixteen_reads_before_first_tile_output_and_exact_finite_bits(self):
        owner = self.accepted()
        rows = [pack(SPECIALS[(r + c) % len(SPECIALS)] for c in range(16)) for r in range(16)]
        for row, data in enumerate(rows):
            req = owner.peek().memory_request
            self.assertFalse(req.write)
            owner.tick(memory_ready=True)
            self.assertIsNone(owner.peek().memory_request)
            owner.tick(response=MODEL.MemoryResponse(req.tag, data))
            self.assertEqual(owner.write_bytes, [0, 0])
            self.assertEqual(owner.peek().memory_request.write, row == 15)
        for column in range(16):
            req = owner.peek().memory_request
            expected = pack(SPECIALS[(row + column) % len(SPECIALS)] for row in range(16))
            self.assertTrue(req.write)
            self.assertEqual(req.data, expected)
            owner.tick(memory_ready=True)
            # Write ACK payload is deliberately nonfinite, and must be ignored.
            owner.tick(response=MODEL.MemoryResponse(req.tag, 0x7FC00000))
        self.assertEqual(owner.write_bytes, [1024, 0])
        self.assertFalse(owner.peek().memory_request.write)

    def test_all_nonfinite_sign_kinds_each_lane_and_late_read_no_tile_write(self):
        m = MODEL
        for value in (0x7F800000, 0xFF800000, 0x7FC00000, 0xFFC00000, 0x7F800001, 0xFF800001):
            for lane in range(16):
                owner = self.accepted()
                req = owner.peek().memory_request
                owner.tick(memory_ready=True)
                owner.tick(response=m.MemoryResponse(req.tag, value << (lane * 32)))
                self.assertEqual((owner.read_bytes, owner.write_bytes, owner.sequence), ([64, 0], [0, 0], 1))
                self.assertEqual(owner.tile, [0] * 16)
                self.failure(owner, m.Status.NUMERICAL)
        owner = self.accepted()
        self.advance(owner, 32 + 15)
        tile_before = owner.tile[:]
        req = owner.peek().memory_request
        owner.tick(memory_ready=True)
        owner.tick(response=m.MemoryResponse(req.tag, 0xFFC00000 << 480))
        self.assertEqual((owner.read_bytes, owner.write_bytes), ([2048, 0], [1024, 0]))
        self.assertEqual(owner.tile, tile_before)
        self.failure(owner, m.Status.NUMERICAL)

    def test_read_write_error_wrongtag_priority_and_ack_counters(self):
        m = MODEL
        for write in (False, True):
            for wrong, error, status in ((True, True, m.Status.PROTOCOL), (True, False, m.Status.PROTOCOL),
                                          (False, True, m.Status.MEMORY)):
                owner = self.accepted()
                if write:
                    self.advance(owner, 16 + 1)
                req = owner.peek().memory_request
                self.assertEqual(req.write, write)
                reads, writes, sequence = owner.read_bytes[:], owner.write_bytes[:], owner.sequence
                owner.tick(memory_ready=True)
                owner.tick(response=m.MemoryResponse(req.tag ^ int(wrong), 0x7FC00000, error))
                self.assertEqual((owner.read_bytes, owner.write_bytes, owner.sequence), (reads, writes, sequence))
                self.failure(owner, status, outstanding=wrong)

    def test_phase3_last_ack_fence_and_no_early_decay(self):
        owner = self.accepted()
        events = self.advance(owner, 1023)
        final = next(events)
        self.assertEqual(final[:2], (True, 3))
        self.assertFalse(owner.phase3_done or owner.second)
        self.assertEqual((owner.read_bytes, owner.write_bytes), ([32768, 0], [32704, 0]))
        req = owner.peek().memory_request
        owner.tick(memory_ready=True)
        for _ in range(3):
            owner.tick(memory_ready=True)
            self.assertFalse(owner.phase3_done or owner.second)
            self.assertIsNone(owner.peek().memory_request)
            self.assertIsNone(owner.peek().done)
        owner.tick(response=MODEL.MemoryResponse(req.tag))
        self.assertTrue(owner.phase3_done and owner.second)
        self.assertIsNone(owner.peek().done)
        self.assertEqual(owner.read_bytes, [32768, 0])
        self.assertFalse(owner.peek().memory_request.write)
        self.assertEqual(owner.peek().memory_request.address, next(events)[2])

    def test_phase4_failure_preserves_real_phase3_checkpoint_not_overall_drain(self):
        m = MODEL
        for kind in ('read_error', 'write_error', 'wrong_tag', 'nonfinite'):
            owner = self.accepted()
            self.advance(owner, 1024 + (16 if kind == 'write_error' else 0))
            req = owner.peek().memory_request
            owner.tick(memory_ready=True)
            owner.tick(response=m.MemoryResponse(req.tag ^ int(kind == 'wrong_tag'),
                       0xFF800001 if kind == 'nonfinite' else 0, kind in ('read_error', 'write_error')))
            done = owner.peek().done
            self.assertEqual((done.phase3.status, done.phase3.drained, done.phase3.scratch_ack_bytes,
                              done.phase3_read_bytes, done.phase3_complete), (0, True, 32768, 32768, True))
            self.assertEqual(done.phase4.scratch_ack_bytes, 0)
            self.assertFalse(done.phase4.drained)
            self.assertEqual(done.phase4_read_bytes, 1024 if kind == 'write_error' else 64 if kind == 'nonfinite' else 0)
            self.failure(owner, m.Status.PROTOCOL if kind == 'wrong_tag' else m.Status.NUMERICAL if kind == 'nonfinite' else m.Status.MEMORY,
                         outstanding=kind == 'wrong_tag')

    def full_case(self, tokens, head, chunk, cold):
        m = MODEL
        job, root = make_job(tokens, head, chunk, cold)
        owner = self.accepted(job, root)
        digest, counts = hashlib.sha256(), [[0, 0], [0, 0]]
        for ordinal, expected in enumerate(independent_events(job)):
            if ordinal in (1023, 2047):
                self.assertIsNone(owner.peek().done)
                self.assertEqual(owner.write_bytes[expected[1] - 3], 32704)
            req = drive_one(self, owner, expected, stalls=ordinal % 257 == 0 or ordinal in (1023, 2047))
            counts[expected[1] - 3][int(expected[0])] += 1
            digest.update(bytes((int(req.write),)) + req.address.to_bytes(8, 'little') +
                          req.tag.to_bytes(8, 'little') + expected[3].to_bytes(64, 'little'))
            if ordinal == 1023:
                self.assertTrue(owner.phase3_done and owner.second)
                self.assertIsNone(owner.peek().done)
        self.assertEqual(counts, [[512, 512], [512, 512]])
        held = owner.peek()
        done = held.done
        self.assertEqual((owner.read_bytes, owner.write_bytes, owner.sequence), ([32768, 32768], [32768, 32768], 2048))
        self.assertTrue(done.phase3_complete and done.phase4_complete and done.stage_complete and done.drained)
        self.assertTrue(done.decay.valid)
        self.assertEqual(done.decay, job.phase2_ready.decay)
        self.assertEqual(done.decay.context, job.context)
        for phase, receipt in ((3, done.phase3), (4, done.phase4)):
            self.assertEqual(receipt, m.Receipt(job.context.tag, job.context.expected_generation, head, chunk,
                                              phase, 0, 32768, 0, 0, True))
        for _ in range(3):
            e = owner.tick(job=repack(job, tag=1), committed=m.Committed(False, 999, 0), memory_ready=True,
                           response=m.MemoryResponse(0))
            self.assertFalse(e.job_fire or e.response_fire or e.memory_fire)
            self.assertEqual(owner.peek(), held)
        e = owner.tick(job=job, committed=root, done_ready=True)
        self.assertTrue(e.done_fire)
        self.assertFalse(e.job_fire)
        self.assertTrue(owner.peek().job_ready)
        self.assertIsNone(owner.peek().done)
        self.assertTrue(owner.tick(job=job, committed=root).job_fire)
        self.assertEqual((owner.sequence, owner.read_bytes, owner.write_bytes, owner.cycles), (0, [0, 0], [0, 0], 0))
        self.assertFalse(owner.phase3_done or owner.second)
        FULL_CASES.append(dict(tokens=tokens, head=head, chunk=chunk, cold=cold,
                               transactions=2048, read_write_counts=counts, sha256=digest.hexdigest()))

    def test_full_m16_cold_bitwise_trace_and_held_terminal_reentry(self):
        self.full_case(16, 3, 0, True)

    def test_full_m128_warm_head15_chunk1_bitwise_trace_and_held_terminal(self):
        self.full_case(128, 15, 1, False)

    def test_sequence_wrap_and_last_ack_counter_integrity_controls(self):
        owner = self.accepted()
        owner.sequence = 0xFFFFFFFF  # Deliberate internal-state fault/control, not a reachable job-length claim.
        req = owner.peek().memory_request
        self.assertEqual(req.tag & 0xFFFFFFFF, 0xFFFFFFFF)
        owner.tick(memory_ready=True)
        owner.tick(response=MODEL.MemoryResponse(req.tag))
        self.assertEqual(owner.sequence, 0)
        owner = self.accepted()
        self.advance(owner, 1023)
        owner.read_bytes[0] -= 64  # Deliberate fault injection at the source's terminal counter guard.
        req = owner.peek().memory_request
        owner.tick(memory_ready=True)
        owner.tick(response=MODEL.MemoryResponse(req.tag))
        self.assertFalse(owner.phase3_done or owner.second)
        self.assertEqual(owner.write_bytes, [32768, 0])
        self.failure(owner, MODEL.Status.PROTOCOL)


def main():
    global MODEL, PINS
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'contract', 'phase1', 'phase2'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(sys.version_info[:2] == (3, 12), 'only separately reviewed Python3.12 admitted')
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'invoke -I -S -B')
    sys.addaudithook(readonly_audit)
    started = time.monotonic()
    try:
        PINS = PinSet(args.base, args.contract, args.phase1, args.phase2)
    except Exception as error:
        print(json.dumps(dict(status='INPUT_PIN_FAILURE', error=str(error))), flush=True)
        return 2
    result, problem, after_ok = None, None, False
    try:
        # No normal import, repository import, or pyc. Every pin is verified first.
        module = types.ModuleType('pinned_chunk_transpose_model')
        module.__file__ = str(HERE / 'transpose_model.py')
        sys.modules[module.__name__] = module  # dataclass registration must precede exec.
        code = compile(PINS.cache[('own', 'transpose_model.py')], module.__file__, 'exec')
        exec(code, module.__dict__)
        MODEL = module
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                                   for cls in (SourceCorrespondence, ModelControls))
        result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    except Exception as error:
        problem = str(error)
    finally:
        try:
            PINS.verify_after()
            after_ok = True
        except Exception as error:
            problem = 'AFTER_PIN_FAILURE: ' + str(error)
    success = problem is None and result is not None and result.wasSuccessful()
    print(json.dumps(dict(status='PASS_SOURCE_AND_PYTHON_SIMULATED_TRANSPOSE_PROTOCOL_ONLY' if success else 'FAIL',
        executed_scala=False, executed_chisel=False, executed_rtl=False, executed_native_model=False,
        real_transport_ack_validation=False, numerical_dut_validation=False,
        response_service='CALLER_SUPPLIED_SIMULATED_FIXED_64B_MEMORY_RESPONSES_AND_ACKS',
        tests=0 if result is None else result.testsRun, full_cases=FULL_CASES,
        pins_before_and_after=after_ok, pinned_files=len(PINS.entries), manifest_sha256=PINS.manifest_sha256,
        seconds=round(time.monotonic() - started, 6), error=problem,
        limits='No actual wiring, receipt provenance, Scala compile/elaboration, transport drain/replay, arithmetic, publication, full chunk/block or hardware QoR proof.'), sort_keys=True), flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
