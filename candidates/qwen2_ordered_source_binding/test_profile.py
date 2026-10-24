"""Config rejection checks only; does not import NumPy or application modules."""
import argparse,copy,importlib.util,json,os,resource,signal,sys,unittest
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
resource.setrlimit(resource.RLIMIT_CPU,(20,20));signal.alarm(25)
from pathlib import Path
HERE=Path(__file__).resolve(strict=True).parent
p=argparse.ArgumentParser();p.add_argument('--config',required=True,type=Path);a,rest=p.parse_known_args();CONFIG=json.loads(a.config.read_text())
spec=importlib.util.spec_from_file_location('_tested_profile_gate',HERE/'profile_gate.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
if Path(gate.__file__).resolve()!=HERE/'profile_gate.py':raise ValueError('gate origin drift')
class Tests(unittest.TestCase):
    def reject(self,mutate):
        c=copy.deepcopy(CONFIG);mutate(c)
        with self.assertRaises(ValueError):gate.validate(c,HERE)
    def test_exact(self):gate.validate(CONFIG,HERE)
    def test_extra_read_path(self):self.reject(lambda c:c['extra_files'].update({'/tmp/unknown':{'bytes':0,'sha256':'0'*64}}))
    def test_observer_pin(self):self.reject(lambda c:c['extra_files'][str(Path(c['observer_root'])/'monitor.py')].update(sha256='0'*64))
    def test_buffer_pin(self):self.reject(lambda c:c['extra_files'][c['buffer_source']].update(bytes=0))
    def test_missing_extra(self):self.reject(lambda c:c['extra_files'].pop(c['buffer_source']))
    def test_runtime_same_hash_wrong_path(self):
        def change(c):k=next(iter(c['runtime_files']));c['runtime_files']['/tmp/wrong']=c['runtime_files'].pop(k)
        self.reject(change)
    def test_missing_runtime(self):self.reject(lambda c:c['runtime_files'].pop(next(iter(c['runtime_files']))))
    def test_manifest_byte_change(self):self.reject(lambda c:c.update(manifest_sha256='0'*64))
    def test_source_pin(self):self.reject(lambda c:c['source_files'].pop(next(iter(c['source_files']))))
    def test_extra_config_key(self):self.reject(lambda c:c.update(ignore_guard=True))
if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
