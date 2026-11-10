from pathlib import Path
import json,urllib.request,hashlib
R=Path(__file__).resolve().parent;W=R.parents[1]
M=W/'round_20261110T0133/recovery/sources/hetero_cloud_recovery_20261107T2134/candidates/chisel_hybrid_host_20261106/MAVEN_INPUTS.json'
rows=json.loads(M.read_text())['jars'];missing=set(json.loads((R/'HYBRID_DEPENDENCY_AUDIT.json').read_text())['missing_or_mismatch']);out=R/'hybrid_jars';out.mkdir(exist_ok=True);results=[]
for r in rows:
 if r['maven_path'] not in missing:continue
 p=out/Path(r['maven_path']).name
 if p.exists():b=p.read_bytes()
 else:
  with urllib.request.urlopen(r['url'],timeout=30) as f:b=f.read(r['bytes']+1)
 if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('jar pin mismatch '+str(p))
 p.write_bytes(b);results.append({'path':str(p),'url':r['url'],'sha256':r['sha256'],'bytes':len(b)})
 (R/'HYBRID_JAR_RECOVERY.json').write_text(json.dumps(results,indent=2))
print('verified recovered',len(results))
