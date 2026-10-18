#!/usr/bin/env python3
"""Small offline cold tests. No live network, raw model bytes, imports or pyc."""
import hashlib
import io
import json
import os
from email.message import Message
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import time
import types
import unittest
from unittest import mock
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv.pop(1)).resolve()
raw = (HERE / "acquire_raw.py").read_bytes()
expected = json.loads((HERE / "CODE_IDENTITY.json").read_bytes())["acquire_raw.py"]
if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
    raise SystemExit("acquirer source drift")
module = types.ModuleType("cold_acquirer")
module.__file__ = str(HERE / "acquire_raw.py")
exec(compile(raw, module.__file__, "exec", dont_inherit=True), module.__dict__)
a = module
plan, helpers, shard = a.check_sources(REPO, HERE / "ACQUISITION_PLAN.json")


class Response:
    def __init__(self, raw=b"test", status=206, headers=None, url=None):
        self.raw, self.status, self.reads, self.closed = raw, status, 0, False
        self.code, self.msg = status, "Synthetic response"
        self.headers = Message()
        for k, v in (headers or {"Content-Range": "bytes 0-3/100", "Content-Length": "4"}).items():
            self.headers[k] = v
        self.url = url or plan["url"]
    def info(self):
        return self.headers
    def geturl(self):
        return self.url
    def read(self, count=-1):
        self.reads += 1
        return self.raw if count < 0 else self.raw[:count]
    def close(self):
        self.closed = True
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class ColdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "run"
        self.output.mkdir()
        (self.output / "segments").mkdir()
        (self.output / "tensors").mkdir()
        self.small_shard = {"url": plan["url"], "file_bytes": 100}
        self.spec = {"index": 0, "segment_index": 0, "tensor": "tiny", "start": 0, "end": 3,
                     "bytes": 4, "sha256": a.sha256(b"test")}
        self.tensor = {"local_name": "tiny", "start": 0, "end": 3, "bytes": 4,
                       "sha256": a.sha256(b"test"), "dtype": "BF16", "shape": [2]}
    def tearDown(self):
        self.temp.cleanup()
    def fetch(self, response):
        return helpers["fetch_range"](plan["url"], 0, 3, 100, opener=lambda *args, **kw: response)
    def save(self):
        raw, receipt = self.fetch(Response())
        a.save_segment(self.output, self.spec, raw, receipt, helpers["validate_http"], self.small_shard)
        return receipt
    def test_real_inherited_blocked_alarm_refused_before_side_effects(self):
        child = r"""
import hashlib,json,pathlib,signal,sys,types
source=pathlib.Path(sys.argv[1]); repo=sys.argv[2]; output=pathlib.Path(sys.argv[3])
raw=source.read_bytes(); expected=json.loads(source.with_name("CODE_IDENTITY.json").read_bytes())["acquire_raw.py"]
if len(raw)!=expected["bytes"] or hashlib.sha256(raw).hexdigest()!=expected["sha256"]: raise SystemExit(20)
m=types.ModuleType("masked_child");m.__file__=str(source)
exec(compile(raw,str(source),"exec",dont_inherit=True),m.__dict__)
signal.pthread_sigmask(signal.SIG_BLOCK,[signal.SIGALRM])
before=signal.pthread_sigmask(signal.SIG_BLOCK,[])
def forbidden(*a,**k): raise RuntimeError("side effect reached")
m.check_sources=forbidden;m.resource.setrlimit=forbidden;m.signal.setitimer=forbidden
m.prepare_output=forbidden;m.strict_opener=forbidden
try:
    m.main(["--repo",repo,"--output",str(output),"--execute"])
except m.Refused as error:
    if "SIGALRM" not in str(error): raise SystemExit(21)
else: raise SystemExit(22)
after=signal.pthread_sigmask(signal.SIG_BLOCK,[])
if after!=before or signal.SIGALRM not in after or output.exists(): raise SystemExit(23)
print("BLOCKED_SIGALRM_REFUSED_UNCHANGED_NO_SIDE_EFFECTS")
"""
        command = [sys.executable, "-B", "-I"]
        if sys.flags.optimize:
            command.append("-O")
        result = subprocess.run(command + ["-c", child, str(HERE / "acquire_raw.py"), str(REPO),
                                str(Path(self.temp.name) / "never_created")],
                                capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("BLOCKED_SIGALRM_REFUSED_UNCHANGED_NO_SIDE_EFFECTS", result.stdout)

    def test_real_opener_delegates_platform_without_application_credentials(self):
        before, after, builders = [], [], []
        real_build = urllib.request.build_opener
        def fake_https(handler, request):
            after.append(request)
            return Response()
        def record_build(*handlers):
            builders.append([type(h).__name__ for h in handlers])
            transport = real_build(*handlers)
            def open_(request, timeout):
                before.append({"host": request.host,
                               "authorization_absent": request.get_header("Authorization") is None,
                               "proxy_authorization_absent": request.get_header("Proxy-authorization") is None})
                return transport.open(request, timeout=timeout)
            return types.SimpleNamespace(open=open_)
        environment = {"https_proxy": "http://synthetic-user:synthetic-secret@proxy.invalid:8080",
                       "HTTPS_PROXY": "http://synthetic-user:synthetic-secret@proxy.invalid:8080",
                       "no_proxy": "", "NO_PROXY": ""}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(urllib.request.HTTPSHandler, "https_open", fake_https), \
                mock.patch.object(urllib.request, "build_opener", record_build):
            opener = a.strict_opener(time.monotonic() + 900)
            raw, receipt = helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(raw, b"test")
        self.assertEqual(builders, [["NoRedirect"]])
        self.assertEqual(before, [{"host": "huggingface.co", "authorization_absent": True,
                                   "proxy_authorization_absent": True}])
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].host, "proxy.invalid:8080")
        self.assertEqual(after[0]._tunnel_host, "huggingface.co")
        # Only presence is retained; the synthetic header value is never logged.
        self.assertIsNotNone(after[0].get_header("Proxy-authorization"))
        self.assertIsNone(after[0].get_header("Authorization"))

    def test_platform_evidence_drift_refused(self):
        root = Path(self.temp.name)
        (root / "ACQUISITION_PLAN.json").write_bytes((HERE / "ACQUISITION_PLAN.json").read_bytes())
        evidence = (HERE / "PLATFORM_API_EVIDENCE.json").read_bytes()
        (root / "PLATFORM_API_EVIDENCE.json").write_bytes(b"!" + evidence[1:])
        with self.assertRaises(a.Refused):
            a.check_sources(REPO, root / "ACQUISITION_PLAN.json")

    def test_fixed_sources_and_totals(self):
        self.assertEqual(len(plan["requests"]), 22)
        self.assertEqual(sum(x["bytes"] for x in plan["requests"]), 94382080)
        self.assertEqual(len(plan["raw_tensors"]), 13)
        self.assertFalse(any(x == "heteronpu" or x.startswith("heteronpu.") for x in sys.modules))
    def test_bad_plan_refused(self):
        path = Path(self.temp.name) / "bad.json"
        data = (HERE / "ACQUISITION_PLAN.json").read_bytes()
        path.write_bytes(data.replace(b"94382080", b"94382081", 1))
        with self.assertRaises(a.Refused):
            a.check_sources(REPO, path)
    def test_bad_source_refused(self):
        repo = Path(self.temp.name) / "repo"
        for source in plan["sources"]:
            dest = repo / source["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / source["path"], dest)
        target = repo / plan["sources"][0]["path"]
        data = target.read_bytes()
        target.write_bytes(b"!" + data[1:])
        with self.assertRaises(a.Refused):
            a.check_sources(repo, HERE / "ACQUISITION_PLAN.json")
    def test_200_refused_before_body_read(self):
        response = Response(status=200)
        with self.assertRaises(a.Refused):
            self.fetch(response)
        self.assertEqual(response.reads, 0)
        self.assertTrue(response.closed)
    def test_bad_range_length_encoding_before_body(self):
        for key, value in (("Content-Range", "bytes 1-4/100"), ("Content-Length", "5"), ("Content-Encoding", "gzip")):
            headers = {"Content-Range": "bytes 0-3/100", "Content-Length": "4", key: value}
            response = Response(headers=headers)
            with self.subTest(header=key), self.assertRaises(a.Refused):
                self.fetch(response)
            self.assertEqual(response.reads, 0)
    def test_short_and_long_body_refused(self):
        for raw in (b"abc", b"abcde"):
            with self.subTest(raw=raw), self.assertRaises(a.Refused):
                self.fetch(Response(raw=raw))
    def test_segment_bad_sha_not_saved(self):
        raw, receipt = self.fetch(Response(raw=b"evil"))
        with self.assertRaises(a.Refused):
            a.save_segment(self.output, self.spec, raw, receipt, helpers["validate_http"], self.small_shard)
        self.assertEqual(list((self.output / "segments").iterdir()), [])
    def test_receipt_bool_is_not_integer(self):
        raw, receipt = self.fetch(Response())
        receipt["status"] = True
        with self.assertRaises(a.Refused):
            helpers["validate_http"](self.small_shard, 0, 3, raw, receipt, self.spec["sha256"])
    def test_valid_atomic_segment_and_tensor(self):
        self.save()
        a.assemble_tensor(self.output, self.tensor, [self.spec], helpers["validate_http"], self.small_shard)
        self.assertEqual((self.output / "tensors/tiny.bin").read_bytes(), b"test")
        self.assertEqual((self.output / "segments/00/payload.bin").read_bytes(), b"test")
        self.assertFalse(any("pending" in p.name for p in self.output.rglob("*")))
    def test_atomic_receipt_failure_keeps_pending(self):
        raw, receipt = self.fetch(Response())
        original = a.write_new
        def fail_receipt(path, data):
            if path.name == "receipt.json":
                raise OSError("synthetic disk failure")
            original(path, data)
        a.write_new = fail_receipt
        try:
            with self.assertRaises(OSError):
                a.save_segment(self.output, self.spec, raw, receipt, helpers["validate_http"], self.small_shard)
        finally:
            a.write_new = original
        self.assertFalse((self.output / "segments/00").exists())
        self.assertEqual((self.output / "segments/.00.pending/payload.bin").read_bytes(), b"test")
    def test_corrupt_cache_refused_before_assembly(self):
        self.save()
        (self.output / "segments/00/payload.bin").write_bytes(b"evil")
        with self.assertRaises(a.Refused):
            a.assemble_tensor(self.output, self.tensor, [self.spec], helpers["validate_http"], self.small_shard)
        self.assertFalse((self.output / "tensors/tiny.bin").exists())
        self.assertTrue((self.output / "segments/00").exists())
    def test_wrong_tensor_sha_preserves_partial(self):
        self.save()
        tensor = {**self.tensor, "sha256": "0" * 64}
        with self.assertRaises(a.Refused):
            a.assemble_tensor(self.output, tensor, [self.spec], helpers["validate_http"], self.small_shard)
        self.assertFalse((self.output / "tensors/tiny.bin").exists())
        self.assertEqual((self.output / "tensors/.tiny.bin.pending").read_bytes(), b"test")
    def test_stale_output_refused(self):
        with self.assertRaises(a.Refused):
            a.prepare_output(REPO, self.output)
    def test_symlink_cache_refused(self):
        self.save()
        path = self.output / "segments/00/payload.bin"
        path.unlink()
        path.symlink_to(HERE / "ACQUISITION_PLAN.json")
        with self.assertRaises(a.Refused):
            a.cached_segment(self.output, self.spec, helpers["validate_http"], self.small_shard)
    def test_redirect_allowlist(self):
        for url in ("http://huggingface.co/a", "https://evil.example/a", "https://x@huggingface.co/a", "https://huggingface.co:444/a"):
            with self.subTest(url=url), self.assertRaises(a.Refused):
                a.allowed_url(url)
        a.allowed_url("https://us.aws.cdn.hf.co/path?signature=synthetic")
    def test_redirect_body_never_read(self):
        body = Response()
        headers = Message()
        headers["Location"] = "https://us.aws.cdn.hf.co/path?signature=synthetic"
        calls = []
        response = Response(url=headers["Location"])
        def open_(request, timeout):
            calls.append((request, timeout))
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 302, "redirect", headers, body)
            return response
        opener = a.strict_opener(time.monotonic() + 900, types.SimpleNamespace(open=open_))
        raw, receipt = helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(raw, b"test")
        self.assertEqual(body.reads, 0)
        self.assertTrue(body.closed)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0].get_header("Range"), "bytes=0-3")
        self.assertEqual(receipt["requested_url"], plan["url"])
    def test_redirect_limit_no_retry(self):
        bodies = []
        headers = Message()
        headers["Location"] = "https://us.aws.cdn.hf.co/path"
        def open_(request, timeout):
            body = Response()
            bodies.append(body)
            raise urllib.error.HTTPError(request.full_url, 302, "redirect", headers, body)
        opener = a.strict_opener(time.monotonic() + 900, types.SimpleNamespace(open=open_))
        with self.assertRaises(a.Refused):
            helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(len(bodies), 5)
        self.assertTrue(all(b.reads == 0 and b.closed for b in bodies))
    def test_duplicate_header_refused_before_read(self):
        response = Response()
        response.headers["Content-Length"] = "4"
        opener = a.strict_opener(time.monotonic() + 900, types.SimpleNamespace(open=lambda *args, **kw: response))
        with self.assertRaises(a.Refused):
            helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        self.assertEqual(response.reads, 0)
    def test_deadline_before_transport(self):
        def forbidden(*args, **kwargs):
            self.fail("transport must not be called")
        opener = a.strict_opener(time.monotonic() - 1, types.SimpleNamespace(open=forbidden))
        with self.assertRaises(a.Refused):
            helpers["fetch_range"](plan["url"], 0, 3, 100, opener=opener)
        with self.assertRaises(TimeoutError):
            a.wall_expired(None, None)
    def test_overbudget_before_write(self):
        with self.assertRaises(a.Refused):
            a.disk_check(self.output, a.DISK_CAP)
    def test_no_network_default_main(self):
        original = a.strict_opener
        def forbidden(*args, **kwargs):
            self.fail("opener must not be created")
        a.strict_opener = forbidden
        try:
            self.assertEqual(a.main(["--repo", str(REPO)]), 0)
        finally:
            a.strict_opener = original


if __name__ == "__main__":
    unittest.main()
