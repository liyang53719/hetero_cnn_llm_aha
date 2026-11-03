"""Test-only exact finite-layer inverse, retaining historical assertions."""
import pathlib,json,hashlib
P=pathlib.Path
PIN='818dc6f36b7283d74cf3d759876111c7d322a06c37e89fd9a3eece73bf10511f'
def prior_text(path):
 p=P(path).resolve();repo=P(__file__).resolve().parents[2];rel=str(p.relative_to(repo));raw=p.read_text();index=P(__file__).with_name('FINITE_WATCHDOG_TEST_INVERSE.json').read_bytes()
 if hashlib.sha256(index).hexdigest()!=PIN:raise ValueError('test inverse fixture drift')
 rows=json.loads(index)['files']
 if rel not in rows:return raw
 row=rows[rel];digest=hashlib.sha256(raw.encode()).hexdigest()
 if digest==row['original_sha256']:return raw
 if digest!=row['candidate_sha256']:raise ValueError('test inverse candidate drift')
 for edit in row['inverse']:
  if raw.count(edit['before'])!=edit['count']:raise ValueError('test inverse exact unique fragment')
  raw=raw.replace(edit['before'],edit['after'])
 if hashlib.sha256(raw.encode()).hexdigest()!=row['original_sha256']:raise ValueError('test inverse original digest')
 return raw
def prior_sha(path):return hashlib.sha256(prior_text(path).encode()).hexdigest()
