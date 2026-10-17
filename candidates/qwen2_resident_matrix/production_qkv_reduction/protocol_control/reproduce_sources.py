"""Reproduce historical control-test source identity; NEVER runs the test."""
from pathlib import Path
import argparse,json,shutil,hashlib
from generate_fixtures import generate
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run(version,out,source_root):
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 pins=json.loads((HERE/'history/VERSIONS.json').read_text())[version]
 out.mkdir(parents=True)
 for n in ['run_protocol.py','owned_compile.py','strict_cleanup.py','FIXTURE_PINS.json','JDK_PINS.json','dependency-lock.json','test_runner_cold.py','test_source_schedule.py']:
  shutil.copyfile(HERE/n,out/n)
 shutil.copytree(HERE/'source',out/'source')
 generate(source_root,out/'fixtures')
 shutil.copyfile(HERE/'history'/(version+'_SOURCE_CLOSURE.json'),out/'SOURCE_CLOSURE.json')
 if version=='v7':shutil.copyfile(HERE/'history/owned_v7.py.txt',out/'owned_compile.py')
 if version in ['v7','v8']:shutil.copyfile(HERE/'history/spec_v8.scala.txt',out/'source/ProductionQkvProtocolSpec.scala')
 for n,h in pins.items():
  if sha(out/n)!=h:raise ValueError('version source drift '+n)
 print('PASS_HISTORICAL_SOURCE_IDENTITY_ONLY '+version+'; no execution')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--version',required=True,choices=['v7','v8','v9']);p.add_argument('--out',required=True,type=Path);p.add_argument('--source-root',required=True,type=Path);a=p.parse_args();run(a.version,a.out,a.source_root)
