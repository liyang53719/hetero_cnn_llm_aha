"""Candidate-only source/JAR acquisition. No compiler, EDA, model or DUT launch."""
import argparse,hashlib,importlib.util,json,pathlib,urllib.request,urllib.error,socket,ssl
P=pathlib.Path
D=P(__file__).resolve().parent
TOOLCHAIN_MANIFEST_SHA256='7c8d4bd1f7a0a080f06161e70361a3c3676ede483703a90986fe9dfcf091d85b'
GENERATION_GATE_SHA256='bf9940b9d85cac7afc5f2a134d1a830cd78b7c515d02874c1c20356eb145cefe'
STATUS_SCHEMA='MODEL_CANDIDATE_JAR_INPUT_STATUS_V1'
REASONS=frozenset({'SOURCE_OR_CONTRACT_REJECTED','JAR_INVENTORY_REJECTED','JAR_CACHE_REJECTED','JAR_MISSING','JAR_CONTENT_REJECTED','JAR_HTTP_ERROR','JAR_NETWORK_ERROR','JAR_TIMEOUT','JAR_IO_ERROR','UNCLASSIFIED_FAILURE'})
class Rejected(ValueError):
 def __init__(self,reason):super().__init__(reason);self.reason=reason

def need(v,reason):
 if not v:raise Rejected(reason)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap,reason):
 p=P(p);need(p.is_absolute()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,reason);return p

def source_inputs(hardware_source='legacy'):
 repo=D.parent.parent;fresh=repo/'candidates/fresh_original_top_recovery_20261028';mp=regular(fresh/'SOURCE_AND_TOOLCHAIN_PINS.json',2<<20,'SOURCE_OR_CONTRACT_REJECTED');need(sha(mp)==TOOLCHAIN_MANIFEST_SHA256,'SOURCE_OR_CONTRACT_REJECTED');original=json.loads(mp.read_text())
 gatepath=regular(D/'candidate_generation_gate.py',1<<20,'SOURCE_OR_CONTRACT_REJECTED');need(sha(gatepath)==GENERATION_GATE_SHA256,'SOURCE_OR_CONTRACT_REJECTED')
 spec=importlib.util.spec_from_file_location('reviewed_model_jar_source_gate',gatepath);gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
 try:
  selection=gate.selected_inputs(repo,hardware_source);contract=selection['contract']
  paths=gate.checked_paths(repo,selection['overlay'],original,contract)
 except (ValueError,KeyError,TypeError,OSError):raise Rejected('SOURCE_OR_CONTRACT_REJECTED')from None
 return fresh,original,paths,contract

def inventory(original):
 rows=original['jars'];need(type(rows)is list and len(rows)==107,'JAR_INVENTORY_REJECTED');seen={}
 for r in rows:
  need(type(r)is dict and set(r)=={'maven_path','url','sha256','bytes','role'},'JAR_INVENTORY_REJECTED');rel=P(r['maven_path'])
  need(not rel.is_absolute()and '..'not in rel.parts and str(rel)==r['maven_path']and rel.suffix=='.jar' ,'JAR_INVENTORY_REJECTED')
  need(r['url']=='https://repo.maven.apache.org/maven2/'+r['maven_path']and type(r['bytes'])is int and 0<r['bytes']<64<<20 and type(r['sha256'])is str and len(r['sha256'])==64 and all(c in '0123456789abcdef'for c in r['sha256'])and r['role']in('classpath','plugin'),'JAR_INVENTORY_REJECTED')
  prior=seen.get(r['maven_path'])
  if prior is not None:need(prior['role']=='classpath'and r['role']=='plugin'and {k:v for k,v in prior.items()if k!='role'}=={k:v for k,v in r.items()if k!='role'},'JAR_INVENTORY_REJECTED')
  else:need(r['role']=='classpath','JAR_INVENTORY_REJECTED');seen[r['maven_path']]=r
 need(sum(r['role']=='classpath'for r in rows)==106 and sum(r['role']=='plugin'for r in rows)==1 and len(seen)==106,'JAR_INVENTORY_REJECTED');return rows

def acquire(cache,row,download):
 q=cache/row['maven_path'];need(all(not p.is_symlink()for p in(q,*q.parents)),'JAR_CACHE_REJECTED')
 if not q.exists():
  need(download,'JAR_MISSING');q.parent.mkdir(parents=True,exist_ok=True)
  with urllib.request.urlopen(row['url'],timeout=60)as f:data=f.read(64<<20)
  need(len(data)==row['bytes']and hashlib.sha256(data).hexdigest()==row['sha256'],'JAR_CONTENT_REJECTED')
  with q.open('xb')as f:f.write(data)
 regular(q,64<<20,'JAR_CACHE_REJECTED');need(q.stat().st_size==row['bytes']and sha(q)==row['sha256'],'JAR_CONTENT_REJECTED')

def run(download=False,verify_only=False,hardware_source='legacy'):
 status=dict(schema=STATUS_SCHEMA,status='INCOMPLETE',reason=None,jar_index=None,http_status=None,source_count=None,required_jar_count=107,verified_jar_count=0,download_requested=download,verify_only=verify_only,compiler_executed=False,numerical_pass=False)
 try:
  fresh,original,paths,contract=source_inputs(hardware_source);status['source_count']=len(paths);rows=inventory(original)
  if verify_only:status['status']='SOURCE_AND_JAR_INVENTORY_VERIFIED_ONLY';return status
  for i,row in enumerate(rows):status['jar_index']=i;acquire(fresh/'cache',row,download);status['verified_jar_count']+=1
  status.update(status='SOURCE_AND_ALL_JAR_BYTES_VERIFIED',jar_index=None);return status
 except Rejected as e:status['reason']=e.reason
 except urllib.error.HTTPError as e:status.update(reason='JAR_HTTP_ERROR',http_status=e.code if type(e.code)is int and 100<=e.code<=599 else None)
 except (TimeoutError,socket.timeout):status['reason']='JAR_TIMEOUT'
 except (urllib.error.URLError,ssl.SSLError):status['reason']='JAR_NETWORK_ERROR'
 except OSError:status['reason']='JAR_IO_ERROR'
 except Exception:status['reason']='UNCLASSIFIED_FAILURE'
 return status

def main():
 ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group();g.add_argument('--download-jars',action='store_true');g.add_argument('--verify-only',action='store_true');ap.add_argument('--status-json',type=P);ap.add_argument('--hardware-source',choices=('legacy','transposed-tile-address-v1','prefill-supply-overlap-v1','gdn-chunk32-abort-v2'),default='legacy');a=ap.parse_args();result=run(a.download_jars,a.verify_only,a.hardware_source);data=(json.dumps(result,sort_keys=True,allow_nan=False)+'\n').encode();need(len(data)<=2048,'UNCLASSIFIED_FAILURE')
 if a.status_json is not None:
  need(a.status_json.is_absolute()and a.status_json.parent.is_dir()and all(not p.is_symlink()for p in(a.status_json,*a.status_json.parents)),'JAR_IO_ERROR')
  with a.status_json.open('xb')as f:f.write(data)
 print('MODEL_JAR_STATUS '+data.decode().strip());return 1 if result['status']=='INCOMPLETE'else 0
if __name__=='__main__':raise SystemExit(main())
