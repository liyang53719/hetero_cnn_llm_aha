"""Stdlib-only preexecution safety tests; no dependency install or model execution."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qwen35_installer", ROOT / "scripts/install_qwen35_official_runtime.py")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerPreflightTests(unittest.TestCase):
    def archive(self, tmp, entries):
        path = Path(tmp) / "fixture.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, content, mode in entries:
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                archive.writestr(info, content)
        return path

    def test_regular_zip_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.archive(tmp, [("package/file.py", b"pass\n", stat.S_IFREG | 0o644)])
            self.assertEqual(INSTALLER.zip_inventory(path)["members"], 1)

    def test_zip_traversal_rejected(self):
        for name in ("../escape.py", "/absolute.py", "package/../../escape", "package\\escape"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = self.archive(tmp, [(name, b"x", stat.S_IFREG | 0o644)])
                with self.assertRaises(ValueError):
                    INSTALLER.zip_inventory(path)

    def test_normalized_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.archive(tmp, [("a/b", b"x", 0), ("a//b", b"x", 0)])
            with self.assertRaises(ValueError):
                INSTALLER.zip_inventory(path)

    def test_wheel_symlink_and_devices_rejected(self):
        for mode in (stat.S_IFLNK, stat.S_IFCHR, stat.S_IFIFO):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                path = self.archive(tmp, [("a", b"target", mode | 0o644)])
                with self.assertRaises(ValueError):
                    INSTALLER.zip_inventory(path)

    def test_noncanonical_archive_link_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.archive(tmp, [(INSTALLER.ARCHIVE_PREFIX + "AGENTS.md", b"wrong-target", stat.S_IFLNK | 0o777)])
            with self.assertRaises(ValueError):
                INSTALLER.zip_inventory(path, official_archive=True)

    def test_reviewed_lock_required_before_runtime_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src/heteronpu").mkdir(parents=True)
            acquisition = root / "work/acquisition"
            acquisition.mkdir(parents=True)
            (acquisition / "official_runtime.lock.json").write_text("{}")
            runtime = root / "work/runtime"
            with self.assertRaisesRegex(ValueError, "Reviewed dependency lock SHA mismatch"):
                INSTALLER.install(root, acquisition, runtime, "0" * 64)
            self.assertFalse(runtime.exists())

    def test_wrapper_is_offline_and_bytecode_disabled(self):
        wrapper = INSTALLER.wrapper_text(Path(sys.executable), ROOT)
        for expected in ("HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "unset PYTHONHOME", "LD_PRELOAD", " -S -B ", "ATEN_CPU_CAPABILITY=default"):
            self.assertIn(expected, wrapper)

    def test_process_guard_denies_before_socket_fork_shell_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            guard = ROOT / "scripts/qwen35_runtime_network_guard.py"
            program = '''import os,runpy,sys,socket,subprocess,json
os.environ['QWEN35_PARENT_GUARD_PID']=str(os.getpid())
runpy.run_path(sys.argv[1])
checks={}
for name,action in [('socket',lambda:socket.socket()),('fork',lambda:os.fork()),('shell',lambda:os.system('true')),('child',lambda:subprocess.Popen([sys.executable,'-c','pass']))]:
 try:action()
 except PermissionError:checks[name]=True
 else:raise AssertionError(name+' unexpectedly allowed')
print(json.dumps(checks))
'''
            env = {"PATH": "/usr/bin:/bin", "QWEN35_RUNTIME_ROOT": str(runtime), "PYTHONPATH": ""}
            result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", program, str(guard)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), dict(socket=True, fork=True, shell=True, child=True))
            events = [json.loads(x) for x in (runtime / "network_guard.jsonl").read_text().splitlines()]
            self.assertEqual(sum(not x["allowed"] for x in events), 4)
            self.assertFalse(list(runtime.rglob("*.pyc")))

    def test_backend_rejects_wrong_helper_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            env = {"PATH": "/usr/bin:/bin", "QWEN35_RUNTIME_ROOT": str(runtime)}
            result = subprocess.run([sys.executable, "-I", "-S", "-B", str(ROOT / "scripts/qwen35_backend_runner.py"),
                                     str(runtime / "wrong.py"), "build_wheel", str(runtime / "tmp")], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unexpected PEP517 helper or hook", result.stderr)
            self.assertFalse(list(runtime.rglob("*.pyc")))


if __name__ == "__main__":
    unittest.main()
