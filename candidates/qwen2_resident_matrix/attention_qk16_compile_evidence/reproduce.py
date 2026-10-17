"""Hash-bound small successor of the existing83-source evidence; no execution."""
import hashlib,json,tempfile,copy
from pathlib import Path
from candidates.qwen2_resident_matrix.attention_qk_owner_compile_evidence import prepare as base
from candidates.qwen2_resident_matrix.attention_qk16_owner_route import prepare as route
HERE=Path(__file__).resolve().parent;ROOT=base.ROOT
sha=base.sha;need=base.need
def encoded(value):return (json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
def evidence():return json.loads((HERE/'EVIDENCE.json').read_bytes())
def check():
 p=json.loads((HERE/'pins.json').read_bytes())
 for n,h in p['own'].items():need(sha(HERE/n)==h,'own evidence drift')
 for n,h in p['sources'].items():need(sha(ROOT/n)==h,'dependency drift')
 base.check();route.check();e=evidence()
 need(sha(base.HERE/'EVIDENCE.json')==e['base_evidence_sha256'] and sha(base.HERE/'pins.json')==e['base_pins_sha256'],'base evidence identity')
 need(sha(route.HERE/'pins.json')==e['executed_route_pins_sha256'],'route identity');return p

def reconstructed():
 check();e=evidence();b=base.evidence();s=copy.deepcopy(b['records']['summary.json']['value']);s.update(e['summary_delta'])
 need(set(e['class_sha256_delta'])<=set(s['classes']) and set(e['source_sha256_delta'])<=set(s['source_sha256']),'replacement-only maps')
 s['classes'].update(e['class_sha256_delta']);s['source_sha256'].update(e['source_sha256_delta'])
 p=copy.deepcopy(b['source_plan']);p.update(e['plan_field_delta']);p['scala'].update(e['source_sha256_delta']);p['overlay_sha256'].update(e['overlay_sha256_delta'])
 need(len(s['classes'])==474 and len(p['scala'])==83 and p['scala']==s['source_sha256'],'exact closure sizes')
 need(hashlib.sha256(encoded(s)).hexdigest()==e['summary_sha256'] and len(encoded(s))==e['summary_bytes'],'summary reconstruction')
 need(hashlib.sha256(encoded(p)).hexdigest()==e['plan_sha256'],'plan reconstruction')
 need(hashlib.sha256(encoded(e['caller'])).hexdigest()==e['caller_sha256'],'caller reconstruction')
 need(hashlib.sha256(encoded(e['filemap'])).hexdigest()==e['filemap_sha256'],'filemap reconstruction')
 old_plan=hashlib.sha256(encoded(b['source_plan'])).hexdigest()
 launcher=(base.HERE/'executed_launcher.txt').read_text().replace('attention_qk_owner_route','attention_qk16_owner_route').replace(old_plan,e['plan_sha256'])
 need(hashlib.sha256(launcher.encode()).hexdigest()==e['launcher_sha256'],'launcher reconstruction')
 return s,p,launcher

def compose(destination,*,original_root,hardfloat_root):
 _,p,_=reconstructed();out=Path(destination)
 base.compose(out,original_root=original_root,hardfloat_root=hardfloat_root)
 with tempfile.TemporaryDirectory() as d:
  o=Path(d)/'overlay';route.compose(o)
  for n in route.TARGETS:(out/n).write_bytes((o/n).read_bytes())
 actual={str(f.relative_to(out)):sha(f) for f in out.rglob('*.scala')}
 need(actual==p['scala'],'successor83-source reconstruction');return actual

def command(java,cache,source,classes):
 _,p,_=reconstructed();e=base.evidence();source=Path(source);cache=Path(cache)
 need(sha(java)==e['java_sha256'] and sha(Path(java).parent.parent/'release')==e['java_release_sha256'],'Java identity')
 for n,h in e['dependencies']['jars'].items():need(sha(cache/n)==h,'locked JAR identity')
 need({str(f.relative_to(source)):sha(f) for f in source.rglob('*.scala')}==p['scala'],'exact compiler inputs')
 cp=':'.join(str(cache.resolve()/n) for n in sorted(e['dependencies']['jars']))
 return [str(java),'-Xmx1024m','-XX:ActiveProcessorCount=1','-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+str(cache.resolve()/e['plugin']),'-language:reflectiveCalls','-d',str(classes)]+[str(f) for f in sorted(source.rglob('*.scala'))]
