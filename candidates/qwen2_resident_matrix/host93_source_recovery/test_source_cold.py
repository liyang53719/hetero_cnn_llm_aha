# SPDX-License-Identifier: Apache-2.0
"""Project-text and synthetic cold tests; never reconstruct production sources."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--repo', required=True, type=Path)
parameters, unittest_args = parser.parse_known_args()
REPO = parameters.repo.absolute()
SOURCE_SHA256 = '75a2145eea0de83ad1bbe3a7a64e1a5f14f20f9f1381f65e619fb5bd3d427641'
SOURCE_BYTES = 15592


def module(name, path):
    # Published source-recovery pattern: validate and execute the SAME buffer.
    raw = path.read_bytes()
    if len(raw) != SOURCE_BYTES or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('project source bytes differ before execution')
    result = types.ModuleType(name)
    result.__file__ = str(path.resolve())
    exec(compile(raw, str(path), 'exec', dont_inherit=True), result.__dict__)
    return result


candidate = module('host93_source_candidate', HERE/'assemble_host93.py')

PATCH = b'--- a/a.scala\n+++ b/a.scala\n@@ -1,2 +1,3 @@\n alpha\n+tap\n omega\n'


class SourceCold(unittest.TestCase):
    def test_01_exact_93_plan_static_preflight_does_not_load_rebase(self):
        with patch.object(candidate, 'source_module', side_effect=AssertionError('external recipe')):
            plan, frozen, identity = candidate.preflight(REPO)
        self.assertEqual(len(plan['expected93']), 93)
        self.assertEqual(len(plan['rebase']['expected92']), 92)
        self.assertEqual(sum(x.startswith(candidate.HF_PREFIX) for x in plan['expected93']), 20)
        self.assertEqual(len(identity), 64)
        self.assertFalse(plan['old_95_identity_inherited'])
        self.assertEqual(plan['bench_sources'], [])

    def test_02_synthetic_forward_reverse(self):
        original = {'a.scala':b'alpha\nomega\n'}
        new = candidate.patch_sources(original, PATCH, insertion_only=True)
        self.assertEqual(new, {'a.scala':b'alpha\ntap\nomega\n'})
        self.assertEqual(candidate.patch_sources(new, PATCH, reverse=True, insertion_only=True), original)

    def test_03_exact_context_no_fuzz_or_offset(self):
        for data in (b'prefix\nalpha\nomega\n', b'Alpha\nomega\n', b'alpha\nOMEGA\n'):
            with self.assertRaises(ValueError): candidate.patch_sources({'a.scala':data}, PATCH)

    def test_04_incomplete_and_wrong_hunk_counts_rejected(self):
        for malformed in (PATCH[:-1], PATCH.replace(b'+1,3',b'+1,4'), PATCH.replace(b'@@ -1,2',b'@@ -2,2')):
            with self.assertRaises(ValueError): candidate.patch_sources({'a.scala':b'alpha\nomega\n'}, malformed)

    def test_05_create_only_if_absent(self):
        create = b'--- /dev/null\n+++ b/new.scala\n@@ -0,0 +1,1 @@\n+source\n'
        self.assertEqual(candidate.patch_sources({},create), {'new.scala':b'source\n'})
        with self.assertRaises(ValueError): candidate.patch_sources({'new.scala':b''},create)
        with self.assertRaises(ValueError): candidate.patch_sources({},create,reverse=True)

    def test_06_unsafe_paths_and_renames_rejected(self):
        for name in ('../x','/tmp/x','a/../b','a//b','a/./b','a\\b',''):
            with self.assertRaises(ValueError): candidate.relative(name)
        with self.assertRaises(ValueError): candidate.patch_entries(PATCH.replace(b'+++ b/a.scala',b'+++ b/b.scala'))
        with self.assertRaises(ValueError): candidate.patch_entries(PATCH.replace(b'a.scala',b'../x'))

    def test_07_tap_replacement_not_insertion(self):
        replacement = b'--- a/a.scala\n+++ b/a.scala\n@@ -1 +1 @@\n-alpha\n+alter\n'
        with self.assertRaises(ValueError): candidate.patch_sources({'a.scala':b'alpha\n'},replacement,insertion_only=True)

    def test_08_duplicate_json_key_and_patch_target_rejected(self):
        with self.assertRaises(ValueError): candidate.decode_json(b'{"same":1,"same":2}')
        with self.assertRaises(ValueError): candidate.patch_entries(PATCH+PATCH)

    def test_09_input_hash_and_inventory_fail_closed(self):
        pins = {'a.scala':hashlib.sha256(b'good').hexdigest()}
        candidate.verify_map({'a.scala':b'good'},pins,'fixture')
        for inputs in ({'a.scala':b'bad'},{},{'a.scala':b'good','extra.scala':b'other'}):
            with self.assertRaises(ValueError): candidate.verify_map(inputs,pins,'fixture')

    def test_10_read_rejects_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'regular').write_bytes(b'abc'); (root/'link').symlink_to(root/'regular')
            with self.assertRaises(ValueError): candidate.read_regular(root,'link')
            with self.assertRaises(ValueError): candidate.read_regular(root,'regular',cap=2)

    def test_11_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out';out.mkdir();(out/'keep').write_bytes(b'existing')
            with self.assertRaises(FileExistsError): candidate.write_tree(out,{'a.scala':b'new'})
            self.assertEqual((out/'keep').read_bytes(),b'existing')

    def test_12_emitter_keeps_exact_original_host_configuration(self):
        plan=json.loads((HERE/'SOURCE_REPLAY_PLAN.json').read_text())
        emitted=(HERE/'source/EmitCanonicalHost93.scala').read_text()
        original=(REPO/plan['emitter']['host_config_source']).read_text()
        compact=lambda s: ''.join(s.split())
        actual, baseline = compact(emitted), compact(original)
        tokens=('hidden=1536','ffn=8960','heads=12','kvHeads=2','headDim=128',
                'maxTokens=1024','retainedMatrix=true','matrixColumns=256','weightReadBeats=16',
                'pipelined=true','burstWrites=true','commitTailRead=false','overlapSilu=false',
                'enableTransposedDown=true','enableResidentFfn=true','enablePublic21QkvReduction=true',
                'numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2','enableProductionPackedQk16=true')
        for token in tokens:
            self.assertIn(token,actual);self.assertIn(token,baseline)
        self.assertEqual(actual.count('ChiselStage.emitCHIRRTL('),1)
        self.assertIn('newHostBlockCollection(shape,',actual)
        self.assertNotIn('emitSystemVerilog(',emitted)
        self.assertNotIn('new ProductionQk16KernelBench',emitted)
        for provider in ('HeteroBF16FmaPre','HeteroBF16FmaMul','HeteroBF16FmaPost','HeteroBF16FmaRound'):
            self.assertIn('new '+provider,(REPO/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockTop.scala').read_text())

    def test_13_87_locked_profile_excludes_test_only_extension(self):
        lock=json.loads((REPO/'candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile/dependency_pins.json').read_text())
        jars=lock['jars'];self.assertEqual(len(jars),87)
        for name in jars:
            self.assertFalse(any(part in name for part in ('chiseltest','scalatest','scalactic','firrtl2')))
        for artifact in ('scala-library','scala-reflect','scala-compiler'):
            self.assertIn(f'org/scala-lang/{artifact}/2.13.16/{artifact}-2.13.16.jar',jars)
        self.assertIn('org/chipsalliance/chisel_2.13/6.7.0/chisel_2.13-6.7.0.jar',jars)
        self.assertIn('org/chipsalliance/chisel-plugin_2.13.16/6.7.0/chisel-plugin_2.13.16-6.7.0.jar',jars)

    def test_14_source_candidate_has_no_native_or_network_calls(self):
        tree=ast.parse((HERE/'assemble_host93.py').read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                self.assertFalse(any(n.name.split('.')[0] in ('subprocess','socket','urllib','requests') for n in node.names))
            if isinstance(node,ast.ImportFrom):
                self.assertNotIn((node.module or '').split('.')[0],('subprocess','socket','urllib','requests'))
        self.assertIn('module.compose', (HERE/'assemble_host93.py').read_text())
        # This is a lexical boundary check, not proof of sandboxing the pinned helper.

    def test_15_changed_plan_is_rejected_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            changed=Path(d)/'changed.json'
            changed.write_bytes((HERE/'SOURCE_REPLAY_PLAN.json').read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError,'fixed source replay plan drift'):
                candidate.preflight(REPO, changed)

    def test_16_valid_polluted_pyc_is_a_positive_control_only(self):
        import importlib.machinery
        import importlib.util
        import marshal
        import struct
        # The real rebase helper is NOT loaded: its loader is exercised using a
        # synthetic source only. The other case loads the source-only assembler.
        cases = [('assembler', (HERE/'assemble_host93.py').read_bytes()),
                 ('synthetic_helper', b'VALUE = 17\n')]
        for kind, raw in cases:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                path=Path(temporary)/'candidate.py';path.write_bytes(raw);stats=path.stat()
                cache=Path(importlib.util.cache_from_source(str(path)));cache.parent.mkdir()
                code=compile(raw+b'\nPYC_INJECTED_MARKER = True\n',str(path),'exec')
                header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,int(stats.st_mtime)&0xffffffff,len(raw))
                cache.write_bytes(header+marshal.dumps(code))
                name='temporary_legacy_cache_control'
                loader=importlib.machinery.SourceFileLoader(name,str(path))
                spec=importlib.util.spec_from_loader(name,loader)
                legacy=importlib.util.module_from_spec(spec);loader.exec_module(legacy)
                self.assertTrue(legacy.PYC_INJECTED_MARKER)
                if kind == 'assembler':
                    checked=module('temporary_verified_assembler',path)
                else:
                    checked=candidate.source_module('temporary_verified_helper',path,path.read_bytes(),
                                                    hashlib.sha256(raw).hexdigest())
                self.assertFalse(hasattr(checked,'PYC_INJECTED_MARKER'))
                self.assertEqual(path.read_bytes(),raw)

    def test_17_changed_execution_bytes_rejected_before_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'candidate.py'
            path.write_bytes((HERE/'assemble_host93.py').read_bytes()+b'\nSOURCE_INJECTED_MARKER = True\n')
            with self.assertRaisesRegex(ValueError,'before execution'):
                module('changed_assembler',path)
            original=b'VALUE = 17\n'
            with self.assertRaisesRegex(ValueError,'before execution'):
                candidate.source_module('changed_helper',path,original+b'\nSOURCE_INJECTED_MARKER = True\n',
                                        hashlib.sha256(original).hexdigest())


if __name__ == '__main__':
    candidate.require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,
                      'run python -I -S -B; optional -O')
    unittest.main(argv=[sys.argv[0]]+unittest_args, verbosity=2)
