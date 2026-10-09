"""Build receipt/profile boundaries; no compiler, model or simulator execution."""
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from host_bf16_gdn_execution import _build_identity, sha


class GdnBuildProfileTests(unittest.TestCase):
    def test_effective_driver_flags_override_inherited_make_optimization(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/run_host_bf16_gdn_gate.sh'
        source = script.read_text()
        assignment, = re.findall(r'^export MAKEFLAGS=.*$', source, re.M)
        cflags, = re.findall(r"-CFLAGS '([^']+)'", source)
        # The two different option orders are the retained Verilator rules:
        # explicit user-file rule in VHostBlockTop.mk and verilated.mk model rule.
        makefile = ('CPPFLAGS := ' + cflags + '\n.PHONY: flags\nflags:\n'
                    '\t@echo $(CXX) $(CPPFLAGS) $(OPT_FAST) -c host_bf16_gdn_core.cpp\n'
                    '\t@echo $(CXX) $(OPT_FAST) $(CPPFLAGS) -c VHostBlockTop.cpp\n'
                    '\t@echo $(OPT_SLOW)\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'flags.mk'; path.write_text(makefile)
            for inherited in ('', 'OPT_FAST=-O0', 'OPT_FAST=-Os OPT_SLOW=-O3'):
                with self.subTest(inherited=inherited):
                    env = dict(os.environ, MAKEFLAGS=inherited)
                    flags = subprocess.check_output(['bash', '-c', assignment + '\nprintf %s "$MAKEFLAGS"'],
                                                    env=env, text=True)
                    env['MAKEFLAGS'] = flags
                    lines = subprocess.check_output(['make', '--no-print-directory', '-j1', '-f', str(path), 'flags'],
                                                    env=env, text=True).splitlines()
                    self.assertEqual(len(lines), 3)
                    for line in lines[:2]:
                        words = shlex.split(line)
                        self.assertEqual([x for x in words if x.startswith('-O')][-1], '-O2')
                        self.assertIn('-fno-fast-math', words)
                        self.assertIn('-ffp-contract=off', words)
                        self.assertNotIn('-ffast-math', words)
                    self.assertEqual(lines[2], '-O0')

    def test_explicit_core_receipt_cannot_be_admitted_as_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('obj/VHostBlockTop', 'generated/HostBlockTop.sv',
                         'sources.sha256.json', 'hardfloat.sha256.json'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('synthetic unit identity ' + name)
            ready = dict(status='BUILT_HOST_GDN_CORE_ONLY_NOT_NUMERICAL_PASS', numerical_pass=False,
                         build_profile='core', experimental_default_off=True,
                         operations=['dense_qkv', 'dense_z', 'dense_ab', 'conv4_silu',
                                     'input_prep', 'recurrent_fp32', 'gated_norm', 'state_fence'],
                         full_block_supported=False, scalar_service_shared=True,
                         recurrent_state_supported=True, gated_norm_supported=True,
                         binary_sha256=sha(root / 'obj/VHostBlockTop'),
                         rtl_sha256=sha(root / 'generated/HostBlockTop.sv'),
                         source_manifest_sha256=sha(root / 'sources.sha256.json'))
            receipt = root / 'build_ready.json'
            receipt.write_text(json.dumps(ready))
            self.assertEqual(len(_build_identity(root, profile='core')), 5)
            with self.assertRaisesRegex(ValueError, 'build-only'):
                _build_identity(root)
            for key, value in [('numerical_pass', True), ('full_block_supported', True),
                               ('build_profile', 'dense-conv'), ('recurrent_state_supported', False),
                               ('gated_norm_supported', False), ('operations', ready['operations'][:-1])]:
                changed = dict(ready, **{key: value})
                receipt.write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    _build_identity(root, profile='core')
            receipt.write_text(json.dumps(ready))
            (root / 'obj/VHostBlockTop').write_text('changed ELF')
            with self.assertRaisesRegex(ValueError, 'identity drift'):
                _build_identity(root, profile='core')

    def test_unknown_profile_rejected_before_build_side_effects(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/run_host_bf16_gdn_gate.sh'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'must_not_exist'
            result = subprocess.run(['bash', str(script), str(out), '0', 'implicit-core'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('UNKNOWN_GDN_BUILD_PROFILE', result.stderr)
            self.assertFalse(out.exists())
