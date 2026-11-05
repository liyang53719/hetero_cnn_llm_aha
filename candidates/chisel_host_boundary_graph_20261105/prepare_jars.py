"""Only reviewed Maven compile inputs, no runtime/model/reference acquisition."""
import hashlib,json,pathlib,sys,urllib.request
repo=pathlib.Path(sys.argv[1]).resolve();root=repo/'candidates/fresh_original_top_recovery_20261028'
x=json.loads((root/'SOURCE_AND_TOOLCHAIN_PINS.json').read_text())
if len(x['jars'])!=107:raise ValueError('jar count')
for row in x['jars']:
 rel=pathlib.PurePosixPath(row['maven_path'])
 if rel.is_absolute() or '..' in rel.parts or row['bytes']>70_000_000:raise ValueError('jar bounds')
 if not row['url'].startswith(('https://repo.maven.apache.org/maven2/','https://repo1.maven.org/maven2/')):raise ValueError('Maven source')
 p=root/'cache'/rel;p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  with urllib.request.urlopen(row['url'],timeout=30) as f:data=f.read(row['bytes']+1)
  if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('jar hash')
  with p.open('xb')as f:f.write(data)
 if p.is_symlink() or p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('jar verification')
