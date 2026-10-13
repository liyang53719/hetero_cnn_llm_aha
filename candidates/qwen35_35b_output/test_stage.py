"""Real norm transport/ACK admission witnesses; no O arithmetic in this suite.
Scripted norm computation isolates transport without forging terminal ledgers.
"""
from dataclasses import replace
import os
import struct
import time
from types import SimpleNamespace
import unittest

from . import stage as s
from ..qwen35_gdn_prefill import test_typed_dense as numeric


def setUpModule():
    numeric.setUpModule()
    if not os.environ.get('GDN_VECTOR16_LIBRARY'):
        raise ValueError('explicit GDN_VECTOR16_LIBRARY required')


class OutputStageTests(unittest.TestCase):
    def setUp(self):
        # Initial test setup, never an inter-stage reset by the helper.
        self.assertEqual(numeric.LIB.td_reset(), 0)
        self.matrix = s.dense.MatrixService(numeric.LIB)
        self.vector = s.Vector16(os.environ['GDN_VECTOR16_LIBRARY'],
                                 exception_policy=s.IEEE_POLICY)
        self.scalar = s.ConvScalar()
        self.memory = s.dense.TypedMemory()
        self.owner = s.StreamingProjectionOwner(s.NoPrefixWorkspace(0x100000000, 16384, 1, 2048))
        self.cursor = 0x100000
        self.active_output = None

    def tearDown(self):
        if self.active_output is not None and self.active_output.response is None:
            # Actual error terminal drains the admitted descriptor before the
            # next test's caller-owned initial reset. No O Matrix group exists.
            for _ in range(8):
                self.active_output.tick(abort=True)
                if self.active_output.response is not None:
                    break
            self.assertIsNotNone(self.active_output.response)
            self.assertIsNone(self.matrix.owner)
            self.assertFalse(self.active_output.output.published)

    def allocate(self, extent, raw=None):
        base = self.cursor
        self.cursor += extent + 64
        return (self.memory.allocate_output(base, extent) if raw is None else
                self.memory.add_readonly(base, raw))

    def produced(self, extent, tag):
        region = self.allocate(extent)
        for offset in range(0, extent, 64):
            identity = (tag << 32) | (offset // 64)
            self.memory.begin_write(s.norm.WriteCommand(region.base + offset, 1, identity))
            self.memory.write_data((0,) * 32, True)
            self.memory.acknowledge(s.norm.WriteAck(identity, False, 64))
        self.memory.publish(region.base, (tag, None, extent))
        return region

    def fixture(self, tokens=16, *, accept=True, fail_ack=False):
        extent = tokens * s.K * 2
        core, gate = self.produced(extent, 10), self.produced(extent, 11)
        gamma = self.allocate(512, struct.pack('<128f', *([1.] * 128)))
        output = self.allocate(extent)
        owner = s.norm.GatedNormOwner(self.scalar, heads=32, layout=s.GROUPED_35B)
        job = s.norm.GatedNormJob(12, core.base, gate.base, gamma.base,
                                  output.base, tokens, 32, s.GROUPED_35B)

        def transport_only(j):
            yield (j.core, None)
            for offset in range(0, j.write_bytes, 64):
                yield (j.output + offset, bytes(64))

        owner._compute = transport_only
        self.norm = s.norm.TypedGatedNormDriver(owner, self.memory, job)
        deadline = time.monotonic() + 30
        for _ in range(40000):
            self.assertLess(time.monotonic(), deadline, 'bounded actual norm transport')
            last_write = self.norm.pending_request is not None and self.norm.pending_request.write
            self.norm.tick(response_ready=accept, ack_error=bool(fail_ack and last_write))
            if self.norm.response is not None or not accept and owner.state == 'finish':
                break
        else:
            self.fail('norm transport budget')
        weight = self.allocate(s.WEIGHT_BYTES, bytes(s.WEIGHT_BYTES))
        destination = self.allocate(tokens * s.N * 2)
        self.args = dict(weight_base=weight.base, output_base=destination.base,
                         profile=s.FourProfile("four_k1024_test", "0"*64), tokens=tokens,
                         scalar=self.scalar, vector=self.vector, tag=13)
        return self.norm

    def prepare(self, **changes):
        args = dict(self.args, **changes)
        result = s.prepare_output_projection(self.norm, self.owner, self.matrix,
                                              self.memory, **args)
        self.active_output = result
        return result

    def reject(self, **changes):
        workspace = self.owner.workspace
        before = (self.owner.state, self.owner.responses, self.matrix.epoch,
                  self.matrix.resource_address, dict(self.matrix.counts),
                  tuple((key, id(region), region.published, set(region.written),
                         set(region.acknowledged)) for key, region in self.memory.regions.items()))
        with self.assertRaises(ValueError):
            self.prepare(**changes)
        self.assertIs(self.owner.workspace, workspace)
        self.assertEqual(before, (self.owner.state, self.owner.responses, self.matrix.epoch,
                  self.matrix.resource_address, dict(self.matrix.counts),
                  tuple((key, id(region), region.published, set(region.written),
                         set(region.acknowledged)) for key, region in self.memory.regions.items())))
        self.assertIsNone(self.matrix.owner)

    def test_actual_norm_to_m16_descriptor_retains_resources(self):
        self.fixture()
        self.check_descriptor(16)

    def test_m128_full_transport_descriptor_only(self):
        self.fixture(128)
        self.check_descriptor(128)

    def check_descriptor(self, tokens):
        identity = (id(self.owner), id(self.owner.a_banks), id(self.owner.b_banks),
                    id(self.memory), id(self.scalar), id(self.vector),
                    self.matrix.resource_address, self.matrix.epoch)
        d = self.prepare()
        self.assertIs(type(d), s.TypedStreamingProjectionDriver)
        self.assertIs(d.a, self.norm.output)
        self.assertEqual((d.job.m,d.job.k,d.job.n),(tokens,4096,2048))
        self.assertEqual(d.output.extent,tokens*2048*2)
        self.assertFalse(d.output.published or d.output.written)
        self.assertIsNone(self.matrix.owner)
        self.assertEqual(d.coordinator.state,'partialFlush')
        self.assertEqual(numeric.LIB.matrix_dense_fmas(),0)
        self.assertEqual(identity,(id(self.owner),id(self.owner.a_banks),id(self.owner.b_banks),
            id(self.memory),id(self.scalar),id(self.vector),self.matrix.resource_address,self.matrix.epoch))
        self.assertIsNone(self.scalar.client);self.assertIsNone(self.vector.client)

    def test_region_or_receipt_cannot_replace_actual_norm_driver(self):
        self.fixture()
        driver = self.norm
        for replacement in (driver.output, driver.response, SimpleNamespace(**vars(driver))):
            self.norm = replacement
            self.reject()
        self.norm = driver

    def test_readonly_output_cannot_masquerade_as_norm_producer(self):
        self.fixture()
        self.norm.output.readonly = True
        self.reject()

    def test_replaced_region_identity_rejected(self):
        self.fixture()
        self.norm.output = self.produced(self.norm.job.write_bytes, 90)
        self.reject()

    def test_missing_norm_ack_rejected(self):
        self.fixture()
        self.norm.output.acknowledged.remove(self.norm.output.extent - 64)
        self.reject()

    def test_real_held_success_is_not_accepted_terminal(self):
        self.fixture(accept=False)
        self.assertIsNone(self.norm.response)
        self.assertEqual(self.norm.owner.state, 'finish')
        self.reject()
        self.norm.tick()
        self.assertIsNotNone(self.norm.response)

    def test_real_failed_norm_ack_cannot_admit_o(self):
        self.fixture(fail_ack=True)
        self.assertIsNotNone(self.norm.response.status)
        self.assertFalse(self.norm.output.published)
        self.reject()

    def test_wrong_or_nonstateless_success_receipt_rejected(self):
        self.fixture()
        receipt = self.norm.response
        for change in (dict(tag=99), dict(write_bytes=64), dict(staging_complete=False),
                       dict(state_committed=True), dict(history_committed=True),
                       dict(generation_advanced=True), dict(status='Aborted')):
            self.norm.response = replace(receipt, **change)
            self.reject()
        self.norm.response = receipt
        self.norm.owner.counts['owner_results'] = 0
        self.reject()

    def test_pending_norm_transport_or_replaced_scalar_rejected(self):
        self.fixture()
        self.norm.pending_request = object()
        self.reject()
        self.norm.pending_request = None
        self.reject(scalar=s.ConvScalar())

    def test_output_extent_freshness_and_alias_rejected(self):
        self.fixture()
        small=self.allocate(64)
        self.reject(output_base=small.base)
        self.reject(output_base=self.norm.output.base)
        self.memory.regions[self.args['output_base']].acknowledged.add(0)
        self.reject()

    def test_wrong_shape_or_numeric_policy_rejected(self):
        self.fixture()
        for changes in (dict(tokens=1),dict(tokens=True),dict(tag=self.norm.job.tag),
                        dict(profile='ascending'),dict(profile=s.FourProfile('x','bad'))):
            self.reject(**changes)

    def test_live_partial_or_busy_shared_resource_rejected(self):
        self.fixture()
        self.owner.tiles.tags[0].live = True
        self.reject()
        self.owner.tiles.tags[0].live = False
        self.vector.client = object()
        self.reject()
        self.vector.client = None


if __name__ == '__main__':
    unittest.main()
