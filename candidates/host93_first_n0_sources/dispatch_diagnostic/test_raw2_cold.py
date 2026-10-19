#!/usr/bin/env python3
"""Offline stdlib-only raw2 tests. Never performs raw GETs or native execution."""
from __future__ import annotations
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit("COLD_ISOLATION_REFUSED")
import os
import stat
import contextlib
import copy
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest

ADAPTER_BYTES = 18633
ADAPTER_SHA256 = "0924380e220161ddc0595fd2116c54ec83f1db08137484a25b4986915abba46d"

class TestLoaderRefused(ValueError):
    pass

def loader_guard(condition):
    if not condition:
        raise TestLoaderRefused("COLD_SOURCE_REFUSED")

def load_pinned_adapter(source):
    """One fd, one bounded read; pin checks precede same-buffer compile."""
    source = Path(source)
    loader_guard(source.is_absolute())
    for part in (source, *source.parents):
        loader_guard(not part.is_symlink())
    with source.open("rb") as stream:
        info = os.fstat(stream.fileno())
        loader_guard(stat.S_ISREG(info.st_mode) and info.st_size == ADAPTER_BYTES)
        data = stream.read(ADAPTER_BYTES + 1)
    loader_guard(len(data) == ADAPTER_BYTES and hashlib.sha256(data).hexdigest() == ADAPTER_SHA256)
    module = types.ModuleType("cold_raw2_adapter")
    module.__file__ = str(source)
    exec(compile(data, str(source), "exec", dont_inherit=True), module.__dict__)
    return module

# Explicit, closed test CLI; positional or relative repositories are refused.
loader_guard(len(sys.argv) == 3 and sys.argv[1] == "--repo")
REPO = Path(sys.argv[2])
loader_guard(REPO.is_absolute())
sys.argv[:] = [sys.argv[0]]
HERE = Path(__file__).absolute().parent
SOURCE = HERE / "raw2_adapter.py"
a = load_pinned_adapter(SOURCE)
original = a.load_original(REPO)
PLAN_PATH = Path(original.__file__).with_name("ACQUISITION_PLAN.json")
plan, helpers, shard = original.check_sources(REPO, PLAN_PATH)
SOURCE_PINS = {REPO / a.ORIGINAL_RELATIVE: (a.ORIGINAL_BYTES, a.ORIGINAL_SHA256),
               PLAN_PATH: (a.PLAN_BYTES, a.PLAN_SHA256)}
for pin in plan["sources"]:
    SOURCE_PINS[REPO / pin["path"]] = (pin["bytes"], pin["sha256"])
evidence = plan["platform_api_evidence"]
SOURCE_PINS[PLAN_PATH.parent / evidence["path"]] = (evidence["bytes"], evidence["sha256"])

def network_denial(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "http.client.connect"):
        raise RuntimeError("COLD_NETWORK_FORBIDDEN")
sys.addaudithook(network_denial)


