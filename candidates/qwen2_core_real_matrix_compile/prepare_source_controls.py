"""Assemble small source-only controls and class-hash metadata. Never launch Scala/JVM.
No class, JAR, provider SV, model or input payloads are fetched or generated.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent
QWEN='candidates/qwen2_core_client_chirrtl_evidence/source/Qwen2Block.scala'
BASE='candidates/qwen2_core_client_chirrtl_evidence/pins/RETAINED_CLASS_PINS.json'
OVERRIDES='candidates/qwen2_core_client_chirrtl_evidence/evidence/NEW_CLASS_HASHES.json'
def read(root,relative,expected):
 rel=PurePosixPath(relative)
 if rel.is_absolute() or not rel.parts or any(p in ('','..','.') for p in rel.parts) or '\\' in relative:raise ValueError('unsafe relative path')
 p=root.joinpath(*rel.parts)
 if not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise ValueError('regular nonsymlink source required')
 b=p.read_bytes()
 if len(b)!=expected['bytes'] or hashlib.sha256(b).hexdigest()!=expected['sha256']:raise ValueError('exact frozen source hash mismatch '+relative)
 return b

def assemble(repo_root,output,package=HERE):
 repo_root=Path(repo_root).absolute();output=Path(output).absolute();package=Path(package).absolute()
 if repo_root.resolve()!=repo_root or package.resolve()!=package:raise ValueError('symlink source root')
 if output.exists() or output.is_symlink() or output.resolve()!=output:raise ValueError('fresh nonsymlink output required')
 if not output.parent.is_dir():raise ValueError('existing output parent required')
 refs=json.loads((package/'pins/EXISTING_PUBLIC_REFERENCES.json').read_text())['references'];data={}
 for row in refs:data[row['repo_path']]=read(repo_root,row['repo_path'],row)
 files={r['public_path']:read(package,r['public_path'],r['published']) for r in json.loads((package/'pins/SOURCE_PINS.json').read_text())['files']}
 files['reference_source/Qwen2Block.scala']=data[QWEN]
 baseline=json.loads(data[BASE]);old20={r['relative']:r for r in json.loads(data[OVERRIDES])['classes']};delta=json.loads((package/'pins/STAGED_CLASS_DELTA.json').read_text());stage={r['relative']:{k:r[k] for k in ('relative','bytes','sha256')} for r in baseline['classes']}
 if len(stage)!=550:raise ValueError('baseline count')
 for r in delta['override14']:
  if any(old20[r['relative']][k]!=r[k] for k in ('relative','bytes','sha256','source_file')):raise ValueError('override not prior reviewed class')
  if r['source_file'] in delta['exclude_source_files']:raise ValueError('excluded source override')
  stage[r['relative']]={k:r[k] for k in ('relative','bytes','sha256')}
 if len(stage)!=554 or sum(r['bytes'] for r in stage.values())!=9631197:raise ValueError('stage metadata count/bytes')
 files['STAGED_CLASS_HASHES.json']=(json.dumps({'scope':'Metadata only; no class contents staged or executed','classes':[stage[k] for k in sorted(stage)]},indent=2)+'\n').encode()
 output.mkdir()
 for n,b in files.items():
  p=output/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
 return {'source_files':5,'hash_metadata_files':1,'stage_hashes':len(stage),'JVM_or_target_executed':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();print(json.dumps(assemble(args.repo_root,args.output),sort_keys=True))
