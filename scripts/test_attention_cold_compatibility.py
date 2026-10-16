"""Synthetic source-gate tests; no numerical execution."""
import tempfile
from pathlib import Path
import unittest
from scripts.check_attention_cold_compatibility import REPLACEMENTS, execution_inventory, package_inventory, read_source, sha, verify_files

class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.root=Path(t.name).resolve()
        self.old={n:p[0] for n,p in REPLACEMENTS.items()}; self.old['unchanged.py']=sha(b'unchanged')
    def test_exact_four_and_unchanged(self):
        result=execution_inventory(self.old,REPLACEMENTS)
        self.assertEqual(len(result),len(self.old)); self.assertEqual(result['unchanged.py'],self.old['unchanged.py'])
        self.assertEqual(sum(result[k]!=self.old[k] for k in result),4)
    def test_missing_replacement(self):
        r=dict(REPLACEMENTS);r.pop(next(iter(r)))
        with self.assertRaises(ValueError): execution_inventory(self.old,r)
    def test_extra_replacement(self):
        r=dict(REPLACEMENTS);r['other.py']=('a'*64,'b'*64)
        with self.assertRaises(ValueError): execution_inventory(self.old,r)
    def test_wrong_current_identity(self):
        r=dict(REPLACEMENTS);key=next(iter(r));r[key]=(r[key][0],'f'*64)
        with self.assertRaises(ValueError): execution_inventory(self.old,r)
    def test_wrong_historical_identity(self):
        self.old[next(iter(REPLACEMENTS))]='0'*64
        with self.assertRaises(ValueError): execution_inventory(self.old,REPLACEMENTS)
    def test_invalid_noop_hashes(self):
        key=next(iter(REPLACEMENTS));old=REPLACEMENTS[key][0]
        for new in (old,'x'*64,'',None):
            r=dict(REPLACEMENTS);r[key]=(old,new)
            with self.subTest(new=new),self.assertRaises(ValueError): execution_inventory(self.old,r)
    def test_dependency_drift(self):
        (self.root/'a.py').write_bytes(b'changed')
        with self.assertRaises(ValueError): verify_files(self.root,{'a.py':sha(b'old')})
    def test_missing_dependency(self):
        with self.assertRaises(ValueError): verify_files(self.root,{'missing':sha(b'')})
    def test_symlink_and_ancestor(self):
        (self.root/'real').mkdir();(self.root/'real'/'a').write_bytes(b'a')
        (self.root/'link').symlink_to(self.root/'real',target_is_directory=True)
        (self.root/'alias').symlink_to(self.root/'real'/'a')
        for name in ('link/a','alias'):
            with self.subTest(name=name),self.assertRaises(ValueError): read_source(self.root,name)
    def test_unsafe_paths(self):
        for name in ('../outside','/etc/passwd','a/../b','./file'):
            with self.subTest(name=name),self.assertRaises(ValueError): read_source(self.root,name)
    def test_package_add_delete_change(self):
        p=self.root/'candidates'/'fixture';p.mkdir(parents=True);(p/'runner.py').write_bytes(b'old')
        before=package_inventory(self.root,('fixture',));(p/'extra.py').write_bytes(b'new')
        self.assertNotEqual(package_inventory(self.root,('fixture',)),before)
        (p/'extra.py').unlink();(p/'runner.py').write_bytes(b'changed')
        self.assertNotEqual(package_inventory(self.root,('fixture',)),before)
        (p/'runner.py').unlink();self.assertNotEqual(package_inventory(self.root,('fixture',)),before)
    def test_package_symlink(self):
        p=self.root/'candidates'/'fixture';p.mkdir(parents=True);(p/'alias').symlink_to(self.root)
        with self.assertRaises(ValueError):package_inventory(self.root,('fixture',))
    def test_exact_file(self):
        (self.root/'ok.py').write_bytes(b'ok');verify_files(self.root,{'ok.py':sha(b'ok')})

if __name__=='__main__': unittest.main()
