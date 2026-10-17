"""Read-only 30s verification of a consumer-supplied exact historical SV."""
import argparse,hashlib,json,signal
from pathlib import Path
from check_sv import check,need
P=Path(__file__).resolve().parent
def verify(path):
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'preexisting alarm')
 def timeout(s,f):raise TimeoutError('offline deadline')
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,30)
 try:
  expected=json.loads((P/'SV_INVENTORY.json').read_text());need(path.is_file() and not path.is_symlink(),'regular SV')
  need(path.stat().st_size==expected['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==expected['sha256'],'exact historical SV')
  result=check(path);need(result==expected,'inventory mismatch')
  return {'scope':'FIXED_SV_OFFLINE_INVENTORY_ONLY','pass':True,'original_v7_run_remains_failed':True,'bytes':result['bytes'],'sha256':result['sha256'],'definitions':result['definition_count'],'external_counts':result['external_inventory']['reachable_external_counts'],'linked':False,'numerical':False}
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--sv',type=Path,required=True);x=a.parse_args();print(json.dumps(verify(x.sv),indent=2))