class Response:
    def __init__(self, body=b"test", status=206, headers=None, url=None):
        self.body, self.status, self.reads, self.closed = body, status, [], False
        self.headers = Message()
        for key, value in (headers or [("Content-Range", "bytes 0-3/100"), ("Content-Length", "4")]):
            self.headers[key] = value
        self.url = url or plan["url"]
    def geturl(self):
        return self.url
    def read(self, length):
        self.reads.append(length)
        return self.body[:length]
    def close(self):
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class Raw2ColdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE, prefix=".cold-")
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def cli(self, *args):
        command = [sys.executable, "-I", "-S", "-B"]
        if sys.flags.optimize:
            command.append("-O")
        return subprocess.run(command + [str(SOURCE), *map(str, args)],
                              capture_output=True, text=True, timeout=15)
    def assert_refused_cli(self, *args):
        result = self.cli(*args)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        value = json.loads(result.stdout)
        self.assertEqual(value["status"], "RAW2_REFUSED")
        self.assertIn(value["code"], set(a.ORIGINAL_FAILURE_CODES.values()) | {"UNEXPECTED"})
        return value
    def fresh(self):
        return original.prepare_output(REPO, self.root / "raw2")
    def test_01_original_source_and_all_pins_unchanged(self):
        for path, (size, digest) in SOURCE_PINS.items():
            data = path.read_bytes()
            self.assertEqual(len(data), size)
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
    def test_02_full_real_source_plan_checked(self):
        self.assertEqual(len(plan["raw_tensors"]), 13)
        self.assertEqual(len(plan["requests"]), 22)
        self.assertEqual(sum(r["bytes"] for r in plan["requests"]), 94382080)
        self.assertNotIn("heteronpu", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        self.assertNotIn("torch", sys.modules)
    def test_03_exact_selection(self):
        tensors, requests = a.fixed_selection(original, plan)
        self.assertEqual(tensors, plan["raw_tensors"][:2])
        self.assertEqual(requests, plan["requests"][:2])
        self.assertEqual([r["index"] for r in requests], [0, 1])
        self.assertEqual(sum(r["bytes"] for r in requests), 789504)
    def test_04_all_request_field_mutations_refused(self):
        for row in (0, 1):
            for key in plan["requests"][row]:
                changed = copy.deepcopy(plan)
                changed["requests"][row][key] = None
                with self.subTest(row=row, field=key), self.assertRaises(original.Refused):
                    a.fixed_selection(original, changed)
    def test_05_all_tensor_field_mutations_refused(self):
        for row in (0, 1):
            for key in plan["raw_tensors"][row]:
                changed = copy.deepcopy(plan)
                changed["raw_tensors"][row][key] = None
                with self.subTest(row=row, field=key), self.assertRaises(original.Refused):
                    a.fixed_selection(original, changed)
    def test_06_added_keys_refused(self):
        for group in ("raw_tensors", "requests"):
            changed = copy.deepcopy(plan)
            changed[group][0]["additional"] = 0
            with self.subTest(group=group), self.assertRaises(original.Refused):
                a.fixed_selection(original, changed)
    def test_07_reordered_selection_refused(self):
        for group in ("raw_tensors", "requests"):
            changed = copy.deepcopy(plan)
            changed[group][0], changed[group][1] = changed[group][1], changed[group][0]
            with self.subTest(group=group), self.assertRaises(original.Refused):
                a.fixed_selection(original, changed)
    def test_08_bool_and_float_not_integer(self):
        for value in (False, 0.0):
            changed = copy.deepcopy(plan)
            changed["requests"][0]["index"] = value
            with self.subTest(value=value), self.assertRaises(original.Refused):
                a.fixed_selection(original, changed)
    def test_09_source_only_cli(self):
        out = self.root / "not-created"
        result = self.cli("--repo", REPO, "--out", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {"status": "SOURCE_CHECK_ONLY", "selected_tensors": 2,
                                                   "requests": 2, "bytes": 789504, "raw_GETs": 0})
        self.assertFalse(out.exists())
    def test_10_cli_missing_repo_is_finite(self):
        self.assert_refused_cli()
    def test_11_cli_arbitrary_argument_not_echoed(self):
        marker = "https://example.invalid/private?token=secret"
        result = self.cli("--repo", REPO, "--bad", marker)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertNotIn(marker, result.stdout)
        self.assertEqual(json.loads(result.stdout), {"status": "RAW2_REFUSED", "code": "UNEXPECTED"})
    def test_12_relative_repo_refused(self):
        self.assert_refused_cli("--repo", "relative")
    def test_13_relative_output_refused(self):
        self.assert_refused_cli("--repo", REPO, "--out", "relative")
    def test_14_execute_requires_output(self):
        self.assert_refused_cli("--repo", REPO, "--deadline", time.monotonic()+30, "--execute")
    def test_15_execute_requires_deadline(self):
        out = self.root / "not-created"
        self.assert_refused_cli("--repo", REPO, "--out", out, "--execute")
        self.assertFalse(out.exists())
    def test_16_invalid_deadlines_refused(self):
        for deadline in ("nan", "inf", "-inf", "0", str(time.monotonic()+181)):
            with self.subTest(deadline=deadline):
                self.assert_refused_cli("--repo", REPO, "--deadline="+deadline)
    def test_17_expired_boundary_refused(self):
        with self.assertRaises(original.Refused):
            a.current_deadline(time.monotonic()-1, original)
    def test_18_output_private_and_original_structure(self):
        out = self.fresh()
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        self.assertEqual(sorted(x.name for x in out.iterdir()), ["segments", "tensors"])
    def test_19_stale_output_refused_before_fetch(self):
        out = self.fresh()
        value = self.assert_refused_cli("--repo", REPO, "--out", out,
                                       "--deadline", time.monotonic()+30, "--execute")
        self.assertEqual(value["code"], "OUTPUT_FRESH")
    def test_20_output_under_repository_refused(self):
        # Original guard rejects before mkdir: no repository mutation.
        out = REPO / "__raw2_cold_must_not_exist__"
        self.assertFalse(out.exists())
        with self.assertRaises(original.Refused):
            original.prepare_output(REPO, out)
        self.assertFalse(out.exists())
    def test_21_work_component_refused(self):
        (self.root / "work").mkdir()
        out = self.root / "work" / "new"
        with self.assertRaises(original.Refused):
            original.prepare_output(REPO, out)
        self.assertFalse(out.exists())
    def test_22_symlink_output_parent_refused(self):
        (self.root / "real").mkdir()
        (self.root / "linked").symlink_to(self.root / "real", target_is_directory=True)
        with self.assertRaises(original.Refused):
            original.prepare_output(REPO, self.root / "linked" / "new")
    def test_23_symlink_original_refused_before_compile(self):
        target = self.root / a.ORIGINAL_RELATIVE
        target.parent.mkdir(parents=True)
        target.symlink_to(REPO / a.ORIGINAL_RELATIVE)
        with self.assertRaises(a.BootstrapRefused):
            a.load_original(self.root)
    def test_24_same_length_source_mutation_refused(self):
        target = self.root / a.ORIGINAL_RELATIVE
        target.parent.mkdir(parents=True)
        data = (REPO / a.ORIGINAL_RELATIVE).read_bytes()
        target.write_bytes(b"!" + data[1:])
        with self.assertRaises(a.BootstrapRefused):
            a.load_original(self.root)
    def test_25_mock_fetch_failure_no_retry_or_completion(self):
        out, calls = self.fresh(), []
        def mock_fetch(url, start, end, total, *, opener):
            calls.append((url, start, end, total))
            raise RuntimeError("https://secret.invalid/?token=PRIVATE")
        with self.assertRaises(RuntimeError):
            a.collect_raw2(original, plan, {**helpers, "fetch_range": mock_fetch}, shard,
                           out, time.monotonic()+30)
        self.assertEqual(calls, [(plan["url"], 38536, 824967, plan["whole_file_bytes"])])
        self.assertFalse((out / "RAW2_RECEIPT.json").exists())
        self.assertEqual(list((out / "segments").iterdir()), [])
    def test_26_mock_fetch_fake_body_cannot_claim_acquisition(self):
        out, calls = self.fresh(), []
        def mock_fetch(url, start, end, total, *, opener):
            calls.append((start, end))
            spec = plan["requests"][0]
            receipt = {"requested_url": url, "request_range": f"bytes={start}-{end}", "status": 206,
                       "content_range": f"bytes {start}-{end}/{total}", "bytes": spec["bytes"],
                       "sha256": spec["sha256"]}
            return bytes(spec["bytes"]), receipt
        with self.assertRaises(original.Refused) as ctx:
            a.collect_raw2(original, plan, {**helpers, "fetch_range": mock_fetch}, shard,
                           out, time.monotonic()+30)
        self.assertEqual(a.public_failure_code(ctx.exception, original), "SEGMENT_HASH")
        self.assertEqual(calls, [(38536, 824967)])
        self.assertFalse((out / "RAW2_RECEIPT.json").exists())
        self.assertEqual(list((out / "segments").iterdir()), [])
    def test_27_expired_boundary_prevents_fetch(self):
        out, calls = self.fresh(), []
        def mock_fetch(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("unreachable")
        with self.assertRaises(original.Refused):
            a.collect_raw2(original, plan, {**helpers, "fetch_range": mock_fetch}, shard,
                           out, time.monotonic()-1)
        self.assertEqual(calls, [])
    def test_28_exception_text_never_public(self):
        marker = "https://secret.invalid/?signature=PRIVATE"
        for error in (RuntimeError(marker), original.Refused(marker), ValueError(marker)):
            self.assertEqual(a.public_failure_code(error, original), "UNEXPECTED")
    def test_29_failure_allowlist_is_exact(self):
        for message, code in a.ORIGINAL_FAILURE_CODES.items():
            self.assertEqual(a.public_failure_code(original.Refused(message), original), code)
            self.assertEqual(a.public_failure_code(original.Refused(message+" private"), original), "UNEXPECTED")
    def test_30_strict_opener_applies_remaining_deadline(self):
        response, timeouts = Response(), []
        def open_(request, timeout):
            timeouts.append(timeout)
            return response
        opener = original.strict_opener(time.monotonic()+2, types.SimpleNamespace(open=open_))
        result, receipt = helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(result, b"test")
        self.assertTrue(0 < timeouts[0] <= 2)
        self.assertEqual(response.reads, [5])
    def test_31_strict_opener_forbids_duplicate_headers(self):
        response = Response(headers=[("Content-Range", "bytes 0-3/100"), ("Content-Length", "4"), ("Content-Length", "4")])
        transport = types.SimpleNamespace(open=lambda *args, **kwargs: response)
        opener = original.strict_opener(time.monotonic()+30, transport)
        with self.assertRaises(original.Refused):
            helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(response.reads, [])
        self.assertTrue(response.closed)
    def test_32_original_range_helper_refuses_200_before_read(self):
        response = Response(status=200)
        with self.assertRaises(original.Refused):
            helpers["fetch_range"](plan["url"], 0, 3, 100, opener=lambda *args, **kwargs: response)
        self.assertEqual(response.reads, [])
    def test_33_original_helpers_synthetic_atomic_roundtrip(self):
        # Tiny synthetic fixture tests helpers only. It is never a raw2 receipt.
        out = self.fresh()
        body, receipt = helpers["fetch_range"](plan["url"], 0, 3, 100,
                                              opener=lambda *args, **kwargs: Response())
        tiny_shard = {"url": plan["url"], "file_bytes": 100}
        spec = {"index": 0, "segment_index": 0, "tensor": "tiny_synthetic", "start": 0,
                "end": 3, "bytes": 4, "sha256": hashlib.sha256(body).hexdigest()}
        tensor = {"local_name": "tiny_synthetic", "dtype": "BF16", "shape": [2],
                  "start": 0, "end": 3, "bytes": 4, "sha256": spec["sha256"]}
        original.save_segment(out, spec, body, receipt, helpers["validate_http"], tiny_shard)
        original.assemble_tensor(out, tensor, [spec], helpers["validate_http"], tiny_shard)
        original.verify_tensor(out / "tensors/tiny_synthetic.bin", tensor)
        self.assertEqual((out / "tensors/tiny_synthetic.bin").read_bytes(), b"test")
        self.assertFalse((out / "RAW2_RECEIPT.json").exists())
    def test_34_module_loading_writes_no_pyc(self):
        self.assertFalse(list(HERE.rglob("*.pyc")))
        self.assertFalse(list(HERE.rglob("__pycache__")))
    def test_35_pins_remain_unchanged_after_tests(self):
        for path, (size, digest) in SOURCE_PINS.items():
            data = path.read_bytes()
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (size, digest))

    def synthetic_postflight(self, receipt=None):
        out = self.fresh()
        (out / "RAW2_RECEIPT.json").write_bytes(original.json_bytes(a.FIXED_RECEIPT if receipt is None else receipt))
        for tensor in a.FIXED_RECEIPT["tensors"]:
            (out / "tensors" / (tensor["local_name"]+".bin")).write_bytes(bytes(tensor["bytes"]))
        for name in ("00", "01"):
            (out / "segments" / name).mkdir()
        return out
    def test_36_fixed_receipt_matches_real_full_checked_sources(self):
        expected = a.FIXED_RECEIPT
        self.assertEqual(expected["source_plan"]["sources"], plan["sources"])
        self.assertEqual(expected["source_plan"]["platform_api_evidence"], plan["platform_api_evidence"])
        self.assertEqual(expected["source_plan"]["source_commit"], plan["source_commit"])
        self.assertEqual(expected["tensors"], plan["raw_tensors"][:2])
        self.assertEqual(expected["requests"], plan["requests"][:2])
        self.assertEqual(expected["status"], "RAW2_ONLY")
        for key in ("model_id", "revision", "layer_id", "header_sha256", "whole_file_bytes"):
            self.assertEqual(expected[key], plan[key])
        for key in ("providers_generated", "canonical_loader_executed", "native_executed",
                    "rtl_executed", "whole_checkpoint_sha256_verified"):
            self.assertIs(expected[key], False)
    def test_37_postflight_rejects_missing_receipt(self):
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(self.fresh())
    def test_38_postflight_rejects_fake_full_size_bodies(self):
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(self.synthetic_postflight())
    def test_39_postflight_rejects_raw13_claim(self):
        changed = copy.deepcopy(a.FIXED_RECEIPT)
        changed["status"] = "ACQUIRED_FIXED_RAW13_ONLY"
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(self.synthetic_postflight(changed))
    def test_40_postflight_rejects_each_identity_mutation(self):
        out = self.synthetic_postflight()
        for key in a.FIXED_RECEIPT:
            changed = copy.deepcopy(a.FIXED_RECEIPT)
            changed[key] = None
            (out / "RAW2_RECEIPT.json").write_bytes(original.json_bytes(changed))
            with self.subTest(field=key), self.assertRaises(a.BootstrapRefused):
                a.verify_receipt(out)
    def test_41_postflight_rejects_duplicate_key(self):
        out = self.synthetic_postflight()
        raw = (out / "RAW2_RECEIPT.json").read_bytes()
        (out / "RAW2_RECEIPT.json").write_bytes(raw.replace(b'{', b'{"status":"RAW2_ONLY",', 1))
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_42_postflight_rejects_nonfinite_number(self):
        out = self.synthetic_postflight()
        (out / "RAW2_RECEIPT.json").write_text('{"invalid":NaN}')
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_43_postflight_rejects_unexpected_file(self):
        out = self.synthetic_postflight()
        (out / "unexpected").write_text("synthetic")
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_44_postflight_rejects_public_directory(self):
        out = self.synthetic_postflight()
        out.chmod(0o755)
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_45_postflight_rejects_tensor_symlink(self):
        out = self.synthetic_postflight()
        target = out / "tensors" / (a.FIXED_RECEIPT["tensors"][0]["local_name"]+".bin")
        target.unlink()
        target.symlink_to(SOURCE)
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_46_postflight_rejects_short_tensor(self):
        out = self.synthetic_postflight()
        target = out / "tensors" / (a.FIXED_RECEIPT["tensors"][0]["local_name"]+".bin")
        target.write_bytes(b"synthetic")
        with self.assertRaises(a.BootstrapRefused):
            a.verify_receipt(out)
    def test_47_safe_markers_finite_exact_no_newlines(self):
        self.assertIs(type(a.SAFE_MARKERS), frozenset)
        self.assertEqual(len(a.SAFE_MARKERS), len(set(a.ORIGINAL_FAILURE_CODES.values()))+1)
        for line in a.SAFE_MARKERS:
            self.assertNotIn("\n", line)
            value = json.loads(line)
            self.assertEqual(set(value), {"status", "code"})
            self.assertEqual(value["status"], "RAW2_REFUSED")
            self.assertIn(value["code"], set(a.ORIGINAL_FAILURE_CODES.values()) | {"UNEXPECTED"})
    def test_48_cli_failure_is_exact_safe_marker(self):
        result = self.cli("--repo", REPO, "--nonsense", "private-context")
        self.assertIn(result.stdout.rstrip("\n"), a.SAFE_MARKERS)
        self.assertEqual(result.stderr, "")
    def test_49_subclass_exception_formatting_never_called(self):
        class Hostile(original.Refused):
            def __str__(self):
                raise RuntimeError("MUST_NOT_FORMAT")
        self.assertEqual(a.public_failure_code(Hostile("private"), original), "UNEXPECTED")
    def test_50_no_completion_claim_from_source_only(self):
        result = self.cli("--repo", REPO)
        self.assertEqual(result.stdout.rstrip("\n"), a.SOURCE_ONLY_MARKER)
        self.assertNotEqual(result.stdout.rstrip("\n"), a.SUCCESS_MARKER)
        self.assertFalse(list(HERE.glob("**/RAW2_RECEIPT.json")))


    def test_51_loader_bad_length_rejected_before_compile(self):
        candidate = self.root / "bad_length.py"
        candidate.write_bytes(b"pass")
        events = []
        def observe(event, args):
            if event == "compile" and args[1] == str(candidate):
                events.append(event)
        sys.addaudithook(observe)
        with self.assertRaises(TestLoaderRefused):
            load_pinned_adapter(candidate)
        self.assertEqual(events, [])
    def test_52_loader_same_length_bad_sha_rejected_before_compile(self):
        candidate = self.root / "bad_sha.py"
        data = SOURCE.read_bytes()
        candidate.write_bytes(b"!" + data[1:])
        events = []
        def observe(event, args):
            if event == "compile" and args[1] == str(candidate):
                events.append(event)
        sys.addaudithook(observe)
        with self.assertRaises(TestLoaderRefused):
            load_pinned_adapter(candidate)
        self.assertEqual(events, [])
    def test_53_loader_fresh_relocation_accepts_fixed_bytes(self):
        relocated = self.root / "fresh" / "raw2_adapter.py"
        relocated.parent.mkdir()
        relocated.write_bytes(SOURCE.read_bytes())
        loaded = load_pinned_adapter(relocated)
        self.assertEqual(loaded.__file__, str(relocated))
        self.assertEqual(loaded.SUCCESS_MARKER, a.SUCCESS_MARKER)
        self.assertEqual(loaded.SAFE_MARKERS, a.SAFE_MARKERS)
        self.assertEqual(loaded.FIXED_RECEIPT, a.FIXED_RECEIPT)
        self.assertFalse(list(relocated.parent.rglob("*.pyc")))

if __name__ == "__main__":
    unittest.main(verbosity=2)
