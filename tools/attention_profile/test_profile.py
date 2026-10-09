# SPDX-License-Identifier: Apache-2.0
"""Small source-identity and synthetic C++ tests; never a production RTL run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("ATTENTION_PROFILE_SOURCE_ROOT", HERE.parents[1]))
spec = importlib.util.spec_from_file_location("attention_profile_generator", HERE / "generate_profile.py")
generator = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(generator)


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=30, **kwargs)


def compile_cpp(source, binary, include):
    result = run(["g++", "-O2", "-std=c++17", "-ffp-contract=off", "-fno-fast-math",
                  "-I", str(include), str(source), "-o", str(binary)])
    if result.returncode:
        raise AssertionError(result.stderr)


class GeneratorTests(unittest.TestCase):
    def test_limit_validation(self):
        for value in ["0", "36", "65537", "-1", "+4096", " 4096", "4096 ", "4e3",
                      "1.0", "0x1000", "99999999999999999", "٤٠٩٦", ""]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                generator.cycle_limit(value)
        self.assertEqual(generator.cycle_limit("4096"), 4096)
        self.assertEqual(generator.cycle_limit("65536"), 65536)

    def test_frozen_sources_exact_reversible_patch_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"
            receipt = generator.generate(ROOT, out, 4096)
            original = generator.frozen_sources(ROOT)
            driver = original["chisel/continuous_prefill/tests/host_bf16_attention_core.cpp"]
            self.assertEqual((out / "host_bf16_attention_core.cpp").read_bytes(), driver)
            self.assertEqual((out / "original/host_bf16_attention_core.cpp").read_bytes(), driver)
            patched = (out / "host_physical_axi.h").read_bytes()
            self.assertEqual(patched.count(b"attentionProfileStep.eval(d,"), 3)
            for old, new in reversed(generator.TRANSFORMS):
                self.assertEqual(patched.count(new), 1)
                patched = patched.replace(new, old, 1)
            self.assertEqual(patched, original["chisel/continuous_prefill/tests/host_physical_axi.h"])
            for name, digest in receipt["generated_files_sha256"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
            self.assertFalse(receipt["numerical_acceptance"])
            with self.assertRaises(ValueError):
                generator.generate(ROOT, out, 4096)
            with self.assertRaises(ValueError):
                generator.generate(ROOT, Path(tmp) / "invalid", True)
            with self.assertRaises(ValueError):
                generator.instrument_header(original["chisel/continuous_prefill/tests/host_physical_axi.h"] + b"d.eval();")

    def test_hash_mismatch_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "generated"
            expected = generator.SOURCE_HASHES.copy()
            try:
                generator.SOURCE_HASHES[next(iter(expected))] = "0" * 64
                with self.assertRaises(ValueError):
                    generator.generate(ROOT, out, 4096)
                self.assertFalse(out.exists())
            finally:
                generator.SOURCE_HASHES.clear()
                generator.SOURCE_HASHES.update(expected)


@unittest.skipUnless(shutil.which("g++"), "small synthetic C++ test requires g++")
class SyntheticCppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="attention-profile-test-")
        cls.root = Path(cls.tmp.name)
        cls.generated = cls.root / "generated"
        generator.generate(ROOT, cls.generated, 96)
        # Compile the *entire unchanged original driver* plus wrapper against a
        # small explicit stub, solely to verify C++ integration and stop flow.
        # This stub is a test asset and is never an input to the production build.
        text = (cls.generated / "host_bf16_attention_core.cpp").read_text()
        text += (cls.generated / "host_physical_axi.h").read_text()
        text += (cls.generated / "profile_runtime.h").read_text()
        fields = set(re.findall(r"\bd\.(\w+)", text)) - {"eval", "io_launch_bits_regions_", "io_axi_", "PORT"}
        fields.update(re.findall(r"PROFILE_PORT\(\"[^\"]+\", (\w+)\)", text))
        for i in range(4):
            for suffix in ["base", "limit", "read", "write"]:
                fields.add(f"io_launch_bits_regions_{i}_{suffix}")
        for channel in ["ar", "aw", "w", "r", "b"]:
            fields.update([f"io_axi_{channel}_valid", f"io_axi_{channel}_ready"])
        for channel in ["ar", "aw"]:
            fields.update(f"io_axi_{channel}_bits_{suffix}" for suffix in ["addr", "id", "len", "size", "burst"])
        data_fields = {"io_axi_r_bits_data", "io_axi_w_bits_data"}
        declarations = "\n".join(f"  uint64_t {name}=0;" for name in sorted(fields - data_fields))
        declarations += "\n" + "\n".join(f"  std::array<uint32_t,16> {name}{{}};" for name in sorted(data_fields))
        (cls.generated / "VHostBlockTop.h").write_text(
            "#pragma once\n#include <array>\n#include <cstdint>\n"
            "#include <cstdlib>\n#include <stdexcept>\n#include <thread>\n#include <chrono>\n"
            "struct VHostBlockTop {\n" + declarations + "\n"
            "  unsigned calls=0;\n"
            "  void eval() {\n"
            "    ++calls; io_launch_ready=1;\n"
            "    if (std::getenv(\"SYNTHETIC_BLOCK\") && calls==4) std::this_thread::sleep_for(std::chrono::seconds(10));\n"
            "    if (std::getenv(\"SYNTHETIC_FAIL\") && calls==125) throw std::runtime_error(\"synthetic eval failure\");\n"
            "    if (std::getenv(\"SYNTHETIC_SLOW\")) std::this_thread::sleep_for(std::chrono::microseconds(20));\n"
            "    if(clock && !reset) { ++io_pipelineIssues; ++io_executedMacs; }\n"
            "  }\n};\n"
        )
        (cls.generated / "verilated.h").write_text("struct Verilated { static void commandArgs(int, char**) {} };\n")
        cls.binary = cls.root / "synthetic-profile"
        compile_cpp(cls.generated / "profile_driver.cpp", cls.binary, cls.generated)
        cls.fixture = cls.root / "fixture"
        cls.make_fixture(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def make_fixture(fixture):
        fixture.mkdir()
        base = 0x100000000
        meta, scratch = base + 4096, base + 65536
        cache, limit = scratch + 65536, scratch + 512 * 1024
        lines = [f"HOST_ATTENTION_CORE_PAIR_V1 {base} {limit} {meta} {scratch} {cache} 256", "11"]
        for i in range(11):
            name = f"input{i}.bin"
            (fixture / name).write_bytes(bytes(64))
            lines.append(f"{name} {base + i * 64} 64")
        names = ["q", "k", "v", "norm_q", "gate", "norm_k", "rope_q", "rope_k", "cache_k", "cache_v", "context"]
        records = [21, 21, 21, 15, 12, 12, 12, 11, 13, 9, 13, 12]
        engines = [2, 2, 2, 3, 3, 3, 3, 4, 2, 3, 2, 3]
        for r in range(2):
            cb, db = meta + r * 4096, meta + r * 4096 + 256
            lines.append(f"{cb} {cb + 192} {db} {db + 2752} 128 {r} 1 {r} {r} {r} {9 + r}")
            for pc in range(12):
                lines.append(f"cmd{pc} {engines[pc]} {records[pc]} {pc + 1} {base} 64 {base + 64} 64")
            expected = fixture / "expected" / ("carried1" if r else "cold0")
            expected.mkdir(parents=True)
            for i, name in enumerate(names):
                address = scratch + r * 4096 + i * 64
                if i == 8:
                    address = cache + r * 1024
                if i == 9:
                    address = cache + 256 * 1024 + r * 1024
                lines.append(f"{name} {min(i, 10)} {address} 64 {address} 64")
                (expected / f"{name}.bf16le").write_bytes(bytes(64))
        (fixture / "launch.txt").write_text("\n".join(lines) + "\n")

    def test_complete_source_wrapper_prefix_and_timing_independent_digest(self):
        import os
        outputs = []
        for name, slow in [("fast", False), ("slow", True)]:
            out = self.root / name
            env = os.environ.copy()
            if slow:
                env["SYNTHETIC_SLOW"] = "1"
            result = run([str(self.binary), str(self.fixture), str(out)], env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("HOST_ATTN_PAIR", result.stdout)
            report = json.loads((out / "attention_profile.json").read_text())
            events = (out / "prefix_events.jsonl").read_bytes()
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["status"], "BOUNDED_DIAGNOSTIC_PREFIX")
            self.assertFalse(report["numerical_acceptance"])
            self.assertTrue(report["prefix_reached"])
            self.assertEqual(report["cycle_limit"], 96)
            self.assertEqual(report["cycles"], 96)
            self.assertEqual(report["eval_calls"], 288)
            self.assertEqual(report["eval_attempts"], 288)
            self.assertEqual(report["incomplete_steps"], 0)
            self.assertEqual(report["eval_phase_calls"], [96, 96, 96])
            self.assertEqual(report["eval_ns"], sum(report["eval_phase_ns"]))
            self.assertGreater(report["eval_ns"], 0)
            self.assertEqual(report["driver_excluding_eval_ns"], report["step_elapsed_ns"] - report["eval_ns"])
            self.assertGreater(report["driver_excluding_eval_ns"], 0)
            self.assertEqual(report["active_cycles"], 60)
            self.assertEqual(report["reset_cycles"], 6)
            self.assertEqual(report["event_bytes"], len(events))
            fnv = 14695981039346656037
            for b in events:
                fnv = ((fnv ^ b) * 1099511628211) & ((1 << 64) - 1)
            self.assertEqual(report["prefix_fnv1a64"], f"{fnv:016x}")
            rows = [json.loads(line) for line in events.splitlines()]
            self.assertEqual(len(rows), 97)
            self.assertEqual([row["cycle"] for row in rows[1:]], list(range(1, 97)))
            self.assertEqual(rows[-1], report["deterministic"]["terminal_event"])
            self.assertFalse(any(k.endswith("_ns") or "time" in k for row in rows[1:] for k in row))
            outputs.append((report, events))
        self.assertEqual(outputs[0][1], outputs[1][1])
        self.assertEqual(outputs[0][0]["deterministic"], outputs[1][0]["deterministic"])
        self.assertGreater(outputs[1][0]["eval_ns"], outputs[0][0]["eval_ns"])

    def test_physical_axi_seeded_read_write_ack_matches_original(self):
        baseline = self.root / "baseline"
        baseline.mkdir()
        shutil.copyfile(self.generated / "original/host_physical_axi.h", baseline / "host_physical_axi.h")
        snapshots = []
        for profiled in [False, True]:
            name = "physical-profile" if profiled else "physical-baseline"
            binary = self.root / name
            args = ["g++", "-O2", "-std=c++17", "-ffp-contract=off", "-fno-fast-math"]
            if profiled:
                args.append("-DPROFILE_SYNTHETIC_TEST=1")
            else:
                args.extend(["-I", str(baseline)])
            args.extend(["-I", str(self.generated), str(HERE / "synthetic_axi.cpp"), "-o", str(binary)])
            compiled = run(args)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            output = self.root / (name + "-output")
            executed = run([str(binary), str(output)])
            self.assertEqual(executed.returncode, 0, executed.stderr)
            snapshots.append(json.loads(executed.stdout))
            if profiled:
                report = json.loads((output / "attention_profile.json").read_text())
                self.assertEqual(report["ar_handshakes"], 1)
                self.assertEqual(report["aw_handshakes"], 1)
                self.assertEqual(report["w_handshakes"], 2)
                self.assertEqual(report["r_handshakes"], 2)
                self.assertEqual(report["b_handshakes"], 1)
                self.assertEqual(report["deterministic"]["terminal_event"]["end_write_acks"], 2)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0]["ticks"], 96)
        self.assertEqual(snapshots[0]["eval_calls"], 288)

    def test_original_failure_is_not_diagnostic_success(self):
        import os
        out = self.root / "failure"
        env = dict(os.environ, SYNTHETIC_FAIL="1")
        result = run([str(self.binary), str(self.fixture), str(out)], env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic eval failure", result.stderr)
        report = json.loads((out / "attention_profile.json").read_text())
        self.assertFalse(report["prefix_reached"])
        self.assertFalse(report["numerical_acceptance"])
        self.assertEqual(report["status"], "DRIVER_FAILED")
        self.assertEqual(report["incomplete_steps"], 1)
        self.assertEqual(report["eval_calls"], 125)
        self.assertLess(report["cycles"], 96)

    def test_killed_run_preserves_unaccepted_partial_checkpoint(self):
        import os
        import time
        out = self.root / "interrupted"
        process = subprocess.Popen([str(self.binary), str(self.fixture), str(out)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=dict(os.environ, SYNTHETIC_BLOCK="1"))
        try:
            deadline = time.monotonic() + 3
            while not (out / "attention_profile.json").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((out / "attention_profile.json").exists())
            process.terminate()
            process.communicate(timeout=3)
            self.assertNotEqual(process.returncode, 0)
            report = json.loads((out / "attention_profile.json").read_text())
            self.assertEqual(report["status"], "PREFIX_RUNNING")
            self.assertFalse(report["prefix_reached"])
            self.assertFalse(report["numerical_acceptance"])
            self.assertEqual(report["cycles"], 1)
            self.assertEqual(report["eval_calls"], 3)
            self.assertEqual(len((out / "prefix_events.jsonl").read_text().splitlines()), 2)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=3)

    def test_invalid_mode_or_existing_output_fails_closed(self):
        result = run([str(self.binary), str(self.fixture), str(self.root / "bad-mode"), "private-profile-opcode"])
        self.assertNotEqual(result.returncode, 0)
        existing = self.root / "existing"
        existing.mkdir()
        result = run([str(self.binary), str(self.fixture), str(existing)])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((existing / "attention_profile.json").exists())


if __name__ == "__main__":
    unittest.main()
