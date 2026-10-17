"""Synthetic metadata tests only; no downloads, installation or native imports."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fresh_packages',HERE/'package_validation.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


def report(lock,role):
    env=dict(implementation_name='cpython',implementation_version='3.12.15',os_name='posix',platform_machine='x86_64',
        platform_system='Linux',python_full_version='3.12.15',platform_python_implementation='CPython',python_version='3.12',sys_platform='linux')
    items=[dict(download_info=dict(url=p['url'],archive_info=dict(hashes=dict(sha256=p['sha256']))),
        is_direct=True,is_yanked=False,requested=True,metadata=dict(name=p['name'],version=p['version']))
        for p in P.selected(lock,role).values()]
    return dict(version='1',pip_version='25.0.1',install=items,environment=env)


class Packages(unittest.TestCase):
    def setUp(self): self.lock=json.loads((HERE/'wheel-lock.json').read_bytes())

    def test_complete_official_lock(self):
        self.assertEqual(P.validate_lock(self.lock),self.lock)
        for role in ('bootstrap','runtime'):
            self.assertTrue(P.validate_requirements((HERE/('requirements-'+role+'.lock')).read_bytes(),self.lock,role))

    def test_lock_rejects_alternate_publisher(self):
        self.lock['packages'][0]['url']=self.lock['packages'][0]['url'].replace('files.pythonhosted.org','example.com')
        with self.assertRaises(ValueError): P.validate_lock(self.lock)

    def test_lock_rejects_duplicate(self):
        self.lock['packages'][1]=self.lock['packages'][0]
        with self.assertRaises(ValueError): P.validate_lock(self.lock)

    def test_lock_rejects_size_drift(self):
        self.lock['packages'][0]['size_bytes']+=1
        with self.assertRaises(ValueError): P.validate_lock(self.lock)

    def test_no_requirement_options_or_unhashed_fallback(self):
        raw=(HERE/'requirements-runtime.lock').read_bytes()
        for changed in (raw+b'--index-url https://example.com\n',raw.replace(b' --hash=sha256:',b' # '),raw+b'numpy==2.3.5\n'):
            with self.subTest(changed=changed[-30:]),self.assertRaises(ValueError): P.validate_requirements(changed,self.lock,'runtime')

    def test_bootstrap_and_runtime_report(self):
        for role in ('bootstrap','runtime'): self.assertTrue(P.validate_report(report(self.lock,role),self.lock,role))

    def test_report_legacy_hash_and_empty_extras(self):
        value=report(self.lock,'bootstrap');item=value['install'][0]
        item['download_info']['archive_info']['hash']='sha256='+item['download_info']['archive_info']['hashes']['sha256']
        item['requested_extras']=[]
        self.assertTrue(P.validate_report(value,self.lock,'bootstrap'))

    def test_report_mutations(self):
        good=report(self.lock,'runtime')
        def alter(path,val):
            changed=copy.deepcopy(good);at=changed
            for key in path[:-1]: at=at[key]
            at[path[-1]]=val
            return changed
        mutations=[(('version',),'2'),(('pip_version',),'25.0.2'),(('environment','python_full_version'),'3.12.14'),
            (('install',0,'is_direct'),False),(('install',0,'is_yanked'),True),(('install',0,'requested'),1),
            (('install',0,'metadata','version'),'0'),(('install',0,'download_info','url'),'https://example.com/a.whl'),
            (('install',0,'download_info','archive_info','hashes','sha256'),'0'*64)]
        for path,value in mutations:
            with self.subTest(path=path),self.assertRaises(ValueError): P.validate_report(alter(path,value),self.lock,'runtime')
        for changed in (dict(good,install=good['install'][:-1]),dict(good,install=good['install']+[good['install'][0]])):
            with self.assertRaises(ValueError): P.validate_report(changed,self.lock,'runtime')

    def test_report_duplicate_same_count(self):
        value=report(self.lock,'runtime');value['install'][1]=copy.deepcopy(value['install'][0])
        with self.assertRaises(ValueError): P.validate_report(value,self.lock,'runtime')

    def test_installed_inventory(self):
        value=dict(schema=1,python='3.12.15',private_venv=True,packages=[dict(name=p['name'],version=p['version'],inside_venv=True) for p in self.lock['packages']])
        self.assertTrue(P.validate_inventory(value,self.lock))
        for changed in (dict(value,private_venv=False),dict(value,packages=value['packages'][:-1]),dict(value,schema=True)):
            with self.assertRaises(ValueError): P.validate_inventory(changed,self.lock)
        value['packages'][0]['inside_venv']=False
        with self.assertRaises(ValueError): P.validate_inventory(value,self.lock)


if __name__=='__main__': unittest.main()
