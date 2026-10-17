import hashlib,json,importlib.util
from pathlib import Path
from reproduce_provider import compose
P=Path(__file__).resolve().parent
for n,h in json.loads((P/'PACKAGE_HASHES.json').read_text()).items():
 f=P/n
 if not f.is_file() or f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest()!=h:raise ValueError('package drift '+n)
for name in ['begin_fix','reserved_fix']:
 spec=importlib.util.spec_from_file_location(name,P/name/'model.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);print(name,m.audit())
compose();print('PASS_PORTABLE_SOURCE_AND_MODEL_ONLY')
