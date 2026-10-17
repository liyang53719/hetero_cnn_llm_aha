"""Reconstruct exact full Scala closure and command, without executing compiler."""
import hashlib,json,tempfile
from pathlib import Path
from candidates.qwen2_resident_matrix.attention_qk_owner_route import prepare as route
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def need(ok,why):
 if not ok:raise ValueError(why)
def evidence():return json.loads((HERE/'EVIDENCE.json').read_bytes())
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 for n,h in p['own'].items():need(sha(HERE/n)==h,'own evidence drift')
 for n,h in p['sources'].items():need(sha(ROOT/n)==h,'construction source drift')
 return p

def compose(destination,*,original_root,hardfloat_root):
 check();e=evidence();p=e['source_plan'];base=Path(original_root);hf=Path(hardfloat_root)
 need(sha(route.HERE/'pins.json')==p['route_pins_sha256'],'reviewed owner route')
 for n,h in p['base_sha256'].items():need(sha(base/n)==h,'original full-project source drift')
 found={str(f.relative_to(hf)) for f in (hf/'hardfloat/src/main/scala').rglob('*.scala')}
 need(found==set(p['hardfloat_sha256']),'exact twenty HardFloat files required')
 for n,h in p['hardfloat_sha256'].items():need(sha(hf/n)==h,'HardFloat drift')
 out=Path(destination);need(not out.exists(),'fresh source directory');out.mkdir(parents=True)
 for n in p['base_sha256']:
  dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((base/n).read_bytes())
 with tempfile.TemporaryDirectory() as temporary:
  overlay=Path(temporary)/'overlay';route.compose(overlay)
  actual={str(f.relative_to(overlay)):sha(f) for f in overlay.rglob('*.scala')}
  need(actual==p['overlay_sha256'],'exact owner overlay')
  for n in actual:
   dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((overlay/n).read_bytes())
 for n in p['hardfloat_sha256']:
  dest=out/'hardfloat_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((hf/n).read_bytes())
 result={str(f.relative_to(out)):sha(f) for f in out.rglob('*.scala')}
 need(result==p['scala'] and len(result)==83,'full83-source equality');return result

def command(java,cache,source,classes):
 check();e=evidence();cache=Path(cache);source=Path(source)
 need(sha(java)==e['java_sha256'],'Java binary drift')
 need(sha(Path(java).parent.parent/'release')==e['java_release_sha256'],'Java release drift')
 jars=e['dependencies']['jars'];need(len(jars)==87,'exact JAR count')
 for n,h in jars.items():need(sha(cache/n)==h,'JAR drift')
 need({str(f.relative_to(source)):sha(f) for f in source.rglob('*.scala')}==e['source_plan']['scala'],'compiler source drift')
 cp=':'.join(str(cache.resolve()/n) for n in sorted(jars))
 return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(cache.resolve()/e['plugin']),'-language:reflectiveCalls','-d',str(classes)]+[str(p) for p in sorted(source.rglob('*.scala'))]
