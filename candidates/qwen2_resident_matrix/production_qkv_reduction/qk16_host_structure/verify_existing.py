"""Read only existing generated IR/classes; never starts a compiler or simulator."""
import argparse,hashlib,json,signal,time
from pathlib import Path
from check_structure import check,need
from check_packed import check_packed
from class_source import source_file
P=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
RECEIPT_SHA='a8ce91353f20935c083022ff9667c804e3aaba600f68e638735eb792e20719e5'
IR_SHA='80aca2cd2cab5758a755fc1b3434b73f0c3887d15395a9f01b0713eaec9d5af9'
def inventory(p,suffix=None):return {str(f.relative_to(p)):sha(f) for f in p.rglob('*') if f.is_file() and (suffix is None or f.suffix==suffix)}
def run(a):
 start=time.monotonic();stop=start+90
 need(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'existing alarm')
 def expired(*unused):raise TimeoutError('offline 90s deadline')
 old=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,90)
 try:
  need(not a.output.exists(),'fresh offline receipt required');a.attempt.resolve(strict=True)
  expected_classes=json.loads((P/'ACTUAL_CLASS_PINS.json').read_text())
  pins=json.loads((P/'SOURCE_PINS.json').read_text());b=json.loads((P/'BASELINE_CLASS_PINS.json').read_text());deps=json.loads((P/'BASELINE_DEPENDENCY_PINS.json').read_text());jdk=json.loads((P/'JDK_PINS.json').read_text())
  need(inventory(a.source_root,'.scala')==b['source_sha256'],'original source92 drift')
  need(inventory(a.attempt/'scala','.scala')==pins and len(pins)==93,'actual source93 drift')
  for root in [a.base_classes,a.attempt/'classes']:
   found=inventory(root);need(all(found.get(n)==h for n,h in b['classes'].items()),'original550 class drift')
   need({n:source_file((root/n).read_bytes()) for n in b['classes']}==b['class_source_files'],'original550 SourceFile drift')
  need(inventory(a.base_classes)==b['classes'],'base extra class')
  actual=inventory(a.attempt/'classes');added=set(actual)-set(b['classes']);expected={'heteronpu/continuous/ProductionQk16HostStructure'+s+'.class' for s in ['', '$','$delayedInit$body']}
  need(added==expected and len(actual)==553,'exact553 class closure');need(all(source_file((a.attempt/'classes'/n).read_bytes())=='ProductionQk16HostStructure.scala' for n in added),'emitter SourceFile')
  need(actual==expected_classes,'actual compiled classes differ from original pre-emit verified inventory')
  for n,h in deps['jars'].items():need(sha(a.cache/n)==h,'dependency drift '+n)
  need(len(deps['jars'])==87,'87 dependency count');java=a.java.resolve(strict=True)
  need(sha(java)==jdk['java_sha256']==deps['java_sha256'],'JDK java drift');need(sha(java.parent.parent/'release')==jdk['java_release_sha256']==deps['java_release_sha256'],'JDK release drift')
  ir=a.attempt/'structure/HostBlockTop.fir';need(ir.stat().st_size==42095784 and sha(ir)==IR_SHA,'actual IR drift')
  structure=check(ir);packed=check_packed(ir)
  need(sha(ir)==IR_SHA,'post read identity drift')
  result=dict(status='PASS_FIXED_IR_PORTABLE_OFFLINE_REVIEW',historical_original_receipt_sha256=RECEIPT_SHA,does_not_rewrite_or_upgrade_generation_receipt=True,java_rerun=False,rtl_simulation=False,numerical=False,source_count=93,base_class_count=550,class_count=553,jar_count=87,postflight=True,elapsed_seconds=time.monotonic()-start,structure=structure,packed_structure=packed)
  need(time.monotonic()<stop,'offline deadline');a.output.write_text(json.dumps(result,indent=2)+'\n')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ['attempt','source-root','base-classes','cache','java','output']:ap.add_argument('--'+n,type=Path,required=True)
 run(ap.parse_args())
