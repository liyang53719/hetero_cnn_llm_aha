"""Rebuild exact reviewed declaration expectation from small metadata.
Imports only the pinned published pure type flattener; no real SV/FIR or native I/O.
"""
import argparse,hashlib,importlib.util,json
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent
DERIVE='candidates/qwen2_core_client_sv_structure/derive_ports.py'
def checked(root,relative,pin):
 r=PurePosixPath(relative)
 if r.is_absolute() or '..' in r.parts or '\\' in relative:raise ValueError('unsafe reference')
 p=root.joinpath(*r.parts)
 if p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise ValueError('regular nonsymlink reference required')
 b=p.read_bytes()
 if len(b)!=pin['bytes'] or hashlib.sha256(b).hexdigest()!=pin['sha256']:raise ValueError('reference hash mismatch')
 return b

def rebuild(repository_root,package=HERE):
 root=Path(repository_root).absolute();package=Path(package).absolute()
 if root.resolve()!=root or package.resolve()!=package:raise ValueError('symlink root')
 refs=json.loads((package/'pins/EXISTING_PUBLIC_REFERENCES.json').read_text())['references']
 data={r['repo_path']:checked(root,r['repo_path'],r) for r in refs}
 pins=json.loads((package/'pins/SOURCE_PINS.json').read_text())
 types=json.loads(checked(package,'pins/TYPE_INPUTS.json',pins['type_input_published']))
 e=json.loads(checked(package,'structure/EXPECTATION_TEMPLATE.json',pins['template']))
 namespace={'__name__':'pinned_type_flattener'}
 exec(compile(data[DERIVE],DERIVE,'exec'),namespace)
 def ports(x):return namespace['derive']({'top_ports':{n:{'direction':v[0],'type':v[1]} for n,v in x.items()}})
 e['selected_module_ports']={n:ports(x['ports']) for n,x in types['components'].items()}
 e['top_ports']=e['selected_module_ports'][e['top']]
 e['external_ports']={n:ports(x) for n,x in types['external_canonical_ABI'].items()}
 b=(json.dumps(e,indent=2,sort_keys=True)+'\n').encode()
 if len(b)!=pins['original_expectation']['bytes'] or hashlib.sha256(b).hexdigest()!=pins['original_expectation']['sha256']:raise ValueError('expectation not exact')
 return b

def write(repository_root,output,package=HERE):
 p=Path(output).absolute()
 if p.exists() or p.is_symlink() or p.resolve()!=p or not p.parent.is_dir():raise ValueError('fresh nonsymlink output required')
 b=rebuild(repository_root,package)
 with p.open('xb') as f:f.write(b)
 return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'target_artifacts_read_or_executed':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repository-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();print(json.dumps(write(v.repository_root,v.output),sort_keys=True))
