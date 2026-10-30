"""Only original official53 locked runtime archives, one shared cache. No install.
Run under strict supervisor with locked free8GiB / owned512MiB / bounded wall.
"""
import argparse,hashlib,importlib.util,json,pathlib,time
P=pathlib.Path
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(v,m):
 if not v:raise ValueError(m)
def run(binding,expected):
 need(sha(binding)==expected,'independent archive binding');b=json.loads(P(binding).read_text())
 for p,h in b['pins'].items():need(sha(p)==h,'original acquisition source pin')
 source=P(b['source_dir']);need(b['pins'].get(str(source/'prepare_runtimes.py'))==sha(source/'prepare_runtimes.py'),'original locked acquire function')
 spec=importlib.util.spec_from_file_location('original_acquire',source/'prepare_runtimes.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);items,specs,_=m.artifacts();union={}
 for x in [*items,*[x for s in specs.values()for x in [*s['artifacts'],s['transformers']]]]:
  k=x['filename'];need(k not in union or (union[k]['sha256'],union[k]['bytes'])==(x['sha256'],x['bytes']),'consistent shared archive');union[k]=x
 need(len(union)==53 and sum(x['bytes']for x in union.values())==305867713,'exact original53 archive union')
 out=P(b['output']);need(not out.exists()and out.is_absolute(),'fresh shared acquisition output');out.mkdir();cache=out/'cache';cache.mkdir();ledger=[];budget=dict(start=time.monotonic(),bytes=0);rows=[]
 for x in union.values():
  p=m.acquire(x,cache,ledger,budget);m.check_wheel_metadata(x,p);rows.append(m.record(p))
 with (out/'ARCHIVES.json').open('x')as f:json.dump(dict(scope='ORIGINAL53_ARCHIVE_ONLY_NO_INSTALL',archives=rows,network_body_bytes=budget['bytes'],logical_fetches=len(ledger)),f,indent=2)
 for p,h in b['pins'].items():need(sha(p)==h,'post acquisition source pin')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--binding',type=P,required=True);a.add_argument('--binding-sha256',required=True);v=a.parse_args();run(v.binding,v.binding_sha256)
