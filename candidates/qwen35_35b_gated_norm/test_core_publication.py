"""Fullshape core-publication transport integration, not chunk arithmetic QA.

The chunk _compute generator is explicitly scripted: it reads one real Prep
beat and writes EVERY real scratch/state/core beat through the actual typed
transport. No terminal, ACK ledger, source hash or publication is injected.
Prep, Z and Conv-history fixtures are transport-only producers. GatedNorm uses
its unchanged actual arithmetic, real accepted reads/writes/ACKs and terminal.
This does not validate checkpoint arithmetic, the full chunk numerical result,
RTL, public Command128, a block state commit, or native numerical acceptance.
"""
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
import time
import unittest

from candidates.qwen35_35b_exp.gate_scalar import GateScalar
from candidates.qwen35_gdn_prefill.chunk import model as c
from candidates.qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY, build_library
from candidates.qwen35_gdn_prefill.gated_norm import model as norm
from candidates.qwen35_gdn_prefill.rms_owner import word
from .core_publication import publish_core_intermediate


HERE = Path(__file__).resolve().parent


@contextmanager
def changed(obj, name, value):
    original = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, original)


class CorePublicationTests(unittest.TestCase):
    def allocate(self, extent, raw=None):
        base = self.cursor
        self.cursor += extent + 64
        return (self.memory.allocate_output(base, extent) if raw is None else
                self.memory.add_readonly(base, raw))

    def producer(self, raw, *, publish, tag):
        """Synthetic fixture producer: real write data and each accepted ACK."""
        region = self.allocate(len(raw))
        for offset in range(0, len(raw), 64):
            identity = (tag << 32) | (offset // 64)
            self.memory.begin_write(c.WriteCommand(region.base + offset, 1, identity))
            self.memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True)
            self.memory.acknowledge(c.WriteAck(identity, False, 64))
        if publish:
            self.memory.publish(region.base, (tag, None, len(raw)))
        return region

    def fixture(self):
        library = os.environ.get('GDN_VECTOR16_LIBRARY')
        if library is None:
            library = build_library(Path('work/core_norm_test_vector'))
        self.scalar = GateScalar(enable_softplus=True, enable_ieee_exp=True,
                                 enable_gate_softplus=True)
        self.vector = Vector16(library, exception_policy=IEEE_POLICY)
        self.memory, self.cursor, self.tokens = c.TypedMemory(), 0x100000, 16
        prep = self.producer(bytes(self.tokens * c.GROUPED_35B.core_row_bytes),
                             publish=True, tag=70)
        self.history = self.producer(bytes.fromhex('a51234ef') * (8192 * 2),
                                     publish=False, tag=71)
        shape = c.ChunkJob(72, 0, 0, 0, 0, 0, self.tokens, heads=32,
                           layout=c.GROUPED_35B, cumsum_policy=c.GUARDED_CUMSUM,
                           exp_policy=c.ep.IEEE_EXP)
        state_in, state_out = self.allocate(shape.state_bytes), self.allocate(shape.state_bytes)
        output, scratch = self.allocate(shape.output_bytes), self.allocate(shape.scratch_bytes)
        job = replace(shape, input=prep.base, state_in=state_in.base, state_out=state_out.base,
                      output=output.base, scratch=scratch.base)
        owner = c.ChunkOwner(self.scalar, self.vector, heads=32, key_dim=128, value_dim=128,
                             host_batch=True, layout=c.GROUPED_35B,
                             cumsum_policy=c.GUARDED_CUMSUM, exp_policy=c.ep.IEEE_EXP)

        def transport_only_script(j):
            yield (j.input, None)
            for base, extent, beat in (
                (j.scratch, j.scratch_bytes, bytes.fromhex('2a5ac33c') * 16),
                (j.state_out, j.state_bytes, bytes.fromhex('4c39622f') * 16),
                (j.output, j.output_bytes, struct.pack('<32H', *([0x3f80] * 32))),
            ):
                for offset in range(0, extent, 64):
                    yield (base + offset, beat)

        owner._compute = transport_only_script
        self.driver = c.TypedChunkDriver(owner, self.memory, job)
        self.private = (self.driver.state_out, self.driver.scratch, self.history, state_in)
        return self.driver

    def publish(self, **overrides):
        args = dict(driver=self.driver, history=self.history, scalar=self.scalar,
                    vector=self.vector, tokens=self.tokens)
        args.update(overrides)
        return publish_core_intermediate(**args)

    def assert_private(self, snapshots, receipt):
        for region, (raw, written, acknowledged, published) in zip(self.private, snapshots):
            self.assertEqual(region.raw(), raw)
            self.assertEqual(region.written, written)
            self.assertEqual(region.acknowledged, acknowledged)
            self.assertEqual(region.published, published)
            self.assertFalse(region.published)
            with self.assertRaisesRegex(ValueError, 'read before producer terminal'):
                self.memory.read64(region.base)
        self.assertIs(self.driver.response, receipt)
        self.assertEqual(self.driver.job.expected_generation, 0)
        self.assertEqual(receipt.expected_generation, 0)
        self.assertFalse(receipt.state_committed or receipt.history_committed or receipt.generation_advanced)

    def reject_unchanged(self, **overrides):
        before = tuple((r.published, c.sha(r.raw())) for r in (
            self.driver.output, self.driver.state_out, self.driver.scratch, self.history))
        with self.assertRaises(ValueError):
            self.publish(**overrides)
        after = tuple((r.published, c.sha(r.raw())) for r in (
            self.driver.output, self.driver.state_out, self.driver.scratch, self.history))
        self.assertEqual(before, after)

    def run_norm(self, fault, private_snapshots, chunk_receipt):
        gate = self.producer(struct.pack('<H', 0x3f00) * (self.tokens * 4096),
                             publish=True, tag=73 if fault == 'core_read' else 74)
        weight = self.allocate(512, struct.pack('<128I', *([word(1.0)] * 128)))
        output = self.allocate(self.tokens * 8192)
        owner = norm.GatedNormOwner(self.scalar, heads=32, layout=c.GROUPED_35B)
        job = norm.GatedNormJob(75 if fault == 'core_read' else 76,
                                self.driver.output.base, gate.base, weight.base, output.base,
                                self.tokens, 32, c.GROUPED_35B)
        d = norm.TypedGatedNormDriver(owner, self.memory, job)
        self.assertIs(d.core, self.driver.output)
        self.assertIs(d.gate, gate)
        self.assertIs(owner.scalar, self.scalar)
        public_before = tuple((r, r.raw()) for r in (self.driver.input, self.driver.output, gate, weight))
        injected, held = False, None
        deadline = time.monotonic() + 90
        for _ in range(20000):
            self.assertLess(time.monotonic(), deadline, 'bounded actual GatedNorm integration')
            q = d.pending_request
            target = q is not None and (
                not q.write and q.address == job.core if fault == 'core_read' else
                q.write and q.address == job.output + job.write_bytes - 64)
            options = {'response_ready': False}
            if target and not injected:
                physical, pending = self.memory.pending, d.pending
                for _ in range(2):
                    d.tick(memory_response_ready=False, response_ready=False)
                    self.assertIs(self.memory.pending, physical)
                    self.assertIs(d.pending, pending)
                    self.assertFalse(output.published)
                options['read_error' if fault == 'core_read' else 'ack_error'] = True
                injected = True
            d.tick(**options)
            if owner.state == 'finish':
                held = owner.result
                break
        else:
            self.fail('actual GatedNorm terminal watchdog')
        self.assertTrue(injected)
        self.assertEqual(held.status, 'Memory')
        self.assertFalse(held.staging_complete)
        for _ in range(2):
            d.tick(response_ready=False)
            self.assertIs(owner.result, held)
            self.assertIsNone(d.response)
        d.tick()
        self.assertIs(d.response, held)
        self.assertFalse(output.published)
        self.assertEqual(owner.counts['owner_results'], 1)
        self.assertIsNone(self.memory.pending)
        self.assertIsNone(d.pending)
        self.assertIsNone(d.pending_request)
        self.assertIsNone(d.pending_write)
        self.assertIsNone(self.scalar.client)
        self.assertIsNone(self.vector.client)
        self.assertTrue(self.driver.output.published)
        self.assertIs(self.memory.exact(job.core, job.write_bytes, readable=True), self.driver.output)
        for region, raw in public_before:
            self.assertTrue(region.published)
            self.assertEqual(region.raw(), raw)
        self.assert_private(private_snapshots, chunk_receipt)
        if fault == 'core_read':
            self.assertEqual(held.write_bytes, 0)
            self.assertEqual(output.written, set())
            self.assertEqual(output.acknowledged, set())
        else:
            self.assertEqual(held.write_bytes, job.write_bytes - 64)
            self.assertEqual(output.written, set(range(0, job.write_bytes, 64)))
            self.assertEqual(output.acknowledged, set(range(0, job.write_bytes - 64, 64)))
            self.assertGreater(self.scalar.calls['sqrt'], 0)
            self.assertGreater(self.scalar.calls['exp_negative'], 0)
        return dict(fault=fault, accepted_terminal=True, status=held.status,
                    actual_gated_norm_arithmetic=True, write_bytes=held.write_bytes,
                    output_published=False, private_spans_unchanged=True)

    def test_fullshape_staging_publication_and_downstream_failure_isolation(self):
        started = time.monotonic()
        d = self.fixture()
        # An admitted driver and an in-flight actual read grant no publication.
        self.reject_unchanged()
        d.tick()
        self.assertIsNotNone(d.pending)
        self.reject_unchanged()
        deadline = time.monotonic() + 120
        limit = 2 * ((d.job.scratch_bytes + d.job.write_bytes) // 64 + 1) + 4
        for tick in range(limit):
            if tick % 10000 == 0:
                self.assertLess(time.monotonic(), deadline, 'bounded transport-only chunk fixture')
            q = d.pending_request
            if q is not None and q.write and q.address == d.job.output + d.job.output_bytes - 64:
                break
            d.tick(response_ready=False)
        else:
            self.fail('last chunk output ACK not reached')
        self.assertEqual(d.output.acknowledged, set(range(0, d.job.output_bytes - 64, 64)))
        self.reject_unchanged()
        d.tick(response_ready=False)
        held = d.owner.result
        self.assertIsNotNone(held)
        self.assertTrue(held.staging_complete)
        self.assertIsNone(d.response)
        self.reject_unchanged()
        for _ in range(2):
            d.tick(response_ready=False)
            self.assertIs(d.owner.result, held)
        d.tick()
        self.assertIs(d.response, held)
        self.assertEqual(d.owner.counts['owner_results'], 1)
        self.assertEqual(d.counts['write_bytes'], d.job.scratch_bytes + d.job.write_bytes)
        self.assertEqual(d.counts['source_read_bytes'], 64)
        self.assertEqual(self.scalar.calls, {})
        self.assertEqual(self.vector.calls, {})
        for region in (d.output, d.state_out, d.scratch, self.history):
            self.assertEqual(region.written, region.acknowledged)
            self.assertEqual(region.written, set(range(0, region.extent, 64)))
            self.assertFalse(region.published)

        invalid_receipts = [
            None, dict(status=None), replace(held, status='Memory'),
            replace(held, staging_complete=False), replace(held, tag=held.tag + 1),
            replace(held, output=held.output + 64), replace(held, state_out=held.state_out + 64),
            replace(held, output_bytes=held.output_bytes - 64),
            replace(held, state_bytes=held.state_bytes - 64),
            replace(held, write_bytes=held.write_bytes - 64),
            replace(held, expected_generation=1), replace(held, expected_generation=False),
            replace(held, state_committed=True), replace(held, history_committed=True),
            replace(held, generation_advanced=True), replace(held, model_ticks=0),
        ]
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt):
                with changed(d, 'response', receipt):
                    self.reject_unchanged()
        for tokens in (1, 128, True):
            with self.subTest(tokens=tokens):
                self.reject_unchanged(tokens=tokens)
        self.reject_unchanged(scalar=GateScalar(enable_ieee_exp=True))
        self.reject_unchanged(vector=object())
        self.reject_unchanged(history=d.state_out)
        same_address_copy = replace(self.history)
        self.reject_unchanged(history=same_address_copy)

        mutations = [
            (d, 'pending', object()), (d, 'pending_request', object()),
            (d, 'pending_write', object()), (self.memory, 'pending', object()),
            (self.scalar, 'client', object()), (self.vector, 'client', object()),
            (d, 'aborted', True), (d, 'resource_identity', ()),
            (d.owner, 'state', 'finish'), (d.owner, 'poison', True),
            (d.owner, 'result', held), (d.owner, 'request', object()),
            (d.owner, 'program', object()), (d.owner, 'job', replace(d.job)),
            (d.owner, 'ack_bytes', d.job.write_bytes - 64),
            (d.owner, 'identity', {}), (d, 'source_hashes', ('bad',)),
            (d, 'output', replace(d.output)), (d, 'state_out', replace(d.state_out)),
            (d, 'scratch', replace(d.scratch)),
        ]
        for obj, name, value in mutations:
            with self.subTest(mutation=name, value_type=type(value).__name__):
                with changed(obj, name, value):
                    self.reject_unchanged()
        for key, value in (('owner_results', 0), ('owner_results', 2), ('scratch_ack_bytes', 0)):
            with self.subTest(owner_count=key, value=value):
                old = d.owner.counts[key]
                try:
                    d.owner.counts[key] = value
                    self.reject_unchanged()
                finally:
                    d.owner.counts[key] = old
        for region in (d.output, d.state_out, d.scratch, self.history):
            for field in ('written', 'acknowledged'):
                with self.subTest(region=region.base, field=field):
                    with changed(region, field, getattr(region, field) - {0}):
                        self.reject_unchanged()
            with self.subTest(region=region.base, field='published'):
                with changed(region, 'published', True):
                    self.reject_unchanged()
        # Publication must remain fail-closed even if a private guard is corrupt.
        original_guard = self.history.storage[0]
        try:
            self.history.storage[0] ^= 1
            with self.assertRaises(ValueError):
                self.publish()
            self.assertFalse(d.output.published)
        finally:
            self.history.storage[0] = original_guard

        snapshots = tuple((r.raw(), r.written.copy(), r.acknowledged.copy(), r.published)
                          for r in self.private)
        receipt = self.publish()
        self.assertTrue(d.output.published)
        self.assertEqual(self.memory.read64(d.job.output), struct.pack('<32H', *([0x3f80] * 32)))
        self.assertIs(self.memory.exact(d.job.output, d.job.output_bytes, readable=True), d.output)
        self.assertEqual(receipt['core_sha256'], c.sha(d.output.raw()))
        self.assert_private(snapshots, held)
        self.reject_unchanged()  # no replay/double publication
        failures = [self.run_norm(fault, snapshots, held) for fault in ('core_read', 'final_ack')]
        report = dict(
            status='PASS_CORE_ONLY_TRANSPORT_AND_GATED_NORM_FAILURE_ISOLATION',
            tokens=self.tokens, chunk_full_geometry=[32, 128, 128],
            chunk_arithmetic='SCRIPTED_TRANSPORT_ONLY_NOT_NUMERICAL_ACCEPTANCE',
            source_read_bytes=d.counts['source_read_bytes'],
            actual_chunk_write_bytes=d.counts['write_bytes'],
            scratch_bytes=d.job.scratch_bytes, state_bytes=d.job.state_bytes,
            output_bytes=d.job.output_bytes, accepted_chunk_terminals=d.owner.counts['owner_results'],
            publication=receipt, downstream=failures,
            rtl_executed=False, native_acceptance=False, full_block=False,
            generation_advanced=False, host_seconds=time.monotonic() - started,
        )
        (Path('work/core_norm_integration_result.json')).write_text(json.dumps(report, indent=2) + '\n')

    def test_receipt_dictionary_cannot_masquerade_as_typed_driver(self):
        with self.assertRaisesRegex(ValueError, 'actual TypedChunkDriver'):
            publish_core_intermediate(dict(response=dict(status=None, staging_complete=True)),
                                      None, None, None, tokens=16)


if __name__ == '__main__':
    unittest.main(verbosity=2)
