"""Prepare byte-exact historical v3 generation runner; does not execute Java."""
import argparse,hashlib,json,shutil
from pathlib import Path
P=Path(__file__).resolve().parent
def prepare(out):
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 pins=json.loads((P/'OPERATIONAL_PINS.json').read_text())
 for n,h in pins.items():
  if hashlib.sha256((P/n).read_bytes()).hexdigest()!=h:raise ValueError('pin drift '+n)
 out.mkdir(parents=True)
 names=['BASELINE_CLASS_PINS.json','BASELINE_DEPENDENCY_PINS.json','JDK_PINS.json','SOURCE_PINS.json','class_source.py','check_structure.py','run_structure.py','owned_compile.py','strict_cleanup.py','source/ProductionQk16HostStructure.scala']
 for n in names:
  (out/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(P/n,out/n)
 shutil.copyfile(P/'historical_v3_check_packed.py',out/'check_packed.py')
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True);prepare(a.parse_args().out)
