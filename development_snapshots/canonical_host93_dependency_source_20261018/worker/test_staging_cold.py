"""Synthetic-only tests. No package body reads, package materialization or tool run."""
import copy
import hashlib
import json
import lzma
from pathlib import Path
import types
import sys
import unittest
from unittest import mock

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise ValueError("use python -I -S -B before loading project code")

HERE = Path(__file__).absolute().parent
MODULE = HERE / "stage_dependencies.py"
WORKER_PIN = {"bytes": 20634, "sha256": "3f56c0b6ce0f41f245abf8d37ff55fa5257d71ead395f49410a2746924682a79"}


def load_raw(raw, path):
    if len(raw) != WORKER_PIN["bytes"]:
        raise ValueError("cold worker source size")
    if hashlib.sha256(raw).hexdigest() != WORKER_PIN["sha256"]:
        raise ValueError("cold worker source SHA256")
    module = types.ModuleType("fixed_staging_cold")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


with MODULE.open("rb") as source:
    WORKER_RAW = source.read(WORKER_PIN["bytes"] + 1)
s = load_raw(WORKER_RAW, MODULE)


def tar_header(name, kind="0", body=b"", link="", mode=0o644):
    h = bytearray(512)
    h[:len(name)] = name.encode("ascii")
    def number(start, width, n):
        h[start:start+width] = ("%0*o" % (width-1, n)).encode() + b"\0"
    number(100, 8, mode); number(108, 8, 0); number(116, 8, 0)
    number(124, 12, len(body)); number(136, 12, 0)
    h[148:156] = b" " * 8
    h[156] = ord(kind)
    h[157:157+len(link)] = link.encode()
    h[257:265] = b"ustar  \0"
    h[265:269] = b"root"; h[297:301] = b"root"
    h[148:156] = ("%06o" % sum(h)).encode() + b"\0 "
    return bytes(h) + body + b"\0" * ((-len(body)) % 512)


def tar_fixture(entries):
    raw = b"".join(tar_header(**x) for x in entries) + b"\0" * 1024
    types_count = {}
    for entry in entries:
        kind = entry.get("kind", "0")
        types_count[kind] = types_count.get(kind, 0) + 1
    framing = {"expanded_bytes": len(raw), "raw_headers": len(entries), "types": types_count,
               "magic8_hex_counts": {"7573746172202000": len(entries)}, "zero_tail_bytes": 1024}
    return raw, framing


def ar_fixture(parts):
    raw = b"!<arch>\n"
    expected = []
    for name, body in parts:
        h = name.encode().ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6) + b"100644".ljust(8) + str(len(body)).encode().ljust(10) + b"`\n"
        raw += h + body + (b"\n" if len(body) % 2 else b"")
        expected.append({"name": name, "bytes": len(body), "sha256": s.sha(body), "prefix_hex": body[:12].hex()})
    return raw, expected


def cfg_fixture():
    lines = [b"# synthetic fixture\n"] * 175
    for n in s.CFG_LINES: lines[n-1] = s.CFG_OLD
    return b"".join(lines)


def cfg_patches(raw):
    derived = raw.replace(s.CFG_OLD, s.CFG_NEW)
    return mock.patch.multiple(s, CFG_BYTES=len(raw), CFG_SHA=s.sha(raw), CFG_DERIVED_BYTES=len(derived), CFG_DERIVED_SHA=s.sha(derived))


def package_fixture():
    cfg = cfg_fixture()
    ctl, cf = tar_fixture([
        {"name": "./", "kind": "5", "mode": 0o755},
        {"name": "./control", "body": b"Package: synthetic\nVersion: 2:1.0-1\nArchitecture: all\nDescription: synthetic\n details\n"}])
    entries = [{"name": "./", "kind": "5", "mode": 0o755},
               {"name": "./" + s.CFG_PATH, "body": cfg},
               {"name": "./usr/bin/mocktool", "body": b"synthetic, never executed\n", "mode": 0o755}]
    for i in range(6):
        entries.append({"name": "./unused%d" % i, "kind": "2", "mode": 0o777, "link": "/absolute/ignored" if i % 2 else "../../ignored"})
    data, df = tar_fixture(entries)
    deb, ar = ar_fixture([( "debian-binary", b"2.0\n"), ("control.tar.xz", lzma.compress(ctl)), ("data.tar.xz", lzma.compress(data))])
    rows, bodies = s.parse_tar(data, df)
    selected = [{"path": r["name"][2:], "raw_tar_path": r["name"], "kind": "regular", "tar_type": "0", "mode": r["mode"], "bytes": r["bytes"], "sha256": r["sha256"]} for r in rows if r["type"] == "0"]
    pin = {"package": "synthetic", "deb_filename": "synthetic.deb", "deb_bytes": len(deb), "deb_sha256": s.sha(deb), "ar": ar,
           "control_framing": cf, "control_tar_sha256": s.sha(ctl), "control_fields": {"Package": "synthetic", "Version": "2:1.0-1", "Architecture": "all"},
           "data_tar_bytes": len(data), "data_tar_sha256": s.sha(data), "data_framing": df, "members": rows, "selected": selected}
    return deb, pin, cfg


