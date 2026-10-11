"""Bridge control with an opaque SFU dependency, not an arithmetic simulation."""
import importlib.util
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location("ffn_bridge_control", Path(__file__).with_name("bridge_model.py"))
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)
m = b.m


def prepare(bank, slot, cols=32):
    c = m.Control(0, slot, 7, 0, 16, cols)
    bank.tick(control=c)
    for i in range(cols):
        bank.tick(write=m.Write(slot, 7, 0, i, tuple(0x3f000000+i*16+j for j in range(16))))
        bank.tick()
    bank.tick(control=m.Control(1, slot, 7, 0, 16, cols))


class BridgeTests(unittest.TestCase):
    def make(self, up_cols=32, arithmetic=lambda gate, up: (gate, False)):
        bank = m.TileBankModel()
        prepare(bank, 0)
        prepare(bank, 1, up_cols)
        return b.BridgeModel(bank, arithmetic)

    def advance(self, bridge, until, limit=2000):
        for tick in range(limit):
            if until():
                return
            bridge.tick(sfu_ready=tick % 4 != 0, bank_ready=tick % 5 != 0)
        self.fail("bounded modeled bridge did not reach target state")

    def test_mismatched_sealed_input_geometry_never_writes_or_completes(self):
        bridge = self.make(up_cols=64)
        before = bridge.banks.counters.copy()
        e = bridge.tick(start=b.Invocation(7, 0, 16, 32))
        self.assertTrue(e['start_fire'])
        self.assertEqual(bridge.state, 'locked')
        for _ in range(5):
            self.assertFalse(bridge.tick()['complete'])
        self.assertEqual(bridge.requests, 0)
        self.assertFalse(bridge.banks.tags[2].live)
        self.assertEqual(bridge.banks.counters['write_requests'], before['write_requests'])

    def test_ordered_pipeline_and_release_are_observed_before_complete(self):
        bridge = self.make()
        bridge.tick(start=b.Invocation(7, 0, 16, 32))
        self.advance(bridge, lambda: bridge.state == 'releaseUp')
        e = bridge.tick()
        self.assertTrue(e['ctl_fire'])
        self.assertFalse(e['complete'])
        self.assertEqual(bridge.state, 'retire')
        self.assertTrue(bridge.tick()['complete'])
        self.assertEqual(bridge.requests, 32)
        self.assertEqual(bridge.completions, 1)
        self.assertFalse(bridge.tick()['complete'])
        self.assertTrue(bridge.banks.tags[2].sealed)
        self.assertFalse(any(t.live for t in bridge.banks.tags[:2]))

    def test_invalid_final_release_and_retire_edge_abort_cannot_publish(self):
        for abort in (False, True):
            bridge = self.make()
            bridge.tick(start=b.Invocation(7, 0, 16, 32))
            self.advance(bridge, lambda: bridge.state == 'releaseUp')
            if not abort:
                # Corrupt control state after valid start: admission fire is
                # not proof of a legal release. Source bank poisons next edge.
                bridge.banks.tags[1].consumed -= 1
            self.assertFalse(bridge.tick()['complete'])
            self.assertFalse(bridge.tick(abort=abort)['complete'])
            self.assertEqual(bridge.completions, 0)
            self.assertTrue(bridge.poison)

    def test_accepted_write_drains_after_abort_and_coordinated_reset_recovers(self):
        bridge = self.make()
        bridge.tick(start=b.Invocation(7, 0, 16, 32))
        self.advance(bridge, lambda: bridge.banks.pending is not None and bridge.banks.pending[0] == 'write')
        self.assertTrue(bridge.tick(abort=True)['rmw_commit'])
        self.assertEqual(bridge.state, 'drain')
        self.assertEqual(bridge.tick()['state'], 'locked')
        self.advance(bridge, lambda: bridge.state == 'locked')
        self.assertEqual(bridge.completions, 0)
        self.assertTrue(bridge.banks.tags[2].live)
        bridge.tick(coordinated_reset=True)
        prepare(bridge.banks, 0)
        prepare(bridge.banks, 1)
        bridge.tick(start=b.Invocation(7, 0, 16, 32))
        self.advance(bridge, lambda: bridge.completions == 1)

    def test_idle_abort_keeps_external_response_routed_and_stable(self):
        bridge = self.make()
        bridge.banks.tick(read=m.Read(0, 7, 0, 0))
        bridge.banks.tick(response_ready=False)
        held = bridge.banks.response
        for _ in range(5):
            e = bridge.tick(abort=True)
            self.assertEqual(e['response'], held)
            self.assertFalse(e['response_fire'])
            self.assertFalse(bridge.busy)
        self.assertTrue(bridge.tick(external_response_ready=True)['response_fire'])

    def test_sfu_error_drains_without_act_publication(self):
        bridge = self.make(arithmetic=lambda gate, up: (gate, True))
        bridge.tick(start=b.Invocation(7, 0, 16, 32))
        self.advance(bridge, lambda: bridge.state == 'locked')
        self.assertEqual(bridge.requests, 1)
        self.assertEqual(bridge.banks.tags[2].produced, 0)
        self.assertFalse(bridge.banks.tags[2].sealed)
        self.assertEqual(bridge.completions, 0)


if __name__ == '__main__':
    unittest.main()
