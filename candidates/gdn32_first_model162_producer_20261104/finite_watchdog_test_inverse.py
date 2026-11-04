"""Test-only exact finite-layer inverse, retaining historical assertions."""
import pathlib,json,hashlib
P=pathlib.Path
PIN='818dc6f36b7283d74cf3d759876111c7d322a06c37e89fd9a3eece73bf10511f'
PREFILL_PIN='1ac6741f09d83fd05978f7d44d0a88242c15b22cfd0b654155ddf7eaf5fb0cba'
def prefill_base_text(rel,raw):
 """Test-only current bytes -> exact finite-long base; never used by runtime."""
 index=P(__file__).with_name('PREFILL_SUPPLY_TEST_INVERSE.json').read_bytes()
 if hashlib.sha256(index).hexdigest()!=PREFILL_PIN:raise ValueError('prefill test inverse fixture drift')
 doc=json.loads(index)
 if doc['scope']!='TEST_ONLY_EXACT_PREFILL_TO_FINITE_BASE_INVERSE_NOT_PRODUCER_ACCEPTANCE':raise ValueError('prefill test inverse scope')
 row=doc['files'].get(rel)
 if row is None:return raw
 data=raw.encode();digest=hashlib.sha256(data).hexdigest()
 if digest==row['base_sha256'] and len(data)==row['base_bytes']:return raw
 if digest!=row['candidate_sha256'] or len(data)!=row['candidate_bytes']:raise ValueError('prefill test inverse candidate drift')
 boundary=len(data)
 for edit in reversed(row['inverse']):
  start,end=edit['start'],edit['end'];before=edit['before'].encode();after=edit['after'].encode()
  if type(start)is not int or type(end)is not int or not 0<=start<=end<=boundary or end-start!=len(before):raise ValueError('prefill test inverse edit bounds')
  if data[start:end]!=before:raise ValueError('prefill test inverse exact before bytes')
  data=data[:start]+after+data[end:];boundary=start
 if hashlib.sha256(data).hexdigest()!=row['base_sha256'] or len(data)!=row['base_bytes']:raise ValueError('prefill test inverse base digest')
 return data.decode()
def prior_text(path):
 p=P(path).resolve();repo=P(__file__).resolve().parents[2];rel=str(p.relative_to(repo));raw=prefill_base_text(rel,p.read_text());index=P(__file__).with_name('FINITE_WATCHDOG_TEST_INVERSE.json').read_bytes()
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
