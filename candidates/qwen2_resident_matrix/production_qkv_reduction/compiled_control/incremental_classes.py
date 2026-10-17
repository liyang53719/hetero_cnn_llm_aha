"""Reuse pinned production classcompile; compile exactly three control-test sources."""
import hashlib,json,shutil,zipfile
from pathlib import Path
from class_source import source_file
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
TEST_SOURCES={'ProductionQkvProtocolHarness.scala','ProductionQkvProtocolElaborate.scala','ProductionQkvProtocolSpec.scala'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def pins():return json.loads((HERE/'BASELINE_CLASS_PINS.json').read_text())
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
def verify_baseline(root,production):
 p=pins();need(p['source_count']==91 and p['class_count']==545,'baseline count')
 need(p['source_sha256']==production,'baseline production source drift')
 need(inventory(root)==p['classes'],'baseline class identity drift')
 for f in root.rglob('*.class'):
  need(source_file(f.read_bytes()) not in TEST_SOURCES,'old test class in production baseline')
def copy_baseline(root,out):
 shutil.copytree(root,out)
 need(inventory(out)==pins()['classes'],'copied baseline mismatch')
def check_no_shadow(cache,jars):
 baseline=set(pins()['classes'])
 for n in jars:
  with zipfile.ZipFile(cache/n) as z:
   names=set(z.namelist())
   need(not names&baseline,'production class shadow in dependency '+n)
   need(not any('heteronpu/continuous/ProductionQkvProtocol' in x for x in names),'test class shadow in dependency '+n)
def verify_final(root):
 p=pins();actual=inventory(root)
 need(all(actual.get(n)==h for n,h in p['classes'].items()),'reused production class overwritten')
 added=set(actual)-set(p['classes']);need(len(added)==10 and len(actual)==555,'unexpected final class count')
 sources={}
 for n in sorted(added):
  need(n.endswith('.class'),'nonclass output')
  src=source_file((root/n).read_bytes());need(src in TEST_SOURCES,'unexpected added class SourceFile')
  sources[n]=src
 need(set(sources.values())==TEST_SOURCES,'missing compiled harness source')
 return dict(reused_production_classes=545,compiled_source_count=3,complete_source_closure=94,final_class_count=555,original_receipt_sha256=p['original_receipt_sha256'],classes=actual,added_class_sourcefiles=sources,protocol_pass_inherited=False)
def verify_dependency_transition(current,jdk):
 old=json.loads((HERE/'BASELINE_DEPENDENCY_PINS.json').read_text())
 need(len(old['jars'])==87 and len(current['jars'])==106,'dependency counts')
 need(set(old['jars'])-set(current['jars'])==set(current['removed']),'removed baseline deps')
 need(set(current['jars'])-set(old['jars'])==set(current['added']),'added test deps')
 need(all(old['jars'][n]==current['jars'][n] for n in set(old['jars'])&set(current['jars'])),'shared dependency hash drift')
 need(all(old[k]==jdk[k] for k in ['java_sha256','java_release_sha256']),'baseline JDK drift')
