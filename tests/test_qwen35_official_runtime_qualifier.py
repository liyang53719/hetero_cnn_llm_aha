"""Stdlib-only qualifier fixtures: never install/import Torch or qualify a runtime."""
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / "scripts/qualify_qwen35_official_runtime.py"
spec = importlib.util.spec_from_file_location("qwen35_qualifier_fixture_module", SOURCE)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class QualifierFixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / "site-packages"
        self.site.mkdir()

    def write(self, relative, raw):
        path = self.site / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def test_module_import_does_not_load_numerical_packages(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_relative_paths_reject_escapes_and_ambiguity(self):
        for value in ("", ".", "..", "../x", "/x", "x//y", "x/./y", "x/../y", "x\\y", "x\x00y"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                q.safe_relative(value)
        self.assertEqual(str(q.safe_relative("safe/file.json")), "safe/file.json")

    def test_file_record_is_measured_and_detects_tampering(self):
        path = self.write("sample.py", b"pass\n")
        record = q.file_record(self.root, path)
        self.assertEqual(record["bytes"], 5)
        self.assertEqual(q.verify_record(self.root, record), record)
        path.write_bytes(b"fail\n")
        with self.assertRaisesRegex(ValueError, "drift"):
            q.verify_record(self.root, record)

    def test_artifact_symlink_and_external_path_rejected(self):
        source = self.write("sample", b"a")
        link = self.site / "link"
        link.symlink_to(source)
        with self.assertRaises(ValueError):
            q.file_record(self.root, link)
        with self.assertRaises(ValueError):
            q.file_record(self.site, self.root / "outside")

    def test_duplicate_json_keys_rejected(self):
        path = self.write("input.json", b'{"checks":{},"checks":{"fake":true}}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            q.read_json(path)

    def test_write_new_never_overwrites(self):
        path = self.root / "output.json"
        q.write_new(path, {"first": True})
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            q.write_new(path, {"second": True})
        self.assertEqual(path.read_bytes(), original)

    def test_canonical_direct_url_not_local_or_fabricated_shape(self):
        value = {"url": q.ARCHIVE_URL, "archive_info": {"hashes": {"sha256": q.ARCHIVE_SHA256}}}
        q.verify_direct_url(value)
        for replacement in ("file:///tmp/archive.zip", q.ARCHIVE_URL + "?fake=1"):
            with self.assertRaises(ValueError):
                q.verify_direct_url(dict(value, url=replacement))
        with self.assertRaises(ValueError):
            q.verify_direct_url(dict(value, dir_info={"editable": True}))
        with self.assertRaises(ValueError):
            q.verify_direct_url({"url": q.ARCHIVE_URL, "archive_info": {"hash": "sha256=" + q.ARCHIVE_SHA256}})

    def test_receipt_cannot_accept_empty_or_truthy_checks(self):
        for checks in ({}, {name: True for name in q.REQUIRED_CHECKS - {"python312"}},
                       {name: "true" for name in q.REQUIRED_CHECKS}):
            with self.assertRaises(ValueError):
                q.require_checks(checks)
        q.require_checks({name: True for name in q.REQUIRED_CHECKS})
        with self.assertRaises(ValueError):
            q.validate_receipt({"status": "PASS_ISOLATED_PINNED_RUNTIME_READY", "scope": q.SCOPE,
                                "checks": {name: True for name in q.REQUIRED_CHECKS}, "artifacts": {}})

    def test_archive_duplicate_normalized_path_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("same", b"x")
            z.writestr("same/", b"")
        with zipfile.ZipFile(stream) as z, self.assertRaisesRegex(ValueError, "duplicate"):
            q.zip_members(z)

    def test_source_symlink_allowlist_is_exact_and_source_only(self):
        member, expected = next(iter(q.SOURCE_SYMLINKS.items()))
        for raw, source, accepted in ((expected, True, True), (expected, False, False), (b"evil", True, False)):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                info = zipfile.ZipInfo(member)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, raw)
            with zipfile.ZipFile(stream) as z:
                if accepted:
                    self.assertIn(member, q.zip_members(z, source_archive=source))
                else:
                    with self.assertRaises(ValueError):
                        q.zip_members(z, source_archive=source)

    def test_unexpected_special_zip_entry_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            info = zipfile.ZipInfo("fifo")
            info.external_attr = (stat.S_IFIFO | 0o600) << 16
            z.writestr(info, b"")
        with zipfile.ZipFile(stream) as z, self.assertRaises(ValueError):
            q.zip_members(z)

    def test_pinned_pth_allowed_but_not_other_injection_files(self):
        self.write("distutils-precedence.pth", b"pinned fixture\n")
        self.assertIn("distutils-precedence.pth", q.inventory_site(self.root, self.site))
        self.write("evil.pth", b"import evil\n")
        with self.assertRaises(ValueError):
            q.inventory_site(self.root, self.site)

    def test_unexpected_bytecode_rejected(self):
        self.write("package/__pycache__/module.cpython-312.pyc", b"fake")
        with self.assertRaisesRegex(ValueError, "bytecode"):
            q.inventory_site(self.root, self.site)

    def test_nested_vendor_distinfo_not_top_level_distribution(self):
        self.write("demo-1.0.dist-info/METADATA", b"Name: demo\nVersion: 1.0\n")
        self.write("demo-1.0.dist-info/RECORD", b"")
        self.write("demo/_vendor/hidden-7.dist-info/METADATA", b"Name: hidden\nVersion: 7\n")
        self.assertEqual(set(q.distribution_inventory(self.site)), {"demo"})

    def test_native_target_record_relocation_and_hashes(self):
        files = {"demo-1.dist-info/METADATA": b"Name: demo\nVersion: 1\n",
                 "bin/demo": b"#!/python\npass\n", "share/man/man1/demo.1": b"manual\n"}
        for name, raw in files.items():
            self.write(name, raw)
        stream = io.StringIO()
        writer = csv.writer(stream)
        for name, raw in files.items():
            relative = "../../" + name if name.startswith(("bin/", "share/")) else name
            hashed = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
            writer.writerow((relative, "sha256=" + hashed, str(len(raw))))
        writer.writerow(("demo-1.dist-info/RECORD", "", ""))
        self.write("demo-1.dist-info/RECORD", stream.getvalue().encode())
        inventory = q.inventory_site(self.root, self.site)
        dists = q.distribution_inventory(self.site)
        self.assertEqual(set(q.verify_installed_records(self.root, self.site, dists, inventory)), set(inventory))
        self.write("bin/demo", b"tampered\n")
        with self.assertRaisesRegex(ValueError, "RECORD mismatch"):
            q.verify_installed_records(self.root, self.site, dists, q.inventory_site(self.root, self.site))

    def test_wheel_data_mapping_has_no_arbitrary_external_locations(self):
        self.assertEqual(q.wheel_target("demo-1.data/data/share/man/x"), "share/man/x")
        self.assertEqual(q.wheel_target("demo-1.data/scripts/demo"), "bin/demo")
        self.assertEqual(q.wheel_target("demo-1.data/purelib/demo.py"), "demo.py")
        with self.assertRaises(ValueError):
            q.wheel_target("demo-1.data/data/etc/secret")

    def test_nested_vendor_record_is_pinned_payload_not_skipped(self):
        files = {"demo-1.dist-info/METADATA": b"Name: demo\nVersion: 1\n",
                 "demo/__init__.py": b"", "demo/_vendor/x-1.dist-info/RECORD": b"vendor-record\n"}
        for name, raw in files.items():
            self.write(name, raw)
        path = self.root / "demo-1-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as z:
            for name, raw in files.items():
                z.writestr(name, raw)
            z.writestr("demo-1.dist-info/RECORD", b"wheel-record\n")
        inventory = q.inventory_site(self.root, self.site)
        owners = {name: "demo" for name in inventory}
        matched = q.verify_wheel_payload(path, "demo", self.site, inventory, owners, self.site / "demo-1.dist-info/METADATA")
        self.assertIn("demo/_vendor/x-1.dist-info/RECORD", matched)
        self.write("demo/_vendor/x-1.dist-info/RECORD", b"tampered\n")
        with self.assertRaisesRegex(ValueError, "pinned wheel"):
            q.verify_wheel_payload(path, "demo", self.site, q.inventory_site(self.root, self.site), owners,
                                   self.site / "demo-1.dist-info/METADATA")

    def test_empty_or_duplicate_pip_report_rejected(self):
        with self.assertRaises(ValueError):
            q.verify_pip_report({"install": []}, {})
        item = {"metadata": {"name": "demo", "version": "1"}}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            q.verify_pip_report({"install": [item, item]}, {"demo": {"version": "1", "sha256": "0" * 64}})

    def test_exact_generated_entrypoint_body_and_long_shebang(self):
        entry = q.importlib.metadata.EntryPoint("demo", "demo.cli:run", "console_scripts")
        for executable in (Path("/short/python"), Path("/" + "long/" * 30 + "python")):
            exe = str(executable).encode()
            if len(exe) + 3 <= 127:
                shebang = b"#!" + exe + b"\n"
            else:
                shebang = b"#!/bin/sh\n'''exec' " + exe + b' "$0" "$@"\n' + b"' '''\n"
            body = (b"import sys\nfrom demo.cli import run\nif __name__ == '__main__':\n"
                    b"    sys.argv[0] = sys.argv[0].removesuffix('.exe')\n    sys.exit(run())\n")
            path = self.write("bin/demo", shebang + body)
            q.verify_entrypoint_script(path, entry, executable)
            path.write_bytes(shebang + body + b"print('unapproved')\n")
            with self.assertRaises(ValueError):
                q.verify_entrypoint_script(path, entry, executable)

    def guard_fixture(self):
        events = []
        def event(pid, name, parent=True, allowed=True, probe=False, detail="fixture"):
            row = dict(pid=pid, event=name, parent_driver=parent, allowed=allowed,
                       expected_self_test=probe, detail=detail)
            events.append(row)
        for pid in (100, 200):
            event(pid, "guard_activated")
            event(pid, "socket.__new__", allowed=False, probe=True)
            event(pid, "socket_guard_self_test", probe=True)
            event(pid, "ancillary_probes_disabled")
            event(pid, "ipv6_ancillary_probe_suppressed")
            event(pid, "pip_transport_self_test")
        event(200, "subprocess.Popen")
        event(200, "backend_spawned", detail="201")
        event(201, "guard_activated", parent=False)
        event(201, "backend_entry_verified", parent=False)
        summary = dict(native_os_sandbox=False, install_network_bytes=0, socket_guard_exercised=True,
                       pip_download_blocked=True, unexpected_network_attempts=0, verified_backend_pids=[201],
                       guard_activations=[e for e in events if e["event"] == "guard_activated"])
        return events, summary

    def test_guard_requires_measured_exact_negative_probes(self):
        events, summary = self.guard_fixture()
        self.assertEqual(q.verify_network_evidence(events, summary)["socket_denial_probes"], 2)
        events.append(dict(pid=100, event="socket.connect", parent_driver=True, allowed=False,
                           expected_self_test=True, detail="not an approved probe"))
        with self.assertRaises(ValueError):
            q.verify_network_evidence(events, summary)

    def test_guard_rejects_missing_backend_or_duplicate_probe(self):
        events, summary = self.guard_fixture()
        with self.assertRaises(ValueError):
            q.verify_network_evidence([e for e in events if e["event"] != "backend_entry_verified"], summary)
        events.append(dict(events[1]))
        with self.assertRaises(ValueError):
            q.verify_network_evidence(events, summary)

    def test_guard_summary_cannot_claim_a_native_sandbox(self):
        events, summary = self.guard_fixture()
        summary["native_os_sandbox"] = True
        with self.assertRaises(ValueError):
            q.verify_network_evidence(events, summary)

    def test_ipv6_probe_suppression_is_exactly_once_and_not_a_denial(self):
        events, summary = self.guard_fixture()
        suppression = next(e for e in events if e["event"] == "ipv6_ancillary_probe_suppressed")
        with self.assertRaises(ValueError):
            q.verify_network_evidence([e for e in events if e is not suppression], summary)
        with self.assertRaises(ValueError):
            q.verify_network_evidence(events + [dict(suppression)], summary)
        suppression["allowed"] = False
        with self.assertRaises(ValueError):
            q.verify_network_evidence(events, summary)

    def test_multiprocessing_main_alias_is_narrowly_allowed(self):
        original = sys.modules["__main__"]
        module = types.ModuleType("__main__")
        try:
            sys.modules["__main__"] = module
            self.assertTrue(q.is_qualifier_main_alias("__main__", module, SOURCE))
            self.assertTrue(q.is_qualifier_main_alias("__mp_main__", module, SOURCE))
            self.assertFalse(q.is_qualifier_main_alias("__mp_main__", types.ModuleType("fake"), SOURCE))
            self.assertFalse(q.is_qualifier_main_alias("fake", module, SOURCE))
            self.assertFalse(q.is_qualifier_main_alias("__main__", module, self.root / "evil.py"))
        finally:
            sys.modules["__main__"] = original


if __name__ == "__main__":
    unittest.main()
