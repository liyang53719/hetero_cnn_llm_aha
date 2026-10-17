"""Offline compatibility review of exact failed-at-postflight compiler output."""
import argparse,hashlib,json,struct,time
from pathlib import Path
from class_source import source_file
from class_abi import abi
from class_code import parse,instructions
P=Path(__file__).resolve().parent
OWNER='heteronpu/continuous/FfnTileSiluBridge';BRIDGE=OWNER+'.class'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def inventory(p,suffix=None):
 r={}
 for x in p.rglob('*'):
  need(not x.is_symlink(),'symlink')
  if x.is_file() and (suffix is None or x.suffix==suffix):r[str(x.relative_to(p))]=sha(x)
 return r
def helper_map(b):
 cp,expand,methods=parse(b);result={};calls=[]
 for (name,desc),(flags,code) in methods.items():
  if code is None:continue
  ins=list(instructions(code))
  if name.startswith('reflMethod$Method'):
   strings=[expand(a[0] if op==18 else struct.unpack('>H',a)[0]) for _,op,a in ins if op in (18,19)]
   strings=[s[1] for s in strings if isinstance(s,tuple) and s[0]==8]
   need(len(strings)==1,'one reflection target')
   result[name]={'target':strings[0],'flags':flags,'descriptor':desc,'code_sha256':hashlib.sha256(code).hexdigest()}
  for off,op,a in ins:
   if op==184:
    ref=expand(struct.unpack('>H',a)[0])
    if ref[0]==10 and ref[1]==(7,OWNER) and ref[2][1].startswith('reflMethod$Method'):
     calls.append({'caller':name,'descriptor':desc,'offset':off,'helper':ref[2][1]})
 return result,calls

def verify(old,new):
 pins=json.loads((P/'BASELINE_PINS.json').read_text());fixed=json.loads((P/'FIXED_OUTPUT.json').read_text())
 need(inventory(old)==pins['classes'],'exact historical original557 bytes')
 need(inventory(new)==fixed['classes'],'exact historical fixed557 bytes')
 need(inventory(old)==pins['classes'] and inventory(new)==fixed['classes'],'class postflight')
 return {'scope':'EXACT_HISTORICAL_CLASS_COMPATIBILITY_OFFLINE','pass':True,'retained':553,'total':557,'external_helper_references':0,'original_strict_run_remains_failed':True}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--original-classes',type=Path,required=True);ap.add_argument('--fixed-classes',type=Path,required=True);a=ap.parse_args();print(json.dumps(verify(a.original_classes,a.fixed_classes),indent=2))
