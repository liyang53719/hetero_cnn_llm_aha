"""Synthetic package bytes only; no PyYAML, native import or DUT execution."""
import base64,csv,hashlib,json
from pathlib import Path
import sys,tempfile,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import dependency as dep
if Path(dep.__file__).resolve()!=HERE/'dependency.py':raise RuntimeError('foreign helper')
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.source=self.base/'site';self.source.mkdir();(self.source/'yaml').mkdir();meta=self.source/'pyyaml-6.0.3.dist-info';meta.mkdir()
        files={}
        for name in ['__init__.py',*[f'm{i}.py' for i in range(16)],'_yaml.cpython-312-x86_64-linux-gnu.so']:
            p=self.source/'yaml'/name;p.write_bytes(b'fixture not executable');files['yaml/'+name]={'bytes':p.stat().st_size,'sha256':dep.digest(p)}
        with (meta/'RECORD').open('w') as f:
            w=csv.writer(f)
            for name,pin in files.items():w.writerow([name,'sha256='+base64.urlsafe_b64encode(bytes.fromhex(pin['sha256'])).decode().rstrip('='),str(pin['bytes'])])
        for name in ('WHEEL','METADATA'):(meta/name).write_text('fixture metadata')
        mpins={str(p.relative_to(self.source)):{'bytes':p.stat().st_size,'sha256':dep.digest(p)} for p in meta.iterdir()}
        self.spec=dict(schema=1,package='PyYAML',version='6.0.3',files=files,metadata_pins=mpins,normal_cyaml_required=True,unrestricted_site_packages_allowed=False)
        self.manifest=self.base/'pins.json';self.manifest.write_text(json.dumps(self.spec));self.sha=dep.digest(self.manifest);self.dest=self.base/'dedicated'
    def tearDown(self):self.temp.cleanup()
    def copy(self):return dep.copy_existing(self.source,self.dest,self.spec)
    def test_manifest(self):self.assertEqual(dep.manifest(self.manifest,self.sha),self.spec)
    def test_manifest_byte_change(self):
        self.manifest.write_text(self.manifest.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'manifest hash'):dep.manifest(self.manifest,self.sha)
    def test_exact_copy(self):self.assertEqual(len(self.copy()),18);self.assertNotIn('yaml',sys.modules)
    def test_no_metadata_copied(self):self.copy();self.assertEqual(list(p.name for p in self.dest.iterdir()),['yaml'])
    def test_existing_destination(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(ValueError,'fresh'):self.copy()
    def test_original_changed(self):
        (self.source/'yaml/__init__.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'bytes differ'):self.copy()
    def test_missing_cyaml(self):
        (self.source/'yaml/_yaml.cpython-312-x86_64-linux-gnu.so').unlink()
        with self.assertRaisesRegex(ValueError,'extent'):self.copy()
    def test_extra_installed_module(self):
        (self.source/'yaml/foreign.py').write_text('')
        with self.assertRaisesRegex(ValueError,'extent'):self.copy()
    def test_cached_pyc_never_copied(self):
        (self.source/'yaml/__pycache__').mkdir();(self.source/'yaml/__pycache__/x.pyc').write_bytes(b'cached');self.copy()
        self.assertFalse((self.dest/'yaml/__pycache__').exists())
    def test_changed_record(self):
        (self.source/'pyyaml-6.0.3.dist-info/RECORD').write_text('bad')
        with self.assertRaisesRegex(ValueError,'bytes differ'):self.copy()
    def test_copy_modified(self):
        self.copy();(self.dest/'yaml/__init__.py').write_text('bad')
        with self.assertRaisesRegex(ValueError,'bytes differ'):dep.verify_copy(self.dest,self.spec)
    def test_copy_extra_package(self):
        self.copy();(self.dest/'foreign.py').write_text('')
        with self.assertRaisesRegex(ValueError,'extra'):dep.verify_copy(self.dest,self.spec)
    def test_copy_symlink(self):
        self.copy();(self.dest/'elsewhere').symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,'symlink'):dep.verify_copy(self.dest,self.spec)
    def test_forbidden_package_permission(self):
        self.spec['unrestricted_site_packages_allowed']=True;self.manifest.write_text(json.dumps(self.spec))
        with self.assertRaisesRegex(ValueError,'broad'):dep.manifest(self.manifest,dep.digest(self.manifest))
    def test_pure_python_fallback_manifest_rejected(self):
        self.spec['normal_cyaml_required']=False;self.manifest.write_text(json.dumps(self.spec))
        with self.assertRaisesRegex(ValueError,'cyaml'):dep.manifest(self.manifest,dep.digest(self.manifest))
if __name__=='__main__':unittest.main()
