"""Cold stdlib tests: synthetic streams/files only; all sockets are denied."""

import ast
from contextlib import redirect_stderr, redirect_stdout
import copy
from email.message import Message
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import marshal
from pathlib import Path
import socket
import struct
import tempfile
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parents[1]
ACQUIRE_SOURCE_PIN = {
    "bytes": 19263,
    "sha256": "4807fc702edfeb98d7eab9b86e727fe6d0d116ae7230200be7babb5a2c5b9b69",
}


def module(name, path, expected):
    # Verify and execute the SAME bytes. Never consult a project bytecode cache.
    raw = path.read_bytes()
    actual = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if actual != expected:
        raise ValueError("project source bytes differ before execution: " + path.name)
    result = types.ModuleType(name)
    result.__file__ = str(path.resolve())
    exec(compile(raw, str(path), "exec", dont_inherit=True), result.__dict__)
    return result


acq = module("host93_acquire", HERE / "acquire.py", ACQUIRE_SOURCE_PIN)


def fixture(data=b"synthetic pinned bytes", group="jar87", known=True):
    artifact = {
        "relative_destination": "fixture.bin",
        "url": acq.URL_PREFIXES[group] + "fixture.bin",
        "sha256": hashlib.sha256(data).hexdigest(),
        "known_size_bytes": len(data) if known else None,
        "max_transfer_bytes": len(data) + 1,
    }
    return {"schema": 1, "group": group, "artifact_count": 1,
            "transport": "connector-materialized-only" if group == "idma" else "https-no-redirect",
            "artifacts": [artifact], "limits": {"total_transfer_bytes": len(data) + 2,
            "socket_timeout_seconds": 2, "elapsed_check_seconds": 60}}


class Response(io.BytesIO):
    def __init__(self, data, artifact, status=200, length=None, url=None, encoding=None):
        super().__init__(data)
        self.status = status
        self.url = url or artifact["url"]
        self.headers = Message()
        if length is not None:
            self.headers["Content-Length"] = str(length)
        if encoding is not None:
            self.headers["Content-Encoding"] = encoding

    def geturl(self):
        return self.url


class ColdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=HERE / "tests")
        self.base = Path(self.temp.name)
        self.repository = self.base / "synthetic-checkout"
        (self.repository / ".git").mkdir(parents=True)
        self.block_socket = mock.patch.object(socket, "socket", side_effect=AssertionError("cold tests prohibit sockets"))
        self.block_connect = mock.patch.object(socket, "create_connection", side_effect=AssertionError("cold tests prohibit network"))
        self.block_socket.start()
        self.block_connect.start()

    def tearDown(self):
        self.block_connect.stop()
        self.block_socket.stop()
        self.temp.cleanup()

    def stream_check(self, data, plan=None, sink=None):
        plan = plan or fixture(data)
        return acq.copy_verified(io.BytesIO(data), sink, plan["artifacts"][0], acq.Budget(plan["limits"]))

    def test_valid_poisoned_pyc_positive_control_and_source_loader_bypass(self):
        source = self.base / "synthetic_module.py"
        raw = b"SOURCE_MARKER = True\n"
        source.write_bytes(raw)
        expected = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        cached = Path(importlib.util.cache_from_source(str(source)))
        cached.parent.mkdir()
        info = source.stat()
        # A valid timestamp cache for these source bytes, containing only a
        # harmless extra attribute. The ordinary loader MUST execute it first.
        code = compile(raw + b"BYTECODE_MARKER = True\n", str(source), "exec", dont_inherit=True)
        cached.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack(
            "<III", 0, int(info.st_mtime) & 0xFFFFFFFF, len(raw)
        ) + marshal.dumps(code))
        positive = types.ModuleType("ordinary_loader_positive_control")
        importlib.machinery.SourceFileLoader(positive.__name__, str(source)).exec_module(positive)
        self.assertIs(positive.BYTECODE_MARKER, True)
        direct = module("source_only_control", source, expected)
        self.assertIs(direct.SOURCE_MARKER, True)
        self.assertFalse(hasattr(direct, "BYTECODE_MARKER"))

    def test_source_drift_is_rejected_before_compile_or_execution(self):
        source = self.base / "drift.py"
        raw = b'GUARD = "before"\n'
        expected = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for changed in (b'GUARD = "after!"\n', raw + b"EXTRA = True\n"):
            source.write_bytes(changed)
            with self.subTest(changed=changed), mock.patch("builtins.compile") as compiler:
                with self.assertRaisesRegex(ValueError, "source bytes differ before execution"):
                    module("rejected_drift", source, expected)
                compiler.assert_not_called()

    def test_pinned_loader_reads_and_executes_one_raw_snapshot(self):
        raw = b"SOURCE_MARKER = True\n"
        expected = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(Path, "read_bytes", side_effect=[raw, b"BYTECODE_MARKER = True\n"]) as reader:
            loaded = module("single_snapshot", self.base / "snapshot.py", expected)
        reader.assert_called_once_with()
        self.assertIs(loaded.SOURCE_MARKER, True)
        self.assertFalse(hasattr(loaded, "BYTECODE_MARKER"))

    def test_all_fixed_plans_and_lock_agree(self):
        lock = json.loads((HERE / "PLAN_LOCK.json").read_text())
        self.assertEqual(set(lock["plans"]), set(acq.GROUP_HASHES))
        for group, expected in acq.GROUP_COUNTS.items():
            with self.subTest(group=group):
                plan = acq.load_plan(group)
                self.assertEqual(len(plan["artifacts"]), expected)
                self.assertEqual(lock["plans"][group]["sha256"], acq.GROUP_HASHES[group])
                self.assertFalse(plan["policy"]["execute_or_extract"])
        self.assertEqual(sum(a["known_size_bytes"] for a in acq.load_plan("hardfloat20")["artifacts"]), 149157)
        self.assertTrue(all(a["known_size_bytes"] is None for a in acq.load_plan("jar87")["artifacts"]))
        self.assertNotIn("106", acq.GROUP_HASHES)
        self.assertEqual(acq.load_plan("idma")["transport"], "connector-materialized-only")

    def test_profile_has_no_added_test_framework_jars(self):
        names = [a["relative_destination"].lower() for a in acq.load_plan("jar87")["artifacts"]]
        self.assertFalse(any(any(t in name for t in ("scalatest", "scalactic", "chiseltest")) for name in names))

    def test_offline_default_plan_does_not_construct_transport(self):
        with mock.patch.object(acq, "default_opener", side_effect=AssertionError("offline command")), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(acq.main([]), 0)
        self.assertEqual(len(json.loads(out.getvalue())), 5)

    def test_plan_tampering_fails_before_parse(self):
        with mock.patch.object(Path, "read_bytes", return_value=b"{}"):
            with self.assertRaisesRegex(acq.AcquisitionError, "digest"):
                acq.load_plan("jar87")

    def test_unknown_group_rejected(self):
        for group in ("jar106", "union", "all", "../jar87"):
            with self.assertRaises(acq.AcquisitionError):
                acq.load_plan(group)

    def test_exact_bytes_pass_known_and_unknown_size(self):
        for known in (True, False):
            sink = io.BytesIO()
            record = self.stream_check(b"test", fixture(b"test", known=known), sink)
            self.assertEqual(record["size_bytes"], 4)
            self.assertEqual(sink.getvalue(), b"test")

    def test_mismatch_truncation_and_trailing_bytes_fail(self):
        plan = fixture(b"test")
        for data in (b"test!", b"tes", b"tess"):
            with self.subTest(data=data), self.assertRaises(acq.AcquisitionError):
                self.stream_check(data, plan)

    def test_artifact_cap_fails_even_with_matching_prefix_hash(self):
        plan = fixture(b"test", known=False)
        plan["artifacts"][0]["max_transfer_bytes"] = 4
        with self.assertRaisesRegex(acq.AcquisitionError, "cap"):
            self.stream_check(b"testMORE", plan)

    def test_total_cap_blocks_before_more_than_cap_is_read(self):
        data = b"bounded stream"
        plan = fixture(data, known=False)
        plan["limits"]["total_transfer_bytes"] = 3
        source = io.BytesIO(data)
        budget = acq.Budget(plan["limits"])
        with self.assertRaisesRegex(acq.AcquisitionError, "cap"):
            acq.copy_verified(source, None, plan["artifacts"][0], budget)
        self.assertEqual(source.tell(), 3)
        self.assertEqual(budget.bytes, 3)

    def test_elapsed_budget_is_checked(self):
        plan = fixture(b"bytes")
        ticks = iter((0, 61))
        budget = acq.Budget(plan["limits"], clock=lambda: next(ticks))
        with self.assertRaisesRegex(acq.AcquisitionError, "elapsed"):
            acq.copy_verified(io.BytesIO(b"bytes"), None, plan["artifacts"][0], budget)

    def test_invalid_destinations_and_collisions_fail(self):
        for path in ("/x", "../x", "a/../x", "a//b", "a/./b", "a\\b", "C:/x", "x\x00y", "ACQUISITION.json", "fixture.bin.part"):
            plan = fixture()
            plan["artifacts"][0]["relative_destination"] = path
            with self.subTest(path=path), self.assertRaises(acq.AcquisitionError):
                acq.validate_plan(plan)
        for second_path in ("fixture.bin", "fixture.bin/child"):
            plan = fixture()
            plan["artifacts"].append(copy.deepcopy(plan["artifacts"][0]))
            plan["artifacts"][1]["relative_destination"] = second_path
            plan["artifact_count"] = 2
            with self.assertRaises(acq.AcquisitionError):
                acq.validate_plan(plan)

    def test_nonfinite_limits_and_invalid_hash_fail(self):
        for value in (0, -1, None, True, "100", float("inf")):
            plan = fixture()
            plan["limits"]["total_transfer_bytes"] = value
            with self.subTest(value=value), self.assertRaises(acq.AcquisitionError):
                acq.validate_plan(plan)
        plan = fixture()
        plan["artifacts"][0]["sha256"] = "latest"
        with self.assertRaises(acq.AcquisitionError):
            acq.validate_plan(plan)

    def test_alternate_credentialed_encoded_and_traversing_urls_fail(self):
        for url in ("http://repo.maven.apache.org/maven2/x", "https://other.example/x", "https://user:pass@repo.maven.apache.org/maven2/x", acq.URL_PREFIXES["jar87"] + "../x", acq.URL_PREFIXES["jar87"] + "%2ex", acq.URL_PREFIXES["jar87"] + "x?token=secret"):
            plan = fixture()
            plan["artifacts"][0]["url"] = url
            with self.subTest(url=url), self.assertRaises(acq.AcquisitionError):
                acq.validate_plan(plan)

    def test_redirect_is_rejected(self):
        with self.assertRaisesRegex(acq.AcquisitionError, "redirect"):
            acq.NoRedirect().redirect_request(None, None, 302, "", {}, "https://alternate.example/")

    def test_default_opener_keeps_default_proxy_handler(self):
        with mock.patch.object(acq.urllib.request, "build_opener") as builder:
            acq.default_opener()
        args, kwargs = builder.call_args
        self.assertEqual(kwargs, {})
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], acq.NoRedirect)

    def test_bad_response_headers_status_url_and_encoding_fail(self):
        artifact = fixture(b"data")["artifacts"][0]
        for kwargs in ({"status": 206}, {"url": "https://other.example/"}, {"encoding": "gzip"}, {"length": "bad"}, {"length": 5}, {"length": 3}):
            with self.subTest(kwargs=kwargs), self.assertRaises(acq.AcquisitionError):
                acq.check_response(Response(b"data", artifact, **kwargs), artifact)
        response = Response(b"data", artifact, length=4)
        response.headers["Content-Length"] = "4"
        with self.assertRaisesRegex(acq.AcquisitionError, "ambiguous"):
            acq.check_response(response, artifact)

    def test_synthetic_fetch_records_verified_identity_no_execution(self):
        data = b"verified fixture"
        plan = fixture(data)
        opener = mock.Mock()
        opener.open.return_value = Response(data, plan["artifacts"][0], length=len(data))
        root = self.base / "output"
        receipt = acq.acquire(plan, root, opener=opener)
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual((root / "fixture.bin").read_bytes(), data)
        self.assertEqual(receipt["status"], "VERIFIED_OPAQUE_BYTES_ONLY")
        for key in ("extracted", "installed", "executed", "host_compilation_or_rtl_evidence"):
            self.assertFalse(receipt[key])
        self.assertTrue((root / "ACQUISITION.json").is_file())
        self.assertFalse((root / "FAILED.json").exists())
        self.assertEqual(acq.verify(plan, root)["status"], "FRESH_BYTE_VERIFICATION_ONLY")

    def test_failure_has_no_success_receipt_no_retry_and_no_partial(self):
        plan = fixture(b"expected")
        opener = mock.Mock()
        opener.open.return_value = Response(b"bad", plan["artifacts"][0])
        root = self.base / "output"
        with self.assertRaises(acq.AcquisitionError):
            acq.acquire(plan, root, opener=opener)
        self.assertEqual(opener.open.call_count, 1)
        self.assertFalse((root / "ACQUISITION.json").exists())
        self.assertFalse((root / "fixture.bin").exists())
        self.assertEqual(list(root.glob("*.part")), [])
        self.assertEqual(json.loads((root / "FAILED.json").read_text())["status"], "INCOMPLETE_NO_ACQUISITION_SUCCESS")

    def test_transport_failure_is_not_retried(self):
        opener = mock.Mock()
        opener.open.side_effect = OSError("synthetic route failure")
        with self.assertRaises(OSError):
            acq.acquire(fixture(), self.base / "output", opener=opener)
        self.assertEqual(opener.open.call_count, 1)

    def test_idma_uses_materialized_file_and_never_transport(self):
        data = b"synthetic connector artifact"
        plan = fixture(data, "idma")
        source = self.base / "connector.zip"
        source.write_bytes(data)
        with mock.patch.object(acq, "default_opener", side_effect=AssertionError("idma must not download")):
            receipt = acq.acquire(plan, self.base / "output", materialized_idma=source)
        self.assertEqual(receipt["received_bytes"], len(data))
        self.assertEqual(receipt["artifacts"][0]["transport"], "connector-materialized-only")

    def test_idma_missing_input_and_other_group_input_rejected(self):
        for plan, source in ((fixture(group="idma"), None), (fixture(), self.base / "unused")):
            with self.assertRaisesRegex(acq.AcquisitionError, "idma"):
                acq.acquire(plan, self.base / "output", materialized_idma=source)
        self.assertFalse((self.base / "output").exists())

    def test_idma_bad_size_hash_symlink_and_nonregular_fail(self):
        plan = fixture(b"good", "idma")
        source = self.base / "connector.zip"
        for i, data in enumerate((b"bad", b"evil")):
            source.write_bytes(data)
            with self.assertRaises(acq.AcquisitionError):
                acq.acquire(plan, self.base / ("output" + str(i)), materialized_idma=source)
        link = self.base / "symlink.zip"
        link.symlink_to(source)
        with self.assertRaisesRegex(acq.AcquisitionError, "symlink"):
            acq.open_regular(link)
        with self.assertRaises(acq.AcquisitionError):
            acq.open_regular(self.base)

    def test_existing_and_repository_output_rejected(self):
        with self.assertRaises(acq.AcquisitionError):
            acq.checked_output_root(HERE / "never-created", self.repository, True)
        with self.assertRaises(acq.AcquisitionError):
            acq.checked_output_root(self.repository, self.repository, True)
        with self.assertRaises(acq.AcquisitionError):
            acq.checked_output_root(Path("relative-output"), self.repository, True)
        with self.assertRaises(FileExistsError):
            acq.acquire(fixture(), self.base)

    def test_explicit_repository_guard_survives_candidate_relocation(self):
        with mock.patch.object(acq, "SOURCE_CANDIDATE", self.base / "relocated-code"):
            output = self.base / "isolated-output"
            self.assertEqual(acq.checked_output_root(output, self.repository, True), output)
            self.assertFalse(output.exists())
            output.mkdir()
            self.assertEqual(acq.checked_output_root(output, self.repository, False), output)
            with self.assertRaises(acq.AcquisitionError):
                acq.checked_output_root(output, self.repository, True)
            for must_be_new in (True, False):
                with self.assertRaises(acq.AcquisitionError):
                    acq.checked_output_root(self.repository / "artifacts", self.repository, must_be_new)
            with self.assertRaisesRegex(acq.AcquisitionError, "checkout"):
                acq.checked_output_root(output, self.base, False)

    def test_verify_cli_refuses_repository_and_candidate_artifact_roots(self):
        for root in (self.repository, HERE):
            with redirect_stderr(io.StringIO()) as err:
                result = acq.main(["verify", "jar87", "--repository", str(self.repository), "--output-root", str(root)])
            self.assertEqual(result, 1)
            self.assertIn("outside", err.getvalue())

    def test_receipt_write_is_atomic_and_never_overwrites(self):
        path = self.base / "receipt.json"
        def fail_dump(value, handle, **kwargs):
            handle.write("partial")
            raise OSError("synthetic disk error")
        with mock.patch.object(acq.json, "dump", side_effect=fail_dump):
            with self.assertRaises(OSError):
                acq.write_json(path, {"success": True})
        self.assertFalse(path.exists())
        self.assertFalse((self.base / "receipt.json.part").exists())
        acq.write_json(path, {"first": True})
        with self.assertRaises(FileExistsError):
            acq.write_json(path, {"second": True})
        self.assertEqual(json.loads(path.read_text()), {"first": True})
        blocked = self.base / "foreign.json.part"
        blocked.write_bytes(b"existing file is untouched")
        with self.assertRaises(FileExistsError):
            acq.write_json(self.base / "foreign.json", {"third": True})
        self.assertEqual(blocked.read_bytes(), b"existing file is untouched")

    def test_receipt_cleanup_failure_keeps_one_committed_terminal_record(self):
        # Exact independent-audit counterexample, with the corrected expectation.
        data=b'good';plan=fixture(data);root=self.base/'output';unlink=Path.unlink
        opener=mock.Mock();opener.open.return_value=Response(data,plan['artifacts'][0])
        def fail_receipt_cleanup(path,*args,**kwargs):
            if path.name=='ACQUISITION.json.part':raise OSError('synthetic cleanup I/O failure')
            return unlink(path,*args,**kwargs)
        with mock.patch.object(Path,'unlink',fail_receipt_cleanup):
            receipt=acq.acquire(plan,root,opener=opener)
        self.assertTrue((root/'ACQUISITION.json').exists())
        self.assertFalse((root/'FAILED.json').exists())
        self.assertTrue((root/'ACQUISITION.json.part').exists())
        self.assertEqual(receipt['post_commit_cleanup_warning']['cleanup_error']['error_type'],'OSError')
        self.assertEqual(json.loads((root/'CLEANUP_WARNING.json').read_text())['status'],
                         'COMMITTED_ACQUISITION_CLEANUP_WARNING')

    def test_failed_partial_cleanup_preserves_hash_error_and_failure_record(self):
        plan=fixture(b'good');root=self.base/'output';unlink=Path.unlink
        opener=mock.Mock();opener.open.return_value=Response(b'evil',plan['artifacts'][0])
        def fail_partial_cleanup(path,*args,**kwargs):
            if path.name=='fixture.bin.part':raise OSError('synthetic cleanup I/O failure')
            return unlink(path,*args,**kwargs)
        with mock.patch.object(Path,'unlink',fail_partial_cleanup):
            with self.assertRaisesRegex(acq.AcquisitionError,'SHA-256 mismatch'):
                acq.acquire(plan,root,opener=opener)
        self.assertFalse((root/'ACQUISITION.json').exists())
        failure=json.loads((root/'FAILED.json').read_text())
        self.assertEqual(failure['error_type'],'AcquisitionError')
        self.assertEqual(failure['cleanup_errors'],[{'path':'fixture.bin.part','error_type':'OSError'}])
        self.assertEqual(failure['received_bytes'],4)
        self.assertEqual((root/'fixture.bin.part').read_bytes(),b'evil')

    def test_deadline_rejected_bytes_are_accounted_before_rejection(self):
        plan=fixture(b'good');now=[0]
        class SlowSynthetic(io.BytesIO):
            def read1(self,n):
                data=super().read1(n);now[0]=61;return data
        stream=SlowSynthetic(b'good');budget=acq.Budget(plan['limits'],clock=lambda:now[0])
        with self.assertRaisesRegex(acq.AcquisitionError,'elapsed'):
            acq.copy_verified(stream,None,plan['artifacts'][0],budget)
        self.assertEqual(stream.tell(),4)
        self.assertEqual(budget.bytes,4)

    def test_fetch_requires_explicit_accident_guard_before_output(self):
        output = self.base / "not-created"
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(acq.main(["fetch", "jar87", "--repository", str(self.repository), "--output-root", str(output)]), 1)
        self.assertIn("disabled", err.getvalue())
        self.assertFalse(output.exists())

    def test_source_has_no_execution_extraction_or_environment_mutation(self):
        tree = ast.parse((HERE / "acquire.py").read_text())
        forbidden_imports = {"subprocess", "tarfile", "zipfile", "ctypes", "importlib", "ssl"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                self.assertFalse(any(n.split(".")[0] in forbidden_imports for n in names))
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ("exec", "eval", "compile"))
                if isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, ("system", "popen", "chmod", "putenv", "unsetenv", "extractall", "install_opener"))
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")


if __name__ == "__main__":
    unittest.main()
