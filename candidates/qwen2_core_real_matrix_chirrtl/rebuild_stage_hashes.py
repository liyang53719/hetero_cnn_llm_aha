"""Reconstruct 557 class HASH records from already published metadata. No class I/O.
No JVM, compilation, elaboration, provider SV or dependency download is performed.
"""
import argparse,hashlib,json
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent
BASE='candidates/qwen2_core_client_chirrtl_evidence/pins/RETAINED_CLASS_PINS.json'
OLD='candidates/qwen2_core_client_chirrtl_evidence/evidence/NEW_CLASS_HASHES.json'
DELTA='candidates/qwen2_core_real_matrix_compile/pins/STAGED_CLASS_DELTA.json'
NEW='candidates/qwen2_core_real_matrix_compile/evidence/NEW_CLASS_SUMMARY.json'
def read(root,rel,pin):
 r=PurePosixPath(rel)
 if r.is_absolute() or '..' in r.parts or '\\' in rel:raise ValueError('unsafe reference')
 p=root.joinpath(*r.parts)
 if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise ValueError('regular nonsymlink reference required')
 b=p.read_bytes()
 if len(b)!=pin['bytes'] or hashlib.sha256(b).hexdigest()!=pin['sha256']:raise ValueError('reference bytes changed')
 return b

def rebuild(repo_root,output,package=HERE):
 repo_root=Path(repo_root).absolute();output=Path(output).absolute();package=Path(package).absolute()
 if repo_root.resolve()!=repo_root or package.resolve()!=package:raise ValueError('symlink input root')
 if output.exists() or output.is_symlink() or output.resolve()!=output or not output.parent.is_dir():raise ValueError('new nonsymlink output with existing parent required')
 refs=json.loads((package/'pins/EXISTING_PUBLIC_REFERENCES.json').read_text())['references'];data={x['repo_path']:read(repo_root,x['repo_path'],x) for x in refs}
 base=json.loads(data[BASE]);old={r['relative']:r for r in json.loads(data[OLD])['classes']};delta=json.loads(data[DELTA]);new=json.loads(data[NEW]);m={r['relative']:{k:r[k] for k in ('relative','bytes','sha256')} for r in base['classes']}
 if len(m)!=550 or len(delta['override14'])!=14:raise ValueError('base/override count')
 for r in delta['override14']:
  if any(r[k]!=old[r['relative']][k] for k in ('relative','bytes','sha256','source_file')):raise ValueError('override provenance')
  m[r['relative']]={k:r[k] for k in ('relative','bytes','sha256')}
 if len(m)!=554 or sum(r['bytes'] for r in m.values())!=9631197:raise ValueError('554 stage mismatch')
 if len(new['classes'])!=3:raise ValueError('new count')
 for r in new['classes']:
  if r['relative'] in m:raise ValueError('duplicate new class')
  m[r['relative']]={k:r[k] for k in ('relative','bytes','sha256')}
 if len(m)!=557 or sum(r['bytes'] for r in m.values())!=9695031:raise ValueError('557 closure mismatch')
 result={'schema':'common-CHIRRTL-557-class-hash-metadata-only-v1','class_count':557,'class_bytes':9695031,'classes':[m[k] for k in sorted(m)],'class_payloads_read_staged_or_executed':False}
 with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
 return {'hash_records':557,'referenced_class_bytes_not_read':9695031,'JVM_executed':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();print(json.dumps(rebuild(v.repo_root,v.output),sort_keys=True))
