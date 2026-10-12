"""Small numeric-capture transport/identity guards; no real tensors required."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ffn_drain_numeric_check_tests", HERE / "check_numeric.py")
check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check
spec.loader.exec_module(check)


def command(address=check.ACT_BASE, beats=2, tag=1):
    return SimpleNamespace(address=address, beats=beats, tag=tag)


def beat(value=7, last=False, mask=check.FULL_MASK):
    return SimpleNamespace(words=(value,) * 16, last=last, mask=mask)


def ack(tag=1, error=False, nbytes=128):
    return SimpleNamespace(tag=tag, error=error, nbytes=nbytes)


class DestinationTests(unittest.TestCase):
    def setUp(self):
        self.ddr = check.DestinationMemory(16)

    def test_descriptor_and_data_are_separate_accepted_obligations(self):
        before = bytes(self.ddr.data)
        self.ddr.accept_command(command())
        self.assertEqual(bytes(self.ddr.data), before)
        self.ddr.accept_data(beat())
        self.assertEqual(self.ddr.data_bytes, 64)
        self.assertEqual(self.ddr.ack_bytes, 0)
        self.ddr.accept_data(beat(last=True))
        self.assertEqual(self.ddr.ack_bytes, 0)
        self.ddr.accept_ack(ack())
        self.assertEqual(self.ddr.ack_bytes, 128)

    def test_rejects_data_without_descriptor(self):
        with self.assertRaisesRegex(ValueError, "without descriptor"):
            self.ddr.accept_data(beat())

    def test_rejects_partial_mask_before_modifying_memory(self):
        before = bytes(self.ddr.data)
        self.ddr.accept_command(command())
        with self.assertRaisesRegex(ValueError, "physical mask"):
            self.ddr.accept_data(beat(mask=check.FULL_MASK ^ 1))
        self.assertEqual(bytes(self.ddr.data), before)

    def test_rejects_descriptor_crossing_1kib(self):
        with self.assertRaisesRegex(ValueError, "1KiB"):
            self.ddr.accept_command(command(check.ACT_BASE + 960))

    def test_rejects_unmapped_output_or_canary_address(self):
        for address in (check.ACT_BASE - 64, check.ACT_BASE + self.ddr.extent,
                        check.DESTINATION_BASES["gate"], check.DESTINATION_BASES["up"]):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, "address-only act region"):
                self.ddr.accept_command(command(address, beats=1))

    def test_rejects_early_wrong_tag_or_error_ack(self):
        self.ddr.accept_command(command())
        with self.assertRaisesRegex(ValueError, "before all"):
            self.ddr.accept_ack(ack())
        self.ddr.accept_data(beat())
        self.ddr.accept_data(beat(last=True))
        for invalid in (ack(tag=2), ack(error=True), ack(nbytes=64)):
            with self.subTest(ack=invalid), self.assertRaisesRegex(ValueError, "tag/status/byte"):
                self.ddr.accept_ack(invalid)
        self.assertEqual(self.ddr.ack_bytes, 0)

    def test_rejects_duplicate_write_address(self):
        self.ddr.accept_command(command())
        self.ddr.accept_data(beat())
        self.ddr.accept_data(beat(last=True))
        self.ddr.accept_ack(ack())
        self.ddr.accept_command(command(tag=2))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.ddr.accept_data(beat())

    def test_rejects_last_mismatch(self):
        self.ddr.accept_command(command())
        with self.assertRaisesRegex(ValueError, "last marker"):
            self.ddr.accept_data(beat(last=True))

    def test_rejects_coverage_and_observation_before_ack(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.ddr.validate_and_read(0, 32)
        self.ddr.accept_command(command())
        self.ddr.accept_data(beat())
        self.ddr.accept_data(beat(last=True))
        with self.assertRaisesRegex(ValueError, "before all matching"):
            self.ddr.validate_and_read(0, 32)

    def fill_small_window(self, ng=160):
        for m in range(16):
            tag = m + 1
            self.ddr.accept_command(command(check.ACT_BASE + (m * check.SOURCE_N + ng) * 4, tag=tag))
            self.ddr.accept_data(beat(value=m + 1))
            self.ddr.accept_data(beat(value=m + 17, last=True))
            self.ddr.accept_ack(ack(tag=tag))
        return ng

    def test_full_stride_nonzero_window_and_canaries(self):
        ng = self.fill_small_window()
        actual, report = self.ddr.validate_and_read(ng, 32)
        expected = [value for m in range(16) for value in ([m + 1] * 16 + [m + 17] * 16)]
        self.assertEqual(actual, expected)
        self.assertEqual(report["written_bytes"], 16 * 32 * 4)
        self.assertEqual(report["untouched_bytes_including_canaries"], 16 * (8960 - 32) * 4 + 128)

    def test_canary_corruption_is_detected(self):
        ng = self.fill_small_window()
        self.ddr.data[0] ^= 1
        with self.assertRaisesRegex(ValueError, "canary"):
            self.ddr.validate_and_read(ng, 32)

    def test_untouched_row_region_corruption_is_detected(self):
        ng = self.fill_small_window()
        self.ddr.data[check.CANARY_BYTES] ^= 1
        with self.assertRaisesRegex(ValueError, "untouched"):
            self.ddr.validate_and_read(ng, 32)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ffn_drain_capture_guard_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pins = json.loads((HERE / "precision_pins.json").read_text())
        for name in self.pins["sources"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((check.ROOT / name).read_bytes())

    def test_source_guards_do_not_require_real_data_for_unit_tests(self):
        self.assertFalse((self.root / "work").exists())
        with patch.object(check, "ROOT", self.root):
            self.assertEqual(check.load_pins(False)["sources"], self.pins["sources"])

    def test_real_capture_requires_local_provenance(self):
        with patch.object(check, "ROOT", self.root), self.assertRaises(FileNotFoundError):
            check.load_pins()

    def test_changed_arithmetic_source_is_rejected(self):
        name = "candidates/qwen2_resident_matrix/ffn_window/numeric_recipe.cpp"
        (self.root / name).write_text("changed arithmetic")
        with patch.object(check, "ROOT", self.root), self.assertRaisesRegex(ValueError, "source identity drift"):
            check.load_pins(False)

    def test_post_capture_source_drift_is_fatal(self):
        name = next(iter(self.pins["sources"]))
        report = {"source_sha256": {name: self.pins["sources"][name]}}
        (self.root / name).write_text("changed after snapshot")
        with patch.object(check, "ROOT", self.root), self.assertRaisesRegex(ValueError, "source changed during frozen"):
            check.verify_capture_sources(report)
        self.assertEqual(report["source_changed_since_freeze"], [name])

    def test_no_second_arithmetic_recipe(self):
        self.assertFalse((HERE / "numeric_recipe.cpp").exists())
        self.assertIn("candidates/qwen2_resident_matrix/ffn_window/numeric_recipe.cpp", self.pins["sources"])

    def test_real_capture_cannot_replace_existing_evidence(self):
        with self.assertRaisesRegex(ValueError, "new evidence"):
            check.run(self.root, 16)


class SmallDrainTests(unittest.TestCase):
    """Actual new owner with synthetic act tile port writes; never full FMA."""
    @classmethod
    def setUpClass(cls):
        cls.model = check.load_module("ffn_drain_numeric_synthetic_model", HERE / "model.py")

    def setUp(self):
        self.prepare_tile()

    def prepare_tile(self, cols=32):
        self.case = {"rows": 16, "cols": cols, "ng": 160, "identity": 1234}
        m = self.model
        self.owner = m.FfnDrainOwnerModel(m.PrefixWorkspace(0x10000000, 16384, 1234, 2560),
                                         enable_ffn_drain=True, enable_ffn_window=True, enable_ffn_tiles=True)
        tile = check.OwnerTilePort(self.owner)
        self.assertTrue(tile.tick(control=m.Control(0, 2, 1234, 160, 16, cols))["ctl_fire"])
        for n in range(cols):
            words = tuple((r + 1) * 1024 + n for r in range(16))
            self.assertTrue(tile.tick(write=m.Write(2, 1234, 160, n, words))["write_fire"])
            tile.tick()
        self.assertTrue(tile.tick(control=m.Control(1, 2, 1234, 160, 16, cols))["ctl_fire"])

    def test_final_ack_stall_and_actual_port_driven_row_repacking(self):
        ddr = check.DestinationMemory(16)
        trace = io.BytesIO()
        actual, report = check.execute_drain(self.model, self.owner, self.case, ddr, trace,
                                             time.monotonic() + 10, final_ack_stall=7)
        self.assertEqual(actual, [(r + 1) * 1024 + n for r in range(16) for n in range(32)])
        self.assertEqual(report["accepted"]["final_ack_stall_ticks"], 7)
        self.assertEqual(report["before_final_ack"]["data_bytes"], 2048)
        self.assertLess(report["before_final_ack"]["ack_bytes"], 2048)
        self.assertTrue(report["before_final_ack"]["slot2_live"])
        self.assertEqual(report["ddr"]["successful_ack_bytes"], 2048)
        self.assertGreater(report["accepted"]["write_data_stall_ticks"], 0)
        events = [json.loads(line) for line in trace.getvalue().splitlines()]
        commands = [e["events"]["write_command"] for e in events if e["events"].get("write_command_fire")]
        self.assertTrue(all(c["address"] // 1024 == (c["address"] + c["beats"] * 64 - 1) // 1024 for c in commands))
        self.assertFalse(self.owner.tiles.tags[2].live)

    def test_idle_owner_preserves_external_response_under_stall(self):
        port = check.OwnerTilePort(self.owner)
        read = self.model.Read(2, 1234, 160, 0)
        self.assertTrue(port.tick(read=read, response_ready=False)["read_fire"])
        held = None
        for _ in range(7):
            event = port.tick(response_ready=False)
            if event["response"] is not None:
                if held is not None:
                    self.assertEqual(event["response"], held)
                held = event["response"]
            self.assertFalse(event["response_fire"])
            self.assertFalse(self.owner.tiles.poison)
            self.assertIsNone(self.owner.error)
        self.assertIsNotNone(held)
        event = port.tick(response_ready=True)
        self.assertTrue(event["response_fire"])
        self.assertEqual(event["response"], held)
        self.assertEqual(port.counts["response_fire"], 1)
        self.assertEqual(port.counts["owner_idle_ticks"], 9)

    def test_actual_owner_splits_each_nonzero_window_row_at_1kib(self):
        self.prepare_tile(cols=160)
        trace = io.BytesIO()
        actual, report = check.execute_drain(self.model, self.owner, self.case, check.DestinationMemory(16),
                                             trace, time.monotonic() + 10)
        self.assertEqual(actual, [(r + 1) * 1024 + n for r in range(16) for n in range(160)])
        events = [json.loads(line) for line in trace.getvalue().splitlines()]
        commands = [e["events"]["write_command"] for e in events if e["events"].get("write_command_fire")]
        self.assertEqual([c["beats"] for c in commands], [6, 4] * 16)
        self.assertEqual(report["ddr"]["written_bytes"], 16 * 160 * 4)
        self.assertEqual(report["ddr"]["successful_acks"], 32)

    def test_held_success_is_rejected_if_acceptance_edge_poisoned(self):
        for fault in ("abort", "unexpected_ack"):
            with self.subTest(fault=fault):
                self.prepare_tile()
                original_tick = self.owner.tick
                injected = []
                def poison_on_result_edge(**inputs):
                    if self.owner.ports().get("drain_result") is not None:
                        injected.append(fault)
                        if fault == "abort":
                            inputs["abort"] = True
                        else:
                            inputs["write_ack"] = self.model.WriteAck(0xFFFFFFFF, False, 64)
                    return original_tick(**inputs)
                trace = io.BytesIO()
                with patch.object(self.owner, "tick", poison_on_result_edge), self.assertRaisesRegex(
                        ValueError, "owner failed after edge"):
                    check.execute_drain(self.model, self.owner, self.case, check.DestinationMemory(16),
                                        trace, time.monotonic() + 10)
                self.assertEqual(injected, [fault])
                final = json.loads(trace.getvalue().splitlines()[-1])
                self.assertTrue(final["events"]["drain_result_fire"])
                self.assertTrue(final["events"]["drain_result"]["committed"])
                self.assertTrue(any(final["events"]["post_tick_owner_status"].values()))

    def test_actual_owner_wrong_ack_never_reports_success(self):
        m = self.model
        q = m.FfnDrainRequest(m.ActivationJob(m=16, a=check.DESTINATION_BASES["gate"],
              b=check.DESTINATION_BASES["up"], dst=check.ACT_BASE, tag=17, write_bytes=16 * 8960 * 4),
              1234, 160, 32)
        self.assertTrue(self.owner.tick(drain=q)["drain_fire"])
        received = None
        for _ in range(1000):
            ports = self.owner.ports()
            kw = {}
            if ports["write_ack_ready"]:
                kw["write_ack"] = m.WriteAck(self.owner.accepted_write.tag + 1, False,
                                             self.owner.accepted_write.beats * 64)
            event = self.owner.tick(**kw)
            if event.get("drain_result_fire"):
                received = event["drain_result"]
                break
        self.assertIsNotNone(received)
        self.assertFalse(received.committed)
        self.assertEqual(received.ddr_write_bytes, 0)
        self.assertTrue(self.owner.tiles.poison)


if __name__ == "__main__":
    unittest.main()
