#!/usr/bin/env python3
"""Tiny pure-mock cold tests; no real network, package, extraction or native run."""
import argparse
import copy
from email.message import Message
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
WORKER_PIN = {'bytes': 9150, 'sha256': 'f43ee638df95dfa23955aaaa53581655efbc8eba330bf98ef4d02448fab00009'}
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise ValueError("use python -I -S -B before loading project code")
parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, required=True)
REPO = parser.parse_args().repo


def load_worker():
    path = HERE / "acquire_dependencies.py"
    with path.open("rb") as source:
        raw = source.read(WORKER_PIN["bytes"] + 1)
    if len(raw) != WORKER_PIN["bytes"]:
        raise ValueError("cold worker source size")
    if hashlib.sha256(raw).hexdigest() != WORKER_PIN["sha256"]:
        raise ValueError("cold worker source SHA256")
    scope = {"__name__": "cold_test_adapter", "__file__": str(path)}
    exec(compile(raw, str(path), "exec", dont_inherit=True), scope)
    return scope


W = load_worker()
PUBLISHED_RAW = W["checked"](HERE / "published_acquire.py", W["PUBLISHED"])


class Stream:
    def __init__(self, payload, url, close_error=False):
        self.source = io.BytesIO(payload)
        self.status = 200
        self.url = url
        self.headers = Message()
        self.close_error = close_error
        self.requests = []

    def read(self, size):
        self.requests.append(size)
        return self.source.read(size)

    def geturl(self):
        return self.url

    def close(self):
        self.source.close()
        if self.close_error:
            raise OSError("synthetic close failure")


class Opener:
    def __init__(self, payloads, close_error=False):
        self.payloads = payloads
        self.close_error = close_error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        if not 0 < timeout <= 30:
            raise ValueError("synthetic opener timeout bound")
        if request.get_header("Accept-encoding") != "identity":
            raise ValueError("synthetic opener encoding")
        return Stream(self.payloads[request.full_url], request.full_url, self.close_error)


class ColdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tiny-mock-", dir=HERE)
        self.base = Path(self.temp.name)
        self.engine, self.projection = W["namespace"](PUBLISHED_RAW, time.monotonic() + 30)
        self.plan = json.loads(W["checked"](HERE / "DEPENDENCY_PLAN.json", W["PLAN_PIN"]))
        self.payloads = {}
        for index, item in enumerate(self.plan["artifacts"]):
            payload = ("tiny" + str(index)).encode()
            self.payloads[item["url"]] = payload
            item["known_size_bytes"] = len(payload)
            item["max_transfer_bytes"] = len(payload) + 1
            item["sha256"] = hashlib.sha256(payload).hexdigest()
        self.root = self.base / "artifacts"

    def tearDown(self):
        self.temp.cleanup()

    def fail_fetch(self, opener=None):
        with self.assertRaises(BaseException) as caught:
            self.engine["acquire"](self.plan, self.root, opener=opener or Opener(self.payloads))
        self.assertFalse((self.root / "ACQUISITION.json").exists())
        self.assertTrue((self.root / "FAILED.json").exists())
        return caught.exception, json.loads((self.root / "FAILED.json").read_text())

    def test_cold_loader_wrong_size_before_compile(self):
        with patch.object(Path, "open", return_value=io.BytesIO(b"BAD")), patch("builtins.compile") as compiler:
            with self.assertRaisesRegex(ValueError, "source size"):
                load_worker()
            compiler.assert_not_called()

    def test_cold_loader_equal_size_wrong_hash_before_compile(self):
        raw = b"#" * WORKER_PIN["bytes"]
        with patch.object(Path, "open", return_value=io.BytesIO(raw)), patch("builtins.compile") as compiler:
            with self.assertRaisesRegex(ValueError, "source SHA256"):
                load_worker()
            compiler.assert_not_called()

    def test_cold_loader_valid_same_buffer_marker_control(self):
        raw = b"SYNTHETIC_BUFFER_MARKER = 731\n"
        pin = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        with patch.dict(WORKER_PIN, pin), patch.object(Path, "open", return_value=io.BytesIO(raw)):
            scope = load_worker()
        self.assertEqual(scope["SYNTHETIC_BUFFER_MARKER"], 731)

    def test_fixed_source_and_plan_preflight(self):
        plan, _engine, _projection = W["preflight"](REPO, time.monotonic() + 10)
        self.assertEqual(len(plan["artifacts"]), 5)
        self.assertEqual(sum(x["known_size_bytes"] for x in plan["artifacts"]), 2466616)
        self.assertEqual(W["absolute_deadline"](100., 270., 109.), 269.)
        for values in ((100., 271., 109.), (100., 270., 110.), (100., float("nan"), 109.)):
            with self.assertRaises(ValueError):
                W["absolute_deadline"](*values)

    def test_source_and_plan_pin_drift(self):
        with self.assertRaises(ValueError):
            W["project"](PUBLISHED_RAW + b"\n")
        raw = W["checked"](HERE / "DEPENDENCY_PLAN.json", W["PLAN_PIN"])
        p = self.base / "changed.json"
        p.write_bytes(b" " + raw[1:])
        with self.assertRaises(ValueError):
            W["checked"](p, W["PLAN_PIN"])

    def test_five_tiny_packages_and_one_terminal_receipt(self):
        opener = Opener(self.payloads)
        receipt = self.engine["acquire"](self.plan, self.root, opener=opener)
        self.assertEqual(receipt["status"], "VERIFIED_OPAQUE_BYTES_ONLY")
        self.assertFalse(receipt["terminal_success"])
        self.assertEqual(receipt["received_bytes"], 25)
        self.assertEqual(len(receipt["artifacts"]), 5)
        self.assertEqual(len(opener.calls), 5)
        self.assertFalse((self.root / "FAILED.json").exists())
        self.assertEqual({p.name for p in self.root.iterdir()},
                         {x["relative_destination"] for x in self.plan["artifacts"]} | {"ACQUISITION.json"})

    def test_wrong_hash_preserves_received_bytes(self):
        self.plan["artifacts"][0]["sha256"] = "0" * 64
        error, failure = self.fail_fetch()
        self.assertIn("SHA-256", str(error))
        self.assertEqual(failure["received_bytes"], 5)
        self.assertEqual(failure["verified_partial_artifacts"], [])

    def test_short_and_trailing_bytes(self):
        item = self.plan["artifacts"][0]
        self.payloads[item["url"]] = b"longer"
        error, failure = self.fail_fetch()
        self.assertIn("pinned size", str(error))
        self.assertEqual(failure["received_bytes"], 6)

    def test_short_body(self):
        item = self.plan["artifacts"][0]
        self.payloads[item["url"]] = b"tiny"
        error, failure = self.fail_fetch()
        self.assertIn("size mismatch", str(error))
        self.assertEqual(failure["received_bytes"], 4)

    def test_shared_transfer_cap_no_retry(self):
        self.plan["limits"]["total_transfer_bytes"] = 7
        opener = Opener(self.payloads)
        error, failure = self.fail_fetch(opener)
        self.assertIn("transfer cap", str(error))
        self.assertEqual(failure["received_bytes"], 7)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(len(failure["verified_partial_artifacts"]), 1)

    def test_received_accounting_before_deadline(self):
        now = [0.]
        budget = self.engine["Budget"]({"total_transfer_bytes": 10, "elapsed_check_seconds": 1}, lambda: now[0])
        class Late:
            def read(self, n):
                now[0] = 2.
                return b"123"
        sink = io.BytesIO()
        with self.assertRaises(self.engine["AcquisitionError"]):
            self.engine["copy_verified"](Late(), sink, self.plan["artifacts"][0], budget)
        self.assertEqual(budget.bytes, 3)
        self.assertEqual(sink.getvalue(), b"")

    def test_received_accounting_before_bounded_contract(self):
        budget = self.engine["Budget"]({"total_transfer_bytes": 2, "elapsed_check_seconds": 1})
        class TooMuch:
            def read(self, n):
                return b"123"
        sink = io.BytesIO()
        with self.assertRaises(self.engine["AcquisitionError"]):
            self.engine["copy_verified"](TooMuch(), sink, self.plan["artifacts"][0], budget)
        self.assertEqual(budget.bytes, 3)
        self.assertEqual(sink.getvalue(), b"")

    def test_redirect_and_response_refused(self):
        with self.assertRaises(self.engine["AcquisitionError"]):
            self.engine["NoRedirect"]().redirect_request(None, None, 302, "redirect", {}, "https://elsewhere.invalid/")
        item = self.plan["artifacts"][0]
        for variant in ("url", "status", "encoding", "length", "ambiguous"):
            response = Stream(b"tiny0", item["url"])
            if variant == "url": response.url += "/changed"
            elif variant == "status": response.status = 206
            elif variant == "encoding": response.headers["Content-Encoding"] = "gzip"
            elif variant == "length": response.headers["Content-Length"] = "6"
            else:
                response.headers["Content-Length"] = "5"
                response.headers["Content-Length"] = "5"
            with self.assertRaises(self.engine["AcquisitionError"]):
                self.engine["check_response"](response, item)

    def test_paths_and_limits_fail_closed(self):
        for destination in ("../escape", "/absolute", "x.part", "FAILED.json"):
            plan = copy.deepcopy(self.plan)
            plan["artifacts"][0]["relative_destination"] = destination
            with self.assertRaises(self.engine["AcquisitionError"]):
                self.engine["validate_plan"](plan)
        plan = copy.deepcopy(self.plan)
        plan["limits"]["total_transfer_bytes"] = True
        with self.assertRaises(self.engine["AcquisitionError"]):
            self.engine["validate_plan"](plan)
        with self.assertRaises(self.engine["AcquisitionError"]):
            self.engine["checked_output_root"](REPO / "forbidden-new", REPO, True)

    def test_atomic_artifact_link_failure(self):
        real_os = os
        class FailingOS:
            def __getattr__(self, name): return getattr(real_os, name)
            def link(self, source, destination):
                if str(destination).endswith(".deb"):
                    raise OSError("synthetic artifact link failure")
                return real_os.link(source, destination)
        self.engine["os"] = FailingOS()
        error, failure = self.fail_fetch()
        self.assertIsInstance(error, OSError)
        self.assertEqual(failure["received_bytes"], 5)
        self.assertEqual({p.name for p in self.root.iterdir()}, {"FAILED.json"})

    def test_atomic_receipt_link_failure_no_success(self):
        real_os = os
        class FailingOS:
            def __getattr__(self, name): return getattr(real_os, name)
            def link(self, source, destination):
                if Path(destination).name == "ACQUISITION.json":
                    raise OSError("synthetic receipt link failure")
                return real_os.link(source, destination)
        self.engine["os"] = FailingOS()
        error, failure = self.fail_fetch()
        self.assertIsInstance(error, OSError)
        self.assertEqual(failure["received_bytes"], 25)
        self.assertFalse((self.root / "ACQUISITION.json.part").exists())

    def test_postcommit_receipt_unlink_warning_not_failure(self):
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path.name == "ACQUISITION.json.part":
                raise OSError("synthetic postcommit cleanup failure")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", unlink):
            receipt = self.engine["acquire"](self.plan, self.root, opener=Opener(self.payloads))
        self.assertEqual(receipt["status"], "VERIFIED_OPAQUE_BYTES_ONLY")
        self.assertTrue((self.root / "ACQUISITION.json").exists())
        self.assertFalse((self.root / "FAILED.json").exists())
        self.assertTrue((self.root / "CLEANUP_WARNING.json").exists())

    def test_primary_pin_error_survives_stream_close_error(self):
        self.plan["artifacts"][0]["sha256"] = "0" * 64
        error, failure = self.fail_fetch(Opener(self.payloads, close_error=True))
        self.assertIsInstance(error, self.engine["AcquisitionError"])
        self.assertIn("SHA-256", str(error))
        self.assertIn("resource close error: OSError", error.__notes__)
        self.assertEqual(failure["error_type"], "AcquisitionError")

    def test_primary_error_survives_sink_close_error(self):
        class BadClose:
            def close(self): raise OSError("close")
        primary = ValueError("original")
        with self.assertRaises(ValueError) as caught:
            with W["safe_closing"](BadClose()):
                raise primary
        self.assertIs(caught.exception, primary)
        self.assertEqual(primary.__notes__, ["resource close error: OSError"])

    def test_failure_cleanup_never_masks_primary(self):
        self.plan["artifacts"][0]["sha256"] = "0" * 64
        original_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path.name.endswith(".deb.part"):
                raise PermissionError("synthetic artifact cleanup failure")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", unlink):
            error, failure = self.fail_fetch()
        self.assertIsInstance(error, self.engine["AcquisitionError"])
        self.assertEqual(failure["received_bytes"], 5)
        self.assertEqual(failure["cleanup_errors"][0]["error_type"], "PermissionError")

    def test_receipt_write_and_cleanup_keep_original_error(self):
        primary = ValueError("synthetic original receipt write error")
        class Handle:
            def write(self, _text): raise primary
            def close(self): raise OSError("synthetic receipt close error")
        class FakePath:
            name = "FAILED.json"
            def with_name(self, _name): return self
            def open(self, *_args, **_kwargs): return Handle()
            def unlink(self, **_kwargs): raise PermissionError("synthetic receipt unlink error")
        with self.assertRaises(ValueError) as caught:
            self.engine["write_json"](FakePath(), {"status": "failed"})
        self.assertIs(caught.exception, primary)
        self.assertEqual(primary.__notes__, ["resource close error: OSError", "receipt cleanup error: PermissionError"])


if __name__ == "__main__":
    # Any unintended real urllib open is a hard test failure, not a mock pass.
    with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("real network forbidden in cold tests")):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ColdTests)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps({"status": "PURE_MOCK_COLD_PASS" if result.wasSuccessful() else "PURE_MOCK_COLD_FAIL",
                      "tests": result.testsRun, "network_started": False, "downloaded": False,
                      "installed": False, "extracted": False, "packages_executed": False}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