class Cold(unittest.TestCase):
    def setUp(self):
        self.deb, self.pin, self.cfg = package_fixture()

    def test_cold_loader_short_before_compile(self):
        with mock.patch("builtins.compile") as compiler:
            with self.assertRaisesRegex(ValueError, "source size"):
                load_raw(b"BAD", MODULE)
            compiler.assert_not_called()

    def test_cold_loader_equal_size_wrong_sha_before_compile(self):
        with mock.patch("builtins.compile") as compiler:
            with self.assertRaisesRegex(ValueError, "source SHA256"):
                load_raw(b"#" * WORKER_PIN["bytes"], MODULE)
            compiler.assert_not_called()

    def test_cold_loader_valid_synthetic_same_buffer(self):
        raw = b"SYNTHETIC_BUFFER_MARKER = 731\n"
        pin = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        with mock.patch.dict(WORKER_PIN, pin):
            module = load_raw(raw, MODULE)
        self.assertEqual(module.SYNTHETIC_BUFFER_MARKER, 731)

    def test_template_metadata_requires_new_binding(self):
        pins = s.load_pins()
        self.assertIsNone(pins["actual_identity_review"])
        self.assertEqual(pins["derived_cfg"], {"bytes": None, "sha256": None})
        self.assertEqual(pins["input_root"], "/UNBOUND_HOST93_DEPENDENCY_INPUT")
        self.assertEqual(pins["output_root"], "/UNBOUND_HOST93_DEPENDENCY_OUTPUT")

    def test_template_stage_rejects_before_package_or_writer(self):
        pins = s.load_pins()
        with mock.patch.object(s, "load_pins", return_value=pins), mock.patch.object(s, "open_absolute_dir") as opened, mock.patch.object(s, "FreshWriter") as writer:
            with self.assertRaisesRegex(ValueError, "ACTUAL_IDENTITY_REVIEW_PENDING"):
                s.stage_fixed()
            opened.assert_not_called()
            writer.assert_not_called()

    def test_01_pinned_metadata_only(self):
        raw = (HERE / "PINS.json").read_bytes()
        self.assertEqual(len(raw), s.PINS_BYTES); self.assertEqual(s.sha(raw), s.PINS_SHA256)
        pins = json.loads(raw)
        self.assertEqual(len(pins["packages"]), 5)
        self.assertEqual(sum(len(p["selected"]) for p in pins["packages"]), 67)
        self.assertEqual(sum(x["bytes"] for p in pins["packages"] for x in p["selected"]), 3598623)
        bison = next(p for p in pins["packages"] if p["package"] == "bison")
        self.assertEqual(bison["control_fields"]["Version"], "2:3.8.2+dfsg-1+b2")
        self.assertEqual(pins["derived_cfg"], {"bytes": s.CFG_DERIVED_BYTES, "sha256": s.CFG_DERIVED_SHA})

    def test_02_package_positive_and_unmaterialized_links(self):
        members, report = s.validate_package(self.deb, self.pin)
        self.assertEqual(set(members), {s.CFG_PATH, "usr/bin/mocktool"})
        self.assertEqual(len(report["ignored_links"]), 6)
        self.assertTrue(all(not x["materialized"] for x in report["ignored_links"]))
        self.assertEqual(report["ignored_links"][0]["target"], "../../ignored")

    def test_03_package_corruption(self):
        with self.assertRaisesRegex(ValueError, "deb synthetic identity"):
            s.validate_package(self.deb[:-1] + b"x", self.pin)

    def test_04_member_identity_deltas(self):
        for key, value in [("mode", "0o755"), ("bytes", 1), ("sha256", "0"*64), ("type", "2")]:
            pin = copy.deepcopy(self.pin); pin["members"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): s.validate_package(self.deb, pin)

    def test_05_selected_identity_deltas(self):
        for key, value in [("mode", "0o755"), ("bytes", 1), ("sha256", "0"*64), ("tar_type", "2"), ("kind", "symlink"), ("path", "../escape")]:
            pin = copy.deepcopy(self.pin); pin["selected"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): s.validate_package(self.deb, pin)

    def test_06_epoch_is_not_optional(self):
        pin = copy.deepcopy(self.pin); pin["control_fields"]["Version"] = "1.0-1"
        with self.assertRaisesRegex(ValueError, "control Package/Version/Architecture"):
            s.validate_package(self.deb, pin)

    def test_07_ar_framing_rejections(self):
        _, expected = ar_fixture([( "debian-binary", b"2.0\n"), ("control.tar.xz", b"x"), ("data.tar.xz", b"y")])
        valid, _ = ar_fixture([( "debian-binary", b"2.0\n"), ("control.tar.xz", b"x"), ("data.tar.xz", b"y")])
        for raw in [b"bad"+valid[3:], valid[:-1], valid+b"x", valid[:8]+b"/"+valid[9:], valid[:66]+b"xx"+valid[68:], valid.replace(b"control.tar.xz", b"control.tar.gz")]:
            with self.subTest(length=len(raw)), self.assertRaises((ValueError, UnicodeError)):
                s.ar_entries(raw, expected)

    def test_08_xz_positive(self):
        raw = b"mock" * 64
        self.assertEqual(s.expand_xz(lzma.compress(raw), len(raw), s.sha(raw)), raw)

    def test_09_xz_tail_concat_truncated_bomb(self):
        raw = b"mock" * 64; enc = lzma.compress(raw)
        for value in [enc + b"\0", enc + enc, enc[:-2], enc + b"junk"]:
            with self.subTest(length=len(value)), self.assertRaises((ValueError, lzma.LZMAError)):
                s.expand_xz(value, len(raw), s.sha(raw))
        with self.assertRaises(ValueError): s.expand_xz(enc, 1, s.sha(b"m"))

    def test_10_tar_unknown_types_and_traversal(self):
        for name, kind in [("./bad", "x"), ("./bad", "L"), ("./bad", "1"), ("./bad", "3"), ("/escape", "0"), ("./../escape", "0"), ("././bad", "0"), ("./a//b", "0")]:
            raw, f = tar_fixture([{"name": name, "kind": kind}])
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError): s.parse_tar(raw, f)

    def test_11_tar_duplicate_collision(self):
        samples = [[{"name": "./a"}, {"name": "./a"}], [{"name": "./a"}, {"name": "./a/b"}], [{"name": "./a/b"}, {"name": "./a"}], [{"name": "./a", "kind": "2", "link": "x"}, {"name": "./a/b"}]]
        for entries in samples:
            raw, f = tar_fixture(entries)
            with self.subTest(entries=entries), self.assertRaises(ValueError): s.parse_tar(raw, f)

    def test_12_tar_checksum_tail_padding_unknown_extension(self):
        raw, f = tar_fixture([{"name": "./x", "body": b"x"}])
        for offset in [0, 345, 513, len(raw)-1]:
            bad = bytearray(raw); bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError): s.parse_tar(bytes(bad), f)
        bad = raw[:-512]; ff = dict(f, expanded_bytes=len(bad), zero_tail_bytes=512)
        with self.assertRaises(ValueError): s.parse_tar(bad, ff)

    def test_13_base256_and_invalid_modes(self):
        raw, f = tar_fixture([{"name": "./x"}])
        for offset, replacement in [(100, 128), (124, 128), (257, ord("v"))]:
            bad = bytearray(raw); bad[offset] = replacement
            with self.subTest(offset=offset), self.assertRaises(ValueError): s.parse_tar(bytes(bad), f)
        raw, f = tar_fixture([{"name": "./x", "mode": 0o4755}])
        with self.assertRaises(ValueError): s.parse_tar(raw, f)

    def test_14_cfg_exact_four_and_inverse(self):
        with cfg_patches(self.cfg):
            derived, report = s.relocate_cfg(self.cfg)
            self.assertEqual(derived.replace(s.CFG_NEW, s.CFG_OLD), self.cfg)
            self.assertEqual([x["line"] for x in report["line_diff"]], [118,145,159,171])
            self.assertEqual(report["replacements"], 4)

    def test_15_cfg_changed_origin_or_derived_pin(self):
        with cfg_patches(self.cfg):
            with self.assertRaises(ValueError): s.relocate_cfg(self.cfg + b"\n")
            with mock.patch.object(s, "CFG_DERIVED_SHA", "0"*64), self.assertRaises(ValueError): s.relocate_cfg(self.cfg)

    def test_16_cfg_occurrence_and_line_changes(self):
        for raw in [self.cfg.replace(s.CFG_OLD, b"# removed\n", 1), b"# extra\n" + self.cfg, self.cfg + s.CFG_OLD]:
            with cfg_patches(raw), self.assertRaises(ValueError): s.relocate_cfg(raw)

    def test_17_paths_rejected(self):
        for p in ["/abs", "../bad", "a/../b", "a//b", "a/./b", "a\\b", "a\nb", "", "a:b"]:
            with self.subTest(path=p), self.assertRaises(ValueError): s.clean_relative(p)

    def test_18_pending_actual_review_before_read(self):
        with mock.patch.object(s, "open_absolute_dir") as opening:
            with self.assertRaisesRegex(ValueError, "PENDING"): s.require_actual_review({"actual_identity_review": None})
            opening.assert_not_called()

    def test_19_no_actual_cli_or_external_execution(self):
        import ast
        tree = ast.parse(MODULE.read_text())
        imports = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.assertFalse(set(imports) & {"subprocess", "tarfile", "shutil", "socket", "urllib"})
        calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertFalse(set(calls) & {"system", "popen", "execv", "execve", "chmod", "symlink", "link", "extractall"})

    def test_20_synthetic_stage_entire_pipeline_without_io(self):
        written = {}
        class MemoryWriter:
            def __init__(self, root):
                self.files = {}; self.total = 0
            def write(self, path, raw):
                if path in written: raise ValueError("duplicate")
                written[path] = raw; self.total += len(raw)
                self.files[path] = {"bytes":len(raw), "sha256":s.sha(raw), "mode":"0o600"}
            def close(self): pass
        pins = {"packages": [self.pin]}
        members, _ = s.validate_package(self.deb, self.pin)
        with cfg_patches(self.cfg), mock.patch.multiple(s, SELECTED_COUNT=len(members), SELECTED_BYTES=sum(map(len,members.values()))), mock.patch.object(s,"load_pins",return_value=pins), mock.patch.object(s,"require_actual_review"), mock.patch.object(s,"open_absolute_dir",return_value=77), mock.patch.object(s,"read_fixed_at",return_value=(self.deb,(1,2,3))), mock.patch.object(s,"FreshWriter",MemoryWriter), mock.patch.object(s.os,"close"):
            result = s.stage_fixed()
        self.assertEqual(set(written), {s.CFG_PATH, "usr/bin/mocktool", "relocation/autom4te.cfg", "STAGING_REPORT.json"})
        self.assertEqual(written[s.CFG_PATH], self.cfg)
        self.assertEqual(result["output_files"], 4)
        self.assertEqual(json.loads(written["STAGING_REPORT.json"])["qualification"], "NOT_RUN")

    def test_21_writer_duplicate_and_caps_before_io(self):
        writer = object.__new__(s.FreshWriter)
        writer.files = {"a": {}}; writer.total = 0; writer.fd = 1
        with mock.patch.object(s.os, "dup") as dup:
            with self.assertRaises(ValueError): writer.write("a", b"x")
            with self.assertRaises(ValueError): writer.write("b", b"x" * (s.MAX_FILE_BYTES + 1))
            writer.total = s.MAX_OUTPUT_BYTES
            with self.assertRaises(ValueError): writer.write("b", b"x")
            dup.assert_not_called()

    def test_22_fresh_root_existing_refused(self):
        with mock.patch.object(s,"open_absolute_dir",return_value=1), mock.patch.object(s.os,"mkdir",side_effect=FileExistsError), mock.patch.object(s.os,"close"), mock.patch.object(s.os,"open") as opening:
            with self.assertRaises(FileExistsError): s.FreshWriter(s.OUTPUT_ROOT)
            opening.assert_not_called()

    def test_23_no_follow_and_exclusive_flags(self):
        self.assertTrue(s.READ_FLAGS & s.os.O_NOFOLLOW)
        self.assertTrue(s.DIRECTORY_FLAGS & s.os.O_NOFOLLOW)
        source = MODULE.read_text()
        self.assertIn("os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW", source)

    def test_24_json_duplicate_keys(self):
        with self.assertRaises(ValueError): s.json_unique(b'{"a":1,"a":2}')

    def test_25_read_input_before_after_and_replacement(self):
        good = types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=0o100600,st_nlink=1,st_size=3,st_mtime_ns=4,st_ctime_ns=5)
        bad = types.SimpleNamespace(**{**vars(good), "st_ino": 99})
        with mock.patch.object(s.os,"open",return_value=2), mock.patch.object(s.os,"close"), mock.patch.object(s.os,"read",side_effect=[b"abc",b""]), mock.patch.object(s.os,"fstat",return_value=good), mock.patch.object(s.os,"stat",return_value=good):
            self.assertEqual(s.read_fixed_at(1,"a",3,s.sha(b"abc"))[0],b"abc")
        with mock.patch.object(s.os,"open",return_value=2), mock.patch.object(s.os,"close"), mock.patch.object(s.os,"read",side_effect=[b"abc",b""]), mock.patch.object(s.os,"fstat",return_value=good), mock.patch.object(s.os,"stat",return_value=bad):
            with self.assertRaisesRegex(ValueError,"path replacement"): s.read_fixed_at(1,"a",3,s.sha(b"abc"))

    def test_26_read_symlink_or_hardlink_before_body(self):
        for mode, links in [(0o120777,1),(0o100600,2)]:
            st = types.SimpleNamespace(st_mode=mode,st_nlink=links,st_size=3)
            with mock.patch.object(s.os,"open",return_value=2), mock.patch.object(s.os,"close"), mock.patch.object(s.os,"fstat",return_value=st), mock.patch.object(s.os,"read") as reading:
                with self.assertRaises(ValueError): s.read_fixed_at(1,"a",3,s.sha(b"abc"))
                reading.assert_not_called()

    def test_27_descriptor_writer_positive_all0600(self):
        writer = object.__new__(s.FreshWriter)
        writer.files = {}; writer.total = 0; writer.fd = 10
        st = types.SimpleNamespace(st_mode=0o100600,st_nlink=1,st_size=3)
        with mock.patch.object(s.os,"dup",return_value=11), mock.patch.object(s.os,"mkdir"), mock.patch.object(s.os,"open",side_effect=[12,13]) as opening, mock.patch.object(s.os,"close"), mock.patch.object(s.os,"write",return_value=3), mock.patch.object(s.os,"fsync"), mock.patch.object(s.os,"fstat",return_value=st), mock.patch.object(s,"read_fixed_at",return_value=(b"abc",())):
            writer.write("a/b", b"abc")
        self.assertEqual(writer.total,3)
        self.assertEqual(writer.files["a/b"]["mode"],"0o600")
        self.assertEqual(opening.call_args_list[0].args[1],s.DIRECTORY_FLAGS)
        self.assertEqual(opening.call_args_list[1].args[2],0o600)
        self.assertTrue(opening.call_args_list[1].args[1] & s.os.O_EXCL)

    def test_28_writer_symlink_directory_open_refusal(self):
        writer = object.__new__(s.FreshWriter)
        writer.files = {}; writer.total = 0; writer.fd = 10
        with mock.patch.object(s.os,"dup",return_value=11), mock.patch.object(s.os,"mkdir",side_effect=FileExistsError), mock.patch.object(s.os,"open",side_effect=OSError("NOFOLLOW")), mock.patch.object(s.os,"close"), mock.patch.object(s.os,"write") as writing:
            with self.assertRaises(OSError): writer.write("symlink/path",b"x")
            writing.assert_not_called()
        self.assertEqual(writer.files,{})


if __name__ == "__main__":
    unittest.main(verbosity=2)
