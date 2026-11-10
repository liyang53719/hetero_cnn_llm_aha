from pathlib import Path
import urllib.request,json,hashlib,time
r=Path(__file__).resolve().parent
pin=json.loads((r/'WHEEL_PIN.json').read_text());start=time.monotonic();h=hashlib.sha256();count=0
try:
 with urllib.request.urlopen(pin['url'],timeout=60) as response,(r/'torch.whl.partial').open('xb') as out:
  for b in iter(lambda:response.read(1<<20),b''):
   if time.monotonic()-start>180:raise TimeoutError('180s total acquisition budget')
   count+=len(b)
   if count>pin['expected_bytes']:raise ValueError('wheel exceeds pin size')
   h.update(b);out.write(b)
 if count!=pin['expected_bytes'] or h.hexdigest()!=pin['expected_sha256']:raise ValueError('wheel pin mismatch')
 (r/'torch.whl.partial').rename(r/'torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl')
 result={'status':'VERIFIED_WHEEL_BYTES_ONLY','bytes':count,'sha256':h.hexdigest(),'url':pin['url']}
except Exception as e:result={'status':'ACQUISITION_FAILED','error':repr(e),'bytes':count,'url':pin['url']}
result['seconds']=time.monotonic()-start;(r/'ACQUISITION.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
