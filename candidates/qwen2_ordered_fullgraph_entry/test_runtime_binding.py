#!/usr/bin/env python3
"""Pure stdlib source-loader fixtures. Never import the real DUT or NumPy."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime_binding as rb
if Path(rb.__file__).resolve() != HERE / 'runtime_binding.py':
    raise RuntimeError('foreign runtime_binding import')


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'; self.root.mkdir()
        self.path = self.root / 'cold_fixture_example.py'
        self.path.write_text('VALUE = 7\ndef tick(x):\n    return x + VALUE\n')
        self.files = {'cold_fixture_example.py': self.pin(self.path)}
        self.manifest = self.base / 'manifest.json'
        self.save()

    def tearDown(self):
        sys.modules.pop('cold_fixture_example', None)
        sys.path[:] = [p for p in sys.path if p != str(self.root)]
        self.temp.cleanup()

    def pin(self, path):
        raw = path.read_bytes()
        return {'bytes': len(raw), 'sha256': rb.digest(raw)}

    def save(self):
        self.manifest.write_text(json.dumps(dict(schema='qwen2-ordered-fullgraph-source-manifest-v1',
                                               source_file_count=len(self.files), source_files=self.files)))
        self.sha = rb.digest(self.manifest.read_bytes())

    def verify(self):
        return rb.verify_sources(self.root, self.manifest, self.sha)

    def test_valid_manifest(self):
        self.assertEqual(self.verify(), (self.root, self.files))

    def test_changed_manifest(self):
        self.manifest.write_bytes(self.manifest.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'manifest hash'): self.verify()

    def test_changed_source(self):
        self.path.write_text('VALUE = 8\n')
        with self.assertRaisesRegex(ValueError, 'source drift'): self.verify()

    def test_extra_source(self):
        (self.root/'extra.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'unmanifested'): self.verify()

    def test_missing_source(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError): self.verify()

    def test_traversal(self):
        self.files['../escape.py'] = self.files.pop('cold_fixture_example.py'); self.save()
        with self.assertRaisesRegex(ValueError, 'escape'): self.verify()

    def test_symlink(self):
        link = self.root/'link.py'; link.symlink_to(self.path)
        self.files['link.py'] = self.pin(self.path); self.save()
        with self.assertRaisesRegex(ValueError, 'escape'): self.verify()

    def test_count(self):
        obj=json.loads(self.manifest.read_text());obj['source_file_count']=3
        self.manifest.write_text(json.dumps(obj));self.sha=rb.digest(self.manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, 'count'): self.verify()

    def test_alias_inventory(self):
        mod=ModuleType('legacy_alias');mod.__file__=str(self.path)
        out=rb.project_inventory(self.root,self.files,{'legacy_alias':mod})
        self.assertEqual(out['legacy_alias']['relative'],self.path.name)

    def test_foreign_project_path(self):
        mod=ModuleType('candidates.x');mod.__file__=str(self.base/'foreign.py')
        with self.assertRaisesRegex(ValueError,'foreign project'):
            rb.project_inventory(self.root,self.files,{'candidates.x':mod})

    def test_foreign_namespace(self):
        mod=ModuleType('candidates');mod.__path__=[str(self.base)]
        with self.assertRaisesRegex(ValueError,'foreign project namespace'):
            rb.project_inventory(self.root,self.files,{'candidates':mod})

    def test_local_namespace(self):
        mod=ModuleType('candidates');mod.__path__=[str(self.root)]
        self.assertEqual(rb.project_inventory(self.root,self.files,{'candidates':mod}),{})

    def test_unmanifested_alias(self):
        mod=ModuleType('alias');mod.__file__=str(self.root/'unknown.py')
        with self.assertRaisesRegex(ValueError,'unmanifested'):
            rb.project_inventory(self.root,self.files,{'alias':mod})

    def test_exec_exact(self):
        gate=rb.ProjectCodeGate(self.root,self.files);gate.active=True
        code=compile(self.path.read_bytes(),str(self.path),'exec',dont_inherit=True,optimize=sys.flags.optimize)
        gate.hook('exec',(code,))
        self.assertEqual(len(gate.events),1)

    def test_exec_replaced_code(self):
        gate=rb.ProjectCodeGate(self.root,self.files);gate.active=True
        with self.assertRaisesRegex(ValueError,'code differs'):
            gate.hook('exec',(compile('VALUE = 99',str(self.path),'exec'),))

    def test_exec_wrong_filename(self):
        gate=rb.ProjectCodeGate(self.root,self.files);gate.active=True
        with self.assertRaisesRegex(ValueError,'foreign project execution'):
            gate.hook('exec',(compile('pass',str(self.root/'unknown.py'),'exec'),))

    def test_inactive_hook(self):
        gate=rb.ProjectCodeGate(self.root,self.files)
        gate.hook('exec',(compile('pass',str(self.path),'exec'),))
        self.assertEqual(gate.events,[])

    def test_normal_fixture_load(self):
        with patch.object(rb,'MODULES',{'fixture':'cold_fixture_example'}):
            runtime, receipt=rb.load_runtime(self.root,self.manifest,self.sha)
        self.assertEqual(runtime.fixture.VALUE,7)
        self.assertEqual(len(receipt['module_exec_events']),1)
        self.assertFalse(receipt['services_constructed'])
        self.assertEqual(receipt['external_runtime_maps_status'],'REQUIRES_SEPARATE_PINNED_GATE')

    def test_preloaded_source_rejected(self):
        mod=ModuleType('cold_fixture_example');mod.__file__=str(self.path)
        sys.modules['cold_fixture_example']=mod
        with patch.object(rb,'MODULES',{'fixture':'cold_fixture_example'}):
            with self.assertRaisesRegex(ValueError,'cold project namespace'):
                rb.load_runtime(self.root,self.manifest,self.sha)

    def test_target_role_set(self):
        self.assertEqual(set(rb.MODULES),{'base','original','fixtures','public','prefix','scalar','suffix',
                         'physical_adapter','owner_module','binding','profiles','execution','policy','dense','matrix'})
        self.assertNotIn('library',rb.MODULES)

if __name__ == '__main__': unittest.main()
